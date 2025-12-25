#!/bin/bash
#
# 本地 OCPP 规范符合性测试完整流程
# 1. 启动本地服务器（如果未运行）
# 2. 启动符合规范的模拟充电桩
# 3. 运行自动化测试
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

CHARGER_ID="${1:-TEST-COMP-001}"
SERVER_URL="${2:-http://localhost:9000}"

echo -e "${BLUE}=========================================="
echo "本地 OCPP 规范符合性测试"
echo "==========================================${NC}"
echo "充电桩ID: $CHARGER_ID"
echo "服务器: $SERVER_URL"
echo ""

# 检查服务器是否运行
echo -e "${BLUE}1. 检查服务器状态...${NC}"
if curl -s "$SERVER_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 服务器已运行${NC}"
else
    echo -e "${YELLOW}⚠ 服务器未运行，请先启动服务器：${NC}"
    echo "  cd csms && docker-compose up -d"
    echo ""
    read -p "是否继续？(y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 启动模拟充电桩（后台）
echo ""
echo -e "${BLUE}2. 启动符合规范的模拟充电桩...${NC}"
python3 charger-sim/compliant_charger_simulator.py \
    --charger-id "$CHARGER_ID" \
    --server "$SERVER_URL" \
    > /tmp/charger_simulator.log 2>&1 &
SIMULATOR_PID=$!

echo -e "${GREEN}✓ 模拟充电桩已启动（PID: $SIMULATOR_PID）${NC}"
echo "等待充电桩连接并发送 BootNotification..."
sleep 5

# 检查模拟器是否还在运行
if ! kill -0 $SIMULATOR_PID 2>/dev/null; then
    echo -e "${RED}✗ 模拟充电桩启动失败${NC}"
    echo "日志:"
    cat /tmp/charger_simulator.log
    exit 1
fi

# 等待充电桩连接
echo "等待充电桩连接..."
for i in {1..10}; do
    if curl -s "$SERVER_URL/api/v1/chargers/$CHARGER_ID" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 充电桩已连接${NC}"
        break
    fi
    if [ $i -eq 10 ]; then
        echo -e "${RED}✗ 充电桩连接超时${NC}"
        kill $SIMULATOR_PID 2>/dev/null || true
        exit 1
    fi
    sleep 2
done

# 运行测试
echo ""
echo -e "${BLUE}3. 运行 OCPP 规范符合性测试...${NC}"
echo ""

# 注意：本地测试不需要 SSH，直接使用 Docker logs
python3 charger-sim/test_ocpp_compliance_auto.py \
    --server "$SERVER_URL" \
    --charge-point-id "$CHARGER_ID" \
    --monitor-logs \
    --container-name csms \
    --server-host localhost

TEST_EXIT_CODE=$?

# 停止模拟充电桩
echo ""
echo -e "${BLUE}4. 停止模拟充电桩...${NC}"
kill $SIMULATOR_PID 2>/dev/null || true
wait $SIMULATOR_PID 2>/dev/null || true
echo -e "${GREEN}✓ 模拟充电桩已停止${NC}"

# 显示测试结果
echo ""
echo -e "${BLUE}=========================================="
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}测试完成（成功）${NC}"
else
    echo -e "${RED}测试完成（有失败项）${NC}"
fi
echo -e "${BLUE}==========================================${NC}"

exit $TEST_EXIT_CODE

