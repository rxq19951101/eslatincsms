#
# 本文件实现一个简易 OCPP 客户端模拟器：按序发送常见动作到 /ocpp。
# 仅用于本地测试，消息为简化 JSON（字段 action + payload）。
# 支持异常重试与超时控制。

import argparse
import asyncio
import json
import sys
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

import qrcode
import websockets


def print_qr_code(charger_id: str) -> None:
    """打印二维码到控制台，供 App 扫码使用"""
    qr = qrcode.QRCode(version=1, box_size=2, border=1)
    # 二维码内容：充电桩 ID
    qr.add_data(charger_id)
    qr.make(fit=True)
    
    print("\n" + "=" * 60)
    print(f"📱 充电桩二维码: {charger_id}")
    print("=" * 60)
    # 生成 ASCII 二维码
    img = qr.make_image(fill_color="black", back_color="white")
    # 转换为 ASCII 字符画（仅在终端显示）
    size = img.size[0]
    qr_str = ""
    for y in range(size):
        for x in range(size):
            # 检查是否是二维码的白色/黑色块
            pixel = img.getpixel((x, y))
            if pixel == 0:
                qr_str += "██"
            else:
                qr_str += "  "
        qr_str += "\n"
    print(qr_str)
    print("提示：使用 App 的扫码功能扫描上方二维码")
    print("=" * 60 + "\n")


async def run_simulator(charger_id: str, url: str, max_retries: int = 3) -> None:
    # 显示充电桩二维码供 App 扫码
    print_qr_code(charger_id)
    
    ws_url = f"{url}?id={charger_id}"
    prefix = f"[{charger_id}]"
    
    attempt = 0
    while True:  # 无限重连循环
        try:
            attempt += 1
            print(f"{prefix} connecting: {ws_url} (attempt {attempt})")
            async with websockets.connect(
                ws_url, subprotocols=["ocpp1.6"], ping_interval=None, close_timeout=10
            ) as ws:
                hello = await ws.recv()
                print(f"{prefix} ✓ connected")
                print(f"{prefix}   response: {hello}")

                async def send(action: str, payload: Optional[Dict[str, Any]] = None):
                    msg = {"action": action}
                    if payload:
                        msg["payload"] = payload
                    await ws.send(json.dumps(msg))
                    print(f"{prefix} → {action} {json.dumps(payload) if payload else ''}")
                    
                    try:
                        resp_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        resp = json.loads(resp_raw)
                        status = resp.get("status", "N/A")
                        print(f"{prefix} ← {action} status={status}")
                    except asyncio.TimeoutError:
                        print(f"{prefix} ← {action} TIMEOUT (no response in 5s)")

                # Boot
                # 根据充电桩 ID 生成不同的厂商和型号
                vendor_model_map = {
                    "CP-0001": {"vendor": "ABB", "model": "Terra AC Wallbox", "firmwareVersion": "1.5.2", "serialNumber": "ABB-001234"},
                    "CP-0002": {"vendor": "Tesla", "model": "Supercharger V3", "firmwareVersion": "2.1.0", "serialNumber": "TSC-005678"},
                    "CP-0003": {"vendor": "Schneider Electric", "model": "EVlink Charging Station", "firmwareVersion": "3.2.1", "serialNumber": "EVL-009012"},
                    "CP-0004": {"vendor": "Siemens", "model": "VersiCharge", "firmwareVersion": "1.8.5", "serialNumber": "SIE-003456"},
                    "CP-0005": {"vendor": "ChargePoint", "model": "CPF50", "firmwareVersion": "4.0.3", "serialNumber": "CHP-007890"},
                }
                
                # 默认值或根据 ID 选择
                charger_info = vendor_model_map.get(charger_id, {
                    "vendor": "Generic EVSE",
                    "model": "Standard Charger",
                    "firmwareVersion": "1.0.0",
                    "serialNumber": f"GEN-{charger_id.replace('CP-', '').zfill(6)}"
                })
                
                await send("BootNotification", {
                    "chargePointVendor": charger_info["vendor"],
                    "chargePointModel": charger_info["model"],
                    "firmwareVersion": charger_info["firmwareVersion"],
                    "chargePointSerialNumber": charger_info["serialNumber"]
                })
                await asyncio.sleep(0.3)

                # StatusNotification - 设置为可用状态
                await send("StatusNotification", {"status": "Available"})
                await asyncio.sleep(0.3)

                print(f"{prefix} ✓ 初始化完成，进入在线模式（保持连接并定期发送心跳）")
                print(f"{prefix}   支持功能: RemoteStartTransaction, RemoteStopTransaction, MeterValues")
                
                # 保持在线：定期发送心跳并监听消息
                async def heartbeat_loop():
                    """每 30 秒发送一次心跳"""
                    while True:
                        await asyncio.sleep(30)
                        try:
                            msg = {"action": "Heartbeat"}
                            await ws.send(json.dumps(msg))
                            print(f"{prefix} → Heartbeat")
                            # 不等待响应，避免阻塞
                        except Exception as e:
                            print(f"{prefix} ✗ 心跳发送失败: {e}")
                            break
                
                # 充电状态管理
                charging_state = {
                    "is_charging": False,
                    "transaction_id": None,
                    "meter_value": 0,
                    "id_tag": None
                }
                
                async def meter_values_loop():
                    """充电时定期发送计量值"""
                    while True:
                        await asyncio.sleep(10)  # 每10秒发送一次
                        if charging_state["is_charging"]:
                            # 模拟电量增加（每次增加 100-500 Wh）
                            charging_state["meter_value"] += random.randint(100, 500)
                            
                            try:
                                meter_msg = {
                                    "action": "MeterValues",
                                    "payload": {
                                        "connectorId": 1,
                                        "transactionId": charging_state["transaction_id"],
                                        "meterValue": [
                                            {
                                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                                "sampledValue": [
                                                    {
                                                        "value": str(charging_state["meter_value"]),
                                                        "context": "Sample.Periodic",
                                                        "format": "Raw",
                                                        "measurand": "Energy.Active.Import.Register",
                                                        "unit": "Wh"
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                }
                                await ws.send(json.dumps(meter_msg))
                                print(f"{prefix} → MeterValues transactionId={charging_state['transaction_id']} meter={charging_state['meter_value']} Wh")
                            except Exception as e:
                                print(f"{prefix} ✗ MeterValues 发送失败: {e}")
                                break
                
                async def message_listener():
                    """持续监听来自 CSMS 的消息"""
                    try:
                        while True:
                            try:
                                msg_raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                                msg = json.loads(msg_raw)
                                action = msg.get("action", "")
                                payload = msg.get("payload", {})
                                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                                print(f"{prefix} ← [{timestamp}] 收到服务器请求: {action}")
                                if payload:
                                    print(f"{prefix}    载荷: {json.dumps(payload, ensure_ascii=False)}")
                                
                                # 处理 RemoteStartTransaction
                                if action == "RemoteStartTransaction":
                                    id_tag = payload.get("idTag", "TAG001")
                                    connector_id = payload.get("connectorId", 1)
                                    
                                    print(f"{prefix}   处理远程启动充电请求: idTag={id_tag}, connectorId={connector_id}")
                                    
                                    # 生成交易ID
                                    transaction_id = int(time.time())
                                    charging_state["transaction_id"] = transaction_id
                                    charging_state["id_tag"] = id_tag
                                    charging_state["meter_value"] = 0
                                    
                                    # 发送 StartTransaction
                                    start_msg = {
                                        "action": "StartTransaction",
                                        "payload": {
                                            "connectorId": connector_id,
                                            "idTag": id_tag,
                                            "meterStart": 0,
                                            "timestamp": datetime.now(timezone.utc).isoformat()
                                        }
                                    }
                                    await ws.send(json.dumps(start_msg))
                                    print(f"{prefix} → StartTransaction transactionId={transaction_id} idTag={id_tag}")
                                    
                                    # 等待响应
                                    try:
                                        resp_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                                        resp = json.loads(resp_raw)
                                        print(f"{prefix} ← StartTransaction 响应: {json.dumps(resp)}")
                                        
                                        # 如果成功，开始充电
                                        if resp.get("transactionId") or resp.get("status") == "Accepted":
                                            charging_state["is_charging"] = True
                                            print(f"{prefix} ✓ 开始充电，交易ID: {transaction_id}")
                                            
                                            # 更新状态为充电中
                                            status_msg = {
                                                "action": "StatusNotification",
                                                "payload": {
                                                    "connectorId": connector_id,
                                                    "errorCode": "NoError",
                                                    "status": "Charging"
                                                }
                                            }
                                            await ws.send(json.dumps(status_msg))
                                            print(f"{prefix} → StatusNotification status=Charging")
                                            
                                            # 启动计量值循环
                                            asyncio.create_task(meter_values_loop())
                                    except asyncio.TimeoutError:
                                        print(f"{prefix} ← StartTransaction 响应超时")
                                
                                # 处理 RemoteStopTransaction
                                elif action == "RemoteStopTransaction":
                                    transaction_id = payload.get("transactionId")
                                    print(f"{prefix}   处理远程停止充电请求: transactionId={transaction_id}")
                                    
                                    if charging_state["is_charging"]:
                                        # 发送 StopTransaction
                                        stop_msg = {
                                            "action": "StopTransaction",
                                            "payload": {
                                                "transactionId": charging_state["transaction_id"],
                                                "meterStop": charging_state["meter_value"],
                                                "reason": "Remote",
                                                "timestamp": datetime.now(timezone.utc).isoformat()
                                            }
                                        }
                                        await ws.send(json.dumps(stop_msg))
                                        print(f"{prefix} → StopTransaction transactionId={charging_state['transaction_id']} meterStop={charging_state['meter_value']} Wh")
                                        
                                        # 等待响应
                                        try:
                                            resp_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                                            resp = json.loads(resp_raw)
                                            print(f"{prefix} ← StopTransaction 响应: {json.dumps(resp)}")
                                            
                                            # 停止充电
                                            charging_state["is_charging"] = False
                                            charging_state["transaction_id"] = None
                                            charging_state["meter_value"] = 0
                                            print(f"{prefix} ✓ 停止充电")
                                            
                                            # 更新状态为可用
                                            status_msg = {
                                                "action": "StatusNotification",
                                                "payload": {
                                                    "connectorId": 1,
                                                    "errorCode": "NoError",
                                                    "status": "Available"
                                                }
                                            }
                                            await ws.send(json.dumps(status_msg))
                                            print(f"{prefix} → StatusNotification status=Available")
                                        except asyncio.TimeoutError:
                                            print(f"{prefix} ← StopTransaction 响应超时")
                                    else:
                                        print(f"{prefix}   警告: 当前未在充电状态")
                                
                            except asyncio.TimeoutError:
                                # 超时是正常的，继续监听
                                continue
                            except Exception as e:
                                print(f"{prefix} ✗ 接收消息错误: {e}")
                                import traceback
                                traceback.print_exc()
                                break
                    except Exception as e:
                        print(f"{prefix} ✗ 消息监听器错误: {e}")
                        import traceback
                        traceback.print_exc()
                
                # 启动心跳和消息监听任务
                heartbeat_task = asyncio.create_task(heartbeat_loop())
                listener_task = asyncio.create_task(message_listener())
                
                # 等待任一任务完成（通常是连接断开）
                done, pending = await asyncio.wait(
                    [heartbeat_task, listener_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # 取消未完成的任务
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                print(f"{prefix} 连接已断开，准备重连...")
                await asyncio.sleep(1)

        except websockets.exceptions.InvalidStatusCode as e:
            print(f"{prefix} ✗ connection refused: {e}")
            print(f"{prefix}   等待 5 秒后重试...")
            await asyncio.sleep(5)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"{prefix} ✗ connection closed: {e}")
            print(f"{prefix}   等待 3 秒后重连...")
            await asyncio.sleep(3)
        except KeyboardInterrupt:
            print(f"\n{prefix} 收到中断信号，正在退出...")
            sys.exit(0)
        except Exception as e:
            print(f"{prefix} ✗ error: {e}")
            print(f"{prefix}   等待 3 秒后重试...")
            await asyncio.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple OCPP 1.6J simulator")
    parser.add_argument(
        "--id",
        default="CP-0001",
        help="Charger ID (default: CP-0001), used as base when --count > 1",
    )
    parser.add_argument(
        "--url",
        default="ws://localhost:9000/ocpp",
        help="CSMS WebSocket url (default: ws://localhost:9000/ocpp)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of charger instances to run concurrently (default: 1)",
    )
    args = parser.parse_args()

    if args.count == 1:
        # Single instance: use --id as-is
        asyncio.run(run_simulator(args.id, args.url))
    else:
        # Multiple instances: spawn CP-0001, CP-0002, ..., CP-00NN
        async def run_all() -> None:
            tasks = []
            # Extract base prefix from default ID (e.g., "CP-" from "CP-0001")
            base_prefix = "CP-"
            if "-" in args.id:
                base_prefix = args.id.rsplit("-", 1)[0] + "-"
            
            for i in range(args.count):
                # Generate ID: CP-0001, CP-0002, etc.
                if args.count <= 99:
                    charger_id = f"{base_prefix}{i + 1:04d}"
                else:
                    charger_id = f"{base_prefix}{i + 1:05d}"
                task = run_simulator(charger_id, args.url)
                tasks.append(task)
            await asyncio.gather(*tasks)
        
        asyncio.run(run_all())


if __name__ == "__main__":
    main()


