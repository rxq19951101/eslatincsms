#!/bin/bash
#
# 在 GitHub 上创建四个远程仓库并推送代码
# 使用 SSH 方式连接
#

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# GitHub 用户名（从 SSH 检测）
PARENT_DIR="/Users/xiaoqingran"

echo -e "${BLUE}开始创建 GitHub 远程仓库...${NC}\n"

# 从 SSH 检测 GitHub 用户名
SSH_USER=$(ssh -T git@github.com 2>&1 | grep -oP '(?<=Hi )\w+(?=!)' || echo "")
if [ -n "$SSH_USER" ]; then
    GITHUB_USER="$SSH_USER"
    echo -e "${GREEN}检测到 GitHub 用户名: ${GITHUB_USER}${NC}\n"
else
    echo -e "${YELLOW}请输入您的 GitHub 用户名：${NC}"
    read -r GITHUB_USER
    if [ -z "$GITHUB_USER" ]; then
        echo -e "${RED}✗ 未提供用户名${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}使用 GitHub 用户名: ${GITHUB_USER}${NC}\n"

# 检查 SSH 连接
echo -e "${BLUE}检查 SSH 连接...${NC}"
if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo -e "${GREEN}✓ SSH 连接正常${NC}\n"
else
    echo -e "${YELLOW}⚠ SSH 连接测试未完全通过，但继续执行...${NC}\n"
fi

# 仓库列表
REPOS=(
    "eslatincsms-csms:CSMS backend service"
    "eslatincsms-admin:Admin management platform"
    "eslatincsms-app:Mobile app"
    "eslatincsms-charger-sim:Charger simulator"
)

# 创建仓库并推送
for repo_info in "${REPOS[@]}"; do
    IFS=':' read -r repo_name repo_desc <<< "$repo_info"
    repo_dir="$PARENT_DIR/$repo_name"
    
    if [ ! -d "$repo_dir" ]; then
        echo -e "${RED}✗ 目录不存在: $repo_dir${NC}"
        continue
    fi
    
    echo -e "${BLUE}处理仓库: $repo_name${NC}"
    cd "$repo_dir"
    
    # 检查是否已有远程仓库
    if git remote get-url origin &>/dev/null; then
        echo -e "${YELLOW}  ⚠ 已存在远程仓库，跳过${NC}\n"
        continue
    fi
    
    # 添加远程仓库（使用 SSH）
    git remote add origin "git@github.com:${GITHUB_USER}/${repo_name}.git" || {
        echo -e "${YELLOW}  ⚠ 远程仓库已存在或添加失败${NC}"
    }
    
    # 设置分支为 main（如果还没有）
    current_branch=$(git branch --show-current 2>/dev/null || echo "main")
    if [ "$current_branch" != "main" ]; then
        git branch -M main 2>/dev/null || true
    fi
    
    echo -e "${GREEN}  ✓ 已添加远程仓库${NC}"
    echo -e "${YELLOW}  📝 请在 GitHub 上手动创建仓库: ${repo_name}${NC}"
    echo -e "${YELLOW}     访问: https://github.com/new${NC}"
    echo -e "${YELLOW}     仓库名: ${repo_name}${NC}"
    echo -e "${YELLOW}     描述: ${repo_desc}${NC}"
    echo -e "${YELLOW}     不要初始化 README（本地已有代码）${NC}\n"
done

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}下一步操作：${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "1. 在 GitHub 上创建四个仓库："
echo -e "   - ${YELLOW}eslatincsms-csms${NC}"
echo -e "   - ${YELLOW}eslatincsms-admin${NC}"
echo -e "   - ${YELLOW}eslatincsms-app${NC}"
echo -e "   - ${YELLOW}eslatincsms-charger-sim${NC}"
echo -e ""
echo -e "2. 创建完成后，运行推送脚本："
echo -e "   ${GREEN}./scripts/push_to_github.sh${NC}"
echo -e ""
echo -e "或者手动推送每个仓库："
echo -e "   cd eslatincsms-csms && git push -u origin main"
echo -e "   cd ../eslatincsms-admin && git push -u origin main"
echo -e "   cd ../eslatincsms-app && git push -u origin main"
echo -e "   cd ../eslatincsms-charger-sim && git push -u origin main"

