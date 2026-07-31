#
# 报表服务层
# 提供各种统计报表和数据分析功能
#

import csv
import io
import json
from decimal import Decimal
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract, case
from app.database.models import (
    ChargePoint, Order, Invoice, ChargingSession, 
    AppUser, Site, EVSEStatus, MeterValue
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
        group_by: str = "day",  # day, week, month, year
        site_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Return paid-invoice revenue for one tenant in a UTC half-open range."""
        if group_by != "day":
            return []

        report_date = func.date(Invoice.issued_at)
        query = db.query(
            report_date.label("date"),
            func.sum(Invoice.total_amount).label("total_revenue"),
            func.sum(Invoice.energy_kwh).label("total_energy"),
            func.count(Invoice.id).label("invoice_count"),
        ).filter(
            Invoice.tenant_id == tenant_id,
            Invoice.issued_at >= start_date,
            Invoice.issued_at < end_date,
            Invoice.status == "paid",
        )

        if site_id is not None:
            query = query.join(
                ChargingSession,
                ChargingSession.id == Invoice.session_id,
            ).join(
                ChargePoint,
                ChargePoint.id == ChargingSession.charge_point_id,
            ).filter(
                ChargePoint.tenant_id == tenant_id,
                ChargePoint.site_id == site_id,
            )

        results = query.group_by(report_date).order_by(report_date).all()
        return [
            {
                "date": str(row.date),
                "total_revenue": row.total_revenue or Decimal("0"),
                "total_energy_kwh": row.total_energy or Decimal("0"),
                "invoice_count": int(row.invoice_count or 0),
                "currency": "COP",
            }
            for row in results
        ]
    
    @staticmethod
    def get_energy_report(
        db: Session,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day",
        site_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Return valid completed-session energy in a UTC half-open range."""
        if group_by != "day":
            return []

        report_date = func.date(ChargingSession.start_time)
        query = db.query(
            report_date.label("date"),
            func.sum(
                ChargingSession.meter_stop - ChargingSession.meter_start
            ).label("total_energy_wh"),
            func.count(ChargingSession.id).label("session_count"),
        ).filter(
            ChargingSession.tenant_id == tenant_id,
            ChargingSession.start_time >= start_date,
            ChargingSession.start_time < end_date,
            ChargingSession.status == "completed",
            ChargingSession.meter_stop.isnot(None),
            ChargingSession.meter_start.isnot(None),
            ChargingSession.meter_stop >= ChargingSession.meter_start,
        )

        if site_id is not None:
            query = query.join(
                ChargePoint,
                ChargePoint.id == ChargingSession.charge_point_id,
            ).filter(
                ChargePoint.tenant_id == tenant_id,
                ChargePoint.site_id == site_id,
            )

        results = query.group_by(report_date).order_by(report_date).all()
        return [
            {
                "date": str(row.date),
                "total_energy_kwh": Decimal(row.total_energy_wh or 0) / Decimal("1000"),
                "session_count": int(row.session_count or 0),
            }
            for row in results
        ]
    
    @staticmethod
    def get_orders_report(
        db: Session,
        tenant_id: UUID,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day",
        site_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Return business-order counts in a UTC half-open range."""
        if group_by != "day":
            return []

        report_date = func.date(Order.created_at)
        query = db.query(
            report_date.label("date"),
            func.count(Order.id).label("order_count"),
            func.sum(
                case(
                    (Order.status == "completed", 1),
                    else_=0,
                )
            ).label("completed_count"),
        ).filter(
            Order.tenant_id == tenant_id,
            Order.created_at >= start_date,
            Order.created_at < end_date,
        )

        if site_id is not None:
            query = query.join(
                ChargePoint,
                ChargePoint.id == Order.charge_point_id,
            ).filter(
                ChargePoint.tenant_id == tenant_id,
                ChargePoint.site_id == site_id,
            )

        results = query.group_by(report_date).order_by(report_date).all()
        return [
            {
                "date": str(row.date),
                "order_count": int(row.order_count or 0),
                "completed_count": int(row.completed_count or 0),
            }
            for row in results
        ]
    
    @staticmethod
    def get_user_statistics(
        db: Session,
        tenant_id: UUID
    ) -> Dict[str, Any]:
        """获取用户统计"""
        # AppUser 是平台级用户，不绑定单一租户；租户口径按实际使用过该租户的用户统计。
        total_users = db.query(func.count(func.distinct(ChargingSession.user_id))).filter(
            ChargingSession.tenant_id == tenant_id,
            ChargingSession.user_id.isnot(None),
        ).scalar() or 0

        # 今日活跃用户（今天在该租户有充电会话）
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        active_today = db.query(func.count(func.distinct(ChargingSession.user_id))).filter(
            ChargingSession.tenant_id == tenant_id,
            ChargingSession.user_id.isnot(None),
            ChargingSession.start_time >= today_start,
        ).scalar() or 0
        
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
        report_type: str,
        start_date: datetime,
        end_date: datetime,
        format: str = "csv",
        site_id: Optional[UUID] = None,
    ) -> bytes:
        """Export one tenant report using the same filters as its query API."""
        if format != "csv":
            raise ValueError("Unsupported export format")

        loaders = {
            "revenue": (
                ReportService.get_revenue_report,
                ["date", "total_revenue", "total_energy_kwh", "invoice_count", "currency"],
            ),
            "energy": (
                ReportService.get_energy_report,
                ["date", "total_energy_kwh", "session_count"],
            ),
            "orders": (
                ReportService.get_orders_report,
                ["date", "order_count", "completed_count"],
            ),
        }
        loader_config = loaders.get(report_type)
        if loader_config is None:
            raise ValueError("Unsupported report type")

        loader, fieldnames = loader_config
        rows = loader(
            db,
            tenant_id,
            start_date,
            end_date,
            "day",
            site_id=site_id,
        )

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        if rows:
            writer.writerows(rows)
        return buf.getvalue().encode("utf-8-sig")

    @staticmethod
    def export_all_tenants_report(
        db: Session,
        report_type: str,
        start_date: datetime,
        end_date: datetime,
        format: str = "csv",
    ) -> bytes:
        """导出总管理员的全租户汇总报表。"""
        loaders = {
            "revenue": ReportService.get_all_tenants_revenue_report,
            "energy": ReportService.get_all_tenants_energy_report,
            "orders": ReportService.get_all_tenants_orders_report,
        }
        loader = loaders.get(report_type)
        if not loader:
            raise ValueError("Unsupported report type")
        rows = loader(db, start_date, end_date, "day")
        if format == "json":
            return json.dumps(rows, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        if format not in {"csv", "excel"}:
            raise ValueError("Unsupported export format")
        fieldnames = {
            "revenue": ["date", "total_revenue", "total_energy_kwh", "invoice_count"],
            "energy": ["date", "total_energy_kwh", "session_count"],
            "orders": ["date", "order_count", "completed_count"],
        }[report_type]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        if rows:
            writer.writerows(rows)
        return buf.getvalue().encode("utf-8-sig")
    
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
        total_users = db.query(AppUser).filter(AppUser.status == "active").count()
        
        # 今日活跃用户
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        active_today = db.query(AppUser).filter(
            AppUser.status == "active",
            AppUser.last_login_at >= today_start,
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
