#!/usr/bin/env python3
#
# 手动创建设备脚本
# 用法: python create_device.py <serial_number> [vendor]
#

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.base import SessionLocal
from app.services.charge_point_service import ChargePointService

def create_device(serial_number: str, vendor: str = None):
    """创建设备"""
    if not serial_number or len(serial_number.strip()) == 0:
        print(f"❌ 错误: 设备序列号不能为空")
        return False
    
    db = SessionLocal()
    try:
        device = ChargePointService.get_or_create_device(
            db=db,
            device_serial_number=serial_number,
            vendor=vendor
        )
        
        if device:
            print(f"✅ 设备创建成功:")
            print(f"   - 序列号: {device.serial_number}")
            print(f"   - 设备类型: {device.device_type.type_code} ({device.device_type.type_name})")
            print(f"   - MQTT客户端ID: {device.mqtt_client_id}")
            print(f"   - MQTT用户名: {device.mqtt_username}")
            print(f"   - 状态: {'激活' if device.is_active else '未激活'}")
            print(f"   - 创建时间: {device.created_at}")
            return True
        else:
            print("❌ 设备创建失败")
            return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python create_device.py <serial_number> [vendor]")
        print("")
        print("参数:")
        print("  serial_number  - 设备序列号")
        print("  vendor        - 设备厂商（可选，用于推断设备类型）")
        print("")
        print("示例:")
        print("  python create_device.py 123456789012345 'Schneider Electric'")
        print("  python create_device.py 123456789012346 'ChargePoint'")
        print("  python create_device.py 123456789012347 'zcf'")
        sys.exit(1)
    
    serial_number = sys.argv[1]
    vendor = sys.argv[2] if len(sys.argv) > 2 else None
    
    success = create_device(serial_number, vendor)
    sys.exit(0 if success else 1)

