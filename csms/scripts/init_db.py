#!/usr/bin/env python3
#
# 数据库初始化脚本
# 创建所有数据库表
#

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入所有模型以确保它们被注册到 Base.metadata
from app.database.models import (
    Charger, Transaction, MeterValue, 
    ChargerConfiguration, Order, SupportMessage, 
    OCPPErrorLog, HeartbeatHistory, StatusHistory
)
from app.database import init_db, check_db_health, engine, Base
from app.core.config import get_settings

def main():
    """初始化数据库"""
    settings = get_settings()
    
    print(f"正在连接数据库: {settings.database_url.split('@')[1] if '@' in settings.database_url else settings.database_url}")
    
    # 检查数据库连接
    if not check_db_health():
        print("✗ 数据库连接失败，请检查数据库配置")
        sys.exit(1)
    
    print("✓ 数据库连接成功")
    
    # 显示要创建的表
    print("\n将要创建以下表：")
    for table_name in sorted(Base.metadata.tables.keys()):
        print(f"  - {table_name}")
    
    # 创建所有表
    print("\n正在创建数据库表...")
    try:
        init_db()
        print("✓ 数据库表创建完成")
        
        # 验证表是否创建成功
        print("\n验证表创建情况...")
        from sqlalchemy import inspect
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        for table_name in sorted(Base.metadata.tables.keys()):
            if table_name in existing_tables:
                print(f"  ✓ {table_name}")
            else:
                print(f"  ✗ {table_name} (创建失败)")
        
        print("\n✓ 数据库初始化完成")
    except Exception as e:
        print(f"✗ 数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

