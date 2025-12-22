#!/bin/bash
#
# 本地模拟充电桩连接远程服务器脚本
# 使用方法: ./connect_remote.sh [充电桩ID] [服务器IP] [设备类型] [序列号]
#

set -e

# 默认参数
CHARGER_ID=${1:-"CP-LOCAL-001"}
SERVER_IP=${2:-"47.236.134.99"}
TYPE_CODE=${3:-"zcf"}
SERIAL_NUMBER=${4:-""}

# MQTT broker 端口
MQTT_PORT=1883

echo "=========================================="
echo "本地模拟充电桩连接远程服务器"
echo "=========================================="
echo ""
echo "配置信息:"
echo "  - 充电桩ID: $CHARGER_ID"
echo "  - 服务器地址: $SERVER_IP"
echo "  - MQTT端口: $MQTT_PORT"
echo "  - 设备类型: $TYPE_CODE"
if [ -n "$SERIAL_NUMBER" ]; then
    echo "  - 设备序列号: $SERIAL_NUMBER"
else
    echo "  - 设备序列号: (自动生成)"
fi
echo ""
echo "MQTT Topic:"
echo "  - 发送: $TYPE_CODE/<serial>/user/up"
echo "  - 接收: $TYPE_CODE/<serial>/user/down"
echo ""
echo "=========================================="
echo ""

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3"
    exit 1
fi

# 检查依赖
if ! python3 -c "import paho.mqtt.client" 2>/dev/null; then
    echo "正在安装依赖..."
    pip3 install paho-mqtt qrcode[pil] --quiet
fi

# 构建命令
CMD="python3 mqtt_simulator.py --id $CHARGER_ID --broker $SERVER_IP --port $MQTT_PORT --type-code $TYPE_CODE"

if [ -n "$SERIAL_NUMBER" ]; then
    CMD="$CMD --serial-number $SERIAL_NUMBER"
fi

echo "启动模拟器..."
echo "命令: $CMD"
echo ""
echo "按 Ctrl+C 停止"
echo ""

# 执行命令
exec $CMD

