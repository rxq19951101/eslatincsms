#
# 管理员用户管理API
# 提供管理员用户的CRUD操作
#

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.database.base import get_db
from app.database.models import AdminUser
from app.core.auth import get_current_user
from app.core.permissions import get_current_admin_user
from app.services.user_service import AdminUserService
from app.core.logging_config import get_logger
from app.core.api_logging import log_api_request, log_api_response, log_api_error, log_business_operation

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class CreateUserRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    is_super_admin: bool = False


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_super_admin: bool
    last_login_at: Optional[str]
    created_at: str
    updated_at: str


# ==================== 用户端点 ====================

@router.get("", response_model=List[UserResponse], summary="获取管理员列表")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取管理员用户列表"""
    try:
        log_api_request(
            method="GET",
            path="/api/v1/admin/users",
            operation="list_users",
            current_user=current_user,
            params={"skip": skip, "limit": limit, "is_active": is_active}
        )
        
        users = AdminUserService.list_admin_users(
            db=db,
            skip=skip,
            limit=limit,
            is_active=is_active
        )
        
        result = [
            UserResponse(
                id=str(u.id),
                username=u.username,
                email=u.email,
                full_name=u.full_name,
                is_active=u.is_active,
                is_super_admin=u.is_super_admin,
                last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
                created_at=u.created_at.isoformat() if u.created_at else "",
                updated_at=u.updated_at.isoformat() if u.updated_at else ""
            )
            for u in users
        ]
        
        log_api_response(
            method="GET",
            path="/api/v1/admin/users",
            operation="list_users",
            result="success",
            current_user=current_user,
            details={"count": len(result)}
        )
        
        return result
    except Exception as e:
        log_api_error(
            method="GET",
            path="/api/v1/admin/users",
            operation="list_users",
            error=e,
            current_user=current_user,
            params={"skip": skip, "limit": limit}
        )
        raise


@router.post("", response_model=UserResponse, summary="创建管理员")
async def create_user(
    request_data: CreateUserRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建管理员用户"""
    try:
        log_api_request(
            method="POST",
            path="/api/v1/admin/users",
            operation="create_user",
            current_user=current_user,
            params={"username": request_data.username, "email": request_data.email}
        )
        
        # 检查权限（需要超级管理员或租户管理员）
        # 这里暂时允许所有认证用户创建，实际应该检查权限
        
        try:
            admin_user = AdminUserService.create_admin_user(
                db=db,
                username=request_data.username,
                email=request_data.email,
                password=request_data.password,
                full_name=request_data.full_name,
                is_super_admin=request_data.is_super_admin
            )
        except ValueError as e:
            log_api_error(
                method="POST",
                path="/api/v1/admin/users",
                operation="create_user",
                error=e,
                current_user=current_user,
                params={"username": request_data.username, "email": request_data.email}
            )
            raise HTTPException(status_code=400, detail=str(e))
        
        log_business_operation(
            operation="创建管理员",
            entity_type="admin_user",
            entity_id=str(admin_user.id),
            result="success",
            current_user=current_user,
            details={"username": admin_user.username, "email": admin_user.email}
        )
        
        log_api_response(
            method="POST",
            path="/api/v1/admin/users",
            operation="create_user",
            result="success",
            current_user=current_user,
            details={"user_id": str(admin_user.id), "username": admin_user.username}
        )
        
        return UserResponse(
            id=str(admin_user.id),
            username=admin_user.username,
            email=admin_user.email,
            full_name=admin_user.full_name,
            is_active=admin_user.is_active,
            is_super_admin=admin_user.is_super_admin,
            last_login_at=admin_user.last_login_at.isoformat() if admin_user.last_login_at else None,
            created_at=admin_user.created_at.isoformat() if admin_user.created_at else "",
            updated_at=admin_user.updated_at.isoformat() if admin_user.updated_at else ""
        )
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="POST",
            path="/api/v1/admin/users",
            operation="create_user",
            error=e,
            current_user=current_user,
            params={"username": request_data.username}
        )
        raise


@router.get("/{user_id}", response_model=UserResponse, summary="获取管理员详情")
async def get_user(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取管理员用户详情"""
    try:
        log_api_request(
            method="GET",
            path=f"/api/v1/admin/users/{user_id}",
            operation="get_user",
            current_user=current_user,
            params={"user_id": str(user_id)}
        )
        
        admin_user = AdminUserService.get_admin_user_by_id(db, user_id)
        if not admin_user:
            log_api_error(
                method="GET",
                path=f"/api/v1/admin/users/{user_id}",
                operation="get_user",
                error=HTTPException(status_code=404, detail="User not found"),
                current_user=current_user,
                params={"user_id": str(user_id)}
            )
            raise HTTPException(status_code=404, detail="User not found")
        
        log_api_response(
            method="GET",
            path=f"/api/v1/admin/users/{user_id}",
            operation="get_user",
            result="success",
            current_user=current_user,
            details={"user_id": str(user_id)}
        )
        
        return UserResponse(
        id=str(admin_user.id),
        username=admin_user.username,
        email=admin_user.email,
        full_name=admin_user.full_name,
        is_active=admin_user.is_active,
        is_super_admin=admin_user.is_super_admin,
        last_login_at=admin_user.last_login_at.isoformat() if admin_user.last_login_at else None,
        created_at=admin_user.created_at.isoformat() if admin_user.created_at else "",
        updated_at=admin_user.updated_at.isoformat() if admin_user.updated_at else ""
        )
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="GET",
            path=f"/api/v1/admin/users/{user_id}",
            operation="get_user",
            error=e,
            current_user=current_user,
            params={"user_id": str(user_id)}
        )
        raise


@router.put("/{user_id}", response_model=UserResponse, summary="更新管理员")
async def update_user(
    user_id: UUID,
    request_data: UpdateUserRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新管理员用户"""
    try:
        log_api_request(
            method="PUT",
            path=f"/api/v1/admin/users/{user_id}",
            operation="update_user",
            current_user=current_user,
            params={"user_id": str(user_id)}
        )
        
        try:
            admin_user = AdminUserService.update_admin_user(
                db=db,
                user_id=user_id,
                full_name=request_data.full_name,
                email=request_data.email,
                is_active=request_data.is_active
            )
        except ValueError as e:
            log_api_error(
                method="PUT",
                path=f"/api/v1/admin/users/{user_id}",
                operation="update_user",
                error=e,
                current_user=current_user,
                params={"user_id": str(user_id)}
            )
            raise HTTPException(status_code=400, detail=str(e))
        
        if not admin_user:
            log_api_error(
                method="PUT",
                path=f"/api/v1/admin/users/{user_id}",
                operation="update_user",
                error=HTTPException(status_code=404, detail="User not found"),
                current_user=current_user,
                params={"user_id": str(user_id)}
            )
            raise HTTPException(status_code=404, detail="User not found")
        
        log_business_operation(
            operation="更新管理员",
            entity_type="admin_user",
            entity_id=str(user_id),
            result="success",
            current_user=current_user
        )
        
        log_api_response(
            method="PUT",
            path=f"/api/v1/admin/users/{user_id}",
            operation="update_user",
            result="success",
            current_user=current_user,
            details={"user_id": str(user_id)}
        )
        
        return UserResponse(
        id=str(admin_user.id),
        username=admin_user.username,
        email=admin_user.email,
        full_name=admin_user.full_name,
        is_active=admin_user.is_active,
        is_super_admin=admin_user.is_super_admin,
        last_login_at=admin_user.last_login_at.isoformat() if admin_user.last_login_at else None,
        created_at=admin_user.created_at.isoformat() if admin_user.created_at else "",
        updated_at=admin_user.updated_at.isoformat() if admin_user.updated_at else ""
        )
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="PUT",
            path=f"/api/v1/admin/users/{user_id}",
            operation="update_user",
            error=e,
            current_user=current_user,
            params={"user_id": str(user_id)}
        )
        raise


@router.delete("/{user_id}", summary="删除管理员")
async def delete_user(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除管理员用户"""
    try:
        log_api_request(
            method="DELETE",
            path=f"/api/v1/admin/users/{user_id}",
            operation="delete_user",
            current_user=current_user,
            params={"user_id": str(user_id)}
        )
        
        success = AdminUserService.delete_admin_user(db, user_id)
        if not success:
            log_api_error(
                method="DELETE",
                path=f"/api/v1/admin/users/{user_id}",
                operation="delete_user",
                error=HTTPException(status_code=404, detail="User not found"),
                current_user=current_user,
                params={"user_id": str(user_id)}
            )
            raise HTTPException(status_code=404, detail="User not found")
        
        log_business_operation(
            operation="删除管理员",
            entity_type="admin_user",
            entity_id=str(user_id),
            result="success",
            current_user=current_user
        )
        
        log_api_response(
            method="DELETE",
            path=f"/api/v1/admin/users/{user_id}",
            operation="delete_user",
            result="success",
            current_user=current_user,
            details={"user_id": str(user_id)}
        )
        
        return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="DELETE",
            path=f"/api/v1/admin/users/{user_id}",
            operation="delete_user",
            error=e,
            current_user=current_user,
            params={"user_id": str(user_id)}
        )
        raise


@router.get("/me", response_model=UserResponse, summary="获取当前管理员信息")
async def get_me(
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """获取当前管理员信息"""
    return UserResponse(
        id=str(current_user_obj.id),
        username=current_user_obj.username,
        email=current_user_obj.email,
        full_name=current_user_obj.full_name,
        is_active=current_user_obj.is_active,
        is_super_admin=current_user_obj.is_super_admin,
        last_login_at=current_user_obj.last_login_at.isoformat() if current_user_obj.last_login_at else None,
        created_at=current_user_obj.created_at.isoformat() if current_user_obj.created_at else "",
        updated_at=current_user_obj.updated_at.isoformat() if current_user_obj.updated_at else ""
    )


@router.put("/me/password", summary="修改密码")
async def change_password(
    request_data: ChangePasswordRequest,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """修改当前用户的密码"""
    user_id = current_user_obj.id
    
    try:
        success = AdminUserService.change_password(
            db=db,
            user_id=user_id,
            old_password=request_data.old_password,
            new_password=request_data.new_password
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "Password changed successfully"}
