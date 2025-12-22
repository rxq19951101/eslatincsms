#!/bin/bash
#
# 本地模拟充电桩连接远程服务器脚本
# 使用方法: ./connect_remote_server.sh [参数]
#

set -e

# 默认配置
DEFAULT_CHARGER_ID="CP-LOCAL-001"
DEFAULT_BROKER="47.236.134.99"
DEFAULT_PORT="1883"
DEFAULT_TYPE_CODE="zcf"
DEFAULT_SERIAL_NUMBER=""

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}本地模拟充电桩连接远程服务器${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 解析参数
CHARGER_ID="${1:-$DEFAULT_CHARGER_ID}"
BROKER="${2:-$DEFAULT_BROKER}"
PORT="${3:-$DEFAULT_PORT}"
TYPE_CODE="${4:-$DEFAULT_TYPE_CODE}"
SERIAL_NUMBER="${5:-$DEFAULT_SERIAL_NUMBER}"

echo -e "${GREEN}配置信息:${NC}"
echo "  充电桩ID: $CHARGER_ID"
echo "  MQTT Broker: $BROKER:$PORT"
echo "  设备类型: $TYPE_CODE"
if [ -n "$SERIAL_NUMBER" ]; then
    echo "  序列号: $SERIAL_NUMBER"
else
    echo "  序列号: 自动生成"
fi
echo ""

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}错误: 未找到 python3${NC}"
    exit 1
fi

# 检查依赖
if ! python3 -c "import paho.mqtt.client" 2>/dev/null; then
    echo -e "${YELLOW}安装依赖: paho-mqtt${NC}"
    pip3 install paho-mqtt qrcode
fi

# 构建命令
CMD="python3 mqtt_simulator.py --id $CHARGER_ID --broker $BROKER --port $PORT --type-code $TYPE_CODE"

if [ -n "$SERIAL_NUMBER" ]; then
    CMD="$CMD --serial-number $SERIAL_NUMBER"
fi

echo -e "${GREEN}启动模拟器...${NC}"
echo "命令: $CMD"
echo ""

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 运行模拟器
exec $CMD

