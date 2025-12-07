#!/bin/bash
#
# Redis MISCONF 错误快速修复脚本
# 使用此脚本立即修复Redis配置，无需重启容器
#

echo "=========================================="
echo "Redis MISCONF 错误快速修复"
echo "=========================================="
echo ""

# 检查Redis容器是否运行
if ! docker ps | grep -q "redis"; then
    echo "❌ Redis容器未运行，请先启动: docker compose up -d redis"
    exit 1
fi

echo "1. 禁用RDB快照..."
docker exec redis redis-cli CONFIG SET save "" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "   ✓ RDB快照已禁用"
else
    echo "   ⚠ 设置失败，但继续..."
fi

echo ""
echo "2. 允许在保存失败时继续写入..."
docker exec redis redis-cli CONFIG SET stop-writes-on-bgsave-error no 2>/dev/null
if [ $? -eq 0 ]; then
    echo "   ✓ 写入保护已禁用"
else
    echo "   ⚠ 设置失败，但继续..."
fi

echo ""
echo "3. 验证配置..."
echo ""
echo "   RDB快照配置:"
docker exec redis redis-cli CONFIG GET save 2>/dev/null | grep -v "^$"

echo ""
echo "   写入保护配置:"
docker exec redis redis-cli CONFIG GET stop-writes-on-bgsave-error 2>/dev/null | grep -v "^$"

echo ""
echo "4. 测试Redis写入..."
docker exec redis redis-cli SET fix_test_key "fix_test_value" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "   ✓ Redis写入测试成功"
    docker exec redis redis-cli DEL fix_test_key >/dev/null 2>&1
else
    echo "   ❌ Redis写入测试失败"
    echo ""
    echo "   如果仍然失败，请尝试重启Redis容器:"
    echo "   docker compose restart redis"
    exit 1
fi

echo ""
echo "=========================================="
echo "✓ 修复完成！"
echo "=========================================="
echo ""
echo "提示: 此修复在容器重启后会丢失。"
echo "      要永久生效，请确保 docker-compose.yml 中的配置正确，"
echo "      然后运行: docker compose down && docker compose up -d"
echo ""

