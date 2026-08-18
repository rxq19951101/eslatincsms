"""Safe, rebuildable App transaction projections for PAY-MP-002.

This module is deliberately read-only.  It joins the existing charging and
typed financial facts, applies AppUser/session-tenant ownership filters, and
returns a public projection.  The projection is never used by Financial
Eligibility or any payment/charging write path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.models import (
    AppUser,
    ChargePoint,
    ChargebackCase,
    ChargingSession,
    EVSE,
    Invoice,
    Payment,
    PaymentAllocation,
    PaymentOrder,
    PricingSnapshot,
    RecoveryAttempt,
    RefundAttempt,
    RefundCase,
    Site,
    SupportCase,
)


_KNOWN_INVOICE_STATUSES = {"pending", "paid", "cancelled", "refunded"}
_KNOWN_RECOVERY_STATUSES = {
    "created",
    "processing",
    "action_required",
    "provider_approved",
    "allocated",
    "declined",
    "failed",
    "cancelled",
    "expired",
    "duplicate_approved",
    "unknown",
}
_KNOWN_ALLOCATION_STATUSES = {
    "pending",
    "committed",
    "reversed",
    "failed",
    "needs_review",
}
_KNOWN_REFUND_STATUSES = {
    "submitted",
    "under_review",
    "approved",
    "provider_processing",
    "partially_refunded",
    "refunded",
    "rejected",
    "manual_review",
    "unknown",
}
_KNOWN_CHARGEBACK_STATUSES = {
    "received",
    "under_review",
    "hold",
    "representment",
    "won",
    "lost",
    "reversed",
    "unknown",
}
_SAFE_PAYMENT_METHODS = {
    "wallet",
    "new_card",
    "saved_card",
    "direct_card",
    "card",
    "free",
}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _money(value: Any) -> str | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite():
        return None
    return format(amount, ".2f")


def _decimal(value: Any, places: str) -> str | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite():
        return None
    return format(amount, places)


def _safe_status(value: Any, allowed: set[str]) -> str:
    value = str(value) if value is not None else ""
    return value if value in allowed else "unknown"


def _session_status(value: Any) -> str:
    return {
        "ongoing": "started",
        "completed": "completed",
        "cancelled": "cancelled",
    }.get(str(value), "unknown")


def _safe_method(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip().lower()
    return value if value in _SAFE_PAYMENT_METHODS else None


def _safe_reference(*values: Any, fallback: UUID | str | None = None) -> str | None:
    """Return an internal/merchant reference, never a Provider id or payload."""

    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return str(fallback) if fallback is not None else None


def _payment_order_links_to_session(
    order: PaymentOrder,
    session: ChargingSession,
    invoice: Invoice | None,
) -> bool:
    if session.payment_order_id == order.id:
        return True
    metadata = order.order_metadata
    if not isinstance(metadata, dict):
        return False
    if str(metadata.get("session_id") or "") != str(session.id):
        return False
    invoice_id = metadata.get("invoice_id")
    return invoice is None or str(invoice_id or "") == str(invoice.id)


@dataclass
class _Facts:
    invoice: Invoice | None = None
    snapshot: PricingSnapshot | None = None
    payments: list[Payment] = field(default_factory=list)
    payment_orders: list[PaymentOrder] = field(default_factory=list)
    attempts: list[RecoveryAttempt] = field(default_factory=list)
    allocations: list[PaymentAllocation] = field(default_factory=list)
    refunds: list[RefundCase] = field(default_factory=list)
    refund_attempts: list[RefundAttempt] = field(default_factory=list)
    chargebacks: list[ChargebackCase] = field(default_factory=list)
    support_cases: list[SupportCase] = field(default_factory=list)


class TransactionProjectionService:
    """Build P002 projections from durable authority facts only."""

    def __init__(self, db: Session, app_user: AppUser):
        self.db = db
        self.app_user = app_user

    def project_sessions(
        self,
        sessions: Iterable[ChargingSession],
        *,
        detail_session_id: UUID | None = None,
    ) -> dict[UUID, dict[str, Any]]:
        sessions = list(sessions)
        if not sessions:
            return {}

        facts = self._load_facts(sessions)
        charge_point_ids = {session.charge_point_id for session in sessions}
        evse_ids = {session.evse_id for session in sessions}
        charge_points = {
            cp.id: cp
            for cp in self.db.query(ChargePoint)
            .filter(ChargePoint.id.in_(charge_point_ids))
            .all()
        }
        sites = {
            site.id: site
            for site in self.db.query(Site)
            .filter(Site.id.in_({cp.site_id for cp in charge_points.values()}))
            .all()
        }
        evses = {
            evse.id: evse
            for evse in self.db.query(EVSE).filter(EVSE.id.in_(evse_ids)).all()
        }

        projected = {}
        for session in sessions:
            charge_point = charge_points.get(session.charge_point_id)
            if charge_point is not None and charge_point.tenant_id != session.tenant_id:
                charge_point = None
            site = (
                sites.get(charge_point.site_id)
                if charge_point is not None
                else None
            )
            if site is not None and site.tenant_id != session.tenant_id:
                site = None
            evse = evses.get(session.evse_id)
            if evse is not None and evse.tenant_id != session.tenant_id:
                evse = None
            projected[session.id] = self._project_session(
                session,
                facts[session.id],
                charge_point,
                site,
                evse,
                detail=detail_session_id == session.id,
            )
        return projected

    def _load_facts(self, sessions: list[ChargingSession]) -> dict[UUID, _Facts]:
        by_session = {session.id: _Facts() for session in sessions}
        session_ids = set(by_session)
        tenant_by_session = {session.id: session.tenant_id for session in sessions}

        invoices = (
            self.db.query(Invoice)
            .filter(Invoice.session_id.in_(session_ids))
            .all()
        )
        invoices = [
            invoice
            for invoice in invoices
            if tenant_by_session.get(invoice.session_id) == invoice.tenant_id
        ]
        invoice_by_id = {invoice.id: invoice for invoice in invoices}
        for invoice in invoices:
            if invoice.session_id in by_session:
                by_session[invoice.session_id].invoice = invoice

        snapshot_ids = {invoice.pricing_snapshot_id for invoice in invoices}
        snapshots = (
            self.db.query(PricingSnapshot)
            .filter(PricingSnapshot.id.in_(snapshot_ids))
            .all()
            if snapshot_ids
            else []
        )
        snapshots_by_id = {snapshot.id: snapshot for snapshot in snapshots}
        for session in sessions:
            facts = by_session[session.id]
            invoice = facts.invoice
            if invoice is not None:
                snapshot = snapshots_by_id.get(invoice.pricing_snapshot_id)
                if snapshot and snapshot.tenant_id == session.tenant_id and (
                    snapshot.session_id in (None, session.id)
                ):
                    facts.snapshot = snapshot
            if facts.snapshot is None:
                fallback = (
                    self.db.query(PricingSnapshot)
                    .filter(
                        PricingSnapshot.session_id == session.id,
                        PricingSnapshot.tenant_id == session.tenant_id,
                    )
                    .order_by(PricingSnapshot.snapshot_time.desc())
                    .first()
                )
                facts.snapshot = fallback

        invoice_ids = set(invoice_by_id)
        payments = (
            self.db.query(Payment)
            .filter(Payment.invoice_id.in_(invoice_ids))
            .all()
            if invoice_ids
            else []
        )
        for payment in payments:
            invoice = invoice_by_id.get(payment.invoice_id)
            if invoice is None or payment.tenant_id != invoice.tenant_id:
                continue
            by_session[invoice.session_id].payments.append(payment)

        payment_orders = (
            self.db.query(PaymentOrder)
            .filter(PaymentOrder.app_user_id == self.app_user.id)
            .all()
        )
        for session in sessions:
            facts = by_session[session.id]
            if facts.invoice is None and session.payment_order_id is None:
                continue
            facts.payment_orders = [
                order
                for order in payment_orders
                if order.type == "charging"
                and _payment_order_links_to_session(order, session, facts.invoice)
            ]

        attempts = (
            self.db.query(RecoveryAttempt)
            .filter(
                RecoveryAttempt.app_user_id == self.app_user.id,
                RecoveryAttempt.session_id.in_(session_ids),
                RecoveryAttempt.invoice_id.in_(invoice_ids),
            )
            .all()
            if invoice_ids
            else []
        )
        attempt_ids: set[UUID] = set()
        for attempt in attempts:
            invoice = invoice_by_id.get(attempt.invoice_id)
            if (
                invoice is None
                or attempt.tenant_id != invoice.tenant_id
                or attempt.session_id != invoice.session_id
            ):
                continue
            by_session[attempt.session_id].attempts.append(attempt)
            attempt_ids.add(attempt.id)

        allocations = (
            self.db.query(PaymentAllocation)
            .filter(
                PaymentAllocation.invoice_id.in_(invoice_ids),
                PaymentAllocation.tenant_id.in_({invoice.tenant_id for invoice in invoices}),
                PaymentAllocation.recovery_attempt_id.in_(attempt_ids),
            )
            .all()
            if invoice_ids and attempt_ids
            else []
        )
        allocation_ids: set[UUID] = set()
        for allocation in allocations:
            invoice = invoice_by_id.get(allocation.invoice_id)
            if invoice is None or allocation.tenant_id != invoice.tenant_id:
                continue
            by_session[invoice.session_id].allocations.append(allocation)
            allocation_ids.add(allocation.id)

        refunds = (
            self.db.query(RefundCase)
            .filter(
                RefundCase.app_user_id == self.app_user.id,
                RefundCase.invoice_id.in_(invoice_ids),
            )
            .all()
            if invoice_ids
            else []
        )
        refund_ids: set[UUID] = set()
        for refund in refunds:
            invoice = invoice_by_id.get(refund.invoice_id)
            if (
                invoice is None
                or refund.tenant_id != invoice.tenant_id
                or refund.payment_allocation_id not in allocation_ids
            ):
                continue
            by_session[invoice.session_id].refunds.append(refund)
            refund_ids.add(refund.id)

        refund_attempts = (
            self.db.query(RefundAttempt)
            .filter(RefundAttempt.refund_case_id.in_(refund_ids))
            .all()
            if refund_ids
            else []
        )
        for attempt in refund_attempts:
            refund = next((item for item in refunds if item.id == attempt.refund_case_id), None)
            if refund is None or attempt.tenant_id != refund.tenant_id:
                continue
            invoice = invoice_by_id.get(refund.invoice_id)
            if invoice is not None:
                by_session[invoice.session_id].refund_attempts.append(attempt)

        chargebacks = (
            self.db.query(ChargebackCase)
            .filter(
                ChargebackCase.app_user_id == self.app_user.id,
                ChargebackCase.invoice_id.in_(invoice_ids),
            )
            .all()
            if invoice_ids
            else []
        )
        for chargeback in chargebacks:
            invoice = invoice_by_id.get(chargeback.invoice_id)
            if (
                invoice is None
                or chargeback.tenant_id != invoice.tenant_id
                or chargeback.payment_allocation_id not in allocation_ids
            ):
                continue
            by_session[invoice.session_id].chargebacks.append(chargeback)

        support_cases = (
            self.db.query(SupportCase)
            .filter(SupportCase.app_user_id == self.app_user.id)
            .all()
        )
        for case in support_cases:
            for session in sessions:
                invoice = by_session[session.id].invoice
                if case.tenant_id != session.tenant_id:
                    continue
                if case.session_id == session.id or (
                    invoice is not None and case.invoice_id == invoice.id
                ):
                    by_session[session.id].support_cases.append(case)
                    break

        return by_session

    def _project_session(
        self,
        session: ChargingSession,
        facts: _Facts,
        charge_point: ChargePoint | None,
        site: Site | None,
        evse: EVSE | None,
        *,
        detail: bool,
    ) -> dict[str, Any]:
        invoice = facts.invoice
        session_energy = None
        if session.meter_start is not None and session.meter_stop is not None:
            session_energy = Decimal(str(max(session.meter_stop - session.meter_start, 0))) / Decimal("1000")
        session_duration = None
        if session.start_time and session.end_time:
            start = session.start_time
            end = session.end_time
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            session_duration = Decimal(str((end - start).total_seconds())) / Decimal("60")

        energy = invoice.energy_kwh if invoice is not None else session_energy
        duration = invoice.duration_minutes if invoice is not None else session_duration
        invoice_status = (
            _safe_status(invoice.status, _KNOWN_INVOICE_STATUSES)
            if invoice is not None
            else None
        )
        payments = self._payment_projections(facts, invoice_status)
        attempts = [self._attempt_projection(attempt) for attempt in facts.attempts]
        allocations = [self._allocation_projection(allocation) for allocation in facts.allocations]
        refunds = [self._refund_projection(refund) for refund in facts.refunds]
        chargebacks = [self._chargeback_projection(case) for case in facts.chargebacks]
        payment_status = self._payment_status(
            invoice_status,
            facts,
            payments,
        )
        data_quality = self._data_quality(invoice_status, facts, payments)

        result: dict[str, Any] = {
            "id": str(session.id),
            "transaction_id": session.transaction_id,
            "charge_point_id": str(session.charge_point_id),
            "ocpp_identity": charge_point.ocpp_identity if charge_point else None,
            "evse_id": str(session.evse_id),
            "start_time": _iso(session.start_time),
            "end_time": _iso(session.end_time),
            "status": session.status,
            "energy_kwh": _decimal(energy, ".3f"),
            "duration_minutes": _decimal(duration, ".2f"),
            "site_name": site.name if site else None,
            "site_address": site.address if site else None,
            "session": {
                "id": str(session.id),
                "reference": str(session.id),
                "status": _session_status(session.status),
                "started_at": _iso(session.start_time),
                "ended_at": _iso(session.end_time),
            },
            "invoice": self._invoice_projection(invoice, facts.snapshot),
            "payments": payments,
            "recovery_attempts": attempts,
            "allocations": allocations,
            "refunds": refunds,
            "chargebacks": chargebacks,
            "payment_status": payment_status,
            "data_quality": data_quality,
            "support_case_refs": [case.case_reference for case in facts.support_cases],
            "allowed_actions": self._allowed_actions(payment_status, invoice),
            "updated_at": _iso(self._updated_at(session, facts)),
        }

        if detail:
            result.update(
                {
                    "meter_start": session.meter_start,
                    "meter_stop": session.meter_stop,
                    "invoice_number": invoice.invoice_number if invoice else None,
                    "total_amount": _money(invoice.total_amount) if invoice else None,
                    "currency": "COP",
                    "billing_status": invoice_status,
                    "pricing_snapshot": self._snapshot_projection(facts.snapshot),
                    "connector_number": evse.evse_id if evse else None,
                    "connector_label": evse.physical_reference if evse else None,
                    "charge_point_label": (
                        (charge_point.display_name or charge_point.display_code)
                        if charge_point
                        else None
                    ),
                    "timeline": self._timeline(
                        session,
                        facts,
                        payments,
                        attempts,
                        allocations,
                        refunds,
                        chargebacks,
                    ),
                }
            )
        return result

    @staticmethod
    def _invoice_projection(
        invoice: Invoice | None,
        snapshot: PricingSnapshot | None,
    ) -> dict[str, Any] | None:
        if invoice is None:
            return None
        return {
            "id": str(invoice.id),
            "reference": invoice.invoice_number,
            "status": _safe_status(invoice.status, _KNOWN_INVOICE_STATUSES),
            "amount": _money(invoice.total_amount),
            "currency": "COP",
            "issued_at": _iso(invoice.issued_at),
            "paid_at": _iso(invoice.paid_at),
            "pricing_snapshot_reference": str(snapshot.id) if snapshot else None,
        }

    @staticmethod
    def _snapshot_projection(snapshot: PricingSnapshot | None) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        return {
            "id": str(snapshot.id),
            "reference": str(snapshot.id),
            "price_per_kwh": _money(snapshot.price_per_kwh),
            "service_fee": _money(snapshot.service_fee),
            "captured_at": _iso(snapshot.snapshot_time),
        }

    @staticmethod
    def _payment_projections(facts: _Facts, invoice_status: str | None) -> list[dict[str, Any]]:
        projections: list[dict[str, Any]] = []
        for payment in facts.payments:
            status = {
                "completed": "paid",
                "pending": "processing",
                "failed": "unpaid",
                "refunded": "refunded",
            }.get(payment.status, "unknown")
            if invoice_status == "paid" and status == "unknown":
                status = "paid"
            projections.append(
                {
                    "id": str(payment.id),
                    "reference": _safe_reference(payment.payment_number, fallback=payment.id),
                    "status": status,
                    "method": _safe_method(payment.payment_method),
                    "amount": _money(payment.amount),
                    "currency": "COP",
                    "occurred_at": _iso(payment.completed_at or payment.initiated_at),
                    "updated_at": _iso(payment.updated_at),
                }
            )

        for order in facts.payment_orders:
            order_status = {
                "created": "processing",
                "processing": "processing",
                "approved": "processing",
                "declined": "unpaid",
                "error": "unpaid",
                "expired": "unpaid",
                "voided": "unpaid",
                "refunded": "refunded",
            }.get(order.status, "unknown")
            if invoice_status == "paid" and order_status == "unknown":
                order_status = "paid"
            metadata = order.order_metadata if isinstance(order.order_metadata, dict) else {}
            projections.append(
                {
                    "id": str(order.id),
                    "reference": _safe_reference(
                        order.reference,
                        fallback=order.id,
                    ),
                    "status": order_status,
                    "method": _safe_method(metadata.get("settlement_method")),
                    "amount": _money(order.amount),
                    "currency": order.currency or "COP",
                    "occurred_at": _iso(order.paid_at or order.created_at),
                    "updated_at": _iso(order.updated_at),
                }
            )
        return sorted(
            projections,
            key=lambda item: (item.get("occurred_at") or "", item["id"]),
        )

    @staticmethod
    def _attempt_projection(attempt: RecoveryAttempt) -> dict[str, Any]:
        status = {
            "provider_approved": "approved",
            "duplicate_approved": "manual_review",
        }.get(attempt.status, _safe_status(attempt.status, _KNOWN_RECOVERY_STATUSES))
        return {
            "id": str(attempt.id),
            "reference": _safe_reference(attempt.audit_reference, fallback=attempt.id),
            "status": status,
            "method": _safe_method(attempt.method),
            "target_amount": _money(attempt.target_amount),
            "allocated_amount": _money(attempt.allocated_amount),
            "currency": attempt.currency or "COP",
            "updated_at": _iso(attempt.updated_at),
        }

    @staticmethod
    def _allocation_projection(allocation: PaymentAllocation) -> dict[str, Any]:
        status = {
            "committed": "confirmed",
            "needs_review": "unknown",
        }.get(allocation.status, _safe_status(allocation.status, _KNOWN_ALLOCATION_STATUSES))
        return {
            "id": str(allocation.id),
            "reference": _safe_reference(allocation.audit_reference, fallback=allocation.id),
            "status": status,
            "method": _safe_method(allocation.method),
            "amount": _money(allocation.amount),
            "currency": allocation.currency or "COP",
            "confirmed_at": _iso(allocation.committed_at),
            "updated_at": _iso(allocation.updated_at),
        }

    @staticmethod
    def _refund_projection(refund: RefundCase) -> dict[str, Any]:
        return {
            "id": str(refund.id),
            "reference": _safe_reference(refund.case_reference, fallback=refund.id),
            "status": _safe_status(refund.status, _KNOWN_REFUND_STATUSES),
            "requested_amount": _money(refund.requested_amount),
            "approved_amount": _money(refund.approved_amount),
            "confirmed_refunded_amount": _money(refund.refunded_amount),
            "currency": refund.currency or "COP",
            "updated_at": _iso(refund.updated_at),
        }

    @staticmethod
    def _chargeback_projection(case: ChargebackCase) -> dict[str, Any]:
        return {
            "id": str(case.id),
            "reference": _safe_reference(case.case_reference, fallback=case.id),
            "status": _safe_status(case.status, _KNOWN_CHARGEBACK_STATUSES),
            "amount": _money(case.disputed_amount),
            "currency": case.currency or "COP",
            "received_at": _iso(case.received_at),
            "updated_at": _iso(case.updated_at),
        }

    @staticmethod
    def _payment_status(
        invoice_status: str | None,
        facts: _Facts,
        payments: list[dict[str, Any]],
    ) -> str:
        chargeback_statuses = [
            _safe_status(case.status, _KNOWN_CHARGEBACK_STATUSES)
            for case in facts.chargebacks
        ]
        if any(
            status in {"received", "under_review", "hold", "representment", "lost"}
            for status in chargeback_statuses
        ):
            return "disputed"
        if "unknown" in chargeback_statuses:
            return "unknown"
        refund_statuses = [
            _safe_status(refund.status, _KNOWN_REFUND_STATUSES)
            for refund in facts.refunds
        ]
        if "refunded" in refund_statuses or invoice_status == "refunded":
            return "refunded"
        if "partially_refunded" in refund_statuses:
            return "partially_refunded"
        if any(status in {"submitted", "under_review", "approved", "provider_processing", "manual_review"} for status in refund_statuses):
            return "processing"
        # Invoice settlement is the durable paid fact.  A stale payment-order
        # or recovery-attempt processing state must not downgrade a settled
        # invoice back to processing.
        if invoice_status == "paid":
            return "paid"
        if any(status == "unknown" for status in refund_statuses):
            return "unknown"
        if any(allocation.status == "reversed" for allocation in facts.allocations):
            return "unknown"
        if any(item.get("status") == "processing" for item in payments):
            return "processing"
        if any(attempt.status in {"processing", "action_required", "provider_approved", "created"} for attempt in facts.attempts):
            return "processing"
        if invoice_status in {"pending", "cancelled"}:
            return "unpaid"
        if invoice_status == "unknown":
            return "unknown"
        if any(status == "paid" for status in payments):
            return "unknown"
        if any(status == "unknown" for status in payments):
            return "unknown"
        return "unknown"

    @staticmethod
    def _data_quality(
        invoice_status: str | None,
        facts: _Facts,
        payments: list[dict[str, Any]],
    ) -> str:
        if invoice_status is None:
            return "legacy"
        if invoice_status == "unknown":
            return "unknown"
        if any(item.get("status") == "unknown" for item in payments):
            return "unknown"
        if any(
            status == "unknown"
            for status in [
                _safe_status(attempt.status, _KNOWN_RECOVERY_STATUSES)
                for attempt in facts.attempts
            ]
            + [
                _safe_status(allocation.status, _KNOWN_ALLOCATION_STATUSES)
                for allocation in facts.allocations
            ]
            + [
                _safe_status(refund.status, _KNOWN_REFUND_STATUSES)
                for refund in facts.refunds
            ]
            + [
                _safe_status(case.status, _KNOWN_CHARGEBACK_STATUSES)
                for case in facts.chargebacks
            ]
        ):
            return "unknown"
        return "current"

    @staticmethod
    def _allowed_actions(payment_status: str, invoice: Invoice | None) -> list[str]:
        actions = ["view", "refresh"]
        if invoice is not None and payment_status == "unpaid":
            actions.extend(["start_recovery", "contact_support"])
        elif payment_status in {"processing", "unknown", "disputed", "partially_refunded"}:
            actions.append("contact_support")
        return actions

    @staticmethod
    def _updated_at(session: ChargingSession, facts: _Facts) -> datetime:
        values = [session.updated_at or session.start_time]
        resources = [
            facts.invoice,
            *facts.payments,
            *facts.payment_orders,
            *facts.attempts,
            *facts.allocations,
            *facts.refunds,
            *facts.chargebacks,
            *facts.support_cases,
        ]
        values.extend(resource.updated_at for resource in resources if resource is not None)
        normalized = []
        for value in values:
            if value is None:
                continue
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            normalized.append(value.astimezone(timezone.utc))
        return max(normalized, default=datetime.now(timezone.utc))

    @staticmethod
    def _timeline(
        session: ChargingSession,
        facts: _Facts,
        payments: list[dict[str, Any]],
        attempts: list[dict[str, Any]],
        allocations: list[dict[str, Any]],
        refunds: list[dict[str, Any]],
        chargebacks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        def add(event_id: Any, event_type: str, status: str, occurred_at: str | None, reference: Any):
            if occurred_at:
                events.append(
                    {
                        "event_id": str(event_id),
                        "type": event_type,
                        "status": status,
                        "occurred_at": occurred_at,
                        "actor": None,
                        "reason_code": None,
                        "reference": str(reference),
                    }
                )

        add(session.id, "session.started", "started", _iso(session.start_time), session.id)
        if session.end_time:
            add(session.id, "session.completed", _session_status(session.status), _iso(session.end_time), session.id)
        if facts.invoice:
            add(
                facts.invoice.id,
                "invoice.issued",
                _safe_status(facts.invoice.status, _KNOWN_INVOICE_STATUSES),
                _iso(facts.invoice.issued_at),
                facts.invoice.invoice_number,
            )
        for item in payments:
            add(item["id"], "payment.state_changed", item["status"], item["occurred_at"], item["reference"])
        for item in attempts:
            add(item["id"], "recovery.state_changed", item["status"], item["updated_at"], item["reference"])
        for item in allocations:
            add(item["id"], "allocation.state_changed", item["status"], item["updated_at"], item["reference"])
        for item in refunds:
            add(item["id"], "refund.state_changed", item["status"], item["updated_at"], item["reference"])
        for item in chargebacks:
            add(item["id"], "chargeback.state_changed", item["status"], item["updated_at"], item["reference"])
        return sorted(events, key=lambda event: (event["occurred_at"], event["event_id"]))
