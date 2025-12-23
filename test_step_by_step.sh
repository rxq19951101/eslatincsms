#!/bin/bash
#
# 分步测试脚本 - 可以分步执行，便于查看每步结果
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

COMPOSE_FILE="docker-compose.prod.yml"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}分步测试脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "请选择要执行的步骤："
echo "  1) 停止服务并清理数据"
echo "  2) 启动服务"
echo "  3) 运行用户流程测试"
echo "  4) 运行单测"
echo "  5) 运行所有测试"
echo "  6) 执行完整流程（1-5）"
echo ""
read -p "请输入选项 (1-6): " choice

case $choice in
    1)
        echo -e "${CYAN}步骤1: 停止服务并清理数据${NC}"
        docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
        echo -e "${GREEN}✓ 服务已停止${NC}"
        ;;
    2)
        echo -e "${CYAN}步骤2: 启动服务${NC}"
        docker compose -f "$COMPOSE_FILE" up -d --build
        echo -e "${BLUE}等待服务就绪...${NC}"
        sleep 10
        max_wait=60
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
        docker compose -f "$COMPOSE_FILE" exec -T csms python -c "
from app.database import init_db, check_db_health
if check_db_health():
    init_db()
    print('✓ 数据库已初始化')
" 2>/dev/null || echo -e "${YELLOW}⚠️  数据库初始化检查失败${NC}"
        ;;
    3)
        echo -e "${CYAN}步骤3: 运行用户流程测试${NC}"
        docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/test_user_flow.py tests/test_user_charging_flow.py tests/test_integration_user_behavior.py -v
        ;;
    4)
        echo -e "${CYAN}步骤4: 运行单测${NC}"
        docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/test_database_models.py tests/test_ocpp_message_handler.py tests/test_api_*.py tests/test_charge_point_service.py -v
        ;;
    5)
        echo -e "${CYAN}步骤5: 运行所有测试${NC}"
        docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/ -v
        ;;
    6)
        echo -e "${CYAN}执行完整流程${NC}"
        # 步骤1
        echo -e "${BLUE}1. 停止服务...${NC}"
        docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
        
        # 步骤2
        echo -e "${BLUE}2. 启动服务...${NC}"
        docker compose -f "$COMPOSE_FILE" up -d --build
        sleep 15
        
        # 等待服务就绪
        echo -e "${BLUE}等待服务就绪...${NC}"
        max_wait=60
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
        
        # 初始化数据库
        docker compose -f "$COMPOSE_FILE" exec -T csms python -c "
from app.database import init_db, check_db_health
if check_db_health():
    init_db()
    print('✓ 数据库已初始化')
" 2>/dev/null || echo -e "${YELLOW}⚠️  数据库初始化检查失败${NC}"
        
        # 步骤3-5
        echo -e "${BLUE}3. 运行所有测试...${NC}"
        docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/ -v --tb=short
        ;;
    *)
        echo -e "${RED}无效选项${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✓ 完成${NC}"

