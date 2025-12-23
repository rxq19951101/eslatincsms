#!/bin/bash
#
# MQTT BootNotification 排查脚本
# 用于检查 BootNotification 消息是否正常接收和响应
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

COMPOSE_FILE="docker-compose.prod.yml"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MQTT BootNotification 排查工具${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. 检查 MQTT Broker 是否运行
echo -e "${BLUE}1. 检查 MQTT Broker 状态...${NC}"
if docker compose -f "$COMPOSE_FILE" ps mqtt-broker | grep -q "Up"; then
    echo -e "${GREEN}✓ MQTT Broker 运行正常${NC}"
else
    echo -e "${RED}✗ MQTT Broker 未运行${NC}"
    exit 1
fi
echo ""

# 2. 检查 CSMS 是否运行
echo -e "${BLUE}2. 检查 CSMS 服务状态...${NC}"
if docker compose -f "$COMPOSE_FILE" ps csms | grep -q "Up"; then
    echo -e "${GREEN}✓ CSMS 服务运行正常${NC}"
else
    echo -e "${RED}✗ CSMS 服务未运行${NC}"
    exit 1
fi
echo ""

# 3. 检查 MQTT 连接状态
echo -e "${BLUE}3. 检查 CSMS MQTT 连接状态...${NC}"
MQTT_CONNECTION=$(docker compose -f "$COMPOSE_FILE" logs --tail=100 csms | grep -i "MQTT.*连接成功\|MQTT.*连接失败\|MQTT 传输已启用" | tail -5)
if echo "$MQTT_CONNECTION" | grep -q "连接成功\|已启用"; then
    echo -e "${GREEN}✓ MQTT 连接正常${NC}"
    echo "$MQTT_CONNECTION" | head -3
else
    echo -e "${YELLOW}⚠ 未找到 MQTT 连接日志，可能未启用 MQTT 传输${NC}"
fi
echo ""

# 4. 检查 MQTT 订阅状态
echo -e "${BLUE}4. 检查 MQTT 订阅状态...${NC}"
MQTT_SUBSCRIBE=$(docker compose -f "$COMPOSE_FILE" logs --tail=200 csms | grep -i "已订阅\|subscribe" | tail -5)
if [ -n "$MQTT_SUBSCRIBE" ]; then
    echo -e "${GREEN}✓ 找到订阅日志：${NC}"
    echo "$MQTT_SUBSCRIBE"
else
    echo -e "${YELLOW}⚠ 未找到订阅日志${NC}"
fi
echo ""

# 5. 检查最近的 BootNotification 消息
echo -e "${BLUE}5. 检查最近的 BootNotification 消息...${NC}"
BOOT_MSGS=$(docker compose -f "$COMPOSE_FILE" logs --tail=500 csms | grep -i "BootNotification" | tail -10)
if [ -n "$BOOT_MSGS" ]; then
    echo -e "${GREEN}✓ 找到 BootNotification 消息：${NC}"
    echo "$BOOT_MSGS"
else
    echo -e "${RED}✗ 未找到 BootNotification 消息${NC}"
    echo -e "${YELLOW}  这可能意味着：${NC}"
    echo -e "${YELLOW}  - 消息未到达 CSMS${NC}"
    echo -e "${YELLOW}  - MQTT 订阅未正确配置${NC}"
    echo -e "${YELLOW}  - 消息主题格式不正确${NC}"
fi
echo ""

# 6. 检查 BootNotification 响应
echo -e "${BLUE}6. 检查 BootNotification 响应...${NC}"
BOOT_RESPONSE=$(docker compose -f "$COMPOSE_FILE" logs --tail=500 csms | grep -i "BootNotification.*Response\|BootNotification.*响应" | tail -10)
if [ -n "$BOOT_RESPONSE" ]; then
    echo -e "${GREEN}✓ 找到 BootNotification 响应：${NC}"
    echo "$BOOT_RESPONSE"
else
    echo -e "${RED}✗ 未找到 BootNotification 响应${NC}"
    echo -e "${YELLOW}  这可能意味着：${NC}"
    echo -e "${YELLOW}  - 消息处理失败${NC}"
    echo -e "${YELLOW}  - 响应发送失败${NC}"
    echo -e "${YELLOW}  - 响应主题不正确${NC}"
fi
echo ""

# 7. 检查 MQTT Broker 收到的消息
echo -e "${BLUE}7. 检查 MQTT Broker 收到的消息...${NC}"
MQTT_RECEIVED=$(docker compose -f "$COMPOSE_FILE" logs --tail=500 mqtt-broker | grep -E "Received PUBLISH|user/up|user/down" | tail -20)
if [ -n "$MQTT_RECEIVED" ]; then
    echo -e "${GREEN}✓ 找到 MQTT 消息：${NC}"
    echo "$MQTT_RECEIVED" | head -10
else
    echo -e "${YELLOW}⚠ 未找到 MQTT 消息（可能是日志级别设置问题）${NC}"
fi
echo ""

# 8. 检查错误日志
echo -e "${BLUE}8. 检查错误日志...${NC}"
ERRORS=$(docker compose -f "$COMPOSE_FILE" logs --tail=500 csms | grep -i "error\|exception\|失败\|失败" | grep -i "mqtt\|boot\|ocpp" | tail -10)
if [ -n "$ERRORS" ]; then
    echo -e "${RED}✗ 找到错误：${NC}"
    echo "$ERRORS"
else
    echo -e "${GREEN}✓ 未找到相关错误${NC}"
fi
echo ""

# 9. 检查消息处理流程
echo -e "${BLUE}9. 检查消息处理流程（最近的消息）...${NC}"
RECENT_MSGS=$(docker compose -f "$COMPOSE_FILE" logs --tail=100 csms | grep -E "<- MQTT OCPP|MQTT 开始处理|MQTT 消息处理完成|-> MQTT OCPP" | tail -20)
if [ -n "$RECENT_MSGS" ]; then
    echo -e "${GREEN}✓ 最近的消息处理：${NC}"
    echo "$RECENT_MSGS"
else
    echo -e "${YELLOW}⚠ 未找到消息处理日志${NC}"
fi
echo ""

# 10. 提供排查建议
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}排查建议${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "如果 BootNotification 没有回复，请检查："
echo ""
echo "1. 消息主题格式是否正确："
echo "   - 设备发送主题: {type_code}/{serial_number}/user/up"
echo "   - 服务器响应主题: {type_code}/{serial_number}/user/down"
echo ""
echo "2. 消息格式是否正确："
echo "   {\"action\": \"BootNotification\", \"payload\": {...}}"
echo ""
echo "3. 设备是否订阅了响应主题："
echo "   {type_code}/{serial_number}/user/down"
echo ""
echo "4. 查看实时日志："
echo "   docker compose -f $COMPOSE_FILE logs -f csms | grep -i boot"
echo ""
echo "5. 测试 MQTT 连接："
echo "   docker compose -f $COMPOSE_FILE exec mqtt-broker mosquitto_pub -h localhost -t test -m test"
echo ""
echo "6. 检查 MQTT 适配器是否初始化："
echo "   docker compose -f $COMPOSE_FILE logs csms | grep -i 'MQTT.*初始化\|MQTT.*启用'"
echo ""

