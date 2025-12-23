#!/usr/bin/env python3
#
# 检查服务器代码版本的脚本
# 通过测试时间格式来判断是否使用了新代码
#

import requests
import json
import sys

def check_time_format(server_url: str):
    """检查服务器返回的时间格式"""
    server_url = server_url.rstrip('/')
    
    print("=" * 80)
    print("检查服务器代码版本")
    print("=" * 80)
    print(f"服务器: {server_url}")
    print("=" * 80)
    print()
    
    # 方法1: 检查 /health 端点
    print("方法1: 检查 /health 端点的时间格式...")
    try:
        response = requests.get(f"{server_url}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            ts = data.get("ts", "")
            print(f"  时间戳: {ts}")
            
            if ts.endswith("Z"):
                print("  ✓ 使用新代码（Z 后缀格式）")
                return True
            elif "+00:00" in ts or ts.endswith("+00:00"):
                print("  ✗ 使用旧代码（+00:00 格式）")
                return False
            else:
                print(f"  ? 未知格式: {ts}")
                return None
        else:
            print(f"  ✗ 请求失败: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ✗ 请求失败: {e}")
    
    print()
    
    # 方法2: 如果设备已连接，检查实际 OCPP 响应
    print("方法2: 检查 OCPP 响应的时间格式...")
    print("  提示: 需要设备发送 Heartbeat 或 BootNotification 消息")
    print("  然后查看日志中的 currentTime 格式")
    print()
    
    return None


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="检查服务器代码版本（通过时间格式）"
    )
    parser.add_argument(
        "--server",
        type=str,
        default="http://47.236.134.99:9000",
        help="CSMS 服务器地址"
    )
    
    args = parser.parse_args()
    
    result = check_time_format(args.server)
    
    print("=" * 80)
    if result is True:
        print("结论: 服务器使用的是新代码（Z 后缀格式）")
    elif result is False:
        print("结论: 服务器使用的是旧代码（+00:00 格式）")
        print()
        print("需要执行以下操作:")
        print("1. 确保代码已更新到最新版本")
        print("2. 重新构建 Docker 镜像:")
        print("   docker-compose -f docker-compose.prod.yml build csms")
        print("3. 重启服务:")
        print("   docker-compose -f docker-compose.prod.yml up -d csms")
    else:
        print("结论: 无法确定代码版本")
    print("=" * 80)


if __name__ == "__main__":
    main()

