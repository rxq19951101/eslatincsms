#!/bin/bash
#
# 服务器文件检查脚本
# 用于诊断服务器上缺少的文件
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}服务器文件结构检查${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查关键文件
echo -e "${YELLOW}[1] 检查关键文件...${NC}"

MISSING=0

# CSMS 文件
echo -e "\n${BLUE}CSMS 服务:${NC}"
if [ -f "csms/Dockerfile" ]; then
    echo -e "${GREEN}✓ csms/Dockerfile${NC}"
else
    echo -e "${RED}✗ csms/Dockerfile (缺失)${NC}"
    MISSING=$((MISSING + 1))
fi

if [ -f "csms/requirements.txt" ]; then
    echo -e "${GREEN}✓ csms/requirements.txt${NC}"
else
    echo -e "${RED}✗ csms/requirements.txt (缺失)${NC}"
    MISSING=$((MISSING + 1))
fi

if [ -d "csms/app" ]; then
    echo -e "${GREEN}✓ csms/app/ (目录存在)${NC}"
else
    echo -e "${RED}✗ csms/app/ (目录缺失)${NC}"
    MISSING=$((MISSING + 1))
fi

# Admin 文件
echo -e "\n${BLUE}Admin 服务:${NC}"
if [ -f "admin/Dockerfile.prod" ]; then
    echo -e "${GREEN}✓ admin/Dockerfile.prod${NC}"
else
    echo -e "${RED}✗ admin/Dockerfile.prod (缺失)${NC}"
    MISSING=$((MISSING + 1))
fi

if [ -f "admin/Dockerfile" ]; then
    echo -e "${GREEN}✓ admin/Dockerfile${NC}"
else
    echo -e "${YELLOW}⚠ admin/Dockerfile (可选)${NC}"
fi

if [ -f "admin/package.json" ]; then
    echo -e "${GREEN}✓ admin/package.json${NC}"
else
    echo -e "${RED}✗ admin/package.json (缺失)${NC}"
    MISSING=$((MISSING + 1))
fi

if [ -d "admin/app" ]; then
    echo -e "${GREEN}✓ admin/app/ (目录存在)${NC}"
else
    echo -e "${RED}✗ admin/app/ (目录缺失)${NC}"
    MISSING=$((MISSING + 1))
fi

# 配置文件
echo -e "\n${BLUE}配置文件:${NC}"
if [ -f "docker-compose.prod.yml" ]; then
    echo -e "${GREEN}✓ docker-compose.prod.yml${NC}"
else
    echo -e "${RED}✗ docker-compose.prod.yml (缺失)${NC}"
    MISSING=$((MISSING + 1))
fi

if [ -f ".env.production" ]; then
    echo -e "${GREEN}✓ .env.production${NC}"
else
    echo -e "${YELLOW}⚠ .env.production (可选，需要创建)${NC}"
fi

if [ -f "mosquitto.conf" ]; then
    echo -e "${GREEN}✓ mosquitto.conf${NC}"
else
    echo -e "${YELLOW}⚠ mosquitto.conf (可选)${NC}"
fi

echo ""

# 显示目录结构
echo -e "${YELLOW}[2] 当前目录结构:${NC}"
echo -e "${BLUE}$(pwd)${NC}"
echo ""

if [ -d "csms" ]; then
    echo -e "${BLUE}csms/ 目录内容:${NC}"
    ls -la csms/ | head -15
    echo ""
fi

if [ -d "admin" ]; then
    echo -e "${BLUE}admin/ 目录内容:${NC}"
    ls -la admin/ | head -15
    echo ""
fi

# 检查 Git 状态
echo -e "${YELLOW}[3] Git 状态:${NC}"
if [ -d ".git" ]; then
    echo -e "${GREEN}✓ Git 仓库存在${NC}"
    echo ""
    echo "当前分支:"
    git branch --show-current 2>/dev/null || echo "无法确定分支"
    echo ""
    echo "最近一次提交:"
    git log -1 --oneline 2>/dev/null || echo "无提交记录"
    echo ""
    echo "未跟踪的文件:"
    git status --short 2>/dev/null | head -10 || echo "无法获取状态"
else
    echo -e "${YELLOW}⚠ 不是 Git 仓库${NC}"
fi

echo ""

# 总结
echo -e "${BLUE}========================================${NC}"
if [ $MISSING -eq 0 ]; then
    echo -e "${GREEN}✓ 所有关键文件都存在${NC}"
    echo -e "${GREEN}========================================${NC}"
    exit 0
else
    echo -e "${RED}✗ 发现 $MISSING 个缺失的关键文件${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo -e "${YELLOW}修复建议:${NC}"
    echo ""
    echo "1. 确保从 Git 仓库完整拉取代码:"
    echo "   git pull origin main"
    echo ""
    echo "2. 如果文件确实缺失，检查 .gitignore 是否忽略了这些文件"
    echo ""
    echo "3. 手动检查文件是否存在:"
    echo "   ls -la admin/Dockerfile.prod"
    echo "   ls -la csms/Dockerfile"
    echo ""
    exit 1
fi

