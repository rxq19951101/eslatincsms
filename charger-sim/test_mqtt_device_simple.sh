#!/bin/bash
#
# 快速测试MQTT设备连接脚本
# 使用已录入的设备信息进行测试
#

# 设备信息（从API获取）
SERIAL_NUMBER="861076087029615"
TYPE_CODE="zcf"
CLIENT_ID="zcf&861076087029615"
USERNAME="861076087029615"
PASSWORD="RrN26pSekjzv"  # 从API获取的密码

# MQTT配置
BROKER="localhost"
PORT=1883

echo "============================================================"
echo "MQTT设备模拟测试"
echo "============================================================"
echo ""
echo "设备信息:"
echo "  序列号: $SERIAL_NUMBER"
echo "  类型: $TYPE_CODE"
echo "  客户端ID: $CLIENT_ID"
echo "  用户名: $USERNAME"
echo ""
echo "MQTT配置:"
echo "  Broker: $BROKER:$PORT"
echo "  发送Topic: $TYPE_CODE/$SERIAL_NUMBER/user/up"
echo "  接收Topic: $TYPE_CODE/$SERIAL_NUMBER/user/down"
echo ""
echo "============================================================"
echo ""

# 运行模拟器
python3 charger-sim/test_mqtt_device.py \
    --broker "$BROKER" \
    --port "$PORT" \
    --client-id "$CLIENT_ID" \
    --username "$USERNAME" \
    --password "$PASSWORD" \
    --serial "$SERIAL_NUMBER" \
    --type-code "$TYPE_CODE"

