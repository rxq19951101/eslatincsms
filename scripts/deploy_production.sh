#!/bin/bash
#
# 生产环境部署脚本
# 用于在服务器上部署 OCPP CSMS 系统
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}OCPP CSMS 生产环境部署脚本${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: 未找到 Docker，请先安装 Docker${NC}"
    exit 1
fi

# 检查 Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}错误: 未找到 docker-compose，请先安装 docker-compose${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker 环境检查通过${NC}"

# 检查环境变量文件
ENV_FILE="$PROJECT_DIR/.env.production"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}警告: 未找到 .env.production 文件${NC}"
    echo -e "${YELLOW}正在从模板创建...${NC}"
    if [ -f "$PROJECT_DIR/.env.production" ]; then
        cp "$PROJECT_DIR/.env.production" "$ENV_FILE"
    else
        echo -e "${RED}错误: 请先创建 .env.production 配置文件${NC}"
        exit 1
    fi
fi

# 检查必要的环境变量
source "$ENV_FILE" 2>/dev/null || true

if [ -z "$DB_PASSWORD" ] || [ "$DB_PASSWORD" = "CHANGE_THIS_SECURE_PASSWORD" ]; then
    echo -e "${RED}错误: 请在 .env.production 中设置 DB_PASSWORD${NC}"
    exit 1
fi

if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "CHANGE_THIS_TO_A_RANDOM_SECRET_KEY_AT_LEAST_32_CHARACTERS" ]; then
    echo -e "${RED}错误: 请在 .env.production 中设置 SECRET_KEY${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 环境变量检查通过${NC}"

# 创建必要的目录
echo -e "${YELLOW}创建必要的目录...${NC}"
mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/backups"
chmod 755 "$PROJECT_DIR/logs"
chmod 755 "$PROJECT_DIR/backups"

# 复制环境变量文件
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}复制 .env.production 到 .env...${NC}"
    cp "$ENV_FILE" "$PROJECT_DIR/.env"
fi

# 停止现有服务
echo -e "${YELLOW}停止现有服务...${NC}"
cd "$PROJECT_DIR"
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# 构建镜像
echo -e "${YELLOW}构建 Docker 镜像...${NC}"
docker-compose -f docker-compose.prod.yml build --no-cache

# 启动服务
echo -e "${YELLOW}启动服务...${NC}"
docker-compose -f docker-compose.prod.yml up -d

# 等待服务就绪
echo -e "${YELLOW}等待服务启动...${NC}"
sleep 10

# 检查服务状态
echo -e "${YELLOW}检查服务状态...${NC}"
docker-compose -f docker-compose.prod.yml ps

# 检查健康状态
echo -e "${YELLOW}检查服务健康状态...${NC}"
sleep 5

# 检查 CSMS 健康
if curl -f http://localhost:${CSMS_PORT:-9000}/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ CSMS 服务健康${NC}"
else
    echo -e "${YELLOW}⚠ CSMS 服务可能尚未就绪，请稍后检查${NC}"
fi

# 检查 Admin 健康
if curl -f http://localhost:${ADMIN_PORT:-3000} > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Admin 服务健康${NC}"
else
    echo -e "${YELLOW}⚠ Admin 服务可能尚未就绪，请稍后检查${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "服务地址："
echo "  - CSMS API: http://localhost:${CSMS_PORT:-9000}"
echo "  - Admin 管理平台: http://localhost:${ADMIN_PORT:-3000}"
echo "  - API 文档: http://localhost:${CSMS_PORT:-9000}/docs"
echo ""
echo "查看日志："
echo "  docker-compose -f docker-compose.prod.yml logs -f"
echo ""
echo "停止服务："
echo "  docker-compose -f docker-compose.prod.yml down"
echo ""

