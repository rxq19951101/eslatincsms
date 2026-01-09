#
# 告警服务层
# 提供告警的创建、查询、确认、解决等功能
#

from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timezone
from app.database.models import Alert, AlertRule, ChargePoint, EVSE
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")


class AlertService:
    """告警服务"""
    
    @staticmethod
    def create_alert(
        db: Session,
        tenant_id: UUID,
        alert_type: str,
        severity: str,
        title: str,
        description: Optional[str] = None,
        charge_point_id: Optional[str] = None,
        evse_id: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> Alert:
        """创建告警"""
        alert = Alert(
            tenant_id=tenant_id,
            charge_point_id=charge_point_id,
            evse_id=evse_id,
            alert_type=alert_type,
            severity=severity,
            status="pending",
            title=title,
            description=description,
            metadata=metadata or {}
        )
        
        db.add(alert)
        db.commit()
        db.refresh(alert)
        
        logger.info(f"Created alert: {alert.id} (type: {alert_type}, severity: {severity})")
        return alert
    
    @staticmethod
    def get_alert_by_id(db: Session, alert_id: UUID) -> Optional[Alert]:
        """根据ID获取告警"""
        return db.query(Alert).filter(Alert.id == alert_id).first()
    
    @staticmethod
    def list_alerts(
        db: Session,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
        charge_point_id: Optional[str] = None
    ) -> List[Alert]:
        """获取告警列表"""
        query = db.query(Alert).filter(Alert.tenant_id == tenant_id)
        
        if status:
            query = query.filter(Alert.status == status)
        if severity:
            query = query.filter(Alert.severity == severity)
        if alert_type:
            query = query.filter(Alert.alert_type == alert_type)
        if charge_point_id:
            query = query.filter(Alert.charge_point_id == charge_point_id)
        
        return query.order_by(Alert.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def acknowledge_alert(
        db: Session,
        alert_id: UUID,
        acknowledged_by: UUID
    ) -> Optional[Alert]:
        """确认告警"""
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return None
        
        alert.status = "acknowledged"
        alert.acknowledged_by = acknowledged_by
        alert.acknowledged_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(alert)
        
        logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
        return alert
    
    @staticmethod
    def resolve_alert(
        db: Session,
        alert_id: UUID
    ) -> Optional[Alert]:
        """解决告警"""
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return None
        
        alert.status = "resolved"
        alert.resolved_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(alert)
        
        logger.info(f"Alert {alert_id} resolved")
        return alert
    
    @staticmethod
    def get_alert_statistics(
        db: Session,
        tenant_id: UUID
    ) -> dict:
        """获取告警统计信息"""
        total = db.query(Alert).filter(Alert.tenant_id == tenant_id).count()
        
        pending = db.query(Alert).filter(
            and_(Alert.tenant_id == tenant_id, Alert.status == "pending")
        ).count()
        
        acknowledged = db.query(Alert).filter(
            and_(Alert.tenant_id == tenant_id, Alert.status == "acknowledged")
        ).count()
        
        resolved = db.query(Alert).filter(
            and_(Alert.tenant_id == tenant_id, Alert.status == "resolved")
        ).count()
        
        critical = db.query(Alert).filter(
            and_(
                Alert.tenant_id == tenant_id,
                Alert.severity == "critical",
                Alert.status == "pending"
            )
        ).count()
        
        warning = db.query(Alert).filter(
            and_(
                Alert.tenant_id == tenant_id,
                Alert.severity == "warning",
                Alert.status == "pending"
            )
        ).count()
        
        return {
            "total": total,
            "pending": pending,
            "acknowledged": acknowledged,
            "resolved": resolved,
            "critical": critical,
            "warning": warning
        }


class AlertRuleService:
    """告警规则服务"""
    
    @staticmethod
    def create_alert_rule(
        db: Session,
        tenant_id: UUID,
        name: str,
        alert_type: str,
        conditions: dict,
        severity: str,
        is_enabled: bool = True
    ) -> AlertRule:
        """创建告警规则"""
        # 检查规则名是否已存在（按租户）
        existing = db.query(AlertRule).filter(
            AlertRule.tenant_id == tenant_id,
            AlertRule.name == name
        ).first()
        
        if existing:
            raise ValueError("Alert rule name already exists")
        
        alert_rule = AlertRule(
            tenant_id=tenant_id,
            name=name,
            alert_type=alert_type,
            conditions=conditions,
            severity=severity,
            is_enabled=is_enabled
        )
        
        db.add(alert_rule)
        db.commit()
        db.refresh(alert_rule)
        
        logger.info(f"Created alert rule: {name} (tenant: {tenant_id})")
        return alert_rule
    
    @staticmethod
    def get_alert_rule_by_id(db: Session, rule_id: UUID) -> Optional[AlertRule]:
        """根据ID获取告警规则"""
        return db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    
    @staticmethod
    def list_alert_rules(
        db: Session,
        tenant_id: UUID,
        is_enabled: Optional[bool] = None
    ) -> List[AlertRule]:
        """获取告警规则列表"""
        query = db.query(AlertRule).filter(AlertRule.tenant_id == tenant_id)
        
        if is_enabled is not None:
            query = query.filter(AlertRule.is_enabled == is_enabled)
        
        return query.all()
    
    @staticmethod
    def update_alert_rule(
        db: Session,
        rule_id: UUID,
        name: Optional[str] = None,
        conditions: Optional[dict] = None,
        severity: Optional[str] = None,
        is_enabled: Optional[bool] = None
    ) -> Optional[AlertRule]:
        """更新告警规则"""
        alert_rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
        if not alert_rule:
            return None
        
        if name is not None:
            # 检查规则名是否已被其他规则使用（按租户）
            existing = db.query(AlertRule).filter(
                AlertRule.tenant_id == alert_rule.tenant_id,
                AlertRule.name == name,
                AlertRule.id != rule_id
            ).first()
            if existing:
                raise ValueError("Alert rule name already exists")
            alert_rule.name = name
        
        if conditions is not None:
            alert_rule.conditions = conditions
        if severity is not None:
            alert_rule.severity = severity
        if is_enabled is not None:
            alert_rule.is_enabled = is_enabled
        
        db.commit()
        db.refresh(alert_rule)
        
        logger.info(f"Updated alert rule: {rule_id}")
        return alert_rule
    
    @staticmethod
    def delete_alert_rule(db: Session, rule_id: UUID) -> bool:
        """删除告警规则"""
        alert_rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
        if not alert_rule:
            return False
        
        db.delete(alert_rule)
        db.commit()
        
        logger.info(f"Deleted alert rule: {rule_id}")
        return True
