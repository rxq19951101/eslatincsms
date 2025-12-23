#!/usr/bin/env python3
#
# 检查充电桩连接状态的调试脚本
#

import requests
import json
import sys

def check_connection(server_url: str, charge_point_id: str):
    """检查充电桩连接状态"""
    base_url = f"{server_url.rstrip('/')}/api/v1"
    
    print("=" * 80)
    print(f"检查充电桩连接状态: {charge_point_id}")
    print("=" * 80)
    
    # 1. 检查充电桩信息
    print("\n1. 获取充电桩信息...")
    try:
        response = requests.get(f"{base_url}/chargers/{charge_point_id}", timeout=5)
        if response.status_code == 200:
            charger = response.json()
            print(f"✓ 充电桩存在")
            print(f"  状态: {charger.get('status')}")
            print(f"  最后活动: {charger.get('last_seen')}")
        else:
            print(f"✗ 获取充电桩信息失败: HTTP {response.status_code}")
            print(f"  响应: {response.text}")
    except Exception as e:
        print(f"✗ 请求失败: {e}")
    
    # 2. 尝试发送一个简单的 OCPP 请求
    print("\n2. 尝试发送 GetConfiguration 请求...")
    try:
        response = requests.post(
            f"{base_url}/ocpp/get-configuration",
            json={"chargePointId": charge_point_id},
            timeout=5
        )
        if response.status_code == 200:
            result = response.json()
            print(f"✓ 请求成功")
            print(f"  响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
        elif response.status_code == 503:
            error = response.json()
            print(f"✗ 请求失败: {error.get('detail', '未知错误')}")
        else:
            print(f"✗ 请求失败: HTTP {response.status_code}")
            print(f"  响应: {response.text}")
    except Exception as e:
        print(f"✗ 请求失败: {e}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python check_connection_status.py <server_url> <charge_point_id>")
        print("示例: python check_connection_status.py http://47.236.134.99:9000 064808011603585")
        sys.exit(1)
    
    server_url = sys.argv[1]
    charge_point_id = sys.argv[2]
    
    check_connection(server_url, charge_point_id)

