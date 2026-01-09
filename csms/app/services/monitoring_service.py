#
# 监控服务
# 后台任务：检测告警、处理设备事件等
#

import asyncio
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.database.models import DeviceEvent, Alert, AlertRule, ChargePoint, EVSEStatus
from app.services.alert_service import AlertService, AlertRuleService
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")


class MonitoringService:
    """监控服务（后台任务）"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def check_offline_chargers(self, tenant_id: UUID, timeout_seconds: int = 90):
        """
        检查离线充电桩
        
        如果充电桩超过 timeout_seconds 秒没有心跳，创建离线告警
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        
        # 查找所有应该在线但超过时间未更新的充电桩
        offline_evses = self.db.query(EVSEStatus).join(ChargePoint).filter(
            ChargePoint.tenant_id == tenant_id,
            EVSEStatus.last_seen < cutoff_time,
            EVSEStatus.status != "Offline"
        ).all()
        
        for evse_status in offline_evses:
            # 检查是否已有未解决的离线告警
            existing_alert = self.db.query(Alert).filter(
                Alert.tenant_id == tenant_id,
                Alert.charge_point_id == evse_status.charge_point_id,
                Alert.alert_type == "offline",
                Alert.status.in_(["pending", "acknowledged"])
            ).first()
            
            if not existing_alert:
                # 创建离线告警
                AlertService.create_alert(
                    db=self.db,
                    tenant_id=tenant_id,
                    alert_type="offline",
                    severity="critical",
                    title=f"充电桩 {evse_status.charge_point_id} 离线",
                    description=f"充电桩超过 {timeout_seconds} 秒未发送心跳",
                    charge_point_id=evse_status.charge_point_id,
                    evse_id=evse_status.evse_id
                )
                logger.warning(f"Created offline alert for charge point: {evse_status.charge_point_id}")
    
    async def process_device_event(self, event: DeviceEvent):
        """
        处理设备事件，根据告警规则创建告警
        
        这个方法应该在设备事件创建时调用
        """
        if not event.tenant_id:
            return
        
        # 获取该租户的所有启用的告警规则
        rules = AlertRuleService.list_alert_rules(
            db=self.db,
            tenant_id=event.tenant_id,
            is_enabled=True
        )
        
        # 检查每个规则
        for rule in rules:
            if rule.alert_type == event.event_type:
                # 检查条件（简化版，实际应该更复杂的条件匹配）
                if self._check_conditions(event, rule.conditions):
                    # 创建告警
                    AlertService.create_alert(
                        db=self.db,
                        tenant_id=event.tenant_id,
                        alert_type=rule.alert_type,
                        severity=rule.severity,
                        title=f"{rule.alert_type} 告警",
                        description=f"设备事件触发告警规则: {rule.name}",
                        charge_point_id=event.charge_point_id,
                        evse_id=event.evse_id,
                        metadata={"rule_id": str(rule.id), "event_id": event.id}
                    )
    
    def _check_conditions(self, event: DeviceEvent, conditions: dict) -> bool:
        """
        检查事件是否满足告警规则的条件
        
        这是一个简化的实现，实际应该支持更复杂的条件匹配
        """
        # 这里应该实现更复杂的条件匹配逻辑
        # 暂时返回 True（总是触发）
        return True
    
    async def run_monitoring_loop(self, interval_seconds: int = 60):
        """
        运行监控循环（后台任务）
        
        定期检查离线充电桩等
        """
        while True:
            try:
                # 获取所有活跃的租户
                from app.database.models import Tenant
                tenants = self.db.query(Tenant).filter(
                    Tenant.status == "active"
                ).all()
                
                for tenant in tenants:
                    await self.check_offline_chargers(tenant.id)
                
                await asyncio.sleep(interval_seconds)
            except Exception as e:
                logger.error(f"监控循环出错: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)
