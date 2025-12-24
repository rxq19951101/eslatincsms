#
# 本文件实现 csms FastAPI 应用：/ocpp WebSocket 与 /health、/chargers REST。
# 使用 Redis 保存充电桩状态（简化 OCPP 1.6J 流程，测试用途）。

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from app.core.id_generator import generate_order_id, generate_invoice_id, generate_site_id

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Body, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ocpp_csms")

# MQTT 传输支持
try:
    from app.ocpp.transport_manager import transport_manager, TransportType
    from app.core.config import get_settings
    MQTT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"MQTT 传输不可用: {e}")
    MQTT_AVAILABLE = False

# 历史记录支持
try:
    from app.utils.history_recorder import (
        record_heartbeat, 
        record_status_change, 
        get_last_heartbeat_time,
        get_last_status
    )
    HISTORY_RECORDING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"历史记录功能不可用: {e}")
    HISTORY_RECORDING_AVAILABLE = False

# 数据库支持
try:
    from app.database import init_db, check_db_health, SessionLocal
    from datetime import datetime, timezone as tz
    DATABASE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"数据库功能不可用: {e}")
    DATABASE_AVAILABLE = False

# OCPP消息处理服务
try:
    from app.services.ocpp_message_handler import ocpp_message_handler
    from app.services.charge_point_service import ChargePointService
    from app.core.mqtt_auth import MQTTAuthService
    OCPP_SERVICE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"OCPP服务不可用: {e}")
    OCPP_SERVICE_AVAILABLE = False


# ---- 生命周期管理 ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理，初始化多种传输方式（MQTT、HTTP、WebSocket）"""
    # 启动时
    # 初始化数据库
    if DATABASE_AVAILABLE:
        try:
            # 等待数据库就绪（最多重试5次，每次等待3秒）
            if check_db_health(max_retries=5, retry_delay=3.0):
                init_db()
                logger.info("数据库表已初始化")
            else:
                logger.error("数据库连接失败，跳过表初始化。请检查数据库配置和连接。")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}", exc_info=True)
    
    if MQTT_AVAILABLE:
        try:
            settings = get_settings()
            
            # 准备启用的传输方式列表
            enabled_transports = []
            
            # 检查并配置 MQTT
            if settings.enable_mqtt_transport:
                enabled_transports.append(TransportType.MQTT)
                # 在 Docker 容器中，优先使用环境变量，否则使用 mqtt-broker（Docker 服务名）
                mqtt_host = os.getenv("MQTT_BROKER_HOST")
                if not mqtt_host:
                    # 检查是否在 Docker 网络中（通过检查是否能解析 mqtt-broker）
                    try:
                        import socket
                        socket.gethostbyname("mqtt-broker")
                        mqtt_host = "mqtt-broker"
                        logger.info("检测到 Docker 网络，使用 mqtt-broker 作为 MQTT broker 地址")
                    except:
                        mqtt_host = settings.mqtt_broker_host or "localhost"
                
                # 如果检测到 Docker 网络，临时修改配置
                if mqtt_host != settings.mqtt_broker_host:
                    # 直接修改 settings 对象（因为它是单例）
                    settings.mqtt_broker_host = mqtt_host
            
            # 检查并配置 HTTP（可通过环境变量 ENABLE_HTTP_TRANSPORT 启用）
            # 环境变量优先级高于配置文件
            enable_http = os.getenv("ENABLE_HTTP_TRANSPORT", "").lower() in ("true", "1", "yes")
            if enable_http or settings.enable_http_transport:
                enabled_transports.append(TransportType.HTTP)
                logger.info("HTTP 传输已启用（通过环境变量或配置）")
            
            # 检查并配置 WebSocket（可通过环境变量 ENABLE_WEBSOCKET_TRANSPORT 启用）
            # 环境变量优先级高于配置文件
            enable_ws = os.getenv("ENABLE_WEBSOCKET_TRANSPORT", "").lower() in ("true", "1", "yes")
            if enable_ws or settings.enable_websocket_transport:
                enabled_transports.append(TransportType.WEBSOCKET)
                logger.info("WebSocket 传输已启用（通过环境变量或配置）")
            
            # 初始化传输管理器
            if enabled_transports:
                # 先初始化传输管理器
                await transport_manager.initialize(enabled_transports)
                # 然后设置消息处理器（确保所有适配器都已创建）
                transport_manager.set_message_handler(handle_ocpp_message)
                logger.info(f"传输管理器已初始化，启用了 {len(enabled_transports)} 种传输方式: {[t.value for t in enabled_transports]}")
                # 验证消息处理器已设置
                for transport_type, adapter in transport_manager.adapters.items():
                    if adapter.message_handler:
                        logger.info(f"{transport_type.value} 适配器消息处理器已设置")
                    else:
                        logger.warning(f"{transport_type.value} 适配器消息处理器未设置")
        except Exception as e:
            logger.error(f"传输管理器初始化失败: {e}", exc_info=True)
            # 不阻止应用启动，只是某些传输方式不可用
    
    # 初始化 Redis 离线检测
    try:
        # 配置 Redis keyspace notifications
        await setup_redis_keyspace_notifications()
        
        # 启动后台任务监听离线事件
        offline_listener_task = asyncio.create_task(listen_charger_offline_events())
        logger.info("充电桩离线检测监听器已启动（基于 Redis 过期键事件）")
    except Exception as e:
        logger.error(f"初始化 Redis 离线检测失败: {e}", exc_info=True)
        # 不阻止应用启动，但离线检测功能不可用
    
    yield
    
    # 关闭时
    if MQTT_AVAILABLE:
        try:
            await transport_manager.shutdown()
            logger.info("传输管理器已关闭")
        except Exception as e:
            logger.error(f"关闭传输管理器时出错: {e}", exc_info=True)


# ---- App & CORS ----
app = FastAPI(
    title="Local OCPP 1.6J CSMS",
    lifespan=lifespan
)

# 添加请求日志中间件
try:
    from app.core.middleware import LoggingMiddleware
    app.add_middleware(LoggingMiddleware)
    logger.info("请求日志中间件已启用")
except ImportError:
    logger.warning("无法导入日志中间件，跳过")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Redis Client ----
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client: redis.Redis = redis.from_url(REDIS_URL, decode_responses=True)

CHARGERS_HASH_KEY = "chargers"
MESSAGES_LIST_KEY = "messages"  # Redis list for messages
ORDERS_HASH_KEY = "orders"  # Redis hash for charging orders

# Redis 离线检测配置
CHARGER_ONLINE_KEY_PREFIX = "charger:"  # charger:{id}:online
CHARGER_OFFLINE_TIMEOUT = 90  # 90 秒后自动过期

# ---- WebSocket connection registry ----
charger_websockets: Dict[str, WebSocket] = {}


# ---- 统一的 OCPP 消息处理函数（供 MQTT 和 WebSocket 使用）----
async def handle_ocpp_message(charge_point_id: str, action: str, payload: Dict[str, Any], device_serial_number: Optional[str] = None, evse_id: int = 1) -> Dict[str, Any]:
    """统一的 OCPP 消息处理函数（使用新表结构）"""
    if OCPP_SERVICE_AVAILABLE:
        # 使用新的服务层处理
        return await ocpp_message_handler.handle_message(
            charge_point_id=charge_point_id,
            action=action,
            payload=payload,
            device_serial_number=device_serial_number,
            evse_id=evse_id
        )
    else:
        # 降级到旧逻辑（如果服务不可用）
        logger.warning("OCPP服务不可用，使用降级处理")
        return {"error": "Service unavailable"}


# ---- Helper function to send OCPP messages from CSMS to Charge Point ----
async def send_ocpp_call(charge_point_id: str, action: str, payload: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
    """
    发送OCPP调用从CSMS到充电桩，并等待响应。
    优先使用 MQTT 传输，如果没有 MQTT 连接则使用 WebSocket。
    返回响应数据或错误信息。
    """
    # 优先使用 MQTT 传输
    if MQTT_AVAILABLE and hasattr(transport_manager, 'adapters'):
        # 检查 transport_manager 是否已初始化（adapters不为空）
        adapters_count = len(transport_manager.adapters) if transport_manager.adapters else 0
        logger.info(f"[{charge_point_id}] send_ocpp_call检查: adapters={adapters_count}, adapters_keys={list(transport_manager.adapters.keys()) if transport_manager.adapters else []}")
        if adapters_count > 0:
            is_conn = transport_manager.is_connected(charge_point_id)
            logger.info(f"[{charge_point_id}] send_ocpp_call检查: is_connected={is_conn}")
            # 如果是MQTT适配器，检查_connected_chargers
            mqtt_adapter = transport_manager.adapters.get(TransportType.MQTT)
            if mqtt_adapter and hasattr(mqtt_adapter, '_connected_chargers'):
                logger.info(f"[{charge_point_id}] MQTT _connected_chargers: {list(mqtt_adapter._connected_chargers)}")
            if is_conn:
                try:
                    logger.info(f"[{charge_point_id}] 通过 MQTT 发送 OCPP 调用: {action}")
                    result = await transport_manager.send_message(
                        charge_point_id,
                        action,
                        payload,
                        preferred_transport=TransportType.MQTT,
                        timeout=timeout
                    )
                    logger.info(f"[{charge_point_id}] MQTT OCPP 调用完成: {action}, 结果: {result}")
                    return {"success": True, "data": result, "transport": "MQTT"}
                except Exception as e:
                    logger.error(f"[{charge_point_id}] 通过 MQTT 发送 OCPP 调用失败: {e}", exc_info=True)
                    # 如果 MQTT 失败，尝试 WebSocket（如果有）
    
    # Fallback: 使用 WebSocket（如果可用）
    ws = charger_websockets.get(charge_point_id)
    if ws:
        try:
            message = {
                "action": action,
                "payload": payload
            }
            await ws.send_text(json.dumps(message))
            logger.info(f"[{charge_point_id}] -> CSMS发送OCPP调用 (WebSocket): {action}")
            
            # 等待响应（简化版本，实际应该使用消息ID匹配）
            try:
                response = await asyncio.wait_for(ws.receive_text(), timeout=timeout)
                response_data = json.loads(response)
                logger.info(f"[{charge_point_id}] <- 收到响应 (WebSocket): {action}")
                return {"success": True, "data": response_data, "transport": "WebSocket"}
            except asyncio.TimeoutError:
                logger.warning(f"[{charge_point_id}] OCPP调用超时 (WebSocket): {action}")
                return {"success": False, "error": "Timeout waiting for response"}
        except Exception as e:
            logger.error(f"[{charge_point_id}] 发送OCPP调用失败 (WebSocket): {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to send OCPP call: {str(e)}")
    
    # 如果都没有连接，抛出错误
    logger.warning(f"[{charge_point_id}] 发送OCPP调用失败: 设备未连接 (transport_manager可用: {MQTT_AVAILABLE}, adapters: {len(transport_manager.adapters) if MQTT_AVAILABLE and hasattr(transport_manager, 'adapters') else 0})")
    raise HTTPException(status_code=404, detail=f"Charger {charge_point_id} is not connected (MQTT or WebSocket)")


def now_iso() -> str:
    """获取当前ISO格式时间（使用Z后缀）"""
    # 版本标识：使用 Z 后缀格式
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def get_default_charger(charger_id: str) -> Dict[str, Any]:
    """创建默认充电桩数据结构"""
    charger = {
        "id": charger_id,
        "vendor": None,
        "model": None,
        "firmware_version": None,
        "serial_number": None,
        "physical_status": "Unknown",  # 物理状态：只允许 OCPP 更新
        "operational_status": "ENABLED",  # 运营状态：ENABLED / MAINTENANCE / DISABLED
        "last_seen": now_iso(),
        "location": {
            "latitude": None,
            "longitude": None,
            "address": "",
        },
        "session": {
            "authorized": False,
            "transaction_id": None,
            "meter": 0,
        },
        "connector_type": "Type2",  # 充电头类型: GBT, Type1, Type2, CCS1, CCS2
        "charging_rate": 7.0,  # 充电速率 (kW)
        "price_per_kwh": 2700.0,  # 每度电价格 (COP/kWh)
    }
    # 计算字段：是否真正可用
    charger["is_available"] = (charger["physical_status"] == "Available" and charger["operational_status"] == "ENABLED")
    return charger


def calculate_is_available(charger: Dict[str, Any]) -> bool:
    """计算充电桩是否真正可用"""
    physical_status = charger.get("physical_status", "Unknown")
    operational_status = charger.get("operational_status", "ENABLED")
    return (physical_status == "Available" and operational_status == "ENABLED")


def migrate_charger_data(charger: Dict[str, Any]) -> Dict[str, Any]:
    """补充缺失的新字段，并修复数据不一致问题"""
    # 确保新字段存在
    if "physical_status" not in charger:
        charger["physical_status"] = "Unknown"
    if "operational_status" not in charger:
        charger["operational_status"] = "ENABLED"
    
    # 如果缺少 connector_type，尝试从数据库获取（从 EVSE 表）
    if "connector_type" not in charger or not charger.get("connector_type"):
        charger_id = charger.get("id")
        if charger_id and DATABASE_AVAILABLE:
            try:
                from app.database.models import EVSE
                db = SessionLocal()
                try:
                    default_evse = db.query(EVSE).filter(
                        EVSE.charge_point_id == charger_id,
                        EVSE.evse_id == 1
                    ).first()
                    if default_evse:
                        charger["connector_type"] = default_evse.connector_type
                    else:
                        charger["connector_type"] = "Type2"  # 默认值
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"从数据库获取 connector_type 失败: {e}，使用默认值")
                charger["connector_type"] = "Type2"
        else:
            charger["connector_type"] = "Type2"  # 默认值
    if "charging_rate" not in charger:
        charger["charging_rate"] = 7.0
    if "price_per_kwh" not in charger:
        charger["price_per_kwh"] = 2700.0
    
    # 确保session中有order_id字段（如果不存在）
    if "session" in charger:
        if "order_id" not in charger["session"]:
            charger["session"]["order_id"] = None
        
        # 修复：如果物理状态是 Available 但 transaction_id 不为 null，清理 transaction_id
        # 注意：这里使用 physical_status 而不是 status
        if charger.get("physical_status") == "Available" and charger["session"].get("transaction_id") is not None:
            logger.info(f"[{charger.get('id')}] Auto-fixing: clearing stale transaction_id for Available charger")
            charger["session"]["transaction_id"] = None
            charger["session"]["order_id"] = None
    
    # 计算 is_available
    charger["is_available"] = calculate_is_available(charger)
    
    return charger


def load_chargers() -> List[Dict[str, Any]]:
    """加载所有充电桩数据，不自动判断离线状态（由充电桩自身通过 OCPP 更新）"""
    items = redis_client.hgetall(CHARGERS_HASH_KEY)
    chargers: List[Dict[str, Any]] = []
    
    for _, val in items.items():
        try:
            charger = json.loads(val)
            # 迁移旧数据，补充缺失字段
            charger = migrate_charger_data(charger)
            
            # 计算 is_available（每次加载时重新计算，确保准确性）
            charger["is_available"] = calculate_is_available(charger)
            chargers.append(charger)
        except Exception as e:
            logger.error(f"加载充电桩数据失败: {e}", exc_info=True)
            continue
    return chargers


def save_charger(charger: Dict[str, Any]) -> None:
    """保存充电桩数据到Redis，带错误处理"""
    # 确保 is_available 字段是最新的
    charger["is_available"] = calculate_is_available(charger)
    
    try:
        redis_client.hset(CHARGERS_HASH_KEY, charger["id"], json.dumps(charger))
    except redis.exceptions.ResponseError as e:
        # Redis配置错误（如MISCONF），记录但不中断流程
        logger.error(f"Redis配置错误，无法保存充电桩 {charger['id']}: {e}")
        logger.warning(f"充电桩数据未保存到Redis，但连接继续: {charger['id']}")
    except Exception as e:
        # 其他Redis错误，记录但不中断流程
        logger.error(f"Redis错误，无法保存充电桩 {charger['id']}: {e}", exc_info=True)
        logger.warning(f"充电桩数据未保存到Redis，但连接继续: {charger['id']}")
    
    # 同步到数据库
    if DATABASE_AVAILABLE:
        try:
            sync_charger_to_db(charger)
        except Exception as e:
            logger.error(f"同步充电桩 {charger['id']} 到数据库失败: {e}", exc_info=True)


def sync_charger_to_db(charger: Dict[str, Any]) -> None:
    """
    将充电桩数据同步到数据库（兼容层）
    注意：此函数保留用于向后兼容，新代码应直接使用ChargePointService
    """
    if not DATABASE_AVAILABLE:
        return
    
    try:
        from app.database.models import ChargePoint, Site, EVSEStatus
        db = SessionLocal()
        try:
            charge_point_id = charger["id"]
            # 查找或创建充电桩记录
            charge_point = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
            
            if not charge_point:
                # 使用ChargePointService创建
                ChargePointService.get_or_create_charge_point(
                    db=db,
                    charge_point_id=charge_point_id,
                    vendor=charger.get("vendor"),
                    model=charger.get("model"),
                    serial_number=charger.get("serial_number"),
                    firmware_version=charger.get("firmware_version")
                )
                db.flush()
                charge_point = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
            
            # 更新字段
            if "vendor" in charger:
                charge_point.vendor = charger.get("vendor")
            if "model" in charger:
                charge_point.model = charger.get("model")
            if "firmware_version" in charger:
                charge_point.firmware_version = charger.get("firmware_version")
            if "serial_number" in charger:
                charge_point.serial_number = charger.get("serial_number")
            
            # 更新位置信息（通过站点）
            if "location" in charger:
                loc = charger["location"]
                if isinstance(loc, dict) and (loc.get("latitude") or loc.get("longitude")):
                    site = charge_point.site if charge_point.site_id else None
                    if not site:
                        # 创建新站点
                        site = Site(
                            id=f"site-{charge_point_id}",
                            name=f"站点-{charge_point_id}",
                            address=loc.get("address", ""),
                            latitude=loc.get("latitude", 0.0),
                            longitude=loc.get("longitude", 0.0)
                        )
                        db.add(site)
                        db.flush()
                        charge_point.site_id = site.id
                    else:
                        site.latitude = loc.get("latitude")
                        site.longitude = loc.get("longitude")
                        if loc.get("address"):
                            site.address = loc.get("address")
            
            # 更新EVSE状态
            if "physical_status" in charger:
                evse_status = db.query(EVSEStatus).filter(
                    EVSEStatus.charge_point_id == charge_point_id
                ).first()
                if evse_status:
                    evse_status.status = charger.get("physical_status", "Unknown")
            if "last_seen" in charger:
                try:
                            evse_status.last_seen = datetime.fromisoformat(charger["last_seen"].replace("Z", "+00:00"))
                except:
                            evse_status.last_seen = datetime.now(timezone.utc)
            
            # 更新定价（通过站点和Tariff）
            if "price_per_kwh" in charger and charge_point.site_id:
                from app.database.models import Tariff
                tariff = db.query(Tariff).filter(
                    Tariff.site_id == charge_point.site_id,
                    Tariff.is_active == True
                ).first()
                if not tariff:
                    tariff = Tariff(
                        site_id=charge_point.site_id,
                        name="默认定价",
                        base_price_per_kwh=charger.get("price_per_kwh", 2700.0),
                        service_fee=0,
                        valid_from=datetime.now(timezone.utc),
                        is_active=True
                    )
                    db.add(tariff)
                else:
                    tariff.base_price_per_kwh = charger.get("price_per_kwh", 2700.0)
                db_charger.price_per_kwh = charger.get("price_per_kwh", 2700.0)
            
            db_charger.is_active = True
            db_charger.updated_at = datetime.now(tz.utc)
            
            db.commit()
        except Exception as e:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.error(f"同步充电桩 {charger.get('id', 'unknown')} 到数据库失败: {e}", exc_info=True)


# ---- Order Management ----
def create_order(
    order_id: str,
    charge_point_id: str,
    user_id: str,
    id_tag: str,
    charging_rate: float,
    start_time: str,
) -> Dict[str, Any]:
    """创建充电订单"""
    order = {
        "id": order_id,
        "charge_point_id": charge_point_id,
        "user_id": user_id,
        "id_tag": id_tag,
        "charging_rate": charging_rate,
        "start_time": start_time,
        "end_time": None,
        "duration_minutes": None,
        "energy_kwh": None,
        "status": "ongoing",  # ongoing, completed, cancelled
    }
    redis_client.hset(ORDERS_HASH_KEY, order_id, json.dumps(order))
    logger.info(f"Order created: {order_id} for charger {charger_id}")
    return order


def update_order(
    order_id: str,
    end_time: str,
    duration_minutes: float,
    energy_kwh: float,
) -> None:
    """更新订单（结束充电时）"""
    order_data = redis_client.hget(ORDERS_HASH_KEY, order_id)
    if not order_data:
        logger.warning(f"Order not found: {order_id}")
        return
    
    order = json.loads(order_data)
    order["end_time"] = end_time
    order["duration_minutes"] = duration_minutes
    order["energy_kwh"] = energy_kwh
    order["status"] = "completed"
    
    redis_client.hset(ORDERS_HASH_KEY, order_id, json.dumps(order))
    logger.info(f"Order updated: {order_id}, energy: {energy_kwh} kWh, duration: {duration_minutes} min")


def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    """获取单个订单"""
    order_data = redis_client.hget(ORDERS_HASH_KEY, order_id)
    if not order_data:
        return None
    return json.loads(order_data)


def get_orders_by_user(user_id: str) -> List[Dict[str, Any]]:
    """获取用户的所有订单"""
    items = redis_client.hgetall(ORDERS_HASH_KEY)
    orders = []
    for _, val in items.items():
        try:
            order = json.loads(val)
            if order.get("user_id") == user_id:
                orders.append(order)
        except Exception:
            continue
    # 按开始时间倒序排列（最新的在前）
    orders.sort(key=lambda x: x.get("start_time", ""), reverse=True)
    return orders


def get_all_orders() -> List[Dict[str, Any]]:
    """获取所有订单"""
    items = redis_client.hgetall(ORDERS_HASH_KEY)
    orders = []
    for _, val in items.items():
        try:
            orders.append(json.loads(val))
        except Exception:
            continue
    # 按开始时间倒序排列（最新的在前）
    orders.sort(key=lambda x: x.get("start_time", ""), reverse=True)
    return orders


# ---- In-memory active chargers (for quick inspection) ----
active_chargers: Dict[str, Dict[str, Any]] = {}


# ---- Redis 离线检测（基于过期键的事件驱动方案）----
def set_charger_online(charge_point_id: str) -> None:
    """
    设置充电桩在线标记（使用 Redis SETEX，90秒后自动过期）
    每次收到心跳时调用此函数，刷新过期时间
    注意：参数名已更新为charge_point_id
    """
    try:
        online_key = f"{CHARGER_ONLINE_KEY_PREFIX}{charge_point_id}:online"
        redis_client.setex(online_key, CHARGER_OFFLINE_TIMEOUT, "true")
        logger.debug(f"[{charge_point_id}] 已设置在线标记，{CHARGER_OFFLINE_TIMEOUT}秒后自动过期")
    except Exception as e:
        logger.error(f"[{charge_point_id}] 设置在线标记失败: {e}", exc_info=True)


def handle_charger_offline(charge_point_id: str) -> None:
    """
    处理充电桩离线事件（当 Redis key 过期时触发）
    更新充电桩状态为离线 - 使用新表结构
    """
    try:
        if DATABASE_AVAILABLE:
            from app.database.models import EVSEStatus, ChargingSession
            db = SessionLocal()
            try:
                # 获取所有EVSE状态
                evse_statuses = db.query(EVSEStatus).filter(
                    EVSEStatus.charge_point_id == charge_point_id
                ).all()
                
                for evse_status in evse_statuses:
                    current_status = evse_status.status
                    
                    # 只有在非离线状态时才更新为离线
                    # 注意：如果充电桩正在充电，不应该因为心跳超时而标记为离线
                    if current_status not in ["Charging", "Unavailable"]:
                        # 检查是否有活跃会话
                        if evse_status.current_session_id:
                            session = db.query(ChargingSession).filter(
                                ChargingSession.id == evse_status.current_session_id
                            ).first()
                            if session and session.status == "ongoing":
                                # 有活跃会话，不更新为离线
                                logger.debug(
                                    f"[{charge_point_id}] 充电桩离线检测：有活跃会话，跳过更新"
                                )
                                continue
                        
                        evse_status.status = "Unavailable"
                        evse_status.last_seen = datetime.now(timezone.utc)
                        db.commit()
                        logger.info(
                            f"[{charge_point_id}] 充电桩离线检测：EVSE状态已更新为 Unavailable"
                        )
                    else:
                        logger.debug(
                            f"[{charge_point_id}] 充电桩离线检测：当前状态为 {current_status}，跳过更新"
                        )
            except Exception as e:
                logger.error(f"[{charge_point_id}] 充电桩离线检测处理错误: {e}", exc_info=True)
                db.rollback()
            finally:
                db.close()
        else:
            # 降级到Redis逻辑
            charger = next((c for c in load_chargers() if c["id"] == charge_point_id), None)
            if charger is None:
                charger = get_default_charger(charge_point_id)
            
            current_physical_status = charger.get("physical_status", "Unknown")
            if current_physical_status not in ["Charging", "Unavailable"]:
                charger["physical_status"] = "Unavailable"
                charger["last_seen"] = now_iso()
                charger["is_available"] = calculate_is_available(charger)
                save_charger(charger)
                logger.info(f"[{charge_point_id}] 充电桩离线检测：物理状态已更新为 Unavailable")
    except Exception as e:
        logger.error(f"[{charge_point_id}] 处理充电桩离线事件失败: {e}", exc_info=True)


async def setup_redis_keyspace_notifications() -> None:
    """
    配置 Redis keyspace notifications，启用过期事件通知
    需要 Redis 配置：notify-keyspace-events Ex
    """
    try:
        # 配置 Redis 启用过期事件通知
        # 使用 CONFIG SET 命令（如果 Redis 允许）
        try:
            redis_client.config_set("notify-keyspace-events", "Ex")
            logger.info("Redis keyspace notifications 已启用（过期事件）")
        except redis.exceptions.ResponseError as e:
            # 如果配置失败，可能是 Redis 配置文件中已设置或权限不足
            logger.warning(f"无法通过 CONFIG SET 启用 keyspace notifications: {e}")
            logger.info("请确保 Redis 配置文件中包含: notify-keyspace-events Ex")
    except Exception as e:
        logger.error(f"配置 Redis keyspace notifications 失败: {e}", exc_info=True)


async def listen_charger_offline_events() -> None:
    """
    监听 Redis 过期事件，当充电桩在线标记过期时，触发离线处理
    使用 Redis PUB/SUB 机制监听 __keyspace@0__:charger:*:online 的 expired 事件
    使用非阻塞方式避免阻塞事件循环
    """
    while True:
        try:
            # 创建专用的 Redis 客户端用于订阅（不能使用 decode_responses=True）
            pubsub_client = redis.from_url(REDIS_URL, decode_responses=False)
            pubsub = pubsub_client.pubsub()
            
            # 订阅过期事件
            # Redis 会在 key 过期时发布消息到 __keyspace@0__:{key} 频道，事件类型为 "expired"
            pattern = f"__keyspace@0__:{CHARGER_ONLINE_KEY_PREFIX}*:online"
            pubsub.psubscribe(pattern)
            
            logger.info(f"开始监听充电桩离线事件，模式: {pattern}")
            
            # 使用非阻塞方式监听，避免阻塞事件循环
            while True:
                try:
                    # 使用 get_message() 非阻塞方式获取消息，超时时间 1 秒
                    message = pubsub.get_message(timeout=1.0, ignore_subscribe_messages=True)
                    
                    if message is None:
                        # 没有消息，继续循环（让出控制权给事件循环）
                        await asyncio.sleep(0.1)
                        continue
                    
                    if message["type"] == "pmessage":
                        # 消息格式：
                        # channel: __keyspace@0__:charger:{id}:online
                        # data: expired
                        channel = message["channel"].decode("utf-8") if isinstance(message["channel"], bytes) else message["channel"]
                        data = message["data"].decode("utf-8") if isinstance(message["data"], bytes) else message["data"]
                        
                        if data == "expired":
                            # 从 channel 中提取充电桩 ID
                            # channel 格式: __keyspace@0__:charger:{id}:online
                            parts = channel.split(":")
                            if len(parts) >= 3:
                                # 找到 "charger" 的位置
                                try:
                                    charger_idx = parts.index("charger")
                                    if charger_idx + 1 < len(parts):
                                        charge_point_id = parts[charger_idx + 1]
                                        logger.info(f"[Redis事件] 检测到充电桩离线: {charge_point_id}")
                                        # 在后台线程中处理离线事件（避免阻塞监听循环）
                                        await asyncio.to_thread(handle_charger_offline, charge_point_id)
                                except ValueError:
                                    logger.warning(f"无法从 channel {channel} 中提取充电桩 ID")
                except Exception as e:
                    logger.error(f"处理 Redis 过期事件失败: {e}", exc_info=True)
                    # 继续监听，不中断
                    await asyncio.sleep(1)
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Redis 连接失败: {e}，5秒后重试...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"监听充电桩离线事件失败: {e}", exc_info=True)
            # 如果监听失败，等待后重试
            await asyncio.sleep(5)
            logger.info("尝试重新连接 Redis 订阅...")


def update_active(
    charger_id: str,
    *,
    vendor: Optional[str] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    txn_id: Optional[Union[int, str]] = None,
) -> None:
    rec = active_chargers.get(charger_id)
    if rec is None:
        rec = {
            "id": charger_id,
            "vendor": None,
            "model": None,
            "status": "Unknown",
            "last_seen": now_iso(),
            "txn_id": None,
        }
        active_chargers[charger_id] = rec
    if vendor is not None:
        rec["vendor"] = vendor
    if model is not None:
        rec["model"] = model
    if status is not None:
        rec["status"] = status
        # 修复：如果状态变为 Available，自动清理 transaction_id（防止数据不一致）
        if status == "Available" and (txn_id is None or txn_id == ""):
            # 从 Redis 加载充电桩数据并清理 transaction_id
            charger = next((c for c in load_chargers() if c["id"] == charger_id), None)
            if charger:
                session = charger.setdefault("session", {
                    "authorized": False,
                    "transaction_id": None,
                    "meter": 0,
                })
                if session.get("transaction_id") is not None:
                    session["transaction_id"] = None
                    session["order_id"] = None
                    save_charger(charger)
                    logger.info(f"[{charger_id}] Auto-cleared stale transaction_id when status became Available")
    if txn_id is not None or txn_id is None:
        rec["txn_id"] = txn_id
    rec["last_seen"] = now_iso()


class HealthResponse(BaseModel):
    ok: bool
    ts: str


class RemoteStartRequest(BaseModel):
    chargePointId: str
    idTag: str


class RemoteStopRequest(BaseModel):
    chargePointId: str


class RemoteResponse(BaseModel):
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class UpdateLocationRequest(BaseModel):
    chargePointId: str
    latitude: float
    longitude: float
    address: str = ""


class UpdatePriceRequest(BaseModel):
    chargePointId: str
    pricePerKwh: float  # 每度电价格 (COP/kWh)


class CreateMessageRequest(BaseModel):
    userId: str
    username: str
    message: str


class ReplyMessageRequest(BaseModel):
    messageId: str
    reply: str


class GetOrdersRequest(BaseModel):
    userId: Optional[str] = None  # 如果提供，只返回该用户的订单；否则返回所有订单


class GetConfigurationRequest(BaseModel):
    chargePointId: str
    keys: Optional[List[str]] = None  # 如果为空，获取所有配置


class ChangeConfigurationRequest(BaseModel):
    chargePointId: str
    key: str
    value: str


class ResetRequest(BaseModel):
    chargePointId: str
    type: str = "Soft"  # Soft or Hard


class UnlockConnectorRequest(BaseModel):
    chargePointId: str
    connectorId: int


class ChangeAvailabilityRequest(BaseModel):
    chargePointId: str
    connectorId: int
    type: str  # Inoperative or Operative

class SetMaintenanceRequest(BaseModel):
    chargePointId: str
    maintenance: bool  # True: 设置为维修状态, False: 取消维修状态


class SetChargingProfileRequest(BaseModel):
    chargePointId: str
    connectorId: int
    csChargingProfiles: Dict[str, Any]


class ClearChargingProfileRequest(BaseModel):
    chargePointId: str
    id: Optional[int] = None
    connectorId: Optional[int] = None
    chargingProfilePurpose: Optional[str] = None
    stackLevel: Optional[int] = None


class GetDiagnosticsRequest(BaseModel):
    chargePointId: str
    location: str
    retries: Optional[int] = None
    retryInterval: Optional[int] = None
    startTime: Optional[str] = None
    stopTime: Optional[str] = None


class ExportLogsRequest(BaseModel):
    chargePointId: str
    location: str = ""  # 可选，用于GetDiagnostics
    retries: Optional[int] = None
    retryInterval: Optional[int] = None
    startTime: Optional[str] = None
    stopTime: Optional[str] = None
    userRole: Optional[str] = None  # 用户角色，用于权限验证


class UpdateFirmwareRequest(BaseModel):
    chargePointId: str
    location: str
    retrieveDate: str
    retryInterval: Optional[int] = None
    retries: Optional[int] = None


class ReserveNowRequest(BaseModel):
    chargePointId: str
    connectorId: int
    expiryDate: str
    idTag: str
    reservationId: int
    parentIdTag: Optional[str] = None


class CancelReservationRequest(BaseModel):
    chargePointId: str
    reservationId: int


@app.get("/health", response_model=HealthResponse, tags=["REST"])
def health() -> HealthResponse:
    """
    Health check endpoint.
    Returns: {"ok": true, "ts": "ISO timestamp"}
    """
    logger.debug("[API] GET /health | 健康检查")
    return HealthResponse(ok=True, ts=now_iso())


@app.get("/api/ocpp/supported", tags=["REST"])
def get_supported_ocpp_features() -> Dict[str, Any]:
    """
    获取当前CSMS实现支持的OCPP功能列表。
    用于检测实体充电桩时了解CSMS的能力。
    """
    return {
        "ocpp_version": "1.6J",
        "chargePoint_to_csms": {
            "supported": [
                "BootNotification",
                "Heartbeat",
                "StatusNotification",
                "Authorize",
                "StartTransaction",
                "StopTransaction",
                "MeterValues",
                "FirmwareStatusNotification",
                "DiagnosticsStatusNotification",
                "DataTransfer"
            ],
            "required_messages": 7,
            "supported_count": 10,
            "status": "all_required_supported",
            "note": "包含所有必需消息和部分可选消息"
        },
        "csms_to_chargePoint": {
            "supported": [
                "RemoteStartTransaction",
                "RemoteStopTransaction",
                "GetConfiguration",
                "ChangeConfiguration",
                "Reset",
                "UnlockConnector",
                "ChangeAvailability",
                "SetChargingProfile",
                "ClearChargingProfile",
                "GetDiagnostics",
                "UpdateFirmware",
                "ReserveNow",
                "CancelReservation"
            ],
            "required_messages": 2,
            "supported_count": 13,
            "status": "all_required_supported",
            "note": "所有功能通过REST API实现"
        },
        "api_endpoints": {
            "chargePoint_to_csms": "WebSocket: /ocpp",
            "csms_to_chargePoint": [
                "POST /api/remoteStart",
                "POST /api/remoteStop",
                "POST /api/getConfiguration",
                "POST /api/changeConfiguration",
                "POST /api/reset",
                "POST /api/unlockConnector",
                "POST /api/changeAvailability",
                "POST /api/setChargingProfile",
                "POST /api/clearChargingProfile",
                "POST /api/getDiagnostics",
                "POST /api/updateFirmware",
                "POST /api/reserveNow",
                "POST /api/cancelReservation"
            ]
        },
        "validation_tool": {
            "available": True,
            "path": "csms/app/ocpp_validator.py",
            "description": "使用 ocpp_validator.py 工具检测实体充电桩"
        }
    }


@app.get("/chargers", tags=["REST"])
def chargers_list() -> List[Dict[str, Any]]:
    """
    List all chargers - 使用新表结构
    Returns: [{"id": str, "status": str, "last_seen": str, ...}, ...]
    """
    logger.info("[API] GET /chargers | 获取所有充电桩列表")
    
    if not DATABASE_AVAILABLE:
        # 降级到Redis
        chargers = load_chargers()
        logger.info(f"[API] GET /chargers 成功 | 返回 {len(chargers)} 个充电桩（Redis）")
        return chargers
    
    try:
        from app.database.models import ChargePoint, EVSEStatus, Site, Tariff
        db = SessionLocal()
        try:
            charge_points = db.query(ChargePoint).all()
            result = []
            
            for cp in charge_points:
                # 获取EVSE状态
                evse_status = db.query(EVSEStatus).filter(
                    EVSEStatus.charge_point_id == cp.id
                ).first()
                status = evse_status.status if evse_status else "Unknown"
                last_seen = evse_status.last_seen if evse_status else None
                
                # 获取站点信息
                site = cp.site if cp.site_id else None
                
                # 获取定价
                tariff = db.query(Tariff).filter(
                    Tariff.site_id == cp.site_id,
                    Tariff.is_active == True
                ).first() if cp.site_id else None
                
                # 获取默认 EVSE 的 connector_type
                from app.database.models import EVSE
                default_evse = db.query(EVSE).filter(
                    EVSE.charge_point_id == cp.id,
                    EVSE.evse_id == 1
                ).first()
                connector_type = default_evse.connector_type if default_evse else "Type2"
                
                result.append({
                    "id": cp.id,
                    "vendor": cp.vendor,
                    "model": cp.model,
                    "connector_type": connector_type,  # 从 EVSE 获取
                    "status": status,
                    "last_seen": last_seen.isoformat() if last_seen else None,
                    "location": {
                        "latitude": site.latitude if site else None,
                        "longitude": site.longitude if site else None,
                        "address": site.address if site else None,
                    },
                    "price_per_kwh": tariff.base_price_per_kwh if tariff else None,
                })
            
            logger.info(f"[API] GET /chargers 成功 | 返回 {len(result)} 个充电桩（数据库）")
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error(f"获取充电桩列表失败: {e}", exc_info=True)
        # 降级到Redis
        chargers = load_chargers()
    return chargers


@app.post("/api/updateLocation", response_model=RemoteResponse, tags=["REST"])
async def update_location(req: UpdateLocationRequest) -> RemoteResponse:
    """
    Update charger location (latitude, longitude, address) - 使用新表结构
    """
    logger.info(
        f"[API] POST /api/updateLocation | "
        f"充电桩ID: {req.chargePointId} | "
        f"位置: ({req.latitude}, {req.longitude}) | "
        f"地址: {req.address or '无'}"
    )
    
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    try:
        from app.database.models import ChargePoint, Site
        db = SessionLocal()
        try:
            charge_point = db.query(ChargePoint).filter(ChargePoint.id == req.chargePointId).first()
            
            if not charge_point:
                # 创建充电桩
                charge_point = ChargePointService.get_or_create_charge_point(
                    db=db,
                    charge_point_id=req.chargePointId
                )
            
            # 更新或创建站点
            site = charge_point.site if charge_point.site_id else None
            if not site:
                site = Site(
                    id=generate_site_id(f"站点-{req.chargePointId}"),
                    name=f"站点-{req.chargePointId}",
                    address=req.address or "",
                    latitude=req.latitude,
                    longitude=req.longitude
                )
                db.add(site)
                db.flush()
                charge_point.site_id = site.id
            else:
                site.latitude = req.latitude
                site.longitude = req.longitude
                if req.address:
                    site.address = req.address
            
            db.commit()
            
            logger.info(
                f"[API] POST /api/updateLocation 成功 | "
                f"充电桩ID: {req.chargePointId} | "
                f"位置: ({req.latitude}, {req.longitude})"
            )
        except Exception as e:
            db.rollback()
            logger.error(f"[API] POST /api/updateLocation 失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"更新位置失败: {str(e)}")
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] POST /api/updateLocation 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新位置失败: {str(e)}")
    
    return RemoteResponse(
        success=True,
        message="Location updated successfully",
        details={
            "chargePointId": req.chargePointId,
            "location": {
                "latitude": req.latitude,
                "longitude": req.longitude,
                "address": req.address
            }
        },
    )


@app.post("/api/updatePrice", response_model=RemoteResponse, tags=["REST"])
async def update_price(req: UpdatePriceRequest) -> RemoteResponse:
    """
    Update charger price per kWh - 使用新表结构
    """
    logger.info(
        f"[API] POST /api/updatePrice | "
        f"充电桩ID: {req.chargePointId} | "
        f"价格: {req.pricePerKwh} COP/kWh"
    )
    
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="数据库不可用")
    
    try:
        from app.database.models import ChargePoint, Tariff
        db = SessionLocal()
        try:
            charge_point = db.query(ChargePoint).filter(ChargePoint.id == req.chargePointId).first()
            
            if not charge_point:
                raise HTTPException(status_code=404, detail=f"充电桩 {req.chargePointId} 未找到")
            
            if not charge_point.site_id:
                raise HTTPException(status_code=400, detail="充电桩未配置站点，请先设置位置")
            
            # 更新或创建定价规则
            tariff = db.query(Tariff).filter(
                Tariff.site_id == charge_point.site_id,
                Tariff.is_active == True
            ).first()
            
            if not tariff:
                tariff = Tariff(
                    site_id=charge_point.site_id,
                    name="默认定价",
                    base_price_per_kwh=req.pricePerKwh,
                    service_fee=0,
                    valid_from=datetime.now(timezone.utc),
                    is_active=True
                )
                db.add(tariff)
            else:
                tariff.base_price_per_kwh = req.pricePerKwh
            
            db.commit()
            
            logger.info(
                f"[API] POST /api/updatePrice 成功 | "
                f"充电桩ID: {req.chargePointId} | "
                f"价格: {req.pricePerKwh} COP/kWh"
            )
        except Exception as e:
            db.rollback()
            logger.error(f"[API] POST /api/updatePrice 失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"更新价格失败: {str(e)}")
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] POST /api/updatePrice 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新价格失败: {str(e)}")
    
    return RemoteResponse(
        success=True,
        message="Price updated successfully",
        details={"chargePointId": req.chargePointId, "pricePerKwh": req.pricePerKwh},
    )


@app.post("/api/remoteStart", response_model=RemoteResponse, tags=["REST"])
async def remote_start(req: RemoteStartRequest) -> RemoteResponse:
    """
    Remote start transaction by sending Authorize + StartTransaction.
    Requires chargePointId and idTag.
    
    NOTE: This is a simplified implementation that mimics user actions.
    In a full OCPP implementation, CSMS would send RemoteStartTransaction to the charger.
    """
    logger.info(
        f"[API] POST /api/remoteStart | "
        f"充电桩ID: {req.chargePointId} | "
        f"用户标签: {req.idTag}"
    )
    
    # 优先使用 MQTT 发送 RemoteStartTransaction
    if MQTT_AVAILABLE and hasattr(transport_manager, 'adapters'):
        if transport_manager.is_connected(req.chargePointId):
            try:
                connection_type = transport_manager.get_connection_type(req.chargePointId)
                logger.info(f"[{req.chargePointId}] 通过 {connection_type.value if connection_type else 'MQTT'} 发送 RemoteStartTransaction")
                logger.info(f"[{req.chargePointId}] 消息内容: action=RemoteStartTransaction, payload={{connectorId: 1, idTag: {req.idTag}}}")
                
                # 发送 RemoteStartTransaction 到充电桩
                result = await transport_manager.send_message(
                    req.chargePointId,
                    "RemoteStartTransaction",
                    {
                        "connectorId": 1,  # 默认使用 connector 1
                        "idTag": req.idTag
                    },
                    preferred_transport=TransportType.MQTT,
                    timeout=10.0
                )
                logger.info(f"[{req.chargePointId}] RemoteStartTransaction 已发送，响应: {result}")
                return RemoteResponse(
                    success=result.get("success", True),
                    message="RemoteStartTransaction sent via MQTT",
                    details={"idTag": req.idTag, "transport": connection_type.value if connection_type else "MQTT", "response": result}
                )
            except Exception as e:
                logger.error(f"[{req.chargePointId}] 通过 MQTT 发送 RemoteStartTransaction 失败: {e}", exc_info=True)
                # 如果 MQTT 发送失败，继续使用 fallback
        else:
            logger.warning(f"[{req.chargePointId}] 充电桩未通过 MQTT 连接")
    
    # Fallback 1: 尝试使用 WebSocket（如果可用）
    ws = charger_websockets.get(req.chargePointId)
    if ws:
        charger = next((c for c in load_chargers() if c["id"] == req.chargePointId), None)
        if charger is None:
            charger = get_default_charger(req.chargePointId)
        session = charger.setdefault("session", {
            "authorized": False,
            "transaction_id": None,
            "meter": 0,
        })
        tx_id = int(datetime.now().timestamp())
        charger["physical_status"] = "Charging"
        session["authorized"] = True
        session["transaction_id"] = tx_id
        charger["last_seen"] = now_iso()
        
        # 创建充电订单
        charging_rate = charger.get("charging_rate", 7.0)
        order_id = f"order_{tx_id}"
        start_time = now_iso()
        create_order(
            order_id=order_id,
            charge_point_id=req.chargePointId,
            user_id=req.idTag,  # 使用idTag作为user_id
            id_tag=req.idTag,
            charging_rate=charging_rate,
            start_time=start_time,
        )
        # 将订单ID保存到session中，以便停止时使用
        session["order_id"] = order_id
        
        save_charger(charger)
        update_active(req.chargePointId, status="Charging", txn_id=tx_id)
        logger.info(
            f"[{req.chargePointId}] RemoteStart fallback: 无连接，模拟交易 {tx_id}, 订单 {order_id}"
        )
        return RemoteResponse(
            success=True,
            message="Charging started (simulated - no connection)",
            details={"transactionId": tx_id, "idTag": req.idTag, "orderId": order_id, "simulated": True},
        )
    try:
        # Step 1: Send Authorize to verify the idTag
        auth_call = json.dumps({
            "action": "Authorize",
            "payload": {"idTag": req.idTag},
        })
        await ws.send_text(auth_call)
        logger.info(f"[{req.chargePointId}] Sent Authorize for idTag={req.idTag}")
        
        # Step 2: Generate transaction ID and send StartTransaction
        tx_id = int(datetime.now().timestamp())
        start_call = json.dumps({
            "action": "StartTransaction",
            "payload": {"transactionId": tx_id},
        })
        await ws.send_text(start_call)
        logger.info(f"[{req.chargePointId}] Sent StartTransaction with txId={tx_id}")
        
        # 创建充电订单
        charger = next((c for c in load_chargers() if c["id"] == req.chargePointId), None)
        if charger is None:
            charger = get_default_charger(req.chargePointId)
        charging_rate = charger.get("charging_rate", 7.0)
        order_id = f"order_{tx_id}"
        start_time = now_iso()
        create_order(
            order_id=order_id,
            charge_point_id=req.chargePointId,
            user_id=req.idTag,  # 使用idTag作为user_id
            id_tag=req.idTag,
            charging_rate=charging_rate,
            start_time=start_time,
        )
        # 将订单ID保存到charger的session中
        session = charger.setdefault("session", {
            "authorized": False,
            "transaction_id": None,
            "meter": 0,
        })
        session["order_id"] = order_id
        save_charger(charger)
        
        return RemoteResponse(
            success=True,
            message="Charging started successfully",
            details={"transactionId": tx_id, "idTag": req.idTag, "orderId": order_id},
        )
    except Exception as e:
        logger.error(f"[{req.chargePointId}] Error starting transaction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/remoteStop", response_model=RemoteResponse, tags=["REST"])
async def remote_stop(req: RemoteStopRequest) -> RemoteResponse:
    """
    Remote stop transaction via RemoteStopTransaction OCPP call.
    Requires chargePointId (transactionId is inferred from active session).
    
    NOTE: In a full OCPP implementation, this would use CallResult/CallError
    with unique message IDs. This simplified version directly sends JSON.
    """
    logger.info(
        f"[API] POST /api/remoteStop | "
        f"充电桩ID: {req.chargePointId}"
    )
    
    # 优先使用 MQTT 发送 RemoteStopTransaction
    if MQTT_AVAILABLE and hasattr(transport_manager, 'adapters'):
        if transport_manager.is_connected(req.chargePointId):
            try:
                # 从数据库获取活跃会话
                txn_id = None
                order_id = None
                
                if DATABASE_AVAILABLE:
                    from app.database.models import ChargingSession, Order
                    db = SessionLocal()
                    try:
                        session = db.query(ChargingSession).filter(
                            ChargingSession.charge_point_id == req.chargePointId,
                            ChargingSession.status == "ongoing"
                        ).order_by(ChargingSession.start_time.desc()).first()
                        
                        if session:
                            txn_id = session.transaction_id
                            order = db.query(Order).filter(Order.session_id == session.id).first()
                            if order:
                                order_id = order.id
                    finally:
                        db.close()
                
                # 如果数据库中没有，尝试从Redis获取（兼容层）
                if not txn_id:
                    charger = next((c for c in load_chargers() if c["id"] == req.chargePointId), None)
                    if charger:
                        session = charger.get("session", {})
                        txn_id = session.get("transaction_id")
                        order_id = session.get("order_id")
                
                if not txn_id:
                    raise HTTPException(status_code=400, detail="No active transaction to stop")
                
                connection_type = transport_manager.get_connection_type(req.chargePointId)
                logger.info(f"[{req.chargePointId}] 通过 {connection_type.value if connection_type else 'MQTT'} 发送 RemoteStopTransaction")
                
                # 发送 RemoteStopTransaction 到充电桩
                result = await transport_manager.send_message(
                    req.chargePointId,
                    "RemoteStopTransaction",
                    {
                        "transactionId": txn_id
                    },
                    preferred_transport=TransportType.MQTT,
                    timeout=10.0
                )
                logger.info(f"[{req.chargePointId}] RemoteStopTransaction 已发送，响应: {result}")
                
                # 更新订单状态（如果数据库可用，使用数据库；否则使用Redis）
                if DATABASE_AVAILABLE and order_id:
                    from app.database.models import Order, ChargingSession
                    db = SessionLocal()
                    try:
                        order = db.query(Order).filter(Order.id == order_id).first()
                        if order and order.status == "ongoing":
                            # 通过session获取meter值计算能量
                            session = db.query(ChargingSession).filter(
                                ChargingSession.id == order.session_id
                            ).first() if order.session_id else None
                            
                            if session and session.end_time:
                                duration_seconds = (session.end_time - session.start_time).total_seconds()
                                duration_minutes = duration_seconds / 60.0
                                
                                # 从meter值计算能量
                                if session.meter_stop and session.meter_start:
                                    energy_wh = session.meter_stop - session.meter_start
                                    energy_kwh = energy_wh / 1000.0
                                else:
                                    energy_kwh = None
                                
                                order.end_time = session.end_time
                                order.duration_minutes = duration_minutes
                                if energy_kwh:
                                    order.energy_kwh = energy_kwh
                                order.status = "completed"
                                db.commit()
                    finally:
                        db.close()
                elif order_id:
                    # 降级到Redis
                    order = get_order(order_id)
                    if order and order.get("status") == "ongoing":
                        start_time_str = order.get("start_time")
                        end_time_str = now_iso()
                        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                        end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                        duration_seconds = (end_time - start_time).total_seconds()
                        duration_minutes = duration_seconds / 60.0
                        charging_rate = order.get("charging_rate", 7.0)
                        energy_kwh = charging_rate * (duration_minutes / 60.0)
                        update_order(
                            order_id=order_id,
                            end_time=end_time_str,
                            duration_minutes=round(duration_minutes, 2),
                            energy_kwh=round(energy_kwh, 2),
                        )
                
                # 更新充电桩状态（兼容层）
                charger = next((c for c in load_chargers() if c["id"] == req.chargePointId), None)
                if charger:
                    charger["physical_status"] = "Available"
                    session = charger.get("session", {})
                    session["transaction_id"] = None
                    session["order_id"] = None
                    session["authorized"] = False
                    save_charger(charger)
                update_active(req.chargePointId, status="Available", txn_id=None)
                
                return RemoteResponse(
                    success=result.get("success", True),
                    message="RemoteStopTransaction sent via MQTT",
                    details={"action": "RemoteStopTransaction", "transactionId": txn_id, "orderId": order_id, "transport": connection_type.value if connection_type else "MQTT", "response": result}
                )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"[{req.chargePointId}] 通过 MQTT 发送 RemoteStopTransaction 失败: {e}", exc_info=True)
                # 如果 MQTT 发送失败，继续使用 fallback
    
    # Fallback 1: 尝试使用 WebSocket（如果可用）
    ws = charger_websockets.get(req.chargePointId)
    if ws:
        try:
            # 获取transaction_id（如果还没有）
            if not txn_id:
                if DATABASE_AVAILABLE:
                    from app.database.models import ChargingSession
                    db = SessionLocal()
                    try:
                        session = db.query(ChargingSession).filter(
                            ChargingSession.charge_point_id == req.chargePointId,
                            ChargingSession.status == "ongoing"
                        ).order_by(ChargingSession.start_time.desc()).first()
                        if session:
                            txn_id = session.transaction_id
                    finally:
                        db.close()
                
                if not txn_id:
                    # 从Redis获取（兼容层）
                    charger = next((c for c in load_chargers() if c["id"] == req.chargePointId), None)
                    if charger:
                        session = charger.get("session", {})
                        txn_id = session.get("transaction_id")
            
            if not txn_id:
                raise HTTPException(status_code=400, detail="No active transaction to stop")
            
            # Send RemoteStopTransaction (simplified format)
            call = json.dumps({
                "action": "RemoteStopTransaction",
                "transactionId": txn_id,
            })
            await ws.send_text(call)
            logger.info(f"[{req.chargePointId}] Sent RemoteStopTransaction (WebSocket)")
            
            # 注意：在实际的OCPP实现中，应该等待StopTransaction响应后再更新订单
            # 这里简化处理，假设会成功停止
            # 订单更新会在WebSocket的StopTransaction处理中完成
            
            return RemoteResponse(
                success=True,
                message="RemoteStopTransaction sent (WebSocket)",
                details={"action": "RemoteStopTransaction", "transactionId": txn_id, "orderId": order_id, "sent": True, "transport": "WebSocket"},
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[{req.chargePointId}] 通过 WebSocket 发送 RemoteStopTransaction 失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    
    # Fallback 2: 如果都没有连接，直接更新状态（模拟停止）
    logger.warning(f"[{req.chargePointId}] RemoteStop fallback: 无连接，模拟停止交易 tx={txn_id}, order={order_id}")
    
    # 更新订单：计算电量和时长
    if order_id:
        order = get_order(order_id)
        if order and order.get("status") == "ongoing":
            start_time_str = order.get("start_time")
            end_time_str = now_iso()
            
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            duration_seconds = (end_time - start_time).total_seconds()
            duration_minutes = duration_seconds / 60.0
            
            charging_rate = order.get("charging_rate", 7.0)
            energy_kwh = charging_rate * (duration_minutes / 60.0)
            
            update_order(
                order_id=order_id,
                end_time=end_time_str,
                duration_minutes=round(duration_minutes, 2),
                energy_kwh=round(energy_kwh, 2),
            )
    
    session["transaction_id"] = None
    session["authorized"] = False
    session["order_id"] = None
    charger["physical_status"] = "Available"
    charger["last_seen"] = now_iso()
    save_charger(charger)
    update_active(req.chargePointId, status="Available", txn_id=None)
    
    return RemoteResponse(
        success=True,
        message="Charging stopped (simulated - no connection)",
        details={"transactionId": txn_id, "orderId": order_id, "simulated": True},
    )


@app.post("/api/getConfiguration", response_model=RemoteResponse, tags=["REST"])
async def get_configuration(req: GetConfigurationRequest) -> RemoteResponse:
    """
    获取充电桩配置参数。
    """
    logger.info(
        f"[API] POST /api/getConfiguration | "
        f"充电桩ID: {req.chargePointId} | "
        f"配置键: {req.keys or '全部'}"
    )
    
    try:
        result = await send_ocpp_call(
            req.chargePointId,
            "GetConfiguration",
            {"key": req.keys} if req.keys else {}
        )
        return RemoteResponse(
            success=result.get("success", False),
            message="GetConfiguration sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in GetConfiguration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/changeConfiguration", response_model=RemoteResponse, tags=["REST"])
async def change_configuration(req: ChangeConfigurationRequest) -> RemoteResponse:
    """
    更改充电桩配置参数。
    """
    logger.info(
        f"[API] POST /api/changeConfiguration | "
        f"充电桩ID: {req.chargePointId} | "
        f"配置键: {req.key} | "
        f"配置值: {req.value}"
    )
    
    try:
        result = await send_ocpp_call(
            req.chargePointId,
            "ChangeConfiguration",
            {"key": req.key, "value": req.value}
        )
        return RemoteResponse(
            success=result.get("success", False),
            message="ChangeConfiguration sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in ChangeConfiguration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reset", response_model=RemoteResponse, tags=["REST"])
async def reset_charger(req: ResetRequest) -> RemoteResponse:
    """
    重置充电桩（软重启或硬重启）。
    """
    logger.info(
        f"[API] POST /api/reset | "
        f"充电桩ID: {req.chargePointId} | "
        f"重置类型: {req.type}"
    )
    
    try:
        result = await send_ocpp_call(
            req.chargePointId,
            "Reset",
            {"type": req.type}
        )
        return RemoteResponse(
            success=result.get("success", False),
            message="Reset sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Reset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/unlockConnector", response_model=RemoteResponse, tags=["REST"])
async def unlock_connector(req: UnlockConnectorRequest) -> RemoteResponse:
    """
    解锁连接器。
    """
    logger.info(
        f"[API] POST /api/unlockConnector | "
        f"充电桩ID: {req.chargePointId} | "
        f"连接器ID: {req.connectorId}"
    )
    
    try:
        result = await send_ocpp_call(
            req.chargePointId,
            "UnlockConnector",
            {"connectorId": req.connectorId}
        )
        return RemoteResponse(
            success=result.get("success", False),
            message="UnlockConnector sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in UnlockConnector: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/changeAvailability", response_model=RemoteResponse, tags=["REST"])
async def change_availability(req: ChangeAvailabilityRequest) -> RemoteResponse:
    """
    更改充电桩或连接器的可用性。
    如果设置为 Inoperative，会自动将充电桩状态设为 Maintenance（维修中）。
    """
    logger.info(
        f"[API] POST /api/changeAvailability | "
        f"充电桩ID: {req.chargePointId} | "
        f"连接器ID: {req.connectorId} | "
        f"类型: {req.type}"
    )
    
    try:
        result = await send_ocpp_call(
            req.chargePointId,
            "ChangeAvailability",
            {"connectorId": req.connectorId, "type": req.type}
        )
        
        # 如果设置为 Inoperative（不可用），更新运营状态为 MAINTENANCE
        if req.type == "Inoperative" and result.get("success"):
            charger = next((c for c in load_chargers() if c["id"] == req.chargePointId), None)
            if charger:
                charger["operational_status"] = "MAINTENANCE"
                save_charger(charger)
                logger.info(f"[{req.chargePointId}] 已设置为维修状态（operational_status=MAINTENANCE）")
        # 如果设置为 Operative（可用），恢复运营状态为 ENABLED
        elif req.type == "Operative" and result.get("success"):
            charger = next((c for c in load_chargers() if c["id"] == req.chargePointId), None)
            if charger:
                charger["operational_status"] = "ENABLED"
                save_charger(charger)
                logger.info(f"[{req.chargePointId}] 已恢复为可用状态（operational_status=ENABLED）")
                logger.info(f"[{req.chargePointId}] 已从维修状态恢复为可用")
        
        return RemoteResponse(
            success=result.get("success", False),
            message="ChangeAvailability sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in ChangeAvailability: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/setMaintenance", response_model=RemoteResponse, tags=["REST"])
async def set_maintenance(req: SetMaintenanceRequest) -> RemoteResponse:
    """
    设置充电桩为维修状态或取消维修状态。
    维修状态的充电桩禁止用户使用。
    """
    logger.info(
        f"[API] POST /api/setMaintenance | "
        f"充电桩ID: {req.chargePointId} | "
        f"维修状态: {req.maintenance}"
    )
    
    try:
        charger = next((c for c in load_chargers() if c["id"] == req.chargePointId), None)
        if not charger:
            raise HTTPException(status_code=404, detail=f"Charger {req.chargePointId} not found")
        
        if req.maintenance:
            # 设置为维修状态（更新运营状态）
            charger["operational_status"] = "MAINTENANCE"
            save_charger(charger)
            # 注意：不更新 physical_status，它由 OCPP 控制
            
            # 同时发送 ChangeAvailability 消息到充电桩（如果连接）
            try:
                await send_ocpp_call(
                    req.chargePointId,
                    "ChangeAvailability",
                    {"connectorId": 0, "type": "Inoperative"}  # connectorId=0 表示整个充电桩
                )
            except Exception as e:
                logger.warning(f"[{req.chargePointId}] 发送 ChangeAvailability 失败（可能离线）: {e}")
            
            logger.info(f"[{req.chargePointId}] 已设置为维修状态（operational_status=MAINTENANCE）")
            return RemoteResponse(
                success=True,
                message="Charger set to maintenance mode",
                details={
                    "chargePointId": req.chargePointId,
                    "operational_status": "MAINTENANCE",
                    "is_available": calculate_is_available(charger)
                }
            )
        else:
            # 取消维修状态，恢复为可用（更新运营状态）
            charger["operational_status"] = "ENABLED"
            save_charger(charger)
            # 注意：不更新 physical_status，它由 OCPP 控制
            
            # 同时发送 ChangeAvailability 消息到充电桩（如果连接）
            try:
                await send_ocpp_call(
                    req.chargePointId,
                    "ChangeAvailability",
                    {"connectorId": 0, "type": "Operative"}  # connectorId=0 表示整个充电桩
                )
            except Exception as e:
                logger.warning(f"[{req.chargePointId}] 发送 ChangeAvailability 失败（可能离线）: {e}")
            
            logger.info(f"[{req.chargePointId}] 已取消维修状态，恢复为可用（operational_status=ENABLED）")
            return RemoteResponse(
                success=True,
                message="Charger maintenance mode cancelled",
                details={
                    "chargePointId": req.chargePointId,
                    "operational_status": "ENABLED",
                    "is_available": calculate_is_available(charger)
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in SetMaintenance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/setChargingProfile", response_model=RemoteResponse, tags=["REST"])
async def set_charging_profile(req: SetChargingProfileRequest) -> RemoteResponse:
    """
    设置充电配置文件。
    """
    try:
        result = await send_ocpp_call(
            req.chargePointId,
            "SetChargingProfile",
            {
                "connectorId": req.connectorId,
                "csChargingProfiles": req.csChargingProfiles
            }
        )
        return RemoteResponse(
            success=result.get("success", False),
            message="SetChargingProfile sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in SetChargingProfile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/clearChargingProfile", response_model=RemoteResponse, tags=["REST"])
async def clear_charging_profile(req: ClearChargingProfileRequest) -> RemoteResponse:
    """
    清除充电配置文件。
    """
    try:
        payload = {}
        if req.id is not None:
            payload["id"] = req.id
        if req.connectorId is not None:
            payload["connectorId"] = req.connectorId
        if req.chargingProfilePurpose is not None:
            payload["chargingProfilePurpose"] = req.chargingProfilePurpose
        if req.stackLevel is not None:
            payload["stackLevel"] = req.stackLevel
        
        result = await send_ocpp_call(
            req.chargePointId,
            "ClearChargingProfile",
            payload
        )
        return RemoteResponse(
            success=result.get("success", False),
            message="ClearChargingProfile sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in ClearChargingProfile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/getDiagnostics", response_model=RemoteResponse, tags=["REST"])
async def get_diagnostics(req: GetDiagnosticsRequest) -> RemoteResponse:
    """
    获取诊断信息。
    """
    try:
        payload = {"location": req.location}
        if req.retries is not None:
            payload["retries"] = req.retries
        if req.retryInterval is not None:
            payload["retryInterval"] = req.retryInterval
        if req.startTime is not None:
            payload["startTime"] = req.startTime
        if req.stopTime is not None:
            payload["stopTime"] = req.stopTime
        
        result = await send_ocpp_call(
            req.chargePointId,
            "GetDiagnostics",
            payload
        )
        return RemoteResponse(
            success=result.get("success", False),
            message="GetDiagnostics sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in GetDiagnostics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/exportLogs", tags=["REST"])
async def export_logs(req: ExportLogsRequest, request: Request = None):
    """
    导出充电桩日志。
    通过GetDiagnostics获取日志文件，然后返回文件下载。
    仅限管理员（admin）使用。
    """
    from fastapi.responses import StreamingResponse
    import io
    
    logger.info(
        f"[API] POST /api/exportLogs | "
        f"充电桩ID: {req.chargePointId} | "
        f"用户角色: {req.userRole or '未提供'}"
    )
    
    # 权限验证：只有管理员才能导出日志
    if req.userRole != "admin":
        logger.warning(
            f"[API] POST /api/exportLogs | 权限拒绝 | "
            f"充电桩ID: {req.chargePointId} | "
            f"用户角色: {req.userRole or '未提供'}"
        )
        raise HTTPException(
            status_code=403, 
            detail="仅管理员可以导出日志。此操作需要管理员权限。"
        )
    
    try:
        # 检查充电桩是否存在
        charger = next((c for c in load_chargers() if c["id"] == req.chargePointId), None)
        if not charger:
            raise HTTPException(status_code=404, detail=f"Charger {req.chargePointId} not found")
        
        # 调用GetDiagnostics获取日志
        # 如果没有提供location，使用默认值（充电桩会返回日志文件位置）
        location = req.location if req.location else "internal://logs"
        
        payload = {"location": location}
        if req.retries is not None:
            payload["retries"] = req.retries
        if req.retryInterval is not None:
            payload["retryInterval"] = req.retryInterval
        if req.startTime is not None:
            payload["startTime"] = req.startTime
        if req.stopTime is not None:
            payload["stopTime"] = req.stopTime
        
        # 尝试通过WebSocket发送GetDiagnostics请求
        result = await send_ocpp_call(
            req.chargePointId,
            "GetDiagnostics",
            payload
        )
        
        # 如果成功，返回日志文件信息
        # 注意：实际的日志文件可能由充电桩上传到指定位置
        # 这里我们返回一个包含日志信息的JSON响应，或者如果充电桩返回了文件，则返回文件
        
        if result.get("success"):
            # 如果充电桩返回了文件名，可以在这里处理文件下载
            # 目前返回一个包含诊断信息的JSON文件
            diagnostics_data = {
                "charger_id": req.chargePointId,
                "timestamp": now_iso(),
                "diagnostics_result": result.get("data", {}),
                "charger_info": {
                    "vendor": charger.get("vendor"),
                    "model": charger.get("model"),
                    "firmware_version": charger.get("firmware_version"),
                    "serial_number": charger.get("serial_number"),
                    "physical_status": charger.get("physical_status", "Unknown"),
                    "operational_status": charger.get("operational_status", "ENABLED"),
                    "is_available": calculate_is_available(charger),
                    "last_seen": charger.get("last_seen"),
                }
            }
            
            # 将数据转换为JSON字符串
            json_content = json.dumps(diagnostics_data, indent=2, ensure_ascii=False)
            
            # 创建文件流
            file_stream = io.BytesIO(json_content.encode('utf-8'))
            
            # 生成文件名
            filename = f"charger_{req.chargePointId}_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            logger.info(
                f"[API] POST /api/exportLogs 成功 | "
                f"充电桩ID: {req.chargePointId} | "
                f"文件名: {filename}"
            )
            
            return StreamingResponse(
                file_stream,
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )
        else:
            # 如果GetDiagnostics失败，仍然返回一个包含基本信息的日志文件
            logger.warning(
                f"[API] POST /api/exportLogs | "
                f"GetDiagnostics失败，返回基本信息 | "
                f"充电桩ID: {req.chargePointId}"
            )
            
            diagnostics_data = {
                "charger_id": req.chargePointId,
                "timestamp": now_iso(),
                "note": "GetDiagnostics请求失败，以下是充电桩基本信息",
                "error": result.get("error", "Unknown error"),
                "charger_info": {
                    "vendor": charger.get("vendor"),
                    "model": charger.get("model"),
                    "firmware_version": charger.get("firmware_version"),
                    "serial_number": charger.get("serial_number"),
                    "physical_status": charger.get("physical_status", "Unknown"),
                    "operational_status": charger.get("operational_status", "ENABLED"),
                    "is_available": calculate_is_available(charger),
                    "last_seen": charger.get("last_seen"),
                }
            }
            
            json_content = json.dumps(diagnostics_data, indent=2, ensure_ascii=False)
            file_stream = io.BytesIO(json_content.encode('utf-8'))
            filename = f"charger_{req.chargePointId}_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            return StreamingResponse(
                file_stream,
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in ExportLogs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/updateFirmware", response_model=RemoteResponse, tags=["REST"])
async def update_firmware(req: UpdateFirmwareRequest) -> RemoteResponse:
    """
    更新固件。
    """
    try:
        payload = {
            "location": req.location,
            "retrieveDate": req.retrieveDate
        }
        if req.retryInterval is not None:
            payload["retryInterval"] = req.retryInterval
        if req.retries is not None:
            payload["retries"] = req.retries
        
        result = await send_ocpp_call(
            req.chargePointId,
            "UpdateFirmware",
            payload
        )
        return RemoteResponse(
            success=result.get("success", False),
            message="UpdateFirmware sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in UpdateFirmware: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reserveNow", response_model=RemoteResponse, tags=["REST"])
async def reserve_now(req: ReserveNowRequest) -> RemoteResponse:
    """
    预约充电。
    """
    try:
        payload = {
            "connectorId": req.connectorId,
            "expiryDate": req.expiryDate,
            "idTag": req.idTag,
            "reservationId": req.reservationId
        }
        if req.parentIdTag is not None:
            payload["parentIdTag"] = req.parentIdTag
        
        result = await send_ocpp_call(
            req.chargePointId,
            "ReserveNow",
            payload
        )
        return RemoteResponse(
            success=result.get("success", False),
            message="ReserveNow sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in ReserveNow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cancelReservation", response_model=RemoteResponse, tags=["REST"])
async def cancel_reservation(req: CancelReservationRequest) -> RemoteResponse:
    """
    取消预约。
    """
    try:
        result = await send_ocpp_call(
            req.chargePointId,
            "CancelReservation",
            {"reservationId": req.reservationId}
        )
        return RemoteResponse(
            success=result.get("success", False),
            message="CancelReservation sent" if result.get("success") else "Failed",
            details=result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in CancelReservation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/messages", response_model=RemoteResponse, tags=["REST"])
async def create_message(req: CreateMessageRequest) -> RemoteResponse:
    """
    Create a new support message from user.
    """
    logger.info(
        f"[API] POST /api/messages | "
        f"用户ID: {req.userId} | "
        f"用户名: {req.username} | "
        f"消息长度: {len(req.message)} 字符"
    )
    
    message_id = f"msg_{int(datetime.now().timestamp() * 1000)}"
    message_data = {
        "id": message_id,
        "userId": req.userId,
        "username": req.username,
        "message": req.message,
        "reply": None,
        "created_at": now_iso(),
        "replied_at": None,
        "status": "pending",
    }
    
    # Save to Redis list
    redis_client.lpush(MESSAGES_LIST_KEY, json.dumps(message_data))
    # Keep only last 100 messages
    redis_client.ltrim(MESSAGES_LIST_KEY, 0, 99)
    
    logger.info(
        f"[API] POST /api/messages 成功 | "
        f"消息ID: {message_id} | "
        f"用户: {req.username} ({req.userId})"
    )
    
    return RemoteResponse(
        success=True,
        message="Message created successfully",
        details={"messageId": message_id, "message": message_data},
    )


@app.get("/api/messages", tags=["REST"])
def list_messages() -> List[Dict[str, Any]]:
    """
    List all support messages (admin view).
    """
    items = redis_client.lrange(MESSAGES_LIST_KEY, 0, -1)
    messages = []
    for val in items:
        try:
            messages.append(json.loads(val))
        except Exception:
            continue
    # Reverse to show newest first
    messages.reverse()
    
    logger.info(f"[API] GET /api/messages 成功 | 返回 {len(messages)} 条消息")
    return messages


@app.post("/api/messages/reply", response_model=RemoteResponse, tags=["REST"])
async def reply_message(req: ReplyMessageRequest) -> RemoteResponse:
    """
    Reply to a support message.
    """
    logger.info(
        f"[API] POST /api/messages/reply | "
        f"消息ID: {req.messageId} | "
        f"回复长度: {len(req.reply)} 字符"
    )
    
    # Find message in Redis
    items = redis_client.lrange(MESSAGES_LIST_KEY, 0, -1)
    found = False
    
    for i, val in enumerate(items):
        try:
            msg = json.loads(val)
            if msg["id"] == req.messageId:
                msg["reply"] = req.reply
                msg["replied_at"] = now_iso()
                msg["status"] = "replied"
                # Update in Redis
                redis_client.lset(MESSAGES_LIST_KEY, i, json.dumps(msg))
                found = True
                logger.info(
                    f"[API] POST /api/messages/reply 成功 | "
                    f"消息ID: {req.messageId}"
                )
                break
        except Exception:
            continue
    
    if not found:
        logger.warning(f"[API] POST /api/messages/reply | 消息未找到: {req.messageId}")
        raise HTTPException(status_code=404, detail="Message not found")
    
    return RemoteResponse(
        success=True,
        message="Reply sent successfully",
        details=None,
    )


@app.get("/api/orders", tags=["REST"])
def get_orders(userId: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get charging orders - 使用新表结构
    If userId is provided, returns only orders for that user.
    Otherwise, returns all orders.
    """
    logger.info(
        f"[API] GET /api/orders | "
        f"用户ID: {userId or '全部'}"
    )
    
    if not DATABASE_AVAILABLE:
        # 降级到Redis
        if userId:
            orders = get_orders_by_user(userId)
        else:
            orders = get_all_orders()
        return orders
    
    try:
        from app.database.models import Order, Invoice
        db = SessionLocal()
        try:
            query = db.query(Order)
            
            if userId:
                query = query.filter(Order.user_id == userId)
            
            orders_db = query.order_by(Order.created_at.desc()).all()
            
            result = []
            for o in orders_db:
                # 获取关联的发票信息
                invoice = db.query(Invoice).filter(Invoice.order_id == o.id).first()
                total_cost = invoice.total_amount if invoice else None
                
                result.append({
                    "id": o.id,
                    "charge_point_id": o.charge_point_id,
                    "user_id": o.user_id,
                    "id_tag": o.id_tag,
                    "start_time": o.start_time.isoformat() if o.start_time else None,
                    "end_time": o.end_time.isoformat() if o.end_time else None,
                    "energy_kwh": o.energy_kwh,
                    "duration_minutes": o.duration_minutes,
                    "total_cost": total_cost,
                    "status": o.status,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                })
            
            logger.info(f"[API] GET /api/orders 成功 | 返回 {len(result)} 个订单（数据库）")
            return result
        finally:
            db.close()
    except Exception as e:
        logger.error(f"获取订单列表失败: {e}", exc_info=True)
        # 降级到Redis
        if userId:
            return get_orders_by_user(userId)
        else:
            return get_all_orders()


@app.get("/api/orders/current", tags=["REST"])
def get_current_order(chargePointId: str = Query(...), transactionId: Optional[int] = Query(None)) -> Dict[str, Any]:
    """
    Get current ongoing order for a charger - 使用新表结构
    If transactionId is provided, find order by transaction ID.
    Otherwise, find the latest ongoing order for the charger.
    """
    logger.info(
        f"[API] GET /api/orders/current | "
        f"充电桩ID: {chargePointId} | "
        f"交易ID: {transactionId or '未指定'}"
    )
    
    if not DATABASE_AVAILABLE:
        # 降级到Redis逻辑
        if transactionId:
            order_id = generate_order_id(transaction_id=transactionId)
            order = get_order(order_id)
            if order:
                return order
    
    charger = next((c for c in load_chargers() if c["id"] == chargePointId), None)
    if charger:
        session = charger.get("session", {})
        order_id = session.get("order_id")
        if order_id:
            order = get_order(order_id)
            if order:
                return order
    
    all_orders = get_all_orders()
    charger_orders = [o for o in all_orders if o.get("charge_point_id") == chargePointId or o.get("charger_id") == chargePointId]
    if charger_orders:
        charger_orders.sort(key=lambda x: x.get("start_time", ""), reverse=True)
        ongoing_order = next((o for o in charger_orders if o.get("status") == "ongoing"), None)
        if ongoing_order:
            return ongoing_order
        return charger_orders[0]
    
    raise HTTPException(status_code=404, detail="No order found")
    
    try:
        from app.database.models import Order, ChargingSession, Invoice
        db = SessionLocal()
        try:
            # 如果提供了transactionId，通过ChargingSession查找
            if transactionId:
                session = db.query(ChargingSession).filter(
                    ChargingSession.charge_point_id == chargePointId,
                    ChargingSession.transaction_id == transactionId
                ).first()
                if session:
                    order = db.query(Order).filter(Order.session_id == session.id).first()
                    if order:
                        invoice = db.query(Invoice).filter(Invoice.order_id == order.id).first()
                        return {
                            "id": order.id,
                            "charge_point_id": order.charge_point_id,
                            "user_id": order.user_id,
                            "id_tag": order.id_tag,
                            "start_time": order.start_time.isoformat() if order.start_time else None,
                            "end_time": order.end_time.isoformat() if order.end_time else None,
                            "energy_kwh": order.energy_kwh,
                            "duration_minutes": order.duration_minutes,
                            "total_cost": invoice.total_amount if invoice else None,
                            "status": order.status,
                        }
            
            # 查找最新的进行中订单
            order = db.query(Order).filter(
                Order.charge_point_id == chargePointId,
                Order.status == "ongoing"
            ).order_by(Order.created_at.desc()).first()
            
            if order:
                invoice = db.query(Invoice).filter(Invoice.order_id == order.id).first()
                return {
                    "id": order.id,
                    "charge_point_id": order.charge_point_id,
                    "user_id": order.user_id,
                    "id_tag": order.id_tag,
                    "start_time": order.start_time.isoformat() if order.start_time else None,
                    "end_time": order.end_time.isoformat() if order.end_time else None,
                    "energy_kwh": order.energy_kwh,
                    "duration_minutes": order.duration_minutes,
                    "total_cost": invoice.total_amount if invoice else None,
                    "status": order.status,
                }
            
            raise HTTPException(status_code=404, detail="No order found")
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取当前订单失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取订单失败: {str(e)}")


@app.get("/api/orders/current/meter", tags=["REST"])
def get_current_order_meter(
    chargePointId: str = Query(...), 
    transactionId: Optional[int] = Query(None)
) -> Dict[str, Any]:
    """
    获取当前充电订单的实时电量数据
    返回最新的 MeterValues 数据，用于实时显示电量和费用
    """
    logger.debug(
        f"[API] GET /api/orders/current/meter | "
        f"充电桩ID: {chargePointId} | "
        f"交易ID: {transactionId or '未指定'}"
    )
    
    charger = next((c for c in load_chargers() if c["id"] == chargePointId), None)
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    
    session = charger.get("session", {})
    current_transaction_id = session.get("transaction_id")
    
    # 如果没有提供transactionId，使用充电桩当前的事务ID
    if not transactionId:
        transactionId = current_transaction_id
    
    if not transactionId:
        raise HTTPException(status_code=404, detail="No active transaction")
    
    # 获取当前电量（Wh），从充电桩的session中获取
    meter_value_wh = session.get("meter", 0)
    
    # 转换为 kWh
    meter_value_kwh = meter_value_wh / 1000.0
    
    # 获取订单信息
    order_id = session.get("order_id") or f"order_{transactionId}"
    order = get_order(order_id)
    
    # 计算费用
    price_per_kwh = charger.get("price_per_kwh", 2700.0)  # COP/kWh
    total_cost = meter_value_kwh * price_per_kwh
    
    # 计算充电时长（如果有订单）
    duration_minutes = None
    if order and order.get("start_time"):
        try:
            start_time = datetime.fromisoformat(order["start_time"].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            duration_minutes = (now - start_time).total_seconds() / 60.0
        except:
            pass
    
    return {
        "charger_id": chargePointId,
        "transaction_id": transactionId,
        "meter_value_wh": meter_value_wh,
        "meter_value_kwh": round(meter_value_kwh, 3),
        "price_per_kwh": price_per_kwh,
        "total_cost": round(total_cost, 2),
        "duration_minutes": round(duration_minutes, 1) if duration_minutes else None,
        "timestamp": now_iso(),
        "order_id": order_id if order else None,
    }
    
    logger.debug(
        f"[API] GET /api/orders/current/meter 成功 | "
        f"充电桩ID: {chargePointId} | "
        f"电量: {meter_value_kwh:.3f} kWh | "
        f"费用: {total_cost:.2f} COP"
    )


# ---- HTTP OCPP 端点（如果启用 HTTP 传输）----
@app.post("/ocpp/{charge_point_id}", tags=["OCPP"])
@app.get("/ocpp/{charge_point_id}", tags=["OCPP"])
async def ocpp_http(charge_point_id: str, request: Request):
    """
    HTTP OCPP 端点
    - POST: 充电桩发送 OCPP 消息
    - GET: 充电桩轮询获取待处理的 CSMS 消息
    """
    if not MQTT_AVAILABLE or not hasattr(transport_manager, 'adapters'):
        raise HTTPException(status_code=503, detail="传输管理器未初始化")
    
    settings = get_settings()
    if not settings.enable_http_transport:
        raise HTTPException(status_code=503, detail="HTTP 传输未启用")
    
    # 获取 HTTP 适配器
    http_adapter = transport_manager.get_adapter(TransportType.HTTP)
    if not http_adapter:
        raise HTTPException(status_code=503, detail="HTTP 传输适配器不可用")
    
    try:
        return await http_adapter.handle_http_request(charge_point_id, request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{charge_point_id}] HTTP OCPP 请求处理错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ocpp")
async def ocpp_ws(ws: WebSocket, id: str = Query(..., description="Charge Point ID")):
    """
    WebSocket OCPP端点（使用新服务层）
    id参数现在表示charge_point_id
    """
    # Enforce subprotocol negotiation for OCPP 1.6J
    requested_proto = (ws.headers.get("sec-websocket-protocol") or "").strip()
    requested = [p.strip() for p in requested_proto.split(",") if p.strip()]
    if "ocpp1.6" not in requested:
        # Refuse if client does not offer ocpp1.6
        await ws.close(code=1002)
        return
    await ws.accept(subprotocol="ocpp1.6")
    
    # 注册WebSocket连接（用于传输管理器）
    charge_point_id = id
    charger_websockets[charge_point_id] = ws
    
    # 如果启用了WebSocket适配器，也注册到适配器
    if MQTT_AVAILABLE and hasattr(transport_manager, 'adapters'):
        ws_adapter = transport_manager.get_adapter(TransportType.WEBSOCKET)
        if ws_adapter:
            await ws_adapter.register_connection(charge_point_id, ws)
    
    logger.info(f"[{charge_point_id}] WebSocket connected, subprotocol=ocpp1.6")
    
    try:
        await ws.send_text(json.dumps({"result": "Connected", "id": charge_point_id}))

        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await ws.send_text(json.dumps({"error": "Invalid JSON"}))
                continue

            # 支持两种格式：
            # 1. OCPP 1.6 标准格式: [MessageType, UniqueId, Action, Payload]
            # 2. 简化格式: {"action": "...", "payload": {...}}
            unique_id = None
            is_ocpp_standard_format = False
            
            if isinstance(msg, list) and len(msg) >= 4:
                # OCPP 1.6 标准格式
                message_type = msg[0]
                if message_type != 2:  # 必须是 CALL
                    logger.error(f"[{charge_point_id}] 无效的 MessageType: {message_type}, 期望 2 (CALL)")
                    await ws.send_text(json.dumps([4, "", "ProtocolError", "Invalid MessageType"]))
                    continue
                
                unique_id = msg[1]
                action = msg[2]
                payload = msg[3] if isinstance(msg[3], dict) else {}
                is_ocpp_standard_format = True
                
                logger.info(f"[{charge_point_id}] <- WebSocket OCPP {action} (标准格式, UniqueId={unique_id}) | payload={json.dumps(payload)}")
            elif isinstance(msg, dict):
                # 简化格式
                action = str(msg.get("action", "")).strip()
                payload = msg.get("payload", {})
                
                logger.info(f"[{charge_point_id}] <- WebSocket OCPP {action} (简化格式) | payload={json.dumps(payload)}")
            else:
                logger.error(f"[{charge_point_id}] 无效的消息格式: {type(msg)}")
                await ws.send_text(json.dumps({"error": "Invalid message format"}))
                continue

            # 使用新的服务层处理OCPP消息
            try:
                # 从payload中提取evse_id（如果有）
                evse_id = payload.get("connectorId", 1)
                if evse_id == 0:
                    evse_id = 1  # OCPP中0表示整个充电桩
                
                # 尝试从payload中提取serial_number（用于BootNotification）
                device_serial_number = None
                if action == "BootNotification":
                    device_serial_number = payload.get("chargePointSerialNumber") or payload.get("serialNumber")
                
                # 调用统一的消息处理函数
                response = await handle_ocpp_message(
                    charge_point_id=charge_point_id,
                    action=action,
                    payload=payload,
                    device_serial_number=device_serial_number,
                    evse_id=evse_id
                )
                    
                # 发送响应
                if is_ocpp_standard_format and unique_id:
                    # OCPP 1.6 标准格式响应
                    if "errorCode" in response or "error" in response or response.get("status") == "Rejected":
                        # CALLERROR: [4, UniqueId, ErrorCode, ErrorDescription, ErrorDetails(可选)]
                        error_code = response.get("errorCode", "InternalError")
                        error_description = response.get("errorDescription", response.get("error", "Unknown error"))
                        error_details = response.get("errorDetails")
                        
                        if error_details:
                            resp_msg = [4, unique_id, error_code, error_description, error_details]
                        else:
                            resp_msg = [4, unique_id, error_code, error_description]
                        logger.warning(f"[{charge_point_id}] -> WebSocket OCPP {action} CALLERROR | {error_code}")
                    else:
                        # CALLRESULT: [3, UniqueId, Payload]
                        resp_msg = [3, unique_id, response]
                        logger.info(f"[{charge_point_id}] -> WebSocket OCPP {action} CALLRESULT | {json.dumps(response)}")
                    
                    await ws.send_text(json.dumps(resp_msg))
                else:
                    # 简化格式响应
                    if response:
                        if action in ["BootNotification", "Heartbeat", "StatusNotification", "Authorize", 
                                     "StartTransaction", "StopTransaction", "MeterValues"]:
                            resp_msg = {
                                "action": action,
                                **response
                            }
                            logger.info(f"[{charge_point_id}] -> WebSocket OCPP {action}Response | {json.dumps(response)}")
                            await ws.send_text(json.dumps(resp_msg))
                        else:
                            await ws.send_text(json.dumps({"action": action, **response}))
                    else:
                        await ws.send_text(json.dumps({"action": action}))

            except Exception as e:
                logger.error(f"[{charge_point_id}] OCPP消息处理错误: {e}", exc_info=True)
                # 发送错误响应
                try:
                    await ws.send_text(json.dumps({
                        "error": "InternalError",
                        "action": action,
                        "detail": str(e)[:200]
                }))
                except Exception:
                    pass  # 连接可能已关闭

    except WebSocketDisconnect:
        logger.info(f"[{charge_point_id}] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[{charge_point_id}] WebSocket处理错误: {e}", exc_info=True)
        # 尝试发送错误响应（如果连接还活着）
        try:
            await ws.send_text(json.dumps({
                "error": "InternalError", 
                "detail": str(e)[:200]  # 限制错误信息长度
            }))
        except Exception:
            # 连接可能已关闭，忽略
            pass
    finally:
        # 注销WebSocket连接
        charger_websockets.pop(charge_point_id, None)
        
        # 从适配器注销
        if MQTT_AVAILABLE and hasattr(transport_manager, 'adapters'):
            ws_adapter = transport_manager.get_adapter(TransportType.WEBSOCKET)
            if ws_adapter:
                await ws_adapter.unregister_connection(charge_point_id)
        
        logger.info(f"[{charge_point_id}] WebSocket unregistered")
        try:
            await ws.close()
        except Exception:
            pass


# ---- 注册 API v1 路由 ----
# 强制刷新输出，确保日志立即显示
import sys
sys.stdout.flush()
sys.stderr.flush()

try:
    logger.info("开始注册 API v1 路由...")
    from app.api.v1 import api_router
    logger.info("API v1 路由模块导入成功")
    
    app.include_router(api_router)
    logger.info("API v1 路由已注册到应用")
    
    # 验证路由是否注册成功 - 列出所有注册的路由
    all_routes = []
    for route in app.routes:
        if hasattr(route, 'path'):
            all_routes.append(route.path)
        elif hasattr(route, 'path_regex'):
            all_routes.append(str(route.path_regex))
    
    logger.info(f"当前已注册的路由总数: {len(all_routes)}")
    
    # 检查是否包含 /api/v1/chargers
    v1_chargers_found = any("/api/v1/chargers" in route for route in all_routes)
    if v1_chargers_found:
        logger.info("✓ /api/v1/chargers 路由已确认注册")
    else:
        logger.warning(f"⚠ /api/v1/chargers 路由未找到")
        logger.warning(f"已注册的路由示例（前20个）: {all_routes[:20] if all_routes else '无'}")
        # 检查是否有其他 /api/v1 路由
        v1_routes = [r for r in all_routes if "/api/v1" in r]
        if v1_routes:
            logger.warning(f"但找到了其他 /api/v1 路由: {v1_routes}")
        else:
            logger.error("✗ 完全没有 /api/v1 路由，说明 API v1 路由注册失败")
    
    sys.stdout.flush()
        
except ImportError as e:
    error_msg = f"API v1 路由注册失败（导入错误）: {e}"
    logger.error(error_msg, exc_info=True)
    print(f"ERROR: {error_msg}", file=sys.stderr)
    sys.stderr.flush()
except Exception as e:
    error_msg = f"API v1 路由注册出错: {e}"
    logger.error(error_msg, exc_info=True)
    print(f"ERROR: {error_msg}", file=sys.stderr)
    sys.stderr.flush()

