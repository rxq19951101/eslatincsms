"""
OCPP控制API单元测试
"""
import pytest
from fastapi.testclient import TestClient


class TestOCPPControlAPI:
    """OCPP控制API测试类"""
    
    def test_remote_start_transaction(self, client: TestClient, sample_charge_point):
        """测试远程启动交易"""
        payload = {
            "chargePointId": sample_charge_point.id,
            "idTag": "TEST_USER_001",
            "connectorId": 1
        }
        response = client.post("/api/v1/ocpp/remote-start-transaction", json=payload)
        # 可能返回200（成功）或503（服务不可用，如果MQTT未连接）
        assert response.status_code in [200, 503]
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
    
    def test_remote_stop_transaction(self, client: TestClient, sample_charge_point):
        """测试远程停止交易"""
        payload = {
            "chargePointId": sample_charge_point.id,
            "transactionId": 12345
        }
        response = client.post("/api/v1/ocpp/remote-stop-transaction", json=payload)
        # 可能返回200（成功）或503（服务不可用）
        assert response.status_code in [200, 503]
    
    def test_change_configuration(self, client: TestClient, sample_charge_point):
        """测试更改配置"""
        payload = {
            "chargePointId": sample_charge_point.id,
            "key": "HeartbeatInterval",
            "value": "60"
        }
        response = client.post("/api/v1/ocpp/change-configuration", json=payload)
        assert response.status_code in [200, 503]
    
    def test_get_configuration(self, client: TestClient, sample_charge_point):
        """测试获取配置"""
        payload = {
            "chargePointId": sample_charge_point.id,
            "keys": ["HeartbeatInterval"]
        }
        response = client.post("/api/v1/ocpp/get-configuration", json=payload)
        assert response.status_code in [200, 503]
    
    def test_reset(self, client: TestClient, sample_charge_point):
        """测试重置充电桩"""
        payload = {
            "chargePointId": sample_charge_point.id,
            "type": "Hard"
        }
        response = client.post("/api/v1/ocpp/reset", json=payload)
        assert response.status_code in [200, 503]
    
    def test_unlock_connector(self, client: TestClient, sample_charge_point):
        """测试解锁连接器"""
        payload = {
            "chargePointId": sample_charge_point.id,
            "connectorId": 1
        }
        response = client.post("/api/v1/ocpp/unlock-connector", json=payload)
        assert response.status_code in [200, 503]

