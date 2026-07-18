#
# 用户管理服务层
# 提供后台管理员用户的 CRUD 操作
#

from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.database.models import AdminUser, TenantMembership, Role, TenantMembershipRole
from app.core.auth import get_password_hash, verify_password
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")


class AdminUserService:
    """管理员用户服务"""
    
    @staticmethod
    def create_admin_user(
        db: Session,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        is_super_admin: bool = False
    ) -> AdminUser:
        """创建管理员用户"""
        # 检查用户名和邮箱是否已存在
        existing_user = db.query(AdminUser).filter(
            (AdminUser.username == username) | (AdminUser.email == email)
        ).first()
        
        if existing_user:
            raise ValueError("Username or email already exists")
        
        admin_user = AdminUser(
            username=username,
            email=email,
            password_hash=get_password_hash(password),
            full_name=full_name,
            is_super_admin=is_super_admin
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        logger.info(f"Created admin user: {username}")
        return admin_user
    
    @staticmethod
    def get_admin_user_by_id(db: Session, user_id: UUID) -> Optional[AdminUser]:
        """根据ID获取管理员用户"""
        return db.query(AdminUser).filter(AdminUser.id == user_id).first()
    
    @staticmethod
    def get_admin_user_by_username(db: Session, username: str) -> Optional[AdminUser]:
        """根据用户名获取管理员用户"""
        return db.query(AdminUser).filter(AdminUser.username == username).first()
    
    @staticmethod
    def get_admin_user_by_email(db: Session, email: str) -> Optional[AdminUser]:
        """根据邮箱获取管理员用户"""
        return db.query(AdminUser).filter(AdminUser.email == email).first()
    
    @staticmethod
    def list_admin_users(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None
    ) -> List[AdminUser]:
        """获取管理员用户列表"""
        query = db.query(AdminUser)
        
        if is_active is not None:
            query = query.filter(AdminUser.is_active == is_active)
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def update_admin_user(
        db: Session,
        user_id: UUID,
        full_name: Optional[str] = None,
        email: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Optional[AdminUser]:
        """更新管理员用户"""
        admin_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
        if not admin_user:
            return None
        
        if full_name is not None:
            admin_user.full_name = full_name
        if email is not None:
            # 检查邮箱是否已被其他用户使用
            existing = db.query(AdminUser).filter(
                and_(AdminUser.email == email, AdminUser.id != user_id)
            ).first()
            if existing:
                raise ValueError("Email already exists")
            admin_user.email = email
        if is_active is not None:
            admin_user.is_active = is_active
        
        db.commit()
        db.refresh(admin_user)
        
        logger.info(f"Updated admin user: {user_id}")
        return admin_user
    
    @staticmethod
    def change_password(
        db: Session,
        user_id: UUID,
        old_password: str,
        new_password: str
    ) -> bool:
        """修改密码"""
        admin_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
        if not admin_user:
            return False
        
        if not verify_password(old_password, admin_user.password_hash):
            raise ValueError("Invalid old password")
        
        admin_user.password_hash = get_password_hash(new_password)
        db.commit()
        
        logger.info(f"Password changed for admin user: {user_id}")
        return True
    
    @staticmethod
    def delete_admin_user(db: Session, user_id: UUID) -> bool:
        """删除管理员用户"""
        admin_user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
        if not admin_user:
            return False
        
        db.delete(admin_user)
        db.commit()
        
        logger.info(f"Deleted admin user: {user_id}")
        return True
