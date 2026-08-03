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
import json

# 避免导入 app.database.base，防止事件监听器被注册
# 直接创建引擎，不通过 ORM
from sqlalchemy import create_engine as create_engine_direct

from app.core.auth import get_password_hash


def get_required_bootstrap_password(name: str) -> str:
    """Read a bootstrap password without generating or logging a fallback."""
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"{name} must be set when bootstrapping an empty database")
    if len(value) < 16:
        raise RuntimeError(f"{name} must contain at least 16 characters")
    return value


def get_required_bootstrap_email(name: str) -> str:
    """Read and minimally validate a bootstrap login email."""
    value = (os.getenv(name) or "").strip().lower()
    if "@" not in value or "." not in value.rsplit("@", 1)[-1] or " " in value:
        raise RuntimeError(f"{name} must be a valid email address")
    return value

def create_initial_data():
    """创建初始租户和管理员用户"""
    # 使用数据库 URL 创建直接连接（不使用 ORM session，避免 RLS 检查）
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set for database bootstrap")
    
    # 不导入 app.database.base，避免请求级事件监听器；bootstrap 必须使用
    # 单一事务，任何一步失败都不得留下半套管理员或角色数据。
    engine = create_engine_direct(database_url)
    
    try:
        print("正在创建初始数据...")
        
        with engine.begin() as connection:
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

            # 空数据库才需要 bootstrap 凭据。禁止固定默认值，也不记录明文。
            super_admin_password = get_required_bootstrap_password(
                "CSMS_BOOTSTRAP_SUPER_ADMIN_PASSWORD"
            )
            tenant_admin_password = get_required_bootstrap_password(
                "CSMS_BOOTSTRAP_TENANT_ADMIN_PASSWORD"
            )
            super_admin_email = get_required_bootstrap_email(
                "CSMS_BOOTSTRAP_SUPER_ADMIN_EMAIL"
            )
            tenant_admin_email = get_required_bootstrap_email(
                "CSMS_BOOTSTRAP_TENANT_ADMIN_EMAIL"
            )
            if super_admin_password == tenant_admin_password:
                raise RuntimeError("Bootstrap admin passwords must be different")
            if super_admin_email == tenant_admin_email:
                raise RuntimeError("Bootstrap admin emails must be different")
            
            # 使用 DATABASE_URL 对应的部署账号。生产账号名称由 DB_USER 配置，
            # 不得在初始化逻辑中写死本地开发角色名。
            
            # 创建默认租户
            print("\n1. 创建默认租户...")
            tenant_id = str(uuid.uuid4())
            connection.execute(text("""
                INSERT INTO tenants (id, name, domain, status, subscription_plan, max_charge_points, max_users, settings, created_at, updated_at)
                VALUES (:id, :name, :domain, :status, :plan, :max_cp, :max_users, CAST(:settings AS jsonb), NOW(), NOW())
            """), {
                "id": tenant_id,
                "name": "默认租户",
                "domain": None,
                "status": "active",
                "plan": "enterprise",
                "max_cp": 100,
                "max_users": 1000,
                "settings": "{}"
            })
            print(f"✓ 租户创建成功: 默认租户 (ID: {tenant_id})")
            
            # 创建超级管理员用户
            print("\n2. 创建超级管理员用户...")
            super_admin_id = str(uuid.uuid4())
            super_admin_password_hash = get_password_hash(super_admin_password)
            connection.execute(text("""
                INSERT INTO admin_users (id, username, email, password_hash, full_name, is_active, is_super_admin, created_at, updated_at)
                VALUES (:id, :username, :email, :password_hash, :full_name, :is_active, :is_super_admin, NOW(), NOW())
            """), {
                "id": super_admin_id,
                "username": super_admin_email,
                "email": super_admin_email,
                "password_hash": super_admin_password_hash,
                "full_name": "系统管理员",
                "is_active": True,
                "is_super_admin": True
            })
            print(f"✓ 超级管理员创建成功: {super_admin_email} (ID: {super_admin_id})")
            print(f"  邮箱: {super_admin_email}")
            
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
            print(f"✓ 超级管理员已关联到默认租户")
            
            # 创建租户管理员用户
            print("\n3. 创建租户管理员用户...")
            tenant_admin_id = str(uuid.uuid4())
            tenant_admin_password_hash = get_password_hash(tenant_admin_password)
            connection.execute(text("""
                INSERT INTO admin_users (id, username, email, password_hash, full_name, is_active, is_super_admin, created_at, updated_at)
                VALUES (:id, :username, :email, :password_hash, :full_name, :is_active, :is_super_admin, NOW(), NOW())
            """), {
                "id": tenant_admin_id,
                "username": tenant_admin_email,
                "email": tenant_admin_email,
                "password_hash": tenant_admin_password_hash,
                "full_name": "租户管理员",
                "is_active": True,
                "is_super_admin": False
            })

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
            # 为初始租户管理员绑定与运行时一致的租户管理员角色。
            role_id = str(uuid.uuid4())
            default_permissions = [
                "admin_users.read", "admin_users.write",
                "memberships.read", "memberships.write",
                "roles.read", "roles.write",
                "alerts.read", "alerts.write",
                "alert_rules.read", "alert_rules.write",
                "configs.read", "configs.write",
                "tenant_settings.read", "tenant_settings.write",
                "reports.read", "chargers.read", "chargers.write", "chargers.control",
                "sites.read", "sites.write", "tariffs.read", "tariffs.edit",
                "transactions.read",
            ]
            connection.execute(text("""
                INSERT INTO roles (id, tenant_id, name, permissions, description, scope, created_at, updated_at)
                VALUES (:id, :tenant_id, 'tenant_admin', CAST(:permissions AS jsonb), '租户初始管理员角色', 'tenant', NOW(), NOW())
            """), {
                "id": role_id,
                "tenant_id": tenant_id,
                "permissions": json.dumps(default_permissions),
            })
            membership_role_id = str(uuid.uuid4())
            connection.execute(text("""
                INSERT INTO tenant_membership_roles (id, membership_id, role_id, created_at)
                VALUES (:id, :membership_id, :role_id, NOW())
            """), {
                "id": membership_role_id,
                "membership_id": membership_id,
                "role_id": role_id,
            })
            print(f"✓ 租户管理员创建成功: {tenant_admin_email} (ID: {tenant_admin_id})")
            print(f"  邮箱: {tenant_admin_email}")
            print(f"  关联租户: 默认租户")
            
            print("\n" + "="*50)
            print("✓ 初始数据创建完成！")
            print("="*50)
            print("\n默认账号信息：")
            print("-" * 50)
            print("超级管理员:")
            print(f"  用户名: {super_admin_email}")
            print(f"  邮箱: {super_admin_email}")
            print(f"  权限: 超级管理员（可访问所有租户）")
            print(f"  主租户: 默认租户")
            print("-" * 50)
            print("租户管理员:")
            print(f"  用户名: {tenant_admin_email}")
            print(f"  邮箱: {tenant_admin_email}")
            print(f"  权限: 租户管理员（仅可访问默认租户）")
            print(f"  租户: 默认租户")
            print("-" * 50)
            print("\nBootstrap 密码已从环境变量读取，明文不会写入日志。")
            
    except Exception as e:
        print(f"\n❌ 创建初始数据失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    create_initial_data()
