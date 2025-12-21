#!/usr/bin/env python3
#
# 充电桩功能测试脚本
# 用于测试已接入充电桩的所有 OCPP 功能
#

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

try:
    import requests
except ImportError:
    print("错误: requests 库未安装，请运行: pip install requests")
    sys.exit(1)


class TestResult(Enum):
    """测试结果枚举"""
    PASS = "✓ PASS"
    FAIL = "✗ FAIL"
    SKIP = "⊘ SKIP"
    WARN = "⚠ WARN"


class ChargerTester:
    """充电桩功能测试器"""
    
    def __init__(self, base_url: str, charger_id: str, id_tag: str = "TEST_TAG_001"):
        """
        初始化测试器
        
        Args:
            base_url: CSMS 服务器地址（例如: http://localhost:9000）
            charger_id: 充电桩ID
            id_tag: 用户标签（用于远程启动充电）
        """
        self.base_url = base_url.rstrip('/')
        self.charger_id = charger_id
        self.id_tag = id_tag
        self.test_results: List[Dict] = []
        self.transaction_id: Optional[int] = None
        self.reservation_id: Optional[int] = None
        
    def _log(self, message: str, level: str = "INFO"):
        """打印日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def _test_api(
        self,
        name: str,
        endpoint: str,
        method: str = "POST",
        data: Optional[Dict] = None,
        expected_status: int = 200,
        check_success: bool = True
    ) -> Tuple[TestResult, Optional[Dict], Optional[str]]:
        """
        测试 API 端点
        
        Returns:
            (结果, 响应数据, 错误信息)
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, params=data, timeout=10)
            else:
                response = requests.post(url, json=data, timeout=10)
            
            if response.status_code != expected_status:
                return (
                    TestResult.FAIL,
                    None,
                    f"HTTP {response.status_code} (期望 {expected_status})"
                )
            
            try:
                result_data = response.json()
            except:
                result_data = {"raw": response.text}
            
            if check_success:
                if isinstance(result_data, dict):
                    success = result_data.get("success", result_data.get("ok", True))
                    if not success:
                        return (
                            TestResult.FAIL,
                            result_data,
                            f"API 返回 success=False: {result_data.get('message', '未知错误')}"
                        )
            
            return (TestResult.PASS, result_data, None)
            
        except requests.exceptions.Timeout:
            return (TestResult.FAIL, None, "请求超时")
        except requests.exceptions.ConnectionError:
            return (TestResult.FAIL, None, "连接失败，请检查服务器地址")
        except Exception as e:
            return (TestResult.FAIL, None, f"异常: {str(e)}")
    
    def _record_test(
        self,
        name: str,
        result: TestResult,
        details: Optional[str] = None,
        response_data: Optional[Dict] = None
    ):
        """记录测试结果"""
        self.test_results.append({
            "name": name,
            "result": result.value,
            "details": details,
            "response": response_data,
            "timestamp": datetime.now().isoformat()
        })
        
        status_icon = {
            TestResult.PASS: "✓",
            TestResult.FAIL: "✗",
            TestResult.SKIP: "⊘",
            TestResult.WARN: "⚠"
        }.get(result, "?")
        
        print(f"  {status_icon} {name}")
        if details:
            print(f"     {details}")
        if response_data and result == TestResult.PASS:
            # 只显示关键信息
            if "details" in response_data:
                print(f"     响应: {json.dumps(response_data.get('details'), ensure_ascii=False)[:100]}")
    
    def test_health(self) -> bool:
        """测试健康检查"""
        self._log(f"测试健康检查...")
        result, data, error = self._test_api(
            "健康检查",
            "/health",
            method="GET",
            check_success=False
        )
        self._record_test("健康检查", result, error, data)
        return result == TestResult.PASS
    
    def test_get_charger_status(self) -> bool:
        """测试获取充电桩状态"""
        self._log(f"测试获取充电桩状态...")
        result, data, error = self._test_api(
            "获取充电桩状态",
            "/chargers",
            method="GET",
            check_success=False
        )
        
        if result == TestResult.PASS and isinstance(data, list):
            charger = next((c for c in data if c.get("id") == self.charger_id), None)
            if charger:
                print(f"     充电桩状态: {charger.get('physical_status')} / {charger.get('operational_status')}")
                print(f"     是否可用: {charger.get('is_available')}")
                print(f"     最后在线: {charger.get('last_seen')}")
            else:
                error = f"未找到充电桩 {self.charger_id}"
                result = TestResult.FAIL
        
        self._record_test("获取充电桩状态", result, error, data)
        return result == TestResult.PASS
    
    def test_get_configuration(self) -> bool:
        """测试获取配置"""
        self._log(f"测试获取配置...")
        result, data, error = self._test_api(
            "获取配置",
            "/api/getConfiguration",
            data={"chargePointId": self.charger_id}
        )
        self._record_test("获取配置", result, error, data)
        return result == TestResult.PASS
    
    def test_change_configuration(self) -> bool:
        """测试更改配置"""
        self._log(f"测试更改配置...")
        result, data, error = self._test_api(
            "更改配置",
            "/api/changeConfiguration",
            data={
                "chargePointId": self.charger_id,
                "key": "HeartbeatInterval",
                "value": "30"
            }
        )
        self._record_test("更改配置", result, error, data)
        return result == TestResult.PASS
    
    def test_remote_start(self) -> bool:
        """测试远程启动充电"""
        self._log(f"测试远程启动充电...")
        result, data, error = self._test_api(
            "远程启动充电",
            "/api/remoteStart",
            data={
                "chargePointId": self.charger_id,
                "idTag": self.id_tag
            }
        )
        
        if result == TestResult.PASS and data:
            details = data.get("details", {})
            self.transaction_id = details.get("transactionId")
            if self.transaction_id:
                print(f"     交易ID: {self.transaction_id}")
        
        self._record_test("远程启动充电", result, error, data)
        return result == TestResult.PASS
    
    def test_remote_stop(self) -> bool:
        """测试远程停止充电"""
        self._log(f"测试远程停止充电...")
        result, data, error = self._test_api(
            "远程停止充电",
            "/api/remoteStop",
            data={"chargePointId": self.charger_id}
        )
        self._record_test("远程停止充电", result, error, data)
        return result == TestResult.PASS
    
    def test_reset(self) -> bool:
        """测试重置充电桩"""
        self._log(f"测试重置充电桩...")
        result, data, error = self._test_api(
            "重置充电桩",
            "/api/reset",
            data={
                "chargePointId": self.charger_id,
                "type": "Soft"
            }
        )
        self._record_test("重置充电桩", result, error, data)
        return result == TestResult.PASS
    
    def test_unlock_connector(self) -> bool:
        """测试解锁连接器"""
        self._log(f"测试解锁连接器...")
        result, data, error = self._test_api(
            "解锁连接器",
            "/api/unlockConnector",
            data={
                "chargePointId": self.charger_id,
                "connectorId": 1
            }
        )
        self._record_test("解锁连接器", result, error, data)
        return result == TestResult.PASS
    
    def test_change_availability(self) -> bool:
        """测试更改可用性"""
        self._log(f"测试更改可用性...")
        result, data, error = self._test_api(
            "更改可用性",
            "/api/changeAvailability",
            data={
                "chargePointId": self.charger_id,
                "connectorId": 0,
                "type": "Operative"
            }
        )
        self._record_test("更改可用性", result, error, data)
        return result == TestResult.PASS
    
    def test_set_maintenance(self) -> bool:
        """测试设置维护模式"""
        self._log(f"测试设置维护模式...")
        result, data, error = self._test_api(
            "设置维护模式",
            "/api/setMaintenance",
            data={
                "chargePointId": self.charger_id,
                "enabled": True
            }
        )
        self._record_test("设置维护模式", result, error, data)
        return result == TestResult.PASS
    
    def test_clear_maintenance(self) -> bool:
        """测试清除维护模式"""
        self._log(f"测试清除维护模式...")
        result, data, error = self._test_api(
            "清除维护模式",
            "/api/setMaintenance",
            data={
                "chargePointId": self.charger_id,
                "enabled": False
            }
        )
        self._record_test("清除维护模式", result, error, data)
        return result == TestResult.PASS
    
    def test_set_charging_profile(self) -> bool:
        """测试设置充电曲线"""
        self._log(f"测试设置充电曲线...")
        result, data, error = self._test_api(
            "设置充电曲线",
            "/api/setChargingProfile",
            data={
                "chargePointId": self.charger_id,
                "connectorId": 1,
                "chargingProfileId": 1,
                "stackLevel": 0,
                "chargingProfilePurpose": "TxProfile",
                "chargingProfileKind": "Absolute",
                "chargingSchedule": {
                    "chargingRateUnit": "A",
                    "chargingSchedulePeriod": [
                        {
                            "startPeriod": 0,
                            "limit": 16.0
                        }
                    ]
                }
            }
        )
        self._record_test("设置充电曲线", result, error, data)
        return result == TestResult.PASS
    
    def test_clear_charging_profile(self) -> bool:
        """测试清除充电曲线"""
        self._log(f"测试清除充电曲线...")
        result, data, error = self._test_api(
            "清除充电曲线",
            "/api/clearChargingProfile",
            data={
                "chargePointId": self.charger_id,
                "id": 1
            }
        )
        self._record_test("清除充电曲线", result, error, data)
        return result == TestResult.PASS
    
    def test_get_diagnostics(self) -> bool:
        """测试获取诊断信息"""
        self._log(f"测试获取诊断信息...")
        result, data, error = self._test_api(
            "获取诊断信息",
            "/api/getDiagnostics",
            data={
                "chargePointId": self.charger_id,
                "location": ""
            }
        )
        self._record_test("获取诊断信息", result, error, data)
        return result == TestResult.PASS
    
    def test_export_logs(self) -> bool:
        """测试导出日志"""
        self._log(f"测试导出日志...")
        result, data, error = self._test_api(
            "导出日志",
            "/api/exportLogs",
            data={
                "chargePointId": self.charger_id
            }
        )
        self._record_test("导出日志", result, error, data)
        return result == TestResult.PASS
    
    def test_update_firmware(self) -> bool:
        """测试更新固件"""
        self._log(f"测试更新固件...")
        result, data, error = self._test_api(
            "更新固件",
            "/api/updateFirmware",
            data={
                "chargePointId": self.charger_id,
                "location": "http://example.com/firmware.bin",
                "retrieveDate": datetime.now().isoformat()
            }
        )
        self._record_test("更新固件", result, error, data)
        return result == TestResult.PASS
    
    def test_reserve_now(self) -> bool:
        """测试预约充电"""
        self._log(f"测试预约充电...")
        self.reservation_id = int(time.time())
        result, data, error = self._test_api(
            "预约充电",
            "/api/reserveNow",
            data={
                "chargePointId": self.charger_id,
                "connectorId": 1,
                "expiryDate": datetime.now().isoformat(),
                "idTag": self.id_tag,
                "reservationId": self.reservation_id
            }
        )
        self._record_test("预约充电", result, error, data)
        return result == TestResult.PASS
    
    def test_cancel_reservation(self) -> bool:
        """测试取消预约"""
        self._log(f"测试取消预约...")
        if not self.reservation_id:
            self._record_test("取消预约", TestResult.SKIP, "没有活跃的预约")
            return True
        
        result, data, error = self._test_api(
            "取消预约",
            "/api/cancelReservation",
            data={
                "chargePointId": self.charger_id,
                "reservationId": self.reservation_id
            }
        )
        self._record_test("取消预约", result, error, data)
        return result == TestResult.PASS
    
    def test_data_transfer(self) -> bool:
        """测试数据传输"""
        self._log(f"测试数据传输...")
        result, data, error = self._test_api(
            "数据传输",
            "/api/messages",
            data={
                "chargePointId": self.charger_id,
                "vendorId": "TestVendor",
                "messageId": "test_message",
                "data": "test_data"
            }
        )
        self._record_test("数据传输", result, error, data)
        return result == TestResult.PASS
    
    def test_get_current_order(self) -> bool:
        """测试获取当前订单"""
        self._log(f"测试获取当前订单...")
        result, data, error = self._test_api(
            "获取当前订单",
            "/api/orders/current",
            method="GET",
            data={"chargerId": self.charger_id},
            check_success=False
        )
        self._record_test("获取当前订单", result, error, data)
        return result == TestResult.PASS
    
    def test_get_meter_value(self) -> bool:
        """测试获取电表值"""
        self._log(f"测试获取电表值...")
        result, data, error = self._test_api(
            "获取电表值",
            "/api/orders/current/meter",
            method="GET",
            data={"chargerId": self.charger_id},
            check_success=False
        )
        self._record_test("获取电表值", result, error, data)
        return result == TestResult.PASS
    
    def run_all_tests(self, test_list: Optional[List[str]] = None) -> Dict:
        """运行所有测试"""
        print(f"\n{'='*60}")
        print(f"充电桩功能测试")
        print(f"{'='*60}")
        print(f"充电桩ID: {self.charger_id}")
        print(f"服务器地址: {self.base_url}")
        print(f"用户标签: {self.id_tag}")
        print(f"{'='*60}\n")
        
        # 定义所有测试
        all_tests = {
            "health": ("健康检查", self.test_health),
            "status": ("获取充电桩状态", self.test_get_charger_status),
            "get_config": ("获取配置", self.test_get_configuration),
            "change_config": ("更改配置", self.test_change_configuration),
            "remote_start": ("远程启动充电", self.test_remote_start),
            "get_order": ("获取当前订单", self.test_get_current_order),
            "get_meter": ("获取电表值", self.test_get_meter_value),
            "remote_stop": ("远程停止充电", self.test_remote_stop),
            "reset": ("重置充电桩", self.test_reset),
            "unlock": ("解锁连接器", self.test_unlock_connector),
            "availability": ("更改可用性", self.test_change_availability),
            "maintenance": ("设置维护模式", self.test_set_maintenance),
            "clear_maintenance": ("清除维护模式", self.test_clear_maintenance),
            "set_profile": ("设置充电曲线", self.test_set_charging_profile),
            "clear_profile": ("清除充电曲线", self.test_clear_charging_profile),
            "diagnostics": ("获取诊断信息", self.test_get_diagnostics),
            "export_logs": ("导出日志", self.test_export_logs),
            "firmware": ("更新固件", self.test_update_firmware),
            "reserve": ("预约充电", self.test_reserve_now),
            "cancel_reserve": ("取消预约", self.test_cancel_reservation),
            "data_transfer": ("数据传输", self.test_data_transfer),
        }
        
        # 如果指定了测试列表，只运行指定的测试
        if test_list:
            tests_to_run = {k: v for k, v in all_tests.items() if k in test_list}
        else:
            tests_to_run = all_tests
        
        # 运行测试
        for test_key, (test_name, test_func) in tests_to_run.items():
            try:
                test_func()
                time.sleep(0.5)  # 测试间隔
            except Exception as e:
                self._record_test(test_name, TestResult.FAIL, f"测试异常: {str(e)}")
        
        # 生成报告
        return self.generate_report()
    
    def generate_report(self) -> Dict:
        """生成测试报告"""
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["result"] == TestResult.PASS.value)
        failed = sum(1 for r in self.test_results if r["result"] == TestResult.FAIL.value)
        skipped = sum(1 for r in self.test_results if r["result"] == TestResult.SKIP.value)
        warned = sum(1 for r in self.test_results if r["result"] == TestResult.WARN.value)
        
        print(f"\n{'='*60}")
        print(f"测试报告")
        print(f"{'='*60}")
        print(f"总计: {total}")
        print(f"通过: {passed} ✓")
        print(f"失败: {failed} ✗")
        print(f"跳过: {skipped} ⊘")
        print(f"警告: {warned} ⚠")
        print(f"成功率: {passed/total*100:.1f}%")
        print(f"{'='*60}\n")
        
        # 显示失败的测试
        if failed > 0:
            print("失败的测试:")
            for result in self.test_results:
                if result["result"] == TestResult.FAIL.value:
                    print(f"  ✗ {result['name']}: {result.get('details', '未知错误')}")
            print()
        
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "warned": warned,
            "success_rate": passed/total*100 if total > 0 else 0,
            "results": self.test_results
        }


def main():
    parser = argparse.ArgumentParser(
        description="充电桩功能测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试所有功能
  python test_charger_functions.py --charger-id AMOS-0001 --url http://localhost:9000
  
  # 只测试基本功能
  python test_charger_functions.py --charger-id AMOS-0001 --url http://localhost:9000 --tests health status remote_start remote_stop
  
  # 测试远程控制功能
  python test_charger_functions.py --charger-id AMOS-0001 --url http://localhost:9000 --tests remote_start remote_stop reset unlock
        """
    )
    
    parser.add_argument(
        "--charger-id",
        type=str,
        required=True,
        help="充电桩ID"
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:9000",
        help="CSMS 服务器地址 (默认: http://localhost:9000)"
    )
    parser.add_argument(
        "--id-tag",
        type=str,
        default="TEST_TAG_001",
        help="用户标签，用于远程启动充电 (默认: TEST_TAG_001)"
    )
    parser.add_argument(
        "--tests",
        type=str,
        nargs="+",
        help="指定要运行的测试（不指定则运行所有测试）"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="将测试报告保存到 JSON 文件"
    )
    
    args = parser.parse_args()
    
    # 创建测试器
    tester = ChargerTester(
        base_url=args.url,
        charger_id=args.charger_id,
        id_tag=args.id_tag
    )
    
    # 运行测试
    report = tester.run_all_tests(test_list=args.tests)
    
    # 保存报告
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"测试报告已保存到: {args.output}")
    
    # 返回退出码
    sys.exit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

