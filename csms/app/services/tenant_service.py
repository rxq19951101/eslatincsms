#
# 租户服务层
# 提供租户的 CRUD 操作和资源限制检查
#

from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.models import AdminUser, Tenant, ChargePoint, TenantMembership, TenantMembershipRole
from app.core.auth import get_password_hash
from app.services.role_service import RoleService
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

VALID_SUBSCRIPTION_PLANS = {"free", "pro", "enterprise"}


class TenantService:
    """租户服务"""

    @staticmethod
    def provision_tenant(
        db: Session,
        *,
        tenant_data: dict,
        admin_data: dict,
    ) -> tuple[Tenant, AdminUser, TenantMembership]:
        """Create a tenant, its first admin, role and membership in one transaction."""
        tenant = Tenant(**tenant_data)
        admin = AdminUser(
            username=admin_data["username"],
            email=admin_data["email"],
            password_hash=get_password_hash(admin_data["password"]),
            full_name=admin_data.get("full_name"),
            is_active=True,
            is_super_admin=False,
        )
        try:
            db.add_all([tenant, admin])
            db.flush()
            membership = TenantMembership(
                tenant_id=tenant.id,
                admin_user_id=admin.id,
                is_primary=True,
                status="active",
            )
            db.add(membership)
            db.flush()
            role = RoleService.ensure_default_tenant_admin_role(db, tenant.id)
            db.add(TenantMembershipRole(membership_id=membership.id, role_id=role.id))
            db.commit()
            db.refresh(tenant)
            db.refresh(admin)
            db.refresh(membership)
            return tenant, admin, membership
        except Exception:
            db.rollback()
            raise
    
    @staticmethod
    def create_tenant(
        db: Session,
        name: str,
        domain: Optional[str] = None,
        subscription_plan: str = "free",
        max_charge_points: int = 10,
        max_users: int = 100,
        settings: Optional[dict] = None
    ) -> Tenant:
        """创建租户"""
        if subscription_plan not in VALID_SUBSCRIPTION_PLANS:
            raise ValueError("subscription_plan must be one of: free, pro, enterprise")
        # 检查域名是否已存在
        if domain:
            existing = db.query(Tenant).filter(Tenant.domain == domain).first()
            if existing:
                raise ValueError("Domain already exists")
        
        tenant = Tenant(
            name=name,
            domain=domain,
            subscription_plan=subscription_plan,
            max_charge_points=max_charge_points,
            max_users=max_users,
            settings=settings or {}
        )
        
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        
        logger.info(f"Created tenant: {name} ({tenant.id})")
        return tenant
    
    @staticmethod
    def get_tenant_by_id(db: Session, tenant_id: UUID) -> Optional[Tenant]:
        """根据ID获取租户"""
        return db.query(Tenant).filter(Tenant.id == tenant_id).first()
    
    @staticmethod
    def get_tenant_by_domain(db: Session, domain: str) -> Optional[Tenant]:
        """根据域名获取租户"""
        return db.query(Tenant).filter(Tenant.domain == domain).first()
    
    @staticmethod
    def list_tenants(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None
    ) -> List[Tenant]:
        """获取租户列表"""
        query = db.query(Tenant)
        
        if status:
            query = query.filter(Tenant.status == status)
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def update_tenant(
        db: Session,
        tenant_id: UUID,
        name: Optional[str] = None,
        domain: Optional[str] = None,
        status: Optional[str] = None,
        subscription_plan: Optional[str] = None,
        max_charge_points: Optional[int] = None,
        max_users: Optional[int] = None,
        settings: Optional[dict] = None
    ) -> Optional[Tenant]:
        """更新租户"""
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return None
        
        if name is not None:
            tenant.name = name
        if domain is not None:
            # 检查域名是否已被其他租户使用
            existing = db.query(Tenant).filter(
                Tenant.domain == domain,
                Tenant.id != tenant_id
            ).first()
            if existing:
                raise ValueError("Domain already exists")
            tenant.domain = domain
        if status is not None:
            tenant.status = status
        if subscription_plan is not None:
            if subscription_plan not in VALID_SUBSCRIPTION_PLANS:
                raise ValueError("subscription_plan must be one of: free, pro, enterprise")
            tenant.subscription_plan = subscription_plan
        if max_charge_points is not None:
            tenant.max_charge_points = max_charge_points
        if max_users is not None:
            tenant.max_users = max_users
        if settings is not None:
            tenant.settings = settings
        
        db.commit()
        db.refresh(tenant)
        
        logger.info(f"Updated tenant: {tenant_id}")
        return tenant
    
    @staticmethod
    def delete_tenant(db: Session, tenant_id: UUID) -> bool:
        """删除租户（级联删除所有相关数据）"""
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return False
        
        db.delete(tenant)
        db.commit()
        
        logger.info(f"Deleted tenant: {tenant_id}")
        return True
    
    @staticmethod
    def check_charge_point_limit(db: Session, tenant_id: UUID) -> tuple[bool, int, int]:
        """
        检查充电桩数量限制
        
        Returns:
            (within_limit, current_count, max_count)
        """
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return False, 0, 0
        
        current_count = db.query(ChargePoint).filter(
            ChargePoint.tenant_id == tenant_id,
            ChargePoint.is_active == True
        ).count()
        
        max_count = tenant.max_charge_points
        within_limit = current_count < max_count
        
        return within_limit, current_count, max_count
    
    @staticmethod
    def check_user_limit(db: Session, tenant_id: UUID) -> tuple[bool, int, int]:
        """
        检查用户数量限制
        
        Returns:
            (within_limit, current_count, max_count)
        """
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return False, 0, 0
        
        current_count = db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.status == "active"
        ).count()
        
        max_count = tenant.max_users
        within_limit = current_count < max_count
        
        return within_limit, current_count, max_count
    
    @staticmethod
    def get_tenant_statistics(db: Session, tenant_id: UUID) -> dict:
        """获取租户统计信息"""
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return {}
        
        charge_point_count = db.query(ChargePoint).filter(
            ChargePoint.tenant_id == tenant_id,
            ChargePoint.is_active == True
        ).count()
        
        user_count = db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.status == "active"
        ).count()
        
        membership_count = db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.status == "active"
        ).count()
        
        return {
            "tenant_id": str(tenant_id),
            "name": tenant.name,
            "subscription_plan": tenant.subscription_plan,
            "charge_points": {
                "current": charge_point_count,
                "max": tenant.max_charge_points,
                "usage_percent": (charge_point_count / tenant.max_charge_points * 100) if tenant.max_charge_points > 0 else 0
            },
            "users": {
                "current": user_count,
                "max": tenant.max_users,
                "usage_percent": (user_count / tenant.max_users * 100) if tenant.max_users > 0 else 0
            },
            "memberships": membership_count
        }
