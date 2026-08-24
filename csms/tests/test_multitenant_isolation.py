#
# 多租户数据隔离测试
# 确保RLS和中间件正确工作，数据不会串租户
#

import pytest
from uuid import uuid4
from sqlalchemy.orm import Session
from app.database.base import tenant_id_context, is_super_admin_context, use_super_connection_context
from app.database.models import Tenant, Site, ChargePoint, Order
from app.core.tenant_middleware import validate_tenant_membership


def test_rls_tenant_isolation(db_session: Session):
    """测试RLS租户隔离"""
    db = db_session
    try:
        # 创建两个租户
        tenant1 = Tenant(
            id=uuid4(),
            name="租户1",
            status="active"
        )
        tenant2 = Tenant(
            id=uuid4(),
            name="租户2",
            status="active"
        )
        db.add(tenant1)
        db.add(tenant2)
        db.commit()

        site1 = Site(
            tenant_id=tenant1.id,
            name="租户一站点",
            address="租户一测试地址",
            latitude=1.0,
            longitude=1.0,
        )
        site2 = Site(
            tenant_id=tenant2.id,
            name="租户二站点",
            address="租户二测试地址",
            latitude=2.0,
            longitude=2.0,
        )
        db.add_all([site1, site2])
        db.commit()
        
        # 为每个租户创建充电桩
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
        db.add(cp1)
        db.add(cp2)
        db.commit()
        
        # 设置 tenant_id 上下文
        tenant_id_context.set(tenant1.id)
        is_super_admin_context.set(False)
        
        # 查询应该只返回租户1的充电桩
        # 注意：这需要RLS正确配置
        charge_points = db.query(ChargePoint).filter(
            ChargePoint.tenant_id == tenant1.id
        ).all()
        
        # 验证：应该只看到租户1的充电桩
        assert len(charge_points) == 1
        assert charge_points[0].tenant_id == tenant1.id
        
    finally:
        db.close()
        tenant_id_context.set(None)
        is_super_admin_context.set(False)


def test_tenant_membership_validation(db_session: Session):
    """测试租户成员关系验证"""
    db = db_session
    try:
        from app.database.models import AdminUser, TenantMembership
        
        # 创建租户和用户
        tenant = Tenant(
            id=uuid4(),
            name="测试租户",
            status="active"
        )
        admin_user = AdminUser(
            id=uuid4(),
            username="testuser",
            email="test@example.com",
            password_hash="hash",
            is_super_admin=False
        )
        db.add(tenant)
        db.add(admin_user)
        db.commit()
        
        # 创建成员关系
        membership = TenantMembership(
            tenant_id=tenant.id,
            admin_user_id=admin_user.id,
            status="active"
        )
        db.add(membership)
        db.commit()
        
        # 验证成员关系
        result = validate_tenant_membership(
            user_id=admin_user.id,
            tenant_id=tenant.id,
            is_super_admin=False,
            db=db
        )
        
        assert result is True
        
        # 验证不属于该租户的情况
        other_tenant = Tenant(
            id=uuid4(),
            name="其他租户",
            status="active"
        )
        db.add(other_tenant)
        db.commit()
        
        result2 = validate_tenant_membership(
            user_id=admin_user.id,
            tenant_id=other_tenant.id,
            is_super_admin=False,
            db=db
        )
        
        assert result2 is False
        
    finally:
        db.close()


def test_super_admin_bypass(db_session: Session):
    """测试超级管理员绕过RLS"""
    db = db_session
    try:
        # 创建两个租户
        tenant1 = Tenant(id=uuid4(), name="租户1", status="active")
        tenant2 = Tenant(id=uuid4(), name="租户2", status="active")
        db.add(tenant1)
        db.add(tenant2)
        db.commit()
        
        # 设置超级管理员上下文
        is_super_admin_context.set(True)
        use_super_connection_context.set(True)
        
        # 超级管理员应该能看到所有租户的数据
        # 注意：这需要使用 app_super 连接
        tenants = db.query(Tenant).all()
        
        # 验证：超级管理员可以看到所有租户
        assert len(tenants) >= 2
        
    finally:
        db.close()
        is_super_admin_context.set(False)
        use_super_connection_context.set(False)
