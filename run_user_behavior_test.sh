#!/bin/bash
#
# 运行用户行为测试并监测所有日志
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

CHARGER_ID="CP-USER-$(date +%s | tail -c 6)"
SERIAL_NUMBER="$(date +%s | tail -c 15)"

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  用户行为模拟器测试（带日志监测）    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}测试参数:${NC}"
echo "  充电桩ID: ${GREEN}$CHARGER_ID${NC}"
echo "  序列号: ${GREEN}$SERIAL_NUMBER${NC}"
echo "  MQTT: ${GREEN}localhost:1883${NC}"
echo "  设备类型: ${GREEN}zcf${NC}"
echo ""

# 检查服务
echo -e "${BLUE}[1/5]${NC} 检查服务状态..."
if ! docker compose -f docker-compose.prod.yml ps mqtt-broker | grep -q "Up"; then
    echo -e "${RED}✗ MQTT Broker 未运行${NC}"
    exit 1
fi
if ! curl -s http://localhost:9000/health > /dev/null 2>&1; then
    echo -e "${RED}✗ CSMS 服务未运行${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 所有服务运行正常${NC}"
echo ""

# 清理旧日志
rm -f /tmp/test_*.log

# 启动日志监测
echo -e "${BLUE}[2/5]${NC} 启动日志监测..."

# CSMS日志（过滤相关消息）
docker compose -f docker-compose.prod.yml logs -f --tail=0 csms 2>&1 | \
    while IFS= read -r line; do
        if echo "$line" | grep -qE "($CHARGER_ID|$SERIAL_NUMBER|Authorize|StartTransaction|StopTransaction|MeterValues|BootNotification|StatusNotification|Heartbeat|MQTT|收到|发送)"; then
            echo -e "${MAGENTA}[CSMS]${NC} $line" | tee -a /tmp/test_csms.log
        fi
    done &
CSMS_LOG_PID=$!

# MQTT日志
docker compose -f docker-compose.prod.yml logs -f --tail=0 mqtt-broker 2>&1 | \
    while IFS= read -r line; do
        if echo "$line" | grep -qE "($CHARGER_ID|$SERIAL_NUMBER|zcf|user/up|user/down|PUBLISH|SUBSCRIBE)"; then
            echo -e "${CYAN}[MQTT]${NC} $line" | tee -a /tmp/test_mqtt.log
        fi
    done &
MQTT_LOG_PID=$!

sleep 2
echo -e "${GREEN}✓ 日志监测已启动${NC}"
echo ""

# 运行测试
echo -e "${BLUE}[3/5]${NC} 启动用户行为模拟器..."
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

cd /Users/xiaoqingran/eslatincsms

python3 -c "
import sys
import os
import asyncio
import time
from datetime import datetime

sys.path.insert(0, 'charger-sim')

from user_behavior_simulator import UserBehaviorSimulator, UserBehavior
import paho.mqtt.client as mqtt

async def run():
    charger_id = '$CHARGER_ID'
    serial_number = '$SERIAL_NUMBER'
    
    sim = UserBehaviorSimulator(
        charger_id=charger_id,
        broker_host='localhost',
        broker_port=1883,
        type_code='zcf',
        serial_number=serial_number,
        charging_power_kw=7.0
    )
    
    # 添加用户行为（2分钟测试）
    sim.add_user_behavior('TEST_USER_001', 'TEST_TAG_001', 2)
    
    # 设置MQTT
    sim.client = mqtt.Client(client_id=f'charger_{charger_id}', protocol=mqtt.MQTTv311)
    sim.client.on_connect = sim._on_connect
    sim.client.on_message = sim._on_message
    sim.client.on_disconnect = sim._on_disconnect
    sim.loop = asyncio.get_event_loop()
    
    # 连接
    print(f'{sim.prefix} 连接到 MQTT broker...')
    sim.client.connect('localhost', 1883, 60)
    sim.client.loop_start()
    await asyncio.sleep(2)
    
    # BootNotification
    sim._send_message('BootNotification', {
        'chargePointVendor': sim.vendor,
        'chargePointModel': sim.model,
        'firmwareVersion': sim.firmware_version,
        'chargePointSerialNumber': sim.serial_number
    })
    await asyncio.sleep(2)
    
    # StatusNotification
    sim.status = sim.ChargerStatus.AVAILABLE
    sim._send_message('StatusNotification', {
        'connectorId': 1,
        'errorCode': 'NoError',
        'status': sim.status.value
    })
    await asyncio.sleep(2)
    
    # 运行用户行为
    if sim.user_behaviors:
        behavior = sim.user_behaviors.pop(0)
        await sim.simulate_user_charging_flow(behavior)
    
    await asyncio.sleep(3)
    
    sim.client.loop_stop()
    sim.client.disconnect()
    print(f'{sim.prefix} 测试完成')

asyncio.run(run())
" 2>&1 | tee /tmp/test_simulator.log &
SIMULATOR_PID=$!

# 等待测试完成（2分钟充电 + 额外时间）
TOTAL_WAIT=150
echo -e "${YELLOW}等待测试完成（预计${TOTAL_WAIT}秒）...${NC}"
echo ""

# 显示实时日志
(
    tail -f /tmp/test_simulator.log 2>/dev/null | while IFS= read -r line; do
        echo -e "${GREEN}[SIM]${NC} $line"
    done
) &
TAIL_PID=$!

sleep $TOTAL_WAIT

# 停止所有进程
kill $SIMULATOR_PID $TAIL_PID 2>/dev/null || true
kill $CSMS_LOG_PID $MQTT_LOG_PID 2>/dev/null || true
wait $SIMULATOR_PID 2>/dev/null || true
sleep 2

echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 显示汇总
echo -e "${BLUE}[4/5]${NC} 测试结果汇总"
echo ""

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}模拟器输出（关键步骤）:${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ -f /tmp/test_simulator.log ]; then
    grep -E "(开始模拟|步骤|充电完成|充电统计|发送消息|收到)" /tmp/test_simulator.log | head -20
else
    echo "日志文件不存在"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}CSMS服务端日志:${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ -f /tmp/test_csms.log ]; then
    tail -30 /tmp/test_csms.log
else
    echo "CSMS日志文件不存在，尝试从实时日志获取..."
    docker compose -f docker-compose.prod.yml logs csms --tail 50 | grep -E "($CHARGER_ID|$SERIAL_NUMBER|Authorize|StartTransaction|StopTransaction|MeterValues)" | tail -20
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}MQTT Broker日志:${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ -f /tmp/test_mqtt.log ]; then
    tail -20 /tmp/test_mqtt.log
else
    echo "MQTT日志文件不存在，尝试从实时日志获取..."
    docker compose -f docker-compose.prod.yml logs mqtt-broker --tail 30 | grep -E "($CHARGER_ID|$SERIAL_NUMBER|zcf)" | tail -15
fi

echo ""
echo -e "${BLUE}[5/5]${NC} 消息统计"
echo ""

if [ -f /tmp/test_csms.log ]; then
    echo "  BootNotification: $(grep -c 'BootNotification' /tmp/test_csms.log 2>/dev/null || echo '0')"
    echo "  Authorize: $(grep -c 'Authorize' /tmp/test_csms.log 2>/dev/null || echo '0')"
    echo "  StartTransaction: $(grep -c 'StartTransaction' /tmp/test_csms.log 2>/dev/null || echo '0')"
    echo "  MeterValues: $(grep -c 'MeterValues' /tmp/test_csms.log 2>/dev/null || echo '0')"
    echo "  StopTransaction: $(grep -c 'StopTransaction' /tmp/test_csms.log 2>/dev/null || echo '0')"
    echo "  StatusNotification: $(grep -c 'StatusNotification' /tmp/test_csms.log 2>/dev/null || echo '0')"
    echo "  Heartbeat: $(grep -c 'Heartbeat' /tmp/test_csms.log 2>/dev/null || echo '0')"
fi

echo ""
echo -e "${BLUE}[6/6]${NC} 数据库数据验证"
echo ""

# 验证数据库中的数据
if docker compose -f docker-compose.prod.yml exec -T db psql -U ocpp_user -d ocpp -c "SELECT COUNT(*) FROM charge_points WHERE id = '$CHARGER_ID';" > /dev/null 2>&1; then
    charge_point_count=$(docker compose -f docker-compose.prod.yml exec -T db psql -U ocpp_user -d ocpp -c "SELECT COUNT(*) FROM charge_points WHERE id = '$CHARGER_ID';" 2>&1 | grep -E "^[[:space:]]*[0-9]+" | tr -d ' ')
    echo "  充电桩记录: $charge_point_count 条"
    
    # 查找交易ID（从日志中提取）
    transaction_id=$(grep -o "transaction_id=[0-9]*" /tmp/test_simulator.log 2>/dev/null | head -1 | cut -d= -f2)
    if [ -n "$transaction_id" ]; then
        session_count=$(docker compose -f docker-compose.prod.yml exec -T db psql -U ocpp_user -d ocpp -c "SELECT COUNT(*) FROM charging_sessions WHERE transaction_id = $transaction_id;" 2>&1 | grep -E "^[[:space:]]*[0-9]+" | tr -d ' ')
        echo "  充电会话: $session_count 条 (交易ID: $transaction_id)"
        
        if [ "$session_count" -gt 0 ]; then
            # 使用正确的列名 session_id
            meter_count=$(docker compose -f docker-compose.prod.yml exec -T db psql -U ocpp_user -d ocpp -c "SELECT COUNT(*) FROM meter_values WHERE session_id IN (SELECT id FROM charging_sessions WHERE transaction_id = $transaction_id);" 2>&1 | grep -E "^[[:space:]]*[0-9]+" | tr -d ' ')
            echo "  计量值记录: $meter_count 条"
            
            event_count=$(docker compose -f docker-compose.prod.yml exec -T db psql -U ocpp_user -d ocpp -c "SELECT COUNT(*) FROM device_events WHERE charge_point_id = '$CHARGER_ID';" 2>&1 | grep -E "^[[:space:]]*[0-9]+" | tr -d ' ')
            echo "  设备事件: $event_count 条"
        fi
    fi
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           测试完成                      ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo "日志文件位置:"
echo "  - 模拟器: /tmp/test_simulator.log"
echo "  - CSMS: /tmp/test_csms.log"
echo "  - MQTT: /tmp/test_mqtt.log"
echo ""
echo "实时查看日志:"
echo "  docker compose -f docker-compose.prod.yml logs -f csms | grep '$CHARGER_ID'"
echo ""

