#!/usr/bin/env python3
#
# 创建初始数据脚本
# 创建默认租户和管理员用户
# 使用原始 SQL 绕过 RLS 检查
#

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
import uuid

# 避免导入 app.database.base，防止事件监听器被注册
# 直接创建引擎，不通过 ORM
from sqlalchemy import create_engine as create_engine_direct

# 导入密码哈希函数
from passlib.context import CryptContext
try:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except:
    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)

def create_initial_data():
    """创建初始租户和管理员用户"""
    # 使用数据库 URL 创建直接连接（不使用 ORM session，避免 RLS 检查）
    database_url = os.getenv("DATABASE_URL", "postgresql://ocpp_user:ocpp_password@db:5432/ocpp")
    
    # 创建引擎（使用 autocommit 模式，避免事务事件）
    # 关键：不导入 app.database.base，避免事件监听器
    engine = create_engine_direct(database_url, isolation_level="AUTOCOMMIT")
    
    try:
        print("正在创建初始数据...")
        
        with engine.connect() as connection:
            # 检查是否已有租户和管理员用户（使用原始 SQL）
            tenant_result = connection.execute(text("SELECT COUNT(*) FROM tenants"))
            tenant_count = tenant_result.scalar()
            admin_result = connection.execute(text("SELECT COUNT(*) FROM admin_users"))
            admin_count = admin_result.scalar()
            
            if tenant_count > 0 or admin_count > 0:
                print(f"⚠️  检测到已有数据:")
                if tenant_count > 0:
                    print(f"   - 租户数量: {tenant_count}")
                if admin_count > 0:
                    print(f"   - 管理员用户数量: {admin_count}")
                print(f"\n跳过初始数据创建（如需重新创建，请先清理数据库）")
                return
            
            # 先设置角色为 postgres superuser（ocpp_user 应该是数据库所有者，有权限）
            # 或者直接使用 ocpp_user，它在创建表时应该有权限
            connection.execute(text("SET LOCAL role = ocpp_user"))
            
            # 创建默认租户
            print("\n1. 创建默认租户...")
            tenant_id = str(uuid.uuid4())
            connection.execute(text("""
                INSERT INTO tenants (id, name, domain, status, subscription_plan, max_charge_points, max_users, settings, created_at, updated_at)
                VALUES (:id, :name, :domain, :status, :plan, :max_cp, :max_users, %(settings)s::jsonb, NOW(), NOW())
            """), {
                "id": tenant_id,
                "name": "默认租户",
                "domain": None,
                "status": "active",
                "plan": "premium",
                "max_cp": 100,
                "max_users": 1000,
                "settings": "{}"
            })
            connection.commit()
            print(f"✓ 租户创建成功: 默认租户 (ID: {tenant_id})")
            
            # 创建超级管理员用户
            print("\n2. 创建超级管理员用户...")
            super_admin_id = str(uuid.uuid4())
            super_admin_password_hash = get_password_hash("test123")
            connection.execute(text("""
                INSERT INTO admin_users (id, username, email, password_hash, full_name, is_active, is_super_admin, created_at, updated_at)
                VALUES (:id, :username, :email, :password_hash, :full_name, :is_active, :is_super_admin, NOW(), NOW())
            """), {
                "id": super_admin_id,
                "username": "admin",
                "email": "admin@example.com",
                "password_hash": super_admin_password_hash,
                "full_name": "系统管理员",
                "is_active": True,
                "is_super_admin": True
            })
            connection.commit()
            print(f"✓ 超级管理员创建成功: admin (ID: {super_admin_id})")
            print(f"  邮箱: admin@example.com")
            print(f"  默认密码: admin123")
            print(f"  ⚠️  请在生产环境中立即修改默认密码！")
            
            # 为超级管理员创建租户成员关系（关联到默认租户）
            print("\n2.1 创建超级管理员的租户关联...")
            super_admin_membership_id = str(uuid.uuid4())
            connection.execute(text("""
                INSERT INTO tenant_memberships (id, tenant_id, admin_user_id, is_primary, status, created_at, updated_at)
                VALUES (:id, :tenant_id, :admin_user_id, :is_primary, :status, NOW(), NOW())
            """), {
                "id": super_admin_membership_id,
                "tenant_id": tenant_id,
                "admin_user_id": super_admin_id,
                "is_primary": True,
                "status": "active"
            })
            connection.commit()
            print(f"✓ 超级管理员已关联到默认租户")
            
            # 创建租户管理员用户
            print("\n3. 创建租户管理员用户...")
            tenant_admin_id = str(uuid.uuid4())
            tenant_admin_password_hash = get_password_hash("admin123")
            connection.execute(text("""
                INSERT INTO admin_users (id, username, email, password_hash, full_name, is_active, is_super_admin, created_at, updated_at)
                VALUES (:id, :username, :email, :password_hash, :full_name, :is_active, :is_super_admin, NOW(), NOW())
            """), {
                "id": tenant_admin_id,
                "username": "tenant_admin",
                "email": "tenant_admin@example.com",
                "password_hash": tenant_admin_password_hash,
                "full_name": "租户管理员",
                "is_active": True,
                "is_super_admin": False
            })
            connection.commit()
            
            # 创建租户成员关系
            membership_id = str(uuid.uuid4())
            connection.execute(text("""
                INSERT INTO tenant_memberships (id, tenant_id, admin_user_id, is_primary, status, created_at, updated_at)
                VALUES (:id, :tenant_id, :admin_user_id, :is_primary, :status, NOW(), NOW())
            """), {
                "id": membership_id,
                "tenant_id": tenant_id,
                "admin_user_id": tenant_admin_id,
                "is_primary": True,
                "status": "active"
            })
            connection.commit()
            print(f"✓ 租户管理员创建成功: tenant_admin (ID: {tenant_admin_id})")
            print(f"  邮箱: tenant_admin@example.com")
            print(f"  默认密码: admin123")
            print(f"  关联租户: 默认租户")
            
            print("\n" + "="*50)
            print("✓ 初始数据创建完成！")
            print("="*50)
            print("\n默认账号信息：")
            print("-" * 50)
            print("超级管理员:")
            print(f"  用户名: admin")
            print(f"  密码: test123")
            print(f"  邮箱: admin@example.com")
            print(f"  权限: 超级管理员（可访问所有租户）")
            print(f"  主租户: 默认租户")
            print("-" * 50)
            print("租户管理员:")
            print(f"  用户名: tenant_admin")
            print(f"  密码: admin123")
            print(f"  邮箱: tenant_admin@example.com")
            print(f"  权限: 租户管理员（仅可访问默认租户）")
            print(f"  租户: 默认租户")
            print("-" * 50)
            print("\n⚠️  重要提示：")
            print("  1. 请在生产环境中立即修改所有默认密码！")
            print("  2. 建议删除或禁用测试账号")
            print("  3. 确保使用强密码策略")
            
    except Exception as e:
        print(f"\n❌ 创建初始数据失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    create_initial_data()
