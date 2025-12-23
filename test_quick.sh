#!/bin/bash
#
# 快速测试脚本（不删除数据，只重启服务并运行测试）
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

COMPOSE_FILE="docker-compose.prod.yml"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}快速测试（不删除数据）${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 重启服务
echo -e "${BLUE}1. 重启服务...${NC}"
docker compose -f "$COMPOSE_FILE" restart csms
sleep 5
echo -e "${GREEN}✓ 服务已重启${NC}"
echo ""

# 等待服务就绪
echo -e "${BLUE}2. 等待服务就绪...${NC}"
max_wait=30
wait_count=0
while [ $wait_count -lt $max_wait ]; do
    if curl -s http://localhost:9000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 服务已就绪${NC}"
        break
    fi
    wait_count=$((wait_count + 1))
    echo -n "."
    sleep 1
done
echo ""

# 运行测试
echo -e "${BLUE}3. 运行测试...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/ -v --tb=short
echo ""

echo -e "${GREEN}✓ 测试完成${NC}"

