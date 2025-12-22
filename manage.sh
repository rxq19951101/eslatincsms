#!/bin/bash
#
# 生产环境服务管理脚本
# 用于启动、停止、重启和查看服务状态
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
COMPOSE_FILE="docker-compose.prod.yml"
SERVICE_NAME="csms"
HEALTH_CHECK_URL="http://localhost:9000/health"
MAX_WAIT_TIME=60  # 最大等待时间（秒）

# 显示帮助信息
show_help() {
    echo -e "${BLUE}生产环境服务管理脚本${NC}"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  start      - 启动所有服务"
    echo "  stop       - 停止所有服务"
    echo "  restart    - 重启所有服务"
    echo "  status     - 查看服务状态"
    echo "  logs       - 查看服务日志（实时）"
    echo "  logs-tail  - 查看最近100行日志"
    echo "  health     - 检查服务健康状态"
    echo "  rebuild    - 重新构建镜像并启动服务"
    echo "  build      - 重新构建镜像（不启动）"
    echo "  clean      - 清理未使用的镜像和容器"
    echo "  clean-all    - 清理所有相关镜像和容器（危险）"
    echo "  clean-volumes - 清理所有数据卷和镜像（危险，会删除所有数据）"
    echo "  test-prod    - 本地测试生产环境配置"
    echo "  down          - 停止并删除容器"
    echo "  cleanup-db    - 清理无效的充电桩数据（预览模式）"
    echo "  cleanup-db-exec - 清理无效的充电桩数据（实际执行）"
    echo "  help          - 显示此帮助信息"
    echo ""
}

# 检查Docker是否运行
check_docker() {
    if ! docker ps > /dev/null 2>&1; then
        echo -e "${RED}❌ Docker未运行，请先启动Docker${NC}"
        exit 1
    fi
}

# 检查docker-compose文件是否存在
check_compose_file() {
    if [ ! -f "$COMPOSE_FILE" ]; then
        echo -e "${YELLOW}⚠️  生产环境配置文件 $COMPOSE_FILE 不存在${NC}"
        echo -e "${YELLOW}   使用默认的 docker-compose.yml${NC}"
        COMPOSE_FILE="docker-compose.yml"
        if [ ! -f "$COMPOSE_FILE" ]; then
            echo -e "${RED}❌ docker-compose.yml 也不存在${NC}"
            exit 1
        fi
    fi
}

# 等待服务就绪
wait_for_service() {
    local service=$1
    local max_wait=$2
    local elapsed=0
    
    echo -e "${BLUE}等待服务 $service 启动...${NC}"
    
    while [ $elapsed -lt $max_wait ]; do
        if docker compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"; then
            echo -e "${GREEN}✓ 服务 $service 已启动${NC}"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
        echo -n "."
    done
    
    echo ""
    echo -e "${YELLOW}⚠️  服务 $service 启动超时${NC}"
    return 1
}

# 检查健康状态
check_health() {
    local max_wait=$1
    local elapsed=0
    
    echo -e "${BLUE}检查服务健康状态...${NC}"
    
    while [ $elapsed -lt $max_wait ]; do
        if curl -sf "$HEALTH_CHECK_URL" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ 服务健康检查通过${NC}"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
        echo -n "."
    done
    
    echo ""
    echo -e "${YELLOW}⚠️  健康检查超时${NC}"
    return 1
}

# 启动服务
start_services() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}启动生产环境服务${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_docker
    check_compose_file
    
    # 检查环境变量
    if [ -z "$ENCRYPTION_KEY" ] && [ -z "$DATABASE_URL" ]; then
        echo -e "${YELLOW}⚠️  警告: 未检测到环境变量${NC}"
        echo -e "${YELLOW}   请确保已设置必要的环境变量（ENCRYPTION_KEY, DATABASE_URL等）${NC}"
        echo -e "${YELLOW}   建议使用 .env 文件或导出环境变量${NC}"
        echo ""
        read -p "是否继续? (y/n) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    echo -e "${BLUE}使用配置文件: $COMPOSE_FILE${NC}"
    echo ""
    
    # 启动服务
    docker compose -f "$COMPOSE_FILE" up -d
    
    # 等待服务启动
    wait_for_service "$SERVICE_NAME" $MAX_WAIT_TIME
    
    # 等待数据库和Redis就绪
    sleep 5
    
    # 检查健康状态
    check_health $MAX_WAIT_TIME
    
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ 服务启动完成${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "服务地址:"
    echo "  - CSMS API: http://localhost:9000"
    echo "  - API文档: http://localhost:9000/docs"
    echo "  - 健康检查: $HEALTH_CHECK_URL"
    echo ""
}

# 停止服务
stop_services() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}停止生产环境服务${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_docker
    check_compose_file
    
    docker compose -f "$COMPOSE_FILE" stop
    
    echo ""
    echo -e "${GREEN}✓ 服务已停止${NC}"
    echo ""
}

# 重启服务
restart_services() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}重启生产环境服务${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_docker
    check_compose_file
    
    # 重启服务
    docker compose -f "$COMPOSE_FILE" restart
    
    # 等待服务启动
    wait_for_service "$SERVICE_NAME" $MAX_WAIT_TIME
    
    # 检查健康状态
    check_health $MAX_WAIT_TIME
    
    echo ""
    echo -e "${GREEN}✓ 服务重启完成${NC}"
    echo ""
}

# 查看服务状态
show_status() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}服务状态${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_docker
    check_compose_file
    
    docker compose -f "$COMPOSE_FILE" ps
    
    echo ""
    echo -e "${BLUE}健康检查:${NC}"
    if curl -sf "$HEALTH_CHECK_URL" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 服务健康${NC}"
        curl -s "$HEALTH_CHECK_URL" | python3 -m json.tool 2>/dev/null || curl -s "$HEALTH_CHECK_URL"
    else
        echo -e "${RED}❌ 服务不健康或未启动${NC}"
    fi
    echo ""
}

# 查看日志
show_logs() {
    check_docker
    check_compose_file
    
    if [ -n "$1" ]; then
        docker compose -f "$COMPOSE_FILE" logs -f "$1"
    else
        docker compose -f "$COMPOSE_FILE" logs -f
    fi
}

# 查看最近日志
show_logs_tail() {
    check_docker
    check_compose_file
    
    if [ -n "$1" ]; then
        docker compose -f "$COMPOSE_FILE" logs --tail=100 "$1"
    else
        docker compose -f "$COMPOSE_FILE" logs --tail=100
    fi
}

# 健康检查
health_check() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}服务健康检查${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_docker
    check_compose_file
    
    # 检查容器状态
    echo -e "${BLUE}容器状态:${NC}"
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
    
    # 检查健康端点
    echo -e "${BLUE}健康端点检查:${NC}"
    if curl -sf "$HEALTH_CHECK_URL" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ CSMS服务健康${NC}"
        echo ""
        echo "响应内容:"
        curl -s "$HEALTH_CHECK_URL" | python3 -m json.tool 2>/dev/null || curl -s "$HEALTH_CHECK_URL"
        echo ""
    else
        echo -e "${RED}❌ CSMS服务不健康或未启动${NC}"
        echo ""
    fi
    
    # 检查数据库连接
    echo -e "${BLUE}数据库连接:${NC}"
    if docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U ${POSTGRES_USER:-ocpp_user} -d ${POSTGRES_DB:-ocpp} > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 数据库连接正常${NC}"
    else
        echo -e "${RED}❌ 数据库连接失败${NC}"
    fi
    echo ""
    
    # 检查Redis连接
    echo -e "${BLUE}Redis连接:${NC}"
    if docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Redis连接正常${NC}"
    else
        echo -e "${RED}❌ Redis连接失败${NC}"
    fi
    echo ""
}

# 重新构建镜像（不启动）
build_images() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}重新构建镜像${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_docker
    check_compose_file
    
    echo -e "${YELLOW}⚠️  这将重新构建所有镜像，可能需要较长时间${NC}"
    read -p "是否继续? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    
    # 重新构建镜像（不启动）
    docker compose -f "$COMPOSE_FILE" build --no-cache
    
    echo ""
    echo -e "${GREEN}✓ 镜像构建完成${NC}"
    echo ""
}

# 重新构建并启动
rebuild_services() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}重新构建镜像并启动服务${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_docker
    check_compose_file
    
    echo -e "${YELLOW}⚠️  这将重新构建镜像并启动服务，可能需要较长时间${NC}"
    read -p "是否继续? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    
    # 停止服务
    docker compose -f "$COMPOSE_FILE" down
    
    # 重新构建并启动
    docker compose -f "$COMPOSE_FILE" up -d --build
    
    # 等待服务启动
    wait_for_service "$SERVICE_NAME" $MAX_WAIT_TIME
    
    # 检查健康状态
    check_health $MAX_WAIT_TIME
    
    echo ""
    echo -e "${GREEN}✓ 服务重新构建并启动完成${NC}"
    echo ""
}

# 清理未使用的镜像和容器
clean_unused() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}清理未使用的镜像和容器${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_docker
    
    echo -e "${YELLOW}⚠️  这将清理未使用的镜像、容器、网络和构建缓存${NC}"
    read -p "是否继续? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    
    # 清理未使用的资源
    docker system prune -f
    
    echo ""
    echo -e "${GREEN}✓ 清理完成${NC}"
    echo ""
}

# 清理所有相关镜像和容器（危险操作）
clean_all() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}清理所有相关镜像和容器${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_docker
    check_compose_file
    
    echo -e "${RED}⚠️  危险操作！这将：${NC}"
    echo -e "${RED}  - 停止并删除所有相关容器${NC}"
    echo -e "${RED}  - 删除所有相关镜像${NC}"
    echo -e "${RED}  - 清理未使用的资源${NC}"
    echo ""
    echo -e "${YELLOW}数据卷不会被删除${NC}"
    echo ""
    read -p "确认继续? (输入 'yes' 继续) " -r
    echo ""
    if [[ ! $REPLY == "yes" ]]; then
        echo "已取消"
        exit 0
    fi
    
    # 停止并删除容器
    docker compose -f "$COMPOSE_FILE" down
    
    # 获取项目相关的镜像（通过容器名称和构建的镜像）
    echo -e "${BLUE}查找相关镜像...${NC}"
    
    # 通过容器名称查找镜像
    local container_images=$(docker ps -a --format "{{.Image}}" | grep -E "(ocpp|csms|eslatincsms)" | sort -u || true)
    
    # 通过docker-compose构建的镜像
    local compose_images=$(docker compose -f "$COMPOSE_FILE" config --images 2>/dev/null || true)
    
    # 合并并去重
    local all_images=$(echo -e "$container_images\n$compose_images" | grep -v "^$" | sort -u || true)
    
    if [ -n "$all_images" ]; then
        echo -e "${BLUE}删除相关镜像:${NC}"
        echo "$all_images" | while read img; do
            if [ -n "$img" ]; then
                echo "  - $img"
                docker rmi -f "$img" 2>/dev/null || true
            fi
        done
    else
        # 如果没有找到，尝试通过项目名称查找
        local project_name=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')
        local project_images=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep -E "($project_name|ocpp|csms)" || true)
        if [ -n "$project_images" ]; then
            echo -e "${BLUE}删除项目相关镜像:${NC}"
            echo "$project_images" | while read img; do
                if [ -n "$img" ]; then
                    echo "  - $img"
                    docker rmi -f "$img" 2>/dev/null || true
                fi
            done
        fi
    fi
    
    # 清理未使用的资源
    docker system prune -af --volumes
    
    echo ""
    echo -e "${GREEN}✓ 清理完成${NC}"
    echo ""
}

# 停止并删除容器
down_services() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}停止并删除容器${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_docker
    check_compose_file
    
    echo -e "${YELLOW}⚠️  这将停止并删除所有容器（不会删除数据卷）${NC}"
    read -p "是否继续? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    
    docker compose -f "$COMPOSE_FILE" down
    
    echo ""
    echo -e "${GREEN}✓ 容器已停止并删除${NC}"
    echo ""
}

# 主函数
main() {
    case "${1:-help}" in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs "$2"
            ;;
        logs-tail)
            show_logs_tail "$2"
            ;;
        health)
            health_check
            ;;
        rebuild)
            rebuild_services
            ;;
        build)
            build_images
            ;;
        clean)
            clean_unused
            ;;
  clean-all)
    clean_all
    ;;
  clean-volumes)
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}清理所有数据卷${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    check_docker
    check_compose_file
    
    echo -e "${RED}⚠️  危险操作！这将：${NC}"
    echo -e "${RED}  - 停止并删除所有容器${NC}"
    echo -e "${RED}  - 删除所有相关数据卷（包括数据库数据）${NC}"
    echo -e "${RED}  - 删除所有相关镜像${NC}"
    echo ""
    echo -e "${YELLOW}所有数据将永久丢失！${NC}"
    echo ""
    read -p "确认继续? (输入 'yes' 继续) " -r
    echo ""
    if [[ ! $REPLY == "yes" ]]; then
        echo "已取消"
        exit 0
    fi
    
    # 停止并删除容器
    docker compose -f "$COMPOSE_FILE" down
    
    # 获取项目相关的镜像
    echo -e "${BLUE}查找相关镜像...${NC}"
    local container_images=$(docker ps -a --format "{{.Image}}" | grep -E "(ocpp|csms|eslatincsms)" | sort -u || true)
    local compose_images=$(docker compose -f "$COMPOSE_FILE" config --images 2>/dev/null || true)
    local all_images=$(echo -e "$container_images\n$compose_images" | grep -v "^$" | sort -u || true)
    
    if [ -n "$all_images" ]; then
        echo -e "${BLUE}删除相关镜像:${NC}"
        echo "$all_images" | while read img; do
            if [ -n "$img" ]; then
                echo "  - $img"
                docker rmi -f "$img" 2>/dev/null || true
            fi
        done
    fi
    
    # 获取项目相关的数据卷
    echo -e "${BLUE}查找相关数据卷...${NC}"
    local project_volumes=$(docker volume ls --format "{{.Name}}" | grep -E "(eslatincsms|ocpp|postgres|redis|mqtt)" || true)
    
    if [ -n "$project_volumes" ]; then
        echo -e "${BLUE}删除相关数据卷:${NC}"
        echo "$project_volumes" | while read vol; do
            if [ -n "$vol" ]; then
                echo "  - $vol"
                docker volume rm -f "$vol" 2>/dev/null || true
            fi
        done
    fi
    
    # 清理未使用的资源
    docker system prune -af
    
    echo ""
    echo -e "${GREEN}✓ 清理完成（包括数据卷）${NC}"
    echo ""
    ;;
        test-prod)
            echo -e "${BLUE}本地测试生产环境配置...${NC}"
            if [ -f "docker-compose.local-prod.yml" ]; then
                echo -e "${BLUE}使用 docker-compose.local-prod.yml 启动测试环境...${NC}"
                docker compose -f docker-compose.local-prod.yml down 2>/dev/null || true
                docker compose -f docker-compose.local-prod.yml up -d --build
                sleep 10
                docker compose -f docker-compose.local-prod.yml ps
                echo ""
                echo -e "${GREEN}✓ 测试环境已启动${NC}"
                echo "服务地址:"
                echo "  - CSMS: http://localhost:9000"
                echo "  - Admin: http://localhost:3000"
                echo ""
                echo "查看日志: docker compose -f docker-compose.local-prod.yml logs -f"
                echo "停止: docker compose -f docker-compose.local-prod.yml down"
            else
                echo -e "${YELLOW}⚠️  docker-compose.local-prod.yml 不存在${NC}"
                echo "使用生产配置进行测试..."
                docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
                docker compose -f "$COMPOSE_FILE" up -d --build
                sleep 10
                docker compose -f "$COMPOSE_FILE" ps
            fi
            ;;
        down)
            down_services
            ;;
        cleanup-db)
            echo -e "${BLUE}清理无效的充电桩数据（预览模式）...${NC}"
            if ! docker compose -f "$COMPOSE_FILE" ps | grep -q "ocpp-csms-prod.*Up"; then
                echo -e "${RED}❌ CSMS容器未运行，请先启动服务${NC}"
                exit 1
            fi
            docker compose -f "$COMPOSE_FILE" exec -T csms python scripts/cleanup_invalid_charge_points.py
            ;;
        cleanup-db-exec)
            echo -e "${YELLOW}⚠️  警告：将实际删除无效的充电桩数据！${NC}"
            read -p "确认要继续吗？(yes/no): " confirm
            if [ "$confirm" != "yes" ]; then
                echo "已取消操作"
                exit 0
            fi
            if ! docker compose -f "$COMPOSE_FILE" ps | grep -q "ocpp-csms-prod.*Up"; then
                echo -e "${RED}❌ CSMS容器未运行，请先启动服务${NC}"
                exit 1
            fi
            echo -e "${BLUE}执行清理操作...${NC}"
            docker compose -f "$COMPOSE_FILE" exec -T csms python scripts/cleanup_invalid_charge_points.py --execute
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo -e "${RED}❌ 未知命令: $1${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
