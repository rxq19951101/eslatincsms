#
# 统计API
# 提供充电桩历史数据统计和监控
#

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case
from app.database import get_db, ChargePoint, ChargingSession, MeterValue, DeviceEvent, Invoice, EVSEStatus, Tariff
from app.core.logging_config import get_logger

logger = get_logger("ocpp_csms")
router = APIRouter()


@router.get("/charger/{charge_point_id}/history", summary="获取充电桩历史监控数据")
def get_charger_history(
    charge_point_id: str,
    days: int = Query(10, ge=1, le=30, description="查询天数，默认10天"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取充电桩过去N天的监控数据（使用新表结构）
    
    返回数据包括:
    - 每日状态变化统计
    - 每日充电次数
    - 每日充电量（kWh）
    - 每日充电时长（分钟）
    - 每日收入（COP）
    - 状态分布
    """
    logger.info(
        f"[API] GET /api/v1/statistics/charger/{charge_point_id}/history | "
        f"查询天数: {days} 天"
    )
    
    # 验证充电桩是否存在
    charge_point = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
    if not charge_point:
        logger.warning(f"[API] GET /api/v1/statistics/charger/{charge_point_id}/history | 充电桩未找到")
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    # 计算时间范围
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # 获取该充电桩的所有充电会话（已完成）
    sessions = db.query(ChargingSession).filter(
        ChargingSession.charge_point_id == charge_point_id,
        ChargingSession.start_time >= start_date,
        ChargingSession.status == "completed"
    ).all()
    
    # 按天统计数据
    daily_stats = {}
    
    # 初始化所有天的数据
    for i in range(days):
        date = (end_date - timedelta(days=i)).date()
        daily_stats[date.isoformat()] = {
            "date": date.isoformat(),
            "charging_sessions": 0,
            "total_energy_kwh": 0.0,
            "total_duration_minutes": 0.0,
            "total_revenue": 0.0,
            "avg_energy_per_session": 0.0,
            "avg_duration_per_session": 0.0,
        }
    
    # 统计会话数据
    for session in sessions:
        if session.start_time:
            session_date = session.start_time.date()
            date_key = session_date.isoformat()
            
            if date_key in daily_stats:
                daily_stats[date_key]["charging_sessions"] += 1
                
                # 计算能量（从meter_stop - meter_start）
                if session.meter_stop is not None and session.meter_start is not None:
                    energy_wh = session.meter_stop - session.meter_start
                    energy_kwh = energy_wh / 1000.0 if energy_wh > 0 else 0
                    daily_stats[date_key]["total_energy_kwh"] += energy_kwh
                
                # 计算时长
                if session.end_time and session.start_time:
                    duration_seconds = (session.end_time - session.start_time).total_seconds()
                    duration_minutes = duration_seconds / 60.0
                    daily_stats[date_key]["total_duration_minutes"] += duration_minutes
                
                # 从发票获取收入
                invoice = db.query(Invoice).filter(Invoice.session_id == session.id).first()
                if invoice:
                    daily_stats[date_key]["total_revenue"] += invoice.total_amount or 0
    
    # 计算平均值
    for date_key, stats in daily_stats.items():
        if stats["charging_sessions"] > 0:
            stats["avg_energy_per_session"] = stats["total_energy_kwh"] / stats["charging_sessions"]
            stats["avg_duration_per_session"] = stats["total_duration_minutes"] / stats["charging_sessions"]
    
    # 转换为列表并按日期排序
    daily_stats_list = sorted(
        [stats for stats in daily_stats.values()],
        key=lambda x: x["date"]
    )
    
    # 计算总计
    total_stats = {
        "total_sessions": sum(s["charging_sessions"] for s in daily_stats_list),
        "total_energy_kwh": sum(s["total_energy_kwh"] for s in daily_stats_list),
        "total_duration_minutes": sum(s["total_duration_minutes"] for s in daily_stats_list),
        "total_revenue": sum(s["total_revenue"] for s in daily_stats_list),
    }
    
    if total_stats["total_sessions"] > 0:
        total_stats["avg_energy_per_session"] = total_stats["total_energy_kwh"] / total_stats["total_sessions"]
        total_stats["avg_duration_per_session"] = total_stats["total_duration_minutes"] / total_stats["total_sessions"]
    else:
        total_stats["avg_energy_per_session"] = 0.0
        total_stats["avg_duration_per_session"] = 0.0
    
    return {
        "charge_point_id": charge_point_id,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days
        },
        "daily_stats": daily_stats_list,
        "total_stats": total_stats,
        "charge_point_info": {
            "id": charge_point.id,
            "vendor": charge_point.vendor,
            "model": charge_point.model,
            "location": {
                "latitude": charge_point.site.latitude if charge_point.site else None,
                "longitude": charge_point.site.longitude if charge_point.site else None,
                "address": charge_point.site.address if charge_point.site else None
            },
            "price_per_kwh": (
                db.query(Tariff).filter(
                    Tariff.site_id == charge_point.site_id,
                    Tariff.is_active == True
                ).first().base_price_per_kwh
                if charge_point.site_id and db.query(Tariff).filter(
                    Tariff.site_id == charge_point.site_id,
                    Tariff.is_active == True
                ).first() else None
            )
        }
    }


@router.get("/charger/{charge_point_id}/status-history", summary="获取充电桩状态变化历史")
def get_charger_status_history(
    charge_point_id: str,
    days: int = Query(10, ge=1, le=30, description="查询天数"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取充电桩状态变化历史
    
    注意：当前实现基于事务数据推断状态，未来可以添加状态历史表
    """
    charge_point = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
    if not charge_point:
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # 获取状态变化历史（从DeviceEvent表）
    status_events = db.query(DeviceEvent).filter(
        DeviceEvent.charge_point_id == charge_point_id,
        DeviceEvent.event_type == "StatusNotification",
        DeviceEvent.timestamp >= start_date
    ).all()
    
    # 按天统计状态分布
    daily_status = {}
    
    for i in range(days):
        date = (end_date - timedelta(days=i)).date()
        daily_status[date.isoformat()] = {
            "date": date.isoformat(),
            "status_distribution": {
                "Available": 0,
                "Charging": 0,
                "Offline": 0,
                "Faulted": 0,
                "Unavailable": 0
            }
        }
    
    # 统计每天的状态
    for event in status_events:
        if event.timestamp:
            event_date = event.timestamp.date()
            date_key = event_date.isoformat()
            
            if date_key in daily_status:
                # 从event_data中提取状态
                status = event.event_data.get("status", "Unknown") if isinstance(event.event_data, dict) else "Unknown"
                if status in daily_status[date_key]["status_distribution"]:
                    daily_status[date_key]["status_distribution"][status] += 1
    
    # 转换为列表
    status_history = sorted(
        [stats for stats in daily_status.values()],
        key=lambda x: x["date"]
    )
    
    return {
        "charge_point_id": charge_point_id,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days
        },
        "status_history": status_history
    }


@router.get("/charger/{charge_point_id}/heartbeat-history", summary="获取充电桩心跳历史")
def get_charger_heartbeat_history(
    charge_point_id: str,
    hours: int = Query(24, ge=1, le=168, description="查询小时数，默认24小时"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取充电桩心跳历史数据，用于健康状态监控
    
    返回数据包括:
    - 心跳时间点列表
    - 每个心跳点的健康状态（normal/warning/abnormal）
    - 心跳间隔统计
    """
    logger.info(
        f"[API] GET /api/v1/statistics/charger/{charge_point_id}/heartbeat-history | "
        f"查询小时数: {hours} 小时"
    )
    charge_point = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
    if not charge_point:
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    # 获取心跳历史记录（从DeviceEvent表）
    heartbeats = db.query(DeviceEvent).filter(
        DeviceEvent.charge_point_id == charge_point_id,
        DeviceEvent.event_type == "Heartbeat",
        DeviceEvent.timestamp >= start_time,
        DeviceEvent.timestamp <= end_time
    ).order_by(DeviceEvent.timestamp.asc()).all()
    
    # 转换为前端需要的格式
    heartbeat_data = []
    prev_timestamp = None
    for hb in heartbeats:
        interval_seconds = None
        if prev_timestamp and hb.timestamp:
            interval_seconds = (hb.timestamp - prev_timestamp).total_seconds()
        
        # 判断健康状态（基于间隔）
        health_status = "normal"
        if interval_seconds:
            if interval_seconds > 120:  # 超过2分钟
                health_status = "abnormal"
            elif interval_seconds > 60:  # 超过1分钟
                health_status = "warning"
        
        heartbeat_data.append({
            "timestamp": hb.timestamp.isoformat() if hb.timestamp else None,
            "health_status": health_status,
            "interval_seconds": interval_seconds,
        })
        prev_timestamp = hb.timestamp
    
    # 统计健康状态分布
    health_stats = {
        "normal": len([h for h in heartbeat_data if h["health_status"] == "normal"]),
        "warning": len([h for h in heartbeat_data if h["health_status"] == "warning"]),
        "abnormal": len([h for h in heartbeat_data if h["health_status"] == "abnormal"]),
    }
    
    # 计算平均心跳间隔
    intervals = [h["interval_seconds"] for h in heartbeat_data if h["interval_seconds"] is not None]
    avg_interval = sum(intervals) / len(intervals) if intervals else None
    
    return {
        "charge_point_id": charge_point_id,
        "period": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "hours": hours
        },
        "heartbeats": heartbeat_data,
        "health_stats": health_stats,
        "avg_interval_seconds": avg_interval,
        "total_heartbeats": len(heartbeat_data)
    }


@router.get("/charger/{charge_point_id}/status-timeline", summary="获取充电桩状态时间线")
def get_charger_status_timeline(
    charge_point_id: str,
    hours: int = Query(24, ge=1, le=168, description="查询小时数，默认24小时"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取充电桩状态变化时间线
    
    返回数据包括:
    - 状态变化记录
    - 每个状态的持续时间
    - 状态分布统计（离线、空闲、充电中）
    """
    logger.info(
        f"[API] GET /api/v1/statistics/charger/{charge_point_id}/status-timeline | "
        f"查询小时数: {hours} 小时"
    )
    charge_point = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
    if not charge_point:
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    # 获取状态历史记录（从DeviceEvent表）
    status_records = db.query(DeviceEvent).filter(
        DeviceEvent.charge_point_id == charge_point_id,
        DeviceEvent.event_type == "StatusNotification",
        DeviceEvent.timestamp >= start_time,
        DeviceEvent.timestamp <= end_time
    ).order_by(DeviceEvent.timestamp.asc()).all()
    
    # 获取当前状态
    evse_status = db.query(EVSEStatus).filter(
        EVSEStatus.charge_point_id == charge_point_id
    ).first()
    current_status = evse_status.status if evse_status else "Unknown"
    
    # 转换为前端需要的格式
    timeline_data = []
    prev_status = None
    for record in status_records:
        # 从event_data中提取状态
        status = record.event_data.get("status", "Unknown") if isinstance(record.event_data, dict) else "Unknown"
        duration_seconds = None
        if prev_status and record.timestamp:
            # 计算持续时间（需要前一个记录的时间）
            pass  # 这里需要前一个记录的时间来计算duration
        
        timeline_data.append({
            "timestamp": record.timestamp.isoformat() if record.timestamp else None,
            "status": status,
            "previous_status": prev_status,
            "duration_seconds": duration_seconds,
        })
        prev_status = status
    
    # 统计状态分布（按小时分组）
    # 将时间线按小时分组，统计每个小时的状态分布
    hourly_status = {}
    
    # 从最新到最旧遍历，构建每小时的状态
    for i in range(hours):
        hour_start = end_time - timedelta(hours=i+1)
        hour_end = end_time - timedelta(hours=i)
        
        # 找到这个小时内的状态变化
        hour_statuses = [r for r in status_records if hour_start <= r.timestamp < hour_end]
        
        # 统计这个小时内的状态分布
        status_counts = {
            "Offline": 0,
            "Available": 0,
            "Charging": 0,
            "Faulted": 0,
            "Unavailable": 0
        }
        
        # 如果有状态变化，使用变化后的状态
        if hour_statuses:
            # 使用最后一个状态变化后的状态
            last_record = hour_statuses[-1]
            last_status = last_record.event_data.get("status", "Unknown") if isinstance(last_record.event_data, dict) else "Unknown"
            if last_status in status_counts:
                status_counts[last_status] = 1
        else:
            # 如果没有状态变化，使用当前状态
            if current_status in status_counts:
                status_counts[current_status] = 1
        
        hour_key = hour_end.strftime("%Y-%m-%d %H:00")
        hourly_status[hour_key] = status_counts
    
    # 转换为列表格式
    hourly_status_list = [
        {
            "hour": hour,
            "status_distribution": status_dist
        }
        for hour, status_dist in sorted(hourly_status.items())
    ]
    
    # 总体状态分布统计
    total_status_dist = {
        "Offline": 0,
        "Available": 0,
        "Charging": 0,
        "Faulted": 0,
        "Unavailable": 0
    }
    
    for record in status_records:
        status = record.event_data.get("status", "Unknown") if isinstance(record.event_data, dict) else "Unknown"
        if status in total_status_dist:
            total_status_dist[status] += 1
    
    return {
        "charge_point_id": charge_point_id,
        "period": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "hours": hours
        },
        "timeline": timeline_data,
        "hourly_status": hourly_status_list,
        "total_status_distribution": total_status_dist,
        "current_status": current_status
    }

