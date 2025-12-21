#!/usr/bin/env python3
#
# 创建测试数据
# 用于测试重构后的系统
#

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.base import SessionLocal, init_db
from app.database.models import (
    Site, ChargePoint, EVSE, EVSEStatus,
    DeviceType, Device,
    Tariff
)
from app.core.crypto import encrypt_master_secret, derive_password
from app.core.id_generator import generate_site_id, generate_charge_point_id
from datetime import datetime, timezone

def create_test_data():
    """创建测试数据"""
    db = SessionLocal()
    try:
        # 初始化数据库
        init_db()
        print("✓ 数据库表已初始化")
        
        # 1. 创建设备类型
        device_type = db.query(DeviceType).filter(DeviceType.type_code == "zcf").first()
        if not device_type:
            # 使用测试master secret（生产环境应该使用强随机密钥）
            master_secret = "test_master_secret_12345678901234567890"
            encrypted_secret = encrypt_master_secret(master_secret)
            
            device_type = DeviceType(
                type_code="zcf",
                type_name="中车充电桩",
                master_secret_encrypted=encrypted_secret,
                encryption_algorithm="AES-256-GCM"
            )
            db.add(device_type)
            db.flush()
            print(f"✓ 创建设备类型: {device_type.type_code}")
        else:
            print(f"✓ 设备类型已存在: {device_type.type_code}")
        
        # 2. 创建设备
        serial_number = "861076087029615"
        device = db.query(Device).filter(Device.serial_number == serial_number).first()
        if not device:
            device = Device(
                serial_number=serial_number,
                device_type_id=device_type.id,
                mqtt_client_id=f"{device_type.type_code}&{serial_number}",
                mqtt_username=serial_number
            )
            db.add(device)
            db.flush()
            print(f"✓ 创建设备: {serial_number}")
            
            # 显示派生密码（用于MQTT连接测试）
            master_secret = "test_master_secret_12345678901234567890"  # 实际应该从加密字段解密
            derived_password = derive_password(master_secret, serial_number)
            print(f"  设备MQTT密码（派生）: {derived_password}")
        else:
            print(f"✓ 设备已存在: {serial_number}")
        
        # 3. 创建站点
        site_id = generate_site_id("测试站点")
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            site = Site(
                id=site_id,
                name="测试站点",
                address="北京市朝阳区测试地址",
                latitude=39.9042,
                longitude=116.4074
            )
            db.add(site)
            db.flush()
            print(f"✓ 创建站点: {site.id}")
        else:
            print(f"✓ 站点已存在: {site.id}")
        
        # 4. 创建充电桩
        charge_point_id = generate_charge_point_id(serial_number=serial_number, vendor="中车")
        charge_point = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
        if not charge_point:
            charge_point = ChargePoint(
                id=charge_point_id,
                site_id=site.id,
                vendor="中车",
                model="ZCF-7KW",
                serial_number=serial_number,
                firmware_version="1.0.0",
                device_serial_number=serial_number
            )
            db.add(charge_point)
            db.flush()
            print(f"✓ 创建充电桩: {charge_point_id}")
            
            # 创建默认EVSE
            evse = EVSE(
                charge_point_id=charge_point_id,
                evse_id=1
            )
            db.add(evse)
            db.flush()
            
            # 创建EVSE状态
            evse_status = EVSEStatus(
                evse_id=evse.id,
                charge_point_id=charge_point_id,
                status="Unknown",
                last_seen=datetime.now(timezone.utc)
            )
            db.add(evse_status)
            print(f"✓ 创建EVSE和状态: evse_id=1")
        else:
            print(f"✓ 充电桩已存在: {charge_point_id}")
        
        # 5. 创建定价规则（Tariff.id是自增主键，不需要手动指定）
        tariff = db.query(Tariff).filter(
            Tariff.site_id == site.id,
            Tariff.is_active == True
        ).first()
        if not tariff:
            tariff = Tariff(
                site_id=site.id,
                name="默认定价",
                base_price_per_kwh=2700.0,  # COP/kWh
                service_fee=0,
                valid_from=datetime.now(timezone.utc),
                is_active=True
            )
            db.add(tariff)
            db.flush()
            print(f"✓ 创建定价规则: {tariff.name} (ID: {tariff.id})")
        else:
            print(f"✓ 定价规则已存在 (ID: {tariff.id})")
        
        db.commit()
        print("\n" + "=" * 60)
        print("✓ 测试数据创建完成")
        print("=" * 60)
        print(f"\n测试设备信息:")
        print(f"  SN号: {serial_number}")
        print(f"  MQTT ClientID: {device_type.type_code}&{serial_number}")
        print(f"  MQTT Username: {serial_number}")
        print(f"  MQTT Password: {derive_password('test_master_secret_12345678901234567890', serial_number)}")
        print(f"  Charge Point ID: {charge_point_id}")
        print(f"\nMQTT Topic:")
        print(f"  设备发送: {device_type.type_code}/{serial_number}/user/up")
        print(f"  服务器发送: {device_type.type_code}/{serial_number}/user/down")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 创建测试数据失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()
    
    return True

if __name__ == "__main__":
    success = create_test_data()
    sys.exit(0 if success else 1)
