"""
OCPP控制API单元测试
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.database.models import ChargingSession, OutboxEvent, Tenant


class TestOCPPControlAPI:
    """OCPP控制API测试类"""
    
    def test_remote_start_transaction(self, admin_client: TestClient, sample_charge_point, sample_evse):
        """测试远程启动交易"""
        payload = {
            "charge_point_id": sample_charge_point.ocpp_identity,
            "id_tag": "TEST_USER_001",
            "connector_id": 1
        }
        response = admin_client.post("/api/v1/ocpp/remote-start-transaction", json=payload)
        # 可能返回200（成功）或503（服务不可用，如果MQTT未连接）
        assert response.status_code in [200, 503]
        if response.status_code == 200:
            data = response.json()
            assert "success" in data

    def test_remote_start_accepts_body_idempotency_key_and_replays_once(
        self, admin_client: TestClient, db_session, sample_charge_point, sample_evse
    ):
        from app.api.v1 import ocpp_control

        payload = {
            "charge_point_id": sample_charge_point.ocpp_identity,
            "id_tag": "BODY-IDEMPOTENT",
            "connector_id": sample_evse.evse_id,
            "idempotency_key": "scenario-remote-start-001",
        }
        with patch.dict(ocpp_control._remote_start_inflight, {}, clear=True), patch(
            "app.api.v1.ocpp_control.check_charger_connection", return_value=True
        ), patch(
            "app.api.v1.ocpp_control.message_handler.send_call",
            new=AsyncMock(return_value={"success": True, "status": "Accepted"}),
        ) as sender:
            first = admin_client.post("/api/v1/ocpp/remote-start-transaction", json=payload)
            replay = admin_client.post("/api/v1/ocpp/remote-start-transaction", json=payload)

        assert first.status_code == replay.status_code == 200
        assert first.json()["success"] is True
        assert replay.json()["success"] is True
        assert replay.json()["details"]["idempotent_replay"] is True
        sender.assert_awaited_once()
        event = db_session.query(OutboxEvent).filter_by(
            idempotency_key="remote-command:scenario-remote-start-001"
        ).one()
        assert event.payload["id_tag"] == "BODY-IDEMPOTENT"

    def test_remote_start_rejects_conflicting_header_and_body_idempotency_keys(
        self, admin_client: TestClient, db_session, sample_charge_point, sample_evse
    ):
        response = admin_client.post(
            "/api/v1/ocpp/remote-start-transaction",
            headers={"Idempotency-Key": "header-command-key"},
            json={
                "charge_point_id": sample_charge_point.ocpp_identity,
                "id_tag": "CONFLICT",
                "connector_id": sample_evse.evse_id,
                "idempotency_key": "body-command-key",
            },
        )

        assert response.status_code == 422
        assert db_session.query(OutboxEvent).filter(
            OutboxEvent.idempotency_key.in_([
                "remote-command:header-command-key",
                "remote-command:body-command-key",
            ])
        ).count() == 0
    
    def test_remote_stop_transaction(self, admin_client: TestClient, db_session, sample_charge_point, sample_evse):
        """测试远程停止交易"""
        payload = {
            "charge_point_id": sample_charge_point.ocpp_identity,
            "transaction_id": 12345
        }
        db_session.add(ChargingSession(
            tenant_id=sample_charge_point.tenant_id,
            evse_id=sample_evse.id,
            charge_point_id=sample_charge_point.id,
            transaction_id=12345,
            id_tag="TEST_USER_001",
            start_time=datetime.now(timezone.utc),
            status="ongoing",
        ))
        db_session.commit()
        response = admin_client.post("/api/v1/ocpp/remote-stop-transaction", json=payload)
        # 可能返回200（成功）或503（服务不可用）
        assert response.status_code in [200, 503]
    
    def test_change_configuration(self, admin_client: TestClient, sample_charge_point):
        """测试更改配置"""
        payload = {
            "charge_point_id": sample_charge_point.ocpp_identity,
            "key": "HeartbeatInterval",
            "value": "60"
        }
        response = admin_client.post("/api/v1/ocpp/change-configuration", json=payload)
        assert response.status_code in [200, 503]
    
    def test_get_configuration(self, admin_client: TestClient, sample_charge_point):
        """测试获取配置"""
        payload = {
            "charge_point_id": sample_charge_point.ocpp_identity,
            "keys": ["HeartbeatInterval"]
        }
        response = admin_client.post("/api/v1/ocpp/get-configuration", json=payload)
        assert response.status_code in [200, 503]
    
    def test_reset(self, admin_client: TestClient, sample_charge_point):
        """测试重置充电桩"""
        payload = {
            "charge_point_id": sample_charge_point.ocpp_identity,
            "type": "Hard"
        }
        response = admin_client.post("/api/v1/ocpp/reset", json=payload)
        assert response.status_code in [200, 503]
    
    def test_unlock_connector(self, admin_client: TestClient, sample_charge_point):
        """测试解锁连接器"""
        payload = {
            "charge_point_id": sample_charge_point.ocpp_identity,
            "connector_id": 1
        }
        response = admin_client.post("/api/v1/ocpp/unlock-connector", json=payload)
        assert response.status_code in [200, 503]

    @pytest.mark.parametrize(
        ("method", "path", "payload"),
        [
            ("post", "/api/v1/ocpp/change-configuration", {"charge_point_id": "CP-1", "key": "k", "value": "v"}),
            ("post", "/api/v1/ocpp/get-configuration", {"charge_point_id": "CP-1"}),
            ("post", "/api/v1/ocpp/unlock-connector", {"charge_point_id": "CP-1", "connector_id": 1}),
            ("get", "/api/v1/ocpp/connected", None),
        ],
    )
    def test_management_endpoints_require_authentication(self, client, method, path, payload):
        client.headers.pop("Authorization", None)
        response = getattr(client, method)(path, json=payload) if payload else getattr(client, method)(path)
        assert response.status_code == 401

    @pytest.mark.parametrize("path", ["changeConfiguration", "getConfiguration", "unlockConnector"])
    def test_legacy_camel_case_routes_are_removed(self, admin_client, path):
        assert admin_client.post(f"/api/v1/ocpp/{path}", json={}).status_code == 404

    @pytest.mark.parametrize(
        ("path", "payload"),
        [
            ("change-configuration", {"chargePointId": "CP-1", "key": "k", "value": "v"}),
            ("get-configuration", {"chargePointId": "CP-1"}),
            ("unlock-connector", {"chargePointId": "CP-1", "connectorId": 1}),
        ],
    )
    def test_camel_case_request_fields_are_rejected(self, admin_client, path, payload):
        assert admin_client.post(f"/api/v1/ocpp/{path}", json=payload).status_code == 422

    def test_management_commands_are_tenant_scoped(
        self, admin_client, db_session, sample_charge_point
    ):
        other_tenant = Tenant(name="Other OCPP tenant", status="active")
        db_session.add(other_tenant)
        db_session.commit()
        admin_client.headers.update({"X-Tenant-Id": str(other_tenant.id)})

        requests = [
            ("change-configuration", {"charge_point_id": sample_charge_point.ocpp_identity, "key": "k", "value": "v"}),
            ("get-configuration", {"charge_point_id": sample_charge_point.ocpp_identity}),
            ("unlock-connector", {"charge_point_id": sample_charge_point.ocpp_identity, "connector_id": 1}),
        ]
        for path, payload in requests:
            assert admin_client.post(f"/api/v1/ocpp/{path}", json=payload).status_code == 403

    def test_connected_list_is_authenticated_and_tenant_scoped(
        self, admin_client, db_session, sample_charge_point
    ):
        other_tenant = Tenant(name="Connected other tenant", status="active")
        db_session.add(other_tenant)
        db_session.flush()
        other_charge_point = type(sample_charge_point)(
            id="CP-OTHER-CONNECTED",
            tenant_id=other_tenant.id,
            site_id=sample_charge_point.site_id,
            vendor="Other vendor",
            model="Other model",
            is_active=True,
        )
        db_session.add(other_charge_point)
        db_session.commit()

        with patch.object(
            __import__("app.api.v1.ocpp_control", fromlist=["connection_manager"]).connection_manager,
            "get_all_charger_ids",
            return_value=[sample_charge_point.ocpp_identity, other_charge_point.ocpp_identity],
            create=True,
        ):
            response = admin_client.get("/api/v1/ocpp/connected")

        assert response.status_code == 200
        assert response.json()["connected_chargers"] == [sample_charge_point.ocpp_identity]

    def test_debug_connection_endpoint_is_removed(self, admin_client, sample_charge_point):
        response = admin_client.get(
            f"/api/v1/ocpp/debug/connection-status/{sample_charge_point.ocpp_identity}"
        )
        assert response.status_code == 404

    def test_idempotent_replay_preserves_device_rejection(
        self, admin_client, db_session, sample_charge_point, sample_evse
    ):
        payload = {
            "charge_point_id": sample_charge_point.ocpp_identity,
            "id_tag": "REJECTED",
            "connector_id": sample_evse.evse_id,
        }
        headers = {"Idempotency-Key": "start-device-rejected"}
        with patch("app.api.v1.ocpp_control.check_charger_connection", return_value=True), patch(
            "app.api.v1.ocpp_control.message_handler.send_call",
            new=AsyncMock(return_value={"success": False, "status": "Rejected"}),
        ) as sender:
            first = admin_client.post("/api/v1/ocpp/remote-start-transaction", json=payload, headers=headers)
            replay = admin_client.post("/api/v1/ocpp/remote-start-transaction", json=payload, headers=headers)

        assert first.status_code == replay.status_code == 200
        assert first.json()["success"] is False
        assert replay.json()["success"] is False
        assert replay.json()["details"]["status"] == "Rejected"
        assert replay.json()["details"]["idempotent_replay"] is True
        sender.assert_awaited_once()
        event = db_session.query(OutboxEvent).filter_by(
            idempotency_key="remote-command:start-device-rejected"
        ).one()
        assert event.payload["command_result"]["success"] is False

    def test_idempotent_replay_preserves_offline_failure(
        self, admin_client, db_session, sample_charge_point
    ):
        payload = {"charge_point_id": sample_charge_point.ocpp_identity, "type": "Soft"}
        headers = {"Idempotency-Key": "reset-offline"}
        with patch("app.api.v1.ocpp_control.check_charger_connection", return_value=False):
            first = admin_client.post("/api/v1/ocpp/reset", json=payload, headers=headers)
            replay = admin_client.post("/api/v1/ocpp/reset", json=payload, headers=headers)

        assert first.status_code == replay.status_code == 503
        event = db_session.query(OutboxEvent).filter_by(
            idempotency_key="remote-command:reset-offline"
        ).one()
        assert event.payload["command_result"]["status_code"] == 503
        assert event.status == "failed"

    def test_idempotent_replay_preserves_sender_exception(
        self, admin_client, db_session, sample_charge_point, sample_evse
    ):
        payload = {
            "charge_point_id": sample_charge_point.ocpp_identity,
            "id_tag": "SEND-ERROR",
            "connector_id": sample_evse.evse_id,
        }
        headers = {"Idempotency-Key": "start-sender-error"}
        with patch("app.api.v1.ocpp_control.check_charger_connection", return_value=True), patch(
            "app.api.v1.ocpp_control.message_handler.send_call",
            new=AsyncMock(side_effect=RuntimeError("transport failed")),
        ) as sender:
            first = admin_client.post("/api/v1/ocpp/remote-start-transaction", json=payload, headers=headers)
            replay = admin_client.post("/api/v1/ocpp/remote-start-transaction", json=payload, headers=headers)

        assert first.status_code == replay.status_code == 502
        sender.assert_awaited_once()
        event = db_session.query(OutboxEvent).filter_by(
            idempotency_key="remote-command:start-sender-error"
        ).one()
        assert event.payload["command_result"]["status_code"] == 502
