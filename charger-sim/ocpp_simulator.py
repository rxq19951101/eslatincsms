#!/usr/bin/env python3
#
# 增强版 OCPP 1.6 充电桩模拟器
# 支持完整的OCPP协议消息，可与OCPP验证工具配合使用
#

import argparse
import asyncio
import json
import sys
import uuid
import hashlib
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set
from enum import Enum

import qrcode
import websockets
from websockets.client import WebSocketClientProtocol


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


class OCPPSimulator:
    """OCPP 1.6 充电桩模拟器"""
    
    # 预定义的厂商和型号列表（用于随机选择，让每个充电桩不同）
    VENDOR_MODELS = [
        ("Tesla", "Supercharger V3"),
        ("ABB", "Terra AC"),
        ("Schneider Electric", "EVlink Charging Station"),
        ("Siemens", "VersiCharge"),
        ("ChargePoint", "CPF50"),
        ("EVBox", "BusinessLine"),
        ("Webasto", "Live"),
        ("Phoenix Contact", "emobility"),
        ("Bosch", "Smart Charging"),
        ("Wallbox", "Quasar"),
    ]
    
    CONNECTOR_TYPES = ["Type2", "CCS2", "CCS1", "CHademo", "GBT", "Type1"]
    
    def __init__(self, charger_id: str, url: str, vendor: Optional[str] = None, 
                 model: Optional[str] = None, firmware_version: Optional[str] = None,
                 serial_number: Optional[str] = None):
        self.charger_id = charger_id
        self.url = f"{url}?id={charger_id}"
        self.ws: Optional[WebSocketClientProtocol] = None
        self.prefix = f"[{charger_id}]"
        
        # 生成唯一的设备标识信息
        self.device_info = self._generate_device_info(charger_id, vendor, model, 
                                                      firmware_version, serial_number)
        
        # 状态管理
        self.status = ChargerStatus.UNAVAILABLE
        self.connector_id = 1
        self.transaction_id: Optional[int] = None
        self.current_id_tag: Optional[str] = None
        self.meter_value = 0
        
        # 消息ID计数
        self.message_id_counter = 1
        
        # 待处理的远程控制请求
        self.pending_remote_start: Optional[Dict[str, Any]] = None
    
    def _generate_device_info(self, charger_id: str, vendor: Optional[str] = None,
                             model: Optional[str] = None, firmware_version: Optional[str] = None,
                             serial_number: Optional[str] = None) -> Dict[str, str]:
        """为每个充电桩生成唯一的设备标识信息"""
        # 使用充电桩ID生成确定性但唯一的标识
        charger_hash = int(hashlib.md5(charger_id.encode()).hexdigest()[:8], 16)
        
        # 厂商和型号（如果未指定，从列表中选择）
        if vendor is None or model is None:
            vendor_idx = charger_hash % len(self.VENDOR_MODELS)
            vendor, model = self.VENDOR_MODELS[vendor_idx]
        
        # 序列号（如果未指定，基于充电桩ID生成）
        if serial_number is None:
            # 生成类似真实序列号的格式：VENDOR-YYYYMMDD-XXXX
            year = 2023 + (charger_hash % 2)  # 2023 或 2024
            month = (charger_hash % 12) + 1
            day = (charger_hash % 28) + 1
            seq_num = charger_hash % 10000
            serial_number = f"{vendor[:3].upper()}-{year:04d}{month:02d}{day:02d}-{seq_num:04d}"
        
        # 固件版本（如果未指定，生成版本号）
        if firmware_version is None:
            major = 1 + (charger_hash % 3)  # 1-3
            minor = charger_hash % 10  # 0-9
            patch = charger_hash % 10  # 0-9
            firmware_version = f"{major}.{minor}.{patch}"
        
        # 连接器类型（基于充电桩ID选择）
        connector_type = self.CONNECTOR_TYPES[charger_hash % len(self.CONNECTOR_TYPES)]
        
        # 充电速率（kW，基于型号范围）
        rate_ranges = {
            "Supercharger V3": (150, 250),
            "Terra AC": (11, 22),
            "EVlink Charging Station": (7, 22),
            "VersiCharge": (7, 22),
            "CPF50": (50, 125),
            "BusinessLine": (11, 22),
            "Live": (7, 22),
            "emobility": (11, 43),
            "Smart Charging": (7, 22),
            "Quasar": (11, 22),
        }
        
        rate_range = rate_ranges.get(model, (7, 22))
        charging_rate = rate_range[0] + (charger_hash % (rate_range[1] - rate_range[0] + 1))
        
        return {
            "vendor": vendor,
            "model": model,
            "serial_number": serial_number,
            "firmware_version": firmware_version,
            "connector_type": connector_type,
            "charging_rate": float(charging_rate),
            "device_id": f"{vendor[:3]}-{serial_number.split('-')[-1]}",  # 设备ID
        }
        
    def get_message_id(self) -> str:
        """生成消息ID"""
        msg_id = str(uuid.uuid4())
        return msg_id
    
    async def connect(self) -> bool:
        """连接到CSMS"""
        try:
            print(f"{self.prefix} 正在连接到: {self.url}")
            self.ws = await websockets.connect(
                self.url,
                subprotocols=["ocpp1.6"],
                ping_interval=None,
                close_timeout=10
            )
            
            # 接收连接确认
            try:
                hello = await asyncio.wait_for(self.ws.recv(), timeout=2.0)
                print(f"{self.prefix} ✓ 连接成功")
                print(f"{self.prefix}   服务器响应: {hello[:100]}...")
            except asyncio.TimeoutError:
                print(f"{self.prefix} ⚠ 未收到连接确认，继续...")
            
            return True
        except Exception as e:
            print(f"{self.prefix} ✗ 连接失败: {e}")
            return False
    
    async def send_message(self, action: str, payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """发送OCPP消息并等待响应"""
        if not self.ws:
            print(f"{self.prefix} ✗ WebSocket未连接")
            return None
        
        try:
            message = {
                "action": action
            }
            if payload:
                message["payload"] = payload
            
            message_json = json.dumps(message)
            await self.ws.send(message_json)
            print(f"{self.prefix} → {action}")
            if payload:
                print(f"{self.prefix}    payload: {json.dumps(payload)[:100]}...")
            
            # 等待响应
            try:
                response_raw = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                response = json.loads(response_raw)
                print(f"{self.prefix} ← 响应: {json.dumps(response)[:100]}...")
                return response
            except asyncio.TimeoutError:
                print(f"{self.prefix} ⚠ 超时: 未收到响应")
                return None
                
        except Exception as e:
            print(f"{self.prefix} ✗ 发送消息失败: {e}")
            return None
    
    async def send_boot_notification(self) -> bool:
        """发送启动通知（包含完整的设备标识信息）"""
        payload = {
            "vendor": self.device_info["vendor"],
            "model": self.device_info["model"],
            "firmwareVersion": self.device_info["firmware_version"],
            "serialNumber": self.device_info["serial_number"],
        }
        
        # 打印设备信息
        print(f"{self.prefix}   设备信息:")
        print(f"{self.prefix}     厂商: {self.device_info['vendor']}")
        print(f"{self.prefix}     型号: {self.device_info['model']}")
        print(f"{self.prefix}     序列号: {self.device_info['serial_number']}")
        print(f"{self.prefix}     固件版本: {self.device_info['firmware_version']}")
        print(f"{self.prefix}     连接器类型: {self.device_info['connector_type']}")
        print(f"{self.prefix}     充电速率: {self.device_info['charging_rate']} kW")
        
        response = await self.send_message("BootNotification", payload)
        if response:
            status = response.get("status", "")
            print(f"{self.prefix}   BootNotification 状态: {status}")
            return status in ["Accepted", "Pending"]
        return False
    
    async def send_heartbeat(self) -> bool:
        """发送心跳"""
        response = await self.send_message("Heartbeat")
        if response:
            timestamp = response.get("currentTime", "")
            print(f"{self.prefix}   当前时间: {timestamp}")
            return True
        return False
    
    async def send_status_notification(self, status: str, connector_id: int = 0) -> bool:
        """发送状态通知"""
        payload = {
            "connectorId": connector_id,
            "status": status
        }
        response = await self.send_message("StatusNotification", payload)
        self.status = ChargerStatus(status)
        return response is not None
    
    async def send_authorize(self, id_tag: str) -> bool:
        """发送授权请求"""
        payload = {
            "idTag": id_tag
        }
        response = await self.send_message("Authorize", payload)
        if response:
            auth_status = response.get("status", "")
            print(f"{self.prefix}   授权状态: {auth_status}")
            return auth_status in ["Accepted", "ConcurrentTx"]
        return False
    
    async def send_start_transaction(self, transaction_id: Optional[int] = None, 
                                     id_tag: str = "TEST_TAG_001") -> bool:
        """发送开始事务"""
        if transaction_id is None:
            transaction_id = self.message_id_counter
            self.message_id_counter += 1
        
        payload = {
            "connectorId": self.connector_id,
            "idTag": id_tag,
            "meterStart": self.meter_value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        response = await self.send_message("StartTransaction", payload)
        if response:
            tx_id = response.get("transactionId")
            if tx_id:
                self.transaction_id = tx_id
                self.current_id_tag = id_tag
                print(f"{self.prefix}   事务ID: {tx_id}")
                return True
        return False
    
    async def send_stop_transaction(self, transaction_id: Optional[int] = None, 
                                    reason: str = "Local") -> bool:
        """发送停止事务"""
        if transaction_id is None:
            transaction_id = self.transaction_id
        
        if transaction_id is None:
            print(f"{self.prefix} ⚠ 没有活跃的事务")
            return False
        
        payload = {
            "transactionId": transaction_id,
            "meterStop": self.meter_value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason
        }
        
        response = await self.send_message("StopTransaction", payload)
        if response:
            self.transaction_id = None
            self.current_id_tag = None
            return True
        return False
    
    async def send_meter_values(self, transaction_id: Optional[int] = None, 
                                meter_value: Optional[int] = None) -> bool:
        """发送计量值"""
        if transaction_id is None:
            transaction_id = self.transaction_id
        
        if meter_value is not None:
            self.meter_value = meter_value
        else:
            self.meter_value += 10  # 默认增加10 Wh
        
        payload = {
            "connectorId": self.connector_id,
            "meterValue": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "sampledValue": [
                        {
                            "value": str(self.meter_value),
                            "context": "Sample.Periodic",
                            "format": "Raw",
                            "measurand": "Energy.Active.Import.Register",
                            "location": "Outlet",
                            "unit": "Wh"
                        }
                    ]
                }
            ]
        }
        
        if transaction_id:
            payload["transactionId"] = transaction_id
        
        response = await self.send_message("MeterValues", payload)
        return response is not None
    
    async def send_data_transfer(self, vendor_id: str = "TestVendor", 
                                 message_id: str = "test_message",
                                 data: str = "test_data") -> bool:
        """发送数据传输"""
        payload = {
            "vendorId": vendor_id,
            "messageId": message_id,
            "data": data
        }
        response = await self.send_message("DataTransfer", payload)
        return response is not None
    
    async def send_diagnostics_status_notification(self, status: str = "Idle") -> bool:
        """发送诊断状态通知"""
        payload = {
            "status": status
        }
        response = await self.send_message("DiagnosticsStatusNotification", payload)
        return response is not None
    
    async def send_firmware_status_notification(self, status: str = "Idle") -> bool:
        """发送固件状态通知"""
        payload = {
            "status": status
        }
        response = await self.send_message("FirmwareStatusNotification", payload)
        return response is not None
    
    async def handle_remote_start_transaction(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理远程启动事务请求"""
        print(f"{self.prefix}   收到远程启动请求")
        connector_id = request.get("connectorId", 1)
        id_tag = request.get("idTag", "TEST_TAG_001")
        
        # 保存待处理的远程启动请求
        self.pending_remote_start = {
            "connectorId": connector_id,
            "idTag": id_tag
        }
        
        # 如果当前可用，立即启动
        if self.status == ChargerStatus.AVAILABLE:
            # 发送状态变化
            await self.send_status_notification("Preparing", connector_id)
            await asyncio.sleep(0.5)
            
            # 发送授权
            await self.send_authorize(id_tag)
            await asyncio.sleep(0.5)
            
            # 启动事务
            await self.send_start_transaction(id_tag=id_tag)
            await asyncio.sleep(0.5)
            
            # 发送充电状态
            await self.send_status_notification("Charging", connector_id)
            
            # 返回成功响应
            return {
                "status": "Accepted"
            }
        else:
            # 返回拒绝响应
            return {
                "status": "Rejected",
                "message": "Charger not available"
            }
    
    async def handle_remote_stop_transaction(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理远程停止事务请求"""
        print(f"{self.prefix}   收到远程停止请求")
        transaction_id = request.get("transactionId")
        
        if self.transaction_id and (transaction_id is None or transaction_id == self.transaction_id):
            # 发送停止事务
            await self.send_stop_transaction(self.transaction_id, reason="Remote")
            await asyncio.sleep(0.5)
            
            # 发送状态变化
            await self.send_status_notification("Finishing", self.connector_id)
            await asyncio.sleep(0.5)
            await self.send_status_notification("Available", self.connector_id)
            
            return {
                "status": "Accepted"
            }
        else:
            return {
                "status": "Rejected",
                "message": "Transaction not found"
            }
    
    async def handle_change_configuration(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理更改配置请求"""
        print(f"{self.prefix}   收到更改配置请求")
        key = request.get("key")
        value = request.get("value")
        print(f"{self.prefix}   配置项: {key} = {value}")
        
        return {
            "status": "Accepted"
        }
    
    async def handle_get_configuration(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取配置请求"""
        print(f"{self.prefix}   收到获取配置请求")
        
        return {
            "configurationKey": [
                {
                    "key": "HeartbeatInterval",
                    "value": "30",
                    "readonly": False
                },
                {
                    "key": "MeterValueSampleInterval",
                    "value": "60",
                    "readonly": False
                }
            ],
            "unknownKey": []
        }
    
    async def handle_reset(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理重置请求"""
        print(f"{self.prefix}   收到重置请求")
        reset_type = request.get("type", "Soft")
        print(f"{self.prefix}   重置类型: {reset_type}")
        
        # 模拟重置过程
        await self.send_status_notification("Unavailable", 0)
        await asyncio.sleep(1.0)
        await self.send_boot_notification()
        await self.send_status_notification("Available", 0)
        
        return {
            "status": "Accepted"
        }
    
    async def handle_unlock_connector(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理解锁连接器请求"""
        print(f"{self.prefix}   收到解锁连接器请求")
        connector_id = request.get("connectorId", 1)
        
        return {
            "status": "Unlocked"
        }
    
    async def handle_change_availability(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理更改可用性请求"""
        print(f"{self.prefix}   收到更改可用性请求")
        connector_id = request.get("connectorId", 0)
        availability_type = request.get("type", "Inoperative")
        
        if availability_type == "Operative":
            await self.send_status_notification("Available", connector_id)
        else:
            await self.send_status_notification("Unavailable", connector_id)
        
        return {
            "status": "Accepted"
        }
    
    async def handle_message_from_csms(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理来自CSMS的消息"""
        action = message.get("action", "")
        payload = message.get("payload", {})
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"{self.prefix} ← [{timestamp}] 收到服务器请求: {action}")
        print(f"{self.prefix}    载荷: {json.dumps(payload, ensure_ascii=False)}")
        
        # 路由到对应的处理器
        handlers = {
            "RemoteStartTransaction": self.handle_remote_start_transaction,
            "RemoteStopTransaction": self.handle_remote_stop_transaction,
            "ChangeConfiguration": self.handle_change_configuration,
            "GetConfiguration": self.handle_get_configuration,
            "Reset": self.handle_reset,
            "UnlockConnector": self.handle_unlock_connector,
            "ChangeAvailability": self.handle_change_availability,
            "SetChargingProfile": lambda req: {"status": "Accepted"},
            "ClearChargingProfile": lambda req: {"status": "Accepted"},
            "GetDiagnostics": lambda req: {"status": "Accepted", "fileName": ""},
            "UpdateFirmware": lambda req: {"status": "Accepted"},
            "DataTransfer": lambda req: {"status": "Accepted", "data": ""},
            "ReserveNow": lambda req: {"status": "Accepted"},
            "CancelReservation": lambda req: {"status": "Accepted"},
            "GetLocalListVersion": lambda req: {"listVersion": 0},
            "SendLocalList": lambda req: {"status": "Accepted"},
        }
        
        handler = handlers.get(action)
        if handler:
            try:
                print(f"{self.prefix}    开始处理请求: {action}")
                response = await handler(payload)
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                print(f"{self.prefix} → [{timestamp}] 请求处理完成: {action}")
                print(f"{self.prefix}    响应: {json.dumps(response, ensure_ascii=False)}")
                return response
            except Exception as e:
                print(f"{self.prefix} ✗ 处理消息失败: {e}")
                import traceback
                traceback.print_exc()
                return {"status": "Rejected", "message": str(e)}
        else:
            print(f"{self.prefix} ⚠ 未知消息类型: {action}")
            return None
    
    async def send_response(self, response: Dict[str, Any]):
        """发送响应消息"""
        if not self.ws:
            return
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        try:
            await self.ws.send(json.dumps(response))
            print(f"{self.prefix} → [{timestamp}] 发送响应到服务器")
            print(f"{self.prefix}    响应内容: {json.dumps(response, ensure_ascii=False)}")
        except Exception as e:
            print(f"{self.prefix} ✗ [{timestamp}] 发送响应失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def message_listener(self):
        """监听来自CSMS的消息"""
        if not self.ws:
            return
        
        try:
            while True:
                try:
                    message_raw = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                    message = json.loads(message_raw)
                    
                    # 处理来自CSMS的消息
                    response = await self.handle_message_from_csms(message)
                    if response:
                        await self.send_response(response)
                    
                except asyncio.TimeoutError:
                    # 超时是正常的，继续监听
                    continue
                except websockets.exceptions.ConnectionClosed:
                    print(f"{self.prefix} 连接已关闭")
                    break
                except Exception as e:
                    print(f"{self.prefix} ✗ 接收消息错误: {e}")
                    break
        except Exception as e:
            print(f"{self.prefix} ✗ 消息监听器错误: {e}")
    
    async def heartbeat_loop(self, interval: int = 30):
        """心跳循环"""
        while True:
            await asyncio.sleep(interval)
            if self.ws:
                try:
                    await self.send_heartbeat()
                except Exception as e:
                    print(f"{self.prefix} ✗ 心跳失败: {e}")
                    break
    
    async def run_validation_mode(self):
        """运行验证模式 - 发送所有OCPP验证工具需要的消息"""
        print(f"\n{self.prefix} 开始OCPP验证模式")
        print(f"{self.prefix} =====================")
        
        # 1. BootNotification
        print(f"\n{self.prefix} [1/10] 发送 BootNotification")
        await self.send_boot_notification()
        await asyncio.sleep(0.5)
        
        # 2. StatusNotification
        print(f"\n{self.prefix} [2/10] 发送 StatusNotification")
        await self.send_status_notification("Available", 0)
        await asyncio.sleep(0.5)
        
        # 3. Heartbeat
        print(f"\n{self.prefix} [3/10] 发送 Heartbeat")
        await self.send_heartbeat()
        await asyncio.sleep(0.5)
        
        # 4. Authorize
        print(f"\n{self.prefix} [4/10] 发送 Authorize")
        await self.send_authorize("TEST_TAG_001")
        await asyncio.sleep(0.5)
        
        # 5. StartTransaction
        print(f"\n{self.prefix} [5/10] 发送 StartTransaction")
        await self.send_start_transaction(id_tag="TEST_TAG_001")
        await asyncio.sleep(0.5)
        
        # 6. MeterValues
        print(f"\n{self.prefix} [6/10] 发送 MeterValues")
        await self.send_meter_values()
        await asyncio.sleep(0.5)
        
        # 7. StopTransaction
        print(f"\n{self.prefix} [7/10] 发送 StopTransaction")
        await self.send_stop_transaction()
        await asyncio.sleep(0.5)
        
        # 8. DataTransfer
        print(f"\n{self.prefix} [8/10] 发送 DataTransfer")
        await self.send_data_transfer()
        await asyncio.sleep(0.5)
        
        # 9. DiagnosticsStatusNotification
        print(f"\n{self.prefix} [9/10] 发送 DiagnosticsStatusNotification")
        await self.send_diagnostics_status_notification()
        await asyncio.sleep(0.5)
        
        # 10. FirmwareStatusNotification
        print(f"\n{self.prefix} [10/10] 发送 FirmwareStatusNotification")
        await self.send_firmware_status_notification()
        await asyncio.sleep(0.5)
        
        print(f"\n{self.prefix} ✓ 所有验证消息已发送")
        print(f"{self.prefix} =====================")
        
        # 继续运行，监听远程控制消息
        print(f"\n{self.prefix} 进入在线模式，等待远程控制消息...")
        
        # 启动心跳和消息监听
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        listener_task = asyncio.create_task(self.message_listener())
        
        # 等待任务完成
        try:
            await asyncio.gather(heartbeat_task, listener_task)
        except asyncio.CancelledError:
            pass
    
    async def run_normal_mode(self):
        """运行正常模式 - 模拟正常充电桩行为"""
        print(f"\n{self.prefix} 启动正常模式")
        
        # 初始化序列
        await self.send_boot_notification()
        await asyncio.sleep(0.5)
        await self.send_status_notification("Available", 0)
        
        print(f"{self.prefix} ✓ 初始化完成，进入在线模式")
        
        # 启动心跳和消息监听
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        listener_task = asyncio.create_task(self.message_listener())
        
        # 等待任务完成
        try:
            await asyncio.gather(heartbeat_task, listener_task)
        except asyncio.CancelledError:
            pass
    
    async def run(self, validation_mode: bool = False):
        """运行模拟器"""
        if not await self.connect():
            return
        
        try:
            if validation_mode:
                await self.run_validation_mode()
            else:
                await self.run_normal_mode()
        except KeyboardInterrupt:
            print(f"\n{self.prefix} 收到中断信号，正在退出...")
        except Exception as e:
            print(f"{self.prefix} ✗ 运行错误: {e}", exc_info=True)
        finally:
            if self.ws:
                await self.ws.close()


def print_qr_code(charger_id: str, device_info: Optional[Dict[str, str]] = None) -> None:
    """打印二维码和设备信息"""
    try:
        qr = qrcode.QRCode(version=1, box_size=2, border=1)
        qr.add_data(charger_id)
        qr.make(fit=True)
        
        print("\n" + "=" * 60)
        print(f"📱 充电桩二维码: {charger_id}")
        print("=" * 60)
        
        # 显示设备信息（如果提供）
        if device_info:
            print(f"\n设备信息:")
            print(f"  厂商: {device_info.get('vendor', 'N/A')}")
            print(f"  型号: {device_info.get('model', 'N/A')}")
            print(f"  序列号: {device_info.get('serial_number', 'N/A')}")
            print(f"  固件版本: {device_info.get('firmware_version', 'N/A')}")
            print(f"  连接器类型: {device_info.get('connector_type', 'N/A')}")
            print(f"  充电速率: {device_info.get('charging_rate', 'N/A')} kW")
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
    except Exception:
        pass  # 如果二维码生成失败，继续运行


def main():
    parser = argparse.ArgumentParser(description="增强版 OCPP 1.6 充电桩模拟器")
    parser.add_argument(
        "--id",
        default="CP-0001",
        help="充电桩ID (默认: CP-0001)"
    )
    parser.add_argument(
        "--url",
        default="ws://localhost:9000/ocpp",
        help="CSMS WebSocket URL (默认: ws://localhost:9000/ocpp)"
    )
    parser.add_argument(
        "--validation",
        action="store_true",
        help="运行验证模式，发送所有OCPP验证工具需要的消息"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="并发运行的充电桩实例数 (默认: 1)"
    )
    parser.add_argument(
        "--vendor",
        type=str,
        default=None,
        help="厂商名称（可选，不指定则自动生成）"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="型号（可选，不指定则自动生成）"
    )
    parser.add_argument(
        "--firmware",
        type=str,
        default=None,
        help="固件版本（可选，不指定则自动生成，格式：x.y.z）"
    )
    parser.add_argument(
        "--serial",
        type=str,
        default=None,
        help="序列号（可选，不指定则自动生成）"
    )
    
    args = parser.parse_args()
    
    if args.count == 1:
        # 单个实例
        simulator = OCPPSimulator(
            args.id, 
            args.url,
            vendor=args.vendor,
            model=args.model,
            firmware_version=args.firmware,
            serial_number=args.serial
        )
        # 打印二维码和设备信息
        print_qr_code(args.id, simulator.device_info)
        asyncio.run(simulator.run(validation_mode=args.validation))
    else:
        # 多个实例
        async def run_all():
            tasks = []
            base_prefix = "CP-"
            if "-" in args.id:
                base_prefix = args.id.rsplit("-", 1)[0] + "-"
            
            for i in range(args.count):
                if args.count <= 99:
                    charger_id = f"{base_prefix}{i + 1:04d}"
                else:
                    charger_id = f"{base_prefix}{i + 1:05d}"
                
                # 每个实例使用不同的设备信息（如果指定了固定值，则复用）
                simulator = OCPPSimulator(
                    charger_id, 
                    args.url,
                    vendor=args.vendor,
                    model=args.model,
                    firmware_version=args.firmware,
                    serial_number=args.serial
                )
                task = simulator.run(validation_mode=args.validation)
                tasks.append(task)
                await asyncio.sleep(0.5)  # 错开启动时间
            
            await asyncio.gather(*tasks)
        
        asyncio.run(run_all())


if __name__ == "__main__":
    main()

