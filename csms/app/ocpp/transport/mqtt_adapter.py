#
# MQTT 传输适配器
# 支持 OCPP 消息通过 MQTT 传输
# 使用新格式：{type_code}/{serial_number}/user/{up|down}
#

import json
import logging
from typing import Dict, Any, Optional
import asyncio
from .base import TransportAdapter, TransportType

logger = logging.getLogger("ocpp_csms")

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.warning("paho-mqtt 未安装，MQTT 传输不可用")


class MQTTAdapter(TransportAdapter):
    """MQTT 传输适配器
    
    支持 OCPP 消息通过 MQTT 传输
    Topic格式:
    - 设备发送消息: {type_code}/{serial_number}/user/up (服务器订阅此主题)
    - 服务器发送消息: {type_code}/{serial_number}/user/down (设备订阅此主题)
    
    示例:
    - zcf品牌: zcf/861076087029615/user/up
    - tesla品牌: tesla/123456789012345/user/up
    """
    
    def __init__(self, broker_host: str = "localhost", broker_port: int = 1883):
        super().__init__(TransportType.MQTT)
        if not MQTT_AVAILABLE:
            raise ImportError("paho-mqtt 未安装，请运行: pip install paho-mqtt")
        
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client: Optional[mqtt.Client] = None
        self._connected_chargers: set[str] = set()
        self._pending_responses: Dict[str, asyncio.Future] = {}  # 等待响应的 Future
        self._loop = None
        self._subscribed_types: set[str] = set()  # 已订阅的设备类型
        self._mqtt_connected: bool = False  # MQTT 连接状态标志
    
    async def start(self) -> None:
        """启动 MQTT 客户端"""
        if not MQTT_AVAILABLE:
            raise ImportError("paho-mqtt 未安装")
        
        self._loop = asyncio.get_event_loop()
        
        # 创建 MQTT 客户端
        self.client = mqtt.Client(client_id="csms_server", protocol=mqtt.MQTTv311)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        # 连接到 MQTT broker
        try:
            logger.info("=" * 60)
            logger.info("正在初始化 MQTT 连接...")
            logger.info("=" * 60)
            logger.info(f"Broker 地址: {self.broker_host}:{self.broker_port}")
            logger.info(f"客户端 ID: csms_server")
            logger.info(f"协议版本: MQTTv311")
            logger.info(f"Keepalive: 60 秒")
            logger.info("=" * 60)
            
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            
            # 等待连接建立（订阅将在 _on_connect 回调中执行）
            # 最多等待5秒
            import time
            for i in range(50):  # 50 * 0.1 = 5秒
                if self._mqtt_connected:
                    break
                await asyncio.sleep(0.1)
            
            if not self._mqtt_connected:
                logger.warning("MQTT 连接建立超时，但继续执行订阅（可能在后台建立）")
            
            logger.info(f"MQTT 传输适配器已启动，连接到 {self.broker_host}:{self.broker_port}")
        except Exception as e:
            logger.error(f"MQTT 连接失败: {e}", exc_info=True)
            raise
    
    async def _subscribe_all_device_types(self):
        """动态订阅所有激活的设备类型"""
        try:
            from app.database.base import SessionLocal
            from app.core.mqtt_auth import MQTTAuthService
            
            db = SessionLocal()
            try:
                device_types = MQTTAuthService.get_all_active_device_types(db)
                for device_type in device_types:
                    type_code = device_type.get("type_code") if isinstance(device_type, dict) else device_type.type_code
                    if type_code and type_code not in self._subscribed_types:
                        # 订阅特定品牌的topic：{type_code}/+/user/up
                        topic = f"{type_code}/+/user/up"
                        
                        logger.info(f"正在订阅设备类型 {type_code} 的topic...")
                        result, mid = self.client.subscribe(topic, qos=1)
                        logger.info(f"订阅 {topic}: rc={result}, mid={mid}")
                        
                        if result == 0:
                            logger.info("=" * 60)
                            logger.info(f"✓ 已订阅设备类型topic: {topic} (MID: {mid}) (类型: {type_code})")
                            logger.info(f"  说明: 通配符 + 会匹配该类型的所有设备，例如: {type_code}/861076087029615/user/up")
                            logger.info("=" * 60)
                        else:
                            logger.warning("=" * 60)
                            logger.warning(f"✗ 订阅设备类型topic失败: {topic} (rc: {result}) (类型: {type_code})")
                            logger.warning("=" * 60)
                        self._subscribed_types.add(type_code)
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"动态订阅设备类型失败: {e}，将使用通用通配符订阅")
    
    async def stop(self) -> None:
        """停止 MQTT 客户端"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None
            self._connected_chargers.clear()
            self._pending_responses.clear()
            self._subscribed_types.clear()
            logger.info("MQTT 传输适配器已停止")
    
    def _on_connect(self, client: mqtt.Client, userdata, flags, rc):
        """MQTT 连接回调"""
        if rc == 0:
            self._mqtt_connected = True
            logger.info("=" * 60)
            logger.info("MQTT 连接成功 - 连接信息详情")
            logger.info("=" * 60)
            logger.info(f"Broker 地址: {self.broker_host}:{self.broker_port}")
            logger.info(f"客户端 ID: {client._client_id}")
            logger.info(f"协议版本: MQTTv311")
            logger.info(f"连接标志 (flags):")
            logger.info(f"  - session present: {flags.get('session present', False)}")
            logger.info(f"  - clean session: {client._clean_session}")
            logger.info(f"Keepalive: {client._keepalive} 秒")
            logger.info(f"返回码 (rc): {rc} (0=成功)")
            logger.info("=" * 60)
            
            # 连接成功后立即订阅（必须在连接建立后才能订阅）
            try:
                # 订阅所有设备类型的up主题（使用通配符）
                # 格式：{type_code}/{serial_number}/user/up
                # 使用通配符：+/+/user/up 匹配所有品牌的设备
                logger.info("开始订阅通用topic...")
                result, mid = client.subscribe("+/+/user/up", qos=1)
                logger.info(f"订阅 +/+/user/up: rc={result}, mid={mid}")
                
                if result == 0:
                    logger.info("=" * 60)
                    logger.info("✓ 已订阅通用topic: +/+/user/up (MID: {}) (支持所有品牌)".format(mid))
                    logger.info("  说明: 通配符 + 会匹配所有设备，例如: zcf/861076087029615/user/up")
                    logger.info("=" * 60)
                else:
                    logger.warning("=" * 60)
                    logger.warning("✗ 订阅通用topic失败: +/+/user/up (rc: {})".format(result))
                    logger.warning("=" * 60)
                
                # 动态订阅所有激活的设备类型（异步执行）
                if self._loop and self._loop.is_running():
                    logger.info("开始动态订阅设备类型...")
                    asyncio.run_coroutine_threadsafe(
                        self._subscribe_all_device_types(),
                        self._loop
                    )
                else:
                    logger.warning("事件循环不可用，无法执行动态订阅")
            except Exception as e:
                logger.error(f"订阅topic时出错: {e}", exc_info=True)
                import traceback
                traceback.print_exc()
        else:
            logger.error("=" * 60)
            logger.error("MQTT 连接失败 - 连接信息详情")
            logger.error("=" * 60)
            logger.error(f"Broker 地址: {self.broker_host}:{self.broker_port}")
            logger.error(f"客户端 ID: {client._client_id}")
            logger.error(f"返回码 (rc): {rc}")
            error_messages = {
                1: "连接被拒绝 - 协议版本不正确",
                2: "连接被拒绝 - 客户端标识符无效",
                3: "连接被拒绝 - 服务器不可用",
                4: "连接被拒绝 - 用户名或密码错误",
                5: "连接被拒绝 - 未授权"
            }
            logger.error(f"错误说明: {error_messages.get(rc, '未知错误')}")
            logger.error("=" * 60)
    
    def _on_message(self, client: mqtt.Client, userdata, msg):
        """MQTT 消息接收回调"""
        try:
            topic = msg.topic
            # 处理前导斜杠：去除前导斜杠以便统一处理
            topic_normalized = topic.lstrip("/")
            topic_parts = topic_normalized.split("/")
            
            # 解析新格式：{type_code}/{serial_number}/user/up
            # 支持格式：zcf/861076087029615/user/up 或 /zcf/861076087029615/user/up
            if len(topic_parts) != 4:
                logger.warning(f"无效的 MQTT 主题格式: {topic}，期望格式: {{type_code}}/{{serial_number}}/user/up 或 /{{type_code}}/{{serial_number}}/user/up")
                logger.warning(f"消息详情: QoS={msg.qos}, MID={msg.mid}, Retain={msg.retain}, Payload长度={len(msg.payload)}")
                return
            
            type_code = topic_parts[0]
            serial_number = topic_parts[1]
            category = topic_parts[2]
            direction = topic_parts[3]
            
            # 验证topic格式
            if category != "user" or direction != "up":
                logger.warning(f"无效的 MQTT 主题格式: {topic}，期望: {{type_code}}/{{serial_number}}/user/up")
                logger.warning(f"消息详情: QoS={msg.qos}, MID={msg.mid}, Retain={msg.retain}, Payload长度={len(msg.payload)}")
                return
            
            # 从serial_number获取charge_point_id（如果设备关联了充电桩）
            charge_point_id = self._get_charge_point_id_from_serial(serial_number)
            if not charge_point_id:
                # 如果没有关联充电桩，使用serial_number作为charge_point_id
                charge_point_id = serial_number
            
            # 解析消息payload
            # 支持两种格式：
            # 1. 简化格式: {"action": "BootNotification", "payload": {...}}
            # 2. OCPP 1.6 标准格式: [MessageType, UniqueId, Action, Payload]
            raw_payload = json.loads(msg.payload.decode())
            
            unique_id = None  # 用于保存 OCPP 标准格式的 UniqueId
            is_ocpp_standard_format = False
            
            if isinstance(raw_payload, list) and len(raw_payload) >= 3:
                # OCPP 1.6 标准格式: [MessageType, UniqueId, ...]
                # MessageType: 2 = CALL (充电桩发送给服务器的请求)
                # MessageType: 3 = CALLRESULT (充电桩响应服务器的请求)
                # MessageType: 4 = CALLERROR (充电桩响应服务器的请求，错误)
                message_type = raw_payload[0]
                unique_id = raw_payload[1]
                
                # 处理 CALLRESULT (MessageType=3): [3, UniqueId, Payload]
                if message_type == 3:
                    if unique_id in self._pending_responses:
                        future = self._pending_responses.pop(unique_id)
                        payload_data = raw_payload[2] if len(raw_payload) > 2 else {}
                        if not future.done():
                            future.set_result(payload_data)
                        logger.info(f"[{charge_point_id}] <- MQTT CALLRESULT (UniqueId: {unique_id}, 品牌: {type_code}, SN: {serial_number}) | payload: {payload_data}")
                    else:
                        logger.warning(f"[{charge_point_id}] 收到未预期的 CALLRESULT (UniqueId: {unique_id})")
                    return
                
                # 处理 CALLERROR (MessageType=4): [4, UniqueId, ErrorCode, ErrorDescription, ErrorDetails(可选)]
                if message_type == 4:
                    if unique_id in self._pending_responses:
                        future = self._pending_responses.pop(unique_id)
                        error_code = raw_payload[2] if len(raw_payload) > 2 else "UnknownError"
                        error_description = raw_payload[3] if len(raw_payload) > 3 else "Unknown error"
                        error_details = raw_payload[4] if len(raw_payload) > 4 else None
                        if not future.done():
                            future.set_exception(Exception(f"{error_code}: {error_description}"))
                        logger.warning(f"[{charge_point_id}] <- MQTT CALLERROR (UniqueId: {unique_id}, ErrorCode: {error_code}, 品牌: {type_code}, SN: {serial_number})")
                    else:
                        logger.warning(f"[{charge_point_id}] 收到未预期的 CALLERROR (UniqueId: {unique_id})")
                    return
                
                # 处理 CALL (MessageType=2): [2, UniqueId, Action, Payload]
                if message_type == 2:
                    if len(raw_payload) < 4:
                        logger.error(f"[{charge_point_id}] 无效的 CALL 消息格式，长度不足: {raw_payload}")
                        return
                else:
                    logger.error(f"[{charge_point_id}] 无效的 MessageType: {message_type}, 期望 2 (CALL), 3 (CALLRESULT), 或 4 (CALLERROR), 消息: {raw_payload}")
                    return
                
                # 验证 UniqueId 必须是字符串
                unique_id = raw_payload[1]
                if not isinstance(unique_id, str):
                    logger.error(f"[{charge_point_id}] 无效的 UniqueId 类型: {type(unique_id)}, 期望字符串, UniqueId: {unique_id}")
                    return
                
                # 验证 Action 必须是字符串
                action = raw_payload[2]
                if not isinstance(action, str):
                    logger.error(f"[{charge_point_id}] 无效的 Action 类型: {type(action)}, 期望字符串, Action: {action}")
                    return
                
                # 验证 Payload 必须是对象
                payload_data = raw_payload[3] if isinstance(raw_payload[3], dict) else {}
                if not isinstance(raw_payload[3], dict):
                    logger.warning(f"[{charge_point_id}] Payload 不是对象类型，使用空对象")
                
                is_ocpp_standard_format = True
                
                logger.info(f"[{charge_point_id}] <- MQTT OCPP {action} (标准格式, MessageType={message_type}, UniqueId={unique_id}, 品牌: {type_code}, SN: {serial_number}, Topic: {topic}) | payload: {payload_data}")
            elif isinstance(raw_payload, dict):
                # 简化格式: {"action": "...", "payload": {...}}
                action = raw_payload.get("action", "")
                payload_data = raw_payload.get("payload", {})
                
                logger.info(f"[{charge_point_id}] <- MQTT OCPP {action} (简化格式, 品牌: {type_code}, SN: {serial_number}, Topic: {topic}) | payload: {payload_data}")
            else:
                logger.error(f"[{charge_point_id}] 无效的消息格式: {raw_payload}, 期望数组或对象")
                return
            
            # 检查是否是第一次连接（新设备）
            is_first_connection = charge_point_id not in self._connected_chargers
            
            # 标记充电桩已连接
            self._connected_chargers.add(charge_point_id)
            
            if is_first_connection:
                # 第一次连接时，打印详细的连接信息
                logger.info("=" * 60)
                logger.info(f"🔌 新设备首次连接 - {charge_point_id}")
                logger.info("=" * 60)
                logger.info(f"设备信息:")
                logger.info(f"  - 充电桩ID: {charge_point_id}")
                logger.info(f"  - 设备类型代码: {type_code}")
                logger.info(f"  - 设备序列号: {serial_number}")
                logger.info(f"MQTT 消息包信息:")
                logger.info(f"  - 消息主题: {topic}")
                logger.info(f"  - 主题格式: {type_code}/{serial_number}/user/up")
                logger.info(f"  - QoS: {msg.qos}")
                logger.info(f"  - 消息ID (MID): {msg.mid}")
                logger.info(f"  - 保留标志 (Retain): {msg.retain}")
                logger.info(f"  - 原始Payload长度: {len(msg.payload)} 字节")
                logger.info(f"  - Payload (原始): {msg.payload.hex()[:100]}..." if len(msg.payload) > 50 else f"  - Payload (原始): {msg.payload.hex()}")
                logger.info(f"消息内容:")
                logger.info(f"  - Action: {action}")
                logger.info(f"  - Payload (JSON):")
                # 格式化 JSON 输出，每行缩进
                payload_str = json.dumps(payload_data, ensure_ascii=False, indent=4)
                for line in payload_str.split('\n'):
                    logger.info(f"    {line}")
                logger.info(f"连接状态:")
                logger.info(f"  - 当前已连接充电桩总数: {len(self._connected_chargers)} 个")
                logger.info(f"  - 连接时间戳: {msg.timestamp if hasattr(msg, 'timestamp') else 'N/A'}")
                logger.info("=" * 60)
            else:
                logger.info(f"[{charge_point_id}] 已标记为已连接（MQTT），当前已连接充电桩: {len(self._connected_chargers)} 个")
            
            # 异步处理消息
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._handle_message(charge_point_id, action, payload_data, type_code, serial_number, unique_id, is_ocpp_standard_format),
                    self._loop
                )
            else:
                logger.warning(f"[{charge_point_id}] 事件循环不可用，无法处理 MQTT 消息")
                
        except json.JSONDecodeError as e:
            logger.error(f"MQTT 消息JSON解析错误: {e}, topic: {topic}, payload: {msg.payload}")
        except Exception as e:
            logger.error(f"MQTT 消息处理错误: {e}", exc_info=True)
    
    def _get_charge_point_id_from_serial(self, serial_number: str) -> Optional[str]:
        """根据设备SN号获取充电桩ID（charge_point_id）"""
        try:
            from app.database.base import SessionLocal
            from app.core.mqtt_auth import MQTTAuthService
            
            db = SessionLocal()
            try:
                charge_point_id = MQTTAuthService.get_charge_point_id_from_serial(db, serial_number)
                return charge_point_id or serial_number
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"获取充电桩ID失败: {e}，使用serial_number作为charge_point_id")
            return serial_number
    
    async def _handle_message(
        self, 
        charge_point_id: str, 
        action: str, 
        payload: Dict[str, Any],
        type_code: str,
        serial_number: str,
        unique_id: Optional[str] = None,
        is_ocpp_standard_format: bool = False
    ):
        """处理接收到的消息"""
        logger.info(f"[{charge_point_id}] MQTT 开始处理消息: {action}")
        try:
            # 传递device_serial_number参数
            response = await self.handle_incoming_message(
                charge_point_id=charge_point_id,
                action=action,
                payload=payload,
                device_serial_number=serial_number,
                evse_id=1  # 默认EVSE ID为1
            )
            logger.info(f"[{charge_point_id}] MQTT 消息处理完成: {action}, 响应: {response}")
        except Exception as e:
            logger.error(f"[{charge_point_id}] MQTT 消息处理失败: {action}, 错误: {e}", exc_info=True)
            # 返回符合 OCPP 规范的错误格式
            response = {
                "errorCode": "InternalError",
                "errorDescription": str(e)
            }
        
        # 发送响应到down主题：{type_code}/{serial_number}/user/down
        response_topic = f"{type_code}/{serial_number}/user/down"
        
        # 根据请求格式决定响应格式
        if is_ocpp_standard_format and unique_id:
            # OCPP 1.6 标准格式响应
            # 检查响应是否包含错误
            if "errorCode" in response or "error" in response or response.get("status") == "Rejected":
                # CALLERROR: [4, UniqueId, ErrorCode, ErrorDescription, ErrorDetails(可选)]
                error_code = response.get("errorCode", "InternalError")
                error_description = response.get("errorDescription", response.get("error", "Unknown error"))
                error_details = response.get("errorDetails")
                
                if error_details:
                    response_message = [4, unique_id, error_code, error_description, error_details]
                else:
                    response_message = [4, unique_id, error_code, error_description]
                logger.warning(f"[{charge_point_id}] 使用 OCPP 标准格式响应 (CALLERROR): {error_code}")
            else:
                # CALLRESULT: [3, UniqueId, Payload]
                response_message = [3, unique_id, response]
                logger.info(f"[{charge_point_id}] 使用 OCPP 标准格式响应 (CALLRESULT)")
        else:
            # 简化格式响应: {"action": "...", "response": {...}}
            response_message = {
                "action": action,
                "response": response
            }
            logger.info(f"[{charge_point_id}] 使用简化格式响应")
        
        if self.client:
            self.client.publish(
                response_topic,
                json.dumps(response_message),
                qos=1
            )
            logger.info(f"[{charge_point_id}] -> MQTT OCPP {action} Response 已发送到主题: {response_topic}, 响应: {response}")
    
    def _on_disconnect(self, client: mqtt.Client, userdata, rc):
        """MQTT 断开连接回调"""
        self._mqtt_connected = False
        logger.warning(f"MQTT 断开连接，返回码: {rc}")
    
    async def send_message(
        self,
        charge_point_id: str,
        action: str,
        payload: Dict[str, Any],
        timeout: float = 5.0
    ) -> Dict[str, Any]:
        """发送消息到设备（服务器请求）"""
        if not self.client:
            raise ConnectionError("MQTT 客户端未连接")
        
        # 从charge_point_id获取设备信息（type_code和serial_number）
        device_info = self._get_device_info_from_charge_point_id(charge_point_id)
        
        if not device_info:
            raise ValueError(f"无法找到设备信息，charge_point_id: {charge_point_id}")
        
        type_code = device_info["type_code"]
        serial_number = device_info["serial_number"]
        
        # 构建topic：{type_code}/{serial_number}/user/down
        topic = f"{type_code}/{serial_number}/user/down"
        
        # 使用 OCPP 1.6 标准格式发送服务器请求
        # CALL: [2, UniqueId, Action, Payload]
        import uuid
        unique_id = f"csms_{uuid.uuid4().hex[:16]}"
        message = [2, unique_id, action, payload]
        
        logger.debug(f"[{charge_point_id}] MQTT 发送服务器请求到主题: {topic}, 消息: {json.dumps(message)}")
        
        # 创建 Future 用于等待响应
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        
        future = self._loop.create_future()
        self._pending_responses[unique_id] = future
        
        try:
            result = self.client.publish(
                topic,
                json.dumps(message),
                qos=1
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"[{charge_point_id}] -> MQTT OCPP {action} (UniqueId: {unique_id}, 发送到主题: {topic})")
                
                # 等待响应
                try:
                    response_payload = await asyncio.wait_for(future, timeout=timeout)
                    logger.info(f"[{charge_point_id}] <- MQTT OCPP {action} 响应 (UniqueId: {unique_id}): {response_payload}")
                    return response_payload
                except asyncio.TimeoutError:
                    # 超时，移除 Future
                    self._pending_responses.pop(unique_id, None)
                    logger.warning(f"[{charge_point_id}] MQTT OCPP {action} 响应超时 (UniqueId: {unique_id}, 超时: {timeout}秒)")
                    raise TimeoutError(f"等待 {action} 响应超时 ({timeout}秒)")
                except Exception as e:
                    # 其他错误（如 CALLERROR），移除 Future
                    self._pending_responses.pop(unique_id, None)
                    logger.error(f"[{charge_point_id}] MQTT OCPP {action} 响应错误 (UniqueId: {unique_id}): {e}")
                    raise
            else:
                # 发布失败，移除 Future
                self._pending_responses.pop(unique_id, None)
                logger.error(f"[{charge_point_id}] MQTT 发布失败，返回码: {result.rc}")
                raise ConnectionError(f"MQTT 发布失败，返回码: {result.rc}")
                
        except Exception as e:
            # 发生错误，移除 Future
            self._pending_responses.pop(unique_id, None)
            logger.error(f"[{charge_point_id}] MQTT 发送错误: {e}", exc_info=True)
            raise
    
    def _get_device_info_from_charge_point_id(self, charge_point_id: str) -> Optional[Dict[str, str]]:
        """根据charge_point_id获取设备信息（type_code和serial_number）"""
        try:
            from app.database.base import SessionLocal
            from app.core.mqtt_auth import MQTTAuthService
            
            db = SessionLocal()
            try:
                return MQTTAuthService.get_device_info_from_charge_point_id(db, charge_point_id)
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"获取设备信息失败: {e}")
            return None
    
    def is_connected(self, charge_point_id: str) -> bool:
        """检查充电桩是否已连接"""
        return charge_point_id in self._connected_chargers
