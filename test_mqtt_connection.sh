#!/bin/bash
#
# MQTT 连接测试脚本
# 用于测试本地MQTT模拟器与CSMS的连接
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

CHARGER_ID="CP-TEST-$(date +%s)"
SERIAL_NUMBER="$(date +%s | tail -c 15)"
BROKER_HOST="localhost"
BROKER_PORT="1883"
TYPE_CODE="zcf"
POWER="7.0"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MQTT 连接测试${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "测试参数:"
echo "  充电桩ID: $CHARGER_ID"
echo "  序列号: $SERIAL_NUMBER"
echo "  MQTT Broker: $BROKER_HOST:$BROKER_PORT"
echo "  设备类型: $TYPE_CODE"
echo "  充电功率: $POWER kW"
echo ""

# 检查MQTT broker是否运行
echo -e "${BLUE}1. 检查MQTT Broker状态...${NC}"
if docker compose -f docker-compose.prod.yml ps mqtt-broker | grep -q "Up"; then
    echo -e "${GREEN}✓ MQTT Broker 运行正常${NC}"
else
    echo -e "${RED}✗ MQTT Broker 未运行${NC}"
    exit 1
fi

# 检查CSMS服务是否运行
echo -e "${BLUE}2. 检查CSMS服务状态...${NC}"
if curl -s http://localhost:9000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ CSMS 服务运行正常${NC}"
else
    echo -e "${RED}✗ CSMS 服务未运行${NC}"
    exit 1
fi

# 检查模拟器脚本是否存在
echo -e "${BLUE}3. 检查模拟器脚本...${NC}"
if [ -f "charger-sim/mqtt_simulator.py" ]; then
    echo -e "${GREEN}✓ 模拟器脚本存在${NC}"
else
    echo -e "${RED}✗ 模拟器脚本不存在${NC}"
    exit 1
fi

# 检查Python依赖
echo -e "${BLUE}4. 检查Python依赖...${NC}"
if python3 -c "import paho.mqtt.client" 2>/dev/null; then
    echo -e "${GREEN}✓ paho-mqtt 已安装${NC}"
else
    echo -e "${YELLOW}⚠ paho-mqtt 未安装，尝试安装...${NC}"
    pip3 install paho-mqtt 2>/dev/null || {
        echo -e "${RED}✗ 无法安装 paho-mqtt${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ paho-mqtt 安装成功${NC}"
fi

echo ""
echo -e "${BLUE}5. 启动MQTT模拟器（运行30秒）...${NC}"
echo -e "${YELLOW}提示: 按 Ctrl+C 可以提前停止${NC}"
echo ""

# 在后台启动模拟器并捕获输出
python3 charger-sim/mqtt_simulator.py \
    --id "$CHARGER_ID" \
    --broker "$BROKER_HOST" \
    --port "$BROKER_PORT" \
    --type-code "$TYPE_CODE" \
    --serial-number "$SERIAL_NUMBER" \
    --power "$POWER" \
    2>&1 | tee /tmp/mqtt_simulator_output.log &
SIMULATOR_PID=$!

# 等待30秒
sleep 30

# 停止模拟器
echo ""
echo -e "${BLUE}6. 停止模拟器...${NC}"
kill $SIMULATOR_PID 2>/dev/null || true
wait $SIMULATOR_PID 2>/dev/null || true
echo -e "${GREEN}✓ 模拟器已停止${NC}"

# 检查CSMS日志
echo ""
echo -e "${BLUE}7. 检查CSMS日志...${NC}"
CSMS_LOGS=$(docker compose -f docker-compose.prod.yml logs csms --tail 100 2>&1 | grep -E "($CHARGER_ID|$SERIAL_NUMBER|BootNotification|StatusNotification|Heartbeat)" | tail -20)
if [ -n "$CSMS_LOGS" ]; then
    echo "$CSMS_LOGS"
    echo -e "${GREEN}✓ 在CSMS日志中找到相关消息${NC}"
else
    echo -e "${YELLOW}⚠ 未在CSMS日志中找到相关消息${NC}"
fi

# 检查MQTT broker日志
echo ""
echo -e "${BLUE}8. 检查MQTT Broker日志...${NC}"
MQTT_LOGS=$(docker compose -f docker-compose.prod.yml logs mqtt-broker --tail 50 2>&1 | grep -E "($CHARGER_ID|$SERIAL_NUMBER|$TYPE_CODE)" | tail -10)
if [ -n "$MQTT_LOGS" ]; then
    echo "$MQTT_LOGS"
    echo -e "${GREEN}✓ 在MQTT Broker日志中找到相关消息${NC}"
else
    echo -e "${YELLOW}⚠ 未在MQTT Broker日志中找到相关消息${NC}"
fi

# 检查模拟器输出
echo ""
echo -e "${BLUE}9. 检查模拟器输出...${NC}"
if [ -f /tmp/mqtt_simulator_output.log ]; then
    if grep -q "MQTT 连接成功" /tmp/mqtt_simulator_output.log; then
        echo -e "${GREEN}✓ 模拟器成功连接到MQTT Broker${NC}"
    else
        echo -e "${RED}✗ 模拟器连接失败${NC}"
    fi
    
    if grep -q "收到服务器响应" /tmp/mqtt_simulator_output.log; then
        echo -e "${GREEN}✓ 模拟器收到服务器响应${NC}"
    else
        echo -e "${YELLOW}⚠ 模拟器未收到服务器响应${NC}"
    fi
    
    echo ""
    echo "模拟器输出摘要:"
    grep -E "(MQTT 连接|订阅主题|发送消息|收到服务器)" /tmp/mqtt_simulator_output.log | head -10
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}测试完成${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "服务地址:"
echo "  - MQTT Broker: $BROKER_HOST:$BROKER_PORT"
echo "  - CSMS API: http://localhost:9000"
echo "  - Admin界面: http://localhost:3000"
echo ""
echo "查看完整日志:"
echo "  - 模拟器输出: cat /tmp/mqtt_simulator_output.log"
echo "  - CSMS日志: docker compose -f docker-compose.prod.yml logs -f csms"
echo "  - MQTT日志: docker compose -f docker-compose.prod.yml logs -f mqtt-broker"
echo ""

