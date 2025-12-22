#!/bin/bash
#
# 运行CSMS单元测试脚本
#

set -e

echo "=========================================="
echo "运行CSMS单元测试"
echo "=========================================="
echo ""

# 检查是否在虚拟环境中
if [ -z "$VIRTUAL_ENV" ] && [ ! -f "venv/bin/activate" ]; then
    echo "提示: 建议在虚拟环境中运行测试"
    echo ""
fi

# 安装测试依赖
echo "1. 检查测试依赖..."
pip install -q pytest pytest-asyncio pytest-cov httpx 2>/dev/null || {
    echo "安装测试依赖..."
    pip install pytest pytest-asyncio pytest-cov httpx
}

echo ""
echo "2. 运行单元测试..."
echo ""

# 运行测试
pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="

