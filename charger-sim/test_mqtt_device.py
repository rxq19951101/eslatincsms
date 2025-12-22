#!/usr/bin/env python3
#
# MQTT设备模拟器
# 模拟设备通过MQTT连接CSMS，从BootNotification开始测试
#

import json
import time
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("错误: paho-mqtt 未安装，请运行: pip install paho-mqtt")
    sys.exit(1)


class MQTTDeviceSimulator:
    """MQTT设备模拟器"""
    
    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        client_id: str,
        username: str,
        password: str,
        type_code: str,
        serial_number: str
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.username = username
        self.password = password
        self.type_code = type_code
        self.serial_number = serial_number
        
        # Topic配置
        self.topic_up = f"{type_code}/{serial_number}/user/up"  # 设备发送
        self.topic_down = f"{type_code}/{serial_number}/user/down"  # 服务器发送
        
        # MQTT客户端（使用V1 API，兼容性更好）
        self.client = mqtt.Client(client_id=client_id)
        self.client.username_pw_set(username, password)
        
        # 设置回调
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        
        # 状态
        self.connected = False
        self.message_id = 0
        self.pending_requests = {}  # {message_id: (action, timestamp)}
        
    def _on_connect(self, client, userdata, flags, rc):
        """连接回调"""
        if rc == 0:
            self.connected = True
            print(f"✅ MQTT连接成功")
            print(f"   Broker: {self.broker_host}:{self.broker_port}")
            print(f"   Client ID: {self.client_id}")
            print(f"   Username: {self.username}")
            print(f"   发送Topic: {self.topic_up}")
            print(f"   接收Topic: {self.topic_down}")
            
            # 订阅服务器下发的消息
            client.subscribe(self.topic_down, qos=1)
            print(f"✅ 已订阅: {self.topic_down}")
        else:
            error_messages = {
                1: "连接被拒绝 - 协议版本不正确",
                2: "连接被拒绝 - 客户端ID无效",
                3: "连接被拒绝 - 服务器不可用",
                4: "连接被拒绝 - 用户名或密码错误",
                5: "连接被拒绝 - 未授权"
            }
            print(f"❌ MQTT连接失败 (错误码: {rc})")
            print(f"   {error_messages.get(rc, '未知错误')}")
            sys.exit(1)
    
    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调"""
        self.connected = False
        if rc != 0:
            print(f"⚠️  MQTT意外断开连接 (错误码: {rc})")
        else:
            print("ℹ️  MQTT连接已断开")
    
    def _on_message(self, client, userdata, msg):
        """消息接收回调"""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            print(f"\n📥 收到服务器消息:")
            print(f"   Topic: {topic}")
            print(f"   内容: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            
            # 处理响应
            action = payload.get("action", "")
            if action:
                print(f"   动作: {action}")
                
                # 检查是否是请求的响应
                if "message_id" in payload:
                    msg_id = payload["message_id"]
                    if msg_id in self.pending_requests:
                        req_action, req_time = self.pending_requests.pop(msg_id)
                        elapsed = time.time() - req_time
                        print(f"   ✅ 响应时间: {elapsed:.2f}秒 (请求: {req_action})")
                
                # 处理特定动作
                if action == "BootNotification":
                    status = payload.get("payload", {}).get("status", "")
                    if status == "Accepted":
                        print(f"   ✅ BootNotification已接受")
                    else:
                        print(f"   ⚠️  BootNotification状态: {status}")
                        
        except json.JSONDecodeError as e:
            print(f"❌ 消息解析失败: {e}")
            print(f"   原始消息: {msg.payload.decode()}")
        except Exception as e:
            print(f"❌ 处理消息时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_publish(self, client, userdata, mid):
        """消息发布回调"""
        print(f"   ✅ 消息已发送 (MID: {mid})")
    
    def connect(self):
        """连接到MQTT broker"""
        print(f"\n🔌 正在连接MQTT broker...")
        print(f"   Broker: {self.broker_host}:{self.broker_port}")
        print(f"   Client ID: {self.client_id}")
        
        try:
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            
            # 等待连接
            timeout = 10
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if not self.connected:
                print("❌ 连接超时")
                return False
            
            return True
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.connected:
            self.client.loop_stop()
            self.client.disconnect()
            print("\n🔌 已断开MQTT连接")
    
    def send_message(self, action: str, payload: Dict[str, Any]) -> int:
        """发送OCPP消息"""
        if not self.connected:
            print("❌ 未连接到MQTT broker")
            return -1
        
        self.message_id += 1
        message = {
            "action": action,
            "payload": payload,
            "message_id": self.message_id
        }
        
        # 记录待处理的请求
        self.pending_requests[self.message_id] = (action, time.time())
        
        message_json = json.dumps(message, ensure_ascii=False)
        
        print(f"\n📤 发送消息:")
        print(f"   Topic: {self.topic_up}")
        print(f"   动作: {action}")
        print(f"   内容: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        print(f"   消息ID: {self.message_id}")
        
        result = self.client.publish(self.topic_up, message_json, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            return self.message_id
        else:
            print(f"❌ 发送失败 (错误码: {result.rc})")
            return -1
    
    def send_boot_notification(self, vendor: str = "ZCF", model: str = "ZCF-001", firmware_version: str = "1.0.0"):
        """发送BootNotification消息"""
        payload = {
            "chargePointVendor": vendor,
            "chargePointModel": model,
            "chargePointSerialNumber": self.serial_number,
            "firmwareVersion": firmware_version
        }
        return self.send_message("BootNotification", payload)
    
    def send_status_notification(self, connector_id: int = 0, status: str = "Available", error_code: str = "NoError"):
        """发送StatusNotification消息"""
        payload = {
            "connectorId": connector_id,
            "status": status,
            "errorCode": error_code
        }
        return self.send_message("StatusNotification", payload)
    
    def send_heartbeat(self):
        """发送Heartbeat消息"""
        payload = {}
        return self.send_message("Heartbeat", payload)
    
    def send_meter_values(self, connector_id: int = 1, transaction_id: Optional[int] = None, energy_wh: int = 0):
        """发送MeterValues消息"""
        meter_value = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sampledValue": [
                {
                    "value": str(energy_wh),
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "Energy.Active.Import.Register",
                    "location": "Outlet",
                    "unit": "Wh"
                },
                {
                    "value": str(energy_wh / 1000.0),  # kWh
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "Energy.Active.Import.Register",
                    "location": "Outlet",
                    "unit": "kWh"
                }
            ]
        }
        
        payload = {
            "connectorId": connector_id,
            "meterValue": [meter_value]
        }
        
        if transaction_id is not None:
            payload["transactionId"] = transaction_id
        
        return self.send_message("MeterValues", payload)
    
    def send_start_transaction(self, connector_id: int = 1, id_tag: str = "TEST_USER_001", meter_start: int = 0):
        """发送StartTransaction消息（开始充电）"""
        payload = {
            "connectorId": connector_id,
            "idTag": id_tag,
            "meterStart": meter_start,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        return self.send_message("StartTransaction", payload)
    
    def send_stop_transaction(self, transaction_id: int, meter_stop: int, reason: str = "Local"):
        """发送StopTransaction消息（停止充电）"""
        payload = {
            "transactionId": transaction_id,
            "meterStop": meter_stop,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason
        }
        return self.send_message("StopTransaction", payload)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MQTT设备模拟器")
    parser.add_argument("--broker", default="localhost", help="MQTT broker地址")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker端口")
    parser.add_argument("--client-id", required=True, help="MQTT客户端ID (例如: zcf&861076087029615)")
    parser.add_argument("--username", required=True, help="MQTT用户名 (例如: 861076087029615)")
    parser.add_argument("--password", required=True, help="MQTT密码")
    parser.add_argument("--type-code", default="zcf", help="设备类型代码")
    parser.add_argument("--serial", required=True, help="设备序列号")
    
    args = parser.parse_args()
    
    # 从client_id解析type_code和serial_number（如果未提供）
    if "&" in args.client_id:
        parts = args.client_id.split("&", 1)
        type_code = parts[0]
        serial_number = parts[1] if len(parts) > 1 else args.serial
    else:
        type_code = args.type_code
        serial_number = args.serial
    
    # 创建模拟器
    simulator = MQTTDeviceSimulator(
        broker_host=args.broker,
        broker_port=args.port,
        client_id=args.client_id,
        username=args.username,
        password=args.password,
        type_code=type_code,
        serial_number=serial_number
    )
    
    # 连接
    if not simulator.connect():
        print("❌ 无法连接到MQTT broker")
        sys.exit(1)
    
    try:
        # 等待一下确保连接稳定
        time.sleep(1)
        
        print("\n" + "=" * 60)
        print("开始模拟设备流程")
        print("=" * 60)
        
        # 1. 发送BootNotification
        print("\n[步骤1] 发送BootNotification")
        print("-" * 60)
        simulator.send_boot_notification(
            vendor="ZCF",
            model="ZCF-001",
            firmware_version="1.0.0"
        )
        time.sleep(2)  # 等待响应
        
        # 2. 发送StatusNotification
        print("\n[步骤2] 发送StatusNotification")
        print("-" * 60)
        simulator.send_status_notification(
            connector_id=0,
            status="Available",
            error_code="NoError"
        )
        time.sleep(1)
        
        # 3. 发送Heartbeat
        print("\n[步骤3] 发送Heartbeat")
        print("-" * 60)
        simulator.send_heartbeat()
        time.sleep(2)
        
        # 4. 开始充电 - StartTransaction
        print("\n[步骤4] 开始充电 - StartTransaction")
        print("-" * 60)
        transaction_id = int(time.time())
        id_tag = "TEST_USER_001"
        meter_start = 0
        simulator.send_start_transaction(
            connector_id=1,
            id_tag=id_tag,
            meter_start=meter_start
        )
        time.sleep(2)
        
        # 5. 更新状态为Charging
        print("\n[步骤5] 更新状态为Charging")
        print("-" * 60)
        simulator.send_status_notification(
            connector_id=1,
            status="Charging",
            error_code="NoError"
        )
        time.sleep(1)
        
        # 6. 发送计量值（模拟充电过程）
        print("\n[步骤6] 发送计量值（模拟充电过程）")
        print("-" * 60)
        charging_duration = 10  # 模拟充电10秒
        energy_wh = 0
        for i in range(5):  # 发送5次计量值
            # 模拟充电功率7kW，每次间隔2秒
            energy_increment = 7 * 2 / 3600 * 1000  # 7kW * 2秒 = Wh
            energy_wh += int(energy_increment)
            
            print(f"\n  发送第 {i+1} 次计量值: {energy_wh} Wh")
            simulator.send_meter_values(
                connector_id=1,
                transaction_id=transaction_id,
                energy_wh=energy_wh
            )
            time.sleep(2)
        
        # 7. 停止充电 - StopTransaction
        print("\n[步骤7] 停止充电 - StopTransaction")
        print("-" * 60)
        meter_stop = energy_wh
        simulator.send_stop_transaction(
            transaction_id=transaction_id,
            meter_stop=meter_stop,
            reason="Local"
        )
        time.sleep(2)
        
        # 8. 更新状态为Available
        print("\n[步骤8] 更新状态为Available")
        print("-" * 60)
        simulator.send_status_notification(
            connector_id=1,
            status="Available",
            error_code="NoError"
        )
        time.sleep(1)
        
        # 9. 再次发送Heartbeat
        print("\n[步骤9] 发送Heartbeat")
        print("-" * 60)
        simulator.send_heartbeat()
        time.sleep(2)
        
        print("\n" + "=" * 60)
        print("✅ 完整充电流程模拟完成")
        print("=" * 60)
        print(f"\n充电统计:")
        print(f"  交易ID: {transaction_id}")
        print(f"  用户标签: {id_tag}")
        print(f"  起始电量: {meter_start} Wh")
        print(f"  结束电量: {meter_stop} Wh")
        print(f"  充电量: {meter_stop - meter_start} Wh ({((meter_stop - meter_start) / 1000):.2f} kWh)")
        print(f"  充电时长: 约 {charging_duration} 秒")
        print("\n保持运行10秒，等待更多消息...")
        print("按 Ctrl+C 提前退出...")
        
        # 保持运行，等待更多消息
        end_time = time.time() + 10
        while time.time() < end_time:
            time.sleep(1)
        
        print("\n⏰ 测试完成，自动退出")
            
    except KeyboardInterrupt:
        print("\n\n收到中断信号，正在退出...")
    finally:
        simulator.disconnect()


if __name__ == "__main__":
    main()

