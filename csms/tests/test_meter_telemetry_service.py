from datetime import datetime, timezone
from unittest.mock import patch
import uuid

import pytest

from app.core.auth import create_access_token
from app.database.models import (
    AppUser,
    ChargingSession,
    MeterValue,
    OCPPMessageEvent,
)
from app.services.meter_telemetry_service import MeterTelemetryService
from app.services.ocpp_message_handler import OCPPMessageHandler


class FakeMeterRedis:
    def __init__(self):
        self.values = {}

    def eval(self, _script, _numkeys, dedupe_key, latest_key, gate_key, *args):
        dedupe_ttl, payload, latest_ttl, message_key, gate_ttl = args
        del dedupe_ttl, latest_ttl, gate_ttl
        if dedupe_key in self.values:
            return [0, 0]
        self.values[dedupe_key] = "1"
        self.values[latest_key] = payload
        if gate_key in self.values:
            return [1, 0]
        self.values[gate_key] = message_key
        return [1, 1]

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)


def _snapshot(value, timestamp):
    return {
        "id": f"realtime:{timestamp}",
        "session_id": "session-1",
        "timestamp": timestamp,
        "connector_id": 1,
        "value_wh": value,
        "sampled_value": [],
        "source": "realtime",
    }


def test_redis_snapshot_deduplicates_and_gates_persistence():
    fake = FakeMeterRedis()
    service = MeterTelemetryService(fake)

    first = service.record_latest(
        tenant_id="tenant-1",
        session_id="session-1",
        message_key="message-1",
        snapshot=_snapshot(100, "2026-01-01T00:00:00Z"),
    )
    second = service.record_latest(
        tenant_id="tenant-1",
        session_id="session-1",
        message_key="message-2",
        snapshot=_snapshot(110, "2026-01-01T00:00:05Z"),
    )
    replay = service.record_latest(
        tenant_id="tenant-1",
        session_id="session-1",
        message_key="message-2",
        snapshot=_snapshot(110, "2026-01-01T00:00:05Z"),
    )

    assert first.should_persist is True
    assert second.should_persist is False
    assert replay.duplicate is True
    latest = service.get_latest(tenant_id="tenant-1", session_id="session-1")
    assert latest["value_wh"] == 110


def test_failed_database_write_can_release_redis_claims_for_retry():
    fake = FakeMeterRedis()
    service = MeterTelemetryService(fake)
    kwargs = {
        "tenant_id": "tenant-1",
        "session_id": "session-1",
        "message_key": "message-retry",
        "snapshot": _snapshot(100, "2026-01-01T00:00:00Z"),
    }

    failed_attempt = service.record_latest(**kwargs)
    service.release_write_claims(failed_attempt)
    retry = service.record_latest(**kwargs)

    assert failed_attempt.should_persist is True
    assert retry.duplicate is False
    assert retry.should_persist is True


@pytest.mark.asyncio
async def test_meter_values_use_redis_and_minute_database_sample(
    db_session,
    sample_commercial_charge_point,
    sample_evse,
    sample_evse_status,
):
    fake = FakeMeterRedis()
    service = MeterTelemetryService(fake)
    handler = OCPPMessageHandler(telemetry_service=service)
    start = await handler.handle_message(
        sample_commercial_charge_point.ocpp_identity,
        "StartTransaction",
        {"connectorId": 1, "idTag": "REDIS_TAG", "meterStart": 0},
        evse_id=1,
        message_unique_id="redis-start-1",
    )

    def payload(value, timestamp):
        return {
            "connectorId": 1,
            "transactionId": start["transactionId"],
            "meterValue": [{
                "timestamp": timestamp,
                "sampledValue": [{
                    "value": str(value),
                    "measurand": "Energy.Active.Import.Register",
                    "unit": "Wh",
                }],
            }],
        }

    first = await handler.handle_message(
        sample_commercial_charge_point.ocpp_identity,
        "MeterValues",
        payload(100, "2026-01-01T00:00:00Z"),
        message_unique_id="redis-meter-1",
    )
    second = await handler.handle_message(
        sample_commercial_charge_point.ocpp_identity,
        "MeterValues",
        payload(110, "2026-01-01T00:00:05Z"),
        message_unique_id="redis-meter-2",
    )
    replay = await handler.handle_message(
        sample_commercial_charge_point.ocpp_identity,
        "MeterValues",
        payload(110, "2026-01-01T00:00:05Z"),
        message_unique_id="redis-meter-2",
    )

    assert first["_outcome"] == "meter_recorded"
    assert second["_outcome"] == "meter_buffered"
    assert replay["_outcome"] == "meter_replayed"
    assert db_session.query(MeterValue).count() == 1
    assert db_session.query(OCPPMessageEvent).filter_by(action="MeterValues").count() == 0
    latest = service.get_latest(
        tenant_id=sample_commercial_charge_point.tenant_id,
        session_id=db_session.query(MeterValue.session_id).scalar(),
    )
    assert latest["value_wh"] == 110


def test_app_meter_values_merge_database_and_realtime_snapshot(
    client,
    db_session,
    sample_charge_point,
    sample_evse,
):
    user = AppUser(
        id=uuid.uuid4(),
        email="meter-realtime@example.test",
        password_hash="test-password-hash",
        email_verified=True,
        status="active",
    )
    session = ChargingSession(
        tenant_id=sample_charge_point.tenant_id,
        charge_point_id=sample_charge_point.id,
        evse_id=sample_evse.id,
        transaction_id=99001,
        id_tag="METER-APP-USER",
        user_id=str(user.id),
        app_user_id=user.id,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status="ongoing",
    )
    db_session.add_all([user, session])
    db_session.flush()
    persisted = MeterValue(
        tenant_id=sample_charge_point.tenant_id,
        session_id=session.id,
        connector_id=1,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        value=100,
        sampled_value=[],
    )
    db_session.add(persisted)
    db_session.commit()

    token = create_access_token({
        "user_id": str(user.id),
        "user_type": "app_user",
        "aud": "app",
    })
    snapshot = _snapshot(110, "2026-01-01T00:00:05Z")
    snapshot["session_id"] = str(session.id)
    with patch(
        "app.api.v1.app.charging.meter_telemetry_service.get_latest",
        return_value=snapshot,
    ):
        response = client.get(
            "/api/v1/app/charging/meter-values",
            params={"session_id": str(session.id)},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    points = response.json()
    assert [point["source"] for point in points] == ["database", "realtime"]
    assert points[0]["id"] == str(persisted.id)
    assert points[1]["id"] == "realtime:2026-01-01T00:00:05Z"
    assert points[1]["value_wh"] == 110
