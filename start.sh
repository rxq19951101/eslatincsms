#!/bin/bash

#
# 便捷启动脚本 - 支持开发、测试、生产环境
# 使用方法: ./start.sh [dev|test|prod] [up|down|restart|logs]
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 默认参数
ENV=${1:-dev}
ACTION=${2:-up}

# 显示帮助信息
show_help() {
    echo -e "${BLUE}ESLatin CSMS 环境管理脚本${NC}"
    echo ""
    echo "使用方法: ./start.sh [环境] [操作]"
    echo ""
    echo "环境选项:"
    echo -e "  ${GREEN}dev${NC}      开发环境 (CSMS:8000, Admin:3001)"
    echo -e "  ${GREEN}test${NC}     测试环境 (CSMS:8001, Admin:3002)"
    echo -e "  ${GREEN}prod${NC}     生产环境 (CSMS:9000, Admin:3000)"
    echo -e "  ${GREEN}default${NC}  快速启动 (使用生产端口)"
    echo ""
    echo "操作选项:"
    echo -e "  ${YELLOW}up${NC}       启动服务 (默认)"
    echo -e "  ${YELLOW}down${NC}     停止服务"
    echo -e "  ${YELLOW}restart${NC}  重启服务"
    echo -e "  ${YELLOW}logs${NC}     查看日志"
    echo -e "  ${YELLOW}ps${NC}       查看运行状态"
    echo -e "  ${YELLOW}clean${NC}    清理数据和镜像"
    echo ""
    echo "示例:"
    echo "  ./start.sh dev up       # 启动开发环境"
    echo "  ./start.sh test logs    # 查看测试环境日志"
    echo "  ./start.sh prod down    # 停止生产环境"
    echo ""
}

# 检查参数
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    show_help
    exit 0
fi

# 确定 docker-compose 文件
case $ENV in
    dev)
        COMPOSE_FILE="docker-compose.dev.yml"
        ENV_NAME="开发环境"
        CSMS_PORT="8000"
        ADMIN_PORT="3001"
        ;;
    test)
        COMPOSE_FILE="docker-compose.test.yml"
        ENV_NAME="测试环境"
        CSMS_PORT="8001"
        ADMIN_PORT="3002"
        ;;
    prod)
        COMPOSE_FILE="docker-compose.prod.yml"
        ENV_NAME="生产环境"
        CSMS_PORT="9000"
        ADMIN_PORT="3000"
        ;;
    default)
        COMPOSE_FILE="docker-compose.yml"
        ENV_NAME="快速启动"
        CSMS_PORT="9000"
        ADMIN_PORT="3000"
        ;;
    *)
        echo -e "${RED}错误: 未知环境 '$ENV'${NC}"
        echo "支持的环境: dev, test, prod, default"
        echo "运行 './start.sh --help' 查看帮助"
        exit 1
        ;;
esac

# 执行操作
case $ACTION in
    up)
        echo -e "${GREEN}正在启动 ${ENV_NAME}...${NC}"
        echo -e "${BLUE}配置文件: ${COMPOSE_FILE}${NC}"
        echo -e "${BLUE}CSMS 端口: ${CSMS_PORT}${NC}"
        echo -e "${BLUE}Admin 端口: ${ADMIN_PORT}${NC}"
        echo ""
        docker compose -f $COMPOSE_FILE up -d --build
        echo ""
        echo -e "${GREEN}✓ 服务启动成功！${NC}"
        echo ""
        echo "访问地址:"
        echo -e "  ${BLUE}Admin 管理界面: http://localhost:${ADMIN_PORT}${NC}"
        echo -e "  ${BLUE}CSMS API: http://localhost:${CSMS_PORT}${NC}"
        echo -e "  ${BLUE}CSMS 健康检查: http://localhost:${CSMS_PORT}/health${NC}"
        if [[ "$ENV" != "prod" ]]; then
            echo -e "  ${BLUE}API 文档: http://localhost:${CSMS_PORT}/docs${NC}"
        fi
        echo ""
        echo "查看日志: ./start.sh $ENV logs"
        ;;
    down)
        echo -e "${YELLOW}正在停止 ${ENV_NAME}...${NC}"
        docker compose -f $COMPOSE_FILE down
        echo -e "${GREEN}✓ 服务已停止${NC}"
        ;;
    restart)
        echo -e "${YELLOW}正在重启 ${ENV_NAME}...${NC}"
        docker compose -f $COMPOSE_FILE restart
        echo -e "${GREEN}✓ 服务已重启${NC}"
        ;;
    logs)
        echo -e "${BLUE}查看 ${ENV_NAME} 日志 (Ctrl+C 退出)${NC}"
        docker compose -f $COMPOSE_FILE logs -f
        ;;
    ps)
        echo -e "${BLUE}${ENV_NAME} 运行状态:${NC}"
        docker compose -f $COMPOSE_FILE ps
        ;;
    clean)
        echo -e "${RED}警告: 这将删除所有容器、数据卷和镜像！${NC}"
        read -p "确认继续? (yes/no): " confirm
        if [[ "$confirm" == "yes" ]]; then
            echo -e "${YELLOW}正在清理 ${ENV_NAME}...${NC}"
            docker compose -f $COMPOSE_FILE down -v --rmi all
            echo -e "${GREEN}✓ 清理完成${NC}"
        else
            echo "已取消"
        fi
        ;;
    *)
        echo -e "${RED}错误: 未知操作 '$ACTION'${NC}"
        echo "支持的操作: up, down, restart, logs, ps, clean"
        echo "运行 './start.sh --help' 查看帮助"
        exit 1
        ;;
esac
