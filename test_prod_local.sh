#!/bin/bash
#
# 本地生产环境测试脚本
# 用于在本地启动生产环境配置并进行测试
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
echo -e "${BLUE}本地生产环境测试${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查Docker是否运行
if ! docker ps > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker未运行，请先启动Docker${NC}"
    exit 1
fi

# 停止可能存在的旧容器
echo -e "${BLUE}1. 停止旧容器...${NC}"
docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
echo -e "${GREEN}✓ 完成${NC}"
echo ""

# 构建并启动服务
echo -e "${BLUE}2. 构建并启动服务...${NC}"
docker compose -f "$COMPOSE_FILE" up -d --build
echo -e "${GREEN}✓ 服务已启动${NC}"
echo ""

# 等待服务就绪
echo -e "${BLUE}3. 等待服务就绪...${NC}"
max_wait=60
wait_count=0
while [ $wait_count -lt $max_wait ]; do
    if docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U ocpp_user -d ocpp > /dev/null 2>&1; then
        if docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping > /dev/null 2>&1; then
            if curl -s http://localhost:9000/health > /dev/null 2>&1; then
                echo -e "${GREEN}✓ 所有服务已就绪${NC}"
                break
            fi
        fi
    fi
    wait_count=$((wait_count + 1))
    echo -n "."
    sleep 1
done
echo ""

if [ $wait_count -ge $max_wait ]; then
    echo -e "${RED}❌ 服务启动超时${NC}"
    echo "查看日志: docker compose -f $COMPOSE_FILE logs"
    exit 1
fi

# 显示服务状态
echo ""
echo -e "${BLUE}4. 服务状态:${NC}"
docker compose -f "$COMPOSE_FILE" ps
echo ""

# 初始化数据库（如果需要）
echo -e "${BLUE}5. 检查数据库初始化...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -c "
from app.database import init_db, check_db_health
if check_db_health():
    init_db()
    print('✓ 数据库已初始化')
else:
    print('⚠️  数据库连接失败')
" 2>/dev/null || echo -e "${YELLOW}⚠️  数据库初始化检查失败（可能已初始化）${NC}"
echo ""

# 运行清理脚本（预览模式）
echo -e "${BLUE}6. 检查无效的充电桩数据（预览模式）...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python scripts/cleanup_invalid_charge_points.py 2>/dev/null || echo -e "${YELLOW}⚠️  清理脚本执行失败或没有无效数据${NC}"
echo ""

# 显示服务信息
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}服务已启动，可以开始测试${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "服务地址:"
echo "  - CSMS API: http://localhost:9000"
echo "  - CSMS Health: http://localhost:9000/health"
echo "  - Admin界面: http://localhost:3000"
echo "  - MQTT Broker: localhost:1883"
echo ""
echo "常用命令:"
echo "  - 查看日志: docker compose -f $COMPOSE_FILE logs -f"
echo "  - 查看CSMS日志: docker compose -f $COMPOSE_FILE logs -f csms"
echo "  - 停止服务: docker compose -f $COMPOSE_FILE down"
echo "  - 清理无效数据: ./manage.sh cleanup-db"
echo "  - 执行清理: ./manage.sh cleanup-db-exec"
echo ""
echo -e "${YELLOW}提示: 使用 Ctrl+C 退出日志查看${NC}"
echo ""

# 询问是否查看日志
read -p "是否查看CSMS日志？(y/n): " view_logs
if [ "$view_logs" = "y" ] || [ "$view_logs" = "Y" ]; then
    echo ""
    echo -e "${BLUE}查看CSMS日志（按Ctrl+C退出）...${NC}"
    docker compose -f "$COMPOSE_FILE" logs -f csms
fi
