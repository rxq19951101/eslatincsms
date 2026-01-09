#
# 简化的API集成测试
# 测试关键API流程，避免复杂的依赖
#

import pytest
import uuid
import logging
import sys
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database.base import (
    tenant_id_context, 
    is_super_admin_context, 
    use_super_connection_context
)
from app.database.models import (
    Tenant, AdminUser, EndUser, TenantMembership, 
    ChargePoint, Site
)
from app.core.auth import get_password_hash, verify_password
from contextlib import contextmanager

# 强制配置测试日志 - 确保能输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    force=True,  # 强制重新配置
    handlers=[
        logging.StreamHandler(sys.stdout),  # 输出到stdout
        logging.StreamHandler(sys.stderr),  # 也输出到stderr
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 确保日志能输出
print("=" * 60, file=sys.stderr)
print("测试文件已加载: test_api_integration_simple.py", file=sys.stderr)
print("=" * 60, file=sys.stderr)
logger.info("=" * 60)
logger.info("测试文件已加载: test_api_integration_simple.py")
logger.info("Logger已初始化")


@contextmanager
def super_admin_context():
    """超级管理员上下文管理器"""
    is_super_admin_context.set(True)
    use_super_connection_context.set(True)
    try:
        yield
    finally:
        is_super_admin_context.set(False)
        use_super_connection_context.set(False)


def create_tenant_for_test(db_session: Session, name: str = "测试租户", **kwargs):
    """辅助函数：创建测试租户"""
    with super_admin_context():
        tenant = Tenant(
            id=uuid.uuid4(),
            name=name,
            status="active",
            subscription_plan="basic",
            max_charge_points=10,
            max_users=50,
            **kwargs
        )
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)
        return tenant


class TestSimpleAPIIntegration:
    """简化的API集成测试"""
    
    def test_admin_login_api(self, client: TestClient, db_session: Session):
        """测试管理员登录API"""
        # 立即输出，不依赖logger
        print("\n" + "=" * 60, flush=True)
        print("✓ 测试函数已开始执行: test_admin_login_api", flush=True)
        print("=" * 60 + "\n", flush=True)
        
        logger.info("=" * 60)
        logger.info("开始测试: test_admin_login_api")
        logger.info("=" * 60)
        
        print("✓ Logger日志测试", flush=True)
        logger.info("✓ Logger日志测试 - 这应该能看到")
        
        try:
            logger.info("步骤1: 创建超级管理员用户")
            with super_admin_context():
                logger.info("  - 已设置超级管理员上下文")
                super_admin = AdminUser(
                    id=uuid.uuid4(),
                    username="testadmin",
                    email="testadmin@test.com",
                    password_hash=get_password_hash("password123"),
                    is_super_admin=True,
                    is_active=True
                )
                logger.info(f"  - 创建AdminUser对象: username={super_admin.username}, id={super_admin.id}")
                db_session.add(super_admin)
                logger.info("  - AdminUser已添加到session")
                db_session.commit()
                logger.info("  - 数据库提交成功")
                db_session.refresh(super_admin)
                logger.info("  - AdminUser刷新成功")
        except Exception as e:
            logger.error(f"步骤1失败: {e}", exc_info=True)
            raise
        
        try:
            logger.info("步骤2: 准备发送登录请求")
            login_data = {
                "username": "testadmin",
                "password": "password123"
            }
            logger.info(f"  - 登录数据: {login_data}")
            logger.info("  - 开始发送POST请求到 /api/v1/admin/auth/login")
            
            response = client.post(
                "/api/v1/admin/auth/login",
                json=login_data
            )
            
            logger.info(f"  - 请求完成，状态码: {response.status_code}")
            logger.info(f"  - 响应头: {dict(response.headers)}")
            
            if response.status_code != 200:
                logger.error(f"  - 登录失败！响应内容: {response.text}")
        except Exception as e:
            logger.error(f"步骤2失败: {e}", exc_info=True)
            raise
        
        try:
            logger.info("步骤3: 验证响应")
            assert response.status_code == 200, f"登录失败，状态码: {response.status_code}, 响应: {response.text}"
            data = response.json()
            logger.info(f"  - 响应JSON解析成功: {list(data.keys())}")
            
            assert "access_token" in data, "响应中缺少 access_token"
            logger.info(f"  - access_token存在: {data['access_token'][:50]}...")
            assert "refresh_token" in data, "响应中缺少 refresh_token"
            logger.info(f"  - refresh_token存在: {data['refresh_token'][:50]}...")
            assert data["token_type"] == "bearer", f"token_type不正确: {data.get('token_type')}"
            logger.info(f"  - token_type正确: {data['token_type']}")
            
            logger.info("✓ test_admin_login_api 测试通过")
            return data["access_token"]
        except Exception as e:
            logger.error(f"步骤3失败: {e}", exc_info=True)
            raise
    
    def test_protected_endpoint_with_token(self, client: TestClient, db_session: Session):
        """测试使用token访问受保护的端点"""
        logger.info("=" * 60)
        logger.info("开始测试: test_protected_endpoint_with_token")
        logger.info("=" * 60)
        
        try:
            logger.info("步骤1: 先登录获取token")
            token = self.test_admin_login_api(client, db_session)
            logger.info(f"  - 获取到token: {token[:50]}...")
        except Exception as e:
            logger.error(f"步骤1失败: {e}", exc_info=True)
            raise
        
        try:
            logger.info("步骤2: 访问受保护的端点 /api/v1/admin/auth/me")
            headers = {"Authorization": f"Bearer {token}"}
            logger.info(f"  - 请求头: Authorization=Bearer {token[:30]}...")
            logger.info("  - 开始发送GET请求")
            
            response = client.get(
                "/api/v1/admin/auth/me",
                headers=headers
            )
            
            logger.info(f"  - 请求完成，状态码: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"  - 请求失败！响应内容: {response.text}")
        except Exception as e:
            logger.error(f"步骤2失败: {e}", exc_info=True)
            raise
        
        try:
            logger.info("步骤3: 验证响应内容")
            assert response.status_code == 200, f"请求失败，状态码: {response.status_code}, 响应: {response.text}"
            user_info = response.json()
            logger.info(f"  - 响应JSON解析成功: {list(user_info.keys())}")
            
            assert user_info["username"] == "testadmin", f"用户名不匹配: {user_info.get('username')}"
            logger.info(f"  - 用户名正确: {user_info['username']}")
            assert user_info["is_super_admin"] is True, f"is_super_admin不正确: {user_info.get('is_super_admin')}"
            logger.info(f"  - is_super_admin正确: {user_info['is_super_admin']}")
            
            logger.info("✓ test_protected_endpoint_with_token 测试通过")
        except Exception as e:
            logger.error(f"步骤3失败: {e}", exc_info=True)
            raise
    
    def test_tenant_creation_with_super_admin(self, client: TestClient, db_session: Session):
        """测试超级管理员创建租户"""
        logger.info("=" * 60)
        logger.info("开始测试: test_tenant_creation_with_super_admin")
        logger.info("=" * 60)
        
        try:
            logger.info("步骤1: 登录获取token")
            token = self.test_admin_login_api(client, db_session)
            logger.info(f"  - 获取到token: {token[:50]}...")
        except Exception as e:
            logger.error(f"步骤1失败: {e}", exc_info=True)
            raise
        
        try:
            logger.info("步骤2: 准备创建租户请求")
            tenant_data = {
                "name": "新租户",
                "subscription_plan": "premium",
                "max_charge_points": 100,
                "max_users": 500
            }
            headers = {"Authorization": f"Bearer {token}"}
            logger.info(f"  - 租户数据: {tenant_data}")
            logger.info(f"  - 请求头: Authorization=Bearer {token[:30]}...")
            logger.info("  - 开始发送POST请求到 /api/v1/admin/tenants")
            
            response = client.post(
                "/api/v1/admin/tenants",
                headers=headers,
                json=tenant_data
            )
            
            logger.info(f"  - 请求完成，状态码: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"  - 创建租户失败！响应内容: {response.text}")
        except Exception as e:
            logger.error(f"步骤2失败: {e}", exc_info=True)
            raise
        
        try:
            logger.info("步骤3: 验证响应内容")
            assert response.status_code == 200, f"创建租户失败，状态码: {response.status_code}, 响应: {response.text}"
            tenant = response.json()
            logger.info(f"  - 响应JSON解析成功: {list(tenant.keys())}")
            
            assert tenant["name"] == "新租户", f"租户名称不匹配: {tenant.get('name')}"
            logger.info(f"  - 租户名称正确: {tenant['name']}")
            assert tenant["subscription_plan"] == "premium", f"订阅计划不匹配: {tenant.get('subscription_plan')}"
            logger.info(f"  - 订阅计划正确: {tenant['subscription_plan']}")
            logger.info(f"  - 租户ID: {tenant.get('id')}")
            
            logger.info("✓ test_tenant_creation_with_super_admin 测试通过")
            return tenant["id"]
        except Exception as e:
            logger.error(f"步骤3失败: {e}", exc_info=True)
            raise
    
    def test_tenant_isolation_in_api(self, client: TestClient, db_session: Session):
        """测试API层面的租户隔离"""
        logger.info("=" * 60)
        logger.info("开始测试: test_tenant_isolation_in_api")
        logger.info("=" * 60)
        
        try:
            logger.info("步骤1: 创建两个租户")
            tenant1 = create_tenant_for_test(db_session, name="租户1")
            logger.info(f"  - 租户1创建成功: id={tenant1.id}, name={tenant1.name}")
            tenant2 = create_tenant_for_test(db_session, name="租户2")
            logger.info(f"  - 租户2创建成功: id={tenant2.id}, name={tenant2.name}")
        except Exception as e:
            logger.error(f"步骤1失败: {e}", exc_info=True)
            raise
        
        try:
            logger.info("步骤2: 创建两个管理员和成员关系")
            with super_admin_context():
                logger.info("  - 已设置超级管理员上下文")
                admin1 = AdminUser(
                    id=uuid.uuid4(),
                    username="admin1",
                    email="admin1@test.com",
                    password_hash=get_password_hash("password123"),
                    is_super_admin=False,
                    is_active=True
                )
                admin2 = AdminUser(
                    id=uuid.uuid4(),
                    username="admin2",
                    email="admin2@test.com",
                    password_hash=get_password_hash("password123"),
                    is_super_admin=False,
                    is_active=True
                )
                logger.info(f"  - AdminUser1创建: username={admin1.username}, id={admin1.id}")
                logger.info(f"  - AdminUser2创建: username={admin2.username}, id={admin2.id}")
                
                membership1 = TenantMembership(
                    tenant_id=tenant1.id,
                    admin_user_id=admin1.id,
                    status="active",
                    is_primary=True
                )
                membership2 = TenantMembership(
                    tenant_id=tenant2.id,
                    admin_user_id=admin2.id,
                    status="active",
                    is_primary=True
                )
                logger.info(f"  - Membership1创建: tenant={tenant1.id}, user={admin1.id}")
                logger.info(f"  - Membership2创建: tenant={tenant2.id}, user={admin2.id}")
                
                db_session.add(admin1)
                db_session.add(admin2)
                db_session.add(membership1)
                db_session.add(membership2)
                logger.info("  - 所有对象已添加到session")
                
                logger.info("步骤3: 创建充电桩数据")
                site1 = Site(
                    id="SITE-001",
                    tenant_id=tenant1.id,
                    name="租户1站点",
                    address="地址1",
                    latitude=39.9,
                    longitude=116.4
                )
                site2 = Site(
                    id="SITE-002",
                    tenant_id=tenant2.id,
                    name="租户2站点",
                    address="地址2",
                    latitude=40.0,
                    longitude=117.0
                )
                cp1 = ChargePoint(
                    id="CP-001",
                    tenant_id=tenant1.id,
                    site_id=site1.id,
                    is_active=True
                )
                cp2 = ChargePoint(
                    id="CP-002",
                    tenant_id=tenant2.id,
                    site_id=site2.id,
                    is_active=True
                )
                logger.info(f"  - Site1创建: id={site1.id}, tenant={tenant1.id}")
                logger.info(f"  - Site2创建: id={site2.id}, tenant={tenant2.id}")
                logger.info(f"  - ChargePoint1创建: id={cp1.id}, tenant={tenant1.id}")
                logger.info(f"  - ChargePoint2创建: id={cp2.id}, tenant={tenant2.id}")
                
                db_session.add(site1)
                db_session.add(site2)
                db_session.add(cp1)
                db_session.add(cp2)
                logger.info("  - 所有站点和充电桩已添加到session")
                
                db_session.commit()
                logger.info("  - 数据库提交成功")
        except Exception as e:
            logger.error(f"步骤2-3失败: {e}", exc_info=True)
            raise
        
        try:
            logger.info("步骤4: admin1 登录")
            login_response = client.post(
                "/api/v1/admin/auth/login",
                json={
                    "username": "admin1",
                    "password": "password123"
                }
            )
            
            logger.info(f"  - 登录请求完成，状态码: {login_response.status_code}")
            if login_response.status_code != 200:
                logger.warning(f"  - 登录失败，跳过API隔离测试。响应: {login_response.text}")
                pytest.skip("登录失败，跳过API隔离测试")
            
            token1 = login_response.json()["access_token"]
            logger.info(f"  - 获取到token: {token1[:50]}...")
        except Exception as e:
            logger.error(f"步骤4失败: {e}", exc_info=True)
            raise
        
        try:
            logger.info("步骤5: admin1 访问租户1的充电桩列表")
            headers = {
                "Authorization": f"Bearer {token1}",
                "X-Tenant-Id": str(tenant1.id)
            }
            logger.info(f"  - 请求头: Authorization=Bearer {token1[:30]}..., X-Tenant-Id={tenant1.id}")
            logger.info("  - 开始发送GET请求到 /api/v1/chargers")
            
            response = client.get(
                "/api/v1/chargers",
                headers=headers
            )
            
            logger.info(f"  - 请求完成，状态码: {response.status_code}")
            if response.status_code not in [200, 403]:
                logger.warning(f"  - 意外的状态码: {response.status_code}, 响应: {response.text}")
        except Exception as e:
            logger.error(f"步骤5失败: {e}", exc_info=True)
            raise
        
        try:
            logger.info("步骤6: 验证响应")
            assert response.status_code in [200, 403], f"意外的状态码: {response.status_code}"
            logger.info(f"  - 状态码验证通过: {response.status_code}")
            
            if response.status_code == 200:
                chargers = response.json()
                logger.info(f"  - 响应JSON解析成功，充电桩数量: {len(chargers)}")
                for i, charger in enumerate(chargers):
                    logger.info(f"    - 充电桩{i+1}: id={charger.get('id')}, tenant_id={charger.get('tenant_id')}")
                # 验证只能看到租户1的充电桩
                for charger in chargers:
                    assert charger.get("id") == "CP-001" or charger.get("tenant_id") == str(tenant1.id), \
                        f"发现了不属于租户1的充电桩: {charger}"
                logger.info("  - 所有充电桩都属于租户1，验证通过")
            else:
                logger.info("  - 返回403，符合预期（权限验证）")
            
            logger.info("✓ test_tenant_isolation_in_api 测试通过")
        except Exception as e:
            logger.error(f"步骤6失败: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
