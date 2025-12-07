#!/bin/bash
# 测试充电桩模拟器的充电数据返回功能

echo "=========================================="
echo "测试充电桩模拟器充电数据返回"
echo "=========================================="
echo ""

# 检查充电桩是否在线
echo "1. 检查充电桩状态..."
CHARGER_ID="CP-DOCKER-1"
API_BASE="http://localhost:9000"

response=$(curl -s "${API_BASE}/api/v1/chargers" 2>/dev/null)
if echo "$response" | grep -q "$CHARGER_ID"; then
    echo "   ✓ 充电桩 $CHARGER_ID 已在线"
else
    echo "   ✗ 充电桩 $CHARGER_ID 未找到"
    exit 1
fi

echo ""
echo "2. 查看模拟器日志（最后20行）..."
docker logs charger-sim --tail 20 2>&1 | grep -E "初始化|连接|Heartbeat|MeterValues|StartTransaction|StopTransaction|充电" || echo "   没有相关日志"

echo ""
echo "3. 触发远程启动充电..."
response=$(curl -s -X POST "${API_BASE}/api/remoteStart" \
  -H "Content-Type: application/json" \
  -d "{\"chargePointId\": \"$CHARGER_ID\", \"idTag\": \"TEST001\"}")

echo "   响应: $response"

echo ""
echo "4. 等待5秒，查看充电数据..."
sleep 5

echo ""
echo "5. 查看模拟器日志（充电相关）..."
docker logs charger-sim --tail 30 2>&1 | grep -E "MeterValues|StartTransaction|充电|transactionId" || echo "   没有充电相关日志"

echo ""
echo "6. 查看后端日志（充电相关）..."
docker logs csms --tail 30 2>&1 | grep -E "MeterValues|StartTransaction|充电|transactionId" || echo "   没有充电相关日志"

echo ""
echo "7. 停止充电..."
response=$(curl -s -X POST "${API_BASE}/api/remoteStop" \
  -H "Content-Type: application/json" \
  -d "{\"chargePointId\": \"$CHARGER_ID\"}")

echo "   响应: $response"

echo ""
echo "=========================================="
echo "测试完成！"
echo "=========================================="
echo ""
echo "实时查看模拟器日志: docker logs -f charger-sim"
echo "实时查看后端日志: docker logs -f csms"

