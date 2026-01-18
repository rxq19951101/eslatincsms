#
# 报表服务层
# 提供各种统计报表和数据分析功能
#

from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract, case
from app.database.models import (
    ChargePoint, Order, Invoice, ChargingSession, 
    EndUser, Site, EVSEStatus, MeterValue
)
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")


class ReportService:
    """报表服务"""
    
    @staticmethod
    def get_revenue_report(
        db: Session,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day"  # day, week, month, year
    ) -> List[Dict[str, Any]]:
        """获取收入报表"""
        query = db.query(Invoice).filter(
            Invoice.tenant_id == tenant_id,
            Invoice.issued_at >= start_date,
            Invoice.issued_at <= end_date,
            Invoice.status == "paid"
        )
        
        if group_by == "day":
            # 按天分组
            results = db.query(
                func.date(Invoice.issued_at).label("date"),
                func.sum(Invoice.total_amount).label("total_revenue"),
                func.sum(Invoice.energy_kwh).label("total_energy"),
                func.count(Invoice.id).label("invoice_count")
            ).filter(
                Invoice.tenant_id == tenant_id,
                Invoice.issued_at >= start_date,
                Invoice.issued_at <= end_date,
                Invoice.status == "paid"
            ).group_by(func.date(Invoice.issued_at)).order_by(func.date(Invoice.issued_at)).all()
            
            return [
                {
                    "date": str(r.date),
                    "total_revenue": float(r.total_revenue or 0),
                    "total_energy_kwh": float(r.total_energy or 0),
                    "invoice_count": r.invoice_count
                }
                for r in results
            ]
        else:
            # 其他分组方式（周、月、年）类似实现
            return []
    
    @staticmethod
    def get_energy_report(
        db: Session,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day"
    ) -> List[Dict[str, Any]]:
        """获取充电量报表"""
        # 从 ChargingSession 或 Invoice 获取充电量数据
        query = db.query(ChargingSession).filter(
            ChargingSession.tenant_id == tenant_id,
            ChargingSession.start_time >= start_date,
            ChargingSession.start_time <= end_date,
            ChargingSession.status == "completed"
        )
        
        if group_by == "day":
            results = db.query(
                func.date(ChargingSession.start_time).label("date"),
                func.sum(
                    (ChargingSession.meter_stop - ChargingSession.meter_start) / 1000.0
                ).label("total_energy_kwh"),
                func.count(ChargingSession.id).label("session_count")
            ).filter(
                ChargingSession.tenant_id == tenant_id,
                ChargingSession.start_time >= start_date,
                ChargingSession.start_time <= end_date,
                ChargingSession.status == "completed",
                ChargingSession.meter_stop.isnot(None),
                ChargingSession.meter_start.isnot(None)
            ).group_by(func.date(ChargingSession.start_time)).order_by(func.date(ChargingSession.start_time)).all()
            
            return [
                {
                    "date": str(r.date),
                    "total_energy_kwh": float(r.total_energy_kwh or 0),
                    "session_count": r.session_count
                }
                for r in results
            ]
        else:
            return []
    
    @staticmethod
    def get_orders_report(
        db: Session,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day"
    ) -> List[Dict[str, Any]]:
        """获取订单报表"""
        if group_by == "day":
            results = db.query(
                func.date(Order.created_at).label("date"),
                func.count(Order.id).label("order_count"),
                func.sum(
                    case(
                        (Order.status == "completed", 1),
                        else_=0
                    )
                ).label("completed_count")
            ).filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= start_date,
                Order.created_at <= end_date
            ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()
            
            return [
                {
                    "date": str(r.date),
                    "order_count": r.order_count,
                    "completed_count": int(r.completed_count or 0)
                }
                for r in results
            ]
        else:
            return []
    
    @staticmethod
    def get_user_statistics(
        db: Session,
        tenant_id: UUID
    ) -> Dict[str, Any]:
        """获取用户统计"""
        total_users = db.query(EndUser).filter(
            EndUser.tenant_id == tenant_id,
            EndUser.status == "active"
        ).count()
        
        # 今日活跃用户（有订单或登录）
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        active_today = db.query(EndUser).filter(
            EndUser.tenant_id == tenant_id,
            EndUser.last_login_at >= today_start
        ).count()
        
        return {
            "total_users": total_users,
            "active_users_today": active_today
        }
    
    @staticmethod
    def get_charge_point_statistics(
        db: Session,
        tenant_id: UUID
    ) -> Dict[str, Any]:
        """获取充电桩统计"""
        total = db.query(ChargePoint).filter(
            ChargePoint.tenant_id == tenant_id,
            ChargePoint.is_active == True
        ).count()
        
        # 在线充电桩（最近30秒内有心跳）
        now = datetime.now(timezone.utc)
        online_threshold = now - timedelta(seconds=30)
        
        online = db.query(EVSEStatus).join(ChargePoint).filter(
            ChargePoint.tenant_id == tenant_id,
            EVSEStatus.last_seen >= online_threshold
        ).distinct(EVSEStatus.charge_point_id).count()
        
        offline = total - online
        
        # 状态统计
        status_counts = db.query(
            EVSEStatus.status,
            func.count(func.distinct(EVSEStatus.charge_point_id))
        ).join(ChargePoint).filter(
            ChargePoint.tenant_id == tenant_id
        ).group_by(EVSEStatus.status).all()
        
        status_dict = {status: count for status, count in status_counts}
        
        return {
            "total": total,
            "online": online,
            "offline": offline,
            "charging": status_dict.get("Charging", 0),
            "available": status_dict.get("Available", 0),
            "faulted": status_dict.get("Faulted", 0)
        }
    
    @staticmethod
    def export_report(
        db: Session,
        tenant_id: UUID,
        report_type: str,  # revenue, energy, orders
        start_date: datetime,
        end_date: datetime,
        format: str = "csv"  # csv, excel, json
    ) -> bytes:
        """
        导出报表
        
        返回文件内容（bytes）
        """
        # 这里应该实现实际的导出逻辑
        # 暂时返回空
        return b""
    
    # ==================== 超级管理员查询所有租户的方法 ====================
    
    @staticmethod
    def get_all_tenants_revenue_report(
        db: Session,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        获取所有租户的收入报表（汇总）
        
        注意：此方法仅供超级管理员使用，需要使用 SuperSessionLocal 绕过 RLS
        """
        if group_by == "day":
            # 不过滤 tenant_id，查询所有租户的数据
            results = db.query(
                func.date(Invoice.issued_at).label("date"),
                func.sum(Invoice.total_amount).label("total_revenue"),
                func.sum(Invoice.energy_kwh).label("total_energy"),
                func.count(Invoice.id).label("invoice_count")
            ).filter(
                Invoice.issued_at >= start_date,
                Invoice.issued_at <= end_date,
                Invoice.status == "paid"
            ).group_by(func.date(Invoice.issued_at)).order_by(func.date(Invoice.issued_at)).all()
            
            return [
                {
                    "date": str(r.date),
                    "total_revenue": float(r.total_revenue or 0),
                    "total_energy_kwh": float(r.total_energy or 0),
                    "invoice_count": r.invoice_count
                }
                for r in results
            ]
        else:
            return []
    
    @staticmethod
    def get_all_tenants_energy_report(
        db: Session,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        获取所有租户的充电量报表（汇总）
        
        注意：此方法仅供超级管理员使用，需要使用 SuperSessionLocal 绕过 RLS
        """
        if group_by == "day":
            results = db.query(
                func.date(ChargingSession.start_time).label("date"),
                func.sum(
                    (ChargingSession.meter_stop - ChargingSession.meter_start) / 1000.0
                ).label("total_energy_kwh"),
                func.count(ChargingSession.id).label("session_count")
            ).filter(
                ChargingSession.start_time >= start_date,
                ChargingSession.start_time <= end_date,
                ChargingSession.status == "completed",
                ChargingSession.meter_stop.isnot(None),
                ChargingSession.meter_start.isnot(None)
            ).group_by(func.date(ChargingSession.start_time)).order_by(func.date(ChargingSession.start_time)).all()
            
            return [
                {
                    "date": str(r.date),
                    "total_energy_kwh": float(r.total_energy_kwh or 0),
                    "session_count": r.session_count
                }
                for r in results
            ]
        else:
            return []
    
    @staticmethod
    def get_all_tenants_orders_report(
        db: Session,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        获取所有租户的订单报表（汇总）
        
        注意：此方法仅供超级管理员使用，需要使用 SuperSessionLocal 绕过 RLS
        """
        if group_by == "day":
            results = db.query(
                func.date(Order.created_at).label("date"),
                func.count(Order.id).label("order_count"),
                func.sum(
                    case(
                        (Order.status == "completed", 1),
                        else_=0
                    )
                ).label("completed_count")
            ).filter(
                Order.created_at >= start_date,
                Order.created_at <= end_date
            ).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at)).all()
            
            return [
                {
                    "date": str(r.date),
                    "order_count": r.order_count,
                    "completed_count": int(r.completed_count or 0)
                }
                for r in results
            ]
        else:
            return []
    
    @staticmethod
    def get_all_tenants_user_statistics(db: Session) -> Dict[str, Any]:
        """
        获取所有租户的用户统计（汇总）
        
        注意：此方法仅供超级管理员使用，需要使用 SuperSessionLocal 绕过 RLS
        """
        # 不过滤 tenant_id
        total_users = db.query(EndUser).filter(
            EndUser.status == "active"
        ).count()
        
        # 今日活跃用户
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        active_today = db.query(EndUser).filter(
            EndUser.last_login_at >= today_start
        ).count()
        
        return {
            "total_users": total_users,
            "active_users_today": active_today
        }
    
    @staticmethod
    def get_all_tenants_charge_point_statistics(db: Session) -> Dict[str, Any]:
        """
        获取所有租户的充电桩统计（汇总）
        
        注意：此方法仅供超级管理员使用，需要使用 SuperSessionLocal 绕过 RLS
        """
        # 不过滤 tenant_id
        total = db.query(ChargePoint).filter(
            ChargePoint.is_active == True
        ).count()
        
        # 在线充电桩
        now = datetime.now(timezone.utc)
        online_threshold = now - timedelta(seconds=30)
        
        online = db.query(EVSEStatus).join(ChargePoint).filter(
            EVSEStatus.last_seen >= online_threshold
        ).distinct(EVSEStatus.charge_point_id).count()
        
        offline = total - online
        
        # 状态统计
        status_counts = db.query(
            EVSEStatus.status,
            func.count(func.distinct(EVSEStatus.charge_point_id))
        ).join(ChargePoint).group_by(EVSEStatus.status).all()
        
        status_dict = {status: count for status, count in status_counts}
        
        return {
            "total": total,
            "online": online,
            "offline": offline,
            "charging": status_dict.get("Charging", 0),
            "available": status_dict.get("Available", 0),
            "faulted": status_dict.get("Faulted", 0)
        }