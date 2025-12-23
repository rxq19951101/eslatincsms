#!/usr/bin/env python3
#
# 测试脚本：使用 OCPP 1.6 标准格式发送 BootNotification
# 格式: [MessageType, UniqueId, Action, Payload]
#

import json
import time
import sys
import uuid

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("错误: paho-mqtt 未安装，请运行: pip install paho-mqtt")
    sys.exit(1)


# 设备信息
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
        print()
        
        # 订阅响应主题
        client.subscribe(DOWN_TOPIC, qos=1)
        print(f"✓ 已订阅响应主题: {DOWN_TOPIC}")
        print()
        
        # 发送 BootNotification（OCPP 标准格式）
        send_boot_notification_ocpp_format(client)
    else:
        print(f"✗ MQTT 连接失败，返回码: {rc}")
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
        
        # 检查响应格式
        if isinstance(payload, list) and len(payload) >= 3:
            # OCPP 标准格式: [MessageType, UniqueId, Payload]
            message_type = payload[0]
            unique_id = payload[1]
            response_payload = payload[2]
            
            if message_type == 3:  # CALLRESULT
                print("=" * 60)
                print("✓ BootNotification 成功！(OCPP 标准格式)")
                print("=" * 60)
                print(f"  消息类型: CALLRESULT (3)")
                print(f"  唯一ID: {unique_id}")
                status = response_payload.get("status", "Unknown")
                print(f"  状态: {status}")
                if status == "Accepted":
                    print(f"  当前时间: {response_payload.get('currentTime', 'N/A')}")
                    print(f"  心跳间隔: {response_payload.get('interval', 'N/A')} 秒")
                print("=" * 60)
                response_received = True
            elif message_type == 4:  # CALLERROR
                print("=" * 60)
                print("✗ BootNotification 错误 (OCPP 标准格式)")
                print("=" * 60)
                print(f"  消息类型: CALLERROR (4)")
                print(f"  唯一ID: {unique_id}")
                print(f"  错误代码: {response_payload.get('errorCode', 'N/A')}")
                print(f"  错误描述: {response_payload.get('errorDescription', 'N/A')}")
                print("=" * 60)
                response_received = True
        elif isinstance(payload, dict):
            # 简化格式: {"action": "...", "response": {...}}
            if payload.get("action") == "BootNotification":
                response_payload = payload.get("response", {})
                status = response_payload.get("status", "Unknown")
                
                print("=" * 60)
                if status == "Accepted":
                    print("✓ BootNotification 成功！(简化格式)")
                else:
                    print("✗ BootNotification 被拒绝 (简化格式)")
                print("=" * 60)
                print(f"  状态: {status}")
                if "error" in response_payload:
                    print(f"  错误: {response_payload['error']}")
                print("=" * 60)
                response_received = True
        else:
            print(f"  未知响应格式: {type(payload)}")
            
        client.disconnect()
            
    except json.JSONDecodeError as e:
        print(f"✗ JSON 解析错误: {e}")
        print(f"  原始消息: {msg.payload}")
    except Exception as e:
        print(f"✗ 消息处理错误: {e}")


def on_subscribe(client, userdata, mid, granted_qos):
    """订阅确认回调"""
    print(f"✓ 订阅确认，QoS: {granted_qos}")
    print()


def send_boot_notification_ocpp_format(client):
    """发送 BootNotification 消息（OCPP 1.6 标准格式）"""
    # OCPP 1.6 标准格式: [MessageType, UniqueId, Action, Payload]
    # MessageType: 2 = CALL (充电桩发送给服务器的请求)
    unique_id = f"{SERIAL_NUMBER}-{int(time.time())}"
    
    message = [
        2,  # MessageType: CALL
        unique_id,  # UniqueId
        "BootNotification",  # Action
        {  # Payload
            "chargePointVendor": "ZCF",
            "chargePointModel": "F1Pro AC 7kW 1",
            "chargePointSerialNumber": SERIAL_NUMBER,
            "firmwareVersion": "A1-04-GB-01-R110-V100.01",
            "iccid": "89860323432024128072"
        }
    ]
    
    print("=" * 60)
    print("发送 BootNotification (OCPP 1.6 标准格式)")
    print("=" * 60)
    print(f"  主题: {UP_TOPIC}")
    print(f"  消息格式: [MessageType, UniqueId, Action, Payload]")
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
    print("BootNotification 测试工具 (OCPP 1.6 标准格式)")
    print("=" * 60)
    print()
    print("设备信息:")
    print(f"  序列号: {SERIAL_NUMBER}")
    print(f"  设备类型: {TYPE_CODE}")
    print()
    print("服务器信息:")
    print(f"  Broker: {BROKER_HOST}:{BROKER_PORT}")
    print()
    print("消息格式:")
    print("  [2, UniqueId, \"BootNotification\", Payload]")
    print("  其中: 2 = CALL (充电桩发送给服务器的请求)")
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

