"""
设备管理API单元测试
"""
import pytest
from fastapi.testclient import TestClient
from app.database.models import Device
from app.core.crypto import derive_password, decrypt_master_secret


class TestDevicesAPI:
    """设备管理API测试类"""
    
    def test_create_device_success(self, client: TestClient, db_session):
        """测试成功创建设备"""
        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "123456789012345",
                "device_type_code": "zcf"  # 直接指定设备类型代码
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["serial_number"] == "123456789012345"
        # 验证设备类型
        assert data["device_type_code"] in ["zcf", "default"]
        assert data["mqtt_client_id"] == f"{data['device_type_code']}&123456789012345"
        assert data["mqtt_username"] == "123456789012345"
        assert len(data["mqtt_password"]) == 12  # 密码必须是12位
        assert data["is_active"] is True
        
        # 验证设备已保存到数据库
        device = db_session.query(Device).filter(
            Device.serial_number == "123456789012345"
        ).first()
        assert device is not None
        assert device.mqtt_client_id == data["mqtt_client_id"]
    
    def test_create_device_duplicate(self, client: TestClient, sample_device, db_session):
        """测试创建重复设备"""
        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": sample_device.serial_number,
                "vendor": "Test Vendor"
            }
        )
        assert response.status_code == 400
        assert "已存在" in response.json()["detail"]
    
    def test_create_device_invalid_serial_length(self, client: TestClient):
        """测试创建序列号长度无效的设备"""
        # 序列号太短
        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "12345",  # 只有5位
                "vendor": "Test Vendor"
            }
        )
        assert response.status_code == 422  # 验证错误
        
        # 序列号太长
        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "12345678901234567890",  # 20位
                "vendor": "Test Vendor"
            }
        )
        assert response.status_code == 422
    
    def test_create_device_with_type_code(self, client: TestClient, db_session):
        """测试使用设备类型代码创建设备"""
        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "987654321098765",
                "device_type_code": "zcf"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["device_type_code"] == "zcf"
    
    def test_create_device_invalid_type_code(self, client: TestClient):
        """测试使用设备类型代码（现在不再验证类型代码是否存在，直接使用）"""
        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "111111111111111",
                "device_type_code": "invalid_type"
            }
        )
        # 现在不再验证类型代码是否存在，直接使用提供的type_code
        assert response.status_code == 201
        data = response.json()
        assert data["device_type_code"] == "invalid_type"
    
    def test_list_devices_empty(self, client: TestClient):
        """测试获取空设备列表"""
        response = client.get("/api/v1/devices")
        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert "total" in data
        assert isinstance(data["devices"], list)
    
    def test_list_devices_with_data(self, client: TestClient, sample_device, db_session):
        """测试获取有数据的设备列表"""
        response = client.get("/api/v1/devices")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0
        assert any(d["serial_number"] == sample_device.serial_number for d in data["devices"])
    
    def test_list_devices_filter_by_type(self, client: TestClient, sample_device, db_session):
        """测试按设备类型筛选"""
        response = client.get(
            f"/api/v1/devices?device_type_code={sample_device.type_code}"
        )
        assert response.status_code == 200
        data = response.json()
        assert all(d["device_type_code"] == sample_device.type_code for d in data["devices"])
    
    def test_list_devices_filter_by_active(self, client: TestClient, sample_device, db_session):
        """测试按激活状态筛选"""
        # 测试激活的设备
        response = client.get("/api/v1/devices?is_active=true")
        assert response.status_code == 200
        data = response.json()
        assert all(d["is_active"] is True for d in data["devices"])
        
        # 测试未激活的设备
        sample_device.is_active = False
        db_session.commit()
        response = client.get("/api/v1/devices?is_active=false")
        assert response.status_code == 200
        data = response.json()
        assert all(d["is_active"] is False for d in data["devices"])
    
    def test_list_devices_pagination(self, client: TestClient, db_session):
        """测试设备列表分页"""
        # 创建多个设备
        from app.services.charge_point_service import ChargePointService
        for i in range(5):
            serial = f"{i:015d}"  # 生成15位序列号
            ChargePointService.get_or_create_device(
                db=db_session,
                device_serial_number=serial,
                vendor="Test Vendor"
            )
        db_session.commit()
        
        # 测试分页
        response = client.get("/api/v1/devices?skip=0&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["devices"]) <= 2
        assert data["total"] >= 5
    
    def test_get_device_detail(self, client: TestClient, sample_device, db_session):
        """测试获取设备详情"""
        response = client.get(f"/api/v1/devices/{sample_device.serial_number}")
        assert response.status_code == 200
        data = response.json()
        assert data["serial_number"] == sample_device.serial_number
        assert data["device_type_code"] == sample_device.type_code
        assert data["mqtt_client_id"] == sample_device.mqtt_client_id
        assert data["mqtt_username"] == sample_device.mqtt_username
        assert len(data["mqtt_password"]) == 12
    
    def test_get_device_not_found(self, client: TestClient):
        """测试获取不存在的设备"""
        response = client.get("/api/v1/devices/999999999999999")
        assert response.status_code == 404
        assert "不存在" in response.json()["detail"]
    
    def test_get_device_password(self, client: TestClient, sample_device, db_session):
        """测试获取设备MQTT密码"""
        response = client.get(f"/api/v1/devices/{sample_device.serial_number}/password")
        assert response.status_code == 200
        data = response.json()
        assert data["serial_number"] == sample_device.serial_number
        assert data["mqtt_client_id"] == sample_device.mqtt_client_id
        assert data["mqtt_username"] == sample_device.mqtt_username
        assert len(data["mqtt_password"]) == 12
        
        # 验证密码是正确的（通过重新计算）
        master_secret = decrypt_master_secret(sample_device.master_secret_encrypted)
        expected_password = derive_password(master_secret, sample_device.serial_number)
        assert data["mqtt_password"] == expected_password
    
    def test_get_device_password_not_found(self, client: TestClient):
        """测试获取不存在设备的密码"""
        response = client.get("/api/v1/devices/999999999999999/password")
        assert response.status_code == 404
    
    def test_activate_device(self, client: TestClient, sample_device, db_session):
        """测试激活设备"""
        # 先停用设备
        sample_device.is_active = False
        db_session.commit()
        
        # 激活设备
        response = client.put(
            f"/api/v1/devices/{sample_device.serial_number}/activate?is_active=true"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True
        
        # 验证数据库已更新
        db_session.refresh(sample_device)
        assert sample_device.is_active is True
    
    def test_deactivate_device(self, client: TestClient, sample_device, db_session):
        """测试停用设备"""
        # 先激活设备
        sample_device.is_active = True
        db_session.commit()
        
        # 停用设备
        response = client.put(
            f"/api/v1/devices/{sample_device.serial_number}/activate?is_active=false"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False
        
        # 验证数据库已更新
        db_session.refresh(sample_device)
        assert sample_device.is_active is False
    
    def test_activate_device_not_found(self, client: TestClient):
        """测试激活不存在的设备"""
        response = client.put(
            "/api/v1/devices/999999999999999/activate?is_active=true"
        )
        assert response.status_code == 404
    
    def test_device_password_consistency(self, client: TestClient, sample_device, db_session):
        """测试设备密码的一致性（多次调用返回相同密码）"""
        # 第一次获取密码
        response1 = client.get(f"/api/v1/devices/{sample_device.serial_number}/password")
        password1 = response1.json()["mqtt_password"]
        
        # 第二次获取密码
        response2 = client.get(f"/api/v1/devices/{sample_device.serial_number}/password")
        password2 = response2.json()["mqtt_password"]
        
        # 密码应该相同
        assert password1 == password2
        
        # 验证密码是正确的
        master_secret = decrypt_master_secret(sample_device.master_secret_encrypted)
        expected_password = derive_password(master_secret, sample_device.serial_number)
        assert password1 == expected_password
    
    def test_create_device_auto_device_type(self, client: TestClient, db_session):
        """测试自动推断设备类型代码"""
        # 使用新的vendor，应该自动推断设备类型代码
        response = client.post(
            "/api/v1/devices",
            json={
                "serial_number": "555555555555555",
                "vendor": "New Vendor Brand"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["device_type_code"] is not None
        # 新vendor应该推断为default类型
        assert data["device_type_code"] == "default"
        
        # 验证设备已创建，且每个设备独立存储master_secret
        device = db_session.query(Device).filter(
            Device.serial_number == "555555555555555"
        ).first()
        assert device is not None
        assert device.master_secret_encrypted is not None
        assert device.type_code == "default"

