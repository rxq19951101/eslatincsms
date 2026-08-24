#
# 计费结算服务
# 接通 ChargingSession → Order → PricingSnapshot → Invoice → Payment 链路
#

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.id_generator import generate_invoice_id, generate_payment_id
from app.database.models import (
    AppUser,
    AppWalletTransaction,
    ChargePoint,
    ChargingSession,
    Invoice,
    Order,
    Payment,
    PaymentOrder,
    PricingSnapshot,
    Tariff,
)
from app.services.pricing_service import PricingService

logger = logging.getLogger("ocpp_csms")


@dataclass
class SettlementResult:
    already_settled: bool
    balance: Optional[Decimal]
    currency: str
    charged_amount: Decimal
    energy_kwh: float = 0.0
    price_per_kwh: Decimal = Decimal("0")
    invoice_id: Optional[str] = None
    settlement_method: str = "wallet"
    payment_status: str = "pending"
    payment_order_id: Optional[str] = None
    next_action: Optional[Dict[str, Any]] = None


class BillingService:
    """计费与结算"""

    # Mercado Pago Colombia sandbox/production payment rails do not accept
    # very small charging totals reliably. Product policy also requires every
    # paid charging session to have a minimum payable amount. Keep this as a
    # Decimal at the billing boundary so every settlement method shares the
    # same Invoice authority without introducing a database field or float.
    # Mercado Pago Colombia Sandbox rejects 1,010 COP and below with 2072;
    # 1,011 COP is the lowest amount verified as approved with the fixed
    # EsLatin test application/card. Keep the provider-compatible floor at
    # the billing authority so all settlement methods share it.
    MINIMUM_PAID_CHARGING_AMOUNT = Decimal("1011.00")

    @staticmethod
    def _minimum_paid_total(total: Decimal, *, pricing_mode: str = "paid") -> Decimal:
        """Apply the paid-session floor while preserving explicit free pricing."""
        normalized = Decimal(str(total)).quantize(Decimal("0.01"))
        if pricing_mode == "free":
            return normalized
        return max(normalized, BillingService.MINIMUM_PAID_CHARGING_AMOUNT)

    @staticmethod
    def resolve_tariff(
        db: Session,
        tenant_id,
        charge_point_id: str,
        at_time: Optional[datetime] = None,
    ) -> Optional[Tariff]:
        pricing = PricingService.resolve(db, tenant_id, charge_point_id, at_time)
        return pricing.tariff if pricing.is_available else None

    @staticmethod
    def _energy_kwh(session: ChargingSession) -> Decimal:
        if session.meter_stop is None or session.meter_start is None:
            return Decimal("0")
        try:
            wh = Decimal(str(session.meter_stop - session.meter_start))
            return (wh / Decimal("1000")).quantize(Decimal("0.001")) if wh > 0 else Decimal("0")
        except Exception:
            return Decimal("0")

    @staticmethod
    def _duration_minutes(session: ChargingSession) -> Decimal:
        if not session.start_time:
            return Decimal("0")
        end = session.end_time or datetime.now(timezone.utc)
        delta = end - session.start_time
        return Decimal(str(max(delta.total_seconds(), 0) / 60)).quantize(Decimal("0.01"))

    @staticmethod
    def _price_for_time(tariff: Tariff, at_time: datetime) -> Decimal:
        """根据时段规则或基础电价返回 kWh 单价。"""
        rules = tariff.time_based_rules
        if rules and isinstance(rules, list):
            hour = at_time.hour
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                start_h = rule.get("start_hour", 0)
                end_h = rule.get("end_hour", 24)
                if start_h <= hour < end_h:
                    price = rule.get("price_per_kwh")
                    if price is not None:
                        return Decimal(str(price))
        return Decimal(str(tariff.base_price_per_kwh or 0))

    @staticmethod
    def calculate_cost(
        session: ChargingSession,
        tariff: Optional[Tariff],
    ) -> Dict[str, Any]:
        energy_kwh = BillingService._energy_kwh(session)
        duration_minutes = BillingService._duration_minutes(session)

        price_per_kwh = Decimal("0")
        service_fee = Decimal("0")
        if tariff:
            ref_time = session.end_time or session.start_time or datetime.now(timezone.utc)
            price_per_kwh = BillingService._price_for_time(tariff, ref_time)
            service_fee = Decimal(str(tariff.service_fee or 0))

        energy_cost = (energy_kwh * price_per_kwh).quantize(Decimal("0.01"))
        total_amount = BillingService._minimum_paid_total(
            energy_cost + service_fee,
        )

        return {
            "energy_kwh": energy_kwh,
            "duration_minutes": duration_minutes,
            "price_per_kwh": price_per_kwh,
            "service_fee": service_fee,
            "energy_cost": energy_cost,
            "total_amount": total_amount,
            "tariff": tariff,
        }

    @staticmethod
    def calculate_snapshot_cost(
        session: ChargingSession,
        snapshot: PricingSnapshot,
    ) -> Dict[str, Any]:
        energy_kwh = BillingService._energy_kwh(session)
        duration_minutes = BillingService._duration_minutes(session)
        price_per_kwh = Decimal(str(snapshot.price_per_kwh or 0))
        service_fee = Decimal(str(snapshot.service_fee or 0))
        energy_cost = (energy_kwh * price_per_kwh).quantize(Decimal("0.01"))
        pricing_mode = (
            snapshot.snapshot_data.get("pricing_mode")
            if isinstance(snapshot.snapshot_data, dict)
            else "paid"
        )
        total_amount = BillingService._minimum_paid_total(
            energy_cost + service_fee,
            pricing_mode=str(pricing_mode or "paid"),
        )
        return {
            "energy_kwh": energy_kwh,
            "duration_minutes": duration_minutes,
            "price_per_kwh": price_per_kwh,
            "service_fee": service_fee,
            "energy_cost": energy_cost,
            "total_amount": total_amount,
        }

    @staticmethod
    def _invoice_for_session(
        db: Session,
        session: ChargingSession,
    ) -> Optional[Invoice]:
        return (
            db.query(Invoice)
            .filter(
                Invoice.tenant_id == session.tenant_id,
                Invoice.session_id == session.id,
            )
            .with_for_update()
            .first()
        )

    @staticmethod
    def _settlement_method(
        order: Optional[Order],
        snapshot: PricingSnapshot,
    ) -> str:
        """Resolve the branch from trusted Order/pricing data only."""
        snapshot_data = snapshot.snapshot_data
        if isinstance(snapshot_data, dict) and snapshot_data.get("pricing_mode") == "free":
            return "free"
        pre_authorization = order.pre_authorization if order else None
        if isinstance(pre_authorization, dict):
            method = pre_authorization.get("settlement_method")
            if method in {"wallet", "direct_card", "free"}:
                return str(method)
        return "wallet"

    @staticmethod
    def _payment_price(invoice: Invoice) -> Decimal:
        energy = Decimal(str(invoice.energy_kwh or 0))
        if energy <= 0:
            return Decimal("0.00")
        return (Decimal(str(invoice.energy_cost or 0)) / energy).quantize(
            Decimal("0.01")
        )

    @staticmethod
    def _result(
        *,
        invoice: Invoice,
        app_user: AppUser,
        already_settled: bool,
        settlement_method: str,
        payment_status: str,
        payment_order_id: Optional[str] = None,
        balance: Optional[Decimal] = None,
        next_action: Optional[Dict[str, Any]] = None,
    ) -> SettlementResult:
        return SettlementResult(
            already_settled=already_settled,
            balance=balance,
            currency="COP",
            charged_amount=Decimal(str(invoice.total_amount)),
            energy_kwh=float(invoice.energy_kwh or 0),
            price_per_kwh=BillingService._payment_price(invoice),
            invoice_id=str(invoice.id),
            settlement_method=settlement_method,
            payment_status=payment_status,
            payment_order_id=payment_order_id,
            next_action=next_action,
        )

    @staticmethod
    def _create_invoice(
        db: Session,
        *,
        session: ChargingSession,
        order: Optional[Order],
        snapshot: PricingSnapshot,
        costs: Dict[str, Any],
        issued_at: datetime,
    ) -> Invoice:
        invoice = Invoice(
            invoice_number=generate_invoice_id(order.order_number if order else None),
            tenant_id=session.tenant_id,
            session_id=session.id,
            order_id=order.id if order else None,
            pricing_snapshot_id=snapshot.id,
            energy_kwh=costs["energy_kwh"],
            duration_minutes=costs["duration_minutes"],
            energy_cost=costs["energy_cost"],
            service_fee=costs["service_fee"],
            total_amount=costs["total_amount"],
            status="pending",
            issued_at=issued_at,
        )
        db.add(invoice)
        try:
            db.flush()
            return invoice
        except IntegrityError:
            # uq_invoices_session is the last line of defence for concurrent
            # Stop/settle requests.
            db.rollback()
            existing = BillingService._invoice_for_session(db, session)
            if existing is None:
                raise
            return existing

    @staticmethod
    def _direct_payment_order(
        db: Session,
        *,
        session: ChargingSession,
        app_user: AppUser,
        invoice: Invoice,
        order: Optional[Order],
        now: datetime,
    ) -> PaymentOrder:
        idempotency_key = f"charging-settlement:{session.id}"
        payment_order = (
            db.query(PaymentOrder)
            .filter(
                PaymentOrder.app_user_id == app_user.id,
                PaymentOrder.idempotency_key == idempotency_key,
            )
            .with_for_update()
            .first()
        )
        if payment_order is not None:
            if Decimal(str(payment_order.amount)) != Decimal(str(invoice.total_amount)):
                raise ValueError("Existing direct-card PaymentOrder amount does not match Invoice")
            session.payment_order_id = payment_order.id
            return payment_order

        pre_authorization = order.pre_authorization if order else {}
        merchant = (
            pre_authorization.get("merchant")
            if isinstance(pre_authorization, dict)
            else None
        )
        if not isinstance(merchant, dict):
            merchant = {}
        metadata = {
            "schema_version": 1,
            "payment_purpose": "charging_direct",
            "settlement_method": "direct_card",
            "invoice_id": str(invoice.id),
            "session_id": str(session.id),
            "operator_tenant_id": str(session.tenant_id),
            "checkout_session_id": (
                str(pre_authorization.get("checkout_session_id"))
                if isinstance(pre_authorization, dict)
                and pre_authorization.get("checkout_session_id")
                else None
            ),
            "merchant": {
                key: merchant[key]
                for key in ("merchant_mode", "merchant_account_ref", "provider")
                if key in merchant
            },
        }
        payment_order = PaymentOrder(
            app_user_id=app_user.id,
            type="charging",
            amount=Decimal(str(invoice.total_amount)),
            currency="COP",
            payment_provider=str(merchant.get("provider") or "mercadopago"),
            idempotency_key=idempotency_key,
            status="created",
            expires_at=now + timedelta(minutes=30),
            payment_deadline_at=now + timedelta(minutes=60),
            order_metadata=metadata,
        )
        db.add(payment_order)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            payment_order = (
                db.query(PaymentOrder)
                .filter(
                    PaymentOrder.app_user_id == app_user.id,
                    PaymentOrder.idempotency_key == idempotency_key,
                )
                .with_for_update()
                .one()
            )
            if Decimal(str(payment_order.amount)) != Decimal(str(invoice.total_amount)):
                raise ValueError("Existing direct-card PaymentOrder amount does not match Invoice")
        session.payment_order_id = payment_order.id
        return payment_order

    @staticmethod
    def _complete_direct_card(
        db: Session,
        *,
        invoice: Invoice,
        session: ChargingSession,
        order: Optional[Order],
        payment_order: PaymentOrder,
        now: datetime,
    ) -> None:
        payment = (
            db.query(Payment)
            .filter(
                Payment.invoice_id == invoice.id,
                Payment.status == "completed",
            )
            .with_for_update()
            .first()
        )
        if payment is None:
            db.add(Payment(
                payment_number=generate_payment_id(invoice.invoice_number),
                tenant_id=invoice.tenant_id,
                invoice_id=invoice.id,
                amount=Decimal(str(invoice.total_amount)),
                payment_method="direct_card",
                payment_provider=payment_order.payment_provider,
                transaction_id=(
                    payment_order.mercadopago_payment_id or str(payment_order.id)
                ),
                status="completed",
                completed_at=now,
            ))
        payment_order.status = "approved"
        payment_order.paid_at = payment_order.paid_at or now
        invoice.status = "paid"
        invoice.paid_at = invoice.paid_at or now
        session.payment_status = "paid"
        if order:
            order.status = "completed"

    @staticmethod
    def _finish_existing_invoice(
        db: Session,
        *,
        invoice: Invoice,
        session: ChargingSession,
        app_user: AppUser,
        order: Optional[Order],
        snapshot: PricingSnapshot,
        now: datetime,
    ) -> Optional[SettlementResult]:
        method = BillingService._settlement_method(order, snapshot)
        if invoice.status == "paid":
            return BillingService._result(
                invoice=invoice,
                app_user=app_user,
                already_settled=True,
                settlement_method=method,
                payment_status="paid",
                balance=(
                    Decimal(str(app_user.balance or 0))
                    if method == "wallet" else None
                ),
                payment_order_id=(
                    str(session.payment_order_id)
                    if session.payment_order_id else None
                ),
            )
        if method != "direct_card":
            return None

        payment_order = (
            db.query(PaymentOrder)
            .filter(
                PaymentOrder.app_user_id == app_user.id,
                PaymentOrder.idempotency_key == f"charging-settlement:{session.id}",
            )
            .with_for_update()
            .first()
        )
        if payment_order is None:
            return None
        session.payment_order_id = payment_order.id
        if payment_order.status == "approved":
            BillingService._complete_direct_card(
                db,
                invoice=invoice,
                session=session,
                order=order,
                payment_order=payment_order,
                now=now,
            )
            return BillingService._result(
                invoice=invoice,
                app_user=app_user,
                already_settled=False,
                settlement_method=method,
                payment_status="paid",
                payment_order_id=str(payment_order.id),
                next_action=(
                    payment_order.order_metadata.get("next_action")
                    if isinstance(payment_order.order_metadata, dict)
                    else None
                ),
            )
        if payment_order.status in {"declined", "error", "expired", "voided"}:
            session.payment_status = "unpaid"
            payment_status = "unpaid"
        elif payment_order.status == "created":
            # The main direct-card branch owns the external provider call after
            # the prepare transaction commits.  Do not report a second status
            # path here.
            return None
        else:
            session.payment_status = "pending"
            payment_status = (
                "action_required"
                if isinstance(payment_order.order_metadata, dict)
                and payment_order.order_metadata.get("next_action")
                else "processing"
            )
        return BillingService._result(
            invoice=invoice,
            app_user=app_user,
            already_settled=False,
            settlement_method=method,
            payment_status=payment_status,
            payment_order_id=str(payment_order.id),
        )

    @staticmethod
    def pay_unpaid_charge(
        db: Session,
        *,
        app_user_id,
        session_id,
        idempotency_key: str,
    ) -> SettlementResult:
        """Atomically settle an existing unpaid Invoice from the wallet."""
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("Idempotency-Key is required")
        session = db.query(ChargingSession).filter(
            ChargingSession.id == session_id,
            ChargingSession.app_user_id == app_user_id,
        ).with_for_update().first()
        if session is None:
            raise LookupError("Unpaid charging session not found")
        user = db.query(AppUser).filter(AppUser.id == app_user_id).with_for_update().one()
        invoice = db.query(Invoice).filter(
            Invoice.session_id == session.id,
            Invoice.tenant_id == session.tenant_id,
        ).with_for_update().one_or_none()
        if invoice is None:
            raise LookupError("Unpaid charging invoice not found")
        total = Decimal(str(invoice.total_amount)).quantize(Decimal("0.01"))
        if total <= Decimal("0.00") or invoice.status not in {"pending", "paid"}:
            raise ValueError("Unpaid charging invoice is invalid")
        if invoice.status == "paid":
            session.payment_status = "paid"
            db.commit()
            return BillingService._result(
                invoice=invoice,
                app_user=user,
                already_settled=True,
                settlement_method="wallet",
                payment_status="paid",
                balance=Decimal(str(user.balance or 0)),
            )
        if session.payment_status != "unpaid":
            raise LookupError("Charging session is not unpaid")

        balance = Decimal(str(user.balance or 0))
        if balance < total:
            session.payment_status = "unpaid"
            db.commit()
            return BillingService._result(
                invoice=invoice,
                app_user=user,
                already_settled=False,
                settlement_method="wallet",
                payment_status="unpaid",
                balance=balance,
            )

        ledger_id = f"unpaid_wallet:{invoice.id}"
        existing_ledger = db.query(AppWalletTransaction).filter(
            AppWalletTransaction.invoice_id == invoice.id,
            AppWalletTransaction.type == "charge",
        ).with_for_update().first()
        if existing_ledger is not None:
            if Decimal(str(existing_ledger.amount)) != -total:
                raise ValueError("Unpaid wallet ledger does not match Invoice")
            raise ValueError("Unpaid wallet ledger exists without a paid Invoice")
        payment = db.query(Payment).filter(
            Payment.invoice_id == invoice.id,
            Payment.status == "completed",
        ).with_for_update().first()
        if payment is not None:
            raise ValueError("Unpaid Invoice already has a completed Payment")

        user.balance = balance - total
        db.add(AppWalletTransaction(
            transaction_number=ledger_id,
            app_user_id=user.id,
            invoice_id=invoice.id,
            operator_tenant_id=session.tenant_id,
            charge_point_id=session.charge_point_id,
            type="charge",
            amount=-total,
            description="Unpaid charging settlement",
            idempotency_key=idempotency_key,
        ))
        db.add(Payment(
            payment_number=generate_payment_id(invoice.invoice_number),
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            amount=total,
            payment_method="wallet",
            payment_provider="app_wallet",
            transaction_id=ledger_id,
            status="completed",
            completed_at=datetime.now(timezone.utc),
        ))
        invoice.status = "paid"
        invoice.paid_at = invoice.paid_at or datetime.now(timezone.utc)
        session.payment_status = "paid"
        db.commit()
        return BillingService._result(
            invoice=invoice,
            app_user=user,
            already_settled=False,
            settlement_method="wallet",
            payment_status="paid",
            balance=Decimal(str(user.balance or 0)),
        )

    @staticmethod
    def settle_session(
        db: Session,
        session: ChargingSession,
        app_user: AppUser,
    ) -> SettlementResult:
        """Create one authoritative Invoice and settle its trusted branch."""
        session = db.query(ChargingSession).filter(
            ChargingSession.id == session.id,
            ChargingSession.tenant_id == session.tenant_id,
        ).with_for_update().one()
        app_user = db.query(AppUser).filter(
            AppUser.id == app_user.id,
        ).with_for_update().one()
        if session.end_time is None and session.meter_stop is None:
            raise ValueError("Session not finished")

        tenant_id = session.tenant_id
        now = datetime.now(timezone.utc)
        order = db.query(Order).filter(
            Order.tenant_id == tenant_id,
            Order.session_id == session.id,
        ).with_for_update().first()
        snapshot = (
            db.query(PricingSnapshot)
            .filter(
                PricingSnapshot.tenant_id == tenant_id,
                PricingSnapshot.session_id == session.id,
            )
            .order_by(PricingSnapshot.snapshot_time.asc())
            .first()
        )
        if snapshot is None:
            pricing = PricingService.resolve(
                db, tenant_id, session.charge_point_id, session.start_time
            )
            if not pricing.is_available:
                raise ValueError("No active tariff configured for this charge point at session start")
            snapshot = PricingService.create_session_snapshot(db, session, pricing)
        if snapshot.order_id is None and order is not None:
            snapshot.order_id = order.id

        invoice = BillingService._invoice_for_session(db, session)
        if invoice is not None:
            existing_result = BillingService._finish_existing_invoice(
                db,
                invoice=invoice,
                session=session,
                app_user=app_user,
                order=order,
                snapshot=snapshot,
                now=now,
            )
            if existing_result is not None:
                db.commit()
                return existing_result

        costs = BillingService.calculate_snapshot_cost(session, snapshot)
        invoice = invoice or BillingService._create_invoice(
            db,
            session=session,
            order=order,
            snapshot=snapshot,
            costs=costs,
            issued_at=now,
        )
        method = BillingService._settlement_method(order, snapshot)
        total = Decimal(str(invoice.total_amount))

        if method == "free":
            if total != Decimal("0.00"):
                raise ValueError("Free settlement requires a zero COP Invoice")
            payment = (
                db.query(Payment)
                .filter(Payment.invoice_id == invoice.id, Payment.status == "completed")
                .first()
            )
            if payment is None:
                db.add(Payment(
                    payment_number=generate_payment_id(invoice.invoice_number),
                    tenant_id=tenant_id,
                    invoice_id=invoice.id,
                    amount=Decimal("0.00"),
                    payment_method="free",
                    payment_provider="internal",
                    transaction_id=f"free:{invoice.id}",
                    status="completed",
                    completed_at=now,
                ))
            invoice.status = "paid"
            invoice.paid_at = invoice.paid_at or now
            session.payment_status = "paid"
            if order:
                order.status = "completed"
            db.commit()
            return BillingService._result(
                invoice=invoice,
                app_user=app_user,
                already_settled=False,
                settlement_method=method,
                payment_status="paid",
                balance=Decimal(str(app_user.balance or 0)),
            )

        if method == "direct_card":
            if total <= Decimal("0.00"):
                raise ValueError("Direct-card settlement requires a positive Invoice")
            payment_order = BillingService._direct_payment_order(
                db,
                session=session,
                app_user=app_user,
                invoice=invoice,
                order=order,
                now=now,
            )
            if payment_order.status == "approved":
                BillingService._complete_direct_card(
                    db,
                    invoice=invoice,
                    session=session,
                    order=order,
                    payment_order=payment_order,
                    now=now,
                )
                payment_status = "paid"
            elif payment_order.status in {"declined", "error", "expired", "voided"}:
                session.payment_status = "unpaid"
                payment_status = "unpaid"
            else:
                session.payment_status = "pending"
                payment_status = "processing"
            checkout_session_id = (payment_order.order_metadata or {}).get(
                "checkout_session_id"
            )
            if payment_order.status == "created" and checkout_session_id:
                # Prepare and commit first; the provider call must not hold a
                # database row lock across the network boundary.
                db.commit()
                from app.services.payment_reconciliation import (
                    PaymentReconciliationService,
                )

                PaymentReconciliationService().start_payment_order(
                    db,
                    payment_order_id=payment_order.id,
                )
                invoice = db.query(Invoice).filter(Invoice.id == invoice.id).one()
                session = db.query(ChargingSession).filter(
                    ChargingSession.id == session.id
                ).one()
                payment_order = db.query(PaymentOrder).filter(
                    PaymentOrder.id == payment_order.id
                ).one()
                if invoice.status == "paid":
                    payment_status = "paid"
                elif payment_order.status in {"declined", "error", "expired", "voided"}:
                    payment_status = "unpaid"
                    session.payment_status = "unpaid"
                else:
                    payment_status = (
                        "action_required"
                        if isinstance(payment_order.order_metadata, dict)
                        and payment_order.order_metadata.get("next_action")
                        else "processing"
                    )
                db.commit()
            db.commit()
            return BillingService._result(
                invoice=invoice,
                app_user=app_user,
                already_settled=False,
                settlement_method=method,
                payment_status=payment_status,
                payment_order_id=str(payment_order.id),
                next_action=(
                    payment_order.order_metadata.get("next_action")
                    if isinstance(payment_order.order_metadata, dict)
                    else None
                ),
            )

        balance = Decimal(str(app_user.balance or 0))
        if total > balance:
            # Insufficient funds leave both balance and Invoice amount intact.
            session.payment_status = "unpaid"
            db.commit()
            return BillingService._result(
                invoice=invoice,
                app_user=app_user,
                already_settled=False,
                settlement_method="wallet",
                payment_status="unpaid",
                balance=balance,
            )

        transaction_number = f"wallet_{invoice.invoice_number}"
        if total > Decimal("0.00"):
            db.add(AppWalletTransaction(
                transaction_number=transaction_number,
                app_user_id=app_user.id,
                invoice_id=invoice.id,
                operator_tenant_id=tenant_id,
                charge_point_id=session.charge_point_id,
                type="charge",
                amount=Decimal("0") - total,
                description="Charging settlement",
                idempotency_key=f"charge:{session.id}",
            ))
        app_user.balance = balance - total
        db.add(Payment(
            payment_number=generate_payment_id(invoice.invoice_number),
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            amount=total,
            payment_method="wallet",
            payment_provider="app_wallet",
            transaction_id=transaction_number,
            status="completed",
            completed_at=now,
        ))
        invoice.status = "paid"
        invoice.paid_at = now
        session.payment_status = "paid"
        if order:
            order.status = "completed"
            if not order.end_time:
                order.end_time = session.end_time or now
        db.commit()
        db.refresh(app_user)
        logger.info(
            "Session settled: session_id=%s invoice_number=%s amount=%s method=%s",
            session.id,
            invoice.invoice_number,
            total,
            method,
        )
        return BillingService._result(
            invoice=invoice,
            app_user=app_user,
            already_settled=False,
            settlement_method="wallet",
            payment_status="paid",
            balance=Decimal(str(app_user.balance or 0)),
        )
