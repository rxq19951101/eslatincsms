#!/usr/bin/env python3
#
# 测试脚本：向远程服务器发送 BootNotification
# 用于测试 BootNotification 响应
#

import json
import time
import sys

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("错误: paho-mqtt 未安装，请运行: pip install paho-mqtt")
    sys.exit(1)


# 设备信息（从API获取）
SERIAL_NUMBER = "861076087029615"
TYPE_CODE = "zcf"
MQTT_CLIENT_ID = "zcf&861076087029615"
MQTT_USERNAME = "861076087029615"
MQTT_PASSWORD = "pHYtWMiW+UOa"

# 服务器信息
BROKER_HOST = "47.236.134.99"
BROKER_PORT = 1883

# MQTT 主题
UP_TOPIC = f"{TYPE_CODE}/{SERIAL_NUMBER}/user/up"
DOWN_TOPIC = f"{TYPE_CODE}/{SERIAL_NUMBER}/user/down"

# 响应接收标志
response_received = False
response_data = None


def on_connect(client, userdata, flags, rc):
    """MQTT 连接回调"""
    if rc == 0:
        print(f"✓ MQTT 连接成功")
        print(f"  Broker: {BROKER_HOST}:{BROKER_PORT}")
        print(f"  客户端ID: {MQTT_CLIENT_ID}")
        print(f"  用户名: {MQTT_USERNAME}")
        print()
        
        # 订阅响应主题
        client.subscribe(DOWN_TOPIC, qos=1)
        print(f"✓ 已订阅响应主题: {DOWN_TOPIC}")
        print()
        
        # 发送 BootNotification
        send_boot_notification(client)
    else:
        print(f"✗ MQTT 连接失败，返回码: {rc}")
        error_messages = {
            1: "协议版本不正确",
            2: "客户端标识符无效",
            3: "服务器不可用",
            4: "用户名或密码错误",
            5: "未授权"
        }
        print(f"  错误: {error_messages.get(rc, '未知错误')}")
        sys.exit(1)


def on_message(client, userdata, msg):
    """MQTT 消息接收回调"""
    global response_received, response_data
    
    try:
        topic = msg.topic
        payload = json.loads(msg.payload.decode())
        
        print(f"✓ 收到响应")
        print(f"  主题: {topic}")
        print(f"  内容: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        print()
        
        # 检查是否是 BootNotification 响应
        if payload.get("action") == "BootNotification":
            response_data = payload.get("response", {})
            status = response_data.get("status", "Unknown")
            
            if status == "Accepted":
                print("=" * 60)
                print("✓ BootNotification 成功！")
                print("=" * 60)
                print(f"  状态: {status}")
                print(f"  当前时间: {response_data.get('currentTime', 'N/A')}")
                print(f"  心跳间隔: {response_data.get('interval', 'N/A')} 秒")
                print("=" * 60)
            else:
                print("=" * 60)
                print("✗ BootNotification 被拒绝")
                print("=" * 60)
                print(f"  状态: {status}")
                if "error" in response_data:
                    print(f"  错误: {response_data['error']}")
                print("=" * 60)
            
            response_received = True
            client.disconnect()
        else:
            print(f"  收到其他消息: {payload.get('action', 'Unknown')}")
            
    except json.JSONDecodeError as e:
        print(f"✗ JSON 解析错误: {e}")
        print(f"  原始消息: {msg.payload}")
    except Exception as e:
        print(f"✗ 消息处理错误: {e}")


def on_subscribe(client, userdata, mid, granted_qos):
    """订阅确认回调"""
    print(f"✓ 订阅确认，QoS: {granted_qos}")
    print()


def on_disconnect(client, userdata, rc):
    """断开连接回调"""
    if rc == 0:
        print("✓ MQTT 连接已断开")
    else:
        print(f"✗ MQTT 意外断开，返回码: {rc}")


def send_boot_notification(client):
    """发送 BootNotification 消息"""
    message = {
        "action": "BootNotification",
        "payload": {
            "chargePointVendor": "ZCF",
            "chargePointModel": "ZCF-001",
            "chargePointSerialNumber": SERIAL_NUMBER,
            "firmwareVersion": "1.0.0"
        }
    }
    
    print("=" * 60)
    print("发送 BootNotification")
    print("=" * 60)
    print(f"  主题: {UP_TOPIC}")
    print(f"  消息: {json.dumps(message, indent=2, ensure_ascii=False)}")
    print("=" * 60)
    print()
    
    result = client.publish(
        UP_TOPIC,
        json.dumps(message),
        qos=1
    )
    
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print("✓ BootNotification 已发送，等待响应...")
        print()
    else:
        print(f"✗ 发送失败，返回码: {result.rc}")
        sys.exit(1)


def main():
    """主函数"""
    print("=" * 60)
    print("BootNotification 测试工具")
    print("=" * 60)
    print()
    print("设备信息:")
    print(f"  序列号: {SERIAL_NUMBER}")
    print(f"  设备类型: {TYPE_CODE}")
    print(f"  MQTT客户端ID: {MQTT_CLIENT_ID}")
    print(f"  MQTT用户名: {MQTT_USERNAME}")
    print()
    print("服务器信息:")
    print(f"  Broker: {BROKER_HOST}:{BROKER_PORT}")
    print()
    print("主题配置:")
    print(f"  发送主题: {UP_TOPIC}")
    print(f"  接收主题: {DOWN_TOPIC}")
    print()
    print("=" * 60)
    print()
    
    # 创建 MQTT 客户端
    client = mqtt.Client(client_id=MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    
    # 设置回调
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect
    
    # 连接到 MQTT Broker
    try:
        print("正在连接到 MQTT Broker...")
        client.connect(BROKER_HOST, BROKER_PORT, 60)
        
        # 启动循环（等待响应）
        client.loop_start()
        
        # 等待响应（最多30秒）
        timeout = 30
        start_time = time.time()
        while not response_received and (time.time() - start_time) < timeout:
            time.sleep(0.5)
        
        client.loop_stop()
        
        if not response_received:
            print("✗ 超时：未收到响应")
            print(f"  等待时间: {timeout} 秒")
            print()
            print("可能的原因:")
            print("  1. 服务器未正确处理消息")
            print("  2. 响应主题配置错误")
            print("  3. 网络连接问题")
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n用户中断")
        client.loop_stop()
        client.disconnect()
        sys.exit(0)
    except Exception as e:
        print(f"✗ 连接错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

