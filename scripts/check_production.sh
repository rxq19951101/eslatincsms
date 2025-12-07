#!/bin/bash
#
# 生产环境检查脚本
# 检查服务器环境和配置
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}OCPP CSMS 生产环境检查${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查项计数
CHECKS_PASSED=0
CHECKS_FAILED=0

# 检查函数
check_command() {
    if command -v "$1" &> /dev/null; then
        VERSION=$($1 --version 2>&1 | head -n 1)
        echo -e "${GREEN}✓${NC} $1: $VERSION"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} $1: 未安装"
        ((CHECKS_FAILED++))
        return 1
    fi
}

check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1: 存在"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${RED}✗${NC} $1: 不存在"
        ((CHECKS_FAILED++))
        return 1
    fi
}

check_port() {
    if netstat -tuln 2>/dev/null | grep -q ":$1 " || ss -tuln 2>/dev/null | grep -q ":$1 "; then
        echo -e "${YELLOW}⚠${NC} 端口 $1: 已被占用"
        ((CHECKS_FAILED++))
        return 1
    else
        echo -e "${GREEN}✓${NC} 端口 $1: 可用"
        ((CHECKS_PASSED++))
        return 0
    fi
}

check_service() {
    if docker ps --format '{{.Names}}' | grep -q "^$1$"; then
        STATUS=$(docker inspect --format='{{.State.Status}}' "$1" 2>/dev/null || echo "unknown")
        if [ "$STATUS" = "running" ]; then
            echo -e "${GREEN}✓${NC} 服务 $1: 运行中"
            ((CHECKS_PASSED++))
            return 0
        else
            echo -e "${YELLOW}⚠${NC} 服务 $1: $STATUS"
            ((CHECKS_FAILED++))
            return 1
        fi
    else
        echo -e "${YELLOW}⚠${NC} 服务 $1: 未运行"
        ((CHECKS_FAILED++))
        return 1
    fi
}

# 1. 检查系统命令
echo -e "${BLUE}[1] 检查系统命令${NC}"
check_command "docker"
check_command "docker-compose"
check_command "curl"
check_command "wget"
echo ""

# 2. 检查 Docker 服务
echo -e "${BLUE}[2] 检查 Docker 服务${NC}"
if systemctl is-active --quiet docker 2>/dev/null || service docker status >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Docker 服务: 运行中"
    ((CHECKS_PASSED++))
else
    echo -e "${RED}✗${NC} Docker 服务: 未运行"
    ((CHECKS_FAILED++))
fi
echo ""

# 3. 检查配置文件
echo -e "${BLUE}[3] 检查配置文件${NC}"
check_file "$PROJECT_DIR/.env.production"
check_file "$PROJECT_DIR/docker-compose.prod.yml"
check_file "$PROJECT_DIR/mosquitto.conf"
echo ""

# 4. 检查环境变量
echo -e "${BLUE}[4] 检查环境变量${NC}"
if [ -f "$PROJECT_DIR/.env.production" ]; then
    source "$PROJECT_DIR/.env.production" 2>/dev/null || true
    
    if [ -z "$DB_PASSWORD" ] || [ "$DB_PASSWORD" = "CHANGE_THIS_SECURE_PASSWORD" ]; then
        echo -e "${RED}✗${NC} DB_PASSWORD: 未设置或使用默认值"
        ((CHECKS_FAILED++))
    else
        echo -e "${GREEN}✓${NC} DB_PASSWORD: 已设置"
        ((CHECKS_PASSED++))
    fi
    
    if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "CHANGE_THIS_TO_A_RANDOM_SECRET_KEY_AT_LEAST_32_CHARACTERS" ]; then
        echo -e "${RED}✗${NC} SECRET_KEY: 未设置或使用默认值"
        ((CHECKS_FAILED++))
    else
        echo -e "${GREEN}✓${NC} SECRET_KEY: 已设置"
        ((CHECKS_PASSED++))
    fi
fi
echo ""

# 5. 检查端口占用
echo -e "${BLUE}[5] 检查端口占用${NC}"
check_port 9000
check_port 3000
check_port 5432
check_port 6379
check_port 1883
echo ""

# 6. 检查磁盘空间
echo -e "${BLUE}[6] 检查磁盘空间${NC}"
DISK_USAGE=$(df -h "$PROJECT_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    echo -e "${GREEN}✓${NC} 磁盘使用率: ${DISK_USAGE}%"
    ((CHECKS_PASSED++))
elif [ "$DISK_USAGE" -lt 90 ]; then
    echo -e "${YELLOW}⚠${NC} 磁盘使用率: ${DISK_USAGE}% (建议清理)"
    ((CHECKS_FAILED++))
else
    echo -e "${RED}✗${NC} 磁盘使用率: ${DISK_USAGE}% (空间不足)"
    ((CHECKS_FAILED++))
fi
echo ""

# 7. 检查内存
echo -e "${BLUE}[7] 检查内存${NC}"
if command -v free &> /dev/null; then
    MEM_TOTAL=$(free -m | awk '/^Mem:/{print $2}')
    MEM_AVAILABLE=$(free -m | awk '/^Mem:/{print $7}')
    if [ "$MEM_TOTAL" -ge 2048 ]; then
        echo -e "${GREEN}✓${NC} 总内存: ${MEM_TOTAL}MB, 可用: ${MEM_AVAILABLE}MB"
        ((CHECKS_PASSED++))
    else
        echo -e "${YELLOW}⚠${NC} 总内存: ${MEM_TOTAL}MB (建议至少 2GB)"
        ((CHECKS_FAILED++))
    fi
fi
echo ""

# 8. 检查运行中的服务
echo -e "${BLUE}[8] 检查运行中的服务${NC}"
check_service "ocpp-db-prod"
check_service "ocpp-redis-prod"
check_service "ocpp-mqtt-prod"
check_service "ocpp-csms-prod"
check_service "ocpp-admin-prod"
echo ""

# 9. 检查服务健康
echo -e "${BLUE}[9] 检查服务健康${NC}"
if docker ps --format '{{.Names}}' | grep -q "^ocpp-csms-prod$"; then
    if curl -f http://localhost:9000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} CSMS 健康检查: 通过"
        ((CHECKS_PASSED++))
    else
        echo -e "${YELLOW}⚠${NC} CSMS 健康检查: 失败"
        ((CHECKS_FAILED++))
    fi
fi

if docker ps --format '{{.Names}}' | grep -q "^ocpp-admin-prod$"; then
    if curl -f http://localhost:3000 > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Admin 健康检查: 通过"
        ((CHECKS_PASSED++))
    else
        echo -e "${YELLOW}⚠${NC} Admin 健康检查: 失败"
        ((CHECKS_FAILED++))
    fi
fi
echo ""

# 总结
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}检查总结${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}通过: $CHECKS_PASSED${NC}"
echo -e "${RED}失败: $CHECKS_FAILED${NC}"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ 所有检查通过！${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ 部分检查未通过，请修复后重试${NC}"
    exit 1
fi

