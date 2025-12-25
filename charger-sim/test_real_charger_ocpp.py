#!/usr/bin/env python3
#
# 真实充电桩 OCPP 功能测试脚本
# 用于测试通过 WebSocket 连接到服务器的真实充电桩
# 服务器地址: 47.236.134.99
#

import argparse
import requests
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
import sys


class RealChargerOCPPTester:
    """真实充电桩 OCPP 功能测试器"""
    
    def __init__(self, server_url: str, charge_point_id: Optional[str] = None):
        self.server_url = server_url.rstrip('/')
        self.charge_point_id = charge_point_id
        self.base_url = f"{self.server_url}/api/v1"
        self.test_results: List[Dict[str, Any]] = []
        
    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 80)
        print(f"测试: {title}")
        print("=" * 80)
    
    def print_section(self, title: str):
        """打印小节标题"""
        print(f"\n{'─' * 80}")
        print(f" {title}")
        print(f"{'─' * 80}")
    
    def record_test(self, test_name: str, success: bool, message: str, 
                    details: Optional[Dict] = None, response_time: Optional[float] = None):
        """记录测试结果"""
        result = {
            "test_name": test_name,
            "success": success,
            "message": message,
            "details": details or {},
            "response_time": response_time,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✓ 通过" if success else "✗ 失败"
        print(f"{status}: {message}")
        if details:
            print(f"详细信息: {json.dumps(details, ensure_ascii=False, indent=2)}")
        if response_time:
            print(f"响应时间: {response_time:.3f} 秒")
    
    def list_connected_chargers(self) -> List[str]:
        """列出所有已连接的充电桩"""
        self.print_section("获取已连接的充电桩列表")
        try:
            response = requests.get(
                f"{self.base_url}/chargers",
                timeout=10
            )
            if response.status_code == 200:
                chargers = response.json()
                connected_chargers = []
                print(f"找到 {len(chargers)} 个充电桩:")
                for charger in chargers:
                    status = charger.get('status', 'Unknown')
                    last_seen = charger.get('last_seen')
                    charger_id = charger.get('id')
                    print(f"  - {charger_id}: 状态={status}, 最后在线={last_seen}")
                    if status != "Unknown" and last_seen:
                        connected_chargers.append(charger_id)
                
                if not connected_chargers:
                    print("\n⚠ 警告: 没有找到已连接的充电桩")
                    print("提示: 请确保充电桩已通过 WebSocket 连接到服务器")
                
                return connected_chargers
            else:
                print(f"✗ 获取充电桩列表失败: HTTP {response.status_code}")
                return []
        except Exception as e:
            print(f"✗ 获取充电桩列表异常: {e}")
            return []
    
    def check_connection(self) -> bool:
        """检查充电桩连接状态"""
        self.print_header("1. 检查充电桩连接状态")
        
        if not self.charge_point_id:
            print("✗ 未提供充电桩ID")
            return False
        
        try:
            start_time = time.time()
            response = requests.get(
                f"{self.base_url}/chargers/{self.charge_point_id}",
                timeout=10
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                charger = response.json()
                status = charger.get('status', 'Unknown')
                last_seen = charger.get('last_seen')
                
                is_connected = status != "Unknown" and last_seen is not None
                
                self.record_test(
                    "连接检查",
                    is_connected,
                    f"充电桩状态: {status}" if is_connected else "充电桩未连接",
                    {
                        "id": charger.get('id'),
                        "vendor": charger.get('vendor'),
                        "model": charger.get('model'),
                        "status": status,
                        "last_seen": last_seen,
                        "connector_type": charger.get('connector_type'),
                    },
                    response_time
                )
                return is_connected
            else:
                self.record_test(
                    "连接检查",
                    False,
                    f"充电桩未找到 (HTTP {response.status_code})",
                    {"status_code": response.status_code},
                    response_time
                )
                return False
        except Exception as e:
            self.record_test(
                "连接检查",
                False,
                f"检查连接失败: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_get_configuration(self, keys: Optional[List[str]] = None) -> bool:
        """测试 GetConfiguration"""
        self.print_header("2. GetConfiguration - 获取配置")
        
        payload = {"chargePointId": self.charge_point_id}
        if keys:
            payload["keys"] = keys
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/ocpp/get-configuration",
                json=payload,
                timeout=15
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                data = result.get("data", {})
                
                if success and isinstance(data, dict):
                    configuration_key = data.get("configurationKey", [])
                    self.record_test(
                        "GetConfiguration",
                        True,
                        f"成功获取 {len(configuration_key)} 个配置项",
                        {
                            "configuration_count": len(configuration_key),
                            "sample_configs": configuration_key[:5] if configuration_key else []
                        },
                        response_time
                    )
                    return True
                else:
                    self.record_test(
                        "GetConfiguration",
                        False,
                        "响应格式不正确",
                        {"response": result},
                        response_time
                    )
                    return False
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.record_test(
                    "GetConfiguration",
                    False,
                    f"HTTP {response.status_code}",
                    error_detail,
                    response_time
                )
                return False
        except Exception as e:
            self.record_test(
                "GetConfiguration",
                False,
                f"请求失败: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_change_configuration(self, key: str, value: str) -> bool:
        """测试 ChangeConfiguration"""
        self.print_header("3. ChangeConfiguration - 更改配置")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "key": key,
            "value": value
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/ocpp/change-configuration",
                json=payload,
                timeout=15
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                data = result.get("data", {})
                
                if isinstance(data, dict):
                    status = data.get("status", "")
                    if status in ["Accepted", "Rejected", "NotSupported"]:
                        is_accepted = status == "Accepted"
                        self.record_test(
                            "ChangeConfiguration",
                            is_accepted,
                            f"配置更改响应: {status}",
                            {"status": status, "key": key, "value": value},
                            response_time
                        )
                        return is_accepted
                    else:
                        self.record_test(
                            "ChangeConfiguration",
                            False,
                            f"响应状态不符合 OCPP 标准: {status}",
                            {"response": data},
                            response_time
                        )
                        return False
                else:
                    self.record_test(
                        "ChangeConfiguration",
                        False,
                        "响应格式不符合 OCPP 标准",
                        {"response": data},
                        response_time
                    )
                    return False
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.record_test(
                    "ChangeConfiguration",
                    False,
                    f"HTTP {response.status_code}",
                    error_detail,
                    response_time
                )
                return False
        except Exception as e:
            self.record_test(
                "ChangeConfiguration",
                False,
                f"请求失败: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_unlock_connector(self, connector_id: int = 1) -> bool:
        """测试 UnlockConnector"""
        self.print_header("4. UnlockConnector - 解锁连接器")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "connectorId": connector_id
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/ocpp/unlock-connector",
                json=payload,
                timeout=15
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                data = result.get("data", {})
                
                if isinstance(data, dict):
                    status = data.get("status", "")
                    if status in ["Unlocked", "UnlockFailed", "NotSupported"]:
                        is_unlocked = status == "Unlocked"
                        self.record_test(
                            "UnlockConnector",
                            is_unlocked,
                            f"解锁响应: {status}",
                            {"status": status, "connector_id": connector_id},
                            response_time
                        )
                        return is_unlocked
                    else:
                        self.record_test(
                            "UnlockConnector",
                            False,
                            f"响应状态不符合 OCPP 标准: {status}",
                            {"response": data},
                            response_time
                        )
                        return False
                else:
                    self.record_test(
                        "UnlockConnector",
                        False,
                        "响应格式不符合 OCPP 标准",
                        {"response": data},
                        response_time
                    )
                    return False
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.record_test(
                    "UnlockConnector",
                    False,
                    f"HTTP {response.status_code}",
                    error_detail,
                    response_time
                )
                return False
        except Exception as e:
            self.record_test(
                "UnlockConnector",
                False,
                f"请求失败: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_remote_start_transaction(self, id_tag: str = "TEST_TAG_001", connector_id: int = 1) -> bool:
        """测试 RemoteStartTransaction"""
        self.print_header("5. RemoteStartTransaction - 远程启动充电")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "idTag": id_tag,
            "connectorId": connector_id
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            print("⚠ 注意: 这将尝试启动真实的充电交易，请确保充电桩已准备好")
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/ocpp/remote-start-transaction",
                json=payload,
                timeout=15
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                data = result.get("data", {})
                
                if isinstance(data, dict):
                    status = data.get("status", "")
                    if status in ["Accepted", "Rejected"]:
                        is_accepted = status == "Accepted"
                        self.record_test(
                            "RemoteStartTransaction",
                            is_accepted,
                            f"远程启动响应: {status}",
                            {"status": status, "id_tag": id_tag, "connector_id": connector_id},
                            response_time
                        )
                        return is_accepted
                    else:
                        self.record_test(
                            "RemoteStartTransaction",
                            False,
                            f"响应状态不符合 OCPP 标准: {status}",
                            {"response": data},
                            response_time
                        )
                        return False
                else:
                    self.record_test(
                        "RemoteStartTransaction",
                        False,
                        "响应格式不符合 OCPP 标准",
                        {"response": data},
                        response_time
                    )
                    return False
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.record_test(
                    "RemoteStartTransaction",
                    False,
                    f"HTTP {response.status_code}",
                    error_detail,
                    response_time
                )
                return False
        except Exception as e:
            self.record_test(
                "RemoteStartTransaction",
                False,
                f"请求失败: {e}",
                {"error": str(e)}
            )
            return False
    
    def get_active_transaction(self) -> Optional[int]:
        """获取正在进行的交易ID"""
        try:
            response = requests.get(
                f"{self.base_url}/transactions",
                params={"charge_point_id": self.charge_point_id, "status": "ongoing"},
                timeout=10
            )
            if response.status_code == 200:
                sessions = response.json()
                if sessions:
                    return sessions[0].get("transaction_id")
            return None
        except Exception as e:
            print(f"获取活动交易失败: {e}")
            return None
    
    def test_remote_stop_transaction(self, transaction_id: Optional[int] = None) -> bool:
        """测试 RemoteStopTransaction"""
        self.print_header("6. RemoteStopTransaction - 远程停止充电")
        
        # 如果没有提供 transaction_id，尝试自动查找
        if transaction_id is None:
            print("正在查找正在进行的交易...")
            transaction_id = self.get_active_transaction()
            
            if transaction_id is None:
                # 尝试查找所有交易，包括最新的
                try:
                    response = requests.get(
                        f"{self.base_url}/transactions",
                        params={"charge_point_id": self.charge_point_id},
                        timeout=10
                    )
                    if response.status_code == 200:
                        transactions = response.json()
                        if transactions:
                            # 使用最新的交易ID
                            transaction_id = transactions[0].get("transaction_id")
                            print(f"找到最新交易ID: {transaction_id}")
                        else:
                            self.record_test(
                                "RemoteStopTransaction",
                                False,
                                "未找到任何交易，无法停止",
                                {"message": "请先启动一个充电交易"}
                            )
                            return False
                except Exception as e:
                    self.record_test(
                        "RemoteStopTransaction",
                        False,
                        f"查找交易失败: {e}",
                        {"error": str(e)}
                    )
                    return False
            else:
                print(f"找到正在进行的交易ID: {transaction_id}")
        
        if transaction_id is None:
            self.record_test(
                "RemoteStopTransaction",
                False,
                "未找到交易ID，无法停止",
                {"message": "请先启动一个充电交易，或手动提供 transaction_id"}
            )
            return False
        
        payload = {
            "chargePointId": self.charge_point_id,
            "transactionId": transaction_id
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            print("⚠ 注意: 这将尝试停止真实的充电交易")
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/ocpp/remote-stop-transaction",
                json=payload,
                timeout=15
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                data = result.get("data", {})
                
                if isinstance(data, dict):
                    status = data.get("status", "")
                    if status in ["Accepted", "Rejected"]:
                        is_accepted = status == "Accepted"
                        self.record_test(
                            "RemoteStopTransaction",
                            is_accepted,
                            f"远程停止响应: {status}",
                            {"status": status, "transaction_id": transaction_id},
                            response_time
                        )
                        return is_accepted
                    else:
                        self.record_test(
                            "RemoteStopTransaction",
                            False,
                            f"响应状态不符合 OCPP 标准: {status}",
                            {"response": data},
                            response_time
                        )
                        return False
                else:
                    self.record_test(
                        "RemoteStopTransaction",
                        False,
                        "响应格式不符合 OCPP 标准",
                        {"response": data},
                        response_time
                    )
                    return False
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.record_test(
                    "RemoteStopTransaction",
                    False,
                    f"HTTP {response.status_code}",
                    error_detail,
                    response_time
                )
                return False
        except Exception as e:
            self.record_test(
                "RemoteStopTransaction",
                False,
                f"请求失败: {e}",
                {"error": str(e)}
            )
            return False
    
    def test_reset(self, reset_type: str = "Soft") -> bool:
        """测试 Reset"""
        self.print_header("7. Reset - 重置充电桩")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "type": reset_type
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            print(f"⚠ 警告: 这将尝试重置充电桩 (类型: {reset_type})")
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/ocpp/reset",
                json=payload,
                timeout=15
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                data = result.get("data", {})
                
                if isinstance(data, dict):
                    status = data.get("status", "")
                    if status in ["Accepted", "Rejected"]:
                        is_accepted = status == "Accepted"
                        self.record_test(
                            "Reset",
                            is_accepted,
                            f"重置响应: {status}",
                            {"status": status, "reset_type": reset_type},
                            response_time
                        )
                        return is_accepted
                    else:
                        self.record_test(
                            "Reset",
                            False,
                            f"响应状态不符合 OCPP 标准: {status}",
                            {"response": data},
                            response_time
                        )
                        return False
                else:
                    self.record_test(
                        "Reset",
                        False,
                        "响应格式不符合 OCPP 标准",
                        {"response": data},
                        response_time
                    )
                    return False
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.record_test(
                    "Reset",
                    False,
                    f"HTTP {response.status_code}",
                    error_detail,
                    response_time
                )
                return False
        except Exception as e:
            self.record_test(
                "Reset",
                False,
                f"请求失败: {e}",
                {"error": str(e)}
            )
            return False
    
    def print_summary(self):
        """打印测试结果总结"""
        self.print_header("测试结果总结")
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["success"])
        failed = total - passed
        
        print(f"总测试数: {total}")
        print(f"通过: {passed} ({passed*100/total:.1f}%)" if total > 0 else "通过: 0")
        print(f"失败: {failed} ({failed*100/total:.1f}%)" if total > 0 else "失败: 0")
        print("\n详细结果:")
        for result in self.test_results:
            status = "✓" if result["success"] else "✗"
            print(f"  {status} {result['test_name']}: {result['message']}")
        
        # 保存报告
        report_filename = f"ocpp_test_report_{self.charge_point_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w', encoding='utf-8') as f:
            json.dump({
                "charge_point_id": self.charge_point_id,
                "server_url": self.server_url,
                "test_time": datetime.now().isoformat(),
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": failed
                },
                "results": self.test_results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n完整报告已保存到: {report_filename}")
    
    def run_all_tests(self, skip_destructive: bool = True):
        """运行所有测试"""
        print("\n" + "=" * 80)
        print("真实充电桩 OCPP 功能测试")
        print("=" * 80)
        print(f"服务器: {self.server_url}")
        print(f"充电桩ID: {self.charge_point_id}")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # 1. 检查连接
        if not self.check_connection():
            print("\n✗ 充电桩未连接，无法继续测试")
            self.print_summary()
            return
        
        # 2. GetConfiguration
        self.test_get_configuration()
        time.sleep(1)
        
        # 3. ChangeConfiguration (测试一个安全的配置项)
        self.test_change_configuration("HeartbeatInterval", "30")
        time.sleep(1)
        
        # 4. UnlockConnector
        self.test_unlock_connector(1)
        time.sleep(1)
        
        # 5. RemoteStartTransaction (可选，需要用户确认)
        if not skip_destructive:
            user_input = input("\n是否测试 RemoteStartTransaction? (y/N): ")
            if user_input.lower() == 'y':
                self.test_remote_start_transaction("TEST_TAG_001", 1)
                time.sleep(2)
                
                # 6. RemoteStopTransaction (如果有活动交易)
                user_input = input("\n是否测试 RemoteStopTransaction? (y/N): ")
                if user_input.lower() == 'y':
                    self.test_remote_stop_transaction()
                    time.sleep(1)
        
        # 7. Reset (可选，需要用户确认)
        if not skip_destructive:
            user_input = input("\n是否测试 Reset? (y/N): ")
            if user_input.lower() == 'y':
                self.test_reset("Soft")
        
        # 打印总结
        self.print_summary()


def main():
    parser = argparse.ArgumentParser(description="测试真实充电桩的 OCPP 功能")
    parser.add_argument("--server", type=str, default="http://47.236.134.99:9000", 
                       help="CSMS服务器URL (默认: http://47.236.134.99:9000)")
    parser.add_argument("--charge-point-id", type=str, 
                       help="充电桩ID (如果不提供，将列出所有已连接的充电桩)")
    parser.add_argument("--list", action="store_true", 
                       help="列出所有已连接的充电桩")
    parser.add_argument("--skip-destructive", action="store_true", default=True,
                       help="跳过可能影响充电桩状态的测试 (RemoteStartTransaction, Reset)")
    args = parser.parse_args()
    
    tester = RealChargerOCPPTester(args.server, args.charge_point_id)
    
    # 如果只是列出充电桩
    if args.list or not args.charge_point_id:
        chargers = tester.list_connected_chargers()
        if chargers and not args.charge_point_id:
            print(f"\n请使用 --charge-point-id 参数指定要测试的充电桩ID")
            print(f"例如: python {sys.argv[0]} --charge-point-id {chargers[0]}")
        return
    
    # 运行测试
    tester.run_all_tests(skip_destructive=args.skip_destructive)


if __name__ == "__main__":
    main()

