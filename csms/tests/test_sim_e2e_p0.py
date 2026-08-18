import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.api.v1.app.charging import StopChargingRequest, stop_charging
from app.api.v1.ocpp_control import send_remote_start, send_remote_stop
from app.database.models import (
    Alert,
    AppUser,
    ChargingSession,
    MeterValue,
    OCPPMessageEvent,
    PaymentOrder,
    PaymentWebhookEvent,
    QrToken,
)
from app.ocpp.connection_manager import ConnectionManager
from app.ocpp.transport.websocket_adapter import WebSocketAdapter
from app.services.ocpp_message_handler import OCPPMessageHandler


@pytest.mark.asyncio
async def test_unique_id_replay_returns_first_transaction_result(
    db_session, sample_commercial_charge_point, sample_evse, sample_evse_status
):
    # StartTransaction is a production-gated admission path.  Keep the
    # default sample_charge_point draft for rejection coverage, and use the
    # explicitly commissioned commercial fixture for this accepted replay.
    handler = OCPPMessageHandler()
    payload = {
        "connectorId": 1,
        "idTag": "SIM-E2E-TAG",
        "meterStart": 10,
        "timestamp": "2026-01-01T00:00:00Z",
    }

    first = await handler.handle_message(
        sample_commercial_charge_point.ocpp_identity,
        "StartTransaction",
        payload,
        evse_id=1,
        message_unique_id="start-unique-1",
    )
    replay = await handler.handle_message(
        sample_commercial_charge_point.ocpp_identity,
        "StartTransaction",
        payload,
        evse_id=1,
        message_unique_id="start-unique-1",
    )

    assert first == replay
    assert isinstance(first["transactionId"], int)
    assert first["transactionId"] > 0
    assert db_session.query(ChargingSession).count() == 1
    event = db_session.query(OCPPMessageEvent).filter_by(
        unique_id="start-unique-1"
    ).one()
    assert event.response_payload["transactionId"] == first["transactionId"]
    assert event.processing_status == "completed"


@pytest.mark.asyncio
async def test_unique_id_cannot_be_reused_for_different_payload(
    db_session, sample_charge_point
):
    handler = OCPPMessageHandler()
    first = await handler.handle_message(
        sample_charge_point.ocpp_identity,
        "Authorize",
        {"idTag": "TAG-1"},
        message_unique_id="authorize-1",
    )
    conflict = await handler.handle_message(
        sample_charge_point.ocpp_identity,
        "Authorize",
        {"idTag": "TAG-2"},
        message_unique_id="authorize-1",
    )
    assert first["idTagInfo"]["status"] == "Accepted"
    assert conflict["_ocpp_error"]["code"] == "ProtocolError"
    assert db_session.query(OCPPMessageEvent).count() == 1


@pytest.mark.asyncio
async def test_meter_and_stop_before_start_are_traceable_without_orphans(
    db_session, sample_charge_point, sample_evse
):
    handler = OCPPMessageHandler()
    meter = await handler.handle_message(
        sample_charge_point.ocpp_identity,
        "MeterValues",
        {
            "connectorId": 1,
            "transactionId": 404,
            "meterValue": [{
                "timestamp": "2026-01-01T00:00:01Z",
                "sampledValue": [{
                    "measurand": "Energy.Active.Import.Register",
                    "value": "100",
                    "unit": "Wh",
                }],
            }],
        },
        message_unique_id="orphan-meter-1",
    )
    stop = await handler.handle_message(
        sample_charge_point.ocpp_identity,
        "StopTransaction",
        {"transactionId": 404, "meterStop": 100},
        message_unique_id="orphan-stop-1",
    )

    assert meter["_outcome"] == "orphan_ignored"
    assert stop["idTagInfo"]["status"] == "Invalid"
    assert db_session.query(MeterValue).count() == 0
    assert db_session.query(ChargingSession).count() == 0
    assert {
        event.outcome for event in db_session.query(OCPPMessageEvent).all()
    } == {"orphan_ignored"}


@pytest.mark.asyncio
async def test_faulted_alert_is_tenant_scoped_deduplicated_and_resolved(
    db_session, sample_charge_point, sample_evse, sample_evse_status
):
    handler = OCPPMessageHandler()
    fault = {"connectorId": 1, "status": "Faulted", "errorCode": "GroundFailure"}
    await handler.handle_message(
        sample_charge_point.ocpp_identity,
        "StatusNotification",
        fault,
        evse_id=1,
        message_unique_id="fault-1",
    )
    await handler.handle_message(
        sample_charge_point.ocpp_identity,
        "StatusNotification",
        fault,
        evse_id=1,
        message_unique_id="fault-2",
    )
    alert = db_session.query(Alert).one()
    assert alert.tenant_id == sample_charge_point.tenant_id
    assert alert.alert_type == "faulted"
    assert alert.status == "pending"

    await handler.handle_message(
        sample_charge_point.ocpp_identity,
        "StatusNotification",
        {"connectorId": 1, "status": "Available", "errorCode": "NoError"},
        evse_id=1,
        message_unique_id="recovered-1",
    )
    db_session.refresh(alert)
    assert alert.status == "resolved"


@pytest.mark.asyncio
async def test_disconnect_creates_one_charge_point_scoped_offline_alert(
    db_session, sample_charge_point
):
    from app.main import _mark_current_connection_offline

    await _mark_current_connection_offline(sample_charge_point.ocpp_identity)
    await _mark_current_connection_offline(sample_charge_point.ocpp_identity)

    alerts = db_session.query(Alert).filter_by(
        tenant_id=sample_charge_point.tenant_id,
        charge_point_id=sample_charge_point.id,
        alert_type="offline",
    ).all()
    assert len(alerts) == 1
    assert alerts[0].evse_id is None
    assert alerts[0].status == "pending"


def test_connection_manager_old_generation_cannot_remove_new_connection():
    manager = ConnectionManager()
    old_ws = object()
    new_ws = object()
    manager.connect("CP-1", old_ws, "generation-old")
    manager.connect("CP-1", new_ws, "generation-new")

    assert manager.disconnect("CP-1", "generation-old", old_ws) is False
    assert manager.get_connection("CP-1") is new_ws
    assert manager.disconnect("CP-1", "generation-new", new_ws) is True


@pytest.mark.asyncio
async def test_adapter_pending_requests_are_cleaned_by_connection_generation():
    class Socket:
        async def send_text(self, _message):
            return None

        async def close(self, *args, **kwargs):
            return None

    adapter = WebSocketAdapter()
    old_ws, new_ws = Socket(), Socket()
    await adapter.register_connection("CP-1", old_ws, "old")
    pending_call = asyncio.create_task(
        adapter.send_message("CP-1", "RemoteStartTransaction", {}, timeout=30)
    )
    await asyncio.sleep(0)
    assert len(adapter._pending_responses) == 1

    await adapter.register_connection("CP-1", new_ws, "new")
    assert not adapter._pending_responses
    with pytest.raises(asyncio.CancelledError):
        await pending_call
    assert await adapter.unregister_connection("CP-1", "old", old_ws) is False
    assert adapter.is_connected("CP-1")


def test_only_canonical_ocpp_websocket_route_is_registered(client):
    websocket_paths = [
        route.path for route in client.app.routes if route.__class__.__name__ == "APIWebSocketRoute"
    ]
    assert websocket_paths.count("/ocpp") == 1
    assert "/ocpp/{charge_point_id_path}" not in websocket_paths


def test_websocket_rejects_non_array_frames(client, sample_charge_point):
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect(
        f"/ocpp?id={sample_charge_point.ocpp_identity}",
        subprotocols=["ocpp1.6"],
    ) as websocket:
        websocket.send_json({"action": "Heartbeat", "payload": {}})
        with pytest.raises(WebSocketDisconnect) as exc:
            websocket.receive_json()
    assert exc.value.code == 1003


def test_standard_websocket_has_no_greeting_and_rejected_is_callresult(
    client, sample_charge_point
):
    with client.websocket_connect(
        f"/ocpp?id={sample_charge_point.ocpp_identity}",
        subprotocols=["ocpp1.6"],
    ) as websocket:
        websocket.send_json([2, "authorize-empty", "Authorize", {"idTag": ""}])
        response = websocket.receive_json()
    assert response == [
        3,
        "authorize-empty",
        {"idTagInfo": {"status": "Invalid"}},
    ]


@pytest.mark.asyncio
async def test_business_rejected_response_is_standard_callresult():
    from app.main import _handle_standard_ocpp_messages

    class Socket:
        def __init__(self):
            self.sent = []
            self.calls = 0

        async def receive_text(self):
            self.calls += 1
            if self.calls == 1:
                return json.dumps([2, "boot-rejected", "BootNotification", {}])
            raise RuntimeError("stop")

        async def send_text(self, value):
            self.sent.append(json.loads(value))

    socket = Socket()
    with patch(
        "app.main.handle_ocpp_message",
        new=AsyncMock(return_value={
            "status": "Rejected",
            "currentTime": "2026-01-01T00:00:00Z",
            "interval": 30,
        }),
    ):
        with pytest.raises(RuntimeError, match="stop"):
            await _handle_standard_ocpp_messages(socket, "CP-1", "generation-1")
    assert socket.sent == [[
        3,
        "boot-rejected",
        {"status": "Rejected", "currentTime": "2026-01-01T00:00:00Z", "interval": 30},
    ]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("helper", "device_status", "expected"),
    [
        (send_remote_start, "Accepted", True),
        (send_remote_start, "Rejected", False),
        (send_remote_stop, "Accepted", True),
        (send_remote_stop, "Rejected", False),
    ],
)
async def test_remote_command_success_uses_device_status(helper, device_status, expected):
    module = "app.api.v1.ocpp_control"
    with patch(f"{module}.check_charger_connection", return_value=True), patch(
        f"{module}.message_handler.send_call",
        new=AsyncMock(return_value={"success": True, "data": {"status": device_status}}),
    ):
        if helper is send_remote_start:
            result = await helper("CP-1", "TAG-1", 1)
        else:
            result = await helper("CP-1", 11)
    assert result.success is expected
    assert result.details["device_status"] == device_status


@pytest.mark.asyncio
async def test_concurrent_remote_start_accepts_only_one():
    from app.api.v1 import ocpp_control

    ocpp_control.mark_remote_start_finished("CP-CONCURRENT", 1)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed_accept(*args, **kwargs):
        entered.set()
        await release.wait()
        return {"success": True, "data": {"status": "Accepted"}}

    with patch("app.api.v1.ocpp_control.check_charger_connection", return_value=True), patch(
        "app.api.v1.ocpp_control.message_handler.send_call", new=AsyncMock(side_effect=delayed_accept)
    ) as sender:
        first_task = asyncio.create_task(send_remote_start("CP-CONCURRENT", "TAG-1", 1))
        await entered.wait()
        second = await send_remote_start("CP-CONCURRENT", "TAG-2", 1)
        release.set()
        first = await first_task

    assert first.success is True
    assert second.success is False
    assert second.details["workflow_status"] == "start_in_progress"
    assert sender.await_count == 1
    ocpp_control.mark_remote_start_finished("CP-CONCURRENT", 1)


@pytest.mark.asyncio
async def test_app_owner_can_stop_unpaid_session(
    db_session, sample_charge_point, sample_evse
):
    from app.core.auth import get_password_hash

    app_user = AppUser(
        email="safe-stop@example.test",
        password_hash=get_password_hash("safe-stop-password"),
        balance=Decimal("0.00"),
        has_unpaid_charges=True,
        status="active",
    )
    db_session.add(app_user)
    db_session.flush()
    qr = QrToken(
        token="safe-stop-qr-token-0001",
        operator_tenant_id=sample_charge_point.tenant_id,
        charge_point_id=sample_charge_point.id,
        connector_id=1,
    )
    db_session.add(qr)
    session = ChargingSession(
        tenant_id=sample_charge_point.tenant_id,
        evse_id=sample_evse.id,
        charge_point_id=sample_charge_point.id,
        transaction_id=7171,
        id_tag=f"APP{str(app_user.id).replace('-', '')[:17]}",
        user_id=str(app_user.id),
        app_user_id=app_user.id,
        start_time=datetime.now(timezone.utc),
        status="ongoing",
        payment_status="unpaid",
    )
    db_session.add(session)
    db_session.commit()

    accepted = type("RemoteResult", (), {
        "success": True,
        "message": "accepted",
        "details": {"device_status": "Accepted"},
    })()
    with patch(
        "app.api.v1.app.charging.send_remote_stop", new=AsyncMock(return_value=accepted)
    ) as remote_stop:
        result = await stop_charging(StopChargingRequest(qr_token=qr.token), app_user)

    assert result.success is True
    remote_stop.assert_awaited_once_with(sample_charge_point.ocpp_identity, 7171)


def test_qr_generation_log_never_contains_full_token(
    db_session, sample_charge_point, tmp_path, caplog
):
    from app.services.qr_service import generate_qr_code

    caplog.set_level("INFO")
    generated = generate_qr_code(db_session, sample_charge_point.id, 1, tmp_path)
    token = db_session.query(QrToken).filter_by(
        charge_point_id=sample_charge_point.id, connector_id=1
    ).one().token
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]

    assert generated.exists()
    assert token not in caplog.text
    assert digest in caplog.text


def test_sim_payment_webhook_is_signed_stateful_and_ledger_idempotent(
    client, db_session, sample_tenant, monkeypatch
):
    from app.api.v1.app.payments import build_sim_webhook_signature
    from app.core.auth import get_password_hash
    from app.database.models import AppWalletTransaction

    secret = "sim-webhook-test-secret"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SIM_E2E_WEBHOOK_SECRET", secret)
    user = AppUser(
        id=uuid.uuid4(),
        email="sim-payment@example.test",
        password_hash=get_password_hash("sim-payment-password"),
        balance=Decimal("0.00"),
        status="active",
    )
    order = PaymentOrder(
        id=uuid.uuid4(),
        app_user_id=user.id,
        type="top_up",
        amount=Decimal("25000.00"),
        currency="COP",
        payment_provider="fake",
        status="created",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add_all([user, order])
    db_session.commit()
    payload = {
        "event_id": "sim-payment-event-001",
        "provider": "fake",
        "status": "approved",
        "payment_order_id": str(order.id),
    }
    headers = {
        "Idempotency-Key": payload["event_id"],
        "X-Sim-Signature": build_sim_webhook_signature(payload, secret),
    }

    rejected = client.post(
        "/api/v1/app/payments/webhooks/sim",
        json=payload,
        headers={**headers, "X-Sim-Signature": "sha256=invalid"},
    )
    first = client.post("/api/v1/app/payments/webhooks/sim", json=payload, headers=headers)
    replay = client.post("/api/v1/app/payments/webhooks/sim", json=payload, headers=headers)

    assert rejected.status_code == 401
    assert first.status_code == 200
    assert first.json()["status"] == "approved"
    assert first.json()["order_status"] == "approved"
    assert first.json()["replayed"] is False
    assert first.json()["ledger_entry_count"] == 1
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["webhook_event_count"] == 1
    assert replay.json()["ledger_entry_count"] == 1
    db_session.refresh(user)
    assert user.balance == Decimal("25000.00")
    assert db_session.query(PaymentWebhookEvent).filter_by(
        payment_provider="fake", event_id=payload["event_id"]
    ).count() == 1
    assert db_session.query(AppWalletTransaction).filter_by(
        payment_order_id=order.id
    ).count() == 1


def test_sim_payment_webhook_is_not_available_in_production(client, monkeypatch):
    from app.api.v1.app.payments import build_sim_webhook_signature

    secret = "sim-webhook-test-secret"
    payload = {
        "event_id": "sim-payment-production-check",
        "provider": "fake",
        "status": "approved",
        "payment_order_id": str(uuid.uuid4()),
    }
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SIM_E2E_WEBHOOK_SECRET", secret)
    response = client.post(
        "/api/v1/app/payments/webhooks/sim",
        json=payload,
        headers={
            "Idempotency-Key": payload["event_id"],
            "X-Sim-Signature": build_sim_webhook_signature(payload, secret),
        },
    )
    assert response.status_code == 404


def test_seed_is_environment_guarded_idempotent_and_non_sensitive(
    db_session, monkeypatch, capsys
):
    from scripts import seed_sim_e2e
    from app.database.models import Tenant, ChargePoint, AppWalletTransaction, Role

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SIM_E2E_ADMIN_PASSWORD", "admin-seed-password")
    monkeypatch.setenv("SIM_E2E_APP_PASSWORD", "app-seed-password")
    monkeypatch.setenv("SIM_E2E_READONLY_PASSWORD", "readonly-seed-password")
    monkeypatch.setattr(seed_sim_e2e, "SessionLocal", lambda: db_session)

    seed_sim_e2e.main()
    first = json.loads(capsys.readouterr().out)
    seed_sim_e2e.main()
    second = json.loads(capsys.readouterr().out)

    assert first["charge_point"]["ocpp_identity"] == "SIM-E2E-CP-001"
    assert "password" not in json.dumps(first).lower()
    assert "jwt" not in json.dumps(first).lower()
    assert first == second
    assert first["fixtures"]["tenants"]["tenant_b"]["domain"] == "sim-e2e-b.local"
    assert first["fixtures"]["admins"]["readonly"]["username"] == "sim_e2e_readonly"
    assert first["fixtures"]["app_users"]["low_balance"]["balance"] == "0.00"
    assert first["fixtures"]["charge_points"]["tenant_b"]["ocpp_identity"] == "SIM-E2E-TENANT-B-CP-001"
    assert first["fixtures"]["qrs"]["other"]["payload"].startswith("qr:")
    assert db_session.query(Tenant).count() == 2
    assert db_session.query(ChargePoint).filter_by(ocpp_identity="SIM-E2E-CP-001").count() == 1
    assert db_session.query(AppWalletTransaction).filter_by(
        idempotency_key="sim-e2e-seed-opening-balance"
    ).count() == 1
    operator_role = db_session.get(Role, seed_sim_e2e.stable_id("role"))
    assert "alerts.write" in operator_role.permissions
    assert "transactions.read" in operator_role.permissions
    assert "alerts.manage" not in operator_role.permissions
    assert db_session.query(ChargingSession).filter_by(
        id=uuid.UUID(first["fixtures"]["ownership_session"]["id"])
    ).count() == 1
    ownership_session = db_session.get(
        ChargingSession,
        uuid.UUID(first["fixtures"]["ownership_session"]["id"]),
    )
    assert ownership_session.status == "completed"
    assert ownership_session.end_time is not None
    assert db_session.query(ChargingSession).filter_by(
        transaction_id=900001,
        status="ongoing",
    ).count() == 0

    from scripts import cleanup_sim_e2e

    discovered = cleanup_sim_e2e.discover_sim_session_ids(db_session)
    assert ownership_session.id in discovered
    assert cleanup_sim_e2e.unmatched_tenant_counts(db_session, discovered) == {}
    deleted = cleanup_sim_e2e.delete_allowlisted_rows(db_session, discovered)
    assert deleted["charging_sessions"] == 1
    assert cleanup_sim_e2e.matched_counts(db_session, discovered) == {}
    db_session.rollback()


def test_seed_refuses_production(monkeypatch):
    from scripts import seed_sim_e2e

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(SystemExit, match="disabled outside development/test"):
        seed_sim_e2e.main()


def test_cleanup_scope_does_not_expand_by_tenant_domain_or_tenant_id(db_session):
    from scripts import cleanup_sim_e2e
    from app.database.models import AppWalletTransaction, Tenant

    unrelated = Tenant(
        name="Unrelated tenant with reused test-looking domain",
        domain="sim-e2e.local",
        status="active",
    )
    db_session.add(unrelated)
    db_session.commit()

    tenant_condition = cleanup_sim_e2e.table_scope_condition(Tenant.__table__)
    matched_ids = set(
        db_session.execute(select(Tenant.id).where(tenant_condition)).scalars()
    )
    assert unrelated.id not in matched_ids

    ledger_condition = cleanup_sim_e2e.table_scope_condition(
        AppWalletTransaction.__table__
    )
    rendered = str(ledger_condition)
    assert "operator_tenant_id" not in rendered
    assert "tenant_id" not in rendered
