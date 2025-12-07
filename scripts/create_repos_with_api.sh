#!/bin/bash
#
# 使用 GitHub API 自动创建仓库并推送代码
# 需要 GitHub Personal Access Token
#

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# GitHub 用户名（从 SSH 检测）
PARENT_DIR="/Users/xiaoqingran"

echo -e "${BLUE}使用 GitHub API 创建仓库...${NC}\n"

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

# 获取 GitHub Token
echo -e "${YELLOW}请输入您的 GitHub Personal Access Token：${NC}"
echo -e "${YELLOW}（如果没有，请访问: https://github.com/settings/tokens）${NC}"
read -s GITHUB_TOKEN

if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${RED}✗ 未提供 Token，无法使用 API 创建仓库${NC}"
    echo -e "${YELLOW}请手动在 GitHub 上创建仓库，然后运行 push_to_github.sh${NC}"
    exit 1
fi

# 仓库列表
REPOS=(
    "eslatincsms-csms:CSMS backend service"
    "eslatincsms-admin:Admin management platform"
    "eslatincsms-app:Mobile app"
    "eslatincsms-charger-sim:Charger simulator"
)

# 创建仓库
for repo_info in "${REPOS[@]}"; do
    IFS=':' read -r repo_name repo_desc <<< "$repo_info"
    repo_dir="$PARENT_DIR/$repo_name"
    
    if [ ! -d "$repo_dir" ]; then
        echo -e "${RED}✗ 目录不存在: $repo_dir${NC}"
        continue
    fi
    
    echo -e "${BLUE}创建仓库: $repo_name${NC}"
    
    # 使用 GitHub API 创建仓库
    response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Authorization: token $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        https://api.github.com/user/repos \
        -d "{
            \"name\": \"$repo_name\",
            \"description\": \"$repo_desc\",
            \"private\": false,
            \"auto_init\": false
        }")
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "201" ]; then
        echo -e "${GREEN}  ✓ 仓库创建成功${NC}"
    elif [ "$http_code" = "422" ]; then
        echo -e "${YELLOW}  ⚠ 仓库可能已存在，继续...${NC}"
    else
        echo -e "${RED}  ✗ 创建失败 (HTTP $http_code)${NC}"
        echo -e "${RED}    响应: $body${NC}"
        continue
    fi
    
    # 配置远程仓库并推送
    cd "$repo_dir"
    
    # 移除旧的远程仓库（如果存在）
    git remote remove origin 2>/dev/null || true
    
    # 添加新的远程仓库
    git remote add origin "git@github.com:${GITHUB_USER}/${repo_name}.git"
    
    # 确保分支名为 main
    current_branch=$(git branch --show-current 2>/dev/null || echo "main")
    if [ "$current_branch" != "main" ]; then
        git branch -M main 2>/dev/null || true
    fi
    
    # 推送代码
    echo -e "${YELLOW}  正在推送代码...${NC}"
    if git push -u origin main 2>&1; then
        echo -e "${GREEN}  ✓ 推送成功${NC}\n"
    else
        echo -e "${RED}  ✗ 推送失败${NC}\n"
    fi
done

echo -e "${GREEN}完成！所有仓库已创建并推送。${NC}"
echo -e "${BLUE}访问您的 GitHub: https://github.com/${GITHUB_USER}${NC}"

