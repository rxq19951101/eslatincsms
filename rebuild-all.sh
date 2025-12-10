#!/bin/bash
#
# 停止所有容器、删除所有镜像、重建并启动的脚本
# 支持开发环境和生产环境
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认使用生产环境配置
COMPOSE_FILE="${1:-docker-compose.prod.yml}"

# 检查 docker-compose 文件是否存在
if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}错误: 未找到 $COMPOSE_FILE 文件${NC}"
    echo -e "${YELLOW}使用方式：${NC}"
    echo "  $0 [docker-compose文件]"
    echo ""
    echo -e "${YELLOW}示例：${NC}"
    echo "  $0                          # 使用 docker-compose.prod.yml（默认）"
    echo "  $0 docker-compose.yml      # 使用开发环境配置"
    echo "  $0 docker-compose.prod.yml # 使用生产环境配置"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}停止、删除、重建并启动所有服务${NC}"
echo -e "${GREEN}使用配置文件: $COMPOSE_FILE${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 确认操作
echo -e "${YELLOW}警告：此操作将：${NC}"
echo "  1. 停止所有容器并删除所有卷（包括数据库数据）"
echo "  2. 删除所有容器"
echo "  3. 删除所有镜像（包括项目构建的镜像）"
echo "  4. 删除所有未使用的镜像、容器、网络和卷"
echo "  5. 重建所有镜像"
echo "  6. 启动所有服务（数据库将重新初始化）"
echo ""
read -p "是否继续？(yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo -e "${YELLOW}操作已取消${NC}"
    exit 0
fi

# 1. 停止所有容器并删除卷
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 1/6: 停止所有容器并删除卷${NC}"
echo -e "${BLUE}========================================${NC}"
docker compose -f "$COMPOSE_FILE" down -v || true
echo -e "${GREEN}✓ 所有容器已停止，卷已删除${NC}"

# 2. 删除所有容器
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 2/6: 删除所有容器${NC}"
echo -e "${BLUE}========================================${NC}"
docker compose -f "$COMPOSE_FILE" rm -f || true
echo -e "${GREEN}✓ 所有容器已删除${NC}"

# 3. 删除所有项目相关的镜像
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 3/6: 删除所有项目相关的镜像${NC}"
echo -e "${BLUE}========================================${NC}"

# 获取项目名称（从 docker-compose 文件所在目录）
PROJECT_NAME=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')

# 删除项目构建的镜像
echo "删除项目构建的镜像..."
docker images --format "{{.Repository}}:{{.Tag}}" | grep -E "(ocpp|csms|admin|charger-sim|${PROJECT_NAME})" | xargs -r docker rmi -f || true

# 删除所有未使用的镜像（包括 dangling 镜像）
echo "删除所有未使用的镜像..."
docker image prune -af || true

echo -e "${GREEN}✓ 所有镜像已删除${NC}"

# 4. 清理所有未使用的资源（包括卷）
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 4/6: 清理所有未使用的资源（包括卷）${NC}"
echo -e "${BLUE}========================================${NC}"
# 删除所有未使用的卷（包括数据库卷）
docker volume prune -f || true
# 清理所有未使用的资源
docker system prune -af || true
echo -e "${GREEN}✓ 所有未使用的资源已清理（包括数据库卷）${NC}"

# 5. 重建所有镜像（不使用缓存）
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 5/6: 重建所有镜像（不使用缓存）${NC}"
echo -e "${BLUE}========================================${NC}"
docker compose -f "$COMPOSE_FILE" build --no-cache
echo -e "${GREEN}✓ 所有镜像已重建${NC}"

# 6. 启动所有服务
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 6/6: 启动所有服务${NC}"
echo -e "${BLUE}========================================${NC}"
docker compose -f "$COMPOSE_FILE" up -d
echo -e "${GREEN}✓ 所有服务已启动${NC}"

# 等待服务启动
echo ""
echo -e "${YELLOW}等待服务启动...${NC}"
sleep 10

# 显示服务状态
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}服务状态：${NC}"
docker compose -f "$COMPOSE_FILE" ps
echo ""

# 显示有用的命令
echo -e "${YELLOW}有用的命令：${NC}"
echo "  查看所有服务日志:"
echo "    docker compose -f $COMPOSE_FILE logs -f"
echo ""
echo "  查看特定服务日志:"
echo "    docker compose -f $COMPOSE_FILE logs -f csms"
echo "    docker compose -f $COMPOSE_FILE logs -f admin"
echo ""
echo "  检查服务健康状态:"
echo "    docker compose -f $COMPOSE_FILE ps"
echo ""
echo "  停止所有服务:"
echo "    docker compose -f $COMPOSE_FILE down"
echo ""
