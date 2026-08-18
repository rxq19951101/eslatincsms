from datetime import datetime, timezone

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.database.models import DeviceEvent, MeterValue, OCPPMessageEvent
from app.services.charge_point_service import ChargePointService
from app.services.ocpp_message_handler import OCPPMessageHandler


@pytest.mark.asyncio
async def test_heartbeat_skips_history_and_throttles_snapshot_writes(
    db_session,
    sample_charge_point,
    sample_evse_status,
):
    handler = OCPPMessageHandler()

    first = await handler.handle_message(
        sample_charge_point.ocpp_identity,
        "Heartbeat",
        {},
        message_unique_id="heartbeat-p0-1",
    )
    assert "currentTime" in first

    db_session.refresh(sample_evse_status)
    first_persisted_at = sample_evse_status.last_seen
    assert first_persisted_at is not None
    assert db_session.query(OCPPMessageEvent).filter_by(action="Heartbeat").count() == 0
    assert db_session.query(DeviceEvent).filter_by(event_type="heartbeat").count() == 0

    second = await handler.handle_message(
        sample_charge_point.ocpp_identity,
        "Heartbeat",
        {},
        message_unique_id="heartbeat-p0-2",
    )
    assert "currentTime" in second

    db_session.refresh(sample_evse_status)
    assert sample_evse_status.last_seen == first_persisted_at
    assert db_session.query(OCPPMessageEvent).filter_by(action="Heartbeat").count() == 0
    assert db_session.query(DeviceEvent).filter_by(event_type="heartbeat").count() == 0


def test_stale_heartbeat_snapshot_is_persisted(
    db_session,
    sample_charge_point,
    sample_evse_status,
):
    sample_evse_status.last_seen = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db_session.commit()
    db_session.refresh(sample_evse_status)
    stale_value = sample_evse_status.last_seen

    persisted = ChargePointService.record_heartbeat(
        db_session,
        sample_charge_point.ocpp_identity,
    )

    assert persisted is True
    db_session.refresh(sample_evse_status)
    assert sample_evse_status.last_seen != stale_value


def test_missing_heartbeat_snapshot_is_persisted(
    db_session,
    sample_charge_point,
    sample_evse_status,
):
    sample_evse_status.last_seen = None
    db_session.commit()

    persisted = ChargePointService.record_heartbeat(
        db_session,
        sample_charge_point.ocpp_identity,
    )

    assert persisted is True
    db_session.refresh(sample_evse_status)
    assert sample_evse_status.last_seen is not None


@pytest.mark.asyncio
async def test_meter_values_message_commits_once(
    db_session,
    sample_commercial_charge_point,
    sample_evse,
    sample_evse_status,
):
    handler = OCPPMessageHandler()
    start = await handler.handle_message(
        sample_commercial_charge_point.ocpp_identity,
        "StartTransaction",
        {"connectorId": 1, "idTag": "P0_TAG", "meterStart": 0},
        evse_id=1,
        message_unique_id="p0-start-1",
    )

    commit_count = [0]

    def count_commit(_session):
        commit_count[0] += 1

    event.listen(Session, "after_commit", count_commit)
    try:
        result = await handler.handle_message(
            sample_commercial_charge_point.ocpp_identity,
            "MeterValues",
            {
                "transactionId": start["transactionId"],
                "meterValue": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "sampledValue": [
                            {
                                "value": "100",
                                "measurand": "Energy.Active.Import.Register",
                                "unit": "Wh",
                            }
                        ],
                    },
                    {
                        "timestamp": "2026-01-01T00:00:05Z",
                        "sampledValue": [
                            {
                                "value": "110",
                                "measurand": "Energy.Active.Import.Register",
                                "unit": "Wh",
                            }
                        ],
                    },
                ],
            },
            message_unique_id="p0-meter-1",
        )
    finally:
        event.remove(Session, "after_commit", count_commit)

    assert result["_outcome"] == "meter_recorded"
    assert commit_count[0] == 1
    assert db_session.query(MeterValue).count() == 2
    assert db_session.query(OCPPMessageEvent).filter_by(action="MeterValues").count() == 0
