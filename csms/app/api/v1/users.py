#
# 充电用户管理API
# 提供充电用户（C端用户）的管理功能
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from datetime import datetime, timezone

from app.database.base import get_db
from app.database.models import EndUser, Order, Invoice, ChargingSession, Tenant
from app.core.auth import get_current_admin_user, require_permission
from app.core.tenant_middleware import get_tenant_id
from app.core.exceptions import PermissionDenied
from app.core.id_generator import generate_order_id
from fastapi import Request

router = APIRouter(prefix="/users", tags=["充电用户管理"])


# ==================== 请求/响应模型 ====================

class EndUserResponse(BaseModel):
    """充电用户响应"""
    id: str
    tenant_id: Optional[str]
    username: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    id_tag: str
    balance: float
    total_spent: float
    status: str
    created_at: datetime
    last_login_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class EndUserDetailResponse(EndUserResponse):
    """充电用户详情响应"""
    order_count: int = 0
    total_energy_kwh: float = 0.0
    total_charging_time_minutes: int = 0


class EndUserUpdateRequest(BaseModel):
    """更新用户请求"""
    username: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    status: Optional[str] = None


class BalanceAdjustRequest(BaseModel):
    """余额调整请求"""
    amount: float
    reason: str
    type: str  # "recharge" or "deduct"


# ==================== 用户管理端点 ====================

@router.get("", response_model=List[EndUserResponse], summary="获取用户列表")
async def get_users(
    status_filter: Optional[str] = Query(None, description="按状态筛选"),
    search: Optional[str] = Query(None, description="搜索（用户名、手机号、邮箱）"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    request: Request,
    current_user = Depends(require_permission("users:view")),
    db: Session = Depends(get_db)
):
    """
    获取充电用户列表
    
    - 支持按状态筛选
    - 支持搜索
    - 自动应用租户过滤
    """
    tenant_id = get_tenant_id(request)
    
    query = db.query(EndUser)
    
    # 多租户过滤
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(EndUser.tenant_id == tenant_id)
    
    if status_filter:
        query = query.filter(EndUser.status == status_filter)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                EndUser.username.like(search_pattern),
                EndUser.phone.like(search_pattern),
                EndUser.email.like(search_pattern),
                EndUser.id_tag.like(search_pattern)
            )
        )
    
    users = query.order_by(desc(EndUser.created_at)).offset(offset).limit(limit).all()
    
    return users


@router.get("/{user_id}", response_model=EndUserDetailResponse, summary="获取用户详情")
async def get_user(
    user_id: str,
    request: Request,
    current_user = Depends(require_permission("users:detail")),
    db: Session = Depends(get_db)
):
    """获取用户详情"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(EndUser).filter(EndUser.id == user_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(EndUser.tenant_id == tenant_id)
    
    user = query.first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 统计订单信息
    order_query = db.query(Order).filter(Order.user_id == user_id)
    if tenant_id and not current_user.is_super_admin:
        order_query = order_query.filter(Order.tenant_id == tenant_id)
    
    order_count = order_query.count()
    
    # 统计总充电量和时长
    completed_orders = order_query.filter(Order.status == "completed").all()
    total_energy_kwh = 0.0
    total_charging_time_minutes = 0
    
    for order in completed_orders:
        if order.session_id:
            session = db.query(ChargingSession).filter(ChargingSession.id == order.session_id).first()
            if session:
                if session.meter_start is not None and session.meter_stop is not None:
                    total_energy_kwh += float(session.meter_stop - session.meter_start) / 1000.0
                if session.start_time and session.end_time:
                    duration = session.end_time - session.start_time
                    total_charging_time_minutes += int(duration.total_seconds() / 60)
    
    return EndUserDetailResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        phone=user.phone,
        email=user.email,
        id_tag=user.id_tag,
        balance=float(user.balance),
        total_spent=float(user.total_spent),
        status=user.status,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        order_count=order_count,
        total_energy_kwh=round(total_energy_kwh, 2),
        total_charging_time_minutes=total_charging_time_minutes
    )


@router.put("/{user_id}", response_model=EndUserResponse, summary="更新用户信息")
async def update_user(
    user_id: str,
    user_data: EndUserUpdateRequest,
    request: Request,
    current_user = Depends(require_permission("users:edit")),
    db: Session = Depends(get_db)
):
    """更新用户信息"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(EndUser).filter(EndUser.id == user_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(EndUser.tenant_id == tenant_id)
    
    user = query.first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 更新字段
    if user_data.username is not None:
        user.username = user_data.username
    if user_data.phone is not None:
        user.phone = user_data.phone
    if user_data.email is not None:
        user.email = user_data.email
    if user_data.status is not None:
        user.status = user_data.status
    
    db.commit()
    db.refresh(user)
    
    return user


@router.put("/{user_id}/freeze", summary="冻结/解冻用户")
async def freeze_user(
    user_id: str,
    freeze: bool = Query(..., description="true=冻结, false=解冻"),
    request: Request,
    current_user = Depends(require_permission("users:freeze")),
    db: Session = Depends(get_db)
):
    """冻结或解冻用户账号"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(EndUser).filter(EndUser.id == user_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(EndUser.tenant_id == tenant_id)
    
    user = query.first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    user.status = "frozen" if freeze else "active"
    db.commit()
    
    return {"message": f"用户已{'冻结' if freeze else '解冻'}"}


@router.post("/{user_id}/balance/adjust", summary="调整用户余额")
async def adjust_user_balance(
    user_id: str,
    balance_data: BalanceAdjustRequest,
    request: Request,
    current_user = Depends(require_permission("users:balance:adjust")),
    db: Session = Depends(get_db)
):
    """
    调整用户余额
    
    - 支持充值和扣款
    - 记录操作日志
    """
    tenant_id = get_tenant_id(request)
    
    query = db.query(EndUser).filter(EndUser.id == user_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(EndUser.tenant_id == tenant_id)
    
    user = query.first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 调整余额
    if balance_data.type == "recharge":
        user.balance += balance_data.amount
    elif balance_data.type == "deduct":
        if user.balance < balance_data.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="余额不足"
            )
        user.balance -= balance_data.amount
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的操作类型，应为 recharge 或 deduct"
        )
    
    # 记录审计日志
    from app.database.models import AuditLog
    audit_log = AuditLog(
        tenant_id=tenant_id,
        admin_user_id=current_user.id,
        action="user_balance_adjust",
        resource_type="user",
        resource_id=user_id,
        details={
            "type": balance_data.type,
            "amount": balance_data.amount,
            "reason": balance_data.reason,
            "new_balance": float(user.balance)
        },
        ip_address=request.client.host if request.client else None
    )
    db.add(audit_log)
    
    db.commit()
    
    return {
        "message": "余额调整成功",
        "new_balance": float(user.balance)
    }
