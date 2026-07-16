#!/usr/bin/env python3
"""
创建测试用户脚本
"""

import sys
sys.path.insert(0, '/app')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import EndUser, Tenant
from app.core.auth import hash_password
from uuid import UUID
import os
from datetime import datetime, timezone

# 数据库连接
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ocpp_user:ocpp_password@localhost:5432/ocpp_db"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def create_test_user():
    db = SessionLocal()
    
    try:
        # 获取第一个租户
        tenant = db.query(Tenant).first()
        if not tenant:
            print("❌ 没有找到租户，请先创建租户")
            return
        
        print(f"✅ 找到租户: {tenant.name} (ID: {tenant.id})")
        
        # 检查用户是否已存在
        existing_user = db.query(EndUser).filter(
            EndUser.email == "test@eslatin.com.co"
        ).first()
        
        if existing_user:
            print(f"✅ 测试用户已存在: {existing_user.email}")
            print(f"   User ID: {existing_user.id}")
            print(f"   Full Name: {existing_user.full_name}")
            print(f"   Phone: {existing_user.phone}")
            return
        
        # 创建测试用户
        test_user = EndUser(
            tenant_id=tenant.id,
            phone="+1234567890",
            email="test@eslatin.com.co",
            full_name="Test User",
            id_tag="TEST_USER_001",
            password_hash=hash_password("Test123456"),  # 密码: Test123456
            email_verified=True,  # 直接设置为已验证
            status="active",
            balance=100.00,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        
        print("\n🎉 测试用户创建成功！")
        print("=" * 50)
        print(f"Email: test@eslatin.com.co")
        print(f"Password: Test123456")
        print(f"User ID: {test_user.id}")
        print(f"Tenant ID: {tenant.id}")
        print(f"Full Name: {test_user.full_name}")
        print(f"Balance: ${test_user.balance}")
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ 创建用户失败: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_test_user()
