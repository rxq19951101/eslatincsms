"""PAY-MP-002 / BE-205 risk budget authority and convergence runtime.

This module owns only D-204 risk facts.  Invoice, MeterValue, Payment and
OCPP facts remain owned by their existing services.  PostgreSQL rows and the
append-only ledger are authoritative; Redis is never consulted to release a
reservation or to treat a RemoteStop as a physical stop.
"""

from __future__ import annotations

import hashlib
import inspect
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Awaitable, Callable, Iterable, Mapping

from sqlalchemy import and_, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    AuditLog,
    ChargePoint,
    ChargingSession,
    Invoice,
    OutboxEvent,
    PricingSnapshot,
    ProviderResolution,
    RiskExposureBalance,
    RiskLedgerEntry,
    RiskPolicyVersion,
    RiskReservation,
    RiskStopAction,
)


UTC = timezone.utc
SYSTEM_ACTOR_ID = uuid.UUID(int=0)
V2_MEDIA_TYPE = "application/vnd.eslatin.pay-mp-002.v2+json"
ACTIVE_RESERVATION_STATES = {
    "reserved",
    "consuming",
    "stop_requested",
    "physical_stop_pending",
    "settlement_pending",
    "release_pending",
    "resolving",
}
NON_TERMINAL_RESERVATION_STATES = ACTIVE_RESERVATION_STATES | {"unresolved"}


def utc_now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return utc_now(value).isoformat().replace("+00:00", "Z")


def decimal(value: Any, places: str = "0.01") -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


class RiskBudgetError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409, retryable: bool = False, **details: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details


class RiskDependencyUnavailable(RiskBudgetError):
    def __init__(self, message: str = "Risk authority or required control dependency is unavailable", **details: Any):
        super().__init__("RISK_DEPENDENCY_UNAVAILABLE", message, status_code=503, retryable=True, **details)


class RiskStateUnknown(RiskBudgetError):
    def __init__(self, message: str = "Authoritative risk state is unknown", **details: Any):
        super().__init__("RISK_STATE_UNKNOWN", message, status_code=503, retryable=True, **details)


class RiskBudgetBlocked(RiskBudgetError):
    def __init__(self, reason_code: str, message: str = "Risk budget does not allow charging", **details: Any):
        super().__init__("RISK_BUDGET_BLOCKED", message, status_code=409, reason_code=reason_code, **details)


class RiskVersionConflict(RiskBudgetError):
    def __init__(self, current_version: int):
        super().__init__("RESOURCE_VERSION_CONFLICT", "Risk resource version is stale", current_version=current_version)


class RiskIdempotencyConflict(RiskBudgetError):
    def __init__(self):
        super().__init__("IDEMPOTENCY_CONFLICT", "Idempotency key was reused with a different operation")


def _fingerprint(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _scope_ref(scope_type: str, value: Any | None = None) -> str:
    if scope_type == "platform":
        return "platform:eslatin"
    return f"{scope_type}:{value}"


def _is_active(reservation: RiskReservation) -> bool:
    return reservation.state in NON_TERMINAL_RESERVATION_STATES


class RiskBudgetService:
    """Transactional use cases for D-204 typed facts."""

    @staticmethod
    def create_policy_version(
        db: Session,
        *,
        policy_version: str,
        approved_reference: str,
        effective_at: datetime,
        session_amount_cop: Decimal,
        session_energy_kwh: Decimal,
        session_duration_minutes: int,
        user_open_cop: Decimal,
        site_window_cop: Decimal,
        platform_window_cop: Decimal,
        meter_degraded_after_seconds: int,
        meter_stop_after_seconds: int,
        offline_unknown_amount_cop: Decimal,
        offline_unknown_duration_seconds: int,
        remote_stop_first_attempt_seconds: int,
        remote_stop_max_attempts: int,
        stop_transaction_timeout_seconds: int,
        recovery_check_after_seconds: int,
        final_resolution_after_seconds: int,
        status: str = "active",
    ) -> RiskPolicyVersion:
        """Create an immutable policy; callers must supply every approved value."""
        if not policy_version.strip() or not approved_reference.strip():
            raise ValueError("policy_version and approved_reference are required")
        if remote_stop_max_attempts > 3:
            raise ValueError("remote_stop_max_attempts cannot exceed 3")
        policy = RiskPolicyVersion(
            policy_version=policy_version.strip(),
            approved_reference=approved_reference.strip(),
            effective_at=utc_now(effective_at),
            session_amount_cop=decimal(session_amount_cop),
            session_energy_kwh=Decimal(str(session_energy_kwh)).quantize(Decimal("0.001")),
            session_duration_minutes=session_duration_minutes,
            user_open_cop=decimal(user_open_cop),
            site_window_cop=decimal(site_window_cop),
            platform_window_cop=decimal(platform_window_cop),
            meter_degraded_after_seconds=meter_degraded_after_seconds,
            meter_stop_after_seconds=meter_stop_after_seconds,
            offline_unknown_amount_cop=decimal(offline_unknown_amount_cop),
            offline_unknown_duration_seconds=offline_unknown_duration_seconds,
            remote_stop_first_attempt_seconds=remote_stop_first_attempt_seconds,
            remote_stop_max_attempts=remote_stop_max_attempts,
            stop_transaction_timeout_seconds=stop_transaction_timeout_seconds,
            recovery_check_after_seconds=recovery_check_after_seconds,
            final_resolution_after_seconds=final_resolution_after_seconds,
            status=status,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy

    @staticmethod
    def _policy(db: Session, policy_version: str | None, now: datetime) -> RiskPolicyVersion:
        query = db.query(RiskPolicyVersion).filter(
            RiskPolicyVersion.status == "active",
            RiskPolicyVersion.effective_at <= now,
        )
        if policy_version:
            policy = query.filter(RiskPolicyVersion.policy_version == policy_version).first()
        else:
            policy = query.order_by(RiskPolicyVersion.effective_at.desc(), RiskPolicyVersion.id.desc()).first()
        if policy is None:
            raise RiskDependencyUnavailable("No effective approved RiskPolicyVersion is available")
        return policy

    @staticmethod
    def _session_context(db: Session, session_id: uuid.UUID) -> tuple[ChargingSession, ChargePoint]:
        row = (
            db.query(ChargingSession, ChargePoint)
            .join(ChargePoint, ChargePoint.id == ChargingSession.charge_point_id)
            .filter(
                ChargingSession.id == session_id,
                ChargingSession.tenant_id == ChargePoint.tenant_id,
            )
            .first()
        )
        if row is None or row[0].app_user_id is None:
            raise RiskStateUnknown("Charging session ownership or charge point authority is unavailable")
        return row

    @staticmethod
    def _scope_specs(session: ChargingSession, charge_point: ChargePoint) -> tuple[tuple[str, str, uuid.UUID | None], ...]:
        # This order is part of the concurrency contract and must not change.
        return (
            ("platform", _scope_ref("platform"), None),
            ("site", _scope_ref("site", charge_point.site_id), session.tenant_id),
            ("user", _scope_ref("user", session.app_user_id), session.tenant_id),
        )

    @staticmethod
    def _lock_balances(
        db: Session,
        *,
        policy: RiskPolicyVersion,
        session: ChargingSession,
        charge_point: ChargePoint,
        now: datetime,
    ) -> list[RiskExposureBalance]:
        rows: list[RiskExposureBalance] = []
        for scope_type, scope_ref, tenant_id in RiskBudgetService._scope_specs(session, charge_point):
            # The lock rows are lazily materialized.  PostgreSQL advisory locks
            # close the first-writer race before the row exists; once present,
            # SELECT ... FOR UPDATE remains the authoritative lock.  SQLite
            # tests do not have this primitive and exercise the same ordering.
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                lock_key = int(_fingerprint(policy.id, scope_type, scope_ref)[:15], 16)
                db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
            row = (
                db.query(RiskExposureBalance)
                .filter(
                    RiskExposureBalance.scope_type == scope_type,
                    RiskExposureBalance.scope_ref == scope_ref,
                    RiskExposureBalance.policy_version_id == policy.id,
                )
                .with_for_update()
                .first()
            )
            if row is None:
                row = RiskExposureBalance(
                    scope_type=scope_type,
                    scope_ref=scope_ref,
                    tenant_id=tenant_id if scope_type != "platform" else None,
                    app_user_id=session.app_user_id if scope_type == "user" else None,
                    site_id=charge_point.site_id if scope_type == "site" else None,
                    policy_version_id=policy.id,
                    current_exposure_cop=Decimal("0.00"),
                    window_started_at=now - timedelta(seconds=policy.aggregate_window_seconds),
                    window_ends_at=now,
                )
                db.add(row)
                db.flush()
            rows.append(row)
        return rows

    @staticmethod
    def _reservation_exposure(reservation: RiskReservation) -> Decimal:
        if reservation.state == "released":
            return Decimal("0.00")
        if reservation.state in {"unresolved", "resolving"}:
            return decimal(reservation.unresolved_cop or reservation.reserved_cop) + decimal(reservation.unknown_cop)
        return decimal(reservation.reserved_cop) + decimal(reservation.unknown_cop)

    @classmethod
    def _current_exposure(
        cls,
        db: Session,
        *,
        scope_type: str,
        session: ChargingSession,
        charge_point: ChargePoint,
        now: datetime,
        window_seconds: int,
    ) -> Decimal:
        query = db.query(RiskReservation).filter(RiskReservation.state != "released")
        if scope_type == "user":
            query = query.filter(RiskReservation.app_user_id == session.app_user_id)
            reservations = query.all()
        elif scope_type == "site":
            query = query.filter(
                RiskReservation.site_id == charge_point.site_id,
                RiskReservation.created_at >= now - timedelta(seconds=window_seconds),
            )
            reservations = query.all()
        else:
            query = query.filter(RiskReservation.created_at >= now - timedelta(seconds=window_seconds))
            reservations = query.all()
        return sum((cls._reservation_exposure(row) for row in reservations), Decimal("0.00"))

    @staticmethod
    def _audit(db: Session, *, reservation: RiskReservation, action: str, before: Mapping[str, Any] | None, after: Mapping[str, Any] | None, source_event_id: str) -> None:
        db.add(AuditLog(
            tenant_id=reservation.tenant_id,
            actor_id=SYSTEM_ACTOR_ID,
            actor_type="system",
            action=f"risk.{action}",
            resource_type="risk_reservation",
            resource_id=str(reservation.id),
            before_data=dict(before or {}),
            after_data=dict(after or {}),
            audit_metadata={
                "policy_version": reservation.policy_version,
                "source_event_id": source_event_id,
                "idempotency_key": reservation.idempotency_key,
                "tenant_id": str(reservation.tenant_id),
            },
        ))

    @staticmethod
    def _outbox(
        db: Session,
        *,
        reservation: RiskReservation,
        event_type: str,
        status: str,
        source_event_id: str,
        reason_code: str | None = None,
        amount_cop: Decimal = Decimal("0.00"),
        energy_kwh: Decimal = Decimal("0.000"),
        data_quality: str = "authoritative",
    ) -> list[OutboxEvent]:
        events: list[OutboxEvent] = []
        session = db.query(ChargingSession).filter(ChargingSession.id == reservation.session_id).first()
        scope_specs = (
            ("platform", "platform:eslatin", None),
            ("tenant", f"tenant:{reservation.tenant_id}", reservation.tenant_id),
        )
        for scope_type, scope_ref, tenant_id in scope_specs:
            key = f"risk:{reservation.id}:{event_type}:{source_event_id}:{scope_type}"
            existing = db.query(OutboxEvent).filter(
                OutboxEvent.scope_type == scope_type,
                OutboxEvent.scope_ref == scope_ref,
                OutboxEvent.idempotency_key == key,
            ).first()
            if existing is not None:
                events.append(existing)
                continue
            event_id = str(uuid.uuid4())
            event = OutboxEvent(
                tenant_id=tenant_id,
                scope_type=scope_type,
                scope_ref=scope_ref,
                aggregate_type="RiskSession",
                aggregate_id=str(reservation.id),
                event_type=event_type,
                idempotency_key=key,
                payload={
                    "event_id": event_id,
                    "schema_version": "risk-event.v2",
                    "event_type": event_type,
                    "scope_type": scope_type,
                    "scope_ref": scope_ref,
                    "aggregate": {"type": "RiskSession", "id": str(reservation.id), "version": reservation.version},
                    "risk_scope": {"type": "platform" if scope_type == "platform" else "user", "ref": scope_ref, "tenant_id": str(tenant_id) if tenant_id else None},
                    "idempotency_key": key,
                    "correlation_id": str(reservation.session_id),
                    "causation_id": source_event_id,
                    "occurred_at_utc": iso_utc(datetime.now(UTC)),
                    "status": status,
                    "reason_code": reason_code,
                    "policy_version": reservation.policy_version,
                    "amount_cop": str(decimal(amount_cop)),
                    "energy_kwh": str(Decimal(str(energy_kwh)).quantize(Decimal("0.001"))),
                    "data_quality": data_quality,
                },
                status="pending",
                attempts=0,
                available_at=datetime.now(UTC),
            )
            db.add(event)
            events.append(event)
        return events

    @classmethod
    def _ledger(
        cls,
        db: Session,
        *,
        reservation: RiskReservation,
        action: str,
        source_event_id: str,
        amount_cop: Decimal,
        energy_kwh: Decimal = Decimal("0.000"),
        duration_minutes: Decimal = Decimal("0.00"),
        data_quality: str = "authoritative",
        reason_code: str | None = None,
        before_balance: Decimal = Decimal("0.00"),
        after_balance: Decimal = Decimal("0.00"),
    ) -> RiskLedgerEntry:
        key = f"risk:{reservation.id}:{action}:{source_event_id}"
        existing = db.query(RiskLedgerEntry).filter(
            RiskLedgerEntry.scope_type == "user",
            RiskLedgerEntry.scope_ref == _scope_ref("user", reservation.app_user_id),
            RiskLedgerEntry.idempotency_key == key,
        ).first()
        if existing is not None:
            return existing
        entry = RiskLedgerEntry(
            scope_type="user",
            scope_ref=_scope_ref("user", reservation.app_user_id),
            tenant_id=reservation.tenant_id,
            app_user_id=reservation.app_user_id,
            site_id=reservation.site_id,
            session_id=reservation.session_id,
            invoice_id=reservation.invoice_id,
            policy_version_id=reservation.policy_version_id,
            policy_version=reservation.policy_version,
            action=action,
            amount_cop=decimal(amount_cop),
            delta_cop=Decimal("0.00"),
            energy_kwh=Decimal(str(energy_kwh)).quantize(Decimal("0.001")),
            duration_minutes=decimal(duration_minutes),
            source_event_id=source_event_id,
            idempotency_key=key,
            before_balance_cop=decimal(before_balance),
            after_balance_cop=decimal(after_balance),
            data_quality=data_quality,
            reason_code=reason_code,
        )
        # The same immutable business action is represented in each aggregate
        # scope.  User/site/platform exposure remains queryable independently.
        db.add(entry)
        for scope_type, scope_ref, tenant_id in (
            ("site", _scope_ref("site", reservation.site_id), reservation.tenant_id),
            ("platform", _scope_ref("platform"), None),
        ):
            db.add(RiskLedgerEntry(
                scope_type=scope_type,
                scope_ref=scope_ref,
                tenant_id=tenant_id,
                app_user_id=reservation.app_user_id,
                site_id=reservation.site_id,
                session_id=reservation.session_id,
                invoice_id=reservation.invoice_id,
                policy_version_id=reservation.policy_version_id,
                policy_version=reservation.policy_version,
                action=action,
                amount_cop=decimal(amount_cop),
                delta_cop=Decimal("0.00"),
                energy_kwh=Decimal(str(energy_kwh)).quantize(Decimal("0.001")),
                duration_minutes=decimal(duration_minutes),
                source_event_id=source_event_id,
                idempotency_key=f"{key}:{scope_type}",
                before_balance_cop=decimal(before_balance),
                after_balance_cop=decimal(after_balance),
                data_quality=data_quality,
                reason_code=reason_code,
            ))
        return entry

    @classmethod
    def reserve(
        cls,
        db: Session,
        *,
        session_id: uuid.UUID,
        idempotency_key: str,
        source_event_id: str,
        policy_version: str | None = None,
        now: datetime | None = None,
        dependency_available: bool = True,
    ) -> RiskReservation:
        if not dependency_available:
            raise RiskDependencyUnavailable()
        if not idempotency_key or not source_event_id:
            raise RiskBudgetError("IDEMPOTENCY_KEY_REQUIRED", "Risk reserve requires an idempotency key and source event", status_code=422)
        now = utc_now(now)
        try:
            session, charge_point = cls._session_context(db, session_id)
            policy = cls._policy(db, policy_version, now)
            fingerprint = _fingerprint(session_id, policy.policy_version, idempotency_key, source_event_id)
            existing = db.query(RiskReservation).filter(
                RiskReservation.session_id == session_id,
                RiskReservation.policy_version_id == policy.id,
            ).first()
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise RiskIdempotencyConflict()
                return existing

            balances = cls._lock_balances(db, policy=policy, session=session, charge_point=charge_point, now=now)
            current = {
                row.scope_type: cls._current_exposure(
                    db,
                    scope_type=row.scope_type,
                    session=session,
                    charge_point=charge_point,
                    now=now,
                    window_seconds=policy.aggregate_window_seconds,
                )
                for row in balances
            }
            limits = {"user": decimal(policy.user_open_cop), "site": decimal(policy.site_window_cop), "platform": decimal(policy.platform_window_cop)}
            for scope_type in ("platform", "site", "user"):
                if current[scope_type] + decimal(policy.session_amount_cop) > limits[scope_type]:
                    raise RiskBudgetBlocked(
                        f"{scope_type.upper()}_EXPOSURE_LIMIT",
                        current_exposure=str(current[scope_type]),
                        limit=str(limits[scope_type]),
                    )

            reservation = RiskReservation(
                tenant_id=session.tenant_id,
                app_user_id=session.app_user_id,
                site_id=charge_point.site_id,
                charge_point_id=charge_point.id,
                session_id=session.id,
                policy_version_id=policy.id,
                policy_version=policy.policy_version,
                state="reserved",
                reserved_cop=decimal(policy.session_amount_cop),
                reserved_energy_kwh=Decimal(str(policy.session_energy_kwh)).quantize(Decimal("0.001")),
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                source_event_id=source_event_id,
                audit_reference=f"risk-audit:{uuid.uuid4().hex}",
                last_meter_wh=session.meter_start,
                last_meter_at=session.start_time,
            )
            db.add(reservation)
            db.flush()
            for row in balances:
                row.current_exposure_cop = current[row.scope_type] + decimal(policy.session_amount_cop)
                row.window_started_at = now - timedelta(seconds=policy.aggregate_window_seconds)
                row.window_ends_at = now
                row.version = int(row.version or 1) + 1
            cls._ledger(
                db,
                reservation=reservation,
                action="reserve",
                source_event_id=source_event_id,
                amount_cop=policy.session_amount_cop,
                before_balance=Decimal("0.00"),
                after_balance=policy.session_amount_cop,
            )
            cls._outbox(
                db,
                reservation=reservation,
                event_type="risk.reservation.created",
                status="reserved",
                source_event_id=source_event_id,
                amount_cop=policy.session_amount_cop,
            )
            cls._audit(db, reservation=reservation, action="reserved", before={"state": "preflight"}, after={"state": "reserved", "amount_cop": str(policy.session_amount_cop)}, source_event_id=source_event_id)
            db.commit()
            db.refresh(reservation)
            return reservation
        except RiskBudgetError:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            raise RiskIdempotencyConflict() from exc
        except Exception as exc:
            db.rollback()
            raise RiskDependencyUnavailable(str(exc)) from exc

    @classmethod
    def _reservation_for_update(cls, db: Session, session_id: uuid.UUID, policy_version: str | None = None) -> RiskReservation:
        query = db.query(RiskReservation).filter(RiskReservation.session_id == session_id).with_for_update()
        if policy_version:
            query = query.filter(RiskReservation.policy_version == policy_version)
        reservation = query.order_by(RiskReservation.created_at.desc()).first()
        if reservation is None:
            raise RiskStateUnknown("Risk reservation is not available for this charging session")
        return reservation

    @classmethod
    def _request_stop_locked(cls, db: Session, *, reservation: RiskReservation, policy: RiskPolicyVersion, reason_code: str, now: datetime, source_event_id: str) -> RiskStopAction:
        existing = db.query(RiskStopAction).filter(
            RiskStopAction.reservation_id == reservation.id,
            RiskStopAction.reason_code == reason_code,
        ).with_for_update().first()
        if existing is not None:
            return existing
        stop = RiskStopAction(
            tenant_id=reservation.tenant_id,
            reservation_id=reservation.id,
            session_id=reservation.session_id,
            charge_point_id=reservation.charge_point_id,
            policy_version_id=reservation.policy_version_id,
            transaction_id=db.query(ChargingSession.transaction_id).filter(ChargingSession.id == reservation.session_id).scalar() or 0,
            status="queued",
            reason_code=reason_code,
            max_automatic_attempts=policy.remote_stop_max_attempts,
            first_attempt_due_at=now + timedelta(seconds=policy.remote_stop_first_attempt_seconds),
            stop_transaction_due_at=now + timedelta(seconds=policy.stop_transaction_timeout_seconds),
            command_id=f"risk-stop:{reservation.id}:{reason_code}",
            idempotency_key=f"risk-stop:{reservation.id}:{reason_code}",
        )
        db.add(stop)
        reservation.state = "stop_requested"
        reservation.version = int(reservation.version or 1) + 1
        db.flush()
        cls._outbox(
            db,
            reservation=reservation,
            event_type="risk.stop_requested",
            status="stop_pending",
            source_event_id=source_event_id,
            reason_code=reason_code,
        )
        cls._audit(db, reservation=reservation, action="stop_requested", before={"state": "consuming"}, after={"state": "stop_requested", "reason_code": reason_code}, source_event_id=source_event_id)
        return stop

    @classmethod
    def consume(
        cls,
        db: Session,
        *,
        session_id: uuid.UUID,
        expected_version: int,
        source_event_id: str,
        amount_cop: Decimal = Decimal("0.00"),
        energy_kwh: Decimal = Decimal("0.000"),
        duration_minutes: Decimal = Decimal("0.00"),
        meter_at: datetime | None = None,
        meter_wh: int | None = None,
        data_quality: str = "authoritative",
        reason_code: str | None = None,
        now: datetime | None = None,
    ) -> RiskReservation:
        if expected_version is None:
            raise RiskBudgetError("EXPECTED_VERSION_REQUIRED", "Risk state changes require expected_version", status_code=422)
        now = utc_now(now)
        try:
            reservation = cls._reservation_for_update(db, session_id)
            if reservation.version != expected_version:
                raise RiskVersionConflict(reservation.version)
            duplicate = db.query(RiskLedgerEntry).filter(
                RiskLedgerEntry.session_id == session_id,
                RiskLedgerEntry.action == "consume",
                RiskLedgerEntry.source_event_id == source_event_id,
            ).first()
            if duplicate is not None:
                return reservation
            if reservation.state in {"released", "physical_stop_pending", "settlement_pending"}:
                raise RiskBudgetError("RISK_STOP_PENDING", "Risk reservation is no longer consuming", reason_code="RISK_STOP_PENDING")
            amount = decimal(amount_cop)
            energy = Decimal(str(energy_kwh)).quantize(Decimal("0.001"))
            duration = decimal(duration_minutes)
            remaining_cop = max(Decimal("0.00"), decimal(reservation.reserved_cop) - decimal(reservation.consumed_cop))
            remaining_energy = max(Decimal("0.000"), Decimal(str(reservation.reserved_energy_kwh)) - Decimal(str(reservation.consumed_energy_kwh)))
            amount = min(amount, remaining_cop)
            energy = min(energy, remaining_energy)
            reservation.consumed_cop = decimal(reservation.consumed_cop) + amount
            reservation.consumed_energy_kwh = Decimal(str(reservation.consumed_energy_kwh)) + energy
            reservation.elapsed_minutes = max(decimal(reservation.elapsed_minutes), duration)
            if meter_at is not None:
                meter_at = utc_now(meter_at)
                if reservation.last_meter_at and meter_at < utc_now(reservation.last_meter_at):
                    return reservation
                reservation.last_meter_at = meter_at
                reservation.meter_freshness = "fresh" if data_quality == "authoritative" else "degraded"
            if meter_wh is not None:
                if reservation.last_meter_wh is not None and meter_wh < reservation.last_meter_wh:
                    raise RiskStateUnknown("MeterValues moved backwards")
                reservation.last_meter_wh = meter_wh
            if reservation.state == "reserved":
                reservation.state = "consuming"
            reservation.version = int(reservation.version or 1) + 1
            cls._ledger(
                db,
                reservation=reservation,
                action="consume",
                source_event_id=source_event_id,
                amount_cop=amount,
                energy_kwh=energy,
                duration_minutes=duration,
                data_quality=data_quality,
                reason_code=reason_code,
                before_balance=reservation.consumed_cop - amount,
                after_balance=reservation.consumed_cop,
            )
            policy = db.query(RiskPolicyVersion).filter(RiskPolicyVersion.id == reservation.policy_version_id).first()
            if policy is None:
                raise RiskDependencyUnavailable("Pinned RiskPolicyVersion is missing")
            threshold_reason = None
            if reservation.consumed_cop >= decimal(policy.session_amount_cop):
                threshold_reason = "SESSION_AMOUNT_LIMIT"
            elif reservation.consumed_energy_kwh >= Decimal(str(policy.session_energy_kwh)):
                threshold_reason = "SESSION_ENERGY_LIMIT"
            elif reservation.elapsed_minutes >= Decimal(policy.session_duration_minutes):
                threshold_reason = "SESSION_DURATION_LIMIT"
            if threshold_reason:
                cls._request_stop_locked(db, reservation=reservation, policy=policy, reason_code=threshold_reason, now=now, source_event_id=source_event_id)
            cls._outbox(db, reservation=reservation, event_type="risk.consumed", status=reservation.state, source_event_id=source_event_id, reason_code=reason_code, amount_cop=amount, energy_kwh=energy, data_quality=data_quality)
            cls._audit(db, reservation=reservation, action="consumed", before={"version": expected_version}, after={"version": reservation.version, "consumed_cop": str(reservation.consumed_cop)}, source_event_id=source_event_id)
            db.commit()
            db.refresh(reservation)
            return reservation
        except RiskBudgetError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise RiskDependencyUnavailable(str(exc)) from exc

    @classmethod
    def observe_meter(
        cls,
        db: Session,
        *,
        session_id: uuid.UUID,
        expected_version: int,
        source_event_id: str,
        meter_wh: int,
        meter_at: datetime,
        now: datetime | None = None,
    ) -> RiskReservation:
        reservation = cls._reservation_for_update(db, session_id)
        if reservation.version != expected_version:
            raise RiskVersionConflict(reservation.version)
        if reservation.last_meter_wh is not None and meter_wh < reservation.last_meter_wh:
            raise RiskStateUnknown("MeterValues moved backwards")
        delta_kwh = Decimal("0.000")
        if reservation.last_meter_wh is not None:
            delta_kwh = (Decimal(meter_wh - reservation.last_meter_wh) / Decimal("1000")).quantize(Decimal("0.001"))
        session = db.query(ChargingSession).filter(ChargingSession.id == session_id).first()
        price = db.query(PricingSnapshot.price_per_kwh).filter(PricingSnapshot.session_id == session_id).order_by(PricingSnapshot.snapshot_time.desc()).scalar()
        amount = delta_kwh * Decimal(str(price or 0))
        duration = Decimal("0.00")
        if session and session.start_time:
            duration = Decimal(str(max(0, (utc_now(meter_at) - utc_now(session.start_time)).total_seconds() / 60))).quantize(Decimal("0.01"))
        return cls.consume(db, session_id=session_id, expected_version=expected_version, source_event_id=source_event_id, amount_cop=amount, energy_kwh=delta_kwh, duration_minutes=duration, meter_at=meter_at, meter_wh=meter_wh, now=now)

    @classmethod
    def check_meter_freshness(cls, db: Session, *, session_id: uuid.UUID, now: datetime | None = None) -> RiskReservation:
        now = utc_now(now)
        try:
            reservation = cls._reservation_for_update(db, session_id)
            policy = db.query(RiskPolicyVersion).filter(RiskPolicyVersion.id == reservation.policy_version_id).first()
            if policy is None:
                raise RiskDependencyUnavailable("Pinned RiskPolicyVersion is missing")
            if reservation.last_meter_at is None:
                age = policy.meter_stop_after_seconds
            else:
                age = max(0, int((now - utc_now(reservation.last_meter_at)).total_seconds()))
            before = reservation.meter_freshness
            if age >= policy.meter_stop_after_seconds:
                reservation.meter_freshness = "stale"
                reservation.version = int(reservation.version or 1) + 1
                cls._request_stop_locked(db, reservation=reservation, policy=policy, reason_code="METER_VALUES_STALE", now=now, source_event_id=f"meter-stale:{reservation.id}:{int(now.timestamp())}")
            elif age >= policy.meter_degraded_after_seconds:
                reservation.meter_freshness = "degraded"
                if before != "degraded":
                    reservation.version = int(reservation.version or 1) + 1
            else:
                reservation.meter_freshness = "fresh"
            db.commit()
            db.refresh(reservation)
            return reservation
        except RiskBudgetError:
            db.rollback()
            raise

    @classmethod
    def mark_offline_unknown(cls, db: Session, *, session_id: uuid.UUID, expected_version: int, source_event_id: str, amount_cop: Decimal, now: datetime | None = None) -> RiskReservation:
        now = utc_now(now)
        try:
            reservation = cls._reservation_for_update(db, session_id)
            if reservation.version != expected_version:
                raise RiskVersionConflict(reservation.version)
            if db.query(RiskLedgerEntry).filter(RiskLedgerEntry.session_id == session_id, RiskLedgerEntry.action == "unresolved", RiskLedgerEntry.source_event_id == source_event_id).first():
                return reservation
            policy = db.query(RiskPolicyVersion).filter(RiskPolicyVersion.id == reservation.policy_version_id).first()
            if policy is None:
                raise RiskDependencyUnavailable("Pinned RiskPolicyVersion is missing")
            reservation.unknown_started_at = reservation.unknown_started_at or now
            reservation.unknown_cop = decimal(reservation.unknown_cop) + decimal(amount_cop)
            elapsed = int((now - utc_now(reservation.unknown_started_at)).total_seconds())
            reservation.meter_freshness = "degraded"
            reservation.version = int(reservation.version or 1) + 1
            reached_limit = reservation.unknown_cop >= decimal(policy.offline_unknown_amount_cop) or elapsed >= policy.offline_unknown_duration_seconds
            if reached_limit:
                reservation.unresolved_cop = max(Decimal("0.00"), decimal(reservation.reserved_cop) - decimal(reservation.consumed_cop))
                cls._ledger(db, reservation=reservation, action="unresolved", source_event_id=source_event_id, amount_cop=reservation.unresolved_cop, data_quality="unknown", reason_code="OFFLINE_BUFFER_LIMIT")
                cls._request_stop_locked(db, reservation=reservation, policy=policy, reason_code="OFFLINE_BUFFER_LIMIT", now=now, source_event_id=source_event_id)
            cls._outbox(
                db,
                reservation=reservation,
                event_type="risk.unresolved" if reached_limit else "risk.consumed",
                status="unresolved" if reached_limit else reservation.state,
                source_event_id=source_event_id,
                reason_code="OFFLINE_BUFFER_LIMIT" if reached_limit else "METER_VALUES_DEGRADED",
                amount_cop=reservation.unresolved_cop if reached_limit else reservation.unknown_cop,
                data_quality="unknown",
            )
            cls._audit(db, reservation=reservation, action="offline_unknown", before={"version": expected_version}, after={"unknown_cop": str(reservation.unknown_cop), "state": reservation.state}, source_event_id=source_event_id)
            db.commit()
            db.refresh(reservation)
            return reservation
        except RiskBudgetError:
            db.rollback()
            raise

    @classmethod
    def mark_unresolved(cls, db: Session, *, session_id: uuid.UUID, expected_version: int, source_event_id: str, reason_code: str, now: datetime | None = None) -> RiskReservation:
        now = utc_now(now)
        try:
            reservation = cls._reservation_for_update(db, session_id)
            if reservation.version != expected_version:
                raise RiskVersionConflict(reservation.version)
            if reservation.state == "unresolved":
                return reservation
            reservation.unresolved_cop = max(Decimal("0.00"), decimal(reservation.reserved_cop) - decimal(reservation.consumed_cop))
            reservation.state = "unresolved"
            reservation.version = int(reservation.version or 1) + 1
            cls._ledger(db, reservation=reservation, action="unresolved", source_event_id=source_event_id, amount_cop=reservation.unresolved_cop, data_quality="unknown", reason_code=reason_code)
            cls._outbox(db, reservation=reservation, event_type="risk.unresolved", status="unresolved", source_event_id=source_event_id, reason_code=reason_code, amount_cop=reservation.unresolved_cop, data_quality="unknown")
            cls._audit(db, reservation=reservation, action="unresolved", before={"version": expected_version}, after={"version": reservation.version, "reason_code": reason_code}, source_event_id=source_event_id)
            db.commit()
            db.refresh(reservation)
            return reservation
        except RiskBudgetError:
            db.rollback()
            raise

    @classmethod
    def confirm_stop_transaction(cls, db: Session, *, session_id: uuid.UUID, source_event_id: str, meter_stop: int | None = None) -> RiskReservation | None:
        try:
            reservation = cls._reservation_for_update(db, session_id)
        except RiskStateUnknown:
            return None
        if db.query(RiskLedgerEntry).filter(RiskLedgerEntry.session_id == session_id, RiskLedgerEntry.action == "correction", RiskLedgerEntry.source_event_id == source_event_id).first():
            return reservation
        reservation.physical_stop_confirmed = True
        reservation.state = "settlement_pending"
        reservation.version = int(reservation.version or 1) + 1
        if meter_stop is not None:
            reservation.last_meter_wh = meter_stop
        stop = db.query(RiskStopAction).filter(RiskStopAction.reservation_id == reservation.id).order_by(RiskStopAction.created_at.desc()).first()
        if stop is not None:
            stop.status = "confirmed"
            stop.physical_stop_confirmed = True
            stop.version = int(stop.version or 1) + 1
        cls._ledger(
            db,
            reservation=reservation,
            action="correction",
            source_event_id=source_event_id,
            amount_cop=Decimal("0.00"),
            reason_code="STOP_TRANSACTION_CONFIRMED",
        )
        cls._outbox(db, reservation=reservation, event_type="risk.stop_confirmed", status="settlement_pending", source_event_id=source_event_id)
        cls._audit(db, reservation=reservation, action="stop_confirmed", before={"physical_stop_confirmed": False}, after={"physical_stop_confirmed": True}, source_event_id=source_event_id)
        db.commit()
        db.refresh(reservation)
        return reservation

    @classmethod
    def release(cls, db: Session, *, session_id: uuid.UUID, expected_version: int, source_event_id: str, invoice_final: bool, provider_status: str, now: datetime | None = None) -> RiskReservation:
        now = utc_now(now)
        try:
            reservation = cls._reservation_for_update(db, session_id)
            if reservation.version != expected_version:
                raise RiskVersionConflict(reservation.version)
            if reservation.state == "released":
                return reservation
            if not (reservation.physical_stop_confirmed and invoice_final and provider_status == "resolved_approved"):
                reservation.unresolved_cop = max(Decimal("0.00"), decimal(reservation.reserved_cop) - decimal(reservation.consumed_cop))
                reservation.state = "unresolved"
                reservation.version = int(reservation.version or 1) + 1
                cls._ledger(db, reservation=reservation, action="unresolved", source_event_id=source_event_id, amount_cop=reservation.unresolved_cop, data_quality="unknown", reason_code="RISK_STATE_UNKNOWN")
                cls._outbox(db, reservation=reservation, event_type="risk.unresolved", status="unresolved", source_event_id=source_event_id, reason_code="RISK_STATE_UNKNOWN", amount_cop=reservation.unresolved_cop, data_quality="unknown")
                db.commit()
                db.refresh(reservation)
                return reservation
            policy = db.query(RiskPolicyVersion).filter(RiskPolicyVersion.id == reservation.policy_version_id).first()
            session, charge_point = cls._session_context(db, session_id)
            if policy is None:
                raise RiskDependencyUnavailable("Pinned RiskPolicyVersion is missing")
            balances = cls._lock_balances(db, policy=policy, session=session, charge_point=charge_point, now=now)
            release_amount = decimal(reservation.reserved_cop)
            for row in balances:
                row.current_exposure_cop = max(Decimal("0.00"), decimal(row.current_exposure_cop) - release_amount)
                row.version = int(row.version or 1) + 1
            reservation.state = "released"
            reservation.final_invoice_confirmed = True
            reservation.provider_resolved = True
            reservation.version = int(reservation.version or 1) + 1
            cls._ledger(db, reservation=reservation, action="release", source_event_id=source_event_id, amount_cop=release_amount, reason_code="RISK_FINALIZED")
            cls._outbox(db, reservation=reservation, event_type="risk.finalized", status="released", source_event_id=source_event_id, reason_code="RISK_FINALIZED")
            cls._audit(db, reservation=reservation, action="released", before={"state": "settlement_pending"}, after={"state": "released"}, source_event_id=source_event_id)
            db.commit()
            db.refresh(reservation)
            return reservation
        except RiskBudgetError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise RiskDependencyUnavailable(str(exc)) from exc

    @classmethod
    def mark_provider_unknown(cls, db: Session, *, session_id: uuid.UUID, provider: str, provider_operation_key: str, source_event_id: str, now: datetime | None = None) -> ProviderResolution:
        now = utc_now(now)
        if not provider_operation_key:
            raise RiskBudgetError("REQUEST_INVALID", "provider_operation_key is required", status_code=422)
        try:
            reservation = cls._reservation_for_update(db, session_id)
            existing = db.query(ProviderResolution).filter(ProviderResolution.reservation_id == reservation.id).with_for_update().first()
            if existing is not None:
                if existing.provider_operation_key != provider_operation_key:
                    raise RiskIdempotencyConflict()
                return existing
            policy = db.query(RiskPolicyVersion).filter(RiskPolicyVersion.id == reservation.policy_version_id).first()
            if policy is None:
                raise RiskDependencyUnavailable("Pinned RiskPolicyVersion is missing")
            resolution = ProviderResolution(
                tenant_id=reservation.tenant_id,
                reservation_id=reservation.id,
                session_id=reservation.session_id,
                provider=provider,
                provider_operation_key=provider_operation_key,
                status="pending",
                unknown_since=now,
                final_due_at=now + timedelta(seconds=policy.final_resolution_after_seconds),
                next_check_at=now + timedelta(seconds=policy.recovery_check_after_seconds),
                duplicate_create_blocked=True,
            )
            reservation.state = "unresolved"
            reservation.unresolved_cop = max(Decimal("0.00"), decimal(reservation.reserved_cop) - decimal(reservation.consumed_cop))
            reservation.version = int(reservation.version or 1) + 1
            db.add(resolution)
            db.flush()
            cls._ledger(db, reservation=reservation, action="unresolved", source_event_id=source_event_id, amount_cop=reservation.unresolved_cop, data_quality="unknown", reason_code="PROVIDER_UNKNOWN")
            cls._outbox(db, reservation=reservation, event_type="risk.provider_recheck_requested", status="unresolved", source_event_id=source_event_id, reason_code="PROVIDER_UNKNOWN", amount_cop=reservation.unresolved_cop, data_quality="unknown")
            cls._audit(db, reservation=reservation, action="provider_unknown", before={"state": "consuming"}, after={"state": "unresolved", "duplicate_create_blocked": True}, source_event_id=source_event_id)
            db.commit()
            db.refresh(resolution)
            return resolution
        except RiskBudgetError:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            raise RiskIdempotencyConflict() from exc

    @staticmethod
    def provider_create_allowed(db: Session, *, provider: str, provider_operation_key: str) -> bool:
        """A Provider operation key can be created at most once."""
        return db.query(ProviderResolution).filter(
            ProviderResolution.provider == provider,
            ProviderResolution.provider_operation_key == provider_operation_key,
        ).first() is None

    @classmethod
    async def recheck_provider(
        cls,
        db: Session,
        *,
        resolution_id: uuid.UUID,
        query_provider: Callable[[str], Mapping[str, Any] | Awaitable[Mapping[str, Any]]],
        now: datetime | None = None,
    ) -> ProviderResolution:
        now = utc_now(now)
        resolution = db.query(ProviderResolution).filter(ProviderResolution.id == resolution_id).with_for_update().first()
        if resolution is None:
            raise RiskStateUnknown("ProviderResolution is not available")
        if resolution.status in {"resolved_approved", "resolved_rejected", "terminal_unresolved"}:
            return resolution
        resolution.status = "checking"
        resolution.version = int(resolution.version or 1) + 1
        db.commit()
        try:
            result = query_provider(resolution.provider_operation_key)
            if inspect.isawaitable(result):
                result = await result
            result = dict(result or {})
            provider_status = str(result.get("status", "unknown")).lower()
            reference = result.get("provider_reference")
        except Exception:
            provider_status = "unknown"
            reference = None
        db.refresh(resolution)
        if provider_status in {"approved", "succeeded", "paid", "resolved_approved"}:
            resolution.status = "resolved_approved"
            resolution.provider_reference = str(reference) if reference else None
            resolution.next_check_at = None
        elif provider_status in {"declined", "failed", "rejected", "resolved_rejected"}:
            resolution.status = "resolved_rejected"
            resolution.provider_reference = str(reference) if reference else None
            resolution.next_check_at = None
        elif now >= utc_now(resolution.final_due_at):
            resolution.status = "terminal_unresolved"
            resolution.next_check_at = None
        else:
            resolution.status = "pending"
            resolution.next_check_at = min(utc_now(resolution.final_due_at), now + timedelta(minutes=15))
        resolution.version = int(resolution.version or 1) + 1
        reservation = db.query(RiskReservation).filter(RiskReservation.id == resolution.reservation_id).with_for_update().first()
        if reservation is not None and resolution.status == "resolved_approved":
            reservation.provider_resolved = True
            reservation.version = int(reservation.version or 1) + 1
            cls._outbox(
                db,
                reservation=reservation,
                event_type="risk.provider_resolution.updated",
                status=resolution.status,
                source_event_id=f"provider-resolution:{resolution.id}:{resolution.version}",
                reason_code="PROVIDER_RESOLVED",
            )
            cls._audit(
                db,
                reservation=reservation,
                action="provider_resolution_updated",
                before={"status": "checking"},
                after={"status": resolution.status, "provider_reference": resolution.provider_reference},
                source_event_id=f"provider-resolution:{resolution.id}:{resolution.version}",
            )
        elif reservation is not None and resolution.status in {"resolved_rejected", "terminal_unresolved"}:
            cls._outbox(
                db,
                reservation=reservation,
                event_type="risk.provider_resolution.updated",
                status=resolution.status,
                source_event_id=f"provider-resolution:{resolution.id}:{resolution.version}",
                reason_code="PROVIDER_RESOLUTION_FINAL" if resolution.status == "resolved_rejected" else "PROVIDER_UNKNOWN",
                data_quality="unknown" if resolution.status == "terminal_unresolved" else "authoritative",
            )
            cls._audit(
                db,
                reservation=reservation,
                action="provider_resolution_updated",
                before={"status": "checking"},
                after={"status": resolution.status},
                source_event_id=f"provider-resolution:{resolution.id}:{resolution.version}",
            )
        db.commit()
        db.refresh(resolution)
        return resolution

    @classmethod
    async def dispatch_remote_stop(
        cls,
        db: Session,
        *,
        stop_id: uuid.UUID,
        send_remote_stop: Callable[[str, int], Any],
        now: datetime | None = None,
    ) -> RiskStopAction:
        now = utc_now(now)
        stop = db.query(RiskStopAction).filter(RiskStopAction.id == stop_id).with_for_update().first()
        if stop is None:
            raise RiskStateUnknown("RiskStopAction is not available")
        if stop.status in {"confirmed", "physical_stop_failed", "unresolved"} or stop.physical_stop_confirmed:
            return stop
        if stop.attempts >= stop.max_automatic_attempts:
            stop.status = "physical_stop_failed"
            db.commit()
            return stop
        cp = db.query(ChargePoint).filter(ChargePoint.id == stop.charge_point_id).first()
        if cp is None:
            raise RiskStateUnknown("Charge point authority is unavailable")
        stop.status = "sending"
        stop.attempts = int(stop.attempts or 0) + 1
        stop.last_attempt_at = now
        stop.version = int(stop.version or 1) + 1
        db.commit()
        try:
            result = send_remote_stop(cp.ocpp_identity, stop.transaction_id)
            if inspect.isawaitable(result):
                result = await result
            result = result.model_dump() if hasattr(result, "model_dump") else dict(result or {})
            details = result.get("details") if isinstance(result.get("details"), dict) else result
            accepted = bool(result.get("success")) and (details.get("device_status") or details.get("status")) == "Accepted"
            error = None if accepted else "REMOTE_STOP_REJECTED"
        except Exception:
            accepted = False
            error = "OCPP_CONTROL_UNAVAILABLE"
        db.refresh(stop)
        if accepted:
            stop.status = "accepted_pending_physical_stop"
            stop.last_error = None
        elif stop.attempts < stop.max_automatic_attempts:
            stop.status = "retry_scheduled"
            stop.last_error = error
        else:
            stop.status = "physical_stop_failed"
            stop.last_error = error
            reservation = db.query(RiskReservation).filter(RiskReservation.id == stop.reservation_id).with_for_update().first()
            if reservation is not None:
                reservation.state = "unresolved"
                reservation.unresolved_cop = max(Decimal("0.00"), decimal(reservation.reserved_cop) - decimal(reservation.consumed_cop))
                reservation.version = int(reservation.version or 1) + 1
        stop.version = int(stop.version or 1) + 1
        db.commit()
        db.refresh(stop)
        return stop

    @classmethod
    def check_stop_timeouts(cls, db: Session, *, now: datetime | None = None) -> list[RiskStopAction]:
        now = utc_now(now)
        stops = db.query(RiskStopAction).filter(
            RiskStopAction.status.in_(("queued", "sending", "accepted_pending_physical_stop", "retry_scheduled")),
            RiskStopAction.stop_transaction_due_at <= now,
            RiskStopAction.physical_stop_confirmed.is_(False),
        ).with_for_update().all()
        for stop in stops:
            stop.status = "physical_stop_failed"
            stop.last_error = "PHYSICAL_STOP_TIMEOUT"
            stop.version = int(stop.version or 1) + 1
            reservation = db.query(RiskReservation).filter(RiskReservation.id == stop.reservation_id).with_for_update().first()
            if reservation is not None:
                reservation.state = "unresolved"
                reservation.unresolved_cop = max(Decimal("0.00"), decimal(reservation.reserved_cop) - decimal(reservation.consumed_cop))
                reservation.version = int(reservation.version or 1) + 1
        db.commit()
        return stops

    @staticmethod
    def risk_session_projection(db: Session, *, session_id: uuid.UUID, app_user_id: uuid.UUID | None = None, tenant_id: uuid.UUID | None = None) -> dict[str, Any]:
        query = db.query(RiskReservation).filter(RiskReservation.session_id == session_id)
        if tenant_id is not None:
            query = query.filter(RiskReservation.tenant_id == tenant_id)
        reservation = query.order_by(RiskReservation.created_at.desc()).first()
        if reservation is None or (app_user_id is not None and reservation.app_user_id != app_user_id):
            raise RiskStateUnknown("Risk session is not available")
        decision = "allow"
        status = {"reserved": "reserved", "consuming": "active", "stop_requested": "stopping", "physical_stop_pending": "stopping", "settlement_pending": "stopped_pending_reconcile", "released": "released", "unresolved": "unresolved", "resolving": "unresolved"}.get(reservation.state, "unknown")
        if reservation.state in {"stop_requested", "physical_stop_pending"}:
            decision = "stop_pending"
        elif reservation.state in {"unresolved", "resolving"}:
            decision = "unknown"
        elif reservation.state == "released":
            decision = "block"
        stop = db.query(RiskStopAction).filter(RiskStopAction.reservation_id == reservation.id).order_by(RiskStopAction.created_at.desc()).first()
        provider = db.query(ProviderResolution).filter(ProviderResolution.reservation_id == reservation.id).first()
        return {
            "risk_session_id": str(reservation.id),
            "charging_session_id": str(reservation.session_id),
            "status": status,
            "decision": decision,
            "reason_codes": [stop.reason_code] if stop and stop.status != "confirmed" else (["PROVIDER_UNKNOWN"] if provider and provider.status not in {"resolved_approved", "resolved_rejected"} else []),
            "policy_version": reservation.policy_version,
            "scope_summary": {"user": "included", "site": "included", "platform": "included", "window": "rolling_24h_utc"},
            "meter_freshness": reservation.meter_freshness,
            "reserved_cop": str(decimal(reservation.reserved_cop)),
            "consumed_cop": str(decimal(reservation.consumed_cop)),
            "unresolved_cop": str(decimal(reservation.unresolved_cop)),
            "next_action": "continue" if decision == "allow" else ("stop_pending" if decision == "stop_pending" else "contact_support"),
            "latest_stop_id": str(stop.id) if stop else None,
            "provider_resolution_id": str(provider.id) if provider else None,
            "allowed_actions": ["view", "refresh"],
            "version": reservation.version,
            "updated_at": iso_utc(reservation.updated_at),
        }

    @staticmethod
    def risk_stop_projection(db: Session, *, stop_id: uuid.UUID, app_user_id: uuid.UUID | None = None, tenant_id: uuid.UUID | None = None) -> dict[str, Any]:
        stop = db.query(RiskStopAction).filter(RiskStopAction.id == stop_id).first()
        if stop is None:
            raise RiskStateUnknown("Risk stop is not available")
        reservation = db.query(RiskReservation).filter(RiskReservation.id == stop.reservation_id).first()
        if reservation is None or (app_user_id is not None and reservation.app_user_id != app_user_id) or (tenant_id is not None and reservation.tenant_id != tenant_id):
            raise RiskStateUnknown("Risk stop is not available")
        return {
            "risk_stop_id": str(stop.id),
            "risk_session_id": str(reservation.id),
            "status": stop.status,
            "reason_code": stop.reason_code,
            "attempts": stop.attempts,
            "max_automatic_attempts": stop.max_automatic_attempts,
            "first_attempt_due_at": iso_utc(stop.first_attempt_due_at),
            "last_attempt_at": iso_utc(stop.last_attempt_at),
            "stop_transaction_due_at": iso_utc(stop.stop_transaction_due_at),
            "physical_stop_confirmed": bool(stop.physical_stop_confirmed),
            "next_action": "refresh" if stop.status not in {"confirmed", "physical_stop_failed", "unresolved"} else "contact_support",
            "allowed_actions": ["view", "refresh"],
            "version": stop.version,
            "updated_at": iso_utc(stop.updated_at),
        }

    @staticmethod
    def provider_resolution_projection(db: Session, *, resolution_id: uuid.UUID, app_user_id: uuid.UUID | None = None, tenant_id: uuid.UUID | None = None) -> dict[str, Any]:
        resolution = db.query(ProviderResolution).filter(ProviderResolution.id == resolution_id).first()
        if resolution is None:
            raise RiskStateUnknown("Provider resolution is not available")
        reservation = db.query(RiskReservation).filter(RiskReservation.id == resolution.reservation_id).first()
        if reservation is None or (app_user_id is not None and reservation.app_user_id != app_user_id) or (tenant_id is not None and reservation.tenant_id != tenant_id):
            raise RiskStateUnknown("Provider resolution is not available")
        return {
            "provider_resolution_id": str(resolution.id),
            "risk_session_id": str(reservation.id),
            "status": resolution.status,
            "provider_reference": resolution.provider_reference,
            "unknown_since": iso_utc(resolution.unknown_since),
            "final_due_at": iso_utc(resolution.final_due_at),
            "duplicate_create_blocked": True,
            "next_action": "refresh" if resolution.status in {"pending", "checking"} else ("contact_support" if resolution.status == "terminal_unresolved" else "none"),
            "allowed_actions": ["view", "refresh"],
            "version": resolution.version,
            "updated_at": iso_utc(resolution.updated_at),
        }
