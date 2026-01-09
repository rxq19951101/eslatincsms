#
# 用户管理服务层
# 提供管理员用户和终端用户的 CRUD 操作
#

from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database.models import AdminUser, EndUser, TenantMembership, Role, TenantMembershipRole
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


class EndUserService:
    """终端用户服务"""
    
    @staticmethod
    def create_end_user(
        db: Session,
        tenant_id: UUID,
        phone: str,
        id_tag: str,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        balance: float = 0.0
    ) -> EndUser:
        """创建终端用户"""
        # 检查手机号和ID标签是否已存在（按租户）
        existing_user = db.query(EndUser).filter(
            and_(
                EndUser.tenant_id == tenant_id,
                (EndUser.phone == phone) | (EndUser.id_tag == id_tag)
            )
        ).first()
        
        if existing_user:
            raise ValueError("Phone or ID tag already exists in this tenant")
        
        end_user = EndUser(
            tenant_id=tenant_id,
            phone=phone,
            id_tag=id_tag,
            email=email,
            full_name=full_name,
            balance=balance
        )
        
        db.add(end_user)
        db.commit()
        db.refresh(end_user)
        
        logger.info(f"Created end user: {phone} (tenant: {tenant_id})")
        return end_user
    
    @staticmethod
    def get_end_user_by_id(db: Session, user_id: UUID) -> Optional[EndUser]:
        """根据ID获取终端用户"""
        return db.query(EndUser).filter(EndUser.id == user_id).first()
    
    @staticmethod
    def get_end_user_by_phone(
        db: Session,
        tenant_id: UUID,
        phone: str
    ) -> Optional[EndUser]:
        """根据手机号获取终端用户（按租户）"""
        return db.query(EndUser).filter(
            and_(EndUser.tenant_id == tenant_id, EndUser.phone == phone)
        ).first()
    
    @staticmethod
    def get_end_user_by_id_tag(
        db: Session,
        tenant_id: UUID,
        id_tag: str
    ) -> Optional[EndUser]:
        """根据ID标签获取终端用户（按租户）"""
        return db.query(EndUser).filter(
            and_(EndUser.tenant_id == tenant_id, EndUser.id_tag == id_tag)
        ).first()
    
    @staticmethod
    def list_end_users(
        db: Session,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None
    ) -> List[EndUser]:
        """获取终端用户列表（按租户）"""
        query = db.query(EndUser).filter(EndUser.tenant_id == tenant_id)
        
        if status:
            query = query.filter(EndUser.status == status)
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def update_end_user(
        db: Session,
        user_id: UUID,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        status: Optional[str] = None,
        balance: Optional[float] = None
    ) -> Optional[EndUser]:
        """更新终端用户"""
        end_user = db.query(EndUser).filter(EndUser.id == user_id).first()
        if not end_user:
            return None
        
        if email is not None:
            # 检查邮箱是否已被其他用户使用（按租户）
            existing = db.query(EndUser).filter(
                and_(
                    EndUser.email == email,
                    EndUser.tenant_id == end_user.tenant_id,
                    EndUser.id != user_id
                )
            ).first()
            if existing:
                raise ValueError("Email already exists in this tenant")
            end_user.email = email
        if full_name is not None:
            end_user.full_name = full_name
        if status is not None:
            end_user.status = status
        if balance is not None:
            end_user.balance = balance
        
        db.commit()
        db.refresh(end_user)
        
        logger.info(f"Updated end user: {user_id}")
        return end_user
    
    @staticmethod
    def delete_end_user(db: Session, user_id: UUID) -> bool:
        """删除终端用户"""
        end_user = db.query(EndUser).filter(EndUser.id == user_id).first()
        if not end_user:
            return False
        
        db.delete(end_user)
        db.commit()
        
        logger.info(f"Deleted end user: {user_id}")
        return True
