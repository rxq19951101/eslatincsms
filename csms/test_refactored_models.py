#!/usr/bin/env python3
#
# 测试重构后的数据库模型
# 验证表结构是否正确创建
#

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.base import init_db, check_db_health, engine
from app.database.models import Base
from sqlalchemy import inspect

def test_models():
    """测试数据库模型"""
    print("=" * 60)
    print("测试重构后的数据库模型")
    print("=" * 60)
    
    # 检查数据库连接
    if not check_db_health():
        print("❌ 数据库连接失败，请检查数据库配置")
        return False
    
    print("✓ 数据库连接成功")
    
    # 初始化数据库
    try:
        init_db()
        print("✓ 数据库表初始化成功")
    except Exception as e:
        print(f"❌ 数据库表初始化失败: {e}")
        return False
    
    # 检查所有表是否创建
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    expected_tables = [
        "sites",
        "charge_points",
        "evses",
        "evse_status",
        "device_types",
        "devices",
        "charging_sessions",
        "meter_values",
        "orders",
        "tariffs",
        "pricing_snapshots",
        "invoices",
        "payments",
        "device_events",
        "device_configs",
        "charge_point_configs",
        "support_messages",
    ]
    
    print("\n检查表结构:")
    print("-" * 60)
    
    missing_tables = []
    for table in expected_tables:
        if table in tables:
            print(f"✓ {table}")
        else:
            print(f"❌ {table} - 表不存在")
            missing_tables.append(table)
    
    if missing_tables:
        print(f"\n❌ 缺少 {len(missing_tables)} 个表")
        return False
    
    print(f"\n✓ 所有 {len(expected_tables)} 个表都已创建")
    
    # 检查表结构
    print("\n检查关键表结构:")
    print("-" * 60)
    
    # 检查sites表
    sites_columns = [col['name'] for col in inspector.get_columns('sites')]
    required_sites_columns = ['id', 'name', 'address', 'latitude', 'longitude']
    for col in required_sites_columns:
        if col in sites_columns:
            print(f"✓ sites.{col}")
        else:
            print(f"❌ sites.{col} - 列不存在")
    
    # 检查charge_points表
    cp_columns = [col['name'] for col in inspector.get_columns('charge_points')]
    required_cp_columns = ['id', 'site_id', 'vendor', 'model', 'device_serial_number']
    for col in required_cp_columns:
        if col in cp_columns:
            print(f"✓ charge_points.{col}")
        else:
            print(f"❌ charge_points.{col} - 列不存在")
    
    # 检查charging_sessions表
    cs_columns = [col['name'] for col in inspector.get_columns('charging_sessions')]
    required_cs_columns = ['id', 'evse_id', 'charge_point_id', 'transaction_id', 'id_tag', 'start_time']
    for col in required_cs_columns:
        if col in cs_columns:
            print(f"✓ charging_sessions.{col}")
        else:
            print(f"❌ charging_sessions.{col} - 列不存在")
    
    # 检查device_types表（密码字段）
    dt_columns = [col['name'] for col in inspector.get_columns('device_types')]
    if 'master_secret_encrypted' in dt_columns:
        print("✓ device_types.master_secret_encrypted (新密码存储方式)")
    else:
        print("❌ device_types.master_secret_encrypted - 列不存在")
    
    if 'password' in dt_columns:
        print("⚠ device_types.password - 旧字段仍存在（需要迁移）")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = test_models()
    sys.exit(0 if success else 1)
