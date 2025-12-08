#
# 本文件实现交互式充电桩模拟器：允许手动切换状态。
# 支持命令：boot, heartbeat, status <state>, auth <tag>, start, meter <value>, stop, quit
# 仅用于本地测试与演示。
#

import argparse
import asyncio
import json
import sys
from typing import Any, Dict, Optional

import qrcode
import websockets
import requests


def print_qr_code(charger_id: str) -> None:
    """打印二维码到控制台，供 App 扫码使用"""
    qr = qrcode.QRCode(version=1, box_size=2, border=1)
    qr.add_data(charger_id)
    qr.make(fit=True)
    
    print("\n" + "=" * 60)
    print(f"📱 充电桩二维码: {charger_id}")
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


async def interactive_simulator(charger_id: str, url: str) -> None:
    # 显示充电桩二维码供 App 扫码
    print_qr_code(charger_id)
    
    ws_url = f"{url}?id={charger_id}"
    prefix = f"[{charger_id}]"

    try:
        print(f"{prefix} connecting: {ws_url}")
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
                    return resp
                except asyncio.TimeoutError:
                    print(f"{prefix} ← {action} TIMEOUT (no response in 5s)")
                    return None

            print(f"\n{prefix} 交互式控制模式")
            print("可用命令:")
            print("  boot                  - 发送 BootNotification")
            print("  hb                    - 发送 Heartbeat")
            print("  status <state>        - 发送 StatusNotification (Available/Preparing/Charging/SuspendedEVSE/Faulted)")
            print("  auth <tag>            - 发送 Authorize")
            print("  start [txid]          - 发送 StartTransaction (可选交易ID)")
            print("  meter <value>         - 发送 MeterValues")
            print("  stop [reason]         - 发送 StopTransaction")
            print("  quit                  - 退出")
            print()

            while True:
                try:
                    cmd_line = input(f"{prefix} > ").strip()
                    if not cmd_line:
                        continue

                    parts = cmd_line.split()
                    cmd = parts[0].lower()

                    if cmd == "quit" or cmd == "q":
                        print(f"{prefix} 退出交互模式")
                        break

                    elif cmd == "boot":
                        # 发送完整的 BootNotification 信息
                        await send("BootNotification", {
                            "chargePointVendor": "Generic EVSE",
                            "chargePointModel": "Interactive Simulator",
                            "firmwareVersion": "1.0.0",
                            "chargePointSerialNumber": f"SIM-{charger_id.replace('CP-', '').zfill(6)}"
                        })

                    elif cmd == "hb":
                        await send("Heartbeat")

                    elif cmd == "status" and len(parts) >= 2:
                        await send("StatusNotification", {"status": parts[1]})

                    elif cmd == "auth" and len(parts) >= 2:
                        await send("Authorize", {"idTag": parts[1]})

                    elif cmd == "start":
                        tx_id = int(parts[1]) if len(parts) >= 2 else 1001
                        await send("StartTransaction", {"transactionId": tx_id})

                    elif cmd == "meter" and len(parts) >= 2:
                        meter_val = int(parts[1])
                        await send("MeterValues", {"meter": meter_val})

                    elif cmd == "stop":
                        reason = parts[1] if len(parts) >= 2 else "Local"
                        await send("StopTransaction", {"reason": reason})

                    else:
                        print(f"未知命令: {cmd_line}")
                        print("输入命令或 'quit' 退出")

                except KeyboardInterrupt:
                    print(f"\n{prefix} 退出交互模式")
                    break
                except Exception as e:
                    print(f"{prefix} 错误: {e}")

    except websockets.exceptions.InvalidStatusCode as e:
        print(f"{prefix} ✗ connection refused: {e}")
        sys.exit(1)
    except websockets.exceptions.ConnectionClosed as e:
        print(f"{prefix} ✗ connection closed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"{prefix} ✗ error: {e}")
        sys.exit(1)


def update_charger_location(charger_id: str, latitude: float, longitude: float, address: str = "") -> bool:
    """更新充电桩位置到 CSMS"""
    try:
        url = "http://localhost:9000/api/updateLocation"
        payload = {
            "chargePointId": charger_id,
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
        }
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            print(f"[{charger_id}] ✓ Location updated: lat={latitude}, lng={longitude}")
            return True
        else:
            print(f"[{charger_id}] ✗ Location update failed: {res.status_code}")
            return False
    except Exception as e:
        print(f"[{charger_id}] ✗ Location update error: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive OCPP 1.6J simulator")
    parser.add_argument(
        "--id",
        default="CP-0001",
        help="Charger ID (default: CP-0001)",
    )
    parser.add_argument(
        "--url",
        default="ws://localhost:9000/ocpp",
        help="CSMS WebSocket url (default: ws://localhost:9000/ocpp)",
    )
    parser.add_argument(
        "--lat",
        type=float,
        default=None,
        help="Charger latitude (e.g., 39.9042)",
    )
    parser.add_argument(
        "--lng",
        type=float,
        default=None,
        help="Charger longitude (e.g., 116.4074)",
    )
    parser.add_argument(
        "--address",
        default="",
        help="Charger address (optional)",
    )
    args = parser.parse_args()

    # 如果提供了位置信息，先更新位置
    if args.lat is not None and args.lng is not None:
        update_charger_location(args.id, args.lat, args.lng, args.address)

    asyncio.run(interactive_simulator(args.id, args.url))


if __name__ == "__main__":
    main()

