#!/usr/bin/env python3
#
# 脚本1：模拟充电桩功能
# - WebSocket连接
# - 发送BootNotification（包含serialNumber=9999）
# - 响应GetConfiguration
# - 响应RemoteStartTransaction
#

import asyncio
import json
import uuid
import sys
from typing import Dict, Any, Optional

try:
    import websockets
except ImportError:
    print("错误: websockets 未安装，请运行: pip install websockets")
    sys.exit(1)


# 配置
# 测试：URL中的id和payload中的serialNumber不同
CHARGE_POINT_ID = "9999"  # URL参数中的id
SERIAL_NUMBER = "3333"    # payload中的serialNumber（应该被用作实际的charge_point_id）
WS_URL = "ws://localhost:9000/ocpp"


class ChargerSimulator:
    """充电桩模拟器"""
    
    def __init__(self, charge_point_id: str, ws_url: str, serial_number: str):
        self.charge_point_id = charge_point_id
        self.ws_url = f"{ws_url}?id={charge_point_id}"
        self.serial_number = serial_number
        self.unique_id_map = {}  # 存储unique_id到action的映射
        self.pending_requests = {}  # 存储待响应的请求
        
    async def send_message(self, ws, message_type: int, unique_id: str, action: str, payload: Dict[str, Any]):
        """发送OCPP标准格式消息: [MessageType, UniqueId, Action, Payload]"""
        message = [message_type, unique_id, action, payload]
        await ws.send(json.dumps(message))
        print(f"→ [{self.charge_point_id}] 发送: {action}")
        print(f"   消息格式: OCPP标准格式")
        print(f"   MessageType: {message_type} ({'CALL' if message_type == 2 else 'CALLRESULT' if message_type == 3 else 'CALLERROR'})")
        print(f"   UniqueId: {unique_id}")
        print(f"   Payload: {json.dumps(payload, ensure_ascii=False)}")
        print()
    
    async def send_response(self, ws, unique_id: str, action: str, payload: Dict[str, Any]):
        """发送响应: [3, UniqueId, Payload]"""
        response = [3, unique_id, payload]
        await ws.send(json.dumps(response))
        print(f"→ [{self.charge_point_id}] 响应: {action}")
        print(f"   UniqueId: {unique_id}")
        print(f"   Payload: {json.dumps(payload, ensure_ascii=False)}")
        print()
    
    async def send_error_response(self, ws, unique_id: str, error_code: str, error_description: str):
        """发送错误响应: [4, UniqueId, ErrorCode, ErrorDescription]"""
        response = [4, unique_id, error_code, error_description]
        await ws.send(json.dumps(response))
        print(f"→ [{self.charge_point_id}] 错误响应")
        print(f"   UniqueId: {unique_id}")
        print(f"   ErrorCode: {error_code}")
        print(f"   ErrorDescription: {error_description}")
        print()
    
    async def handle_incoming_message(self, ws, message: list):
        """处理来自CSMS的消息"""
        if not isinstance(message, list) or len(message) < 3:
            print(f"✗ [{self.charge_point_id}] 无效的消息格式")
            return
        
        message_type = message[0]
        unique_id = message[1]
        
        if message_type == 2:  # CALL
            if len(message) < 4:
                print(f"✗ [{self.charge_point_id}] 无效的CALL消息格式")
                return
            
            action = message[2]
            payload = message[3] if isinstance(message[3], dict) else {}
            
            print(f"← [{self.charge_point_id}] 收到: {action}")
            print(f"   UniqueId: {unique_id}")
            print(f"   Payload: {json.dumps(payload, ensure_ascii=False)}")
            print()
            
            # 处理GetConfiguration
            if action == "GetConfiguration":
                await self.handle_get_configuration(ws, unique_id, payload)
            
            # 处理RemoteStartTransaction
            elif action == "RemoteStartTransaction":
                await self.handle_remote_start_transaction(ws, unique_id, payload)
            
            else:
                print(f"⚠ [{self.charge_point_id}] 未知的action: {action}")
                await self.send_error_response(ws, unique_id, "NotSupported", f"Action {action} not supported")
        
        elif message_type == 3:  # CALLRESULT
            print(f"← [{self.charge_point_id}] 收到CALLRESULT")
            print(f"   UniqueId: {unique_id}")
            print(f"   Payload: {json.dumps(message[2], ensure_ascii=False) if len(message) > 2 else '{}'}")
            print()
        
        elif message_type == 4:  # CALLERROR
            error_code = message[2] if len(message) > 2 else "Unknown"
            error_desc = message[3] if len(message) > 3 else "Unknown error"
            print(f"← [{self.charge_point_id}] 收到CALLERROR")
            print(f"   UniqueId: {unique_id}")
            print(f"   ErrorCode: {error_code}")
            print(f"   ErrorDescription: {error_desc}")
            print()
    
    async def handle_get_configuration(self, ws, unique_id: str, payload: Dict[str, Any]):
        """处理GetConfiguration请求"""
        requested_keys = payload.get("key", [])
        if not isinstance(requested_keys, list):
            requested_keys = [requested_keys] if requested_keys else []
        
        # 模拟配置项
        configuration_keys = []
        if not requested_keys:
            # 如果没有指定keys，返回所有配置
            configuration_keys = [
                {"key": "HeartbeatInterval", "value": "30", "readonly": True},
                {"key": "MeterValueSampleInterval", "value": "60", "readonly": False},
                {"key": "WebSocketPingInterval", "value": "60", "readonly": False},
            ]
        else:
            # 返回请求的keys
            known_configs = {
                "HeartbeatInterval": {"value": "30", "readonly": True},
                "MeterValueSampleInterval": {"value": "60", "readonly": False},
                "WebSocketPingInterval": {"value": "60", "readonly": False},
            }
            for key in requested_keys:
                if key in known_configs:
                    configuration_keys.append({
                        "key": key,
                        "value": known_configs[key]["value"],
                        "readonly": known_configs[key]["readonly"]
                    })
                else:
                    configuration_keys.append({"key": key, "value": None, "readonly": False})
        
        unknown_keys = []
        
        response_payload = {
            "configurationKey": configuration_keys,
            "unknownKey": unknown_keys
        }
        
        await self.send_response(ws, unique_id, "GetConfiguration", response_payload)
    
    async def handle_remote_start_transaction(self, ws, unique_id: str, payload: Dict[str, Any]):
        """处理RemoteStartTransaction请求"""
        id_tag = payload.get("idTag", "")
        connector_id = payload.get("connectorId", 1)
        
        print(f"   处理远程启动充电请求:")
        print(f"     idTag: {id_tag}")
        print(f"     connectorId: {connector_id}")
        print()
        
        # 模拟接受启动请求
        response_payload = {
            "status": "Accepted"
        }
        
        await self.send_response(ws, unique_id, "RemoteStartTransaction", response_payload)
    
    async def run(self):
        """运行模拟器"""
        print("=" * 60)
        print(f"充电桩模拟器（测试模式）")
        print("=" * 60)
        print(f"URL参数中的id: {self.charge_point_id}")
        print(f"Payload中的serialNumber: {self.serial_number}")
        print(f"WebSocket URL: {self.ws_url}")
        print()
        print("⚠️  测试目的：验证系统是否使用payload中的serialNumber作为charge_point_id")
        print(f"   如果系统正确，实际的charge_point_id应该是: {self.serial_number}")
        print("=" * 60)
        print()
        
        try:
            async with websockets.connect(
                self.ws_url,
                subprotocols=["ocpp1.6"],
                ping_interval=None,
                close_timeout=10
            ) as ws:
                print(f"✓ [{self.charge_point_id}] WebSocket连接成功")
                print()
                print("=" * 60)
                print("测试说明:")
                print(f"  URL参数中的id: {self.charge_point_id}")
                print(f"  Payload中的serialNumber: {self.serial_number}")
                print(f"  预期: 系统应该使用payload中的serialNumber({self.serial_number})作为charge_point_id")
                print("=" * 60)
                print()
                
                # 发送BootNotification
                unique_id = f"boot_{uuid.uuid4().hex[:16]}"
                boot_payload = {
                    "chargePointVendor": "TestVendor",
                    "chargePointModel": "TestModel",
                    "firmwareVersion": "1.0.0",
                    "serialNumber": self.serial_number  # 包含serialNumber（应该被用作charge_point_id）
                }
                
                print(f"发送BootNotification:")
                print(f"  URL中的id参数: {self.charge_point_id}")
                print(f"  Payload中的serialNumber: {self.serial_number}")
                print(f"  ⚠️  注意：如果系统正确，应该使用serialNumber({self.serial_number})作为charge_point_id")
                print()
                
                await self.send_message(ws, 2, unique_id, "BootNotification", boot_payload)
                
                # 等待BootNotification响应
                try:
                    response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    response = json.loads(response_raw)
                    print(f"← [{self.charge_point_id}] BootNotification响应:")
                    print(f"   {json.dumps(response, indent=2, ensure_ascii=False)}")
                    print()
                    
                    if isinstance(response, list) and len(response) >= 3:
                        if response[0] == 3:  # CALLRESULT
                            boot_result = response[2] if isinstance(response[2], dict) else {}
                            status = boot_result.get("status", "Unknown")
                            if status == "Accepted":
                                print("=" * 60)
                                print("✓ BootNotification 已接受")
                                print(f"  当前时间: {boot_result.get('currentTime', 'N/A')}")
                                print(f"  心跳间隔: {boot_result.get('interval', 'N/A')} 秒")
                                print()
                                print("⚠️  重要提示：")
                                print(f"   请检查服务器日志或数据库，确认实际使用的charge_point_id:")
                                print(f"   - 如果使用URL中的id: {self.charge_point_id} (错误)")
                                print(f"   - 如果使用payload中的serialNumber: {self.serial_number} (正确)")
                                print("=" * 60)
                            else:
                                print(f"✗ BootNotification 被拒绝: {status}")
                        elif response[0] == 4:  # CALLERROR
                            print(f"✗ BootNotification 错误: {response[2] if len(response) > 2 else 'Unknown'}")
                    print()
                except asyncio.TimeoutError:
                    print(f"✗ BootNotification 响应超时")
                    print()
                
                # 持续监听来自CSMS的消息
                print(f"✓ [{self.charge_point_id}] 进入监听模式，等待CSMS请求...")
                print()
                
                try:
                    while True:
                        message_raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                        message = json.loads(message_raw)
                        await self.handle_incoming_message(ws, message)
                except asyncio.TimeoutError:
                    print(f"⚠ [{self.charge_point_id}] 30秒内未收到消息，保持连接...")
                except websockets.exceptions.ConnectionClosed:
                    print(f"✗ [{self.charge_point_id}] WebSocket连接已关闭")
                except Exception as e:
                    print(f"✗ [{self.charge_point_id}] 处理消息时出错: {e}")
                    
        except Exception as e:
            print(f"✗ [{self.charge_point_id}] 连接失败: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="充电桩WebSocket模拟器（测试URL id vs payload serialNumber）")
    parser.add_argument("--url", type=str, default=WS_URL, help=f"WebSocket服务器URL (默认: {WS_URL})")
    parser.add_argument("--serial", type=str, default=SERIAL_NUMBER, help=f"Payload中的Serial Number (默认: {SERIAL_NUMBER})")
    parser.add_argument("--id", type=str, default=CHARGE_POINT_ID, help=f"URL参数中的Charge Point ID (默认: {CHARGE_POINT_ID})")
    
    args = parser.parse_args()
    
    print()
    print("=" * 60)
    print("配置信息:")
    print(f"  URL参数中的id: {args.id}")
    print(f"  Payload中的serialNumber: {args.serial}")
    print("=" * 60)
    print()
    
    if args.id == args.serial:
        print("⚠️  警告: URL中的id和payload中的serialNumber相同，无法测试差异")
        print(f"   建议: --id {args.id} --serial {int(args.id) + 1000 if args.id.isdigit() else 'different_value'}")
        print()
        response = input("是否继续? (y/n): ").strip().lower()
        if response != 'y':
            print("已取消")
            return
    
    simulator = ChargerSimulator(args.id, args.url, args.serial)
    
    try:
        await simulator.run()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n\n程序出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

