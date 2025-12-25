#!/usr/bin/env python3
#
# OCPP 1.6 规范符合性测试脚本（自动监控服务器日志版本）
# 全面测试充电桩的 OCPP 功能实现和响应规范符合性
# 自动监控服务器日志，验证消息格式
#

import argparse
import requests
import json
import time
import re
import subprocess
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from queue import Queue
import sys


class LogMonitor:
    """服务器日志监控器"""
    
    def __init__(self, server_host: str, container_name: str = "ocpp-csms-prod", 
                 use_ssh: bool = False, ssh_user: str = "root", ssh_key: Optional[str] = None):
        self.server_host = server_host
        self.container_name = container_name
        self.use_ssh = use_ssh
        self.ssh_user = ssh_user
        self.ssh_key = ssh_key
        self.log_queue = Queue()
        self.monitoring = False
        self.monitor_thread = None
        self.logs = []
        
    def start_monitoring(self):
        """开始监控日志"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_logs, daemon=True)
        self.monitor_thread.start()
        time.sleep(1)  # 等待线程启动
        print("✓ 日志监控已启动")
    
    def stop_monitoring(self):
        """停止监控日志"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        print("✓ 日志监控已停止")
    
    def _monitor_logs(self):
        """监控日志（后台线程）"""
        try:
            if self.use_ssh:
                # 通过 SSH 连接
                ssh_cmd = ["ssh"]
                if self.ssh_key:
                    ssh_cmd.extend(["-i", self.ssh_key])
                ssh_cmd.extend([
                    f"{self.ssh_user}@{self.server_host}",
                    f"docker logs -f {self.container_name}"
                ])
                process = subprocess.Popen(
                    ssh_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
            else:
                # 直接执行 docker logs（本地或远程 Docker）
                # 注意：这需要能够直接访问 Docker
                process = subprocess.Popen(
                    ["docker", "logs", "-f", self.container_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
            
            for line in iter(process.stdout.readline, ''):
                if not self.monitoring:
                    break
                if line:
                    line = line.strip()
                    self.logs.append({
                        "timestamp": datetime.now().isoformat(),
                        "content": line
                    })
                    self.log_queue.put(line)
            
            process.terminate()
        except Exception as e:
            print(f"⚠️  日志监控错误: {e}")
    
    def get_recent_logs(self, charge_point_id: str, since: Optional[datetime] = None) -> List[str]:
        """获取最近的日志（包含指定充电桩ID）"""
        filtered_logs = []
        for log in self.logs:
            if charge_point_id in log["content"]:
                if since is None or datetime.fromisoformat(log["timestamp"]) >= since:
                    filtered_logs.append(log["content"])
        return filtered_logs
    
    def wait_for_message(self, charge_point_id: str, pattern: str, timeout: float = 10.0) -> Optional[str]:
        """等待匹配指定模式的消息"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                line = self.log_queue.get(timeout=0.5)
                if charge_point_id in line and pattern in line:
                    return line
            except:
                continue
        return None


class OCPPMessageParser:
    """OCPP 消息解析器"""
    
    @staticmethod
    def parse_ocpp_message(log_line: str) -> Optional[Dict[str, Any]]:
        """解析日志中的 OCPP 消息"""
        # 匹配 OCPP 消息格式
        # 示例: [861076087029615] <- MQTT OCPP CALL: GetConfiguration (UniqueId: req_123)
        # 或: [861076087029615] <- MQTT CALLRESULT (UniqueId: req_123) | payload: {...}
        # 或: [861076087029615] <- MQTT OCPP CALL: Heartbeat (UniqueId: xxx)
        # 或: [861076087029615] <- MQTT OCPP CALL: StatusNotification (UniqueId: xxx)
        # 或: [861076087029615] <- MQTT OCPP CALL: MeterValues (UniqueId: xxx)
        
        # 尝试解析 payload（可能在日志的不同位置）
        payload_match = re.search(r'payload:\s*({.+?})(?:\s|$)', log_line)
        payload = None
        if payload_match:
            try:
                payload = json.loads(payload_match.group(1))
            except:
                pass
        
        patterns = [
            # CALL 消息（从充电桩到服务器）
            r'\[([^\]]+)\].*<-.*OCPP CALL:\s+(\w+)\s+\(UniqueId:\s+([^\)]+)\)',
            # CALL 消息（简化格式）
            r'\[([^\]]+)\].*<-.*(\w+).*\(UniqueId:\s+([^\)]+)\)',
            # CALLRESULT 消息
            r'\[([^\]]+)\].*CALLRESULT.*UniqueId:\s+([^,\)]+)',
            # CALLERROR 消息
            r'\[([^\]]+)\].*CALLERROR.*UniqueId:\s+([^,\)]+).*ErrorCode:\s+([^,\)]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, log_line)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    charge_point_id = groups[0]
                    action_or_id = groups[1] if len(groups) > 1 else None
                    unique_id = groups[2] if len(groups) > 2 else groups[1]
                    
                    # 判断消息类型
                    if "CALLERROR" in log_line:
                        message_type = "CALLERROR"
                        error_code = groups[2] if len(groups) > 2 else None
                    elif "CALLRESULT" in log_line:
                        message_type = "CALLRESULT"
                    elif "CALL" in log_line or "<-" in log_line:
                        message_type = "CALL"
                    else:
                        continue
                    
                    # 对于 CALL 消息，action_or_id 就是 action
                    action = action_or_id if message_type == "CALL" else None
                    
                    return {
                        "charge_point_id": charge_point_id,
                        "message_type": message_type,
                        "action": action,
                        "unique_id": unique_id,
                        "payload": payload,
                        "error_code": error_code if message_type == "CALLERROR" else None,
                        "log_line": log_line
                    }
        return None
    
    @staticmethod
    def validate_ocpp_format(message: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """验证 OCPP 消息格式"""
        issues = []
        
        if message["message_type"] == "CALL":
            # CALL 消息应包含 action 和 unique_id
            if not message.get("action"):
                issues.append("CALL 消息缺少 action")
            if not message.get("unique_id"):
                issues.append("CALL 消息缺少 unique_id")
        
        elif message["message_type"] == "CALLRESULT":
            # CALLRESULT 消息应包含 unique_id 和 payload
            if not message.get("unique_id"):
                issues.append("CALLRESULT 消息缺少 unique_id")
            if message.get("payload") is None:
                issues.append("CALLRESULT 消息缺少 payload")
            else:
                # 验证 payload 是对象
                if not isinstance(message["payload"], dict):
                    issues.append("CALLRESULT payload 应为对象类型")
        
        elif message["message_type"] == "CALLERROR":
            # CALLERROR 消息应包含 unique_id 和 error_code
            if not message.get("unique_id"):
                issues.append("CALLERROR 消息缺少 unique_id")
            if not message.get("error_code"):
                issues.append("CALLERROR 消息缺少 error_code")
        
        return len(issues) == 0, issues


class OCPPComplianceTester:
    """OCPP 规范符合性测试器（自动监控日志版本）"""
    
    def __init__(self, server_url: str, charge_point_id: str, 
                 log_monitor: Optional[LogMonitor] = None):
        self.server_url = server_url.rstrip('/')
        self.charge_point_id = charge_point_id
        self.base_url = f"{self.server_url}/api/v1"
        self.test_results: List[Dict[str, Any]] = []
        self.compliance_issues: List[Dict[str, Any]] = []
        self.log_monitor = log_monitor
        self.message_parser = OCPPMessageParser()
        self.request_unique_ids = {}  # 存储请求的 unique_id
        
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
                    compliance_issues: Optional[List[str]] = None,
                    log_analysis: Optional[Dict] = None):
        """记录测试结果"""
        result = {
            "test_name": test_name,
            "success": success,
            "message": message,
            "details": details or {},
            "response_time": response_time,
            "compliance_issues": compliance_issues or [],
            "log_analysis": log_analysis or {},
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
        if log_analysis:
            print(f"📋 日志分析:")
            if log_analysis.get("messages_found"):
                print(f"   找到 {len(log_analysis['messages_found'])} 条相关消息")
            if log_analysis.get("format_issues"):
                print(f"   格式问题: {len(log_analysis['format_issues'])} 个")
                for issue in log_analysis["format_issues"]:
                    print(f"     - {issue}")
        if response_time:
            print(f"响应时间: {response_time:.3f} 秒")
    
    def analyze_logs_for_test(self, test_name: str, action: str, 
                              timeout: float = 5.0) -> Dict[str, Any]:
        """分析测试相关的日志"""
        if not self.log_monitor:
            return {}
        
        analysis = {
            "messages_found": [],
            "format_issues": [],
            "messages": []
        }
        
        # 等待并收集相关日志
        start_time = datetime.now()
        time.sleep(0.5)  # 等待日志写入
        
        # 获取最近的日志
        recent_logs = self.log_monitor.get_recent_logs(
            self.charge_point_id,
            since=start_time
        )
        
        # 解析 OCPP 消息
        for log_line in recent_logs:
            if action in log_line or "CALLRESULT" in log_line or "CALLERROR" in log_line:
                message = self.message_parser.parse_ocpp_message(log_line)
                if message:
                    analysis["messages"].append(message)
                    analysis["messages_found"].append(log_line)
                    
                    # 验证格式
                    is_valid, issues = self.message_parser.validate_ocpp_format(message)
                    if not is_valid:
                        analysis["format_issues"].extend(issues)
        
        return analysis
    
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
                
                required_fields = ['id', 'status']
                for field in required_fields:
                    if field not in charger:
                        issues.append(f"缺少必要字段: {field}")
                
                # 分析日志
                log_analysis = self.analyze_logs_for_test("连接检查", "连接")
                
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
                    issues,
                    log_analysis
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
            
            # 分析日志
            log_analysis = self.analyze_logs_for_test("GetConfiguration", "GetConfiguration", timeout=3.0)
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                # API 响应结构: {success, message, details: {success, data, transport}}
                details = result.get("details", {})
                data = details.get("data", {}) if isinstance(details, dict) else {}
                
                issues = []
                
                # 验证响应结构
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                # 验证 configurationKey 字段
                if "configurationKey" in data:
                    config_list = data["configurationKey"]
                    if not isinstance(config_list, list):
                        issues.append("configurationKey 应为数组类型")
                    else:
                        for i, item in enumerate(config_list[:5]):
                            if not isinstance(item, dict):
                                issues.append(f"配置项 {i} 应为对象类型")
                            else:
                                if "key" not in item:
                                    issues.append(f"配置项 {i} 缺少 key 字段")
                                if "value" not in item:
                                    issues.append(f"配置项 {i} 缺少 value 字段（可为 null）")
                
                # 合并日志分析中的格式问题
                issues.extend(log_analysis.get("format_issues", []))
                
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
                    issues,
                    log_analysis
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
                    response_time,
                    log_analysis=log_analysis
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
            
            # 分析日志
            log_analysis = self.analyze_logs_for_test("ChangeConfiguration", "ChangeConfiguration", timeout=3.0)
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                # API 响应结构: {success, message, details: {success, data, transport}}
                details = result.get("details", {})
                data = details.get("data", {}) if isinstance(details, dict) else {}
                
                issues = []
                
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                if "status" in data:
                    status = data["status"]
                    valid_statuses = ["Accepted", "Rejected", "NotSupported", "RebootRequired"]
                    if status not in valid_statuses:
                        issues.append(f"status 值 '{status}' 不符合 OCPP 1.6 规范，应为: {valid_statuses}")
                else:
                    issues.append("缺少 status 字段（OCPP 1.6 必需）")
                
                # 合并日志分析中的格式问题
                issues.extend(log_analysis.get("format_issues", []))
                
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
                    issues,
                    log_analysis
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
                    response_time,
                    log_analysis=log_analysis
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
            
            # 分析日志
            log_analysis = self.analyze_logs_for_test("UnlockConnector", "UnlockConnector", timeout=3.0)
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                # API 响应结构: {success, message, details: {success, data, transport}}
                details = result.get("details", {})
                data = details.get("data", {}) if isinstance(details, dict) else {}
                
                issues = []
                
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                if "status" in data:
                    status = data["status"]
                    valid_statuses = ["Unlocked", "UnlockFailed", "NotSupported"]
                    if status not in valid_statuses:
                        issues.append(f"status 值 '{status}' 不符合 OCPP 1.6 规范，应为: {valid_statuses}")
                else:
                    issues.append("缺少 status 字段（OCPP 1.6 必需）")
                
                # 合并日志分析中的格式问题
                issues.extend(log_analysis.get("format_issues", []))
                
                self.record_test(
                    "UnlockConnector",
                    success and len(issues) == 0,
                    f"解锁连接器{'成功' if success else '失败'}，状态: {data.get('status', 'N/A')}",
                    {
                        "response": data,
                        "connector_id": payload["connectorId"]
                    },
                    response_time,
                    issues,
                    log_analysis
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
                    response_time,
                    log_analysis=log_analysis
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
            
            # 分析日志
            log_analysis = self.analyze_logs_for_test("RemoteStartTransaction", "RemoteStartTransaction", timeout=3.0)
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                # API 响应结构: {success, message, details: {success, data, transport}}
                details = result.get("details", {})
                data = details.get("data", {}) if isinstance(details, dict) else {}
                
                issues = []
                
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                if "status" in data:
                    status = data["status"]
                    valid_statuses = ["Accepted", "Rejected"]
                    if status not in valid_statuses:
                        issues.append(f"status 值 '{status}' 不符合 OCPP 1.6 规范，应为: {valid_statuses}")
                else:
                    issues.append("缺少 status 字段（OCPP 1.6 必需）")
                
                # 合并日志分析中的格式问题
                issues.extend(log_analysis.get("format_issues", []))
                
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
                    issues,
                    log_analysis
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
                    response_time,
                    log_analysis=log_analysis
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
    
    def get_heartbeat_interval(self) -> Optional[int]:
        """获取 HeartbeatInterval 配置值"""
        try:
            payload = {"chargePointId": self.charge_point_id}
            response = requests.post(
                f"{self.base_url}/ocpp/get-configuration",
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})
                config_list = data.get("configurationKey", [])
                for item in config_list:
                    if item.get("key") == "HeartbeatInterval":
                        value = item.get("value")
                        if value:
                            try:
                                return int(value)
                            except:
                                pass
        except:
            pass
        return None
    
    def get_meter_value_sample_interval(self) -> Optional[int]:
        """获取 MeterValueSampleInterval 配置值"""
        try:
            payload = {"chargePointId": self.charge_point_id}
            response = requests.post(
                f"{self.base_url}/ocpp/get-configuration",
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})
                config_list = data.get("configurationKey", [])
                # OCPP 1.6 可能的配置键名
                config_keys = ["MeterValueSampleInterval", "MeterValuesSampleInterval", "MeterValuesInterval"]
                for key in config_keys:
                    for item in config_list:
                        if item.get("key") == key:
                            value = item.get("value")
                            if value:
                                try:
                                    return int(value)
                                except:
                                    pass
        except:
            pass
        return None
    
    def test_heartbeat_monitoring(self, monitor_duration: int = 60) -> bool:
        """测试 Heartbeat 消息监测 - 验证上报频率是否符合配置"""
        self.print_header("7. Heartbeat 消息监测")
        
        # 获取 HeartbeatInterval 配置
        heartbeat_interval = self.get_heartbeat_interval()
        if heartbeat_interval is None:
            heartbeat_interval = 300  # 默认值（秒）
            print(f"⚠️  未找到 HeartbeatInterval 配置，使用默认值: {heartbeat_interval} 秒")
        else:
            print(f"✓ 获取到 HeartbeatInterval 配置: {heartbeat_interval} 秒")
        
        print(f"开始监测 Heartbeat 消息（持续 {monitor_duration} 秒）...")
        print(f"预期频率: 每 {heartbeat_interval} 秒一次")
        
        start_time = datetime.now()
        heartbeat_messages = []
        issues = []
        
        # 监测指定时长
        while (datetime.now() - start_time).total_seconds() < monitor_duration:
            if self.log_monitor:
                # 获取最近的日志
                recent_logs = self.log_monitor.get_recent_logs(
                    self.charge_point_id,
                    since=start_time
                )
                
                # 查找 Heartbeat 消息
                for log_line in recent_logs:
                    if "Heartbeat" in log_line and self.charge_point_id in log_line:
                        # 解析消息
                        message = self.message_parser.parse_ocpp_message(log_line)
                        if message and message.get("action") == "Heartbeat":
                            # 检查是否已记录（避免重复）
                            if not any(m.get("log_line") == log_line for m in heartbeat_messages):
                                heartbeat_messages.append({
                                    "timestamp": datetime.now(),
                                    "message": message,
                                    "log_line": log_line
                                })
            
            time.sleep(1)  # 每秒检查一次
        
        # 分析结果
        print(f"\n监测结果: 共收到 {len(heartbeat_messages)} 条 Heartbeat 消息")
        
        if len(heartbeat_messages) == 0:
            issues.append("未收到任何 Heartbeat 消息")
        else:
            # 验证消息格式
            for i, hb in enumerate(heartbeat_messages):
                msg = hb["message"]
                is_valid, msg_issues = self.message_parser.validate_ocpp_format(msg)
                if not is_valid:
                    issues.extend([f"消息 {i+1}: {issue}" for issue in msg_issues])
                
                # 验证 payload 结构
                if msg.get("payload"):
                    payload = msg["payload"]
                    if not isinstance(payload, dict):
                        issues.append(f"消息 {i+1}: payload 应为对象类型")
                    elif "currentTime" not in payload:
                        issues.append(f"消息 {i+1}: payload 缺少 currentTime 字段（OCPP 1.6 必需）")
            
            # 验证频率
            intervals = []
            avg_interval = 0
            if len(heartbeat_messages) >= 2:
                for i in range(1, len(heartbeat_messages)):
                    interval = (heartbeat_messages[i]["timestamp"] - 
                               heartbeat_messages[i-1]["timestamp"]).total_seconds()
                    intervals.append(interval)
                
                avg_interval = sum(intervals) / len(intervals) if intervals else 0
                expected_interval = heartbeat_interval
                tolerance = expected_interval * 0.2  # 允许 20% 误差
                
                print(f"平均间隔: {avg_interval:.1f} 秒")
                print(f"预期间隔: {expected_interval} 秒")
                
                if abs(avg_interval - expected_interval) > tolerance:
                    issues.append(
                        f"Heartbeat 频率不符合配置: 平均间隔 {avg_interval:.1f} 秒，"
                        f"预期 {expected_interval} 秒（允许误差 ±{tolerance:.1f} 秒）"
                    )
            else:
                issues.append("Heartbeat 消息数量不足，无法验证频率")
        
        # 分析日志
        log_analysis = {
            "messages_found": [hb["log_line"] for hb in heartbeat_messages],
            "format_issues": issues,
            "messages": [hb["message"] for hb in heartbeat_messages],
            "heartbeat_interval_config": heartbeat_interval,
            "monitor_duration": monitor_duration,
            "message_count": len(heartbeat_messages)
        }
        
        success = len(issues) == 0
        
        self.record_test(
            "Heartbeat 监测",
            success,
            f"监测到 {len(heartbeat_messages)} 条 Heartbeat 消息" + 
            (f"，平均间隔 {avg_interval:.1f} 秒" if len(heartbeat_messages) >= 2 else ""),
            {
                "heartbeat_interval_config": heartbeat_interval,
                "monitor_duration": monitor_duration,
                "message_count": len(heartbeat_messages),
                "intervals": intervals if len(heartbeat_messages) >= 2 else []
            },
            monitor_duration,
            issues,
            log_analysis
        )
        
        return success
    
    def validate_status_transition(self, from_status: str, to_status: str) -> Tuple[bool, str]:
        """验证状态转换是否合理"""
        # OCPP 1.6 状态转换规则
        valid_transitions = {
            "Available": ["Preparing", "Reserved", "Unavailable", "Faulted"],
            "Preparing": ["Charging", "Available", "Unavailable", "Faulted"],
            "Charging": ["SuspendedEVSE", "SuspendedEV", "Finishing", "Faulted"],
            "SuspendedEVSE": ["Charging", "Finishing", "Faulted"],
            "SuspendedEV": ["Charging", "Finishing", "Faulted"],
            "Finishing": ["Available", "Faulted"],
            "Reserved": ["Available", "Preparing", "Unavailable", "Faulted"],
            "Unavailable": ["Available", "Faulted"],
            "Faulted": ["Available", "Unavailable"]
        }
        
        if from_status not in valid_transitions:
            return False, f"未知的起始状态: {from_status}"
        
        if to_status not in valid_transitions[from_status]:
            return False, f"无效的状态转换: {from_status} -> {to_status}"
        
        return True, ""
    
    def test_status_notification_monitoring(self, monitor_duration: int = 30) -> bool:
        """测试 StatusNotification 消息监测 - 验证上报逻辑"""
        self.print_header("8. StatusNotification 消息监测")
        
        print(f"开始监测 StatusNotification 消息（持续 {monitor_duration} 秒）...")
        
        start_time = datetime.now()
        status_messages = []
        issues = []
        
        # 监测指定时长
        while (datetime.now() - start_time).total_seconds() < monitor_duration:
            if self.log_monitor:
                recent_logs = self.log_monitor.get_recent_logs(
                    self.charge_point_id,
                    since=start_time
                )
                
                for log_line in recent_logs:
                    if "StatusNotification" in log_line and self.charge_point_id in log_line:
                        message = self.message_parser.parse_ocpp_message(log_line)
                        if message and message.get("action") == "StatusNotification":
                            if not any(m.get("log_line") == log_line for m in status_messages):
                                status_messages.append({
                                    "timestamp": datetime.now(),
                                    "message": message,
                                    "log_line": log_line
                                })
            
            time.sleep(1)
        
        print(f"\n监测结果: 共收到 {len(status_messages)} 条 StatusNotification 消息")
        
        if len(status_messages) == 0:
            issues.append("未收到任何 StatusNotification 消息（可能充电桩状态未变化）")
        else:
            # 验证消息格式
            for i, st in enumerate(status_messages):
                msg = st["message"]
                is_valid, msg_issues = self.message_parser.validate_ocpp_format(msg)
                if not is_valid:
                    issues.extend([f"消息 {i+1}: {issue}" for issue in msg_issues])
                
                # 验证 payload 结构
                if msg.get("payload"):
                    payload = msg["payload"]
                    if not isinstance(payload, dict):
                        issues.append(f"消息 {i+1}: payload 应为对象类型")
                    else:
                        # OCPP 1.6 StatusNotification 必需字段
                        required_fields = ["connectorId", "status"]
                        for field in required_fields:
                            if field not in payload:
                                issues.append(f"消息 {i+1}: payload 缺少 {field} 字段（OCPP 1.6 必需）")
                        
                        # 验证 status 枚举值
                        if "status" in payload:
                            status = payload["status"]
                            valid_statuses = [
                                "Available", "Preparing", "Charging", "SuspendedEVSE",
                                "SuspendedEV", "Finishing", "Reserved", "Unavailable", "Faulted"
                            ]
                            if status not in valid_statuses:
                                issues.append(
                                    f"消息 {i+1}: status 值 '{status}' 不符合 OCPP 1.6 规范，"
                                    f"应为: {valid_statuses}"
                                )
            
            # 验证状态转换逻辑
            if len(status_messages) >= 2:
                print("\n验证状态转换逻辑...")
                previous_status = None
                for i, st in enumerate(status_messages):
                    current_status = st["message"].get("payload", {}).get("status")
                    connector_id = st["message"].get("payload", {}).get("connectorId")
                    
                    if current_status:
                        if previous_status is not None:
                            # 验证状态转换
                            is_valid, error_msg = self.validate_status_transition(
                                previous_status, current_status
                            )
                            if not is_valid:
                                issues.append(
                                    f"消息 {i+1} (connectorId={connector_id}): "
                                    f"状态转换不符合逻辑 - {error_msg}"
                                )
                            else:
                                print(f"  ✓ 状态转换: {previous_status} -> {current_status} (connectorId={connector_id})")
                        else:
                            print(f"  初始状态: {current_status} (connectorId={connector_id})")
                        
                        previous_status = current_status
            else:
                print("状态消息数量不足，无法验证状态转换逻辑")
        
        log_analysis = {
            "messages_found": [st["log_line"] for st in status_messages],
            "format_issues": issues,
            "messages": [st["message"] for st in status_messages],
            "monitor_duration": monitor_duration,
            "message_count": len(status_messages),
            "status_transitions": [
                {
                    "from": status_messages[i-1]["message"].get("payload", {}).get("status") if i > 0 else None,
                    "to": st["message"].get("payload", {}).get("status"),
                    "connector_id": st["message"].get("payload", {}).get("connectorId")
                }
                for i, st in enumerate(status_messages)
            ] if len(status_messages) > 0 else []
        }
        
        success = len(issues) == 0
        
        self.record_test(
            "StatusNotification 监测",
            success,
            f"监测到 {len(status_messages)} 条 StatusNotification 消息" +
            (f"，状态转换逻辑{'正常' if len(status_messages) >= 2 and len([i for i in issues if '状态转换' in i]) == 0 else '异常'}" if len(status_messages) >= 2 else ""),
            {
                "monitor_duration": monitor_duration,
                "message_count": len(status_messages),
                "statuses": [
                    st["message"].get("payload", {}).get("status") 
                    for st in status_messages 
                    if st["message"].get("payload")
                ],
                "status_transitions_valid": len([i for i in issues if '状态转换' in i]) == 0 if len(status_messages) >= 2 else None
            },
            monitor_duration,
            issues,
            log_analysis
        )
        
        return success
    
    def test_meter_values_monitoring(self, monitor_duration: int = 30) -> bool:
        """测试 MeterValues 消息监测 - 验证上报频率是否符合配置"""
        self.print_header("9. MeterValues 消息监测")
        
        # 获取 MeterValueSampleInterval 配置
        sample_interval = self.get_meter_value_sample_interval()
        if sample_interval is None:
            sample_interval = 60  # 默认值（秒）
            print(f"⚠️  未找到 MeterValueSampleInterval 配置，使用默认值: {sample_interval} 秒")
        else:
            print(f"✓ 获取到 MeterValueSampleInterval 配置: {sample_interval} 秒")
        
        print(f"开始监测 MeterValues 消息（持续 {monitor_duration} 秒）...")
        print("⚠️  注意：MeterValues 通常在充电过程中上报")
        print(f"预期频率: 每 {sample_interval} 秒一次")
        
        start_time = datetime.now()
        meter_messages = []
        issues = []
        
        # 监测指定时长
        while (datetime.now() - start_time).total_seconds() < monitor_duration:
            if self.log_monitor:
                recent_logs = self.log_monitor.get_recent_logs(
                    self.charge_point_id,
                    since=start_time
                )
                
                for log_line in recent_logs:
                    if "MeterValues" in log_line and self.charge_point_id in log_line:
                        message = self.message_parser.parse_ocpp_message(log_line)
                        if message and message.get("action") == "MeterValues":
                            if not any(m.get("log_line") == log_line for m in meter_messages):
                                meter_messages.append({
                                    "timestamp": datetime.now(),
                                    "message": message,
                                    "log_line": log_line
                                })
            
            time.sleep(1)
        
        print(f"\n监测结果: 共收到 {len(meter_messages)} 条 MeterValues 消息")
        
        if len(meter_messages) == 0:
            issues.append("未收到任何 MeterValues 消息（可能未在充电状态）")
        else:
            # 验证消息格式
            for i, mv in enumerate(meter_messages):
                msg = mv["message"]
                is_valid, msg_issues = self.message_parser.validate_ocpp_format(msg)
                if not is_valid:
                    issues.extend([f"消息 {i+1}: {issue}" for issue in msg_issues])
                
                # 验证 payload 结构
                if msg.get("payload"):
                    payload = msg["payload"]
                    if not isinstance(payload, dict):
                        issues.append(f"消息 {i+1}: payload 应为对象类型")
                    else:
                        # OCPP 1.6 MeterValues 必需字段
                        if "connectorId" not in payload:
                            issues.append(f"消息 {i+1}: payload 缺少 connectorId 字段（OCPP 1.6 必需）")
                        if "meterValue" not in payload:
                            issues.append(f"消息 {i+1}: payload 缺少 meterValue 字段（OCPP 1.6 必需）")
                        elif not isinstance(payload["meterValue"], list):
                            issues.append(f"消息 {i+1}: meterValue 应为数组类型")
                        else:
                            # 验证 meterValue 数组中的元素
                            for j, mv_item in enumerate(payload["meterValue"]):
                                if not isinstance(mv_item, dict):
                                    issues.append(f"消息 {i+1}, meterValue[{j}]: 应为对象类型")
                                else:
                                    if "timestamp" not in mv_item:
                                        issues.append(f"消息 {i+1}, meterValue[{j}]: 缺少 timestamp 字段")
                                    if "sampledValue" not in mv_item:
                                        issues.append(f"消息 {i+1}, meterValue[{j}]: 缺少 sampledValue 字段")
                                    elif not isinstance(mv_item["sampledValue"], list):
                                        issues.append(f"消息 {i+1}, meterValue[{j}]: sampledValue 应为数组类型")
            
            # 验证上报频率
            intervals = []
            avg_interval = 0
            if len(meter_messages) >= 2:
                for i in range(1, len(meter_messages)):
                    interval = (meter_messages[i]["timestamp"] - 
                               meter_messages[i-1]["timestamp"]).total_seconds()
                    intervals.append(interval)
                
                avg_interval = sum(intervals) / len(intervals) if intervals else 0
                expected_interval = sample_interval
                tolerance = expected_interval * 0.3  # 允许 30% 误差（MeterValues 可能更灵活）
                
                print(f"平均间隔: {avg_interval:.1f} 秒")
                print(f"预期间隔: {expected_interval} 秒")
                
                if abs(avg_interval - expected_interval) > tolerance:
                    issues.append(
                        f"MeterValues 频率不符合配置: 平均间隔 {avg_interval:.1f} 秒，"
                        f"预期 {expected_interval} 秒（允许误差 ±{tolerance:.1f} 秒）"
                    )
            else:
                issues.append("MeterValues 消息数量不足，无法验证频率")
        
        log_analysis = {
            "messages_found": [mv["log_line"] for mv in meter_messages],
            "format_issues": issues,
            "messages": [mv["message"] for mv in meter_messages],
            "monitor_duration": monitor_duration,
            "message_count": len(meter_messages),
            "sample_interval_config": sample_interval,
            "intervals": intervals if len(meter_messages) >= 2 else []
        }
        
        success = len(issues) == 0
        
        self.record_test(
            "MeterValues 监测",
            success,
            f"监测到 {len(meter_messages)} 条 MeterValues 消息" +
            (f"，平均间隔 {avg_interval:.1f} 秒" if len(meter_messages) >= 2 else ""),
            {
                "monitor_duration": monitor_duration,
                "message_count": len(meter_messages),
                "sample_interval_config": sample_interval,
                "intervals": intervals if len(meter_messages) >= 2 else []
            },
            monitor_duration,
            issues,
            log_analysis
        )
        
        return success
    
    def test_remote_stop_transaction(self, transaction_id: Optional[int] = None) -> bool:
        """测试 RemoteStopTransaction - 验证响应格式"""
        self.print_header("6. RemoteStopTransaction - 远程停止充电")
        
        if transaction_id is None:
            transaction_id = self.get_active_transaction()
        
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
            
            # 分析日志
            log_analysis = self.analyze_logs_for_test("RemoteStopTransaction", "RemoteStopTransaction", timeout=3.0)
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                # API 响应结构: {success, message, details: {success, data, transport}}
                details = result.get("details", {})
                data = details.get("data", {}) if isinstance(details, dict) else {}
                
                issues = []
                
                if not isinstance(data, dict):
                    issues.append("响应 data 字段应为对象类型")
                
                if "status" in data:
                    status = data["status"]
                    valid_statuses = ["Accepted", "Rejected"]
                    if status not in valid_statuses:
                        issues.append(f"status 值 '{status}' 不符合 OCPP 1.6 规范，应为: {valid_statuses}")
                else:
                    issues.append("缺少 status 字段（OCPP 1.6 必需）")
                
                # 合并日志分析中的格式问题
                issues.extend(log_analysis.get("format_issues", []))
                
                self.record_test(
                    "RemoteStopTransaction",
                    success and len(issues) == 0,
                    f"远程停止充电{'成功' if success else '失败'}，状态: {data.get('status', 'N/A')}",
                    {
                        "response": data,
                        "transaction_id": transaction_id
                    },
                    response_time,
                    issues,
                    log_analysis
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
                    response_time,
                    log_analysis=log_analysis
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
    
    def run_all_tests(self, include_reset: bool = False):
        """运行所有测试"""
        self.print_header("OCPP 1.6 规范符合性测试（自动监控日志）")
        print(f"充电桩ID: {self.charge_point_id}")
        print(f"服务器: {self.server_url}")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"包含重置测试: {'是' if include_reset else '否'}")
        
        # 启动日志监控
        if self.log_monitor:
            self.log_monitor.start_monitoring()
            time.sleep(2)  # 等待日志监控稳定
        
        try:
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
            time.sleep(2)
            
            # 6. RemoteStopTransaction
            self.test_remote_stop_transaction()
            time.sleep(1)
            
            # 7. Heartbeat 监测（监测 60 秒）
            self.test_heartbeat_monitoring(monitor_duration=60)
            
            # 8. StatusNotification 监测（监测 30 秒）
            self.test_status_notification_monitoring(monitor_duration=30)
            
            # 9. MeterValues 监测（监测 30 秒，如果正在充电）
            self.test_meter_values_monitoring(monitor_duration=30)
        finally:
            # 停止日志监控
            if self.log_monitor:
                self.log_monitor.stop_monitoring()
        
        # 生成报告
        self.generate_report()
    
    def generate_report(self):
        """生成测试报告"""
        self.print_header("测试报告")
        
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
        
        print(f"\n详细结果:")
        for result in self.test_results:
            status = "✓" if result["success"] else "✗"
            print(f"  {status} {result['test_name']}: {result['message']}")
            if result.get("compliance_issues"):
                for issue in result["compliance_issues"]:
                    print(f"    ⚠️  {issue}")
            if result.get("log_analysis", {}).get("format_issues"):
                for issue in result["log_analysis"]["format_issues"]:
                    print(f"    📋 日志格式问题: {issue}")
        
        if self.compliance_issues:
            print(f"\n规范问题汇总:")
            for issue_info in self.compliance_issues:
                print(f"  - [{issue_info['test']}] {issue_info['issue']}")
        
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


def main():
    parser = argparse.ArgumentParser(
        description="OCPP 1.6 规范符合性测试脚本（自动监控日志版本）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本测试（通过 SSH 监控日志）
  python test_ocpp_compliance_auto.py \\
    --server http://47.236.134.99:9000 \\
    --charge-point-id 861076087029615 \\
    --monitor-logs \\
    --server-host 47.236.134.99 \\
    --use-ssh \\
    --ssh-user root

  # 本地 Docker 监控
  python test_ocpp_compliance_auto.py \\
    --server http://localhost:9000 \\
    --charge-point-id CP001 \\
    --monitor-logs \\
    --container-name ocpp-csms-prod
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
        "--monitor-logs",
        action="store_true",
        help="启用日志监控"
    )
    parser.add_argument(
        "--server-host",
        type=str,
        help="服务器主机地址（用于 SSH 连接）"
    )
    parser.add_argument(
        "--container-name",
        type=str,
        default="ocpp-csms-prod",
        help="Docker 容器名称"
    )
    parser.add_argument(
        "--use-ssh",
        action="store_true",
        help="使用 SSH 连接服务器"
    )
    parser.add_argument(
        "--ssh-user",
        type=str,
        default="root",
        help="SSH 用户名"
    )
    parser.add_argument(
        "--ssh-key",
        type=str,
        help="SSH 私钥路径"
    )
    
    args = parser.parse_args()
    
    # 创建日志监控器（如果启用）
    log_monitor = None
    if args.monitor_logs:
        server_host = args.server_host or args.server.split("://")[1].split(":")[0]
        log_monitor = LogMonitor(
            server_host=server_host,
            container_name=args.container_name,
            use_ssh=args.use_ssh,
            ssh_user=args.ssh_user,
            ssh_key=args.ssh_key
        )
        print("✓ 日志监控已配置")
    
    tester = OCPPComplianceTester(args.server, args.charge_point_id, log_monitor)
    tester.run_all_tests()


if __name__ == "__main__":
    main()

