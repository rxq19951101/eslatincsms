#
# 角色权限服务
# 管理角色定义和用户角色分配
#

from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.database.models import Role, TenantMembershipRole, TenantMembership
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")


class RoleService:
    """角色服务"""
    
    @staticmethod
    def create_role(
        db: Session,
        name: str,
        permissions: List[str],
        tenant_id: Optional[UUID] = None,
        description: Optional[str] = None,
        scope: str = "tenant"
    ) -> Role:
        """创建角色"""
        # 检查角色名是否已存在（按租户）
        existing = db.query(Role).filter(
            Role.tenant_id == tenant_id,
            Role.name == name
        ).first()
        
        if existing:
            raise ValueError("Role name already exists")
        
        role = Role(
            tenant_id=tenant_id,
            name=name,
            permissions=permissions,
            description=description,
            scope=scope
        )
        
        db.add(role)
        db.commit()
        db.refresh(role)
        
        logger.info(f"Created role: {name} (tenant: {tenant_id})")
        return role
    
    @staticmethod
    def get_role_by_id(db: Session, role_id: UUID) -> Optional[Role]:
        """根据ID获取角色"""
        return db.query(Role).filter(Role.id == role_id).first()
    
    @staticmethod
    def list_roles(
        db: Session,
        tenant_id: Optional[UUID] = None,
        scope: Optional[str] = None
    ) -> List[Role]:
        """获取角色列表"""
        query = db.query(Role)
        
        if tenant_id is not None:
            # 包括系统角色（tenant_id 为 NULL）和租户角色
            query = query.filter(
                (Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None))
            )
        else:
            # 只获取系统角色
            query = query.filter(Role.tenant_id.is_(None))
        
        if scope:
            query = query.filter(Role.scope == scope)
        
        return query.all()
    
    @staticmethod
    def update_role(
        db: Session,
        role_id: UUID,
        name: Optional[str] = None,
        permissions: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> Optional[Role]:
        """更新角色"""
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            return None
        
        if name is not None:
            # 检查角色名是否已被其他角色使用（按租户）
            existing = db.query(Role).filter(
                Role.tenant_id == role.tenant_id,
                Role.name == name,
                Role.id != role_id
            ).first()
            if existing:
                raise ValueError("Role name already exists")
            role.name = name
        
        if permissions is not None:
            role.permissions = permissions
        
        if description is not None:
            role.description = description
        
        db.commit()
        db.refresh(role)
        
        logger.info(f"Updated role: {role_id}")
        return role
    
    @staticmethod
    def delete_role(db: Session, role_id: UUID) -> bool:
        """删除角色"""
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            return False
        
        db.delete(role)
        db.commit()
        
        logger.info(f"Deleted role: {role_id}")
        return True


class MembershipRoleService:
    """成员角色关系服务"""
    
    @staticmethod
    def assign_role_to_membership(
        db: Session,
        membership_id: UUID,
        role_id: UUID
    ) -> TenantMembershipRole:
        """为成员分配角色"""
        # 检查是否已存在
        existing = db.query(TenantMembershipRole).filter(
            TenantMembershipRole.membership_id == membership_id,
            TenantMembershipRole.role_id == role_id
        ).first()
        
        if existing:
            raise ValueError("Role is already assigned to this membership")
        
        membership_role = TenantMembershipRole(
            membership_id=membership_id,
            role_id=role_id
        )
        
        db.add(membership_role)
        db.commit()
        db.refresh(membership_role)
        
        logger.info(f"Assigned role {role_id} to membership {membership_id}")
        return membership_role
    
    @staticmethod
    def remove_role_from_membership(
        db: Session,
        membership_id: UUID,
        role_id: UUID
    ) -> bool:
        """从成员中移除角色"""
        membership_role = db.query(TenantMembershipRole).filter(
            TenantMembershipRole.membership_id == membership_id,
            TenantMembershipRole.role_id == role_id
        ).first()
        
        if not membership_role:
            return False
        
        db.delete(membership_role)
        db.commit()
        
        logger.info(f"Removed role {role_id} from membership {membership_id}")
        return True
    
    @staticmethod
    def get_membership_roles(
        db: Session,
        membership_id: UUID
    ) -> List[Role]:
        """获取成员的所有角色"""
        return db.query(Role).join(TenantMembershipRole).filter(
            TenantMembershipRole.membership_id == membership_id
        ).all()
    
    @staticmethod
    def get_user_permissions(
        db: Session,
        admin_user_id: UUID,
        tenant_id: UUID
    ) -> List[str]:
        """获取用户在租户中的所有权限"""
        # 获取成员关系
        membership = db.query(TenantMembership).filter(
            TenantMembership.admin_user_id == admin_user_id,
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.status == "active"
        ).first()
        
        if not membership:
            return []
        
        # 获取所有角色
        roles = db.query(Role).join(TenantMembershipRole).filter(
            TenantMembershipRole.membership_id == membership.id
        ).all()
        
        # 合并所有权限
        permissions = set()
        for role in roles:
            if isinstance(role.permissions, list):
                permissions.update(role.permissions)
            elif role.permissions == ["*"]:
                # 超级权限
                return ["*"]
        
        return list(permissions)
