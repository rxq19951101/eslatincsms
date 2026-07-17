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
    db_session, sample_charge_point, sample_evse, sample_evse_status
):
    handler = OCPPMessageHandler()
    start_payload = {
        "transactionId": 9001,
        "connectorId": 1,
        "idTag": "TEST_TAG",
        "meterStart": 100,
    }
    first_start = await handler.handle_start_transaction(
        sample_charge_point.id, start_payload, evse_id=1, db=db_session
    )
    second_start = await handler.handle_start_transaction(
        sample_charge_point.id, start_payload, evse_id=1, db=db_session
    )
    assert first_start["idTagInfo"]["status"] == "Accepted"
    assert second_start["idTagInfo"]["status"] == "Accepted"
    assert db_session.query(ChargingSession).filter_by(transaction_id=9001).count() == 1
    assert db_session.query(OCPPMessageEvent).filter_by(action="StartTransaction").count() == 1

    meter_payload = {
        "transactionId": 9001,
        "meterValue": [{
            "timestamp": "2026-01-01T00:00:00Z",
            "sampledValue": [{
                "value": "120",
                "measurand": "Energy.Active.Import.Register",
                "unit": "Wh",
            }],
        }],
    }
    await handler.handle_meter_values(sample_charge_point.id, meter_payload, db=db_session)
    await handler.handle_meter_values(sample_charge_point.id, meter_payload, db=db_session)
    session = db_session.query(ChargingSession).filter_by(transaction_id=9001).one()
    assert db_session.query(MeterValue).filter_by(session_id=session.id).count() == 1
    assert db_session.query(OCPPMessageEvent).filter_by(action="MeterValues").count() == 1

    stop_payload = {"transactionId": 9001, "meterStop": 120, "reason": "Local"}
    await handler.handle_stop_transaction(sample_charge_point.id, stop_payload, db=db_session)
    await handler.handle_stop_transaction(sample_charge_point.id, stop_payload, db=db_session)
    db_session.refresh(session)
    assert session.status == "completed"
    assert db_session.query(OutboxEvent).filter_by(aggregate_id=str(session.id)).count() == 2
    assert db_session.query(OCPPMessageEvent).filter_by(action="StopTransaction").count() == 1
