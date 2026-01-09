#
# 租户成员关系服务
# 管理管理员用户与租户的关系
#

from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.database.models import TenantMembership, AdminUser, Tenant
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")


class MembershipService:
    """租户成员关系服务"""
    
    @staticmethod
    def add_user_to_tenant(
        db: Session,
        tenant_id: UUID,
        admin_user_id: UUID,
        is_primary: bool = False
    ) -> TenantMembership:
        """将管理员用户添加到租户"""
        # 检查是否已存在
        existing = db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.admin_user_id == admin_user_id
        ).first()
        
        if existing:
            raise ValueError("User is already a member of this tenant")
        
        # 如果设置为 primary，需要将其他租户的 is_primary 设置为 False
        if is_primary:
            db.query(TenantMembership).filter(
                TenantMembership.admin_user_id == admin_user_id
            ).update({"is_primary": False})
        
        membership = TenantMembership(
            tenant_id=tenant_id,
            admin_user_id=admin_user_id,
            is_primary=is_primary,
            status="active"
        )
        
        db.add(membership)
        db.commit()
        db.refresh(membership)
        
        logger.info(f"Added user {admin_user_id} to tenant {tenant_id}")
        return membership
    
    @staticmethod
    def remove_user_from_tenant(
        db: Session,
        tenant_id: UUID,
        admin_user_id: UUID
    ) -> bool:
        """从租户中移除管理员用户"""
        membership = db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.admin_user_id == admin_user_id
        ).first()
        
        if not membership:
            return False
        
        db.delete(membership)
        db.commit()
        
        logger.info(f"Removed user {admin_user_id} from tenant {tenant_id}")
        return True
    
    @staticmethod
    def set_primary_tenant(
        db: Session,
        admin_user_id: UUID,
        tenant_id: UUID
    ) -> bool:
        """设置用户的默认租户"""
        # 验证用户是否属于该租户
        membership = db.query(TenantMembership).filter(
            TenantMembership.admin_user_id == admin_user_id,
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.status == "active"
        ).first()
        
        if not membership:
            raise ValueError("User does not belong to the specified tenant")
        
        # 将所有租户的 is_primary 设置为 FALSE
        db.query(TenantMembership).filter(
            TenantMembership.admin_user_id == admin_user_id
        ).update({"is_primary": False})
        
        # 设置指定租户为默认
        membership.is_primary = True
        db.commit()
        
        logger.info(f"Set primary tenant {tenant_id} for user {admin_user_id}")
        return True
    
    @staticmethod
    def get_user_tenants(
        db: Session,
        admin_user_id: UUID
    ) -> List[TenantMembership]:
        """获取用户所属的所有租户"""
        return db.query(TenantMembership).filter(
            TenantMembership.admin_user_id == admin_user_id,
            TenantMembership.status == "active"
        ).all()
    
    @staticmethod
    def get_tenant_members(
        db: Session,
        tenant_id: UUID
    ) -> List[TenantMembership]:
        """获取租户的所有成员"""
        return db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.status == "active"
        ).all()
    
    @staticmethod
    def get_membership(
        db: Session,
        tenant_id: UUID,
        admin_user_id: UUID
    ) -> Optional[TenantMembership]:
        """获取成员关系"""
        return db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.admin_user_id == admin_user_id
        ).first()
    
    @staticmethod
    def update_membership_status(
        db: Session,
        tenant_id: UUID,
        admin_user_id: UUID,
        status: str
    ) -> bool:
        """更新成员状态"""
        membership = db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.admin_user_id == admin_user_id
        ).first()
        
        if not membership:
            return False
        
        membership.status = status
        db.commit()
        
        logger.info(f"Updated membership status for user {admin_user_id} in tenant {tenant_id}")
        return True
