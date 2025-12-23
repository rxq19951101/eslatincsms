#!/usr/bin/env python3
#
# 简单的 MQTT 连接测试脚本
#

import paho.mqtt.client as mqtt
import time
import sys

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✓ MQTT 连接成功!")
        print(f"  返回码: {rc}")
        print(f"  连接标志: {flags}")
    else:
        print(f"✗ MQTT 连接失败!")
        print(f"  返回码: {rc}")
        error_messages = {
            1: "协议版本不正确",
            2: "客户端标识符无效",
            3: "服务器不可用",
            4: "用户名或密码错误",
            5: "未授权",
            6: "网络错误",
            7: "网络错误或连接超时"
        }
        print(f"  错误: {error_messages.get(rc, f'未知错误 ({rc})')}")
        sys.exit(1)

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"⚠ 意外断开，返回码: {rc}")
    else:
        print("✓ 正常断开")

def on_subscribe(client, userdata, mid, granted_qos):
    print(f"✓ 订阅成功，MID: {mid}, QoS: {granted_qos}")

def on_message(client, userdata, msg):
    print(f"← 收到消息:")
    print(f"  主题: {msg.topic}")
    print(f"  QoS: {msg.qos}")
    print(f"  内容: {msg.payload.decode()}")

# 配置
broker = "47.236.134.99"
port = 1883
client_id = "zcf&861076087029615"
username = "861076087029615"
password = "pHYtWMiW+UOa"
topic = "zcf/861076087029615/user/down"

print("=" * 60)
print("MQTT 连接测试")
print("=" * 60)
print(f"Broker: {broker}:{port}")
print(f"客户端 ID: {client_id}")
print(f"用户名: {username}")
print(f"主题: {topic}")
print("=" * 60)

client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
client.username_pw_set(username, password)
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_subscribe = on_subscribe
client.on_message = on_message

try:
    print("\n正在连接...")
    client.connect(broker, port, keepalive=60)
    client.loop_start()
    
    # 等待连接
    time.sleep(2)
    
    # 订阅主题
    print(f"\n正在订阅主题: {topic}")
    result, mid = client.subscribe(topic, qos=1)
    if result == mqtt.MQTT_ERR_SUCCESS:
        print(f"订阅请求已发送，MID: {mid}")
    else:
        print(f"订阅失败，返回码: {result}")
    
    # 保持连接并监听消息
    print("\n保持连接，监听消息...")
    print("按 Ctrl+C 退出\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在断开连接...")
        client.loop_stop()
        client.disconnect()
        print("已断开")
        
except Exception as e:
    print(f"✗ 错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

