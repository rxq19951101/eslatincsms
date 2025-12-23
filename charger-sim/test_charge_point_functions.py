#!/usr/bin/env python3
#
# 测试已连接充电桩的所有基本 OCPP 功能
# 通过 API 发送 OCPP 请求并验证响应
#

import argparse
import requests
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional


class ChargePointTester:
    """充电桩功能测试器"""
    
    def __init__(self, server_url: str, charge_point_id: str):
        self.server_url = server_url.rstrip('/')
        self.charge_point_id = charge_point_id
        self.base_url = f"{self.server_url}/api/v1"
        
    def print_header(self, title: str):
        """打印测试标题"""
        print("\n" + "=" * 80)
        print(f"测试: {title}")
        print("=" * 80)
    
    def print_result(self, success: bool, message: str, details: Optional[Dict] = None):
        """打印测试结果"""
        status = "✓ 成功" if success else "✗ 失败"
        print(f"{status}: {message}")
        if details:
            print(f"详细信息: {json.dumps(details, ensure_ascii=False, indent=2)}")
    
    def check_connection(self) -> bool:
        """检查充电桩是否连接"""
        self.print_header("检查充电桩连接状态")
        try:
            response = requests.get(
                f"{self.base_url}/chargers/{self.charge_point_id}",
                timeout=5
            )
            if response.status_code == 200:
                charger = response.json()
                print(f"✓ 充电桩已连接")
                print(f"  ID: {charger.get('id')}")
                print(f"  厂商: {charger.get('vendor', 'N/A')}")
                print(f"  型号: {charger.get('model', 'N/A')}")
                print(f"  状态: {charger.get('status', 'N/A')}")
                return True
            else:
                print(f"✗ 充电桩未找到 (HTTP {response.status_code})")
                return False
        except Exception as e:
            print(f"✗ 检查连接失败: {e}")
            return False
    
    def test_remote_start_transaction(self, id_tag: str = "TEST_TAG_001", connector_id: int = 1) -> bool:
        """测试远程启动充电"""
        self.print_header("RemoteStartTransaction - 远程启动充电")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "idTag": id_tag,
            "connectorId": connector_id
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            response = requests.post(
                f"{self.base_url}/ocpp/remote-start-transaction",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                message = result.get("message", "")
                details = result.get("details", {})
                
                self.print_result(success, message, details)
                return success
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.print_result(False, f"HTTP {response.status_code}", error_detail)
                return False
        except Exception as e:
            self.print_result(False, f"请求失败: {e}")
            return False
    
    def test_remote_stop_transaction(self, transaction_id: int) -> bool:
        """测试远程停止充电"""
        self.print_header("RemoteStopTransaction - 远程停止充电")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "transactionId": transaction_id
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            response = requests.post(
                f"{self.base_url}/ocpp/remote-stop-transaction",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                message = result.get("message", "")
                details = result.get("details", {})
                
                self.print_result(success, message, details)
                return success
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.print_result(False, f"HTTP {response.status_code}", error_detail)
                return False
        except Exception as e:
            self.print_result(False, f"请求失败: {e}")
            return False
    
    def test_get_configuration(self, keys: Optional[list] = None) -> bool:
        """测试获取配置"""
        self.print_header("GetConfiguration - 获取配置")
        
        payload = {
            "chargePointId": self.charge_point_id
        }
        if keys:
            payload["keys"] = keys
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            response = requests.post(
                f"{self.base_url}/ocpp/get-configuration",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                message = result.get("message", "")
                details = result.get("details", {})
                
                self.print_result(success, message, details)
                if success and details:
                    config = details.get("configurationKey", [])
                    if config:
                        print(f"\n配置项数量: {len(config)}")
                        for item in config[:5]:  # 只显示前5个
                            print(f"  - {item.get('key', 'N/A')}: {item.get('value', 'N/A')}")
                return success
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.print_result(False, f"HTTP {response.status_code}", error_detail)
                return False
        except Exception as e:
            self.print_result(False, f"请求失败: {e}")
            return False
    
    def test_change_configuration(self, key: str, value: str) -> bool:
        """测试更改配置"""
        self.print_header("ChangeConfiguration - 更改配置")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "key": key,
            "value": value
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            response = requests.post(
                f"{self.base_url}/ocpp/change-configuration",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                message = result.get("message", "")
                details = result.get("details", {})
                
                self.print_result(success, message, details)
                return success
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.print_result(False, f"HTTP {response.status_code}", error_detail)
                return False
        except Exception as e:
            self.print_result(False, f"请求失败: {e}")
            return False
    
    def test_reset(self, reset_type: str = "Soft") -> bool:
        """测试重置充电桩"""
        self.print_header(f"Reset - 重置充电桩 ({reset_type})")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "type": reset_type
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            print(f"⚠️  警告: 这将重置充电桩，可能导致充电中断！")
            response = requests.post(
                f"{self.base_url}/ocpp/reset",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                message = result.get("message", "")
                details = result.get("details", {})
                
                self.print_result(success, message, details)
                return success
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.print_result(False, f"HTTP {response.status_code}", error_detail)
                return False
        except Exception as e:
            self.print_result(False, f"请求失败: {e}")
            return False
    
    def test_unlock_connector(self, connector_id: int = 1) -> bool:
        """测试解锁连接器"""
        self.print_header("UnlockConnector - 解锁连接器")
        
        payload = {
            "chargePointId": self.charge_point_id,
            "connectorId": connector_id
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            response = requests.post(
                f"{self.base_url}/ocpp/unlock-connector",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                message = result.get("message", "")
                details = result.get("details", {})
                
                self.print_result(success, message, details)
                return success
            else:
                error_detail = response.text
                try:
                    error_detail = response.json()
                except:
                    pass
                self.print_result(False, f"HTTP {response.status_code}", error_detail)
                return False
        except Exception as e:
            self.print_result(False, f"请求失败: {e}")
            return False
    
    def test_change_availability(self, connector_id: int = 1, availability_type: str = "Inoperative") -> bool:
        """测试更改可用性"""
        self.print_header(f"ChangeAvailability - 更改可用性 ({availability_type})")
        
        # 注意：这个 API 可能在不同的端点
        payload = {
            "chargePointId": self.charge_point_id,
            "connectorId": connector_id,
            "type": availability_type
        }
        
        try:
            print(f"发送请求: {json.dumps(payload, ensure_ascii=False)}")
            # 尝试不同的端点
            endpoints = [
                f"{self.base_url}/ocpp/change-availability",
                f"{self.base_url}/ocpp/changeAvailability",
            ]
            
            for endpoint in endpoints:
                try:
                    response = requests.post(endpoint, json=payload, timeout=10)
                    if response.status_code == 200:
                        result = response.json()
                        success = result.get("success", False)
                        message = result.get("message", "")
                        details = result.get("details", {})
                        self.print_result(success, message, details)
                        return success
                except:
                    continue
            
            self.print_result(False, "未找到可用的端点")
            return False
        except Exception as e:
            self.print_result(False, f"请求失败: {e}")
            return False
    
    def run_all_tests(self, skip_reset: bool = True, skip_availability: bool = True):
        """运行所有测试"""
        print("\n" + "=" * 80)
        print("充电桩功能测试套件")
        print("=" * 80)
        print(f"服务器: {self.server_url}")
        print(f"充电桩ID: {self.charge_point_id}")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        results = {}
        
        # 1. 检查连接
        results["连接检查"] = self.check_connection()
        if not results["连接检查"]:
            print("\n✗ 充电桩未连接，无法继续测试")
            return results
        
        time.sleep(1)
        
        # 2. 获取配置
        results["获取配置"] = self.test_get_configuration()
        time.sleep(1)
        
        # 3. 更改配置（测试配置）
        results["更改配置"] = self.test_change_configuration("HeartbeatInterval", "30")
        time.sleep(1)
        
        # 4. 解锁连接器
        results["解锁连接器"] = self.test_unlock_connector(connector_id=1)
        time.sleep(1)
        
        # 5. 远程启动充电
        results["远程启动充电"] = self.test_remote_start_transaction(
            id_tag="TEST_TAG_001",
            connector_id=1
        )
        time.sleep(2)
        
        # 6. 远程停止充电（需要 transaction_id）
        # 注意：这里需要从启动充电的响应中获取 transaction_id
        # 暂时跳过，或者可以手动指定
        print("\n提示: 远程停止充电需要 transaction_id，请从启动充电的响应中获取")
        
        # 7. 更改可用性（可选，可能影响充电桩状态）
        if not skip_availability:
            results["更改可用性"] = self.test_change_availability(
                connector_id=1,
                availability_type="Inoperative"
            )
            time.sleep(1)
        
        # 8. 重置（危险操作，默认跳过）
        if not skip_reset:
            results["重置"] = self.test_reset(reset_type="Soft")
            time.sleep(2)
        
        # 打印总结
        print("\n" + "=" * 80)
        print("测试结果总结")
        print("=" * 80)
        for test_name, success in results.items():
            status = "✓ 通过" if success else "✗ 失败"
            print(f"{test_name}: {status}")
        
        passed = sum(1 for s in results.values() if s)
        total = len(results)
        print(f"\n总计: {passed}/{total} 测试通过")
        print("=" * 80)
        
        return results


def main():
    parser = argparse.ArgumentParser(
        description="测试已连接充电桩的所有基本 OCPP 功能",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行所有测试（跳过危险操作）
  python test_charge_point_functions.py \\
    --server http://47.236.134.99:9000 \\
    --charge-point-id 861076087029615
  
  # 运行所有测试（包括重置）
  python test_charge_point_functions.py \\
    --server http://47.236.134.99:9000 \\
    --charge-point-id 861076087029615 \\
    --include-reset
  
  # 只测试特定功能
  python test_charge_point_functions.py \\
    --server http://47.236.134.99:9000 \\
    --charge-point-id 861076087029615 \\
    --test get-configuration
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
        default="861076087029615",
        help="充电桩ID"
    )
    parser.add_argument(
        "--test",
        type=str,
        choices=["all", "connection", "get-config", "change-config", "unlock", "start", "stop", "reset"],
        default="all",
        help="要运行的测试"
    )
    parser.add_argument(
        "--include-reset",
        action="store_true",
        help="包含重置测试（危险操作）"
    )
    parser.add_argument(
        "--include-availability",
        action="store_true",
        help="包含更改可用性测试"
    )
    
    args = parser.parse_args()
    
    tester = ChargePointTester(args.server, args.charge_point_id)
    
    if args.test == "all":
        tester.run_all_tests(
            skip_reset=not args.include_reset,
            skip_availability=not args.include_availability
        )
    elif args.test == "connection":
        tester.check_connection()
    elif args.test == "get-config":
        tester.test_get_configuration()
    elif args.test == "change-config":
        tester.test_change_configuration("HeartbeatInterval", "30")
    elif args.test == "unlock":
        tester.test_unlock_connector(1)
    elif args.test == "start":
        tester.test_remote_start_transaction("TEST_TAG_001", 1)
    elif args.test == "stop":
        print("需要 transaction_id，请使用 --transaction-id 参数")
    elif args.test == "reset":
        tester.test_reset("Soft")


if __name__ == "__main__":
    main()

