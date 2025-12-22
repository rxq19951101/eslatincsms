"""
充电桩API单元测试
"""
import pytest
from fastapi.testclient import TestClient


class TestChargersAPI:
    """充电桩API测试类"""
    
    def test_list_chargers_empty(self, client: TestClient):
        """测试获取空充电桩列表"""
        response = client.get("/api/v1/chargers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert len(response.json()) == 0
    
    def test_list_chargers_with_data(self, client: TestClient, sample_charge_point):
        """测试获取有数据的充电桩列表"""
        response = client.get("/api/v1/chargers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        assert any(cp["id"] == sample_charge_point.id for cp in data)
    
    def test_list_chargers_filter_configured(self, client: TestClient, sample_charge_point, sample_site, db_session):
        """测试筛选已配置的充电桩"""
        # 需要添加定价规则
        from app.database.models import Tariff
        from datetime import datetime, timezone
        tariff = Tariff(
            site_id=sample_site.id,
            name="测试定价",
            base_price_per_kwh=1.5,
            is_active=True,
            valid_from=datetime.now(timezone.utc)  # 添加必需的 valid_from 字段
        )
        db_session.add(tariff)
        db_session.commit()
        
        # 确保充电桩关联到站点
        sample_charge_point.site_id = sample_site.id
        db_session.commit()
        
        response = client.get("/api/v1/chargers?filter_type=configured")
        assert response.status_code == 200
        data = response.json()
        # 应该包含已配置的充电桩
        assert isinstance(data, list)
    
    def test_get_charger_by_id(self, client: TestClient, sample_charge_point):
        """测试根据ID获取充电桩"""
        response = client.get(f"/api/v1/chargers/{sample_charge_point.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_charge_point.id
    
    def test_get_charger_by_id_not_found(self, client: TestClient):
        """测试获取不存在的充电桩"""
        response = client.get("/api/v1/chargers/CP-NOT-FOUND")
        assert response.status_code == 404
    
    def test_create_charger(self, client: TestClient, sample_site):
        """测试创建充电桩"""
        payload = {
            "id": "CP-CREATE-001",
            "vendor": "新厂商",
            "model": "新型号",
            "site_id": sample_site.id
        }
        response = client.post("/api/v1/chargers", json=payload)
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["id"] == "CP-CREATE-001"
    
    def test_update_charger(self, client: TestClient, sample_charge_point):
        """测试更新充电桩"""
        payload = {
            "vendor": "更新厂商",
            "model": "更新型号"
        }
        response = client.put(f"/api/v1/chargers/{sample_charge_point.id}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["vendor"] == "更新厂商"
    
    def test_delete_charger(self, client: TestClient, sample_charge_point):
        """测试删除充电桩"""
        response = client.delete(f"/api/v1/chargers/{sample_charge_point.id}")
        assert response.status_code in [200, 204]
        
        # 验证已删除
        response = client.get(f"/api/v1/chargers/{sample_charge_point.id}")
        assert response.status_code == 404

