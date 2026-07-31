#
# 计费结算服务
# 接通 ChargingSession → Order → PricingSnapshot → Invoice → Payment 链路
#

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import or_
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
    PricingSnapshot,
    Tariff,
)

logger = logging.getLogger("ocpp_csms")


@dataclass
class SettlementResult:
    already_settled: bool
    balance: Decimal
    currency: str
    charged_amount: Decimal
    energy_kwh: float = 0.0
    price_per_kwh: Decimal = Decimal("0")
    invoice_id: Optional[str] = None


class BillingService:
    """计费与结算"""

    @staticmethod
    def resolve_tariff(
        db: Session,
        tenant_id,
        charge_point_id: str,
        at_time: Optional[datetime] = None,
    ) -> Optional[Tariff]:
        now = at_time or datetime.now(timezone.utc)
        tariff = (
            db.query(Tariff)
            .filter(
                Tariff.is_active.is_(True),
                Tariff.tenant_id == tenant_id,
                Tariff.charge_point_id == charge_point_id,
                Tariff.valid_from <= now,
            )
            .filter((Tariff.valid_until.is_(None)) | (Tariff.valid_until >= now))
            .order_by(Tariff.valid_from.desc())
            .first()
        )
        if tariff:
            return tariff

        cp = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
        if not cp or not cp.site_id:
            return None

        return (
            db.query(Tariff)
            .filter(
                Tariff.is_active.is_(True),
                Tariff.tenant_id == tenant_id,
                Tariff.site_id == cp.site_id,
                Tariff.valid_from <= now,
            )
            .filter((Tariff.valid_until.is_(None)) | (Tariff.valid_until >= now))
            .order_by(Tariff.valid_from.desc())
            .first()
        )

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
        total_amount = (energy_cost + service_fee).quantize(Decimal("0.01"))

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
    def _existing_settlement(
        db: Session,
        session: ChargingSession,
        app_user: AppUser,
    ) -> Optional[SettlementResult]:
        invoice = (
            db.query(Invoice)
            .filter(
                Invoice.tenant_id == session.tenant_id,
                Invoice.session_id == session.id,
                Invoice.status == "paid",
            )
            .first()
        )
        if invoice:
            bal = Decimal(str(app_user.balance or 0))
            return SettlementResult(
                already_settled=True,
                balance=bal,
                currency="COP",
                charged_amount=Decimal(str(invoice.total_amount)),
                energy_kwh=float(invoice.energy_kwh),
                price_per_kwh=Decimal(str(
                    invoice.energy_cost / invoice.energy_kwh
                    if invoice.energy_kwh and float(invoice.energy_kwh) > 0
                    else 0
                )),
                invoice_id=str(invoice.id),
            )

        transaction_number = f"charge_{session.id}"
        existing_tx = (
            db.query(AppWalletTransaction)
            .filter(
                AppWalletTransaction.app_user_id == app_user.id,
                AppWalletTransaction.operator_tenant_id == session.tenant_id,
                or_(
                    AppWalletTransaction.idempotency_key == f"charge:{session.id}",
                    AppWalletTransaction.transaction_number == transaction_number,
                ),
            )
            .first()
        )
        if existing_tx:
            bal = Decimal(str(app_user.balance or 0))
            return SettlementResult(
                already_settled=True,
                balance=bal,
                currency="COP",
                charged_amount=Decimal(str(abs(existing_tx.amount))),
                invoice_id=None,
            )
        return None

    @staticmethod
    def settle_session(
        db: Session,
        session: ChargingSession,
        app_user: AppUser,
    ) -> SettlementResult:
        """
        完整结算：PricingSnapshot → Invoice → Payment → 钱包扣款 → AppWalletTransaction
        """
        # 同一会话的并发 Stop/结算请求串行化，保证钱包只扣一次。
        session = db.query(ChargingSession).filter(
            ChargingSession.id == session.id,
            ChargingSession.tenant_id == session.tenant_id,
        ).with_for_update().one()
        app_user = db.query(AppUser).filter(AppUser.id == app_user.id).with_for_update().one()
        if session.end_time is None and session.meter_stop is None:
            raise ValueError("Session not finished")

        existing = BillingService._existing_settlement(db, session, app_user)
        if existing:
            return existing

        tenant_id = session.tenant_id
        now = datetime.now(timezone.utc)
        tariff = BillingService.resolve_tariff(db, tenant_id, session.charge_point_id, now)
        if not tariff:
            tariff = (
                db.query(Tariff)
                .filter(Tariff.tenant_id == tenant_id, Tariff.is_active.is_(True))
                .order_by(Tariff.valid_from.desc())
                .first()
            )
        if not tariff:
            raise ValueError("No active tariff configured for this charge point")

        costs = BillingService.calculate_cost(session, tariff)
        total = costs["total_amount"]

        order = db.query(Order).filter(
            Order.tenant_id == tenant_id,
            Order.session_id == session.id,
        ).first()
        order_id = order.id if order else None

        snapshot = PricingSnapshot(
            tenant_id=tenant_id,
            tariff_id=tariff.id,
            session_id=session.id,
            order_id=order_id,
            price_per_kwh=costs["price_per_kwh"],
            service_fee=costs["service_fee"],
            snapshot_data={
                "base_price_per_kwh": float(costs["price_per_kwh"]),
                "service_fee": float(costs["service_fee"]),
                "tariff_name": tariff.name if tariff else None,
                "time_based_rules": tariff.time_based_rules if tariff else None,
            },
        )
        db.add(snapshot)
        db.flush()

        invoice_number = generate_invoice_id(order.order_number if order else None)
        invoice = Invoice(
            invoice_number=invoice_number,
            tenant_id=tenant_id,
            session_id=session.id,
            order_id=order_id,
            pricing_snapshot_id=snapshot.id,
            energy_kwh=costs["energy_kwh"],
            duration_minutes=costs["duration_minutes"],
            energy_cost=costs["energy_cost"],
            service_fee=costs["service_fee"],
            total_amount=total,
            status="pending",
            issued_at=now,
        )
        db.add(invoice)
        db.flush()

        bal = Decimal(str(app_user.balance or 0))
        new_bal = bal - total
        if new_bal < 0:
            new_bal = Decimal("0")
        app_user.balance = new_bal

        transaction_number = f"wallet_{invoice_number}"
        wallet_tx = AppWalletTransaction(
            transaction_number=transaction_number,
            app_user_id=app_user.id,
            invoice_id=invoice.id,
            operator_tenant_id=tenant_id,
            charge_point_id=session.charge_point_id,
            type="charge",
            amount=Decimal("0") - total,
            description="Charging settlement",
            idempotency_key=f"charge:{session.id}",
        )
        db.add(wallet_tx)

        payment_number = generate_payment_id(invoice_number)
        payment = Payment(
            payment_number=payment_number,
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            amount=total,
            payment_method="wallet",
            payment_provider="app_wallet",
            transaction_id=transaction_number,
            status="completed",
            completed_at=now,
        )
        db.add(payment)

        invoice.status = "paid"
        invoice.paid_at = now
        session.payment_status = "paid"

        if order:
            order.status = "completed"
            if not order.end_time:
                order.end_time = session.end_time or now

        db.add(app_user)
        db.commit()
        db.refresh(app_user)

        logger.info(
            "Session settled: session_id=%s invoice_number=%s amount=%s",
            session.id,
            invoice_number,
            total,
        )

        return SettlementResult(
            already_settled=False,
            balance=Decimal(str(app_user.balance or 0)),
            currency="COP",
            charged_amount=Decimal(str(total)),
            energy_kwh=float(costs["energy_kwh"]),
            price_per_kwh=Decimal(str(costs["price_per_kwh"])),
            invoice_id=str(invoice.id),
        )
