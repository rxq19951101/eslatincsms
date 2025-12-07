#!/bin/bash
#
# 推送所有仓库到 GitHub
#

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PARENT_DIR="/Users/xiaoqingran"

REPOS=(
    "eslatincsms-csms"
    "eslatincsms-admin"
    "eslatincsms-app"
    "eslatincsms-charger-sim"
)

echo -e "${BLUE}开始推送所有仓库到 GitHub...${NC}\n"

for repo_name in "${REPOS[@]}"; do
    repo_dir="$PARENT_DIR/$repo_name"
    
    if [ ! -d "$repo_dir" ]; then
        echo -e "${RED}✗ 目录不存在: $repo_dir${NC}\n"
        continue
    fi
    
    echo -e "${BLUE}推送: $repo_name${NC}"
    cd "$repo_dir"
    
    # 检查远程仓库
    if ! git remote get-url origin &>/dev/null; then
        echo -e "${RED}  ✗ 未配置远程仓库，请先运行 create_github_repos.sh${NC}\n"
        continue
    fi
    
    # 检查分支
    current_branch=$(git branch --show-current 2>/dev/null || echo "main")
    if [ "$current_branch" != "main" ]; then
        git branch -M main 2>/dev/null || true
    fi
    
    # 推送
    echo -e "${YELLOW}  正在推送...${NC}"
    if git push -u origin main 2>&1; then
        echo -e "${GREEN}  ✓ 推送成功${NC}\n"
    else
        echo -e "${RED}  ✗ 推送失败，请检查：${NC}"
        echo -e "${YELLOW}     1. GitHub 仓库是否已创建${NC}"
        echo -e "${YELLOW}     2. SSH 密钥是否正确配置${NC}"
        echo -e "${YELLOW}     3. 仓库权限是否正确${NC}\n"
    fi
done

echo -e "${GREEN}完成！${NC}"

