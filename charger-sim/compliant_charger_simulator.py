#!/usr/bin/env python3
#
# OCPP 1.6 规范符合性模拟充电桩
# 用于本地测试，完全符合 OCPP 1.6 规范
#

import argparse
import asyncio
import json
import time
import websockets
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid
import threading


class CompliantChargerSimulator:
    """符合 OCPP 1.6 规范的充电桩模拟器"""
    
    # OCPP 1.6 消息类型
    CALL = 2
    CALLRESULT = 3
    CALLERROR = 4
    
    def __init__(self, charger_id: str, server_url: str):
        self.charger_id = charger_id
        self.server_url = server_url.rstrip('/')
        self.ws_url = f"{self.server_url}/ocpp?id={charger_id}"
        self.ws = None
        self.running = False
        
        # 充电桩状态
        self.vendor = "TestVendor"
        self.model = "TestModel-AC-7kW"
        self.serial_number = charger_id
        self.firmware_version = "1.0.0"
        
        # 配置
        self.heartbeat_interval = 300  # 默认 300 秒
        self.meter_value_sample_interval = 60  # 默认 60 秒
        self.configuration = {
            "HeartbeatInterval": {"value": "300", "readonly": False},
            "MeterValueSampleInterval": {"value": "60", "readonly": False},
            "SupportedFeatureProfiles": {"value": "Core,SmartCharging", "readonly": True},
        }
        
        # 连接器状态
        self.connector_status = {
            1: "Available"  # connectorId -> status
        }
        
        # 充电状态
        self.transaction_id = None
        self.is_charging = False
        self.meter_start = 0
        self.meter_current = 0
        
        # 任务
        self.heartbeat_task = None
        self.meter_values_task = None
        
    async def connect(self):
        """连接到服务器"""
        print(f"[{self.charger_id}] 正在连接到服务器: {self.ws_url}")
        try:
            self.ws = await websockets.connect(
                self.ws_url,
                subprotocols=["ocpp1.6"]
            )
            print(f"[{self.charger_id}] ✓ WebSocket 连接成功")
            return True
        except Exception as e:
            print(f"[{self.charger_id}] ✗ 连接失败: {e}")
            return False
    
    async def send_message(self, message: list):
        """发送 OCPP 标准格式消息"""
        if self.ws:
            message_json = json.dumps(message)
            await self.ws.send(message_json)
            print(f"[{self.charger_id}] -> 发送: {message[1]} ({message[2] if len(message) > 2 else 'N/A'})")
    
    async def send_boot_notification(self):
        """发送 BootNotification"""
        unique_id = str(uuid.uuid4())
        payload = {
            "chargePointVendor": self.vendor,
            "chargePointModel": self.model,
            "chargePointSerialNumber": self.serial_number,
            "firmwareVersion": self.firmware_version
        }
        message = [self.CALL, unique_id, "BootNotification", payload]
        await self.send_message(message)
        return unique_id
    
    async def send_heartbeat(self):
        """发送 Heartbeat"""
        unique_id = str(uuid.uuid4())
        payload = {}  # Heartbeat 不需要 payload
        message = [self.CALL, unique_id, "Heartbeat", payload]
        await self.send_message(message)
        return unique_id
    
    async def send_status_notification(self, connector_id: int, status: str, error_code: Optional[str] = None):
        """发送 StatusNotification"""
        unique_id = str(uuid.uuid4())
        payload = {
            "connectorId": connector_id,
            "status": status
        }
        if error_code:
            payload["errorCode"] = error_code
        
        message = [self.CALL, unique_id, "StatusNotification", payload]
        await self.send_message(message)
        
        # 更新本地状态
        self.connector_status[connector_id] = status
        return unique_id
    
    async def send_meter_values(self, connector_id: int, transaction_id: Optional[int] = None):
        """发送 MeterValues"""
        unique_id = str(uuid.uuid4())
        
        # 更新计量值（模拟充电）
        if self.is_charging:
            self.meter_current += 100  # 每次增加 100 Wh
        
        meter_value = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "sampledValue": [
                {
                    "value": str(self.meter_current),
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "Energy.Active.Import.Register",
                    "unit": "Wh"
                }
            ]
        }
        
        payload = {
            "connectorId": connector_id,
            "meterValue": [meter_value]
        }
        
        if transaction_id:
            payload["transactionId"] = transaction_id
        
        message = [self.CALL, unique_id, "MeterValues", payload]
        await self.send_message(message)
        return unique_id
    
    async def send_start_transaction(self, connector_id: int, id_tag: str):
        """发送 StartTransaction"""
        unique_id = str(uuid.uuid4())
        self.transaction_id = int(time.time())  # 使用时间戳作为 transaction_id
        
        payload = {
            "connectorId": connector_id,
            "idTag": id_tag,
            "meterStart": self.meter_start,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        }
        
        message = [self.CALL, unique_id, "StartTransaction", payload]
        await self.send_message(message)
        return unique_id
    
    async def send_stop_transaction(self, transaction_id: int, id_tag: str, reason: str = "Local"):
        """发送 StopTransaction"""
        unique_id = str(uuid.uuid4())
        
        payload = {
            "idTag": id_tag,
            "meterStop": self.meter_current,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "transactionId": transaction_id,
            "reason": reason
        }
        
        message = [self.CALL, unique_id, "StopTransaction", payload]
        await self.send_message(message)
        return unique_id
    
    async def handle_call(self, unique_id: str, action: str, payload: Dict[str, Any]):
        """处理服务器发来的 CALL 请求"""
        print(f"[{self.charger_id}] <- 收到服务器请求: {action} (UniqueId: {unique_id})")
        
        response_payload = {}
        
        if action == "GetConfiguration":
            # 返回配置列表
            keys = payload.get("key", [])
            if keys:
                # 返回指定键的配置
                config_list = []
                for key in keys:
                    if key in self.configuration:
                        config_list.append({
                            "key": key,
                            "value": self.configuration[key]["value"],
                            "readonly": self.configuration[key]["readonly"]
                        })
                    else:
                        # 未知键
                        pass
                response_payload = {"configurationKey": config_list}
            else:
                # 返回所有配置
                config_list = [
                    {
                        "key": k,
                        "value": v["value"],
                        "readonly": v["readonly"]
                    }
                    for k, v in self.configuration.items()
                ]
                response_payload = {"configurationKey": config_list}
        
        elif action == "ChangeConfiguration":
            key = payload.get("key")
            value = payload.get("value")
            
            if key in self.configuration:
                if self.configuration[key]["readonly"]:
                    response_payload = {"status": "Rejected"}
                else:
                    # 更新配置
                    self.configuration[key]["value"] = value
                    response_payload = {"status": "Accepted"}
                    
                    # 如果更改了 HeartbeatInterval，更新间隔
                    if key == "HeartbeatInterval":
                        try:
                            self.heartbeat_interval = int(value)
                            print(f"[{self.charger_id}] HeartbeatInterval 已更新为: {self.heartbeat_interval} 秒")
                        except:
                            pass
                    
                    # 如果更改了 MeterValueSampleInterval，更新间隔
                    if key == "MeterValueSampleInterval":
                        try:
                            self.meter_value_sample_interval = int(value)
                            print(f"[{self.charger_id}] MeterValueSampleInterval 已更新为: {self.meter_value_sample_interval} 秒")
                        except:
                            pass
            else:
                response_payload = {"status": "NotSupported"}
        
        elif action == "UnlockConnector":
            connector_id = payload.get("connectorId")
            if connector_id in self.connector_status:
                # 模拟解锁
                response_payload = {"status": "Unlocked"}
            else:
                response_payload = {"status": "UnlockFailed"}
        
        elif action == "RemoteStartTransaction":
            connector_id = payload.get("connectorId", 1)
            id_tag = payload.get("idTag")
            
            # 检查连接器状态
            if self.connector_status.get(connector_id) == "Available":
                response_payload = {"status": "Accepted"}
                # 启动充电流程（异步）
                asyncio.create_task(self.start_charging_flow(connector_id, id_tag))
            else:
                response_payload = {"status": "Rejected"}
        
        elif action == "RemoteStopTransaction":
            transaction_id = payload.get("transactionId")
            
            if self.is_charging and self.transaction_id == transaction_id:
                response_payload = {"status": "Accepted"}
                # 停止充电流程（异步）
                asyncio.create_task(self.stop_charging_flow())
            else:
                response_payload = {"status": "Rejected"}
        
        elif action == "Reset":
            reset_type = payload.get("type", "Soft")
            response_payload = {"status": "Accepted"}
            print(f"[{self.charger_id}] ⚠️  收到重置请求: {reset_type}")
            # 注意：实际充电桩会重启
        
        else:
            response_payload = {"status": "NotSupported"}
        
        # 发送 CALLRESULT
        response = [self.CALLRESULT, unique_id, response_payload]
        response_json = json.dumps(response)
        await self.ws.send(response_json)
        print(f"[{self.charger_id}] -> 已回复: {action} (UniqueId: {unique_id})")
    
    async def start_charging_flow(self, connector_id: int, id_tag: str):
        """启动充电流程"""
        print(f"[{self.charger_id}] 开始充电流程...")
        
        # 1. 状态转换：Available -> Preparing
        await self.send_status_notification(connector_id, "Preparing")
        await asyncio.sleep(2)
        
        # 2. 状态转换：Preparing -> Charging
        await self.send_status_notification(connector_id, "Charging")
        
        # 3. 发送 StartTransaction
        await self.send_start_transaction(connector_id, id_tag)
        await asyncio.sleep(1)
        
        # 4. 开始充电
        self.is_charging = True
        self.meter_start = self.meter_current
        
        # 5. 启动 MeterValues 上报任务
        if self.meter_values_task:
            self.meter_values_task.cancel()
        self.meter_values_task = asyncio.create_task(self.meter_values_loop(connector_id))
    
    async def stop_charging_flow(self):
        """停止充电流程"""
        print(f"[{self.charger_id}] 停止充电流程...")
        
        # 1. 停止 MeterValues 上报
        if self.meter_values_task:
            self.meter_values_task.cancel()
            self.meter_values_task = None
        
        # 2. 状态转换：Charging -> Finishing
        await self.send_status_notification(1, "Finishing")
        await asyncio.sleep(2)
        
        # 3. 发送 StopTransaction
        if self.transaction_id:
            await self.send_stop_transaction(self.transaction_id, "TEST_TAG_001", "Remote")
        
        # 4. 状态转换：Finishing -> Available
        await asyncio.sleep(1)
        await self.send_status_notification(1, "Available")
        
        # 5. 重置状态
        self.is_charging = False
        self.transaction_id = None
    
    async def heartbeat_loop(self):
        """Heartbeat 循环任务"""
        while self.running:
            try:
                await self.send_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[{self.charger_id}] Heartbeat 错误: {e}")
                await asyncio.sleep(5)
    
    async def meter_values_loop(self, connector_id: int):
        """MeterValues 循环任务（充电时）"""
        while self.running and self.is_charging:
            try:
                await self.send_meter_values(connector_id, self.transaction_id)
                await asyncio.sleep(self.meter_value_sample_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[{self.charger_id}] MeterValues 错误: {e}")
                await asyncio.sleep(5)
    
    async def message_handler(self):
        """消息处理循环"""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    
                    if isinstance(data, list) and len(data) >= 3:
                        message_type = data[0]
                        unique_id = data[1]
                        
                        if message_type == self.CALL:
                            # 服务器发来的 CALL 请求
                            if len(data) >= 4:
                                action = data[2]
                                payload = data[3]
                                await self.handle_call(unique_id, action, payload)
                        elif message_type == self.CALLRESULT:
                            # 服务器对之前请求的响应
                            payload = data[2] if len(data) > 2 else {}
                            print(f"[{self.charger_id}] <- 收到 CALLRESULT (UniqueId: {unique_id})")
                        elif message_type == self.CALLERROR:
                            # 服务器返回错误
                            error_code = data[2] if len(data) > 2 else "Unknown"
                            error_description = data[3] if len(data) > 3 else ""
                            print(f"[{self.charger_id}] <- 收到 CALLERROR (UniqueId: {unique_id}, Error: {error_code})")
                except json.JSONDecodeError as e:
                    print(f"[{self.charger_id}] JSON 解析错误: {e}")
                except Exception as e:
                    print(f"[{self.charger_id}] 消息处理错误: {e}")
        except websockets.exceptions.ConnectionClosed:
            print(f"[{self.charger_id}] WebSocket 连接已关闭")
        except Exception as e:
            print(f"[{self.charger_id}] 消息处理循环错误: {e}")
    
    async def run(self):
        """运行模拟器"""
        if not await self.connect():
            return
        
        self.running = True
        
        # 1. 发送 BootNotification
        print(f"[{self.charger_id}] 发送 BootNotification...")
        await self.send_boot_notification()
        await asyncio.sleep(2)
        
        # 2. 发送初始状态
        await self.send_status_notification(1, "Available")
        await asyncio.sleep(1)
        
        # 3. 启动 Heartbeat 循环
        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        
        # 4. 启动消息处理
        await self.message_handler()
    
    async def stop(self):
        """停止模拟器"""
        self.running = False
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.meter_values_task:
            self.meter_values_task.cancel()
        if self.ws:
            await self.ws.close()


async def main_async():
    """异步主函数"""
    parser = argparse.ArgumentParser(description="OCPP 1.6 规范符合性充电桩模拟器")
    parser.add_argument(
        "--charger-id",
        type=str,
        default="TEST-COMP-001",
        help="充电桩ID（默认: TEST-COMP-001，最多15个字符）"
    )
    parser.add_argument(
        "--server",
        type=str,
        default="http://localhost:9000",
        help="CSMS 服务器地址（默认: http://localhost:9000）"
    )
    
    args = parser.parse_args()
    
    # 转换 HTTP URL 为 WebSocket URL
    if args.server.startswith("http://"):
        ws_url = args.server.replace("http://", "ws://")
    elif args.server.startswith("https://"):
        ws_url = args.server.replace("https://", "wss://")
    else:
        ws_url = args.server
    
    print("=" * 80)
    print("OCPP 1.6 规范符合性充电桩模拟器")
    print("=" * 80)
    print(f"充电桩ID: {args.charger_id}")
    print(f"服务器: {ws_url}")
    print("=" * 80)
    print()
    
    simulator = CompliantChargerSimulator(args.charger_id, ws_url)
    
    try:
        await simulator.run()
    except KeyboardInterrupt:
        print("\n正在停止模拟器...")
        await simulator.stop()
        print("模拟器已停止")


def main():
    """主函数"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

