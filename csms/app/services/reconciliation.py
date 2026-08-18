"""PAY-MP-002 BE-208 reconciliation authority.

The service stores bounded, provider-neutral source facts and derives matching
items from them.  It never imports historical data, calls a Provider, or
rewrites Invoice/Payment/Allocation authority.  Replays only recompute the
matching projection for a bounded run window.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.base import tenant_id_context
from app.database.models import (
    AdminUser,
    AuditLog,
    ReconciliationException,
    ReconciliationExport,
    ReconciliationItem,
    ReconciliationRun,
    ReconciliationSourceFact,
    ReconciliationSourceWatermark,
    ReconciliationWorkItem,
)


SYSTEM_ACTOR_ID = uuid5(NAMESPACE_URL, "https://eslatin.com.co/system/reconciliation")
SOURCE_TYPES = frozenset({"eslatin", "provider", "funds"})
MATCH_STATUSES = frozenset({"matched", "pending", "mismatch", "manual_review", "temporarily_accepted", "closed", "unknown"})
TEMPORARY_EXCEPTION_TYPES = frozenset({"timing", "fee", "funds_release_timing"})
MAX_CANONICAL_TEXT = 255
MAX_PAGE_SIZE = 100


class ReconciliationError(RuntimeError):
    code = "REQUEST_INVALID"
    status_code = 422
    retryable = False


class ReconciliationNotFound(ReconciliationError):
    code = "RESOURCE_NOT_FOUND"
    status_code = 404


class ReconciliationPermissionDenied(ReconciliationError):
    code = "PERMISSION_DENIED"
    status_code = 403


class ReconciliationVersionConflict(ReconciliationError):
    code = "RESOURCE_VERSION_CONFLICT"
    status_code = 409


class ReconciliationIdempotencyConflict(ReconciliationError):
    code = "IDEMPOTENCY_CONFLICT"
    status_code = 409


class ReconciliationCursorInvalid(ReconciliationError):
    code = "CURSOR_INVALID"
    status_code = 409


class ReconciliationExceptionNotEligible(ReconciliationError):
    code = "EXCEPTION_NOT_ELIGIBLE"
    status_code = 422


class ReconciliationExportStateError(ReconciliationError):
    code = "EXPORT_NOT_READY"
    status_code = 409
    retryable = True


class ReconciliationExportFailed(ReconciliationError):
    code = "EXPORT_FAILED"
    status_code = 409


class ReconciliationExportExpired(ReconciliationError):
    code = "EXPORT_EXPIRED"
    status_code = 410


class ReconciliationExportConsumed(ReconciliationError):
    code = "EXPORT_CONSUMED"
    status_code = 410


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return _now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _utc(value).isoformat().replace("+00:00", "Z") if value else None


def _money(value: Any, *, allow_none: bool = False) -> Decimal | None:
    if value is None and allow_none:
        return None
    try:
        result = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError) as exc:
        raise ReconciliationError("Invalid monetary value") from exc
    if not result.is_finite() or result < 0:
        raise ReconciliationError("Invalid monetary value")
    return result


def _text(value: Any, name: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ReconciliationError(f"{name} is required")
        return None
    result = str(value).strip()
    if not result or len(result) > MAX_CANONICAL_TEXT:
        raise ReconciliationError(f"{name} is invalid")
    return result


def _fingerprint(values: Mapping[str, Any]) -> str:
    canonical = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cursor_encode(created_at: datetime, resource_id: UUID) -> str:
    raw = f"{_iso(created_at)}|{resource_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _cursor_decode(cursor: str | None) -> tuple[str, UUID] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created, resource_id = base64.urlsafe_b64decode(padded.encode()).decode().split("|", 1)
        return created, UUID(resource_id)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ReconciliationCursorInvalid("Invalid reconciliation cursor") from exc


def _scope_for_actor(actor: AdminUser | None, requested_tenant_id: UUID | None = None) -> tuple[str, str, UUID | None]:
    if actor is not None and actor.is_super_admin:
        if requested_tenant_id:
            return "tenant", f"tenant:{requested_tenant_id}", requested_tenant_id
        return "platform", "platform:eslatin", None
    contextual_tenant = tenant_id_context.get()
    if not contextual_tenant:
        raise ReconciliationPermissionDenied("Tenant context required")
    if requested_tenant_id and requested_tenant_id != contextual_tenant:
        raise ReconciliationPermissionDenied("Tenant scope denied")
    return "tenant", f"tenant:{contextual_tenant}", contextual_tenant


def _audit(db: Session, *, actor_id: UUID, tenant_id: UUID | None, action: str, resource_type: str, resource_id: UUID, after: Mapping[str, Any]) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type="admin" if actor_id != SYSTEM_ACTOR_ID else "system",
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        after_data=dict(after),
        audit_metadata={"source": "pay-mp-002-be-208"},
    ))


def _project_run(run: ReconciliationRun) -> dict[str, Any]:
    return {
        "run_id": str(run.id),
        "scope": {"type": run.scope_type, "ref": run.scope_ref},
        "tenant_id": str(run.tenant_id) if run.tenant_id else None,
        "provider": run.provider,
        "business_date": run.business_date.isoformat(),
        "run_type": run.run_type,
        "status": run.status,
        "cutoff_at": _iso(run.cutoff_at),
        "closed_at": _iso(run.closed_at),
        "source_watermarks": run.source_watermarks or {},
        "item_count": run.item_count,
        "matched_count": run.matched_count,
        "exception_count": run.exception_count,
        "version": run.version,
        "created_at": _iso(run.created_at),
        "updated_at": _iso(run.updated_at),
        "allowed_actions": ["view", "refresh"],
    }


def _project_item(item: ReconciliationItem) -> dict[str, Any]:
    return {
        "item_id": str(item.id),
        "run_id": str(item.reconciliation_run_id),
        "scope": {"type": item.scope_type, "ref": item.scope_ref},
        "tenant_id": str(item.tenant_id) if item.tenant_id else None,
        "provider": item.provider,
        "canonical_reference": item.canonical_reference,
        "references": {
            "eslatin": item.eslatin_reference,
            "provider": item.provider_reference,
            "funds": item.funds_reference,
            "merchant": item.merchant_reference,
        },
        "amounts": {
            "expected": str(item.expected_amount) if item.expected_amount is not None else None,
            "observed": str(item.observed_amount),
            "provider": str(item.provider_amount) if item.provider_amount is not None else None,
            "funds": str(item.funds_amount) if item.funds_amount is not None else None,
            "fee": str(item.fee_amount) if item.fee_amount is not None else None,
            "refund": str(item.refund_amount) if item.refund_amount is not None else None,
            "hold": str(item.hold_amount) if item.hold_amount is not None else None,
            "release": str(item.release_amount) if item.release_amount is not None else None,
        },
        "currency": item.currency,
        "funds_status": item.funds_status,
        "status": item.status,
        "mismatch_code": item.mismatch_code,
        "conflict_code": item.conflict_code,
        "source_watermark": item.source_watermark,
        "version": item.version,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
        "allowed_actions": ["view", "refresh"],
    }


def _project_exception(exc: ReconciliationException) -> dict[str, Any]:
    return {
        "exception_id": str(exc.id),
        "run_id": str(exc.reconciliation_run_id),
        "item_id": str(exc.reconciliation_item_id),
        "scope": {"type": exc.scope_type, "ref": exc.scope_ref},
        "tenant_id": str(exc.tenant_id) if exc.tenant_id else None,
        "status": exc.status,
        "reason_code": exc.reason_code,
        "difference_type": exc.difference_type,
        "difference_amount": str(exc.difference_amount) if exc.difference_amount is not None else None,
        "owner_ref": exc.owner_ref,
        "severity": exc.severity,
        "due_at": _iso(exc.due_at),
        "escalation": exc.escalation,
        "resolution_code": exc.resolution_code,
        "temporary_exception_until": _iso(exc.temporarily_accepted_until),
        "finance_approver": str(exc.initiator_admin_id) if exc.initiator_admin_id else None,
        "platform_approver": str(exc.approver_admin_id) if exc.approver_admin_id else None,
        "version": exc.version,
        "created_at": _iso(exc.created_at),
        "updated_at": _iso(exc.updated_at),
        "allowed_actions": ["view", "resolve", "request_temporary_acceptance"],
    }


def _project_export(export: ReconciliationExport) -> dict[str, Any]:
    return {
        "export_id": str(export.id),
        "status": export.status,
        "download_path": export.download_path if export.status == "ready" else None,
        "expires_at": _iso(export.expires_at),
        "row_count": export.row_count,
        "audit_reference": export.audit_reference,
        "version": export.version,
        "created_at": _iso(export.created_at),
        "updated_at": _iso(export.updated_at),
    }


class ReconciliationService:
    """BE-208 three-way fact ingestion, matching and exception workflow."""

    def create_run(self, db: Session, *, provider: str, provider_account_ref: str, business_date: date,
                   source_checksum: str, run_type: str = "continuous", actor: AdminUser | None = None,
                   tenant_id: UUID | None = None, cutoff_at: datetime | None = None) -> ReconciliationRun:
        scope_type, scope_ref, resolved_tenant = _scope_for_actor(actor, tenant_id) if actor else (
            ("tenant", f"tenant:{tenant_id}", tenant_id) if tenant_id else ("platform", "platform:eslatin", None)
        )
        provider = _text(provider, "provider", required=True)
        provider_account_ref = _text(provider_account_ref, "provider_account_ref", required=True)
        source_checksum = _text(source_checksum, "source_checksum", required=True)
        if run_type not in {"continuous", "daily"}:
            raise ReconciliationError("Invalid run type")
        query = db.query(ReconciliationRun).filter(
            ReconciliationRun.provider == provider,
            ReconciliationRun.provider_account_ref == provider_account_ref,
            ReconciliationRun.business_date == business_date,
            ReconciliationRun.source_checksum == source_checksum,
        )
        existing = query.first()
        if existing:
            if existing.scope_type != scope_type or existing.scope_ref != scope_ref:
                raise ReconciliationPermissionDenied("Reconciliation run scope denied")
            return existing
        run = ReconciliationRun(
            scope_type=scope_type, scope_ref=scope_ref, tenant_id=resolved_tenant,
            provider=provider, provider_account_ref=provider_account_ref,
            business_date=business_date, run_type=run_type,
            source_checksum=source_checksum, cutoff_at=_utc(cutoff_at) if cutoff_at else None,
            source_watermarks={}, audit_reference=f"recon-run:{uuid4()}",
        )
        db.add(run)
        db.flush()
        _audit(db, actor_id=actor.id if actor else SYSTEM_ACTOR_ID, tenant_id=resolved_tenant,
               action="create", resource_type="reconciliation_run", resource_id=run.id,
               after={"status": run.status, "business_date": business_date.isoformat()})
        db.commit()
        db.refresh(run)
        return run

    def ingest_source_fact(self, db: Session, *, source_type: str, source_reference: str,
                           canonical_reference: str | None = None, amount: Any, currency: str,
                           provider: str, provider_account_ref: str, business_date: date | None = None,
                           merchant_reference: str | None = None, fee_amount: Any = 0,
                           refund_amount: Any = 0, hold_amount: Any = 0, release_amount: Any = 0,
                           funds_status: str | None = None, source_event_id: str | None = None,
                           source_cursor: str | None = None, source_watermark: str | None = None,
                           occurred_at: datetime | None = None, scope_type: str = "platform",
                           scope_ref: str = "platform:eslatin", tenant_id: UUID | None = None,
                           idempotency_key: str | None = None, payload: Any = None) -> ReconciliationSourceFact:
        if payload is not None:
            raise ReconciliationError("Raw Provider payload is not accepted by reconciliation authority")
        if source_type not in SOURCE_TYPES:
            raise ReconciliationError("Invalid reconciliation source type")
        if scope_type == "tenant" and (tenant_id is None or scope_ref != f"tenant:{tenant_id}"):
            raise ReconciliationPermissionDenied("Invalid tenant reconciliation scope")
        if scope_type == "platform" and (tenant_id is not None or scope_ref != "platform:eslatin"):
            raise ReconciliationPermissionDenied("Invalid platform reconciliation scope")
        source_reference = _text(source_reference, "source_reference", required=True)
        canonical_reference = _text(canonical_reference or source_reference, "canonical_reference", required=True)
        provider = _text(provider, "provider", required=True)
        provider_account_ref = _text(provider_account_ref, "provider_account_ref", required=True)
        values = {
            "source_type": source_type, "source_reference": source_reference,
            "canonical_reference": canonical_reference, "merchant_reference": merchant_reference,
            "amount": str(_money(amount)), "currency": currency.upper(),
            "fee_amount": str(_money(fee_amount)), "refund_amount": str(_money(refund_amount)),
            "hold_amount": str(_money(hold_amount)), "release_amount": str(_money(release_amount)),
            "funds_status": funds_status, "source_event_id": source_event_id,
            "source_cursor": source_cursor, "source_watermark": source_watermark,
        }
        if values["currency"] != "COP":
            raise ReconciliationError("Only COP reconciliation facts are supported")
        # Cursor/watermark metadata advances independently of the financial
        # fact. It must not turn a replay of the same canonical source fact
        # into a conflict.
        fingerprint = _fingerprint({key: values[key] for key in (
            "source_type", "source_reference", "canonical_reference", "merchant_reference",
            "amount", "currency", "fee_amount", "refund_amount", "hold_amount",
            "release_amount", "funds_status",
        )})
        dedupe_key = _text(idempotency_key or source_event_id or source_reference, "dedupe_key", required=True)
        existing = db.query(ReconciliationSourceFact).filter(
            ReconciliationSourceFact.provider == provider,
            ReconciliationSourceFact.source_type == source_type,
            ReconciliationSourceFact.source_reference == source_reference,
            ReconciliationSourceFact.source_fingerprint == fingerprint,
        ).first()
        if existing:
            return existing
        conflict = db.query(ReconciliationSourceFact).filter(
            ReconciliationSourceFact.provider == provider,
            ReconciliationSourceFact.source_type == source_type,
            ReconciliationSourceFact.source_reference == source_reference,
            ReconciliationSourceFact.source_fingerprint != fingerprint,
        ).first()
        status = "conflict" if conflict else "accepted"
        conflict_code = "source_payload_conflict" if conflict else None
        if conflict:
            dedupe_key = f"{dedupe_key}:conflict:{fingerprint[:16]}"
        fact = ReconciliationSourceFact(
            scope_type=scope_type, scope_ref=scope_ref, tenant_id=tenant_id,
            provider=provider, provider_account_ref=provider_account_ref,
            source_type=source_type, source_reference=source_reference,
            canonical_reference=canonical_reference, merchant_reference=_text(merchant_reference, "merchant_reference"),
            amount=_money(amount), currency=values["currency"], fee_amount=_money(fee_amount),
            refund_amount=_money(refund_amount), hold_amount=_money(hold_amount), release_amount=_money(release_amount),
            funds_status=_text(funds_status, "funds_status"), source_event_id=_text(source_event_id, "source_event_id"),
            source_cursor=_text(source_cursor, "source_cursor"), source_watermark=_text(source_watermark, "source_watermark"),
            source_fingerprint=fingerprint, dedupe_key=dedupe_key, conflict_code=conflict_code,
            status=status, occurred_at=_utc(occurred_at),
        )
        db.add(fact)
        db.flush()
        work = ReconciliationWorkItem(
            scope_type=scope_type, scope_ref=scope_ref, tenant_id=tenant_id,
            source_fact_id=fact.id, status="queued",
        )
        db.add(work)
        wm = db.query(ReconciliationSourceWatermark).filter(
            ReconciliationSourceWatermark.scope_type == scope_type,
            ReconciliationSourceWatermark.scope_ref == scope_ref,
            ReconciliationSourceWatermark.provider == provider,
            ReconciliationSourceWatermark.source_type == source_type,
        ).first()
        if source_watermark:
            if wm is None:
                wm = ReconciliationSourceWatermark(
                    scope_type=scope_type, scope_ref=scope_ref, tenant_id=tenant_id,
                    provider=provider, source_type=source_type, watermark=source_watermark,
                )
                db.add(wm)
            elif wm.watermark != source_watermark:
                wm.watermark = source_watermark
                wm.version += 1
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            duplicate = db.query(ReconciliationSourceFact).filter(
                ReconciliationSourceFact.provider == provider,
                ReconciliationSourceFact.source_type == source_type,
                ReconciliationSourceFact.source_reference == source_reference,
                ReconciliationSourceFact.source_fingerprint == fingerprint,
            ).first()
            if duplicate:
                return duplicate
            raise ReconciliationError("Unable to persist reconciliation fact") from exc
        db.refresh(fact)
        return fact

    def _facts_for_run(self, db: Session, run: ReconciliationRun, *, limit: int) -> list[ReconciliationSourceFact]:
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise ReconciliationError("limit must be between 1 and 100")
        start = datetime.combine(run.business_date, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        query = db.query(ReconciliationSourceFact).filter(
            ReconciliationSourceFact.scope_type == run.scope_type,
            ReconciliationSourceFact.scope_ref == run.scope_ref,
            ReconciliationSourceFact.provider == run.provider,
            ReconciliationSourceFact.occurred_at >= start,
            ReconciliationSourceFact.occurred_at < end,
            ReconciliationSourceFact.status.in_(["accepted", "conflict"]),
        )
        return query.order_by(ReconciliationSourceFact.created_at.asc(), ReconciliationSourceFact.id.asc()).limit(limit).all()

    def match_run(self, db: Session, run_id: UUID, *, limit: int = 100, replay: bool = False) -> ReconciliationRun:
        run = db.query(ReconciliationRun).filter(ReconciliationRun.id == run_id).first()
        if not run:
            raise ReconciliationNotFound("Reconciliation run not found")
        run.status = "running"
        facts = self._facts_for_run(db, run, limit=limit)
        grouped: dict[str, dict[str, ReconciliationSourceFact]] = {}
        for fact in facts:
            grouped.setdefault(fact.canonical_reference, {})[fact.source_type] = fact
        for canonical, sources in grouped.items():
            self._match_one(db, run, canonical, sources, replay=replay)
        if replay:
            run.version += 1
        run.item_count = db.query(func.count(ReconciliationItem.id)).filter(ReconciliationItem.reconciliation_run_id == run.id).scalar() or 0
        run.matched_count = db.query(func.count(ReconciliationItem.id)).filter(ReconciliationItem.reconciliation_run_id == run.id, ReconciliationItem.status == "matched").scalar() or 0
        run.exception_count = db.query(func.count(ReconciliationException.id)).filter(ReconciliationException.reconciliation_run_id == run.id, ReconciliationException.status.notin_(["closed", "temporarily_accepted"])).scalar() or 0
        if run.exception_count:
            run.status = "completed_with_exceptions"
        elif facts:
            run.status = "completed"
        run.completed_at = _now()
        db.commit()
        db.refresh(run)
        return run

    def _match_one(self, db: Session, run: ReconciliationRun, canonical: str, sources: Mapping[str, ReconciliationSourceFact], *, replay: bool) -> ReconciliationItem:
        eslatin = sources.get("eslatin")
        provider = sources.get("provider")
        funds = sources.get("funds")
        expected = eslatin.amount if eslatin else None
        observed = provider.amount if provider else (funds.amount if funds else Decimal("0.00"))
        mismatch: str | None = None
        difference_type: str | None = None
        difference_amount: Decimal | None = None
        if any(f.status == "conflict" for f in sources.values()):
            mismatch = "source_payload_conflict"
            difference_type = "conflict"
        elif not (eslatin and provider and funds):
            mismatch = "unmatched_source"
            difference_type = "unmatched"
        elif eslatin.amount != provider.amount or eslatin.amount != funds.amount:
            mismatch = "amount_mismatch"
            difference_type = "amount"
            difference_amount = max(abs(eslatin.amount - provider.amount), abs(eslatin.amount - funds.amount))
        elif len({x.merchant_reference for x in (eslatin, provider, funds) if x.merchant_reference}) > 1:
            mismatch = "merchant_mismatch"
            difference_type = "merchant"
        elif provider.fee_amount != funds.fee_amount:
            mismatch = "fee_mismatch"
            difference_type = "fee"
        elif provider.release_amount != funds.release_amount:
            mismatch = "funds_release_timing"
            difference_type = "funds_release_timing"
        status = "mismatch" if mismatch else "matched"
        item = db.query(ReconciliationItem).filter(
            ReconciliationItem.reconciliation_run_id == run.id,
            ReconciliationItem.canonical_reference == canonical,
        ).first()
        primary = provider or funds or eslatin
        if item is None:
            item = ReconciliationItem(
                reconciliation_run_id=run.id, scope_type=run.scope_type, scope_ref=run.scope_ref, tenant_id=run.tenant_id,
                provider=run.provider, source_reference=primary.source_reference, canonical_reference=canonical,
                source_type="canonical", eslatin_reference=eslatin.source_reference if eslatin else None,
                provider_reference=provider.source_reference if provider else None, funds_reference=funds.source_reference if funds else None,
                merchant_reference=primary.merchant_reference, payment_allocation_id=None,
                expected_amount=expected, observed_amount=observed, currency=primary.currency,
                provider_amount=provider.amount if provider else None, funds_amount=funds.amount if funds else None,
                fee_amount=provider.fee_amount if provider else (funds.fee_amount if funds else None),
                refund_amount=provider.refund_amount if provider else (funds.refund_amount if funds else None),
                hold_amount=funds.hold_amount if funds else None, release_amount=funds.release_amount if funds else None,
                funds_status=funds.funds_status if funds else None, status=status, mismatch_code=mismatch,
                conflict_code="source_fact_conflict" if any(f.status == "conflict" for f in sources.values()) else None,
                source_fingerprint=_fingerprint({k: v.source_fingerprint for k, v in sources.items()}),
                source_cursor=primary.source_cursor, source_watermark=primary.source_watermark,
                audit_reference=f"recon-item:{uuid4()}", occurred_at=primary.occurred_at,
            )
            db.add(item)
            db.flush()
        else:
            item.status = status
            item.mismatch_code = mismatch
            item.version += 1 if replay else 0
            item.replay_count += 1 if replay else 0
            item.provider_reference = provider.source_reference if provider else item.provider_reference
            item.funds_reference = funds.source_reference if funds else item.funds_reference
            item.provider_amount = provider.amount if provider else item.provider_amount
            item.funds_amount = funds.amount if funds else item.funds_amount
            item.observed_amount = observed
        if mismatch:
            exc = db.query(ReconciliationException).filter(ReconciliationException.reconciliation_item_id == item.id).first()
            if exc is None:
                exc = ReconciliationException(
                    reconciliation_run_id=run.id, reconciliation_item_id=item.id, scope_type=run.scope_type,
                    scope_ref=run.scope_ref, tenant_id=run.tenant_id, status="mismatch", reason_code=mismatch,
                    difference_type=difference_type, difference_amount=difference_amount, severity="blocking",
                    due_at=run.cutoff_at, owner_ref="finance", audit_reference=f"recon-exception:{uuid4()}",
                )
                db.add(exc)
            elif exc.status == "temporarily_accepted" and exc.temporarily_accepted_until and exc.temporarily_accepted_until > _now():
                item.status = "temporarily_accepted"
            else:
                exc.status = "mismatch"
                exc.reason_code = mismatch
                exc.difference_type = difference_type
                exc.difference_amount = difference_amount
                exc.temporarily_accepted_until = None
                exc.version += 1
        return item

    def replay_run(self, db: Session, run_id: UUID, *, limit: int = 100) -> ReconciliationRun:
        return self.match_run(db, run_id, limit=limit, replay=True)

    def claim_work(self, db: Session, *, worker_id: str, limit: int = 100, lease_seconds: int = 60) -> list[ReconciliationWorkItem]:
        worker_id = _text(worker_id, "worker_id", required=True)
        if limit < 1 or limit > MAX_PAGE_SIZE or lease_seconds < 1 or lease_seconds > 3600:
            raise ReconciliationError("Invalid work claim bounds")
        now = _now()
        work = db.query(ReconciliationWorkItem).filter(
            ReconciliationWorkItem.status.in_(["queued", "retryable"]),
            ReconciliationWorkItem.next_attempt_at <= now,
            or_(ReconciliationWorkItem.lease_expires_at.is_(None), ReconciliationWorkItem.lease_expires_at < now),
        ).order_by(ReconciliationWorkItem.next_attempt_at.asc(), ReconciliationWorkItem.id.asc()).limit(limit).with_for_update().all()
        for item in work:
            item.status = "leased"
            item.lease_owner = worker_id
            item.lease_expires_at = now + timedelta(seconds=lease_seconds)
        db.commit()
        return work

    def fail_work(self, db: Session, work_id: UUID, *, worker_id: str, error_code: str, retry_delay_seconds: int = 30) -> ReconciliationWorkItem:
        work = db.query(ReconciliationWorkItem).filter(ReconciliationWorkItem.id == work_id).first()
        if not work or work.lease_owner != worker_id:
            raise ReconciliationNotFound("Reconciliation work item not found")
        work.retry_count += 1
        work.last_error_code = _text(error_code, "error_code", required=True)
        work.lease_owner = None
        work.lease_expires_at = None
        if work.retry_count >= work.max_retries:
            work.status = "dead_letter"
            work.dead_lettered_at = _now()
        else:
            work.status = "retryable"
            work.next_attempt_at = _now() + timedelta(seconds=min(max(retry_delay_seconds, 1), 3600))
        db.commit()
        return work

    def _scoped_query(self, db: Session, model: Any, actor: AdminUser, tenant_id: UUID | None = None):
        scope_type, scope_ref, resolved_tenant = _scope_for_actor(actor, tenant_id)
        return db.query(model).filter(model.scope_type == scope_type, model.scope_ref == scope_ref), resolved_tenant

    def list_runs(self, db: Session, *, actor: AdminUser, status: str | None = None, business_date: date | None = None,
                  cursor: str | None = None, limit: int = 50, tenant_id: UUID | None = None) -> dict[str, Any]:
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise ReconciliationError("limit must be between 1 and 100")
        query, _ = self._scoped_query(db, ReconciliationRun, actor, tenant_id)
        if status: query = query.filter(ReconciliationRun.status == status)
        if business_date: query = query.filter(ReconciliationRun.business_date == business_date)
        decoded = _cursor_decode(cursor)
        if decoded:
            created, rid = decoded
            query = query.filter(or_(ReconciliationRun.business_date < date.fromisoformat(created[:10]), and_(ReconciliationRun.business_date == date.fromisoformat(created[:10]), ReconciliationRun.id < rid)))
        rows = query.order_by(ReconciliationRun.business_date.desc(), ReconciliationRun.id.desc()).limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = _cursor_encode(datetime.combine(row.business_date, datetime.min.time(), tzinfo=timezone.utc), row.id) if has_more and rows else None
        return {"items": [_project_run(row) for row in rows], "page": {"next_cursor": next_cursor, "has_more": has_more}}

    def get_run(self, db: Session, *, actor: AdminUser, run_id: UUID, tenant_id: UUID | None = None) -> ReconciliationRun:
        query, _ = self._scoped_query(db, ReconciliationRun, actor, tenant_id)
        run = query.filter(ReconciliationRun.id == run_id).first()
        if not run: raise ReconciliationNotFound("Reconciliation run not found")
        return run

    def list_items(self, db: Session, *, actor: AdminUser, run_id: UUID, status: str | None = None, cursor: str | None = None, limit: int = 50, tenant_id: UUID | None = None) -> dict[str, Any]:
        run = self.get_run(db, actor=actor, run_id=run_id, tenant_id=tenant_id)
        if limit < 1 or limit > MAX_PAGE_SIZE: raise ReconciliationError("limit must be between 1 and 100")
        query = db.query(ReconciliationItem).filter(ReconciliationItem.reconciliation_run_id == run.id)
        if status: query = query.filter(ReconciliationItem.status == status)
        decoded = _cursor_decode(cursor)
        if decoded:
            created_text, item_id = decoded
            try:
                created_at = datetime.fromisoformat(created_text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ReconciliationCursorInvalid("Invalid reconciliation cursor") from exc
            query = query.filter(or_(ReconciliationItem.created_at > created_at, and_(ReconciliationItem.created_at == created_at, ReconciliationItem.id > item_id)))
        rows = query.order_by(ReconciliationItem.created_at.asc(), ReconciliationItem.id.asc()).limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = _cursor_encode(rows[-1].created_at, rows[-1].id) if has_more and rows else None
        return {"items": [_project_item(row) for row in rows], "page": {"next_cursor": next_cursor, "has_more": has_more}}

    def get_exception(self, db: Session, *, actor: AdminUser, exception_id: UUID, tenant_id: UUID | None = None) -> ReconciliationException:
        query, _ = self._scoped_query(db, ReconciliationException, actor, tenant_id)
        exception = query.filter(ReconciliationException.id == exception_id).first()
        if not exception: raise ReconciliationNotFound("Reconciliation exception not found")
        return exception

    def list_exceptions(self, db: Session, *, actor: AdminUser, status: str | None = None, cursor: str | None = None, limit: int = 50, tenant_id: UUID | None = None) -> dict[str, Any]:
        if limit < 1 or limit > MAX_PAGE_SIZE: raise ReconciliationError("limit must be between 1 and 100")
        query, _ = self._scoped_query(db, ReconciliationException, actor, tenant_id)
        if status: query = query.filter(ReconciliationException.status == status)
        decoded = _cursor_decode(cursor)
        if decoded:
            created_text, exception_id = decoded
            try:
                created_at = datetime.fromisoformat(created_text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ReconciliationCursorInvalid("Invalid reconciliation cursor") from exc
            # The due_at ordering remains the contract ordering; created/id
            # is the opaque continuation tie-breaker for bounded pages.
            query = query.filter(or_(ReconciliationException.created_at > created_at, and_(ReconciliationException.created_at == created_at, ReconciliationException.id > exception_id)))
        rows = query.order_by(ReconciliationException.due_at.asc().nulls_last(), ReconciliationException.id.asc()).limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = _cursor_encode(rows[-1].created_at, rows[-1].id) if has_more and rows else None
        return {"items": [_project_exception(row) for row in rows], "page": {"next_cursor": next_cursor, "has_more": has_more}}

    def create_resolution_intent(self, db: Session, *, actor: AdminUser, exception_id: UUID, resolution_code: str,
                                 reason: str, expected_version: int, idempotency_key: str, tenant_id: UUID | None = None) -> ReconciliationException:
        exception = self.get_exception(db, actor=actor, exception_id=exception_id, tenant_id=tenant_id)
        if exception.resolution_idempotency_key == idempotency_key:
            return exception
        if expected_version != exception.version: raise ReconciliationVersionConflict("Reconciliation exception version conflict")
        if not _text(resolution_code, "resolution_code") or not _text(reason, "reason"):
            raise ReconciliationError("Resolution fields are required")
        exception.resolution_code = resolution_code
        exception.resolution_reason = reason
        exception.resolution_idempotency_key = _text(idempotency_key, "Idempotency-Key", required=True)
        # A resolution intent records operator evidence only. It never
        # changes the financial match result or clears a blocking exception.
        exception.status = "manual_review"
        exception.closed_at = _now()
        exception.version += 1
        _audit(db, actor_id=actor.id, tenant_id=exception.tenant_id, action="resolve", resource_type="reconciliation_exception", resource_id=exception.id, after={"status": exception.status, "resolution_code": resolution_code})
        db.commit(); db.refresh(exception)
        return exception

    def request_temporary_acceptance(self, db: Session, *, actor: AdminUser, exception_id: UUID, reason: str,
                                     expected_version: int, idempotency_key: str, tenant_id: UUID | None = None) -> ReconciliationException:
        exception = self.get_exception(db, actor=actor, exception_id=exception_id, tenant_id=tenant_id)
        if exception.request_idempotency_key == idempotency_key:
            return exception
        if expected_version != exception.version: raise ReconciliationVersionConflict("Reconciliation exception version conflict")
        if exception.difference_type not in TEMPORARY_EXCEPTION_TYPES:
            raise ReconciliationExceptionNotEligible("Only timing, fee, or funds-release timing may be temporarily accepted")
        exception.initiator_admin_id = actor.id
        exception.request_idempotency_key = _text(idempotency_key, "Idempotency-Key", required=True)
        exception.resolution_reason = _text(reason, "reason", required=True)
        exception.status = "manual_review"
        exception.version += 1
        _audit(db, actor_id=actor.id, tenant_id=exception.tenant_id, action="temporary_acceptance_requested", resource_type="reconciliation_exception", resource_id=exception.id, after={"status": exception.status})
        db.commit(); db.refresh(exception)
        return exception

    def decide_temporary_acceptance(self, db: Session, *, actor: AdminUser, exception_id: UUID, decision: str,
                                    reason: str, expected_version: int, idempotency_key: str, tenant_id: UUID | None = None) -> ReconciliationException:
        exception = self.get_exception(db, actor=actor, exception_id=exception_id, tenant_id=tenant_id)
        if exception.decision_idempotency_key == idempotency_key:
            return exception
        if expected_version != exception.version: raise ReconciliationVersionConflict("Reconciliation exception version conflict")
        if not exception.initiator_admin_id or exception.initiator_admin_id == actor.id:
            raise ReconciliationError("A different platform actor must decide the exception")
        if decision not in {"approve", "reject"}: raise ReconciliationError("Invalid exception decision")
        exception.decision_idempotency_key = _text(idempotency_key, "Idempotency-Key", required=True)
        exception.approver_admin_id = actor.id
        exception.resolution_reason = _text(reason, "reason", required=True)
        item = db.query(ReconciliationItem).filter(ReconciliationItem.id == exception.reconciliation_item_id).first()
        if decision == "approve":
            exception.status = "temporarily_accepted"
            exception.temporarily_accepted_until = _now() + timedelta(hours=24)
            if item: item.status = "temporarily_accepted"
        else:
            exception.status = "mismatch"
            exception.temporarily_accepted_until = None
            if item: item.status = "mismatch"
        exception.version += 1
        _audit(db, actor_id=actor.id, tenant_id=exception.tenant_id, action="temporary_acceptance_decided", resource_type="reconciliation_exception", resource_id=exception.id, after={"status": exception.status, "decision": decision})
        db.commit(); db.refresh(exception)
        return exception

    def expire_temporary_acceptances(self, db: Session, *, now: datetime | None = None, limit: int = 100) -> int:
        now = _utc(now)
        rows = db.query(ReconciliationException).filter(
            ReconciliationException.status == "temporarily_accepted",
            ReconciliationException.temporarily_accepted_until <= now,
        ).order_by(ReconciliationException.temporarily_accepted_until.asc(), ReconciliationException.id.asc()).limit(limit).with_for_update().all()
        for exception in rows:
            exception.status = "mismatch"
            exception.temporarily_accepted_until = None
            exception.version += 1
            item = db.query(ReconciliationItem).filter(ReconciliationItem.id == exception.reconciliation_item_id).first()
            if item: item.status = "mismatch"; item.version += 1
        db.commit()
        return len(rows)

    def create_export(self, db: Session, *, actor: AdminUser, run_id: UUID, filters: Mapping[str, Any], idempotency_key: str, tenant_id: UUID | None = None) -> ReconciliationExport:
        run = self.get_run(db, actor=actor, run_id=run_id, tenant_id=tenant_id)
        key = _text(idempotency_key, "Idempotency-Key", required=True)
        statuses = filters.get("status", []) if isinstance(filters, Mapping) else []
        if not isinstance(statuses, list) or len(statuses) > 7 or any(status not in MATCH_STATUSES for status in statuses):
            raise ReconciliationError("Export filters are invalid")
        safe_filters = {"status": list(statuses)}
        existing = db.query(ReconciliationExport).filter(
            ReconciliationExport.scope_type == run.scope_type,
            ReconciliationExport.scope_ref == run.scope_ref,
            ReconciliationExport.idempotency_key == key,
        ).first()
        if existing:
            if existing.reconciliation_run_id != run.id or (existing.filters or {}) != safe_filters:
                raise ReconciliationIdempotencyConflict("Export idempotency key conflicts")
            return existing
        export = ReconciliationExport(
            reconciliation_run_id=run.id, scope_type=run.scope_type, scope_ref=run.scope_ref,
            tenant_id=run.tenant_id, status="queued", filters=safe_filters,
            idempotency_key=key, audit_reference=f"recon-export:{uuid4()}",
            expires_at=_now() + timedelta(hours=1),
        )
        db.add(export)
        db.flush()
        _audit(db, actor_id=actor.id, tenant_id=run.tenant_id, action="create", resource_type="reconciliation_export", resource_id=export.id, after={"status": export.status})
        db.commit(); db.refresh(export)
        return export

    def get_export(self, db: Session, *, actor: AdminUser, export_id: UUID, tenant_id: UUID | None = None) -> ReconciliationExport:
        query, _ = self._scoped_query(db, ReconciliationExport, actor, tenant_id)
        export = query.filter(ReconciliationExport.id == export_id).first()
        if not export: raise ReconciliationNotFound("Reconciliation export not found")
        return export

    def generate_export(self, db: Session, *, actor: AdminUser, export_id: UUID, tenant_id: UUID | None = None) -> ReconciliationExport:
        export = self.get_export(db, actor=actor, export_id=export_id, tenant_id=tenant_id)
        if export.status == "ready": return export
        if export.status in {"downloaded", "expired", "failed"}:
            raise ReconciliationExportStateError("Export cannot be generated in its current state")
        if _utc(export.expires_at) <= _now():
            export.status = "expired"; export.version += 1; db.commit()
            raise ReconciliationExportStateError("Export has expired")
        export.status = "generating"
        db.flush()
        statuses = (export.filters or {}).get("status", [])
        query = db.query(ReconciliationItem).filter(ReconciliationItem.reconciliation_run_id == export.reconciliation_run_id)
        if statuses: query = query.filter(ReconciliationItem.status.in_(statuses))
        rows = query.order_by(ReconciliationItem.created_at.asc(), ReconciliationItem.id.asc()).limit(export.max_rows + 1).all()
        if len(rows) > export.max_rows:
            export.status = "failed"; export.version += 1; db.commit()
            raise ReconciliationError("Export row limit exceeded")
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["item_id", "canonical_reference", "status", "currency", "expected_amount", "provider_amount", "funds_amount", "fee_amount", "refund_amount", "hold_amount", "release_amount", "mismatch_code"])
        for item in rows:
            writer.writerow([
                str(item.id), item.canonical_reference or item.source_reference, item.status, item.currency,
                str(item.expected_amount) if item.expected_amount is not None else "",
                str(item.provider_amount) if item.provider_amount is not None else "",
                str(item.funds_amount) if item.funds_amount is not None else "",
                str(item.fee_amount) if item.fee_amount is not None else "",
                str(item.refund_amount) if item.refund_amount is not None else "",
                str(item.hold_amount) if item.hold_amount is not None else "",
                str(item.release_amount) if item.release_amount is not None else "",
                item.mismatch_code or "",
            ])
        export.content = stream.getvalue()
        export.row_count = len(rows)
        export.status = "ready"
        export.download_path = f"/api/v1/admin/reconciliation/exports/{export.id}/download"
        export.version += 1
        db.commit(); db.refresh(export)
        return export

    def download_export(self, db: Session, *, actor: AdminUser, export_id: UUID, tenant_id: UUID | None = None) -> str:
        export = self.get_export(db, actor=actor, export_id=export_id, tenant_id=tenant_id)
        if export.status == "failed":
            raise ReconciliationExportFailed("Export generation failed")
        if export.status == "expired":
            raise ReconciliationExportExpired("Export has expired")
        if export.status == "downloaded":
            raise ReconciliationExportConsumed("Export has already been downloaded")
        now = _now()
        if _utc(export.expires_at) <= now:
            export.status = "expired"; export.version += 1; db.commit()
            raise ReconciliationExportExpired("Export has expired")
        if export.status != "ready" or not export.content:
            raise ReconciliationExportStateError("Export is not ready")
        content = export.content
        export.status = "downloaded"
        export.version += 1
        export.content = None
        _audit(db, actor_id=actor.id, tenant_id=export.tenant_id, action="download", resource_type="reconciliation_export", resource_id=export.id, after={"status": export.status})
        db.commit()
        return content
