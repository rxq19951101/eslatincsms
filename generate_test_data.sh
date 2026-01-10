#!/bin/bash
#
# 测试数据生成脚本
# 在Docker容器中执行Python脚本生成测试数据
#

set -e

echo "========================================="
echo "开始生成测试数据"
echo "========================================="

# 检查容器是否运行
if ! docker ps | grep -q ocpp-csms-prod; then
    echo "❌ CSMS容器未运行，请先启动服务："
    echo "   docker compose -f docker-compose.prod.yml up -d"
    exit 1
fi

echo ""
echo "📊 即将生成以下测试数据："
echo "  - 5个充电站点（分布在深圳各区）"
echo "  - 20个充电桩（每站点4个）"
echo "  - 40个EVSE枪口（每桩2个）"
echo "  - 50个终端用户"
echo "  - 约600个充电会话（30天历史）"
echo "  - 约600个订单和发票"
echo "  - 30条告警记录"
echo ""
echo "⏱️  预计耗时: 10-30秒"
echo ""

read -p "确认生成？(y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 已取消"
    exit 0
fi

echo ""
echo "🚀 开始生成..."
echo ""

# 在容器中执行Python脚本
docker exec ocpp-csms-prod python /app/scripts/generate_test_data.py

echo ""
echo "========================================="
echo "✅ 测试数据生成完成！"
echo "========================================="
echo ""
echo "🌐 现在可以访问前端查看数据："
echo "   http://localhost:3000"
echo ""
echo "📄 页面检查清单："
echo "  ✓ 仪表板 - 查看统计数据和趋势图"
echo "  ✓ 充电桩 - 查看充电桩列表和详情"
echo "  ✓ 用户 - 查看用户列表"
echo "  ✓ 交易记录 - 查看充电历史"
echo "  ✓ 统计报表 - 查看收入、充电量等统计"
echo "  ✓ 告警 - 查看告警列表"
echo "  ✓ 地图 - 查看站点分布"
echo ""
