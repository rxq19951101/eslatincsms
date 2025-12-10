#!/bin/bash
#
# 正式环境重新构建并替换 csms Docker 镜像的脚本
# 支持两种方式：
# 1. 使用 build 方式（本地构建）
# 2. 使用 image 方式（从镜像仓库拉取）
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}正式环境重新构建/替换 csms Docker 镜像${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查是否提供了镜像名
if [ -z "$1" ]; then
    echo -e "${YELLOW}使用方式：${NC}"
    echo "  方式1（本地构建）: $0 build"
    echo "  方式2（拉取镜像）: $0 <镜像名>"
    echo ""
    echo -e "${YELLOW}示例：${NC}"
    echo "  $0 build                                    # 本地构建"
    echo "  $0 registry.example.com/csms:latest        # 拉取指定镜像"
    echo "  $0 ocpp-csms:1.0.0                         # 拉取指定镜像"
    echo ""
    exit 1
fi

COMPOSE_FILE="docker-compose.prod.yml"

# 检查 docker-compose.prod.yml 是否存在
if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}错误: 未找到 $COMPOSE_FILE 文件${NC}"
    exit 1
fi

# 方式1：本地构建
if [ "$1" = "build" ]; then
    echo -e "${YELLOW}方式：本地构建镜像${NC}"
    echo ""
    
    # 1. 停止 csms 容器
    echo -e "${YELLOW}1. 停止 csms 容器...${NC}"
    docker compose -f $COMPOSE_FILE stop csms || true
    
    # 2. 删除 csms 容器
    echo -e "${YELLOW}2. 删除 csms 容器...${NC}"
    docker compose -f $COMPOSE_FILE rm -f csms || true
    
    # 3. 重新构建镜像（不使用缓存）
    echo -e "${YELLOW}3. 重新构建 csms 镜像（不使用缓存）...${NC}"
    docker compose -f $COMPOSE_FILE build --no-cache csms
    
    # 4. 启动服务
    echo -e "${YELLOW}4. 启动 csms 服务...${NC}"
    docker compose -f $COMPOSE_FILE up -d csms

# 方式2：从镜像仓库拉取
else
    IMAGE_NAME="$1"
    echo -e "${YELLOW}方式：从镜像仓库拉取镜像${NC}"
    echo -e "${YELLOW}镜像名: ${IMAGE_NAME}${NC}"
    echo ""
    
    # 1. 停止 csms 容器
    echo -e "${YELLOW}1. 停止 csms 容器...${NC}"
    docker compose -f $COMPOSE_FILE stop csms || true
    
    # 2. 删除 csms 容器
    echo -e "${YELLOW}2. 删除 csms 容器...${NC}"
    docker compose -f $COMPOSE_FILE rm -f csms || true
    
    # 3. 拉取新镜像
    echo -e "${YELLOW}3. 拉取新镜像: ${IMAGE_NAME}...${NC}"
    docker pull "$IMAGE_NAME"
    
    # 4. 修改 docker-compose.prod.yml 使用新镜像（临时）
    # 注意：这里需要手动修改 docker-compose.prod.yml，或者使用环境变量
    echo -e "${YELLOW}4. 提示：请确保 $COMPOSE_FILE 中的 csms 服务使用 image: ${IMAGE_NAME}${NC}"
    echo -e "${YELLOW}   或者使用环境变量 CSMS_IMAGE=${IMAGE_NAME}${NC}"
    echo ""
    
    # 如果设置了环境变量，使用它
    if [ -n "$CSMS_IMAGE" ]; then
        export CSMS_IMAGE="$IMAGE_NAME"
    fi
    
    # 5. 启动服务（使用新镜像）
    echo -e "${YELLOW}5. 启动 csms 服务...${NC}"
    # 如果 docker-compose.prod.yml 使用环境变量，可以这样：
    # CSMS_IMAGE="$IMAGE_NAME" docker compose -f $COMPOSE_FILE up -d csms
    # 否则需要手动修改 docker-compose.prod.yml
    docker compose -f $COMPOSE_FILE up -d csms
fi

# 6. 等待服务启动
echo -e "${YELLOW}6. 等待服务启动...${NC}"
sleep 5

# 7. 查看服务状态
echo -e "${YELLOW}7. 查看服务状态...${NC}"
docker compose -f $COMPOSE_FILE ps csms

# 8. 查看日志
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "查看日志："
echo "  docker compose -f $COMPOSE_FILE logs -f csms"
echo ""
echo "检查健康状态："
echo "  curl http://localhost:\${CSMS_PORT:-9000}/health"
echo ""
