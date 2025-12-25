#!/usr/bin/env python3
#
# OCPP 1.6 规范符合性测试脚本
# 全面测试充电桩的 OCPP 功能实现和响应规范符合性
#

import argparse
import requests
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
import sys


class OCPPComplianceTester:
    """OCPP 规范符合性测试器"""
    
    # OCPP 1.6 标准消息类型
    CALL = 2
    CALLRESULT = 3
    CALLERROR = 4
    
    def __init__(self, server_url: str, charge_point_id: str):
        self.server_url = server_url.rstrip('/')
        self.charge_point_id = charge_point_id
        self.base_url = f"{self.server_url}/api/v1"
        self.test_results: List[Dict[str, Any]] = []
        self.compliance_issues: List[Dict[str, Any]] = []
        
    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 80)
        print(f"{title}")
        print("=" * 80)
    
    def print_section(self, title: str):
        """打印小节标题"""
        print(f"\n{'─' * 80}")
        print(f" {title}")
        print(f"{'─' * 80}")
    
    def record_test(self, test_name: str, success: bool, message: str, 
                    details: Optional[Dict] = None, response_time: Optional[float] = None,
                    compliance_issues: Optional[List[str]] = None):
        """记录测试结果"""
        result = {
            "test_name": test_name,
            "success": success,
            "message": message,
            "details": details or {},
            "response_time": response_time,
            "compliance_issues": compliance_issues or [],
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        if compliance_issues:
            self.compliance_issues.extend([
                {"test": test_name, "issue": issue} for issue in compliance_issues
            ])
        
        status = "✓ 通过" if success else "✗ 失败"
        print(f"{status}: {message}")
        if details:
            print(f"详细信息: {json.dumps(details, ensure_ascii=False, indent=2)}")
        if compliance_issues:
            print(f"⚠️  规范问题:")
            for issue in compliance_issues:
                print(f"   - {issue}")
        if response_time:
            print(f"响应时间: {response_time:.3f} 秒")
    
    def check_connection(self) -> bool:
        """检查充电桩连接状态"""
        self.print_header("1. 连接状态检查")
        try:
            start_time = time.time()
            response = requests.get(
                f"{self.base_url}/chargers/{self.charge_point_id}",
                timeout=10
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                charger = response.json()
                issues = []
                
                # 检查必要字段
                required_fields = ['id', 'status']
                for field in required_fields:
                    if field not in charger:
                        issues.append(f"缺少必要字段: {field}")
                
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
                    response_time,
                    issues
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
        """测试 GetConfiguration - 验证响应格式"""
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
                
                issues = []
                
                # 验证响应结构
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                # 验证 configurationKey 字段（OCPP 1.6 标准）
                if "configurationKey" in data:
                    config_list = data["configurationKey"]
                    if not isinstance(config_list, list):
                        issues.append("configurationKey 应为数组类型")
                    else:
                        # 验证每个配置项的结构
                        for i, item in enumerate(config_list[:5]):  # 检查前5个
                            if not isinstance(item, dict):
                                issues.append(f"配置项 {i} 应为对象类型")
                            else:
                                if "key" not in item:
                                    issues.append(f"配置项 {i} 缺少 key 字段")
                                if "value" not in item:
                                    issues.append(f"配置项 {i} 缺少 value 字段（可为 null）")
                
                # 验证 unknownKey 字段（如果存在）
                if "unknownKey" in data:
                    if not isinstance(data["unknownKey"], list):
                        issues.append("unknownKey 应为数组类型")
                
                self.record_test(
                    "GetConfiguration",
                    success and len(issues) == 0,
                    f"获取配置{'成功' if success else '失败'}",
                    {
                        "response": data,
                        "config_count": len(data.get("configurationKey", [])),
                        "unknown_keys": data.get("unknownKey", [])
                    },
                    response_time,
                    issues
                )
                return success and len(issues) == 0
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
        """测试 ChangeConfiguration - 验证响应格式"""
        self.print_header("3. ChangeConfiguration - 更改配置")
        
        # 测试更改 HeartbeatInterval（通常可写）
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
                
                issues = []
                
                # 验证响应结构
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                # 验证 status 字段（OCPP 1.6 标准）
                if "status" in data:
                    status = data["status"]
                    valid_statuses = ["Accepted", "Rejected", "NotSupported", "RebootRequired"]
                    if status not in valid_statuses:
                        issues.append(f"status 值 '{status}' 不符合 OCPP 1.6 规范，应为: {valid_statuses}")
                else:
                    issues.append("缺少 status 字段（OCPP 1.6 必需）")
                
                self.record_test(
                    "ChangeConfiguration",
                    success and len(issues) == 0,
                    f"更改配置{'成功' if success else '失败'}，状态: {data.get('status', 'N/A')}",
                    {
                        "response": data,
                        "key": payload["key"],
                        "value": payload["value"]
                    },
                    response_time,
                    issues
                )
                return success and len(issues) == 0
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
        """测试 UnlockConnector - 验证响应格式"""
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
                
                issues = []
                
                # 验证响应结构
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                # 验证 status 字段（OCPP 1.6 标准）
                if "status" in data:
                    status = data["status"]
                    valid_statuses = ["Unlocked", "UnlockFailed", "NotSupported"]
                    if status not in valid_statuses:
                        issues.append(f"status 值 '{status}' 不符合 OCPP 1.6 规范，应为: {valid_statuses}")
                else:
                    issues.append("缺少 status 字段（OCPP 1.6 必需）")
                
                self.record_test(
                    "UnlockConnector",
                    success and len(issues) == 0,
                    f"解锁连接器{'成功' if success else '失败'}，状态: {data.get('status', 'N/A')}",
                    {
                        "response": data,
                        "connector_id": payload["connectorId"]
                    },
                    response_time,
                    issues
                )
                return success and len(issues) == 0
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
    
    def test_remote_start_transaction(self) -> bool:
        """测试 RemoteStartTransaction - 验证响应格式"""
        self.print_header("5. RemoteStartTransaction - 远程启动充电")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "idTag": "TEST_TAG_001",
            "connectorId": 1
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            print("⚠️  注意：这将实际启动充电！")
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
                
                issues = []
                
                # 验证响应结构
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                # 验证 status 字段（OCPP 1.6 标准）
                if "status" in data:
                    status = data["status"]
                    valid_statuses = ["Accepted", "Rejected"]
                    if status not in valid_statuses:
                        issues.append(f"status 值 '{status}' 不符合 OCPP 1.6 规范，应为: {valid_statuses}")
                else:
                    issues.append("缺少 status 字段（OCPP 1.6 必需）")
                
                self.record_test(
                    "RemoteStartTransaction",
                    success and len(issues) == 0,
                    f"远程启动充电{'成功' if success else '失败'}，状态: {data.get('status', 'N/A')}",
                    {
                        "response": data,
                        "id_tag": payload["idTag"],
                        "connector_id": payload["connectorId"]
                    },
                    response_time,
                    issues
                )
                return success and len(issues) == 0
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
        except:
            pass
        return None
    
    def test_remote_stop_transaction(self, transaction_id: Optional[int] = None) -> bool:
        """测试 RemoteStopTransaction - 验证响应格式"""
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
                        sessions = response.json()
                        if sessions:
                            transaction_id = sessions[0].get("transaction_id")
                            print(f"找到最新交易ID: {transaction_id}")
                except:
                    pass
        
        if transaction_id is None:
            self.record_test(
                "RemoteStopTransaction",
                False,
                "未找到交易ID，无法停止",
                {"message": "请先启动一个充电交易"}
            )
            return False
        
        payload = {
            "chargePointId": self.charge_point_id,
            "transactionId": transaction_id
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            print("⚠️  注意：这将实际停止充电！")
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
                
                issues = []
                
                # 验证响应结构
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                # 验证 status 字段（OCPP 1.6 标准）
                if "status" in data:
                    status = data["status"]
                    valid_statuses = ["Accepted", "Rejected"]
                    if status not in valid_statuses:
                        issues.append(f"status 值 '{status}' 不符合 OCPP 1.6 规范，应为: {valid_statuses}")
                else:
                    issues.append("缺少 status 字段（OCPP 1.6 必需）")
                
                self.record_test(
                    "RemoteStopTransaction",
                    success and len(issues) == 0,
                    f"远程停止充电{'成功' if success else '失败'}，状态: {data.get('status', 'N/A')}",
                    {
                        "response": data,
                        "transaction_id": transaction_id
                    },
                    response_time,
                    issues
                )
                return success and len(issues) == 0
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
    
    def test_reset(self) -> bool:
        """测试 Reset - 验证响应格式"""
        self.print_header("7. Reset - 重置充电桩")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "type": "Hard"
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            print("⚠️  警告：这将触发充电桩硬重置！")
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
                
                issues = []
                
                # 验证响应结构
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                # 验证 status 字段（OCPP 1.6 标准）
                if "status" in data:
                    status = data["status"]
                    valid_statuses = ["Accepted", "Rejected"]
                    if status not in valid_statuses:
                        issues.append(f"status 值 '{status}' 不符合 OCPP 1.6 规范，应为: {valid_statuses}")
                else:
                    issues.append("缺少 status 字段（OCPP 1.6 必需）")
                
                self.record_test(
                    "Reset",
                    success and len(issues) == 0,
                    f"重置充电桩{'成功' if success else '失败'}，状态: {data.get('status', 'N/A')}",
                    {
                        "response": data,
                        "reset_type": payload["type"]
                    },
                    response_time,
                    issues
                )
                return success and len(issues) == 0
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
    
    def run_all_tests(self, include_reset: bool = False):
        """运行所有测试"""
        self.print_header("OCPP 1.6 规范符合性测试")
        print(f"充电桩ID: {self.charge_point_id}")
        print(f"服务器: {self.server_url}")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"包含重置测试: {'是' if include_reset else '否'}")
        
        # 1. 连接检查
        if not self.check_connection():
            print("\n✗ 充电桩未连接，无法继续测试")
            return
        
        # 2. GetConfiguration
        self.test_get_configuration()
        time.sleep(1)
        
        # 3. ChangeConfiguration
        self.test_change_configuration()
        time.sleep(1)
        
        # 4. UnlockConnector
        self.test_unlock_connector()
        time.sleep(1)
        
        # 5. RemoteStartTransaction
        self.test_remote_start_transaction()
        time.sleep(2)  # 等待充电启动
        
        # 6. RemoteStopTransaction
        self.test_remote_stop_transaction()
        time.sleep(1)
        
        # 7. Reset (可选)
        if include_reset:
            self.test_reset()
        
        # 生成报告
        self.generate_report()
    
    def generate_report(self):
        """生成测试报告"""
        self.print_header("测试报告")
        
        # 统计
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        failed_tests = total_tests - passed_tests
        total_issues = len(self.compliance_issues)
        
        print(f"\n测试统计:")
        print(f"  总测试数: {total_tests}")
        print(f"  通过: {passed_tests}")
        print(f"  失败: {failed_tests}")
        print(f"  规范问题: {total_issues}")
        print(f"  通过率: {passed_tests/total_tests*100:.1f}%")
        
        # 详细结果
        print(f"\n详细结果:")
        for result in self.test_results:
            status = "✓" if result["success"] else "✗"
            print(f"  {status} {result['test_name']}: {result['message']}")
            if result.get("compliance_issues"):
                for issue in result["compliance_issues"]:
                    print(f"    ⚠️  {issue}")
        
        # 规范问题汇总
        if self.compliance_issues:
            print(f"\n规范问题汇总:")
            for issue_info in self.compliance_issues:
                print(f"  - [{issue_info['test']}] {issue_info['issue']}")
        
        # 保存报告
        report_data = {
            "charge_point_id": self.charge_point_id,
            "server_url": self.server_url,
            "test_time": datetime.now().isoformat(),
            "summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "compliance_issues": total_issues,
                "pass_rate": passed_tests/total_tests*100 if total_tests > 0 else 0
            },
            "test_results": self.test_results,
            "compliance_issues": self.compliance_issues
        }
        
        report_filename = f"ocpp_compliance_report_{self.charge_point_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n完整报告已保存到: {report_filename}")
        
        # 输出建议
        if total_issues > 0:
            print(f"\n建议:")
            print(f"  1. 检查服务器日志，确认充电桩发送的消息格式")
            print(f"  2. 验证充电桩的 OCPP 1.6 实现是否完整")
            print(f"  3. 参考 OCPP 1.6 规范文档修复规范问题")


def main():
    parser = argparse.ArgumentParser(
        description="OCPP 1.6 规范符合性测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本测试
  python test_ocpp_compliance.py \\
    --server http://47.236.134.99:9000 \\
    --charge-point-id 861076087029615
  
  # 包含重置测试
  python test_ocpp_compliance.py \\
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
    parser.add_argument(
        "--include-reset",
        action="store_true",
        help="包含 Reset 测试（会触发充电桩重置）"
    )
    
    args = parser.parse_args()
    
    tester = OCPPComplianceTester(args.server, args.charge_point_id)
    tester.run_all_tests(include_reset=args.include_reset)


if __name__ == "__main__":
    main()

