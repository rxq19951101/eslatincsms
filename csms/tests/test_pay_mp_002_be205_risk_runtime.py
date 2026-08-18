"""Targeted PAY-MP-002 / BE-205 authority and convergence tests."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.database.models import (
    AppUser,
    ChargingSession,
    OutboxEvent,
    ProviderResolution,
    RiskLedgerEntry,
    RiskReservation,
    RiskStopAction,
)
from app.services.risk_budget import (
    RiskBudgetBlocked,
    RiskBudgetService,
    RiskDependencyUnavailable,
    RiskIdempotencyConflict,
    RiskVersionConflict,
)


UTC = timezone.utc


def _user(db_session, suffix: str) -> AppUser:
    user = AppUser(
        email=f"be205-{suffix}-{uuid.uuid4().hex}@example.test",
        password_hash="test-only",
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _session(db_session, charge_point, evse, user: AppUser, transaction_id: int, start: datetime) -> ChargingSession:
    session = ChargingSession(
        tenant_id=charge_point.tenant_id,
        evse_id=evse.id,
        charge_point_id=charge_point.id,
        transaction_id=transaction_id,
        id_tag=f"BE205-{transaction_id}",
        app_user_id=user.id,
        start_time=start,
        meter_start=0,
        status="ongoing",
        payment_status="pending",
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


def _policy(db_session, now: datetime, suffix: str, **overrides):
    values = dict(
        policy_version=f"PAY-MP-002-v2-test-{suffix}-{uuid.uuid4().hex}",
        approved_reference="D204-B_ARCHITECTURE_GATE",
        effective_at=now - timedelta(seconds=1),
        session_amount_cop=Decimal("200000"),
        session_energy_kwh=Decimal("100"),
        session_duration_minutes=180,
        user_open_cop=Decimal("250000"),
        site_window_cop=Decimal("1000000"),
        platform_window_cop=Decimal("5000000"),
        meter_degraded_after_seconds=120,
        meter_stop_after_seconds=300,
        offline_unknown_amount_cop=Decimal("15000"),
        offline_unknown_duration_seconds=300,
        remote_stop_first_attempt_seconds=10,
        remote_stop_max_attempts=3,
        stop_transaction_timeout_seconds=300,
        recovery_check_after_seconds=900,
        final_resolution_after_seconds=86400,
    )
    values.update(overrides)
    return RiskBudgetService.create_policy_version(db_session, **values)


def test_reserve_scope_caps_and_rolling_utc_window(db_session, sample_commercial_charge_point, sample_evse):
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    _policy(db_session, now, "scope", site_window_cop=Decimal("200000"), platform_window_cop=Decimal("400000"))
    first = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "one"), 20501, now)
    second = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "two"), 20502, now)

    RiskBudgetService.reserve(db_session, session_id=first.id, idempotency_key="reserve-1", source_event_id="start-1", now=now)
    with pytest.raises(RiskBudgetBlocked) as blocked:
        RiskBudgetService.reserve(db_session, session_id=second.id, idempotency_key="reserve-2", source_event_id="start-2", now=now)
    assert blocked.value.details["reason_code"] == "SITE_EXPOSURE_LIMIT"

    # A released reservation is excluded, and the window is UTC rolling rather
    # than a local-midnight bucket.  The service computes exposure from facts.
    old = db_session.query(RiskReservation).filter(RiskReservation.session_id == first.id).one()
    old.state = "released"
    old.created_at = now - timedelta(seconds=86401)
    db_session.commit()
    released = RiskBudgetService.reserve(db_session, session_id=second.id, idempotency_key="reserve-2b", source_event_id="start-2b", now=now)
    assert released.state == "reserved"


def test_reserve_idempotency_and_expected_version(db_session, sample_commercial_charge_point, sample_evse):
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    _policy(db_session, now, "idempotency")
    session = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "idem"), 20503, now)
    reservation = RiskBudgetService.reserve(db_session, session_id=session.id, idempotency_key="same", source_event_id="start-same", now=now)
    replay = RiskBudgetService.reserve(db_session, session_id=session.id, idempotency_key="same", source_event_id="start-same", now=now)
    assert replay.id == reservation.id
    with pytest.raises(RiskIdempotencyConflict):
        RiskBudgetService.reserve(db_session, session_id=session.id, idempotency_key="different", source_event_id="start-other", now=now)

    initial_version = reservation.version
    changed = RiskBudgetService.consume(db_session, session_id=session.id, expected_version=initial_version, source_event_id="meter-1", amount_cop=Decimal("100"), now=now)
    with pytest.raises(RiskVersionConflict):
        RiskBudgetService.consume(db_session, session_id=session.id, expected_version=initial_version, source_event_id="meter-2", amount_cop=Decimal("100"), now=now)
    assert changed.consumed_cop == Decimal("100.00")


def test_first_limit_wins_and_meter_fresh_degraded_stale(db_session, sample_commercial_charge_point, sample_evse):
    start = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    _policy(db_session, start, "limits", session_amount_cop=Decimal("200"), session_energy_kwh=Decimal("100"), session_duration_minutes=180)
    session = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "limit"), 20504, start)
    reservation = RiskBudgetService.reserve(db_session, session_id=session.id, idempotency_key="limit", source_event_id="start-limit", now=start)
    consumed = RiskBudgetService.consume(db_session, session_id=session.id, expected_version=reservation.version, source_event_id="meter-limit", amount_cop=Decimal("200"), now=start)
    stop = db_session.query(RiskStopAction).filter(RiskStopAction.reservation_id == consumed.id).one()
    assert stop.reason_code == "SESSION_AMOUNT_LIMIT"
    assert consumed.state == "stop_requested"

    meter_session = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "meter"), 20505, start)
    meter = RiskBudgetService.reserve(db_session, session_id=meter_session.id, idempotency_key="meter", source_event_id="start-meter", now=start)
    degraded = RiskBudgetService.check_meter_freshness(db_session, session_id=meter_session.id, now=start + timedelta(seconds=120))
    assert degraded.meter_freshness == "degraded"
    stale = RiskBudgetService.check_meter_freshness(db_session, session_id=meter_session.id, now=start + timedelta(seconds=300))
    assert stale.meter_freshness == "stale"
    assert db_session.query(RiskStopAction).filter(RiskStopAction.reservation_id == meter.id, RiskStopAction.reason_code == "METER_VALUES_STALE").count() == 1


def test_offline_buffer_stop_and_fail_closed_dependency(db_session, sample_commercial_charge_point, sample_evse, monkeypatch):
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    _policy(db_session, now, "offline")
    session = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "offline"), 20506, now)
    reservation = RiskBudgetService.reserve(db_session, session_id=session.id, idempotency_key="offline", source_event_id="start-offline", now=now)
    unknown = RiskBudgetService.mark_offline_unknown(db_session, session_id=session.id, expected_version=reservation.version, source_event_id="offline-1", amount_cop=Decimal("15000"), now=now)
    assert unknown.state == "stop_requested"
    assert unknown.meter_freshness == "degraded"
    assert db_session.query(RiskLedgerEntry).filter(RiskLedgerEntry.session_id == session.id, RiskLedgerEntry.action == "unresolved").count() == 3

    blocked_session = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "dependency"), 20507, now)
    with pytest.raises(RiskDependencyUnavailable):
        RiskBudgetService.reserve(db_session, session_id=blocked_session.id, idempotency_key="down", source_event_id="start-down", dependency_available=False, now=now)
    assert db_session.query(RiskReservation).filter(RiskReservation.session_id == blocked_session.id).count() == 0

    outbox_session = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "outbox"), 20512, now)
    original_outbox = RiskBudgetService._outbox
    monkeypatch.setattr(RiskBudgetService, "_outbox", staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("outbox down"))))
    with pytest.raises(RiskDependencyUnavailable):
        RiskBudgetService.reserve(db_session, session_id=outbox_session.id, idempotency_key="outbox-down", source_event_id="start-outbox-down", now=now)
    assert db_session.query(RiskReservation).filter(RiskReservation.session_id == outbox_session.id).count() == 0
    monkeypatch.setattr(RiskBudgetService, "_outbox", original_outbox)


def test_remote_stop_retry_timeout_and_stop_transaction_confirmation(db_session, sample_commercial_charge_point, sample_evse):
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    _policy(db_session, now, "stop")
    session = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "stop"), 20508, now)
    reservation = RiskBudgetService.reserve(db_session, session_id=session.id, idempotency_key="stop", source_event_id="start-stop", now=now)
    reservation = RiskBudgetService.consume(db_session, session_id=session.id, expected_version=reservation.version, source_event_id="meter-stop", amount_cop=Decimal("200000"), now=now)
    stop = db_session.query(RiskStopAction).filter(RiskStopAction.reservation_id == reservation.id).one()

    calls = []
    async def reject(_identity, _transaction_id):
        calls.append(True)
        return {"success": False, "details": {"status": "Rejected"}}

    for _ in range(3):
        asyncio.run(RiskBudgetService.dispatch_remote_stop(db_session, stop_id=stop.id, send_remote_stop=reject, now=now))
        db_session.refresh(stop)
    assert len(calls) == 3
    assert stop.status == "physical_stop_failed"
    assert reservation.state == "unresolved"

    accepted_session = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "accepted"), 20509, now)
    accepted_reservation = RiskBudgetService.reserve(db_session, session_id=accepted_session.id, idempotency_key="accepted", source_event_id="start-accepted", now=now)
    accepted_reservation = RiskBudgetService.consume(db_session, session_id=accepted_session.id, expected_version=accepted_reservation.version, source_event_id="meter-accepted", amount_cop=Decimal("200000"), now=now)
    accepted_stop = db_session.query(RiskStopAction).filter(RiskStopAction.reservation_id == accepted_reservation.id).one()
    accepted = asyncio.run(RiskBudgetService.dispatch_remote_stop(db_session, stop_id=accepted_stop.id, send_remote_stop=lambda *_: {"success": True, "details": {"device_status": "Accepted"}}, now=now))
    assert accepted.status == "accepted_pending_physical_stop"
    assert accepted.physical_stop_confirmed is False
    confirmed = RiskBudgetService.confirm_stop_transaction(db_session, session_id=accepted_session.id, source_event_id="stop-tx-1", meter_stop=1000)
    assert confirmed.physical_stop_confirmed is True
    assert confirmed.state == "settlement_pending"


def test_provider_unknown_queries_same_key_for_24h_without_create(db_session, sample_commercial_charge_point, sample_evse):
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    _policy(db_session, now, "provider")
    session = _session(db_session, sample_commercial_charge_point, sample_evse, _user(db_session, "provider"), 20510, now)
    RiskBudgetService.reserve(db_session, session_id=session.id, idempotency_key="provider", source_event_id="start-provider", now=now)
    resolution = RiskBudgetService.mark_provider_unknown(db_session, session_id=session.id, provider="mercadopago", provider_operation_key="op-20510", source_event_id="provider-unknown", now=now)
    assert RiskBudgetService.provider_create_allowed(db_session, provider="mercadopago", provider_operation_key="op-20510") is False
    replay = RiskBudgetService.mark_provider_unknown(db_session, session_id=session.id, provider="mercadopago", provider_operation_key="op-20510", source_event_id="provider-unknown", now=now)
    assert replay.id == resolution.id
    calls = []
    pending = asyncio.run(RiskBudgetService.recheck_provider(db_session, resolution_id=resolution.id, query_provider=lambda key: calls.append(key) or {"status": "unknown"}, now=now + timedelta(hours=1)))
    pending_status = pending.status
    terminal = asyncio.run(RiskBudgetService.recheck_provider(db_session, resolution_id=resolution.id, query_provider=lambda key: calls.append(key) or {"status": "unknown"}, now=now + timedelta(hours=24)))
    assert calls == ["op-20510", "op-20510"]
    assert pending_status == "pending"
    assert terminal.status == "terminal_unresolved"
    assert db_session.query(ProviderResolution).filter(ProviderResolution.provider_operation_key == "op-20510").count() == 1


def test_tenant_platform_outbox_projection_and_release_fail_closed(db_session, sample_commercial_charge_point, sample_evse):
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    _policy(db_session, now, "projection")
    user = _user(db_session, "projection")
    session = _session(db_session, sample_commercial_charge_point, sample_evse, user, 20511, now)
    reservation = RiskBudgetService.reserve(db_session, session_id=session.id, idempotency_key="projection", source_event_id="start-projection", now=now)
    events = db_session.query(OutboxEvent).filter(OutboxEvent.aggregate_id == str(reservation.id)).all()
    assert {event.scope_type for event in events} == {"platform", "tenant"}
    assert all(event.payload["schema_version"] == "risk-event.v2" for event in events)
    projection = RiskBudgetService.risk_session_projection(db_session, session_id=session.id, app_user_id=user.id)
    assert projection["scope_summary"]["window"] == "rolling_24h_utc"
    unresolved = RiskBudgetService.release(db_session, session_id=session.id, expected_version=reservation.version, source_event_id="release-before-final", invoice_final=False, provider_status="unknown", now=now)
    assert unresolved.state == "unresolved"
    assert unresolved.unresolved_cop == Decimal("200000.00")
    with pytest.raises(Exception):
        RiskBudgetService.risk_session_projection(db_session, session_id=session.id, app_user_id=uuid.uuid4())
