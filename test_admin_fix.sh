#!/bin/bash
#
# 测试Admin修复脚本
# 验证占位符检测和错误提示功能
#

echo "=========================================="
echo "Admin配置修复测试"
echo "=========================================="
echo ""

# 检查服务状态
echo "1. 检查服务状态..."
docker compose -f docker-compose.prod.yml ps admin csms | grep -E "(admin|csms)" | head -2
echo ""

# 测试API连接
echo "2. 测试CSMS API连接..."
API_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/api/v1/chargers)
if [ "$API_RESPONSE" = "200" ]; then
    echo "   ✅ CSMS API正常 (HTTP $API_RESPONSE)"
    CHARGER_COUNT=$(curl -s http://localhost:9000/api/v1/chargers | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    echo "   📊 充电桩数量: $CHARGER_COUNT"
else
    echo "   ❌ CSMS API异常 (HTTP $API_RESPONSE)"
fi
echo ""

# 测试Admin页面
echo "3. 测试Admin页面..."
ADMIN_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/chargers)
if [ "$ADMIN_RESPONSE" = "200" ]; then
    echo "   ✅ Admin页面可访问 (HTTP $ADMIN_RESPONSE)"
else
    echo "   ❌ Admin页面异常 (HTTP $ADMIN_RESPONSE)"
fi
echo ""

# 检查环境变量
echo "4. 检查环境变量配置..."
ENV_VAR=$(docker compose -f docker-compose.prod.yml exec -T admin env 2>&1 | grep "NEXT_PUBLIC_CSMS_HTTP" || echo "未设置")
if [ "$ENV_VAR" = "未设置" ]; then
    echo "   ⚠️  NEXT_PUBLIC_CSMS_HTTP 未设置（将使用自动检测）"
else
    echo "   ✅ 环境变量已设置: $ENV_VAR"
    if echo "$ENV_VAR" | grep -q "your-server-ip\|your-ip"; then
        echo "   ❌ 检测到占位符！需要修复"
    fi
fi
echo ""

# 测试场景说明
echo "5. 测试场景说明："
echo "   📝 正常情况（localhost）："
echo "      - 访问: http://localhost:3000/chargers"
echo "      - 预期: API地址自动检测为 http://localhost:9000"
echo "      - 结果: ✅ 应该正常工作"
echo ""
echo "   📝 占位符情况（模拟生产环境问题）："
echo "      - 访问: http://your-server-ip:3000/chargers"
echo "      - 预期: 检测到占位符，显示配置错误提示"
echo "      - 结果: ⚠️  应该显示友好的错误信息和修复步骤"
echo ""

echo "=========================================="
echo "测试完成"
echo "=========================================="
echo ""
echo "💡 提示："
echo "   1. 在浏览器中访问 http://localhost:3000/chargers 查看实际效果"
echo "   2. 如果看到充电桩列表，说明配置正常"
echo "   3. 如果看到配置错误提示，说明占位符检测功能正常工作"
echo ""

