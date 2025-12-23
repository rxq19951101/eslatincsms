#!/usr/bin/env python3
#
# 远程 MQTT OCPP 1.6 标准格式测试脚本
# 用于测试远程 MQTT broker 是否符合 OCPP 标准
# 使用 OCPP 1.6 标准消息格式: [MessageType, UniqueId, Action, Payload]
#

import argparse
import asyncio
import json
import sys
import uuid
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("错误: paho-mqtt 未安装，请运行: pip install paho-mqtt")
    sys.exit(1)


class RemoteMQTTOCPPTester:
    """远程 MQTT OCPP 1.6 标准格式测试器"""
    
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
        down_topic: str
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
        
        self.prefix = f"[{serial_number}]"
        
        # 状态管理
        self.transaction_id: Optional[int] = None
        self.meter_value = 0
        self.pending_requests: Dict[str, Dict[str, Any]] = {}  # unique_id -> {action, timestamp, ...}
        
        # MQTT 客户端
        self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        self.client.username_pw_set(username, password)
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        self.loop = None
        self.connected = False
    
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
            print("=" * 80)
            
            # 订阅 down 主题（接收 CSMS 的响应和请求）
            result, mid = client.subscribe(self.down_topic, qos=1)
            if result == mqtt.MQTT_ERR_SUCCESS:
                print(f"{self.prefix} ✓ 已订阅主题: {self.down_topic} (接收服务器消息, MID: {mid})")
            else:
                print(f"{self.prefix} ✗ 订阅失败，返回码: {result}")
        else:
            self.connected = False
            print("=" * 80)
            print(f"{self.prefix} ✗ MQTT 连接失败")
            print("=" * 80)
            print(f"返回码 (rc): {rc}")
            error_messages = {
                1: "连接被拒绝 - 协议版本不正确",
                2: "连接被拒绝 - 客户端标识符无效",
                3: "连接被拒绝 - 服务器不可用",
                4: "连接被拒绝 - 用户名或密码错误",
                5: "连接被拒绝 - 未授权",
                6: "连接被拒绝 - 网络错误",
                7: "连接被拒绝 - 网络错误或连接超时"
            }
            print(f"错误说明: {error_messages.get(rc, f'未知错误 (rc={rc})')}")
            print("=" * 80)
            # 不立即退出，让主循环处理重连
    
    def _on_message(self, client: mqtt.Client, userdata, msg):
        """MQTT 消息接收回调"""
        try:
            topic = msg.topic
            payload_str = msg.payload.decode()
            
            print(f"\n{self.prefix} ← 收到消息")
            print(f"{self.prefix}    主题: {topic}")
            print(f"{self.prefix}    QoS: {msg.qos}")
            print(f"{self.prefix}    原始Payload: {payload_str}")
            
            if topic != self.down_topic:
                print(f"{self.prefix} ⚠ 警告: 收到未知主题的消息")
                return
            
            # 解析消息
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError as e:
                print(f"{self.prefix} ✗ JSON 解析错误: {e}")
                return
            
            # 检查消息格式
            if isinstance(payload, list) and len(payload) >= 3:
                # OCPP 1.6 标准格式
                message_type = payload[0]
                unique_id = payload[1]
                
                if message_type == self.CALLRESULT:
                    # 服务器响应（成功）
                    response_payload = payload[2] if len(payload) > 2 else {}
                    print(f"{self.prefix} ✓ 收到 CALLRESULT (MessageType=3)")
                    print(f"{self.prefix}    UniqueId: {unique_id}")
                    print(f"{self.prefix}    响应内容: {json.dumps(response_payload, ensure_ascii=False, indent=2)}")
                    
                    # 查找对应的请求
                    if unique_id in self.pending_requests:
                        request_info = self.pending_requests[unique_id]
                        action = request_info.get("action", "Unknown")
                        elapsed = (datetime.now(timezone.utc) - request_info["timestamp"]).total_seconds()
                        print(f"{self.prefix}    ✓ 匹配到请求: {action} (耗时: {elapsed:.2f}秒)")
                        del self.pending_requests[unique_id]
                        
                        # 处理响应
                        asyncio.run_coroutine_threadsafe(
                            self._handle_response(action, response_payload),
                            self.loop
                        )
                    else:
                        print(f"{self.prefix} ⚠ 警告: 未找到对应的请求 (UniqueId: {unique_id})")
                
                elif message_type == self.CALLERROR:
                    # 服务器响应（错误）
                    error_code = payload[2] if len(payload) > 2 else "Unknown"
                    error_description = payload[3] if len(payload) > 3 else ""
                    error_details = payload[4] if len(payload) > 4 else None
                    
                    print(f"{self.prefix} ✗ 收到 CALLERROR (MessageType=4)")
                    print(f"{self.prefix}    UniqueId: {unique_id}")
                    print(f"{self.prefix}    错误代码: {error_code}")
                    print(f"{self.prefix}    错误描述: {error_description}")
                    if error_details:
                        print(f"{self.prefix}    错误详情: {error_details}")
                    
                    # 查找对应的请求
                    if unique_id in self.pending_requests:
                        request_info = self.pending_requests[unique_id]
                        action = request_info.get("action", "Unknown")
                        elapsed = (datetime.now(timezone.utc) - request_info["timestamp"]).total_seconds()
                        print(f"{self.prefix}    ✗ 匹配到请求: {action} (耗时: {elapsed:.2f}秒)")
                        del self.pending_requests[unique_id]
                
                elif message_type == self.CALL:
                    # 服务器请求（CSMS 主动发送的请求）
                    action = payload[2] if len(payload) > 2 else ""
                    request_payload = payload[3] if len(payload) > 3 else {}
                    
                    print(f"{self.prefix} ← 收到服务器请求 (MessageType=2)")
                    print(f"{self.prefix}    UniqueId: {unique_id}")
                    print(f"{self.prefix}    Action: {action}")
                    print(f"{self.prefix}    请求内容: {json.dumps(request_payload, ensure_ascii=False, indent=2)}")
                    
                    # 处理服务器请求
                    asyncio.run_coroutine_threadsafe(
                        self._handle_server_request(unique_id, action, request_payload),
                        self.loop
                    )
                else:
                    print(f"{self.prefix} ✗ 未知的 MessageType: {message_type}")
            
            elif isinstance(payload, dict):
                # 简化格式（向后兼容）
                print(f"{self.prefix} ⚠ 收到简化格式消息（非标准 OCPP 格式）")
                print(f"{self.prefix}    内容: {json.dumps(payload, ensure_ascii=False, indent=2)}")
            else:
                print(f"{self.prefix} ✗ 无效的消息格式: {type(payload)}")
        
        except Exception as e:
            print(f"{self.prefix} ✗ 消息处理错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_disconnect(self, client: mqtt.Client, userdata, rc):
        """MQTT 断开连接回调"""
        self.connected = False
        if rc != 0:
            print(f"{self.prefix} ⚠ MQTT 意外断开，返回码: {rc}")
            if rc == 7:
                print(f"{self.prefix}    提示: 返回码 7 通常表示网络错误或连接超时")
                print(f"{self.prefix}    可能原因: 网络不稳定、防火墙阻止、broker 配置问题")
        else:
            print(f"{self.prefix} MQTT 已正常断开")
    
    def _send_ocpp_message(self, action: str, payload: Dict[str, Any]) -> str:
        """发送 OCPP 1.6 标准格式消息
        
        返回: unique_id
        """
        # 生成唯一ID
        unique_id = f"test_{uuid.uuid4().hex[:16]}"
        
        # OCPP 1.6 标准格式: [MessageType, UniqueId, Action, Payload]
        # MessageType = 2 表示 CALL（充电桩发送给服务器的请求）
        message = [self.CALL, unique_id, action, payload]
        
        # 记录待处理的请求
        self.pending_requests[unique_id] = {
            "action": action,
            "timestamp": datetime.now(timezone.utc),
            "payload": payload
        }
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"\n{self.prefix} → 发送 OCPP 标准格式消息")
        print(f"{self.prefix}    时间: {timestamp}")
        print(f"{self.prefix}    主题: {self.up_topic}")
        print(f"{self.prefix}    MessageType: {self.CALL} (CALL)")
        print(f"{self.prefix}    UniqueId: {unique_id}")
        print(f"{self.prefix}    Action: {action}")
        print(f"{self.prefix}    Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
        print(f"{self.prefix}    完整消息: {json.dumps(message, ensure_ascii=False)}")
        
        try:
            result = self.client.publish(
                self.up_topic,
                json.dumps(message),
                qos=1
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"{self.prefix}    ✓ 消息已发送")
            else:
                print(f"{self.prefix}    ✗ 消息发送失败，返回码: {result.rc}")
        except Exception as e:
            print(f"{self.prefix}    ✗ 发送错误: {e}")
            import traceback
            traceback.print_exc()
        
        return unique_id
    
    async def _handle_response(self, action: str, response: Dict[str, Any]):
        """处理服务器响应"""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"{self.prefix} → [{timestamp}] 处理响应: {action}")
        print(f"{self.prefix}    响应内容: {json.dumps(response, ensure_ascii=False, indent=2)}")
        
        # 根据不同的 action 处理响应
        if action == "BootNotification":
            status = response.get("status", "")
            interval = response.get("interval", 0)
            current_time = response.get("currentTime", "")
            print(f"{self.prefix}    ✓ BootNotification 响应: status={status}, interval={interval}, currentTime={current_time}")
        
        elif action == "StatusNotification":
            # StatusNotification 通常没有响应内容
            print(f"{self.prefix}    ✓ StatusNotification 已确认")
        
        elif action == "Heartbeat":
            current_time = response.get("currentTime", "")
            print(f"{self.prefix}    ✓ Heartbeat 响应: currentTime={current_time}")
    
    async def _handle_server_request(self, unique_id: str, action: str, payload: Dict[str, Any]):
        """处理来自服务器的请求"""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"{self.prefix} → [{timestamp}] 处理服务器请求: {action}")
        
        response_payload = None
        
        if action == "RemoteStartTransaction":
            id_tag = payload.get("idTag", "")
            connector_id = payload.get("connectorId", 1)
            print(f"{self.prefix}    请求参数: idTag={id_tag}, connectorId={connector_id}")
            
            # 生成交易ID
            self.transaction_id = int(datetime.now(timezone.utc).timestamp())
            self.meter_value = 0
            
            response_payload = {
                "status": "Accepted",
                "transactionId": self.transaction_id
            }
            print(f"{self.prefix}    响应: 接受远程启动，交易ID={self.transaction_id}")
        
        elif action == "RemoteStopTransaction":
            transaction_id = payload.get("transactionId")
            print(f"{self.prefix}    请求参数: transactionId={transaction_id}")
            
            if self.transaction_id:
                response_payload = {"status": "Accepted"}
                self.transaction_id = None
                print(f"{self.prefix}    响应: 接受远程停止")
            else:
                response_payload = {"status": "Rejected"}
                print(f"{self.prefix}    响应: 拒绝（当前未在充电状态）")
        
        else:
            print(f"{self.prefix}    ⚠ 未知请求类型: {action}")
            response_payload = {"status": "NotSupported"}
        
        # 发送响应（使用 CALLRESULT 格式）
        if response_payload:
            self._send_ocpp_response(unique_id, response_payload)
    
    def _send_ocpp_response(self, unique_id: str, response_payload: Dict[str, Any]):
        """发送 OCPP 1.6 标准格式响应
        
        CALLRESULT: [3, UniqueId, Payload]
        """
        message = [self.CALLRESULT, unique_id, response_payload]
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"\n{self.prefix} → 发送 OCPP 标准格式响应")
        print(f"{self.prefix}    时间: {timestamp}")
        print(f"{self.prefix}    主题: {self.up_topic}")
        print(f"{self.prefix}    MessageType: {self.CALLRESULT} (CALLRESULT)")
        print(f"{self.prefix}    UniqueId: {unique_id}")
        print(f"{self.prefix}    响应内容: {json.dumps(response_payload, ensure_ascii=False, indent=2)}")
        print(f"{self.prefix}    完整消息: {json.dumps(message, ensure_ascii=False)}")
        
        try:
            result = self.client.publish(
                self.up_topic,
                json.dumps(message),
                qos=1
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"{self.prefix}    ✓ 响应已发送")
            else:
                print(f"{self.prefix}    ✗ 响应发送失败，返回码: {result.rc}")
        except Exception as e:
            print(f"{self.prefix}    ✗ 发送错误: {e}")
            import traceback
            traceback.print_exc()
    
    async def run_test_sequence(self):
        """运行测试序列"""
        print("\n" + "=" * 80)
        print("等待 MQTT 连接稳定...")
        print("=" * 80)
        
        # 等待连接建立并稳定
        max_wait = 10
        wait_count = 0
        while not self.connected and wait_count < max_wait:
            await asyncio.sleep(1)
            wait_count += 1
            if wait_count % 2 == 0:
                print(f"{self.prefix} 等待连接... ({wait_count}/{max_wait}秒)")
        
        if not self.connected:
            print(f"{self.prefix} ✗ MQTT 未连接，无法继续测试")
            print(f"{self.prefix} 请检查:")
            print(f"{self.prefix}   - 网络连接")
            print(f"{self.prefix}   - Broker 地址和端口")
            print(f"{self.prefix}   - 用户名和密码")
            print(f"{self.prefix}   - 客户端 ID 格式")
            return
        
        print("\n" + "=" * 80)
        print("开始 OCPP 1.6 标准格式测试序列")
        print("=" * 80)
        
        # 额外等待确保连接稳定
        await asyncio.sleep(2)
        
        # 1. BootNotification
        print("\n" + "-" * 80)
        print("测试 1: BootNotification")
        print("-" * 80)
        self._send_ocpp_message("BootNotification", {
            "chargePointVendor": "TestVendor",
            "chargePointModel": "TestModel",
            "firmwareVersion": "1.0.0",
            "chargePointSerialNumber": self.serial_number
        })
        await asyncio.sleep(3)
        
        # 2. StatusNotification
        print("\n" + "-" * 80)
        print("测试 2: StatusNotification")
        print("-" * 80)
        self._send_ocpp_message("StatusNotification", {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": "Available"
        })
        await asyncio.sleep(2)
        
        # 3. Heartbeat
        print("\n" + "-" * 80)
        print("测试 3: Heartbeat")
        print("-" * 80)
        self._send_ocpp_message("Heartbeat", {})
        await asyncio.sleep(2)
        
        # 4. 再次发送 Heartbeat（测试重复消息）
        print("\n" + "-" * 80)
        print("测试 4: Heartbeat (重复)")
        print("-" * 80)
        self._send_ocpp_message("Heartbeat", {})
        await asyncio.sleep(2)
        
        # 5. MeterValues（如果有交易）
        if self.transaction_id:
            print("\n" + "-" * 80)
            print("测试 5: MeterValues")
            print("-" * 80)
            self.meter_value = random.randint(1000, 5000)
            self._send_ocpp_message("MeterValues", {
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
            await asyncio.sleep(2)
        
        # 等待所有响应
        print("\n" + "-" * 80)
        print("等待所有响应...")
        print("-" * 80)
        await asyncio.sleep(5)
        
        # 检查未完成的请求
        if self.pending_requests:
            print(f"\n{self.prefix} ⚠ 警告: 有 {len(self.pending_requests)} 个请求未收到响应:")
            for unique_id, info in self.pending_requests.items():
                elapsed = (datetime.now(timezone.utc) - info["timestamp"]).total_seconds()
                print(f"{self.prefix}    - {info['action']} (UniqueId: {unique_id}, 等待时间: {elapsed:.2f}秒)")
        else:
            print(f"\n{self.prefix} ✓ 所有请求都已收到响应")
        
        print("\n" + "=" * 80)
        print("测试序列完成")
        print("=" * 80)
        print(f"{self.prefix} 保持连接，等待服务器请求...")
        print(f"{self.prefix} 按 Ctrl+C 退出")
        print("=" * 80)
        
        # 定期发送心跳
        try:
            while True:
                await asyncio.sleep(30)
                if self.connected:
                    self._send_ocpp_message("Heartbeat", {})
        except KeyboardInterrupt:
            print(f"\n{self.prefix} 正在停止...")
            self.client.loop_stop()
            self.client.disconnect()
            print(f"{self.prefix} 已停止")
    
    async def run(self):
        """运行测试器"""
        # 设置事件循环
        self.loop = asyncio.get_event_loop()
        
        # 连接到 MQTT broker
        print(f"{self.prefix} 正在连接到 MQTT broker: {self.broker_host}:{self.broker_port}")
        print(f"{self.prefix} 客户端 ID: {self.client_id}")
        print(f"{self.prefix} 用户名: {self.username}")
        
        try:
            # 设置连接选项
            self.client.reconnect_delay_set(min_delay=1, max_delay=120)
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            
            # 等待连接建立
            await asyncio.sleep(1)
        except Exception as e:
            print(f"{self.prefix} ✗ 连接失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        # 运行测试序列
        await self.run_test_sequence()


def main():
    parser = argparse.ArgumentParser(
        description="远程 MQTT OCPP 1.6 标准格式测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python test_remote_mqtt_ocpp.py \\
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
    
    parser.add_argument(
        "--broker",
        type=str,
        required=True,
        help="MQTT broker 地址"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=1883,
        help="MQTT broker 端口 (默认: 1883)"
    )
    parser.add_argument(
        "--client-id",
        type=str,
        required=True,
        help="MQTT 客户端 ID"
    )
    parser.add_argument(
        "--username",
        type=str,
        required=True,
        help="MQTT 用户名"
    )
    parser.add_argument(
        "--password",
        type=str,
        required=True,
        help="MQTT 密码"
    )
    parser.add_argument(
        "--type-code",
        type=str,
        required=True,
        help="设备类型代码（如 zcf）"
    )
    parser.add_argument(
        "--serial-number",
        type=str,
        required=True,
        help="设备序列号"
    )
    parser.add_argument(
        "--up-topic",
        type=str,
        required=True,
        help="发送主题（设备发送消息到服务器）"
    )
    parser.add_argument(
        "--down-topic",
        type=str,
        required=True,
        help="接收主题（设备接收服务器消息）"
    )
    
    args = parser.parse_args()
    
    if not MQTT_AVAILABLE:
        print("错误: paho-mqtt 未安装")
        print("请运行: pip install paho-mqtt")
        sys.exit(1)
    
    tester = RemoteMQTTOCPPTester(
        broker_host=args.broker,
        broker_port=args.port,
        client_id=args.client_id,
        username=args.username,
        password=args.password,
        type_code=args.type_code,
        serial_number=args.serial_number,
        up_topic=args.up_topic,
        down_topic=args.down_topic
    )
    
    try:
        asyncio.run(tester.run())
    except KeyboardInterrupt:
        print("\n测试已停止")


if __name__ == "__main__":
    main()

