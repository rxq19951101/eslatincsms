#
# 告警管理API
# 提供告警的查询、创建、确认、解决等功能
#

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.database.base import get_db, tenant_id_context
from app.database.models import Alert
from app.core.auth import get_current_user
from app.core.permissions import get_current_admin_user
from app.services.alert_service import AlertService, AlertRuleService
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")

router = APIRouter()


# ==================== 请求/响应模型 ====================

class CreateAlertRequest(BaseModel):
    alert_type: str
    severity: str
    title: str
    description: Optional[str] = None
    charge_point_id: Optional[str] = None
    evse_id: Optional[int] = None
    metadata: Optional[dict] = None


class AlertResponse(BaseModel):
    id: str
    tenant_id: str
    charge_point_id: Optional[str]
    evse_id: Optional[int]
    alert_type: str
    severity: str
    status: str
    title: str
    description: Optional[str]
    metadata: dict
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[str]
    resolved_at: Optional[str]
    created_at: str
    updated_at: str


class CreateAlertRuleRequest(BaseModel):
    name: str
    alert_type: str
    conditions: dict
    severity: str
    is_enabled: bool = True


class UpdateAlertRuleRequest(BaseModel):
    name: Optional[str] = None
    conditions: Optional[dict] = None
    severity: Optional[str] = None
    is_enabled: Optional[bool] = None


class AlertRuleResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    alert_type: str
    conditions: dict
    severity: str
    is_enabled: bool
    created_at: str
    updated_at: str


# ==================== 告警端点 ====================

@router.get("", response_model=List[AlertResponse], summary="获取告警列表")
async def list_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    charge_point_id: Optional[str] = Query(None),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """获取告警列表"""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    alerts = AlertService.list_alerts(
        db=db,
        tenant_id=tenant_id,
        skip=skip,
        limit=limit,
        status=status,
        severity=severity,
        alert_type=alert_type,
        charge_point_id=charge_point_id
    )
    
    return [
        AlertResponse(
            id=str(a.id),
            tenant_id=str(a.tenant_id),
            charge_point_id=a.charge_point_id,
            evse_id=a.evse_id,
            alert_type=a.alert_type,
            severity=a.severity,
            status=a.status,
            title=a.title,
            description=a.description,
            # models.Alert 使用 alert_metadata（避免与 SQLAlchemy Base.metadata 冲突）
            metadata=a.alert_metadata if isinstance(getattr(a, "alert_metadata", None), dict) else {},
            acknowledged_by=str(a.acknowledged_by) if a.acknowledged_by else None,
            acknowledged_at=a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
            created_at=a.created_at.isoformat() if a.created_at else "",
            updated_at=a.updated_at.isoformat() if a.updated_at else ""
        )
        for a in alerts
    ]


@router.post("", response_model=AlertResponse, summary="创建告警（手动）")
async def create_alert(
    request_data: CreateAlertRequest,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """创建告警（手动）"""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    try:
        alert = AlertService.create_alert(
            db=db,
            tenant_id=tenant_id,
            alert_type=request_data.alert_type,
            severity=request_data.severity,
            title=request_data.title,
            description=request_data.description,
            charge_point_id=request_data.charge_point_id,
            evse_id=request_data.evse_id,
            metadata=request_data.metadata
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return AlertResponse(
        id=str(alert.id),
        tenant_id=str(alert.tenant_id),
        charge_point_id=alert.charge_point_id,
        evse_id=alert.evse_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        title=alert.title,
        description=alert.description,
        metadata=alert.alert_metadata if isinstance(getattr(alert, "alert_metadata", None), dict) else {},
        acknowledged_by=str(alert.acknowledged_by) if alert.acknowledged_by else None,
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        updated_at=alert.updated_at.isoformat() if alert.updated_at else ""
    )


@router.get("/{alert_id}", response_model=AlertResponse, summary="获取告警详情")
async def get_alert(
    alert_id: UUID,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """获取告警详情"""
    alert = AlertService.get_alert_by_id(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return AlertResponse(
        id=str(alert.id),
        tenant_id=str(alert.tenant_id),
        charge_point_id=alert.charge_point_id,
        evse_id=alert.evse_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        title=alert.title,
        description=alert.description,
        metadata=alert.alert_metadata if isinstance(getattr(alert, "alert_metadata", None), dict) else {},
        acknowledged_by=str(alert.acknowledged_by) if alert.acknowledged_by else None,
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        updated_at=alert.updated_at.isoformat() if alert.updated_at else ""
    )


@router.put("/{alert_id}/acknowledge", response_model=AlertResponse, summary="确认告警")
async def acknowledge_alert(
    alert_id: UUID,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """确认告警"""
    alert = AlertService.acknowledge_alert(
        db=db,
        alert_id=alert_id,
        acknowledged_by=current_user_obj.id
    )
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return AlertResponse(
        id=str(alert.id),
        tenant_id=str(alert.tenant_id),
        charge_point_id=alert.charge_point_id,
        evse_id=alert.evse_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        title=alert.title,
        description=alert.description,
        metadata=alert.alert_metadata if isinstance(getattr(alert, "alert_metadata", None), dict) else {},
        acknowledged_by=str(alert.acknowledged_by) if alert.acknowledged_by else None,
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        updated_at=alert.updated_at.isoformat() if alert.updated_at else ""
    )


@router.put("/{alert_id}/resolve", response_model=AlertResponse, summary="解决告警")
async def resolve_alert(
    alert_id: UUID,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """解决告警"""
    alert = AlertService.resolve_alert(db=db, alert_id=alert_id)
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return AlertResponse(
        id=str(alert.id),
        tenant_id=str(alert.tenant_id),
        charge_point_id=alert.charge_point_id,
        evse_id=alert.evse_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        title=alert.title,
        description=alert.description,
        metadata=alert.alert_metadata if isinstance(getattr(alert, "alert_metadata", None), dict) else {},
        acknowledged_by=str(alert.acknowledged_by) if alert.acknowledged_by else None,
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        created_at=alert.created_at.isoformat() if alert.created_at else "",
        updated_at=alert.updated_at.isoformat() if alert.updated_at else ""
    )


@router.get("/statistics", summary="获取告警统计")
async def get_alert_statistics(
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """获取告警统计信息"""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    stats = AlertService.get_alert_statistics(db, tenant_id)
    return stats


# ==================== 告警规则端点 ====================

@router.get("/rules", response_model=List[AlertRuleResponse], summary="获取告警规则列表")
async def list_alert_rules(
    is_enabled: Optional[bool] = Query(None),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """获取告警规则列表"""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    rules = AlertRuleService.list_alert_rules(
        db=db,
        tenant_id=tenant_id,
        is_enabled=is_enabled
    )
    
    return [
        AlertRuleResponse(
            id=str(r.id),
            tenant_id=str(r.tenant_id),
            name=r.name,
            alert_type=r.alert_type,
            conditions=r.conditions if isinstance(r.conditions, dict) else {},
            severity=r.severity,
            is_enabled=r.is_enabled,
            created_at=r.created_at.isoformat() if r.created_at else "",
            updated_at=r.updated_at.isoformat() if r.updated_at else ""
        )
        for r in rules
    ]


@router.post("/rules", response_model=AlertRuleResponse, summary="创建告警规则")
async def create_alert_rule(
    request_data: CreateAlertRuleRequest,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """创建告警规则"""
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    try:
        rule = AlertRuleService.create_alert_rule(
            db=db,
            tenant_id=tenant_id,
            name=request_data.name,
            alert_type=request_data.alert_type,
            conditions=request_data.conditions,
            severity=request_data.severity,
            is_enabled=request_data.is_enabled
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return AlertRuleResponse(
        id=str(rule.id),
        tenant_id=str(rule.tenant_id),
        name=rule.name,
        alert_type=rule.alert_type,
        conditions=rule.conditions if isinstance(rule.conditions, dict) else {},
        severity=rule.severity,
        is_enabled=rule.is_enabled,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else ""
    )


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse, summary="更新告警规则")
async def update_alert_rule(
    rule_id: UUID,
    request_data: UpdateAlertRuleRequest,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """更新告警规则"""
    try:
        rule = AlertRuleService.update_alert_rule(
            db=db,
            rule_id=rule_id,
            name=request_data.name,
            conditions=request_data.conditions,
            severity=request_data.severity,
            is_enabled=request_data.is_enabled
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    return AlertRuleResponse(
        id=str(rule.id),
        tenant_id=str(rule.tenant_id),
        name=rule.name,
        alert_type=rule.alert_type,
        conditions=rule.conditions if isinstance(rule.conditions, dict) else {},
        severity=rule.severity,
        is_enabled=rule.is_enabled,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else ""
    )


@router.delete("/rules/{rule_id}", summary="删除告警规则")
async def delete_alert_rule(
    rule_id: UUID,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """删除告警规则"""
    success = AlertRuleService.delete_alert_rule(db, rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    return {"message": "Alert rule deleted successfully"}
