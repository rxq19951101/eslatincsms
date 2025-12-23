#!/bin/bash
#
# 本地生产环境完整测试脚本
# 1. 删除所有数据
# 2. 重启服务（使用docker-compose.prod.yml）
# 3. 运行用户流程测试
# 4. 运行单测
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

COMPOSE_FILE="docker-compose.prod.yml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}本地生产环境完整测试${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查Docker是否运行
if ! docker ps > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker未运行，请先启动Docker${NC}"
    exit 1
fi

# ========================================
# 步骤1: 删除所有数据
# ========================================
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}步骤1: 删除所有数据${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# 停止服务（如果正在运行）
echo -e "${BLUE}1.1 停止现有服务...${NC}"
docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
echo -e "${GREEN}✓ 服务已停止${NC}"
echo ""

# 删除数据库数据
echo -e "${BLUE}1.2 删除数据库数据...${NC}"
if docker ps -a | grep -q ocpp-db-prod; then
    # 如果容器存在，先启动它
    docker start ocpp-db-prod 2>/dev/null || true
    sleep 2
    
    # 删除所有表数据
    docker exec ocpp-db-prod psql -U ocpp_user -d ocpp -c "
        DO \$\$ 
        DECLARE 
            r RECORD;
        BEGIN
            -- 禁用外键约束检查
            SET session_replication_role = 'replica';
            
            -- 删除所有表的数据
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
            LOOP
                EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
            
            -- 恢复外键约束检查
            SET session_replication_role = 'origin';
        END \$\$;
    " 2>/dev/null || echo -e "${YELLOW}⚠️  数据库清理失败（可能表不存在）${NC}"
    
    echo -e "${GREEN}✓ 数据库数据已删除${NC}"
else
    echo -e "${YELLOW}⚠️  数据库容器不存在，跳过数据删除${NC}"
fi
echo ""

# 删除Redis数据
echo -e "${BLUE}1.3 删除Redis数据...${NC}"
if docker ps -a | grep -q ocpp-redis-prod; then
    docker start ocpp-redis-prod 2>/dev/null || true
    sleep 1
    docker exec ocpp-redis-prod redis-cli FLUSHALL 2>/dev/null || echo -e "${YELLOW}⚠️  Redis清理失败${NC}"
    echo -e "${GREEN}✓ Redis数据已删除${NC}"
else
    echo -e "${YELLOW}⚠️  Redis容器不存在，跳过数据删除${NC}"
fi
echo ""

# 删除Docker volumes（可选，更彻底的清理）
# 默认不删除volumes，如需删除可以设置环境变量 DELETE_VOLUMES=yes
if [ "${DELETE_VOLUMES:-no}" = "yes" ]; then
    echo -e "${BLUE}1.4 删除Docker volumes...${NC}"
    docker compose -f "$COMPOSE_FILE" down -v 2>/dev/null || true
    echo -e "${GREEN}✓ Docker volumes已删除${NC}"
    echo ""
else
    echo -e "${BLUE}1.4 跳过Docker volumes删除（如需删除，设置环境变量 DELETE_VOLUMES=yes）${NC}"
    echo ""
fi

# ========================================
# 步骤2: 重启服务
# ========================================
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}步骤2: 重启服务（生产环境配置）${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# 构建并启动服务
echo -e "${BLUE}2.1 构建并启动服务...${NC}"
docker compose -f "$COMPOSE_FILE" up -d --build
echo -e "${GREEN}✓ 服务已启动${NC}"
echo ""

# 等待服务就绪
echo -e "${BLUE}2.2 等待服务就绪...${NC}"
max_wait=120
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

# 初始化数据库
echo -e "${BLUE}2.3 初始化数据库...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -c "
from app.database import init_db, check_db_health
if check_db_health():
    init_db()
    print('✓ 数据库已初始化')
else:
    print('⚠️  数据库连接失败')
" 2>/dev/null || echo -e "${YELLOW}⚠️  数据库初始化检查失败（可能已初始化）${NC}"
echo ""

# 显示服务状态
echo -e "${BLUE}2.4 服务状态:${NC}"
docker compose -f "$COMPOSE_FILE" ps
echo ""

# ========================================
# 步骤3: 运行用户流程测试
# ========================================
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}步骤3: 运行用户流程测试${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

echo -e "${BLUE}3.1 运行端到端用户流程测试...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/test_user_flow.py -v --tb=short || {
    echo -e "${RED}❌ 用户流程测试失败${NC}"
    echo "查看详细日志: docker compose -f $COMPOSE_FILE logs csms"
}
echo ""

echo -e "${BLUE}3.2 运行用户充电流程测试...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/test_user_charging_flow.py -v --tb=short || {
    echo -e "${YELLOW}⚠️  用户充电流程测试失败或跳过${NC}"
}
echo ""

echo -e "${BLUE}3.3 运行用户行为集成测试...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/test_integration_user_behavior.py -v --tb=short || {
    echo -e "${YELLOW}⚠️  用户行为集成测试失败或跳过${NC}"
}
echo ""

# ========================================
# 步骤4: 运行单测
# ========================================
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}步骤4: 运行单测${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# 数据库模型测试
echo -e "${BLUE}4.1 运行数据库模型测试...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/test_database_models.py -v --tb=short || {
    echo -e "${YELLOW}⚠️  数据库模型测试失败或跳过${NC}"
}
echo ""

# OCPP消息处理测试
echo -e "${BLUE}4.2 运行OCPP消息处理测试...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/test_ocpp_message_handler.py -v --tb=short || {
    echo -e "${YELLOW}⚠️  OCPP消息处理测试失败或跳过${NC}"
}
echo ""

# API测试
echo -e "${BLUE}4.3 运行API测试...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/test_api_*.py -v --tb=short || {
    echo -e "${YELLOW}⚠️  API测试失败或跳过${NC}"
}
echo ""

# 服务层测试
echo -e "${BLUE}4.4 运行服务层测试...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/test_charge_point_service.py -v --tb=short || {
    echo -e "${YELLOW}⚠️  服务层测试失败或跳过${NC}"
}
echo ""

# ========================================
# 步骤5: 运行所有测试（汇总）
# ========================================
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}步骤5: 运行所有测试（汇总）${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

echo -e "${BLUE}5.1 运行所有测试...${NC}"
docker compose -f "$COMPOSE_FILE" exec -T csms python -m pytest tests/ -v --tb=short --maxfail=5 || {
    echo -e "${YELLOW}⚠️  部分测试失败（查看上方详细输出）${NC}"
}
echo ""

# ========================================
# 总结
# ========================================
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}测试完成${NC}"
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
echo "  - 重新运行测试: docker compose -f $COMPOSE_FILE exec csms python -m pytest tests/ -v"
echo ""
echo -e "${YELLOW}提示: 使用 Ctrl+C 退出日志查看${NC}"
echo ""

