#!/bin/bash
#
# 修复 Docker 构建问题
# 检查文件结构并修复路径问题
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Docker 构建问题修复脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

cd "$PROJECT_DIR"

# 检查文件结构
echo -e "${YELLOW}[1] 检查文件结构...${NC}"

MISSING_FILES=0

# 检查 csms/Dockerfile
if [ ! -f "csms/Dockerfile" ]; then
    echo -e "${RED}✗ 未找到: csms/Dockerfile${NC}"
    MISSING_FILES=$((MISSING_FILES + 1))
else
    echo -e "${GREEN}✓ 找到: csms/Dockerfile${NC}"
fi

# 检查 admin/Dockerfile.prod
if [ ! -f "admin/Dockerfile.prod" ]; then
    echo -e "${RED}✗ 未找到: admin/Dockerfile.prod${NC}"
    MISSING_FILES=$((MISSING_FILES + 1))
else
    echo -e "${GREEN}✓ 找到: admin/Dockerfile.prod${NC}"
fi

# 检查 csms/requirements.txt
if [ ! -f "csms/requirements.txt" ]; then
    echo -e "${RED}✗ 未找到: csms/requirements.txt${NC}"
    MISSING_FILES=$((MISSING_FILES + 1))
else
    echo -e "${GREEN}✓ 找到: csms/requirements.txt${NC}"
fi

# 检查 admin/package.json
if [ ! -f "admin/package.json" ]; then
    echo -e "${RED}✗ 未找到: admin/package.json${NC}"
    MISSING_FILES=$((MISSING_FILES + 1))
else
    echo -e "${GREEN}✓ 找到: admin/package.json${NC}"
fi

if [ $MISSING_FILES -gt 0 ]; then
    echo -e "${RED}错误: 缺少 $MISSING_FILES 个必要文件${NC}"
    echo -e "${YELLOW}请确保已从 Git 仓库完整拉取代码${NC}"
    exit 1
fi

echo ""

# 检查 docker-compose.prod.yml
echo -e "${YELLOW}[2] 检查 docker-compose.prod.yml...${NC}"
if [ ! -f "docker-compose.prod.yml" ]; then
    echo -e "${RED}✗ 未找到: docker-compose.prod.yml${NC}"
    exit 1
fi

# 验证构建上下文路径
echo -e "${YELLOW}[3] 验证构建上下文...${NC}"

# 检查 csms 目录
if [ ! -d "csms" ]; then
    echo -e "${RED}✗ 目录不存在: csms/${NC}"
    exit 1
fi

# 检查 admin 目录
if [ ! -d "admin" ]; then
    echo -e "${RED}✗ 目录不存在: admin/${NC}"
    exit 1
fi

# 检查 csms/app 目录
if [ ! -d "csms/app" ]; then
    echo -e "${RED}✗ 目录不存在: csms/app/${NC}"
    exit 1
fi

# 检查 admin/app 目录
if [ ! -d "admin/app" ]; then
    echo -e "${RED}✗ 目录不存在: admin/app/${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 所有目录结构正确${NC}"
echo ""

# 测试构建上下文
echo -e "${YELLOW}[4] 测试构建上下文...${NC}"

# 测试 csms 构建上下文
cd "$PROJECT_DIR/csms"
if [ -f "Dockerfile" ] && [ -f "requirements.txt" ] && [ -d "app" ]; then
    echo -e "${GREEN}✓ csms 构建上下文完整${NC}"
else
    echo -e "${RED}✗ csms 构建上下文不完整${NC}"
    exit 1
fi

# 测试 admin 构建上下文
cd "$PROJECT_DIR/admin"
if [ -f "Dockerfile.prod" ] && [ -f "package.json" ] && [ -d "app" ]; then
    echo -e "${GREEN}✓ admin 构建上下文完整${NC}"
else
    echo -e "${RED}✗ admin 构建上下文不完整${NC}"
    exit 1
fi

cd "$PROJECT_DIR"
echo ""

# 显示当前目录结构
echo -e "${YELLOW}[5] 当前目录结构:${NC}"
echo -e "${BLUE}$(pwd)${NC}"
echo ""
echo "csms/"
ls -la csms/ | head -10
echo ""
echo "admin/"
ls -la admin/ | head -10
echo ""

# 提供修复建议
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}检查完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "如果仍然遇到构建错误，请尝试："
echo ""
echo "1. 清理 Docker 缓存："
echo "   docker system prune -a"
echo ""
echo "2. 单独构建服务："
echo "   cd csms && docker build -t csms-test ."
echo "   cd admin && docker build -f Dockerfile.prod -t admin-test ."
echo ""
echo "3. 检查文件权限："
echo "   ls -la csms/Dockerfile admin/Dockerfile.prod"
echo ""
echo "4. 查看详细错误："
echo "   docker-compose -f docker-compose.prod.yml build --progress=plain"
echo ""

