#!/usr/bin/env python3
#
# 列出所有已连接的充电桩
#

import argparse
import requests
import json
from typing import List, Dict, Any


def list_connected_chargers(server_url: str) -> List[Dict[str, Any]]:
    """列出所有已连接的充电桩"""
    server_url = server_url.rstrip('/')
    base_url = f"{server_url}/api/v1"
    
    try:
        # 获取所有充电桩
        response = requests.get(f"{base_url}/chargers", timeout=10)
        if response.status_code != 200:
            print(f"✗ 获取充电桩列表失败: HTTP {response.status_code}")
            return []
        
        chargers = response.json()
        
        # 过滤出已连接的充电桩（有 last_seen 且状态不是 Unknown）
        connected = []
        for charger in chargers:
            status = charger.get('status', 'Unknown')
            last_seen = charger.get('last_seen')
            
            # 判断是否连接：状态不是 Unknown 且有 last_seen
            if status != 'Unknown' and last_seen:
                connected.append(charger)
        
        return connected
    except Exception as e:
        print(f"✗ 获取充电桩列表失败: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="列出所有已连接的充电桩")
    parser.add_argument(
        "--server",
        type=str,
        default="http://47.236.134.99:9000",
        help="CSMS服务器URL（默认: http://47.236.134.99:9000）"
    )
    args = parser.parse_args()
    
    print("=" * 80)
    print("查询已连接的充电桩")
    print("=" * 80)
    print(f"服务器: {args.server}")
    print()
    
    connected = list_connected_chargers(args.server)
    
    if not connected:
        print("✗ 未找到已连接的充电桩")
        print("\n提示：")
        print("  1. 确保充电桩已通过 WebSocket 连接到服务器")
        print("  2. 检查服务器地址是否正确")
        print("  3. 检查充电桩是否已发送 BootNotification")
        return
    
    print(f"✓ 找到 {len(connected)} 个已连接的充电桩：\n")
    
    for i, charger in enumerate(connected, 1):
        print(f"{i}. 充电桩ID: {charger.get('id')}")
        print(f"   厂商: {charger.get('vendor', 'N/A')}")
        print(f"   型号: {charger.get('model', 'N/A')}")
        print(f"   状态: {charger.get('status', 'N/A')}")
        print(f"   最后心跳: {charger.get('last_seen', 'N/A')}")
        print()
    
    print("=" * 80)
    print("使用以下命令测试充电桩：")
    print("=" * 80)
    for charger in connected:
        charger_id = charger.get('id')
        print(f"python3 charger-sim/verify_ocpp_protocol.py --server {args.server} --charge-point-id {charger_id}")
    print()


if __name__ == "__main__":
    main()

