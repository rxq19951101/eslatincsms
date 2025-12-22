#!/usr/bin/env python3
#
# 用户行为模拟充电桩
# 模拟完整的用户充电流程：扫码 -> 授权 -> 开始充电 -> 充电过程 -> 停止充电
#

import argparse
import asyncio
import json
import sys
import uuid
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
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
    
    # 添加类属性以便在实例中访问
    @classmethod
    def get_enum(cls):
        return cls


class UserBehavior:
    """用户行为定义"""
    def __init__(self, user_id: str, id_tag: str, charging_duration_minutes: int = 30):
        self.user_id = user_id
        self.id_tag = id_tag
        self.charging_duration_minutes = charging_duration_minutes
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None


class UserBehaviorSimulator:
    """用户行为模拟充电桩"""
    
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
                 charging_power_kw: float = 7.0):
        self.charger_id = charger_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.type_code = type_code
        self.prefix = f"[{charger_id}]"
        
        # 生成设备信息
        import hashlib
        charger_hash = int(hashlib.md5(charger_id.encode()).hexdigest()[:8], 16)
        vendor_idx = charger_hash % len(self.VENDOR_MODELS)
        self.vendor, self.model = self.VENDOR_MODELS[vendor_idx]
        self.firmware_version = f"1.{charger_hash % 10}.{charger_hash % 100}"
        
        # 生成或使用提供的序列号
        if serial_number:
            self.serial_number = serial_number
        else:
            charger_hash_full = int(hashlib.md5(charger_id.encode()).hexdigest()[:15], 16)
            self.serial_number = str(charger_hash_full).zfill(15)
        
        # MQTT 主题
        self.up_topic = f"{type_code}/{self.serial_number}/user/up"
        self.down_topic = f"{type_code}/{self.serial_number}/user/down"
        
        # 状态管理
        self.status = ChargerStatus.UNAVAILABLE
        self.ChargerStatus = ChargerStatus  # 保存枚举类引用
        self.transaction_id: Optional[int] = None
        self.current_id_tag: Optional[str] = None
        self.meter_value = 0  # 电表值（Wh）
        self.charging_power_kw = charging_power_kw
        self.meter_report_interval = 10  # 秒
        
        # 用户行为队列
        self.user_behaviors: List[UserBehavior] = []
        self.current_user: Optional[UserBehavior] = None
        self.behavior_task: Optional[asyncio.Task] = None
        
        # MQTT 客户端
        self.client = mqtt.Client(client_id=f"charger_{charger_id}", protocol=mqtt.MQTTv311)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        self.loop = None
    
    def _on_connect(self, client: mqtt.Client, userdata, flags, rc):
        """MQTT 连接回调"""
        if rc == 0:
            print(f"{self.prefix} ✓ MQTT 连接成功")
            client.subscribe(self.down_topic, qos=1)
            print(f"{self.prefix}   订阅主题: {self.down_topic}")
        else:
            print(f"{self.prefix} ✗ MQTT 连接失败，返回码: {rc}")
            sys.exit(1)
    
    def _on_message(self, client: mqtt.Client, userdata, msg):
        """MQTT 消息接收回调"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            if topic == self.down_topic:
                action = payload.get("action", "")
                
                if "response" in payload:
                    # 服务器响应
                    response = payload.get("response", {})
                    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    print(f"{self.prefix} ← [{timestamp}] 收到服务器响应: {action}")
                    
                    asyncio.run_coroutine_threadsafe(
                        self._handle_response(action, response),
                        self.loop
                    )
                elif "payload" in payload:
                    # 服务器请求
                    request_payload = payload.get("payload", {})
                    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    print(f"{self.prefix} ← [{timestamp}] 收到服务器请求: {action}")
                    
                    asyncio.run_coroutine_threadsafe(
                        self._handle_request(action, request_payload),
                        self.loop
                    )
        except Exception as e:
            print(f"{self.prefix} ✗ 消息处理错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_disconnect(self, client: mqtt.Client, userdata, rc):
        """MQTT 断开连接回调"""
        if rc != 0:
            print(f"{self.prefix} ⚠ MQTT 意外断开，返回码: {rc}")
    
    async def _handle_request(self, action: str, payload: Dict[str, Any]):
        """处理来自 CSMS 的请求"""
        response = None
        
        if action == "RemoteStartTransaction":
            id_tag = payload.get("idTag", "")
            connector_id = payload.get("connectorId", 1)
            
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
        
        elif action == "RemoteStopTransaction":
            transaction_id = payload.get("transactionId")
            
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
            else:
                response = {"status": "Rejected"}
        
        else:
            # 其他请求的默认响应
            response = {"status": "Accepted"}
        
        # 发送响应
        if response:
            response_message = {
                "action": action,
                "response": response
            }
            self.client.publish(
                self.up_topic,
                json.dumps(response_message),
                qos=1
            )
    
    async def _handle_response(self, action: str, response: Dict[str, Any]):
        """处理 CSMS 响应"""
        pass
    
    def _send_message(self, action: str, payload: Optional[Dict[str, Any]] = None):
        """发送 OCPP 消息到 CSMS"""
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
                print(f"{self.prefix} → [{timestamp}] 发送消息: {action}")
                if payload:
                    print(f"{self.prefix}    载荷: {json.dumps(payload, ensure_ascii=False)}")
        except Exception as e:
            print(f"{self.prefix} ✗ 发送错误: {e}")
    
    async def _meter_values_loop(self):
        """充电时定期发送计量值"""
        while self.status == ChargerStatus.CHARGING:
            await asyncio.sleep(self.meter_report_interval)
            if self.status == ChargerStatus.CHARGING:
                # 计算电量增量
                energy_increment_wh = self.charging_power_kw * (self.meter_report_interval / 3600.0) * 1000
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
    
    def add_user_behavior(self, user_id: str, id_tag: str, charging_duration_minutes: int = 30):
        """添加用户行为到队列"""
        behavior = UserBehavior(user_id, id_tag, charging_duration_minutes)
        self.user_behaviors.append(behavior)
        print(f"{self.prefix} 📝 添加用户行为: {user_id} ({id_tag}), 充电时长: {charging_duration_minutes}分钟")
    
    async def simulate_user_charging_flow(self, behavior: UserBehavior):
        """模拟用户充电流程"""
        print(f"\n{self.prefix} {'='*60}")
        print(f"{self.prefix} 🚗 开始模拟用户充电流程")
        print(f"{self.prefix}    用户ID: {behavior.user_id}")
        print(f"{self.prefix}    ID标签: {behavior.id_tag}")
        print(f"{self.prefix}    预计充电时长: {behavior.charging_duration_minutes}分钟")
        print(f"{self.prefix} {'='*60}\n")
        
        # 步骤1: 用户扫码（模拟）
        print(f"{self.prefix} 📱 步骤1: 用户扫码充电桩二维码")
        await asyncio.sleep(1)
        
        # 步骤2: 发送授权请求
        print(f"{self.prefix} 🔐 步骤2: 发送授权请求")
        self._send_message("Authorize", {
            "idTag": behavior.id_tag
        })
        await asyncio.sleep(2)
        
        # 步骤3: 等待用户插枪（模拟状态变化）
        print(f"{self.prefix} 🔌 步骤3: 用户插枪，状态变为Preparing")
        self.status = ChargerStatus.PREPARING
        self._send_message("StatusNotification", {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": ChargerStatus.PREPARING.value
        })
        await asyncio.sleep(2)
        
        # 步骤4: 开始充电（发送StartTransaction）
        print(f"{self.prefix} ⚡ 步骤4: 开始充电")
        self.transaction_id = int(datetime.now(timezone.utc).timestamp())
        self.current_id_tag = behavior.id_tag
        self.status = ChargerStatus.CHARGING
        self.meter_value = 0
        behavior.start_time = datetime.now(timezone.utc)
        
        self._send_message("StartTransaction", {
            "connectorId": 1,
            "idTag": behavior.id_tag,
            "meterStart": 0,
            "timestamp": behavior.start_time.isoformat()
        })
        
        self._send_message("StatusNotification", {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": ChargerStatus.CHARGING.value
        })
        
        # 开始发送计量值
        meter_task = asyncio.create_task(self._meter_values_loop())
        
        # 步骤5: 充电过程（持续发送计量值）
        print(f"{self.prefix} 🔋 步骤5: 充电中... (持续{behavior.charging_duration_minutes}分钟)")
        print(f"{self.prefix}    将每{self.meter_report_interval}秒发送一次计量值")
        
        # 等待充电完成
        await asyncio.sleep(behavior.charging_duration_minutes * 60)
        
        # 停止计量值发送
        meter_task.cancel()
        
        # 步骤6: 用户拔枪，停止充电
        print(f"{self.prefix} 🔌 步骤6: 用户拔枪，停止充电")
        behavior.end_time = datetime.now(timezone.utc)
        
        self._send_message("StopTransaction", {
            "transactionId": self.transaction_id,
            "meterStop": self.meter_value,
            "timestamp": behavior.end_time.isoformat(),
            "reason": "Local"
        })
        
        self.status = ChargerStatus.FINISHING
        self._send_message("StatusNotification", {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": ChargerStatus.FINISHING.value
        })
        await asyncio.sleep(2)
        
        # 步骤7: 充电完成，状态恢复为Available
        print(f"{self.prefix} ✅ 步骤7: 充电完成")
        self.status = ChargerStatus.AVAILABLE
        self._send_message("StatusNotification", {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": ChargerStatus.AVAILABLE.value
        })
        
        # 计算充电统计
        duration_seconds = (behavior.end_time - behavior.start_time).total_seconds()
        duration_minutes = duration_seconds / 60
        energy_kwh = self.meter_value / 1000.0
        
        print(f"\n{self.prefix} {'='*60}")
        print(f"{self.prefix} 📊 充电统计:")
        print(f"{self.prefix}    交易ID: {self.transaction_id}")
        print(f"{self.prefix}    用户ID: {behavior.user_id}")
        print(f"{self.prefix}    充电时长: {duration_minutes:.2f}分钟")
        print(f"{self.prefix}    消耗电量: {energy_kwh:.2f} kWh")
        print(f"{self.prefix}    平均功率: {self.charging_power_kw:.2f} kW")
        print(f"{self.prefix} {'='*60}\n")
        
        # 清理状态
        self.transaction_id = None
        self.current_id_tag = None
        self.meter_value = 0
    
    async def run_behavior_loop(self):
        """运行用户行为循环"""
        while True:
            if self.user_behaviors:
                behavior = self.user_behaviors.pop(0)
                self.current_user = behavior
                await self.simulate_user_charging_flow(behavior)
                self.current_user = None
                
                # 等待一段时间再处理下一个用户
                await asyncio.sleep(5)
            else:
                # 如果没有用户行为，等待
                await asyncio.sleep(10)
    
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
        self.print_qr_code()
        
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
        
        print(f"{self.prefix} ✓ 初始化完成，进入用户行为模拟模式")
        print(f"{self.prefix} 使用 add_user_behavior() 方法添加用户行为")
        print(f"{self.prefix} 或使用 --auto-users 参数自动生成用户行为\n")
        
        # 启动用户行为循环
        self.behavior_task = asyncio.create_task(self.run_behavior_loop())
        
        # 定期发送心跳
        try:
            while True:
                await asyncio.sleep(30)
                if self.status != ChargerStatus.CHARGING:
                    self._send_message("Heartbeat", {})
        except KeyboardInterrupt:
            print(f"\n{self.prefix} 正在停止...")
            if self.behavior_task:
                self.behavior_task.cancel()
            self.client.loop_stop()
            self.client.disconnect()
            print(f"{self.prefix} 已停止")


def main():
    parser = argparse.ArgumentParser(description="用户行为模拟充电桩")
    parser.add_argument("--id", type=str, default="CP-USER-001", help="充电桩ID")
    parser.add_argument("--broker", type=str, default="localhost", help="MQTT broker地址")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker端口")
    parser.add_argument("--type-code", type=str, default="zcf", help="设备类型代码")
    parser.add_argument("--serial-number", type=str, default=None, help="设备序列号")
    parser.add_argument("--power", type=float, default=7.0, help="充电功率（kW）")
    parser.add_argument("--auto-users", type=int, default=0, help="自动生成用户行为数量")
    parser.add_argument("--user-interval", type=int, default=60, help="用户行为间隔（秒）")
    
    args = parser.parse_args()
    
    if not MQTT_AVAILABLE:
        print("错误: paho-mqtt 未安装")
        print("请运行: pip install paho-mqtt")
        sys.exit(1)
    
    simulator = UserBehaviorSimulator(
        charger_id=args.id,
        broker_host=args.broker,
        broker_port=args.port,
        type_code=args.type_code,
        serial_number=args.serial_number,
        charging_power_kw=args.power
    )
    
    # 创建异步函数来运行模拟器
    async def run_simulator_with_auto_users():
        # 如果指定了自动生成用户，先添加用户行为
        if args.auto_users > 0:
            print(f"\n{simulator.prefix} 🤖 自动生成 {args.auto_users} 个用户行为")
            for i in range(args.auto_users):
                user_id = f"USER_{i+1:03d}"
                id_tag = f"TAG_{i+1:03d}"
                duration = random.randint(15, 60)  # 15-60分钟随机
                simulator.add_user_behavior(user_id, id_tag, duration)
        
        # 运行模拟器
        await simulator.run()
    
    try:
        asyncio.run(run_simulator_with_auto_users())
    except KeyboardInterrupt:
        print("\n模拟器已停止")


if __name__ == "__main__":
    main()

