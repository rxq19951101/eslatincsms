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
                 broker_port: int = 1883, topic_prefix: str = "ocpp",
                 username: Optional[str] = None, password: Optional[str] = None):
        self.charger_id = charger_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic_prefix = topic_prefix
        self.prefix = f"[{charger_id}]"
        
        # MQTT 主题
        self.request_topic = f"{topic_prefix}/{charger_id}/requests"   # 充电桩发送
        self.response_topic = f"{topic_prefix}/{charger_id}/responses"  # CSMS 发送
        
        # 生成设备信息
        charger_hash = int(hashlib.md5(charger_id.encode()).hexdigest()[:8], 16)
        vendor_idx = charger_hash % len(self.VENDOR_MODELS)
        self.vendor, self.model = self.VENDOR_MODELS[vendor_idx]
        self.serial_number = f"{self.vendor[:3].upper()}-{charger_hash % 10000:04d}"
        self.firmware_version = f"1.{charger_hash % 10}.{charger_hash % 100}"
        
        # 状态管理
        self.status = ChargerStatus.UNAVAILABLE
        self.transaction_id: Optional[int] = None
        self.current_id_tag: Optional[str] = None
        self.meter_value = 0
        self.message_id_counter = 1
        
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
            # 订阅响应主题（接收 CSMS 消息）
            client.subscribe(self.response_topic, qos=1)
            print(f"{self.prefix}   订阅主题: {self.response_topic}")
        else:
            print(f"{self.prefix} ✗ MQTT 连接失败，返回码: {rc}")
            sys.exit(1)
    
    def _on_message(self, client: mqtt.Client, userdata, msg):
        """MQTT 消息接收回调"""
        try:
            payload = json.loads(msg.payload.decode())
            action = payload.get("action", "")
            response = payload.get("response", {})
            
            print(f"{self.prefix} ← MQTT {action} Response: {json.dumps(response)}")
            
            # 处理响应
            asyncio.run_coroutine_threadsafe(
                self._handle_response(action, response),
                self.loop
            )
        except Exception as e:
            print(f"{self.prefix} ✗ 消息处理错误: {e}")
    
    def _on_disconnect(self, client: mqtt.Client, userdata, rc):
        """MQTT 断开连接回调"""
        if rc != 0:
            print(f"{self.prefix} ⚠ MQTT 意外断开，返回码: {rc}")
        else:
            print(f"{self.prefix} MQTT 已断开")
    
    async def _handle_response(self, action: str, response: Dict[str, Any]):
        """处理 CSMS 响应"""
        if action == "RemoteStartTransaction":
            if response.get("status") == "Accepted":
                self.status = ChargerStatus.CHARGING
                self.transaction_id = response.get("transactionId")
                print(f"{self.prefix} → 开始充电，交易ID: {self.transaction_id}")
                # 开始发送计量值
                asyncio.create_task(self._meter_values_loop())
        
        elif action == "RemoteStopTransaction":
            if response.get("status") == "Accepted":
                self.status = ChargerStatus.AVAILABLE
                self.transaction_id = None
                print(f"{self.prefix} → 停止充电")
    
    def _send_message(self, action: str, payload: Optional[Dict[str, Any]] = None):
        """发送 OCPP 消息到 CSMS"""
        message = {
            "action": action
        }
        if payload:
            message["payload"] = payload
        
        try:
            result = self.client.publish(
                self.request_topic,
                json.dumps(message),
                qos=1
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"{self.prefix} → MQTT {action} {json.dumps(payload) if payload else ''}")
            else:
                print(f"{self.prefix} ✗ 消息发送失败，返回码: {result.rc}")
        except Exception as e:
            print(f"{self.prefix} ✗ 发送错误: {e}")
    
    async def _meter_values_loop(self):
        """充电时定期发送计量值"""
        while self.status == ChargerStatus.CHARGING:
            await asyncio.sleep(10)  # 每10秒发送一次
            if self.status == ChargerStatus.CHARGING:
                self.meter_value += random.randint(100, 500)  # 增加电量（Wh）
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
        
        # 发送 BootNotification
        self._send_message("BootNotification", {
            "chargePointVendor": self.vendor,
            "chargePointModel": self.model,
            "firmwareVersion": self.firmware_version,
            "chargePointSerialNumber": self.serial_number
        })
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
    parser = argparse.ArgumentParser(description="MQTT OCPP 1.6 充电桩模拟器")
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
        "--topic-prefix",
        type=str,
        default="ocpp",
        help="MQTT 主题前缀 (默认: ocpp)"
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
    
    args = parser.parse_args()
    
    if not MQTT_AVAILABLE:
        print("错误: paho-mqtt 未安装")
        print("请运行: pip install paho-mqtt")
        sys.exit(1)
    
    simulator = MQTTOCPPSimulator(
        charger_id=args.id,
        broker_host=args.broker,
        broker_port=args.port,
        topic_prefix=args.topic_prefix,
        username=args.username,
        password=args.password
    )
    
    try:
        asyncio.run(simulator.run())
    except KeyboardInterrupt:
        print("\n模拟器已停止")


if __name__ == "__main__":
    main()

