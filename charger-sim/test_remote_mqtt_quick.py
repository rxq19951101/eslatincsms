#!/usr/bin/env python3
#
# 快速测试版本 - 带超时和详细输出
#

import asyncio
import signal
import sys
import os

# 导入主测试脚本
sys.path.insert(0, os.path.dirname(__file__))
from test_remote_mqtt_ocpp import RemoteMQTTOCPPTester

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("测试超时")

async def run_with_timeout(tester, timeout_seconds=30):
    """运行测试，带超时"""
    try:
        # 设置超时
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)
        
        await tester.run()
    except TimeoutError:
        print("\n" + "=" * 80)
        print("测试超时（30秒），但连接可能仍在运行")
        print("=" * 80)
        print(f"连接状态: {'已连接' if tester.connected else '未连接'}")
        print(f"待处理请求数: {len(tester.pending_requests)}")
        print("=" * 80)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    finally:
        signal.alarm(0)  # 取消超时
        if tester.client:
            tester.client.loop_stop()
            tester.client.disconnect()

def main():
    tester = RemoteMQTTOCPPTester(
        broker_host="47.236.134.99",
        broker_port=1883,
        client_id="zcf&861076087029615",
        username="861076087029615",
        password="pHYtWMiW+UOa",
        type_code="zcf",
        serial_number="861076087029615",
        up_topic="zcf/861076087029615/user/up",
        down_topic="zcf/861076087029615/user/down"
    )
    
    try:
        asyncio.run(run_with_timeout(tester, timeout_seconds=30))
    except KeyboardInterrupt:
        print("\n测试已停止")

if __name__ == "__main__":
    main()

