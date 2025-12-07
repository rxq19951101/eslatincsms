#!/bin/bash
#
# 快速创建 GitHub 仓库并推送代码
# 交互式输入 Token
#

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PARENT_DIR="/Users/xiaoqingran"
GITHUB_USER="rxq19951101"

clear
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  GitHub 仓库创建工具${NC}"
echo -e "${BLUE}========================================${NC}\n"
echo -e "${GREEN}GitHub 用户名: ${GITHUB_USER}${NC}\n"
echo -e "${YELLOW}需要 GitHub Personal Access Token${NC}"
echo -e "${YELLOW}获取地址: https://github.com/settings/tokens/new${NC}"
echo -e "${YELLOW}权限: 勾选 'repo' (完整仓库权限)${NC}\n"
echo -e "${BLUE}请输入您的 Token:${NC} "
read -sp "" GITHUB_TOKEN
echo -e "\n"

if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${RED}✗ 未提供 Token${NC}"
    exit 1
fi

# 仓库列表
REPOS=(
    "eslatincsms-csms:CSMS backend service - OCPP 1.6J 后端服务"
    "eslatincsms-admin:Admin management platform - 充电桩管理后台"
    "eslatincsms-app:Mobile app - 充电桩用户端应用"
    "eslatincsms-charger-sim:Charger simulator - 充电桩模拟器"
)

SUCCESS_COUNT=0
FAIL_COUNT=0

echo -e "${BLUE}开始创建仓库...${NC}\n"

# 创建并推送每个仓库
for repo_info in "${REPOS[@]}"; do
    IFS=':' read -r repo_name repo_desc <<< "$repo_info"
    repo_dir="$PARENT_DIR/$repo_name"
    
    if [ ! -d "$repo_dir" ]; then
        echo -e "${RED}✗ 目录不存在: $repo_dir${NC}\n"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi
    
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}处理: ${YELLOW}$repo_name${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    cd "$repo_dir"
    
    # 1. 创建 GitHub 仓库
    echo -e "${YELLOW}[1/3] 创建 GitHub 仓库...${NC}"
    response=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Authorization: token $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        https://api.github.com/user/repos \
        -d "{
            \"name\": \"$repo_name\",
            \"description\": \"$repo_desc\",
            \"private\": false,
            \"auto_init\": false
        }" 2>&1)
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "201" ]; then
        echo -e "${GREEN}  ✓ 仓库创建成功${NC}"
    elif [ "$http_code" = "422" ]; then
        if echo "$body" | grep -q "already exists"; then
            echo -e "${YELLOW}  ⚠ 仓库已存在，继续推送...${NC}"
        else
            echo -e "${RED}  ✗ 创建失败: 仓库可能已存在或名称无效${NC}"
            FAIL_COUNT=$((FAIL_COUNT + 1))
            continue
        fi
    elif [ "$http_code" = "401" ]; then
        echo -e "${RED}  ✗ Token 无效或已过期${NC}"
        echo -e "${YELLOW}  请检查 Token 是否正确${NC}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    else
        echo -e "${RED}  ✗ 创建失败 (HTTP $http_code)${NC}"
        echo -e "${RED}  响应: $(echo "$body" | head -c 200)${NC}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi
    
    # 2. 配置远程仓库
    echo -e "${YELLOW}[2/3] 配置远程仓库...${NC}"
    git remote remove origin 2>/dev/null || true
    git remote add origin "git@github.com:${GITHUB_USER}/${repo_name}.git" 2>/dev/null || \
        git remote set-url origin "git@github.com:${GITHUB_USER}/${repo_name}.git"
    echo -e "${GREEN}  ✓ 远程仓库已配置${NC}"
    
    # 3. 确保分支名为 main
    current_branch=$(git branch --show-current 2>/dev/null || echo "main")
    if [ "$current_branch" != "main" ]; then
        git branch -M main 2>/dev/null || true
    fi
    
    # 4. 推送代码
    echo -e "${YELLOW}[3/3] 推送代码到 GitHub...${NC}"
    if git push -u origin main 2>&1; then
        echo -e "${GREEN}  ✓ 推送成功${NC}"
        echo -e "${GREEN}  📦 仓库地址: https://github.com/${GITHUB_USER}/${repo_name}${NC}\n"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo -e "${RED}  ✗ 推送失败${NC}"
        echo -e "${YELLOW}  提示: 请检查 SSH 密钥配置${NC}\n"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

# 总结
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "成功创建并推送: ${GREEN}${SUCCESS_COUNT}${NC} 个仓库"
if [ $FAIL_COUNT -gt 0 ]; then
    echo -e "失败: ${RED}${FAIL_COUNT}${NC} 个仓库"
fi
echo -e "${BLUE}========================================${NC}\n"

if [ $SUCCESS_COUNT -gt 0 ]; then
    echo -e "${GREEN}访问您的仓库：${NC}"
    echo -e "https://github.com/${GITHUB_USER}?tab=repositories\n"
    
    echo -e "${GREEN}仓库列表：${NC}"
    for repo_info in "${REPOS[@]}"; do
        IFS=':' read -r repo_name repo_desc <<< "$repo_info"
        echo -e "  • https://github.com/${GITHUB_USER}/${repo_name}"
    done
    echo ""
fi

