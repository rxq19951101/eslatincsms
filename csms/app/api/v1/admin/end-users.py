#
# 终端用户管理API
# 提供终端用户的CRUD操作（运营后台）
#

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.database.base import get_db
from app.database.models import EndUser
from app.core.auth import get_current_user
from app.core.permissions import get_current_admin_user
from app.services.user_service import EndUserService
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class CreateEndUserRequest(BaseModel):
    phone: str
    id_tag: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    balance: float = 0.0


class UpdateEndUserRequest(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    status: Optional[str] = None
    balance: Optional[float] = None


class EndUserResponse(BaseModel):
    id: str
    tenant_id: str
    phone: str
    email: Optional[str]
    full_name: Optional[str]
    id_tag: str
    balance: float
    status: str
    last_login_at: Optional[str]
    created_at: str
    updated_at: str


# ==================== 终端用户端点 ====================

@router.get("", response_model=List[EndUserResponse], summary="获取终端用户列表")
async def list_end_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取终端用户列表（按租户）"""
    # 从请求中获取 tenant_id（通过中间件设置）
    from app.database.base import tenant_id_context
    tenant_id = tenant_id_context.get()
    
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    users = EndUserService.list_end_users(
        db=db,
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
        status=status
    )
    
    return [
        EndUserResponse(
            id=str(u.id),
            tenant_id=str(u.tenant_id),
            phone=u.phone,
            email=u.email,
            full_name=u.full_name,
            id_tag=u.id_tag,
            balance=float(u.balance),
            status=u.status,
            last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
            created_at=u.created_at.isoformat() if u.created_at else "",
            updated_at=u.updated_at.isoformat() if u.updated_at else ""
        )
        for u in users
    ]


@router.post("", response_model=EndUserResponse, summary="创建终端用户")
async def create_end_user(
    request_data: CreateEndUserRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建终端用户"""
    # 从请求中获取 tenant_id
    from app.database.base import tenant_id_context
    tenant_id = tenant_id_context.get()
    
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    try:
        end_user = EndUserService.create_end_user(
            db=db,
            tenant_id=tenant_id,
            phone=request_data.phone,
            id_tag=request_data.id_tag,
            email=request_data.email,
            full_name=request_data.full_name,
            balance=request_data.balance
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return EndUserResponse(
        id=str(end_user.id),
        tenant_id=str(end_user.tenant_id),
        phone=end_user.phone,
        email=end_user.email,
        full_name=end_user.full_name,
        id_tag=end_user.id_tag,
        balance=float(end_user.balance),
        status=end_user.status,
        last_login_at=end_user.last_login_at.isoformat() if end_user.last_login_at else None,
        created_at=end_user.created_at.isoformat() if end_user.created_at else "",
        updated_at=end_user.updated_at.isoformat() if end_user.updated_at else ""
    )


@router.get("/{user_id}", response_model=EndUserResponse, summary="获取终端用户详情")
async def get_end_user(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取终端用户详情"""
    end_user = EndUserService.get_end_user_by_id(db, user_id)
    if not end_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return EndUserResponse(
        id=str(end_user.id),
        tenant_id=str(end_user.tenant_id),
        phone=end_user.phone,
        email=end_user.email,
        full_name=end_user.full_name,
        id_tag=end_user.id_tag,
        balance=float(end_user.balance),
        status=end_user.status,
        last_login_at=end_user.last_login_at.isoformat() if end_user.last_login_at else None,
        created_at=end_user.created_at.isoformat() if end_user.created_at else "",
        updated_at=end_user.updated_at.isoformat() if end_user.updated_at else ""
    )


@router.put("/{user_id}", response_model=EndUserResponse, summary="更新终端用户")
async def update_end_user(
    user_id: UUID,
    request_data: UpdateEndUserRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新终端用户"""
    try:
        end_user = EndUserService.update_end_user(
            db=db,
            user_id=user_id,
            email=request_data.email,
            full_name=request_data.full_name,
            status=request_data.status,
            balance=request_data.balance
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not end_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return EndUserResponse(
        id=str(end_user.id),
        tenant_id=str(end_user.tenant_id),
        phone=end_user.phone,
        email=end_user.email,
        full_name=end_user.full_name,
        id_tag=end_user.id_tag,
        balance=float(end_user.balance),
        status=end_user.status,
        last_login_at=end_user.last_login_at.isoformat() if end_user.last_login_at else None,
        created_at=end_user.created_at.isoformat() if end_user.created_at else "",
        updated_at=end_user.updated_at.isoformat() if end_user.updated_at else ""
    )


@router.delete("/{user_id}", summary="删除终端用户")
async def delete_end_user(
    user_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除终端用户"""
    success = EndUserService.delete_end_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "User deleted successfully"}
