#!/usr/bin/env python3
#
# OCPP 1.6 协议验证脚本
# 用于验证真实充电桩的 OCPP 协议合规性
#

import argparse
import requests
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
import sys


class OCPPProtocolVerifier:
    """OCPP 协议验证器"""
    
    def __init__(self, server_url: str, charge_point_id: str):
        self.server_url = server_url.rstrip('/')
        self.charge_point_id = charge_point_id
        self.base_url = f"{self.server_url}/api/v1"
        self.test_results: List[Dict[str, Any]] = []
        
    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 80)
        print(f"测试: {title}")
        print("=" * 80)
    
    def record_test(self, test_name: str, success: bool, message: str, 
                    details: Optional[Dict] = None, response_time: Optional[float] = None):
        """记录测试结果"""
        result = {
            "test_name": test_name,
            "success": success,
            "message": message,
            "details": details,
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
    
    def check_connection(self) -> bool:
        """检查充电桩连接状态"""
        self.print_header("1. 检查充电桩连接状态")
        try:
            start_time = time.time()
            response = requests.get(
                f"{self.base_url}/chargers/{self.charge_point_id}",
                timeout=10
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                charger = response.json()
                self.record_test(
                    "连接检查",
                    True,
                    "充电桩已连接",
                    {
                        "id": charger.get('id'),
                        "vendor": charger.get('vendor'),
                        "model": charger.get('model'),
                        "status": charger.get('status'),
                        "last_seen": charger.get('last_seen')
                    },
                    response_time
                )
                return True
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
    
    def test_get_configuration(self) -> bool:
        """测试 GetConfiguration"""
        self.print_header("2. GetConfiguration - 获取配置")
        
        payload = {"chargePointId": self.charge_point_id}
        
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
                
                # 验证响应格式
                if isinstance(data, dict):
                    if "configurationKey" in data:
                        config_items = data.get("configurationKey", [])
                        self.record_test(
                            "GetConfiguration",
                            success,
                            f"获取配置成功，共 {len(config_items)} 项",
                            {
                                "config_count": len(config_items),
                                "sample_configs": config_items[:3] if config_items else []
                            },
                            response_time
                        )
                        return success
                    else:
                        # 可能是错误响应
                        self.record_test(
                            "GetConfiguration",
                            False,
                            "响应格式不符合 OCPP 标准（缺少 configurationKey）",
                            {"response": data},
                            response_time
                        )
                        return False
                else:
                    self.record_test(
                        "GetConfiguration",
                        False,
                        "响应格式不符合 OCPP 标准（不是对象）",
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
    
    def test_change_configuration(self) -> bool:
        """测试 ChangeConfiguration"""
        self.print_header("3. ChangeConfiguration - 更改配置")
        
        # 尝试更改一个常见的配置项
        payload = {
            "chargePointId": self.charge_point_id,
            "key": "HeartbeatInterval",
            "value": "300"
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
                
                # 验证响应格式
                if isinstance(data, dict):
                    status = data.get("status", "")
                    if status in ["Accepted", "Rejected", "NotSupported", "RebootRequired"]:
                        self.record_test(
                            "ChangeConfiguration",
                            success,
                            f"配置更改响应: {status}",
                            {"status": status, "response": data},
                            response_time
                        )
                        return success
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
    
    def test_unlock_connector(self) -> bool:
        """测试 UnlockConnector"""
        self.print_header("4. UnlockConnector - 解锁连接器")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "connectorId": 1
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
                
                # 验证响应格式
                if isinstance(data, dict):
                    status = data.get("status", "")
                    if status in ["Unlocked", "UnlockFailed", "NotSupported", "NotSupported"]:
                        self.record_test(
                            "UnlockConnector",
                            success,
                            f"解锁响应: {status}",
                            {"status": status, "response": data},
                            response_time
                        )
                        return success
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
    
    def query_charging_session(self, transaction_id: int) -> Optional[Dict[str, Any]]:
        """查询充电会话数据"""
        try:
            response = requests.get(
                f"{self.base_url}/transactions",
                params={
                    "charge_point_id": self.charge_point_id
                },
                timeout=10
            )
            
            if response.status_code == 200:
                transactions = response.json()
                # 查找匹配的交易ID
                for tx in transactions:
                    if tx.get("transaction_id") == transaction_id:
                        return tx
            return None
        except Exception as e:
            print(f"查询充电会话失败: {e}")
            return None
    
    def query_order(self, transaction_id: int) -> Optional[Dict[str, Any]]:
        """查询订单数据（通过交易ID关联）"""
        try:
            # 先通过交易ID找到充电会话
            session = self.query_charging_session(transaction_id)
            if not session:
                return None
            
            # 查询订单（通过充电桩ID和时间范围）
            response = requests.get(
                f"{self.base_url}/orders",
                params={
                    "charge_point_id": self.charge_point_id,
                    "limit": 10
                },
                timeout=10
            )
            
            if response.status_code == 200:
                orders = response.json()
                # 查找与交易相关的订单（通过时间匹配或session_id）
                session_id = session.get("id")
                for order in orders:
                    # 如果订单有session_id，直接匹配
                    if order.get("session_id") == session_id:
                        return order
                    # 或者通过时间范围匹配（订单创建时间在会话时间范围内）
                    order_time = order.get("created_at")
                    session_start = session.get("start_time")
                    session_end = session.get("end_time")
                    if order_time and session_start:
                        if session_end:
                            if session_start <= order_time <= session_end:
                                return order
                        else:
                            # 如果会话未结束，匹配开始时间之后的订单
                            if order_time >= session_start:
                                return order
            return None
        except Exception as e:
            print(f"查询订单失败: {e}")
            return None
    
    def get_active_transaction(self) -> Optional[int]:
        """获取正在进行的交易ID"""
        try:
            # 查询正在进行的交易
            response = requests.get(
                f"{self.base_url}/transactions",
                params={
                    "charge_point_id": self.charge_point_id,
                    "status": "active"
                },
                timeout=10
            )
            
            if response.status_code == 200:
                transactions = response.json()
                # 查找状态为 active 或 charging 的交易
                for tx in transactions:
                    if tx.get("status") in ["active", "charging"]:
                        transaction_id = tx.get("transaction_id")
                        if transaction_id:
                            return transaction_id
                
                # 如果没有找到 active 状态，尝试查找最新的未结束交易
                if transactions:
                    latest = transactions[0]
                    if latest.get("end_time") is None:
                        return latest.get("transaction_id")
            
            return None
        except Exception as e:
            print(f"获取交易信息失败: {e}")
            return None
    
    def test_remote_start_transaction(self) -> bool:
        """测试 RemoteStartTransaction"""
        self.print_header("5. RemoteStartTransaction - 远程启动充电")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "idTag": "TEST_OCPP_VERIFY_001",
            "connectorId": 1
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
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
                
                # 验证响应格式
                if isinstance(data, dict):
                    status = data.get("status", "")
                    if status in ["Accepted", "Rejected"]:
                        self.record_test(
                            "RemoteStartTransaction",
                            success,
                            f"远程启动响应: {status}",
                            {"status": status, "response": data},
                            response_time
                        )
                        return success
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
                
                # 验证响应格式
                if isinstance(data, dict):
                    status = data.get("status", "")
                    if status in ["Accepted", "Rejected"]:
                        # 收到响应后，查询数据库中的订单和充电数据
                        print("\n" + "=" * 80)
                        print("查询数据库中的订单和充电数据...")
                        print("=" * 80)
                        
                        # 等待一下，让数据库更新
                        time.sleep(2)
                        
                        # 查询充电会话数据
                        session_data = self.query_charging_session(transaction_id)
                        if session_data:
                            print("\n充电会话数据:")
                            print(f"  交易ID: {session_data.get('transaction_id')}")
                            print(f"  状态: {session_data.get('status')}")
                            print(f"  开始时间: {session_data.get('start_time')}")
                            print(f"  结束时间: {session_data.get('end_time')}")
                            print(f"  电量: {session_data.get('energy_kwh', 0):.2f} kWh")
                            print(f"  时长: {session_data.get('duration_minutes', 0):.1f} 分钟")
                            print(f"  用户标签: {session_data.get('id_tag')}")
                        else:
                            print("\n未找到充电会话数据")
                        
                        # 查询订单数据
                        order_data = self.query_order(transaction_id)
                        if order_data:
                            print("\n订单数据:")
                            print(f"  订单ID: {order_data.get('id')}")
                            print(f"  状态: {order_data.get('status')}")
                            print(f"  金额: {order_data.get('amount', 0):.2f} 元")
                            print(f"  创建时间: {order_data.get('created_at')}")
                            print(f"  支付时间: {order_data.get('paid_at', '未支付')}")
                        else:
                            print("\n未找到订单数据")
                        
                        print("=" * 80)
                        
                        self.record_test(
                            "RemoteStopTransaction",
                            success,
                            f"远程停止响应: {status}",
                            {
                                "status": status,
                                "transaction_id": transaction_id,
                                "response": data,
                                "session_data": session_data,
                                "order_data": order_data
                            },
                            response_time
                        )
                        return success
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
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 80)
        print("OCPP 协议验证报告")
        print("=" * 80)
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"服务器: {self.server_url}")
        print(f"充电桩ID: {self.charge_point_id}")
        print("=" * 80)
        
        passed = sum(1 for r in self.test_results if r["success"])
        total = len(self.test_results)
        
        print(f"\n测试结果: {passed}/{total} 通过")
        print("\n详细结果:")
        print("-" * 80)
        
        for result in self.test_results:
            status = "✓" if result["success"] else "✗"
            print(f"{status} {result['test_name']}: {result['message']}")
            if result.get("response_time"):
                print(f"  响应时间: {result['response_time']:.3f} 秒")
        
        print("\n" + "=" * 80)
        print("OCPP 协议合规性评估")
        print("=" * 80)
        
        # 评估合规性
        critical_tests = ["连接检查", "GetConfiguration", "RemoteStartTransaction"]
        critical_passed = all(
            any(r["test_name"] == test and r["success"] for r in self.test_results)
            for test in critical_tests
        )
        
        if critical_passed and passed == total:
            print("✓ 完全符合 OCPP 1.6 协议标准")
        elif critical_passed:
            print("⚠ 基本符合 OCPP 1.6 协议标准（部分功能未通过）")
        else:
            print("✗ 不符合 OCPP 1.6 协议标准（关键功能失败）")
        
        print("=" * 80)
        
        # 保存报告到文件
        report_file = f"ocpp_verification_report_{self.charge_point_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                "test_time": datetime.now().isoformat(),
                "server_url": self.server_url,
                "charge_point_id": self.charge_point_id,
                "summary": {
                    "passed": passed,
                    "total": total,
                    "pass_rate": f"{passed/total*100:.1f}%" if total > 0 else "0%"
                },
                "results": self.test_results
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n详细报告已保存到: {report_file}")
    
    def show_menu(self):
        """显示测试菜单"""
        print("\n" + "=" * 80)
        print("OCPP 1.6 协议验证测试 - 交互式菜单")
        print("=" * 80)
        print(f"服务器: {self.server_url}")
        print(f"充电桩ID: {self.charge_point_id}")
        print("=" * 80)
        print("\n请选择要运行的测试:")
        print("  1. 检查充电桩连接状态")
        print("  2. GetConfiguration - 获取配置")
        print("  3. ChangeConfiguration - 更改配置")
        print("  4. UnlockConnector - 解锁连接器")
        print("  5. RemoteStartTransaction - 远程启动充电")
        print("  6. RemoteStopTransaction - 远程停止充电（自动查找交易ID）")
        print("  a. 运行所有测试")
        print("  r. 查看测试报告")
        print("  q. 退出")
        print("=" * 80)
    
    def run_interactive(self):
        """交互式运行测试"""
        print("\n" + "=" * 80)
        print("OCPP 1.6 协议验证测试 - 交互式模式")
        print("=" * 80)
        print(f"服务器: {self.server_url}")
        print(f"充电桩ID: {self.charge_point_id}")
        print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        while True:
            self.show_menu()
            choice = input("\n请输入选项 (1-6/a/r/q): ").strip().lower()
            
            if choice == 'q':
                print("\n退出测试")
                break
            elif choice == 'r':
                self.generate_report()
                input("\n按 Enter 键继续...")
            elif choice == 'a':
                print("\n运行所有测试...")
                if not self.check_connection():
                    print("\n✗ 充电桩未连接，无法继续测试")
                    input("\n按 Enter 键继续...")
                    continue
                
                self.test_get_configuration()
                time.sleep(1)
                
                self.test_change_configuration()
                time.sleep(1)
                
                self.test_unlock_connector()
                time.sleep(1)
                
                self.test_remote_start_transaction()
                time.sleep(1)
                
                # 尝试停止充电（如果有正在进行的交易）
                transaction_id = self.get_active_transaction()
                if transaction_id:
                    print(f"\n检测到正在进行的交易 (ID: {transaction_id})，尝试停止...")
                    self.test_remote_stop_transaction(transaction_id)
                else:
                    print("\n未检测到正在进行的交易，跳过停止测试")
                
                print("\n✓ 所有测试完成")
                input("\n按 Enter 键继续...")
            elif choice == '1':
                self.check_connection()
                input("\n按 Enter 键继续...")
            elif choice == '2':
                self.test_get_configuration()
                input("\n按 Enter 键继续...")
            elif choice == '3':
                self.test_change_configuration()
                input("\n按 Enter 键继续...")
            elif choice == '4':
                self.test_unlock_connector()
                input("\n按 Enter 键继续...")
            elif choice == '5':
                self.test_remote_start_transaction()
                input("\n按 Enter 键继续...")
            elif choice == '6':
                # 先尝试自动查找交易ID
                transaction_id = self.get_active_transaction()
                if transaction_id:
                    print(f"自动找到交易ID: {transaction_id}")
                    use_auto = input("使用此交易ID? (y/n，n可手动输入): ").strip().lower()
                    if use_auto != 'y':
                        tx_id_input = input("请输入交易ID (直接回车跳过): ").strip()
                        transaction_id = int(tx_id_input) if tx_id_input.isdigit() else None
                else:
                    print("未找到正在进行的交易")
                    tx_id_input = input("请输入交易ID (直接回车跳过): ").strip()
                    transaction_id = int(tx_id_input) if tx_id_input.isdigit() else None
                
                self.test_remote_stop_transaction(transaction_id)
                input("\n按 Enter 键继续...")
            else:
                print("\n✗ 无效选项，请重新选择")
                time.sleep(1)
        
        # 退出时生成报告
        if self.test_results:
            print("\n生成最终测试报告...")
            self.generate_report()


def main():
    parser = argparse.ArgumentParser(
        description="OCPP 1.6 协议验证脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本测试
  python verify_ocpp_protocol.py \\
    --server http://47.236.134.99:9000 \\
    --charge-point-id 861076087029615
  
  # 包含重置测试（会触发充电桩重置）
  python verify_ocpp_protocol.py \\
    --server http://47.236.134.99:9000 \\
    --charge-point-id 861076087029615 \\
    --include-reset
        """
    )
    
    parser.add_argument(
        "--server",
        type=str,
        default="http://47.236.134.99:9000",
        help="CSMS 服务器地址"
    )
    parser.add_argument(
        "--charge-point-id",
        type=str,
        required=True,
        help="充电桩ID（序列号）"
    )
    
    args = parser.parse_args()
    
    verifier = OCPPProtocolVerifier(args.server, args.charge_point_id)
    verifier.run_interactive()


if __name__ == "__main__":
    main()

