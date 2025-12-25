#!/bin/bash
#
# OCPP 自动化规范符合性测试便捷脚本
# 使用方法: ./run_auto_compliance_test.sh <充电桩ID> [服务器地址]
#

set -e

CHARGE_POINT_ID="${1}"
SERVER_URL="${2:-http://47.236.134.99:9000}"
SERVER_HOST="${3:-47.236.134.99}"
CONTAINER_NAME="${4:-ocpp-csms-prod}"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================="
echo "OCPP 自动化规范符合性测试"
echo "==========================================${NC}"
echo "服务器: $SERVER_URL"
echo "服务器主机: $SERVER_HOST"
echo "容器名称: $CONTAINER_NAME"
echo ""

if [ -z "$CHARGE_POINT_ID" ]; then
    echo -e "${YELLOW}未指定充电桩ID${NC}"
    echo ""
    echo "使用方法: $0 <充电桩ID> [服务器URL] [服务器主机] [容器名称]"
    echo ""
    echo "示例:"
    echo "  $0 861076087029615"
    echo "  $0 861076087029615 http://47.236.134.99:9000 47.236.134.99 ocpp-csms-prod"
    echo ""
    echo "查询已连接的充电桩:"
    echo "  python3 charger-sim/list_connected_chargers.py --server $SERVER_URL"
    exit 1
fi

echo "充电桩ID: $CHARGE_POINT_ID"
echo ""

# 检查 SSH 连接（如果使用 SSH）
echo -e "${BLUE}检查 SSH 连接...${NC}"
if ssh -o ConnectTimeout=5 -o BatchMode=yes "$SERVER_HOST" "docker ps" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ SSH 连接正常${NC}"
    USE_SSH="--use-ssh"
else
    echo -e "${YELLOW}⚠ SSH 连接失败，将尝试本地 Docker 访问${NC}"
    USE_SSH=""
fi

echo ""
echo -e "${BLUE}开始自动化测试...${NC}"
echo ""

# 运行测试脚本
python3 charger-sim/test_ocpp_compliance_auto.py \
    --server "$SERVER_URL" \
    --charge-point-id "$CHARGE_POINT_ID" \
    --monitor-logs \
    --server-host "$SERVER_HOST" \
    $USE_SSH \
    --ssh-user root \
    --container-name "$CONTAINER_NAME"

echo ""
echo -e "${GREEN}=========================================="
echo "测试完成"
echo "==========================================${NC}"
echo ""
echo "查看测试报告:"
echo "  ls -lt ocpp_compliance_report_${CHARGE_POINT_ID}_*.json | head -1"

