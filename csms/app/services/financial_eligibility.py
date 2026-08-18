"""PAY-MP-002 financial eligibility and charging admission decisions.

This module is the only owner of the platform-level D1 financial decision.
It deliberately does not inspect UI flags, Redis, provider payloads, or rail
controls while evaluating financial facts.  Resource/rail checks are composed
by :class:`ChargingAdmissionPreflight`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping
from uuid import UUID, uuid4

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.database.models import (
    AppUser,
    ChargePoint,
    ChargebackCase,
    ChargingSession,
    FinancialEligibilityDecision,
    Invoice,
    Payment,
    PaymentAllocation,
    PaymentOrder,
    QrToken,
    OutboxEvent,
    ReconciliationException,
    ReconciliationItem,
    RecoveryAttempt,
    RefundAttempt,
    RefundCase,
    EVSE,
)
from app.services.payment_providers.merchant_context import (
    MerchantContextError,
    PaymentPurpose,
    PlatformMerchantAccountResolver,
)
from app.services.pricing_service import PricingMode, PricingService
from app.services.qr_service import resolve_qr_token
from app.services.runtime_rail_control import RuntimeRailControlService


FINANCIAL_OPERATION = "paid_charging_admission"
DOMAIN_STATUSES = {"eligible", "blocked", "recheck_required", "unknown"}
PUBLIC_STATUS = {"recheck_required": "evaluating"}
REASON_CODES = {
    "open_invoice",
    "recovery_processing",
    "recovery_unknown",
    "refund_or_chargeback",
    "funds_unknown",
    "reconciliation_mismatch",
}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _utc(value)
    return normalized.isoformat().replace("+00:00", "Z") if normalized else None


def _resource(resource_type: str, resource_id: UUID | str) -> dict[str, str]:
    return {"type": resource_type, "id": str(resource_id)}


def _reason_priority(reason: str) -> int:
    return {
        "recovery_unknown": 0,
        "funds_unknown": 1,
        "reconciliation_mismatch": 2,
        "refund_or_chargeback": 3,
        "recovery_processing": 4,
        "open_invoice": 5,
    }.get(reason, 99)


@dataclass(frozen=True)
class FinancialEligibilityResult:
    """Canonical evaluator result; ``recheck_required`` is domain state."""

    app_user_id: UUID
    operation: str
    status: str
    reason_codes: tuple[str, ...]
    blocking_resources: tuple[Mapping[str, str], ...]
    evaluated_at: datetime
    decision_version: int
    source_watermark: str

    @property
    def public_status(self) -> str:
        return PUBLIC_STATUS.get(self.status, self.status)

    def public_projection(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.public_status,
            "reason_codes": list(self.reason_codes),
            "blocking_resources": [dict(item) for item in self.blocking_resources],
            "allowed_actions": (
                ["view_unpaid_charges", "contact_support"]
                if self.status != "eligible"
                else ["start_charging"]
            ),
            "evaluated_at": _iso(self.evaluated_at),
            "version": self.decision_version,
        }


@dataclass(frozen=True)
class RailEligibility:
    axis: str
    status: str
    matched_scope_refs: tuple[str, ...]
    version: int
    evaluated_at: datetime

    def public_projection(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "status": self.status,
            "matched_scope_refs": list(self.matched_scope_refs),
            "evaluated_at": _iso(self.evaluated_at),
            "version": self.version,
        }


@dataclass(frozen=True)
class ChargingAdmissionDecision:
    resource: Mapping[str, Any]
    financial_eligibility: FinancialEligibilityResult
    rail_eligibility: RailEligibility
    decision: str

    def public_projection(self) -> dict[str, Any]:
        return {
            "resource": dict(self.resource),
            "financial_eligibility": self.financial_eligibility.public_projection(),
            "rail_eligibility": self.rail_eligibility.public_projection(),
            "decision": self.decision,
            "allowed_actions": ["start_charging"] if self.decision == "allowed" else ["refresh", "contact_support"],
        }


class FinancialEligibilityEvaluator:
    """Rebuild the one platform-level financial eligibility decision."""

    @staticmethod
    def _ownership_clause(app_user_id: UUID):
        user_id = str(app_user_id)
        id_tag = f"APP{user_id.replace('-', '')[:17]}"
        return or_(
            ChargingSession.app_user_id == app_user_id,
            ChargingSession.user_id == user_id,
            ChargingSession.id_tag == id_tag,
        )

    @staticmethod
    def _fact_timestamp(row: Any) -> datetime | None:
        timestamps = [
            timestamp
            for timestamp in (
                _utc(getattr(row, name, None))
                for name in ("updated_at", "created_at", "evaluated_at")
            )
            if timestamp is not None
        ]
        return max(timestamps) if timestamps else None

    @classmethod
    def _watermark(cls, rows: Iterable[Any], user: AppUser) -> str:
        facts = []
        latest = _utc(user.updated_at) or _utc(user.created_at)
        for row in rows:
            timestamp = cls._fact_timestamp(row)
            latest = max((latest, timestamp), default=latest)
            facts.append(
                ":".join(
                    [
                        row.__class__.__name__,
                        str(getattr(row, "id", "")),
                        str(getattr(row, "version", "")),
                        str(getattr(row, "status", "")),
                        _iso(timestamp) or "",
                    ]
                )
            )
        digest = hashlib.sha256("|".join(sorted(facts)).encode("utf-8")).hexdigest()[:24]
        return f"financial-facts:{_iso(latest) or 'none'}:{digest}"

    @classmethod
    def evaluate(
        cls,
        db: Session,
        *,
        app_user_id: UUID,
        operation: str = FINANCIAL_OPERATION,
    ) -> FinancialEligibilityResult:
        if operation != FINANCIAL_OPERATION:
            raise ValueError("Unsupported financial eligibility operation")

        user = db.query(AppUser).filter(AppUser.id == app_user_id).first()
        if user is None:
            raise ValueError("App user is not available")

        sessions = db.query(ChargingSession).filter(cls._ownership_clause(app_user_id)).all()
        session_ids = {row.id for row in sessions}
        invoices = (
            db.query(Invoice).filter(Invoice.session_id.in_(session_ids)).all()
            if session_ids
            else []
        )
        invoice_ids = {row.id for row in invoices}

        attempts = db.query(RecoveryAttempt).filter(RecoveryAttempt.app_user_id == app_user_id).all()
        invoice_ids.update(row.invoice_id for row in attempts)
        if invoice_ids:
            missing_invoices = (
                db.query(Invoice).filter(Invoice.id.in_(invoice_ids)).all()
            )
            known = {row.id for row in invoices}
            invoices.extend(row for row in missing_invoices if row.id not in known)

        allocations = (
            db.query(PaymentAllocation).filter(PaymentAllocation.invoice_id.in_(invoice_ids)).all()
            if invoice_ids
            else []
        )
        allocation_ids = {row.id for row in allocations}
        payments = (
            db.query(Payment).filter(Payment.invoice_id.in_(invoice_ids)).all()
            if invoice_ids
            else []
        )
        payment_orders = (
            db.query(PaymentOrder)
            .filter(PaymentOrder.app_user_id == app_user_id, PaymentOrder.type == "charging")
            .all()
        )
        refunds = db.query(RefundCase).filter(RefundCase.app_user_id == app_user_id).all()
        refund_ids = {row.id for row in refunds}
        refund_attempts = (
            db.query(RefundAttempt).filter(RefundAttempt.refund_case_id.in_(refund_ids)).all()
            if refund_ids
            else []
        )
        chargebacks = db.query(ChargebackCase).filter(ChargebackCase.app_user_id == app_user_id).all()
        reconciliation_items = (
            db.query(ReconciliationItem)
            .filter(ReconciliationItem.payment_allocation_id.in_(allocation_ids))
            .all()
            if allocation_ids
            else []
        )
        reconciliation_item_ids = {row.id for row in reconciliation_items}
        reconciliation_exceptions = (
            db.query(ReconciliationException)
            .filter(ReconciliationException.reconciliation_item_id.in_(reconciliation_item_ids))
            .all()
            if reconciliation_item_ids
            else []
        )

        fact_rows = [
            *sessions,
            *invoices,
            *attempts,
            *allocations,
            *payments,
            *payment_orders,
            *refunds,
            *refund_attempts,
            *chargebacks,
            *reconciliation_items,
            *reconciliation_exceptions,
        ]
        reasons: dict[str, list[Mapping[str, str]]] = {reason: [] for reason in REASON_CODES}
        committed_by_invoice: dict[UUID, Decimal] = {}
        for allocation in allocations:
            if allocation.status == "committed":
                committed_by_invoice[allocation.invoice_id] = committed_by_invoice.get(allocation.invoice_id, 0) + Decimal(str(allocation.amount))

        for invoice in invoices:
            total = Decimal(str(invoice.total_amount))
            committed = committed_by_invoice.get(invoice.id, Decimal("0.00"))
            if invoice.status == "pending" and committed < total:
                reasons["open_invoice"].append(_resource("invoice", invoice.id))
            elif invoice.status not in {"pending", "paid", "refunded", "cancelled"}:
                reasons["funds_unknown"].append(_resource("invoice", invoice.id))
            if invoice.status == "refunded":
                reasons["refund_or_chargeback"].append(_resource("invoice", invoice.id))

        settled_session_ids = {
            invoice.session_id
            for invoice in invoices
            if invoice.status == "paid"
            or committed_by_invoice.get(invoice.id, Decimal("0.00")) >= Decimal(str(invoice.total_amount))
        }
        for session in sessions:
            if (
                session.status == "completed"
                and session.payment_status == "unpaid"
                and session.end_time is not None
                and session.id not in settled_session_ids
            ):
                reasons["open_invoice"].append(_resource("session", session.id))

        for attempt in attempts:
            resource = _resource("recovery_attempt", attempt.id)
            if attempt.status in {"created", "processing", "action_required", "provider_approved"}:
                reasons["recovery_processing"].append(resource)
            elif attempt.status == "unknown":
                reasons["recovery_unknown"].append(resource)
            elif attempt.status == "duplicate_approved":
                reasons["reconciliation_mismatch"].append(resource)

        for allocation in allocations:
            resource = _resource("payment_allocation", allocation.id)
            if allocation.status in {"pending"}:
                reasons["recovery_processing"].append(resource)
            elif allocation.status in {"reversed"}:
                reasons["refund_or_chargeback"].append(resource)
            elif allocation.status in {"needs_review", "failed"}:
                reasons["funds_unknown"].append(resource)

        for payment in payments:
            if payment.status in {"pending"}:
                reasons["recovery_processing"].append(_resource("payment", payment.id))
            elif payment.status in {"refunded"}:
                reasons["refund_or_chargeback"].append(_resource("payment", payment.id))

        for order in payment_orders:
            if order.status in {"created", "processing"}:
                reasons["recovery_processing"].append(_resource("payment_order", order.id))
            elif order.status == "refunded":
                reasons["refund_or_chargeback"].append(_resource("payment_order", order.id))

        for case in refunds:
            if case.status in {"submitted", "under_review", "approved", "provider_processing", "partially_refunded", "manual_review", "unknown", "refunded"}:
                reasons["refund_or_chargeback"].append(_resource("refund_case", case.id))
        for attempt in refund_attempts:
            if attempt.status in {"processing", "partially_refunded", "manual_review", "unknown", "refunded"}:
                reasons["refund_or_chargeback"].append(_resource("refund_attempt", attempt.id))

        for case in chargebacks:
            if case.status in {"received", "under_review", "hold", "representment", "lost", "unknown"}:
                reasons["refund_or_chargeback"].append(_resource("chargeback_case", case.id))

        for item in reconciliation_items:
            if item.status in {"pending", "mismatch", "manual_review", "temporarily_accepted", "unknown"}:
                reason = "reconciliation_mismatch" if item.status in {"mismatch", "manual_review"} else "funds_unknown"
                reasons[reason].append(_resource("reconciliation_item", item.id))
        for exception in reconciliation_exceptions:
            if exception.status in {"pending", "mismatch", "manual_review", "temporarily_accepted", "unknown"}:
                reason = "reconciliation_mismatch" if exception.status in {"mismatch", "manual_review"} else "funds_unknown"
                reasons[reason].append(_resource("reconciliation_exception", exception.id))

        reason_codes = tuple(sorted((key for key, values in reasons.items() if values), key=_reason_priority))
        unknown_fact = any(
            getattr(row, "status", None) == "unknown"
            for row in (*attempts, *allocations, *refunds, *refund_attempts, *chargebacks, *reconciliation_items, *reconciliation_exceptions)
        ) or any(row.status == "needs_review" for row in allocations)
        resources: list[Mapping[str, str]] = []
        seen = set()
        for reason in reason_codes:
            for item in reasons[reason]:
                identity = (item["type"], item["id"])
                if identity not in seen:
                    seen.add(identity)
                    resources.append(item)

        if unknown_fact or "recovery_unknown" in reason_codes:
            status = "unknown"
        elif "funds_unknown" in reason_codes and not any(
            reason in reason_codes for reason in ("open_invoice", "recovery_processing", "refund_or_chargeback", "reconciliation_mismatch")
        ):
            status = "unknown"
        elif "recovery_processing" in reason_codes:
            status = "recheck_required"
        elif reason_codes:
            status = "blocked"
        else:
            status = "eligible"

        evaluated_at = datetime.now(timezone.utc)
        watermark = cls._watermark(fact_rows, user)
        previous = (
            db.query(FinancialEligibilityDecision)
            .filter(
                FinancialEligibilityDecision.app_user_id == app_user_id,
                FinancialEligibilityDecision.operation == operation,
            )
            .with_for_update()
            .first()
        )
        version = (previous.version + 1) if previous else 1
        if previous is None:
            previous = FinancialEligibilityDecision(
                app_user_id=app_user_id,
                operation=operation,
                version=version,
                schema_version=1,
                audit_reference=f"pay-mp-002:eligibility:{app_user_id}",
            )
            db.add(previous)
        previous.status = status
        previous.reason_codes = list(reason_codes)
        previous.blocking_resources = resources
        previous.version = version
        previous.evaluated_at = evaluated_at
        db.commit()
        return FinancialEligibilityResult(
            app_user_id=app_user_id,
            operation=operation,
            status=status,
            reason_codes=reason_codes,
            blocking_resources=tuple(resources),
            evaluated_at=evaluated_at,
            decision_version=version,
            source_watermark=watermark,
        )


def enqueue_financial_eligibility_recheck(
    db: Session,
    *,
    app_user_id: UUID,
    source_type: str,
    source_id: UUID | str,
    source_version: int | str,
    tenant_id: UUID | None = None,
    reason_code: str = "financial_fact_changed",
) -> None:
    """Request one replayable re-evaluation for a changed financial fact."""

    scope_type = "tenant" if tenant_id is not None else "platform"
    scope_ref = f"tenant:{tenant_id}" if tenant_id is not None else "platform:eslatin"
    idempotency_key = f"eligibility-recheck:{app_user_id}:{source_type}:{source_id}:{source_version}"
    existing = (
        db.query(OutboxEvent)
        .filter(
            OutboxEvent.scope_type == scope_type,
            OutboxEvent.scope_ref == scope_ref,
            OutboxEvent.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is not None:
        return

    db.add(
        OutboxEvent(
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_ref=scope_ref,
            aggregate_type="app_user",
            aggregate_id=str(app_user_id),
            event_type="financial.eligibility.recheck_requested",
            idempotency_key=idempotency_key,
            status="pending",
            attempts=0,
            payload={
                "event_id": str(uuid4()),
                "schema_version": 1,
                "aggregate_type": "app_user",
                "id": str(app_user_id),
                "scope_type": scope_type,
                "scope_ref": scope_ref,
                "status": "recheck_requested",
                "version": str(source_version),
                "occurred_at_utc": _iso(datetime.now(timezone.utc)),
                "reason_code": reason_code,
                "source_type": source_type,
                "source_id": str(source_id),
                "source_version": str(source_version),
                "app_user_id": str(app_user_id),
            },
        )
    )
    db.flush()


class ChargingAdmissionPreflight:
    """Compose FinancialEligibility with server-resolved paid-admission rail."""

    @staticmethod
    def _rail(
        db: Session,
        *,
        tenant_id: UUID,
        site_id: UUID,
        provider: str,
        evaluated_at: datetime,
    ) -> RailEligibility:
        decision = RuntimeRailControlService.evaluate(
            db,
            axis="paid_admission",
            tenant_id=tenant_id,
            site_id=site_id,
            provider=provider,
        )
        return RailEligibility(
            "paid_admission",
            decision.status,
            decision.matched_scope_refs,
            decision.version,
            evaluated_at,
        )

    @classmethod
    def evaluate(
        cls,
        db: Session,
        *,
        app_user_id: UUID,
        qr_token: str,
        settlement_method: str,
    ) -> ChargingAdmissionDecision:
        token = resolve_qr_token(db, qr_token)
        charge_point = (
            db.query(ChargePoint)
            .filter(
                ChargePoint.id == token.charge_point_id,
                ChargePoint.tenant_id == token.operator_tenant_id,
            )
            .first()
        )
        if charge_point is None:
            raise ValueError("Charging resource is not available")
        evse = (
            db.query(EVSE)
            .filter(EVSE.charge_point_id == charge_point.id, EVSE.evse_id == token.connector_id)
            .first()
        )
        if evse is None:
            raise ValueError("Charging connector is not available")
        pricing = PricingService.resolve(db, charge_point.tenant_id, charge_point.id)
        financial = FinancialEligibilityEvaluator.evaluate(db, app_user_id=app_user_id)
        evaluated_at = datetime.now(timezone.utc)
        if pricing.pricing_mode is PricingMode.FREE:
            rail = RailEligibility("paid_admission", "not_applicable", tuple(), 0, evaluated_at)
        elif pricing.pricing_mode is PricingMode.PAID:
            try:
                provider = PlatformMerchantAccountResolver().resolve(
                    operator_tenant_id=charge_point.tenant_id,
                    payment_purpose=PaymentPurpose.CHARGING_DIRECT,
                ).provider
            except MerchantContextError:
                rail = RailEligibility("paid_admission", "unknown", tuple(), 0, evaluated_at)
            else:
                rail = cls._rail(
                    db,
                    tenant_id=charge_point.tenant_id,
                    site_id=charge_point.site_id,
                    provider=provider,
                    evaluated_at=evaluated_at,
                )
        else:
            rail = RailEligibility("paid_admission", "unknown", tuple(), 0, evaluated_at)
        allowed = financial.status == "eligible" and rail.status in {"open", "not_applicable"}
        return ChargingAdmissionDecision(
            resource={
                "charge_point_id": str(charge_point.id),
                "site_id": str(charge_point.site_id),
                "connector_id": token.connector_id,
                "pricing_mode": pricing.pricing_mode.value,
            },
            financial_eligibility=financial,
            rail_eligibility=rail,
            decision="allowed" if allowed else "blocked",
        )
