#!/bin/bash
#
# 合并子仓库到主仓库脚本
# 删除子仓库的 .git 目录，整合到主仓库
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
echo -e "${BLUE}合并子仓库到主仓库${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

cd "$PROJECT_DIR"

# 检查是否在主仓库
if [ ! -d ".git" ]; then
    echo -e "${RED}错误: 当前目录不是 Git 仓库${NC}"
    exit 1
fi

# 检查远程仓库
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if [ -z "$REMOTE_URL" ]; then
    echo -e "${YELLOW}警告: 未配置远程仓库${NC}"
    echo -e "${YELLOW}请先配置远程仓库: git remote add origin <url>${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 主仓库: $REMOTE_URL${NC}"
echo ""

# 查找子仓库
SUBMODULES=("csms" "admin" "app" "charger-sim")
FOUND_SUBMODULES=()

echo -e "${YELLOW}[1] 检查子仓库...${NC}"
for dir in "${SUBMODULES[@]}"; do
    if [ -d "$dir/.git" ]; then
        echo -e "${YELLOW}  发现子仓库: $dir/.git${NC}"
        FOUND_SUBMODULES+=("$dir")
    fi
done

if [ ${#FOUND_SUBMODULES[@]} -eq 0 ]; then
    echo -e "${GREEN}✓ 没有发现子仓库${NC}"
    exit 0
fi

echo ""
echo -e "${YELLOW}将删除以下子仓库的 .git 目录:${NC}"
for dir in "${FOUND_SUBMODULES[@]}"; do
    echo -e "  - $dir/.git"
done
echo ""

# 确认操作
read -p "是否继续？(y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}操作已取消${NC}"
    exit 0
fi

# 删除子仓库的 .git 目录
echo -e "${YELLOW}[2] 删除子仓库的 .git 目录...${NC}"
for dir in "${FOUND_SUBMODULES[@]}"; do
    if [ -d "$dir/.git" ]; then
        echo -e "${YELLOW}  删除: $dir/.git${NC}"
        rm -rf "$dir/.git"
        echo -e "${GREEN}  ✓ $dir/.git 已删除${NC}"
    fi
done

# 删除 .gitmodules 文件（如果存在）
if [ -f ".gitmodules" ]; then
    echo -e "${YELLOW}[3] 删除 .gitmodules 文件...${NC}"
    rm -f .gitmodules
    echo -e "${GREEN}  ✓ .gitmodules 已删除${NC}"
fi

# 添加所有文件到主仓库
echo -e "${YELLOW}[4] 添加所有文件到主仓库...${NC}"
git add -A

# 检查是否有变更
if git diff --cached --quiet && git diff --quiet; then
    echo -e "${GREEN}✓ 没有需要提交的变更${NC}"
else
    echo -e "${YELLOW}[5] 提交变更...${NC}"
    git commit -m "chore: 合并子仓库到主仓库

- 删除 csms, admin, app, charger-sim 子仓库的 .git 目录
- 整合所有代码到主仓库 eslatincsms
- 删除 .gitmodules 文件"
    
    echo -e "${GREEN}✓ 变更已提交${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}合并完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "下一步："
echo "  1. 检查状态: git status"
echo "  2. 推送到远程: git push origin main"
echo ""

