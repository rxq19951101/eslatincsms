import pytest

from app.database.models import ChargingSession, MeterValue, OCPPMessageEvent, OutboxEvent
from app.domain.charging_session import validate_transition
from app.services.ocpp_message_handler import OCPPMessageHandler


def test_charging_session_state_machine_rejects_reopen():
    validate_transition("ongoing", "completed")
    with pytest.raises(ValueError):
        validate_transition("completed", "ongoing")


@pytest.mark.asyncio
async def test_replayed_ocpp_messages_are_idempotent(
    db_session, sample_commercial_charge_point, sample_evse, sample_evse_status
):
    handler = OCPPMessageHandler()
    start_payload = {
        "connectorId": 1,
        "idTag": "TEST_TAG",
        "meterStart": 100,
    }
    first_start = await handler.handle_message(
        sample_commercial_charge_point.ocpp_identity, "StartTransaction", start_payload,
        evse_id=1, message_unique_id="phase3-start-1",
    )
    second_start = await handler.handle_message(
        sample_commercial_charge_point.ocpp_identity, "StartTransaction", start_payload,
        evse_id=1, message_unique_id="phase3-start-1",
    )
    assert first_start["idTagInfo"]["status"] == "Accepted"
    assert second_start["idTagInfo"]["status"] == "Accepted"
    transaction_id = first_start["transactionId"]
    assert transaction_id > 0
    assert second_start["transactionId"] == transaction_id
    assert db_session.query(ChargingSession).filter_by(transaction_id=transaction_id).count() == 1
    assert db_session.query(OCPPMessageEvent).filter_by(action="StartTransaction").count() == 1

    meter_payload = {
        "transactionId": transaction_id,
        "meterValue": [{
            "timestamp": "2026-01-01T00:00:00Z",
            "sampledValue": [{
                "value": "120",
                "measurand": "Energy.Active.Import.Register",
                "unit": "Wh",
            }],
        }],
    }
    await handler.handle_message(sample_commercial_charge_point.ocpp_identity, "MeterValues", meter_payload, message_unique_id="phase3-meter-1")
    await handler.handle_message(sample_commercial_charge_point.ocpp_identity, "MeterValues", meter_payload, message_unique_id="phase3-meter-1")
    session = db_session.query(ChargingSession).filter_by(transaction_id=transaction_id).one()
    assert db_session.query(MeterValue).filter_by(session_id=session.id).count() == 1
    assert db_session.query(OCPPMessageEvent).filter_by(action="MeterValues").count() == 0

    stop_payload = {"transactionId": transaction_id, "meterStop": 120, "reason": "Local"}
    await handler.handle_message(sample_commercial_charge_point.ocpp_identity, "StopTransaction", stop_payload, message_unique_id="phase3-stop-1")
    await handler.handle_message(sample_commercial_charge_point.ocpp_identity, "StopTransaction", stop_payload, message_unique_id="phase3-stop-1")
    db_session.refresh(session)
    assert session.status == "completed"
    assert session.payment_status == "unpaid"
    assert db_session.query(OutboxEvent).filter_by(aggregate_id=str(session.id)).count() == 2
    assert db_session.query(OCPPMessageEvent).filter_by(action="StopTransaction").count() == 1
