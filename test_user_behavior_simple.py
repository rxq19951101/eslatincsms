#!/usr/bin/env python3
#
# 简化的用户行为测试脚本
# 用于快速测试用户充电流程
#

import sys
import os
import asyncio
import time
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'charger-sim'))

from user_behavior_simulator import UserBehaviorSimulator, UserBehavior

async def run_test():
    charger_id = f"CP-TEST-{int(time.time())}"
    serial_number = str(int(time.time()))[-15:].zfill(15)
    
    print("=" * 60)
    print("用户行为模拟器测试")
    print("=" * 60)
    print(f"充电桩ID: {charger_id}")
    print(f"序列号: {serial_number}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()
    
    simulator = UserBehaviorSimulator(
        charger_id=charger_id,
        broker_host="localhost",
        broker_port=1883,
        type_code="zcf",
        serial_number=serial_number,
        charging_power_kw=7.0
    )
    
    # 添加测试用户（2分钟）
    simulator.add_user_behavior("TEST_USER_001", "TEST_TAG_001", 2)
    
    # 设置MQTT客户端
    import paho.mqtt.client as mqtt
    simulator.client = mqtt.Client(client_id=f"charger_{charger_id}", protocol=mqtt.MQTTv311)
    simulator.client.on_connect = simulator._on_connect
    simulator.client.on_message = simulator._on_message
    simulator.client.on_disconnect = simulator._on_disconnect
    
    simulator.loop = asyncio.get_event_loop()
    
    # 连接到MQTT
    print(f"{simulator.prefix} 正在连接到 MQTT broker: localhost:1883")
    try:
        simulator.client.connect("localhost", 1883, 60)
        simulator.client.loop_start()
        await asyncio.sleep(2)
        print(f"{simulator.prefix} ✓ MQTT 连接成功")
    except Exception as e:
        print(f"{simulator.prefix} ✗ 连接失败: {e}")
        return
    
    # 发送BootNotification
    print(f"{simulator.prefix} 发送 BootNotification...")
    simulator._send_message("BootNotification", {
        "chargePointVendor": simulator.vendor,
        "chargePointModel": simulator.model,
        "firmwareVersion": simulator.firmware_version,
        "chargePointSerialNumber": simulator.serial_number
    })
    await asyncio.sleep(2)
    
    # 发送StatusNotification
    print(f"{simulator.prefix} 发送 StatusNotification (Available)...")
    simulator.status = simulator.ChargerStatus.AVAILABLE
    simulator._send_message("StatusNotification", {
        "connectorId": 1,
        "errorCode": "NoError",
        "status": simulator.status.value
    })
    await asyncio.sleep(2)
    
    # 运行用户行为
    if simulator.user_behaviors:
        behavior = simulator.user_behaviors.pop(0)
        await simulator.simulate_user_charging_flow(behavior)
    
    # 等待日志完成
    await asyncio.sleep(3)
    
    # 停止
    print(f"{simulator.prefix} 正在停止...")
    simulator.client.loop_stop()
    simulator.client.disconnect()
    
    print()
    print("=" * 60)
    print("测试完成")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        print("\n测试已中断")

