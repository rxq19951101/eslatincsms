#
# 告警管理API
# 提供实时告警监控和告警规则配置
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from datetime import datetime, timezone

from app.database.base import get_db
from app.database.models import Alert, ChargePoint, Tenant
from app.core.auth import get_current_admin_user, require_permission
from app.core.tenant_middleware import get_tenant_id
from fastapi import Request

router = APIRouter(prefix="/alerts", tags=["告警管理"])


# ==================== 请求/响应模型 ====================

class AlertResponse(BaseModel):
    """告警响应"""
    id: int
    tenant_id: Optional[str]
    alert_type: str
    severity: str
    charge_point_id: Optional[str]
    message: str
    status: str
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class AlertAcknowledgeRequest(BaseModel):
    """确认告警请求"""
    note: Optional[str] = None


# ==================== 告警管理端点 ====================

@router.get("", response_model=List[AlertResponse], summary="获取告警列表")
async def get_alerts(
    alert_type: Optional[str] = Query(None, description="按类型筛选"),
    severity: Optional[str] = Query(None, description="按级别筛选"),
    status_filter: Optional[str] = Query(None, description="按状态筛选"),
    charge_point_id: Optional[str] = Query(None, description="按充电桩筛选"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    request: Request,
    current_user = Depends(require_permission("alerts:view")),
    db: Session = Depends(get_db)
):
    """
    获取告警列表
    
    - 支持按类型、级别、状态、充电桩筛选
    - 自动应用租户过滤
    """
    tenant_id = get_tenant_id(request)
    
    query = db.query(Alert)
    
    # 多租户过滤
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Alert.tenant_id == tenant_id)
    
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    if severity:
        query = query.filter(Alert.severity == severity)
    if status_filter:
        query = query.filter(Alert.status == status_filter)
    if charge_point_id:
        query = query.filter(Alert.charge_point_id == charge_point_id)
    
    alerts = query.order_by(desc(Alert.created_at)).offset(offset).limit(limit).all()
    
    return alerts


@router.post("/{alert_id}/acknowledge", summary="确认告警")
async def acknowledge_alert(
    alert_id: int,
    acknowledge_data: AlertAcknowledgeRequest,
    request: Request,
    current_user = Depends(require_permission("alerts:acknowledge")),
    db: Session = Depends(get_db)
):
    """确认告警"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Alert).filter(Alert.id == alert_id)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Alert.tenant_id == tenant_id)
    
    alert = query.first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警不存在"
        )
    
    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = current_user.id
    
    db.commit()
    
    return {"message": "告警已确认"}


@router.get("/stats", summary="获取告警统计")
async def get_alert_stats(
    request: Request,
    current_user = Depends(require_permission("alerts:view")),
    db: Session = Depends(get_db)
):
    """获取告警统计信息"""
    tenant_id = get_tenant_id(request)
    
    query = db.query(Alert)
    if tenant_id and not current_user.is_super_admin:
        query = query.filter(Alert.tenant_id == tenant_id)
    
    # 按级别统计
    from sqlalchemy import func
    severity_stats = query.with_entities(
        Alert.severity,
        func.count(Alert.id).label("count")
    ).group_by(Alert.severity).all()
    
    # 按状态统计
    status_stats = query.with_entities(
        Alert.status,
        func.count(Alert.id).label("count")
    ).group_by(Alert.status).all()
    
    # 按类型统计
    type_stats = query.with_entities(
        Alert.alert_type,
        func.count(Alert.id).label("count")
    ).group_by(Alert.alert_type).all()
    
    return {
        "by_severity": {severity: count for severity, count in severity_stats},
        "by_status": {status: count for status, count in status_stats},
        "by_type": {alert_type: count for alert_type, count in type_stats}
    }
