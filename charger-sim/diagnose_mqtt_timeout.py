#!/usr/bin/env python3
#
# MQTT 超时问题诊断脚本
# 用于诊断为什么充电桩没有响应服务器的请求
#

import argparse
import requests
import json
from typing import Optional, Dict


def get_device_info(server_url: str, serial_number: str) -> Optional[Dict]:
    """获取设备信息"""
    try:
        response = requests.get(
            f"{server_url}/api/v1/devices/{serial_number}",
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"✗ 获取设备信息失败: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"✗ 获取设备信息失败: {e}")
        return None


def diagnose_timeout(server_url: str, charge_point_id: str):
    """诊断超时问题"""
    print("=" * 80)
    print("MQTT 超时问题诊断")
    print("=" * 80)
    print(f"服务器: {server_url}")
    print(f"充电桩ID: {charge_point_id}")
    print("=" * 80)
    
    # 1. 检查设备信息
    print("\n1. 检查设备信息...")
    device_info = get_device_info(server_url, charge_point_id)
    if not device_info:
        print("✗ 无法获取设备信息，请确认设备已注册")
        return
    
    print("✓ 设备信息:")
    print(f"  序列号: {device_info.get('serial_number')}")
    print(f"  类型: {device_info.get('device_type_code')}")
    print(f"  MQTT客户端ID: {device_info.get('mqtt_client_id')}")
    print(f"  MQTT用户名: {device_info.get('mqtt_username')}")
    
    type_code = device_info.get('device_type_code')
    serial_number = device_info.get('serial_number')
    
    # 2. 检查预期的 MQTT topic
    print("\n2. 检查 MQTT Topic 配置...")
    expected_down_topic = f"{type_code}/{serial_number}/user/down"
    expected_up_topic = f"{type_code}/{serial_number}/user/up"
    
    print(f"✓ 服务器发送消息到: {expected_down_topic}")
    print(f"✓ 充电桩应订阅: {expected_down_topic}")
    print(f"✓ 充电桩应发送消息到: {expected_up_topic}")
    print(f"✓ 服务器订阅: {expected_up_topic}")
    
    # 3. 检查充电桩连接状态
    print("\n3. 检查充电桩连接状态...")
    try:
        response = requests.get(
            f"{server_url}/api/v1/chargers/{charge_point_id}",
            timeout=10
        )
        if response.status_code == 200:
            charger = response.json()
            print(f"✓ 充电桩状态: {charger.get('status')}")
            print(f"✓ 最后活动: {charger.get('last_seen')}")
            
            if charger.get('status') != 'Available':
                print(f"⚠ 警告: 充电桩状态不是 Available，可能影响响应")
        else:
            print(f"✗ 无法获取充电桩信息: HTTP {response.status_code}")
    except Exception as e:
        print(f"✗ 检查充电桩状态失败: {e}")
    
    # 4. 可能的原因分析
    print("\n4. 可能的原因分析:")
    print("=" * 80)
    print("可能原因 1: 充电桩未订阅正确的 down topic")
    print(f"  解决: 确认充电桩订阅了: {expected_down_topic}")
    print()
    print("可能原因 2: 充电桩订阅的 topic 格式不对")
    print(f"  检查: 充电桩是否订阅了带前导斜杠的 topic: /{expected_down_topic}")
    print(f"  注意: 服务器发送到: {expected_down_topic} (无前导斜杠)")
    print()
    print("可能原因 3: 充电桩不支持 GetConfiguration")
    print("  解决: 检查充电桩是否实现了 GetConfiguration 处理")
    print()
    print("可能原因 4: 充电桩响应格式不正确")
    print("  要求: 响应必须是 OCPP 1.6 标准格式: [3, UniqueId, Payload]")
    print("  示例: [3, 'csms_xxx', {'configurationKey': [...]}]")
    print()
    print("可能原因 5: 充电桩响应发送到了错误的 topic")
    print(f"  要求: 响应必须发送到: {expected_up_topic}")
    print()
    print("可能原因 6: 网络延迟或MQTT broker问题")
    print("  解决: 检查MQTT broker连接状态和网络延迟")
    print()
    
    # 5. 建议的检查步骤
    print("5. 建议的检查步骤:")
    print("=" * 80)
    print("步骤 1: 检查充电桩的 MQTT 订阅")
    print(f"  - 确认充电桩订阅了: {expected_down_topic}")
    print()
    print("步骤 2: 检查充电桩的 OCPP 消息处理")
    print("  - 确认充电桩能正确解析 [2, UniqueId, Action, Payload] 格式")
    print("  - 确认充电桩能正确处理 GetConfiguration action")
    print()
    print("步骤 3: 检查充电桩的响应格式")
    print("  - 确认响应格式: [3, UniqueId, Payload]")
    print(f"  - 确认响应发送到: {expected_up_topic}")
    print()
    print("步骤 4: 使用 MQTT 客户端工具测试")
    print(f"  - 订阅: {expected_up_topic} 查看充电桩是否发送响应")
    print(f"  - 发布到: {expected_down_topic} 测试充电桩是否收到消息")
    print()
    
    print("=" * 80)
    print("诊断完成")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="MQTT 超时问题诊断工具")
    parser.add_argument(
        "--server",
        type=str,
        default="http://47.236.134.99:9000",
        help="CSMS 服务器地址"
    )
    parser.add_argument(
        "--charge-point-id",
        type=str,
        required=True,
        help="充电桩ID（序列号）"
    )
    
    args = parser.parse_args()
    diagnose_timeout(args.server, args.charge_point_id)


if __name__ == "__main__":
    main()

