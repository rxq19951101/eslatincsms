#!/usr/bin/env python3
#
# 真实充电桩模拟器
# 持续运行，模拟真实充电桩的行为：
# - 连接MQTT
# - 发送 BootNotification
# - 定期发送 Heartbeat 和 StatusNotification
# - 持续运行，不退出
#

import argparse
import asyncio
import json
import sys
import uuid
import signal
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("错误: paho-mqtt 未安装，请运行: pip install paho-mqtt")
    sys.exit(1)


class RealChargerSimulator:
    """真实充电桩模拟器"""
    
    # OCPP 1.6 消息类型
    CALL = 2  # 充电桩发送给服务器的请求
    CALLRESULT = 3  # 服务器响应（成功）
    CALLERROR = 4  # 服务器响应（错误）
    
    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        client_id: str,
        username: str,
        password: str,
        type_code: str,
        serial_number: str,
        up_topic: str,
        down_topic: str,
        heartbeat_interval: int = 60,
        status_interval: int = 300
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.username = username
        self.password = password
        self.type_code = type_code
        self.serial_number = serial_number
        self.up_topic = up_topic
        self.down_topic = down_topic
        self.heartbeat_interval = heartbeat_interval
        self.status_interval = status_interval
        
        self.prefix = f"[{serial_number}]"
        
        # 状态管理
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.boot_notification_sent = False
        self.boot_notification_accepted = False
        self.running = True
        
        # MQTT 客户端
        self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        self.client.username_pw_set(username, password)
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        self.connected = False
        self.last_heartbeat = 0
        self.last_status = 0
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理"""
        print(f"\n{self.prefix} 收到停止信号，正在断开连接...")
        self.running = False
        if self.connected:
            self.client.disconnect()
        sys.exit(0)
    
    def _on_connect(self, client: mqtt.Client, userdata, flags, rc):
        """MQTT 连接回调"""
        if rc == 0:
            self.connected = True
            print("=" * 80)
            print(f"{self.prefix} ✓ MQTT 连接成功")
            print("=" * 80)
            print(f"Broker 地址: {self.broker_host}:{self.broker_port}")
            print(f"客户端 ID: {self.client_id}")
            print(f"用户名: {self.username}")
            print(f"设备类型: {self.type_code}")
            print(f"序列号: {self.serial_number}")
            print(f"发送主题: {self.up_topic}")
            print(f"接收主题: {self.down_topic}")
            print(f"心跳间隔: {self.heartbeat_interval} 秒")
            print(f"状态上报间隔: {self.status_interval} 秒")
            print("=" * 80)
            
            # 订阅 down 主题
            result, mid = client.subscribe(self.down_topic, qos=1)
            if result == mqtt.MQTT_ERR_SUCCESS:
                print(f"{self.prefix} ✓ 已订阅主题: {self.down_topic} (MID: {mid})")
            else:
                print(f"{self.prefix} ✗ 订阅失败，返回码: {result}")
            
            # 连接成功后立即发送 BootNotification
            time.sleep(0.5)
            self.send_boot_notification()
        else:
            self.connected = False
            print("=" * 80)
            print(f"{self.prefix} ✗ MQTT 连接失败")
            print("=" * 80)
            print(f"返回码: {rc}")
            if rc == 1:
                print("  说明: 协议版本不正确")
            elif rc == 2:
                print("  说明: 客户端ID无效")
            elif rc == 3:
                print("  说明: 服务器不可用")
            elif rc == 4:
                print("  说明: 用户名或密码错误")
            elif rc == 5:
                print("  说明: 未授权")
            elif rc == 7:
                print("  说明: 连接被拒绝（可能是客户端ID格式问题）")
            print("=" * 80)
    
    def _on_message(self, client: mqtt.Client, userdata, msg):
        """MQTT 消息接收回调"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            # 解析 OCPP 消息
            try:
                message = json.loads(payload)
            except json.JSONDecodeError:
                print(f"{self.prefix} ✗ 收到无效JSON消息: {payload[:100]}")
                return
            
            # 检查是否是标准 OCPP 格式 [MessageType, UniqueId, Action, Payload]
            if isinstance(message, list) and len(message) >= 3:
                message_type = message[0]
                unique_id = message[1]
                
                if message_type == self.CALLRESULT:
                    # 服务器响应（成功）
                    if len(message) >= 3:
                        payload_data = message[2] if len(message) > 2 else {}
                        self._handle_callresult(unique_id, payload_data)
                elif message_type == self.CALLERROR:
                    # 服务器响应（错误）
                    if len(message) >= 4:
                        error_code = message[2]
                        error_description = message[3]
                        error_details = message[4] if len(message) > 4 else None
                        self._handle_callerror(unique_id, error_code, error_description, error_details)
                elif message_type == self.CALL:
                    # 服务器请求（如 RemoteStartTransaction, RemoteStopTransaction 等）
                    if len(message) >= 4:
                        action = message[2]
                        payload_data = message[3]
                        self._handle_call(action, payload_data, unique_id)
            else:
                # 简化格式 {"action": "...", "payload": {...}}
                action = message.get("action")
                payload_data = message.get("payload", {})
                if action:
                    print(f"{self.prefix} <- 收到简化格式消息: {action}")
                    # 对于简化格式，我们只处理响应，不处理请求
                    pass
        except Exception as e:
            print(f"{self.prefix} ✗ 处理消息时出错: {e}", exc_info=True)
    
    def _on_disconnect(self, client: mqtt.Client, userdata, rc):
        """MQTT 断开连接回调"""
        self.connected = False
        if rc != 0:
            print(f"{self.prefix} ⚠ MQTT 意外断开连接 (rc: {rc})")
            if self.running:
                print(f"{self.prefix} 正在尝试重新连接...")
        else:
            print(f"{self.prefix} MQTT 连接已断开")
    
    def _handle_callresult(self, unique_id: str, payload: Dict[str, Any]):
        """处理 CALLRESULT 响应"""
        if unique_id in self.pending_requests:
            request_info = self.pending_requests.pop(unique_id)
            action = request_info.get("action")
            elapsed = time.time() - request_info.get("timestamp", 0)
            
            print(f"{self.prefix} ✓ 收到响应: {action} (UniqueId: {unique_id}, 耗时: {elapsed:.3f}秒)")
            
            if action == "BootNotification":
                status = payload.get("status", "Unknown")
                if status == "Accepted":
                    self.boot_notification_accepted = True
                    print(f"{self.prefix} ✓ BootNotification 已被服务器接受")
                    if "interval" in payload:
                        print(f"{self.prefix}   服务器要求心跳间隔: {payload['interval']} 秒")
                        # 可以更新心跳间隔，但这里我们保持使用配置的间隔
                else:
                    print(f"{self.prefix} ⚠ BootNotification 状态: {status}")
            elif action == "Heartbeat":
                current_time = payload.get("currentTime", "Unknown")
                print(f"{self.prefix}   服务器时间: {current_time}")
            elif action == "StatusNotification":
                print(f"{self.prefix}   StatusNotification 已确认")
        else:
            print(f"{self.prefix} ⚠ 收到未知请求的响应 (UniqueId: {unique_id})")
    
    def _handle_callerror(self, unique_id: str, error_code: str, error_description: str, error_details: Any):
        """处理 CALLERROR 响应"""
        if unique_id in self.pending_requests:
            request_info = self.pending_requests.pop(unique_id)
            action = request_info.get("action")
            print(f"{self.prefix} ✗ 收到错误响应: {action}")
            print(f"{self.prefix}   错误代码: {error_code}")
            print(f"{self.prefix}   错误描述: {error_description}")
            if error_details:
                print(f"{self.prefix}   错误详情: {error_details}")
        else:
            print(f"{self.prefix} ⚠ 收到未知请求的错误响应 (UniqueId: {unique_id})")
    
    def _handle_call(self, action: str, payload: Dict[str, Any], unique_id: str):
        """处理服务器发来的 CALL 请求"""
        print(f"{self.prefix} <- 收到服务器请求: {action} (UniqueId: {unique_id})")
        
        # 对于真实充电桩，这里应该实现各种请求的处理
        # 但因为我们只是模拟，所以简单回复 NotSupported
        response = [self.CALLRESULT, unique_id, {}]
        self._publish_message(json.dumps(response))
        print(f"{self.prefix} -> 已回复: {action} (NotSupported)")
    
    def _publish_message(self, message: str):
        """发布 MQTT 消息"""
        if not self.connected:
            print(f"{self.prefix} ⚠ MQTT 未连接，无法发送消息")
            return False
        
        result = self.client.publish(self.up_topic, message, qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            return True
        else:
            print(f"{self.prefix} ✗ 发布消息失败，返回码: {result.rc}")
            return False
    
    def send_boot_notification(self):
        """发送 BootNotification"""
        if self.boot_notification_sent:
            return
        
        unique_id = str(uuid.uuid4())
        action = "BootNotification"
        payload = {
            "chargePointVendor": "ZCF",
            "chargePointModel": "ZCF-AC-7KW",
            "chargePointSerialNumber": self.serial_number,
            "firmwareVersion": "1.0.0"
        }
        
        message = [self.CALL, unique_id, action, payload]
        message_str = json.dumps(message)
        
        if self._publish_message(message_str):
            self.pending_requests[unique_id] = {
                "action": action,
                "timestamp": time.time()
            }
            self.boot_notification_sent = True
            print(f"{self.prefix} -> 发送 BootNotification (UniqueId: {unique_id})")
        else:
            print(f"{self.prefix} ✗ 发送 BootNotification 失败")
    
    def send_heartbeat(self):
        """发送 Heartbeat"""
        unique_id = str(uuid.uuid4())
        action = "Heartbeat"
        payload = {}
        
        message = [self.CALL, unique_id, action, payload]
        message_str = json.dumps(message)
        
        if self._publish_message(message_str):
            self.pending_requests[unique_id] = {
                "action": action,
                "timestamp": time.time()
            }
            print(f"{self.prefix} -> 发送 Heartbeat (UniqueId: {unique_id})")
            self.last_heartbeat = time.time()
        else:
            print(f"{self.prefix} ✗ 发送 Heartbeat 失败")
    
    def send_status_notification(self, connector_id: int = 0, status: str = "Available"):
        """发送 StatusNotification"""
        unique_id = str(uuid.uuid4())
        action = "StatusNotification"
        payload = {
            "connectorId": connector_id,
            "status": status,
            "errorCode": "NoError"
        }
        
        message = [self.CALL, unique_id, action, payload]
        message_str = json.dumps(message)
        
        if self._publish_message(message_str):
            self.pending_requests[unique_id] = {
                "action": action,
                "timestamp": time.time()
            }
            print(f"{self.prefix} -> 发送 StatusNotification (ConnectorId: {connector_id}, Status: {status}, UniqueId: {unique_id})")
            self.last_status = time.time()
        else:
            print(f"{self.prefix} ✗ 发送 StatusNotification 失败")
    
    def connect(self):
        """连接 MQTT Broker"""
        try:
            print(f"{self.prefix} 正在连接 MQTT Broker: {self.broker_host}:{self.broker_port}...")
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            print(f"{self.prefix} ✗ 连接失败: {e}")
            return False
        return True
    
    def run(self):
        """运行模拟器"""
        if not self.connect():
            return False
        
        print(f"\n{self.prefix} 模拟器已启动，持续运行中...")
        print(f"{self.prefix} 按 Ctrl+C 停止")
        print("=" * 80)
        
        # 等待连接建立
        timeout = 10
        start_time = time.time()
        while not self.connected and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        if not self.connected:
            print(f"{self.prefix} ✗ 连接超时")
            return False
        
        # 主循环
        try:
            while self.running:
                current_time = time.time()
                
                # 定期发送心跳
                if current_time - self.last_heartbeat >= self.heartbeat_interval:
                    if self.boot_notification_accepted:
                        self.send_heartbeat()
                    else:
                        # 如果 BootNotification 还未被接受，重新发送
                        if not self.boot_notification_sent:
                            self.send_boot_notification()
                        else:
                            # 等待响应
                            time.sleep(1)
                
                # 定期发送状态通知
                if current_time - self.last_status >= self.status_interval:
                    if self.boot_notification_accepted:
                        self.send_status_notification(connector_id=0, status="Available")
                    else:
                        time.sleep(1)
                
                # 检查连接状态
                if not self.connected:
                    print(f"{self.prefix} ⚠ 连接已断开，等待重连...")
                    time.sleep(5)
                    continue
                
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n{self.prefix} 收到停止信号...")
        finally:
            self.running = False
            self.client.loop_stop()
            self.client.disconnect()
            print(f"{self.prefix} 模拟器已停止")


def main():
    parser = argparse.ArgumentParser(
        description="真实充电桩模拟器 - 持续运行模式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用设备信息运行模拟器
  python run_real_charger_simulator.py \\
    --broker 47.236.134.99 \\
    --port 1883 \\
    --client-id "zcf&861076087029615" \\
    --username "861076087029615" \\
    --password "pHYtWMiW+UOa" \\
    --type-code "zcf" \\
    --serial-number "861076087029615" \\
    --up-topic "zcf/861076087029615/user/up" \\
    --down-topic "zcf/861076087029615/user/down"
        """
    )
    
    parser.add_argument("--broker", type=str, required=True, help="MQTT Broker 地址")
    parser.add_argument("--port", type=int, default=1883, help="MQTT Broker 端口")
    parser.add_argument("--client-id", type=str, required=True, help="MQTT 客户端 ID")
    parser.add_argument("--username", type=str, required=True, help="MQTT 用户名")
    parser.add_argument("--password", type=str, required=True, help="MQTT 密码")
    parser.add_argument("--type-code", type=str, required=True, help="设备类型代码")
    parser.add_argument("--serial-number", type=str, required=True, help="设备序列号")
    parser.add_argument("--up-topic", type=str, required=True, help="发送主题 (up)")
    parser.add_argument("--down-topic", type=str, required=True, help="接收主题 (down)")
    parser.add_argument("--heartbeat-interval", type=int, default=60, help="心跳间隔（秒，默认: 60）")
    parser.add_argument("--status-interval", type=int, default=300, help="状态上报间隔（秒，默认: 300）")
    
    args = parser.parse_args()
    
    simulator = RealChargerSimulator(
        broker_host=args.broker,
        broker_port=args.port,
        client_id=args.client_id,
        username=args.username,
        password=args.password,
        type_code=args.type_code,
        serial_number=args.serial_number,
        up_topic=args.up_topic,
        down_topic=args.down_topic,
        heartbeat_interval=args.heartbeat_interval,
        status_interval=args.status_interval
    )
    
    simulator.run()


if __name__ == "__main__":
    main()

