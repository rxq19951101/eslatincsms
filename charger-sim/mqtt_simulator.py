#!/usr/bin/env python3
#
# MQTT OCPP 1.6 充电桩模拟器
# 支持通过 MQTT 协议与 CSMS 通信
#

import argparse
import asyncio
import json
import sys
import uuid
import hashlib
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from enum import Enum

import qrcode

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("错误: paho-mqtt 未安装，请运行: pip install paho-mqtt")
    sys.exit(1)


class ChargerStatus(Enum):
    """充电桩状态"""
    AVAILABLE = "Available"
    PREPARING = "Preparing"
    CHARGING = "Charging"
    SUSPENDED_EVSE = "SuspendedEVSE"
    SUSPENDED_EV = "SuspendedEV"
    FINISHING = "Finishing"
    RESERVED = "Reserved"
    UNAVAILABLE = "Unavailable"
    FAULTED = "Faulted"


class MQTTOCPPSimulator:
    """MQTT OCPP 1.6 充电桩模拟器"""
    
    VENDOR_MODELS = [
        ("Tesla", "Supercharger V3"),
        ("ABB", "Terra AC"),
        ("Schneider Electric", "EVlink Charging Station"),
        ("Siemens", "VersiCharge"),
        ("ChargePoint", "CPF50"),
    ]
    
    def __init__(self, charger_id: str, broker_host: str = "localhost", 
                 broker_port: int = 1883, type_code: str = "zcf",
                 serial_number: Optional[str] = None,
                 username: Optional[str] = None, password: Optional[str] = None,
                 charging_power_kw: float = 7.0):
        self.charger_id = charger_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.type_code = type_code  # 设备类型代码（如 zcf, tesla）
        self.prefix = f"[{charger_id}]"
        
        # 生成设备信息（用于厂商、型号等）
        charger_hash = int(hashlib.md5(charger_id.encode()).hexdigest()[:8], 16)
        vendor_idx = charger_hash % len(self.VENDOR_MODELS)
        self.vendor, self.model = self.VENDOR_MODELS[vendor_idx]
        self.firmware_version = f"1.{charger_hash % 10}.{charger_hash % 100}"
        
        # 生成或使用提供的序列号
        if serial_number:
            self.serial_number = serial_number
        else:
            # 如果没有提供序列号，从 charger_id 生成一个（使用15位数字）
            charger_hash_full = int(hashlib.md5(charger_id.encode()).hexdigest()[:15], 16)
            self.serial_number = str(charger_hash_full)
        
        # MQTT 主题（新格式）
        # 设备发送消息到: {type_code}/{serial_number}/user/up
        self.up_topic = f"{type_code}/{self.serial_number}/user/up"
        # 设备订阅接收: {type_code}/{serial_number}/user/down
        self.down_topic = f"{type_code}/{self.serial_number}/user/down"
        
        # 状态管理
        self.status = ChargerStatus.UNAVAILABLE
        self.transaction_id: Optional[int] = None
        self.current_id_tag: Optional[str] = None
        self.meter_value = 0  # 电表值（Wh）
        self.message_id_counter = 1
        
        # 充电功率（kW），默认 7kW
        self.charging_power_kw = charging_power_kw
        # 电表上报间隔（秒），默认 10 秒
        self.meter_report_interval = 10
        
        # MQTT 客户端
        self.client = mqtt.Client(client_id=f"charger_{charger_id}", protocol=mqtt.MQTTv311)
        if username and password:
            self.client.username_pw_set(username, password)
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        # 消息队列（用于等待响应）
        self.pending_responses: Dict[str, asyncio.Future] = {}
        self.loop = None
    
    def _on_connect(self, client: mqtt.Client, userdata, flags, rc):
        """MQTT 连接回调"""
        if rc == 0:
            print(f"{self.prefix} ✓ MQTT 连接成功")
            print(f"{self.prefix}   设备类型: {self.type_code}")
            print(f"{self.prefix}   序列号: {self.serial_number}")
            # 订阅 down 主题（接收 CSMS 的响应和请求）
            client.subscribe(self.down_topic, qos=1)
            print(f"{self.prefix}   订阅主题: {self.down_topic} (接收服务器消息)")
            print(f"{self.prefix}   发送主题: {self.up_topic} (发送消息到服务器)")
        else:
            print(f"{self.prefix} ✗ MQTT 连接失败，返回码: {rc}")
            sys.exit(1)
    
    def _on_message(self, client: mqtt.Client, userdata, msg):
        """MQTT 消息接收回调"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            # 充电桩订阅 down 主题，接收服务器的响应和请求
            if topic == self.down_topic:
                # 检查是响应还是请求（通过消息格式判断）
                action = payload.get("action", "")
                
                if "response" in payload:
                    # 这是来自服务器的响应（针对之前发送的请求）
                    response = payload.get("response", {})
                    
                    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    print(f"{self.prefix} ← [{timestamp}] 收到服务器响应: {action}")
                    print(f"{self.prefix}    主题: {topic}")
                    print(f"{self.prefix}    响应: {json.dumps(response, ensure_ascii=False)}")
                    
                    # 处理响应
                    asyncio.run_coroutine_threadsafe(
                        self._handle_response(action, response),
                        self.loop
                    )
                elif "payload" in payload:
                    # 这是来自服务器的请求（CSMS 主动发送的请求）
                    request_payload = payload.get("payload", {})
                    from_sender = payload.get("from", "csms")
                    
                    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    print(f"{self.prefix} ← [{timestamp}] 收到服务器请求: {action}")
                    print(f"{self.prefix}    来源: {from_sender}")
                    print(f"{self.prefix}    主题: {topic}")
                    print(f"{self.prefix}    载荷: {json.dumps(request_payload, ensure_ascii=False)}")
                    
                    # 处理请求
                    asyncio.run_coroutine_threadsafe(
                        self._handle_request(action, request_payload),
                        self.loop
                    )
            else:
                print(f"{self.prefix} ⚠ 收到未知主题的消息: {topic}")
        except Exception as e:
            print(f"{self.prefix} ✗ 消息处理错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_disconnect(self, client: mqtt.Client, userdata, rc):
        """MQTT 断开连接回调"""
        if rc != 0:
            print(f"{self.prefix} ⚠ MQTT 意外断开，返回码: {rc}")
        else:
            print(f"{self.prefix} MQTT 已断开")
    
    async def _handle_request(self, action: str, payload: Dict[str, Any]):
        """处理来自 CSMS 的请求"""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"{self.prefix} → [{timestamp}] 开始处理服务器请求: {action}")
        
        response = None
        
        if action == "RemoteStartTransaction":
            id_tag = payload.get("idTag", "")
            connector_id = payload.get("connectorId", 1)
            print(f"{self.prefix}    请求参数: idTag={id_tag}, connectorId={connector_id}")
            
            # 生成交易ID
            self.transaction_id = int(datetime.now(timezone.utc).timestamp())
            self.current_id_tag = id_tag
            self.status = ChargerStatus.CHARGING
            self.meter_value = 0
            
            # 发送 StartTransaction
            self._send_message("StartTransaction", {
                "connectorId": connector_id,
                "idTag": id_tag,
                "meterStart": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # 发送 StatusNotification
            self._send_message("StatusNotification", {
                "connectorId": connector_id,
                "errorCode": "NoError",
                "status": ChargerStatus.CHARGING.value
            })
            
            # 开始发送计量值
            asyncio.create_task(self._meter_values_loop())
            
            response = {
                "status": "Accepted",
                "transactionId": self.transaction_id
            }
            print(f"{self.prefix}    响应: 接受远程启动，交易ID={self.transaction_id}")
        
        elif action == "RemoteStopTransaction":
            transaction_id = payload.get("transactionId")
            print(f"{self.prefix}    请求参数: transactionId={transaction_id}")
            
            if self.status == ChargerStatus.CHARGING and self.transaction_id:
                # 发送 StopTransaction
                self._send_message("StopTransaction", {
                    "transactionId": self.transaction_id,
                    "meterStop": self.meter_value,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": "Remote"
                })
                
                # 发送 StatusNotification
                self._send_message("StatusNotification", {
                    "connectorId": 1,
                    "errorCode": "NoError",
                    "status": ChargerStatus.AVAILABLE.value
                })
                
                self.status = ChargerStatus.AVAILABLE
                self.transaction_id = None
                self.current_id_tag = None
                
                response = {"status": "Accepted"}
                print(f"{self.prefix}    响应: 接受远程停止")
            else:
                response = {"status": "Rejected"}
                print(f"{self.prefix}    响应: 拒绝（当前未在充电状态）")
        
        elif action == "ChangeConfiguration":
            key = payload.get("key", "")
            value = payload.get("value", "")
            print(f"{self.prefix}    请求参数: key={key}, value={value}")
            response = {"status": "Accepted"}
            print(f"{self.prefix}    响应: 配置已更改")
        
        elif action == "GetConfiguration":
            keys = payload.get("keys", [])
            print(f"{self.prefix}    请求参数: keys={keys}")
            response = {"configurationKey": []}
            print(f"{self.prefix}    响应: 返回配置列表")
        
        elif action == "Reset":
            reset_type = payload.get("type", "Hard")
            print(f"{self.prefix}    请求参数: type={reset_type}")
            response = {"status": "Accepted"}
            print(f"{self.prefix}    响应: 接受重置请求")
        
        elif action == "UnlockConnector":
            connector_id = payload.get("connectorId", 1)
            print(f"{self.prefix}    请求参数: connectorId={connector_id}")
            response = {"status": "Unlocked"}
            print(f"{self.prefix}    响应: 连接器已解锁")
        
        elif action == "ChangeAvailability":
            connector_id = payload.get("connectorId", 1)
            availability_type = payload.get("type", "Inoperative")
            print(f"{self.prefix}    请求参数: connectorId={connector_id}, type={availability_type}")
            response = {"status": "Accepted"}
            print(f"{self.prefix}    响应: 可用性已更改")
        
        else:
            print(f"{self.prefix}    ⚠ 未知请求类型: {action}")
            response = {"status": "NotSupported"}
        
        # 发送响应（通过 up 主题发送，格式与发送请求相同）
        if response:
            response_message = {
                "action": action,
                "response": response
            }
            try:
                result = self.client.publish(
                    self.up_topic,
                    json.dumps(response_message),
                    qos=1
                )
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    print(f"{self.prefix} → [{timestamp}] 已发送响应: {action}")
                    print(f"{self.prefix}    主题: {self.up_topic}")
                else:
                    print(f"{self.prefix} ✗ 响应发送失败，返回码: {result.rc}")
            except Exception as e:
                print(f"{self.prefix} ✗ 发送响应错误: {e}")
    
    async def _handle_response(self, action: str, response: Dict[str, Any]):
        """处理 CSMS 响应（保留向后兼容）"""
        # 这个函数现在主要用于处理之前发送的消息的响应
        # 实际请求处理在 _handle_request 中
        pass
    
    def _send_message(self, action: str, payload: Optional[Dict[str, Any]] = None):
        """发送 OCPP 消息到 CSMS（通过 up 主题）"""
        message = {
            "action": action
        }
        if payload:
            message["payload"] = payload
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        try:
            result = self.client.publish(
                self.up_topic,
                json.dumps(message),
                qos=1
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"{self.prefix} → [{timestamp}] 发送消息到服务器: {action}")
                if payload:
                    print(f"{self.prefix}    主题: {self.up_topic}")
                    print(f"{self.prefix}    载荷: {json.dumps(payload, ensure_ascii=False)}")
            else:
                print(f"{self.prefix} ✗ [{timestamp}] 消息发送失败，返回码: {result.rc}")
        except Exception as e:
            print(f"{self.prefix} ✗ [{timestamp}] 发送错误: {e}")
            import traceback
            traceback.print_exc()
    
    async def _meter_values_loop(self):
        """充电时定期发送计量值"""
        while self.status == ChargerStatus.CHARGING:
            await asyncio.sleep(self.meter_report_interval)
            if self.status == ChargerStatus.CHARGING:
                # 根据充电功率和时间间隔计算电量增量
                # 公式：电量（Wh）= 功率（kW）× 时间（小时）× 1000
                # 例如：7kW × (10秒 / 3600秒) × 1000 = 19.44 Wh
                energy_increment_wh = self.charging_power_kw * (self.meter_report_interval / 3600.0) * 1000
                # 添加小的随机波动（±2%）模拟实际充电
                variation = random.uniform(0.98, 1.02)
                self.meter_value += int(energy_increment_wh * variation)
                
                self._send_message("MeterValues", {
                    "connectorId": 1,
                    "transactionId": self.transaction_id,
                    "meterValue": [
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "sampledValue": [
                                {
                                    "value": str(self.meter_value),
                                    "context": "Sample.Periodic",
                                    "format": "Raw",
                                    "measurand": "Energy.Active.Import.Register",
                                    "unit": "Wh"
                                }
                            ]
                        }
                    ]
                })
    
    def print_qr_code(self):
        """打印二维码"""
        qr = qrcode.QRCode(version=1, box_size=2, border=1)
        qr.add_data(self.charger_id)
        qr.make(fit=True)
        
        print("\n" + "=" * 60)
        print(f"📱 充电桩二维码: {self.charger_id}")
        print("=" * 60)
        img = qr.make_image(fill_color="black", back_color="white")
        size = img.size[0]
        qr_str = ""
        for y in range(size):
            for x in range(size):
                pixel = img.getpixel((x, y))
                if pixel == 0:
                    qr_str += "██"
                else:
                    qr_str += "  "
            qr_str += "\n"
        print(qr_str)
        print("提示：使用 App 的扫码功能扫描上方二维码")
        print("=" * 60 + "\n")
    
    async def run(self):
        """运行模拟器"""
        # 显示二维码
        self.print_qr_code()
        
        # 设置事件循环
        self.loop = asyncio.get_event_loop()
        
        # 连接到 MQTT broker
        print(f"{self.prefix} 正在连接到 MQTT broker: {self.broker_host}:{self.broker_port}")
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"{self.prefix} ✗ 连接失败: {e}")
            sys.exit(1)
        
        # 等待连接建立
        await asyncio.sleep(1)
        
        # 发送 BootNotification（使用 OCPP 1.6 标准字段名）
        self._send_message("BootNotification", {
            "chargePointVendor": self.vendor,
            "chargePointModel": self.model,
            "firmwareVersion": self.firmware_version,
            "chargePointSerialNumber": self.serial_number
        })
        print(f"{self.prefix}   发送 BootNotification: vendor={self.vendor}, model={self.model}, "
              f"firmware={self.firmware_version}, serial={self.serial_number}")
        print(f"{self.prefix}   使用 MQTT 主题: {self.up_topic} (发送) / {self.down_topic} (接收)")
        await asyncio.sleep(1)
        
        # 发送 StatusNotification
        self.status = ChargerStatus.AVAILABLE
        self._send_message("StatusNotification", {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": self.status.value
        })
        await asyncio.sleep(1)
        
        print(f"{self.prefix} ✓ 初始化完成，进入在线模式")
        
        # 定期发送心跳
        try:
            while True:
                await asyncio.sleep(30)
                self._send_message("Heartbeat", {})
        except KeyboardInterrupt:
            print(f"\n{self.prefix} 正在停止...")
            self.client.loop_stop()
            self.client.disconnect()
            print(f"{self.prefix} 已停止")


def main():
    parser = argparse.ArgumentParser(description="MQTT OCPP 1.6 充电桩模拟器（新格式）")
    parser.add_argument(
        "--id",
        type=str,
        default="CP-MQTT-001",
        help="充电桩ID (默认: CP-MQTT-001)"
    )
    parser.add_argument(
        "--broker",
        type=str,
        default="localhost",
        help="MQTT broker 地址 (默认: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=1883,
        help="MQTT broker 端口 (默认: 1883)"
    )
    parser.add_argument(
        "--type-code",
        type=str,
        default="zcf",
        help="设备类型代码，如 zcf, tesla (默认: zcf)"
    )
    parser.add_argument(
        "--serial-number",
        type=str,
        default=None,
        help="设备序列号（可选，不提供则自动生成）"
    )
    parser.add_argument(
        "--username",
        type=str,
        default=None,
        help="MQTT 用户名（可选）"
    )
    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="MQTT 密码（可选）"
    )
    parser.add_argument(
        "--power",
        type=float,
        default=7.0,
        help="充电功率（kW），默认 7.0 kW"
    )
    
    args = parser.parse_args()
    
    if not MQTT_AVAILABLE:
        print("错误: paho-mqtt 未安装")
        print("请运行: pip install paho-mqtt")
        sys.exit(1)
    
    simulator = MQTTOCPPSimulator(
        charger_id=args.id,
        broker_host=args.broker,
        broker_port=args.port,
        type_code=args.type_code,
        serial_number=args.serial_number,
        username=args.username,
        password=args.password,
        charging_power_kw=args.power
    )
    
    try:
        asyncio.run(simulator.run())
    except KeyboardInterrupt:
        print("\n模拟器已停止")


if __name__ == "__main__":
    main()

