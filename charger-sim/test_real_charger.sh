#!/bin/bash
#
# 测试真实充电桩的 OCPP 功能
# 使用方法: ./test_real_charger.sh [充电桩ID] [服务器URL]
#

set -e

CHARGE_POINT_ID="${1}"
SERVER_URL="${2:-http://47.236.134.99:9000}"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "真实充电桩 OCPP 功能测试"
echo "=========================================="
echo "服务器: $SERVER_URL"
echo ""

# 如果没有提供充电桩ID，先列出已连接的充电桩
if [ -z "$CHARGE_POINT_ID" ]; then
    echo -e "${YELLOW}未指定充电桩ID，正在查询已连接的充电桩...${NC}"
    echo ""
    
    python3 charger-sim/list_connected_chargers.py --server "$SERVER_URL"
    
    echo ""
    echo -e "${YELLOW}请提供充电桩ID作为第一个参数：${NC}"
    echo "用法: $0 <充电桩ID> [服务器URL]"
    echo "示例: $0 CP001 http://47.236.134.99:9000"
    exit 1
fi

echo "充电桩ID: $CHARGE_POINT_ID"
echo ""

# 检查充电桩是否连接
echo "1. 检查充电桩连接状态..."
python3 -c "
import requests
import sys
try:
    response = requests.get('$SERVER_URL/api/v1/chargers/$CHARGE_POINT_ID', timeout=10)
    if response.status_code == 200:
        charger = response.json()
        print(f\"✓ 充电桩已连接\")
        print(f\"  厂商: {charger.get('vendor', 'N/A')}\")
        print(f\"  型号: {charger.get('model', 'N/A')}\")
        print(f\"  状态: {charger.get('status', 'N/A')}\")
        print(f\"  最后心跳: {charger.get('last_seen', 'N/A')}\")
    else:
        print(f\"✗ 充电桩未找到或未连接 (HTTP {response.status_code})\")
        sys.exit(1)
except Exception as e:
    print(f\"✗ 检查连接失败: {e}\")
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo -e "${RED}充电桩未连接，无法继续测试${NC}"
    exit 1
fi

echo ""
echo "2. 运行 OCPP 协议验证..."
echo ""

# 运行验证脚本（交互式模式）
python3 charger-sim/verify_ocpp_protocol.py \
    --server "$SERVER_URL" \
    --charge-point-id "$CHARGE_POINT_ID"

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="

