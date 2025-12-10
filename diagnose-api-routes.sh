#!/bin/bash
#
# 诊断 API 路由注册问题的脚本
#

API_BASE="${1:-http://47.236.134.99:9000}"

echo "=========================================="
echo "诊断 API 路由注册问题"
echo "=========================================="
echo ""

# 1. 检查 OpenAPI JSON，看是否有 /api/v1/chargers
echo "1. 检查 OpenAPI 规范中的路由定义..."
OPENAPI_JSON=$(curl -s "$API_BASE/openapi.json" 2>/dev/null)

if [ $? -eq 0 ] && [ -n "$OPENAPI_JSON" ]; then
    echo "   ✓ OpenAPI JSON 可访问"
    
    # 检查是否有 /api/v1/chargers
    if echo "$OPENAPI_JSON" | grep -q "\"/api/v1/chargers\""; then
        echo "   ✓ 找到 /api/v1/chargers 路由定义"
    else
        echo "   ✗ 未找到 /api/v1/chargers 路由定义"
        echo ""
        echo "   检查是否有其他 /api/v1 路由："
        echo "$OPENAPI_JSON" | grep -o '"/api/v1[^"]*"' | sort -u | head -10
    fi
    
    # 检查是否有 /chargers (旧版)
    if echo "$OPENAPI_JSON" | grep -q "\"/chargers\""; then
        echo "   ✓ 找到 /chargers 路由定义（旧版）"
    fi
else
    echo "   ✗ 无法访问 OpenAPI JSON"
fi
echo ""

# 2. 直接测试端点
echo "2. 直接测试端点..."
echo "   测试 /api/v1/chargers:"
V1_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$API_BASE/api/v1/chargers" 2>/dev/null)
V1_CODE=$(echo "$V1_RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
V1_BODY=$(echo "$V1_RESPONSE" | sed '/HTTP_CODE/d')

if [ "$V1_CODE" = "200" ]; then
    echo "   ✓ /api/v1/chargers 返回 200"
elif [ "$V1_CODE" = "404" ]; then
    echo "   ✗ /api/v1/chargers 返回 404 (路由不存在)"
else
    echo "   ✗ /api/v1/chargers 返回 $V1_CODE"
    echo "   响应: ${V1_BODY:0:200}"
fi

echo ""
echo "   测试 /chargers (旧版):"
OLD_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$API_BASE/chargers" 2>/dev/null)
OLD_CODE=$(echo "$OLD_RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)

if [ "$OLD_CODE" = "200" ]; then
    echo "   ✓ /chargers 返回 200 (旧版端点可用)"
else
    echo "   ✗ /chargers 返回 $OLD_CODE"
fi
echo ""

# 3. 检查服务器日志（如果在本地）
echo "3. 检查建议："
echo "   在服务器上运行以下命令查看启动日志："
echo ""
echo "   docker compose -f docker-compose.prod.yml logs csms | grep -E 'API v1|路由|chargers|ERROR|WARNING' | tail -50"
echo ""
echo "   或者查看完整的启动日志："
echo "   docker compose -f docker-compose.prod.yml logs csms | tail -100"
echo ""

# 4. 检查容器内是否可以导入模块
echo "4. 如果可能，在容器内检查模块导入："
echo "   docker compose -f docker-compose.prod.yml exec csms python -c \"from app.api.v1 import api_router; print('导入成功')\""
echo ""

echo "=========================================="
echo "诊断完成"
echo "=========================================="
