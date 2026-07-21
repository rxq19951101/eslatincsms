"""
充电桩API单元测试
"""
import pytest
import uuid
from decimal import Decimal
from fastapi.testclient import TestClient

from app.core.auth import create_access_token, get_password_hash
from app.database.models import AppUser, ChargePoint, Site, Tenant


class TestChargersAPI:
    """充电桩API测试类"""
    
    def test_list_chargers_empty(self, admin_client: TestClient):
        """测试获取空充电桩列表"""
        response = admin_client.get("/api/v1/chargers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert len(response.json()) == 0
    
    def test_list_chargers_with_data(self, admin_client: TestClient, sample_charge_point):
        """测试获取有数据的充电桩列表"""
        response = admin_client.get("/api/v1/chargers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        assert any(cp["id"] == str(sample_charge_point.id) for cp in data)
    
    def test_list_chargers_filter_configured(self, admin_client: TestClient, sample_charge_point, sample_site, db_session):
        """测试筛选已配置的充电桩"""
        # 需要添加定价规则
        from app.database.models import Tariff
        from datetime import datetime, timezone
        tariff = Tariff(
            tenant_id=sample_site.tenant_id,
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
        
        response = admin_client.get("/api/v1/chargers?filter_type=configured")
        assert response.status_code == 200
        data = response.json()
        # 应该包含已配置的充电桩
        assert isinstance(data, list)

    def test_app_user_lists_configured_chargers_without_tenant_header(
        self,
        client: TestClient,
        db_session,
        sample_charge_point,
    ):
        app_user = AppUser(
            id=uuid.uuid4(),
            email="app-charger-discovery@example.test",
            password_hash=get_password_hash("test-password"),
            email_verified=True,
            balance=Decimal("0.00"),
            status="active",
        )
        db_session.add(app_user)
        db_session.commit()

        token = create_access_token({
            "user_id": str(app_user.id),
            "user_type": "app_user",
            "aud": "app",
        })
        response = client.get(
            "/api/v1/app/chargers?filter_type=configured",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert "X-Tenant-Id" not in response.request.headers
        assert any(
            charger["id"] == str(sample_charge_point.id)
            for charger in response.json()
        )

        invalid_response = client.get(
            "/api/v1/app/chargers?filter_type=configured",
            headers={"Authorization": "Bearer invalid-app-token"},
        )
        assert invalid_response.status_code == 401

    def test_app_public_chargers_cross_tenants_and_ignore_tenant_header(
        self,
        client: TestClient,
        db_session,
        sample_charge_point,
        sample_tenant,
    ):
        other_tenant = Tenant(name="App public other tenant", status="active")
        db_session.add(other_tenant)
        db_session.flush()
        other_site = Site(
            tenant_id=other_tenant.id,
            name="Other public site",
            address="Other address",
            latitude=4.61,
            longitude=-74.08,
            is_active=True,
        )
        db_session.add(other_site)
        db_session.flush()
        other_charge_point = ChargePoint(
            tenant_id=other_tenant.id,
            site_id=other_site.id,
            ocpp_identity="CP-APP-PUBLIC-OTHER",
            is_active=True,
        )
        app_user = AppUser(
            email="app-cross-tenant@example.test",
            password_hash=get_password_hash("test-password"),
            email_verified=True,
            balance=Decimal("0.00"),
            status="active",
        )
        db_session.add_all([other_charge_point, app_user])
        db_session.commit()

        token = create_access_token({
            "user_id": str(app_user.id),
            "user_type": "app_user",
            "aud": "app",
        })
        response = client.get(
            "/api/v1/app/chargers",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-Id": str(sample_tenant.id),
            },
        )

        assert response.status_code == 200
        identities = {item["ocpp_identity"] for item in response.json()}
        assert sample_charge_point.ocpp_identity in identities
        assert other_charge_point.ocpp_identity in identities
    
    def test_get_charger_by_id(self, admin_client: TestClient, sample_charge_point):
        """测试根据ID获取充电桩"""
        response = admin_client.get(f"/api/v1/chargers/{sample_charge_point.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_charge_point.id)
        assert data["ocpp_identity"] == sample_charge_point.ocpp_identity
    
    def test_get_charger_by_id_not_found(self, admin_client: TestClient):
        """测试获取不存在的充电桩"""
        response = admin_client.get("/api/v1/chargers/CP-NOT-FOUND")
        assert response.status_code == 404
    
    def test_create_charger(self, admin_client: TestClient, sample_site):
        """测试创建充电桩"""
        payload = {
            "id": "CP-CREATE-001",
            "vendor": "新厂商",
            "model": "新型号",
            "site_id": str(sample_site.id)
        }
        response = admin_client.post("/api/v1/chargers", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["ocpp_identity"] == "CP-CREATE-001"
    
    def test_update_charger(self, admin_client: TestClient, sample_charge_point):
        """测试更新充电桩"""
        payload = {
            "vendor": "更新厂商",
            "model": "更新型号"
        }
        response = admin_client.put(f"/api/v1/chargers/{sample_charge_point.id}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["vendor"] == "更新厂商"
    
    def test_delete_charger(self, admin_client: TestClient, sample_charge_point):
        """测试删除充电桩"""
        response = admin_client.delete(f"/api/v1/chargers/{sample_charge_point.id}")
        assert response.status_code == 200
        
        # 验证已删除
        response = admin_client.get(f"/api/v1/chargers/{sample_charge_point.id}")
        assert response.status_code == 404
