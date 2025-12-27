#!/usr/bin/env python3
#
# 脚本2：测试服务器API
# - 选择IP地址测试服务器
# - 查询已连接的充电桩列表
# - 测试指定charge_id的GetConfiguration
# - 测试指定charge_id的ChangeConfiguration（修改配置，如心跳间隔）
# - 测试指定charge_id的RemoteStartTransaction
# - 测试指定charge_id的RemoteStopTransaction
# - 测试指定charge_id的Reset（软重启/硬重启）
#

import requests
import json
import sys
from typing import Optional, Dict, Any, List


class ServerTester:
    """服务器API测试器"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.api_base = f"{self.base_url}/api/v1/ocpp"
    
    def test_get_configuration(self, charge_point_id: str, keys: Optional[list] = None) -> Dict[str, Any]:
        """测试GetConfiguration"""
        url = f"{self.api_base}/getConfiguration"
        payload = {
            "chargePointId": charge_point_id
        }
        if keys:
            payload["keys"] = keys
        
        print(f"测试 GetConfiguration")
        print(f"  URL: {url}")
        print(f"  Charge Point ID: {charge_point_id}")
        if keys:
            print(f"  Keys: {keys}")
        print()
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            print(f"  状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"  响应:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                print()
                return {"success": True, "data": result}
            else:
                print(f"  错误响应:")
                try:
                    error_data = response.json()
                    print(json.dumps(error_data, indent=2, ensure_ascii=False))
                except:
                    print(response.text)
                print()
                return {"success": False, "status_code": response.status_code, "error": response.text}
        except requests.exceptions.RequestException as e:
            print(f"  ✗ 请求失败: {e}")
            print()
            return {"success": False, "error": str(e)}
    
    def test_remote_start_transaction(self, charge_point_id: str, id_tag: str = "TAG001", connector_id: int = 1) -> Dict[str, Any]:
        """测试RemoteStartTransaction"""
        url = f"{self.api_base}/remoteStart"
        payload = {
            "chargePointId": charge_point_id,
            "idTag": id_tag,
            "connectorId": connector_id
        }
        
        print(f"测试 RemoteStartTransaction")
        print(f"  URL: {url}")
        print(f"  Charge Point ID: {charge_point_id}")
        print(f"  ID Tag: {id_tag}")
        print(f"  Connector ID: {connector_id}")
        print()
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            print(f"  状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"  响应:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                print()
                return {"success": True, "data": result}
            else:
                print(f"  错误响应:")
                try:
                    error_data = response.json()
                    print(json.dumps(error_data, indent=2, ensure_ascii=False))
                except:
                    print(response.text)
                print()
                return {"success": False, "status_code": response.status_code, "error": response.text}
        except requests.exceptions.RequestException as e:
            print(f"  ✗ 请求失败: {e}")
            print()
            return {"success": False, "error": str(e)}
    
    def test_remote_stop_transaction(self, charge_point_id: str, transaction_id: int) -> Dict[str, Any]:
        """测试RemoteStopTransaction"""
        url = f"{self.api_base}/remoteStop"
        payload = {
            "chargePointId": charge_point_id,
            "transactionId": transaction_id
        }
        
        print(f"测试 RemoteStopTransaction")
        print(f"  URL: {url}")
        print(f"  Charge Point ID: {charge_point_id}")
        print(f"  Transaction ID: {transaction_id}")
        print()
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            print(f"  状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"  响应:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                print()
                return {"success": True, "data": result}
            else:
                print(f"  错误响应:")
                try:
                    error_data = response.json()
                    print(json.dumps(error_data, indent=2, ensure_ascii=False))
                except:
                    print(response.text)
                print()
                return {"success": False, "status_code": response.status_code, "error": response.text}
        except requests.exceptions.RequestException as e:
            print(f"  ✗ 请求失败: {e}")
            print()
            return {"success": False, "error": str(e)}
    
    def test_reset(self, charge_point_id: str, reset_type: str = "Soft") -> Dict[str, Any]:
        """测试Reset（软重启或硬重启）"""
        url = f"{self.api_base}/reset"
        payload = {
            "chargePointId": charge_point_id,
            "type": reset_type
        }
        
        print(f"测试 Reset")
        print(f"  URL: {url}")
        print(f"  Charge Point ID: {charge_point_id}")
        print(f"  Reset Type: {reset_type} ({'软重启' if reset_type == 'Soft' else '硬重启' if reset_type == 'Hard' else reset_type})")
        print()
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            print(f"  状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"  响应:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                print()
                return {"success": True, "data": result}
            else:
                print(f"  错误响应:")
                try:
                    error_data = response.json()
                    print(json.dumps(error_data, indent=2, ensure_ascii=False))
                except:
                    print(response.text)
                print()
                return {"success": False, "status_code": response.status_code, "error": response.text}
        except requests.exceptions.RequestException as e:
            print(f"  ✗ 请求失败: {e}")
            print()
            return {"success": False, "error": str(e)}
    
    def test_change_configuration(self, charge_point_id: str, key: str, value: str) -> Dict[str, Any]:
        """测试ChangeConfiguration（修改配置）"""
        url = f"{self.api_base}/changeConfiguration"
        payload = {
            "chargePointId": charge_point_id,
            "key": key,
            "value": value
        }
        
        print(f"测试 ChangeConfiguration")
        print(f"  URL: {url}")
        print(f"  Charge Point ID: {charge_point_id}")
        print(f"  Configuration Key: {key}")
        print(f"  Configuration Value: {value}")
        print()
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            print(f"  状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"  响应:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                print()
                return {"success": True, "data": result}
            else:
                print(f"  错误响应:")
                try:
                    error_data = response.json()
                    print(json.dumps(error_data, indent=2, ensure_ascii=False))
                except:
                    print(response.text)
                print()
                return {"success": False, "status_code": response.status_code, "error": response.text}
        except requests.exceptions.RequestException as e:
            print(f"  ✗ 请求失败: {e}")
            print()
            return {"success": False, "error": str(e)}
    
    def get_connected_chargers(self) -> List[str]:
        """获取所有已连接的充电桩ID列表"""
        url = f"{self.api_base}/connected"
        
        print(f"获取已连接的充电桩列表")
        print(f"  URL: {url}")
        print()
        
        try:
            response = requests.get(url, timeout=10)
            print(f"  状态码: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                connected_chargers = result.get("connected_chargers", [])
                count = result.get("count", 0)
                sources = result.get("sources", {})
                
                print(f"  响应:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                print()
                print(f"  已连接充电桩数量: {count}")
                if sources.get("websocket"):
                    print(f"  WebSocket连接: {len(sources['websocket'])} 个")
                if sources.get("mqtt"):
                    print(f"  MQTT连接: {len(sources['mqtt'])} 个")
                print()
                
                return connected_chargers
            else:
                print(f"  错误响应:")
                try:
                    error_data = response.json()
                    print(json.dumps(error_data, indent=2, ensure_ascii=False))
                except:
                    print(response.text)
                print()
                return []
        except requests.exceptions.RequestException as e:
            print(f"  ✗ 请求失败: {e}")
            print()
            return []
    
    def test_health(self) -> bool:
        """测试服务器健康状态"""
        url = f"{self.base_url}/health"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"✓ 服务器健康检查通过: {url}")
                return True
            else:
                print(f"✗ 服务器健康检查失败: 状态码 {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"✗ 无法连接到服务器: {e}")
            return False


def select_server() -> str:
    """选择服务器IP"""
    print("=" * 60)
    print("选择测试服务器")
    print("=" * 60)
    print()
    print("预设服务器:")
    print("  1. localhost:9000 (本地)")
    print("  2. 47.236.134.99:9000 (远程)")
    print("  3. 自定义")
    print()
    
    choice = input("请选择 (1/2/3): ").strip()
    
    if choice == "1":
        return "http://localhost:9000"
    elif choice == "2":
        return "http://47.236.134.99:9000"
    elif choice == "3":
        ip = input("请输入IP地址 (例如: 192.168.1.100): ").strip()
        port = input("请输入端口 (默认: 9000): ").strip() or "9000"
        return f"http://{ip}:{port}"
    else:
        print("无效选择，使用默认: localhost:9000")
        return "http://localhost:9000"


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="服务器API测试工具")
    parser.add_argument("--server", type=str, help="服务器地址 (例如: http://localhost:9000)")
    parser.add_argument("--charge-id", type=str, help="Charge Point ID")
    parser.add_argument("--test", type=str, choices=["getconf", "changeconf", "remotestart", "remotestop", "reset", "connected", "both", "all"], default="both",
                        help="测试类型: getconf, changeconf, remotestart, remotestop, reset, connected(查询已连接充电桩), both(包含getconf和remotestart), all(包含所有) (默认: both)")
    parser.add_argument("--list-connected", action="store_true", help="查询已连接的充电桩列表（不执行其他测试）")
    
    args = parser.parse_args()
    
    # 选择服务器
    if args.server:
        base_url = args.server
    else:
        base_url = select_server()
    
    print()
    print("=" * 60)
    print(f"服务器地址: {base_url}")
    print("=" * 60)
    print()
    
    # 创建测试器
    tester = ServerTester(base_url)
    
    # 测试健康状态
    print("测试服务器健康状态...")
    if not tester.test_health():
        print("\n服务器不可用，请检查服务器地址和连接")
        sys.exit(1)
    print()
    
    # 如果只是查询已连接充电桩，直接执行并退出
    if args.list_connected or args.test == "connected":
        print("=" * 60)
        print("查询已连接的充电桩")
        print("=" * 60)
        print()
        
        connected_chargers = tester.get_connected_chargers()
        
        if connected_chargers:
            print("=" * 60)
            print(f"找到 {len(connected_chargers)} 个已连接的充电桩:")
            print("=" * 60)
            for i, charger_id in enumerate(connected_chargers, 1):
                print(f"  {i}. {charger_id}")
            print("=" * 60)
        else:
            print("=" * 60)
            print("没有找到已连接的充电桩")
            print("=" * 60)
        
        return
    
    # 获取Charge Point ID
    if args.charge_id:
        charge_point_id = args.charge_id
    else:
        charge_point_id = input("请输入Charge Point ID (例如: 9999): ").strip()
        if not charge_point_id:
            print("Charge Point ID不能为空")
            sys.exit(1)
    
    print()
    print("=" * 60)
    print(f"Charge Point ID: {charge_point_id}")
    print("=" * 60)
    print()
    
    # 执行测试
    results = {}
    
    if args.test in ["getconf", "both", "all"]:
        print("=" * 60)
        print("测试 1: GetConfiguration")
        print("=" * 60)
        print()
        
        # 询问是否指定keys
        use_keys = input("是否指定配置项keys? (y/n，默认n): ").strip().lower()
        keys = None
        if use_keys == 'y':
            keys_input = input("请输入keys (用逗号分隔，例如: HeartbeatInterval,MeterValueSampleInterval): ").strip()
            if keys_input:
                keys = [k.strip() for k in keys_input.split(",")]
        
        results["get_configuration"] = tester.test_get_configuration(charge_point_id, keys)
        print()
    
    if args.test in ["changeconf", "all"]:
        print("=" * 60)
        print("测试 1.5: ChangeConfiguration")
        print("=" * 60)
        print()
        
        # 默认修改心跳间隔
        print("常用配置项:")
        print("  1. HeartbeatInterval (心跳间隔，单位：秒)")
        print("  2. MeterValueSampleInterval (计量值采样间隔，单位：秒)")
        print("  3. WebSocketPingInterval (WebSocket Ping间隔，单位：秒)")
        print("  4. 自定义")
        print()
        
        choice = input("请选择配置项 (1/2/3/4，默认1): ").strip() or "1"
        
        if choice == "1":
            key = "HeartbeatInterval"
            default_value = "30"
        elif choice == "2":
            key = "MeterValueSampleInterval"
            default_value = "60"
        elif choice == "3":
            key = "WebSocketPingInterval"
            default_value = "60"
        else:
            key = input("请输入配置项Key: ").strip()
            default_value = ""
        
        if not key:
            print("配置项Key不能为空，跳过ChangeConfiguration测试")
        else:
            value_input = input(f"请输入配置项Value (默认: {default_value}): ").strip()
            value = value_input if value_input else default_value
            
            if value:
                results["change_configuration"] = tester.test_change_configuration(charge_point_id, key, value)
            else:
                print("配置项Value不能为空，跳过ChangeConfiguration测试")
        print()
    
    if args.test in ["remotestart", "both", "all"]:
        print("=" * 60)
        print("测试 2: RemoteStartTransaction")
        print("=" * 60)
        print()
        
        # 询问参数
        id_tag = input("请输入ID Tag (默认: TAG001): ").strip() or "TAG001"
        connector_id_input = input("请输入Connector ID (默认: 1): ").strip() or "1"
        try:
            connector_id = int(connector_id_input)
        except ValueError:
            connector_id = 1
        
        results["remote_start"] = tester.test_remote_start_transaction(charge_point_id, id_tag, connector_id)
        print()
    
    if args.test in ["remotestop", "all"]:
        print("=" * 60)
        print("测试 3: RemoteStopTransaction")
        print("=" * 60)
        print()
        
        # 询问参数
        transaction_id_input = input("请输入Transaction ID (必填): ").strip()
        if not transaction_id_input:
            print("Transaction ID不能为空，跳过RemoteStop测试")
        else:
            try:
                transaction_id = int(transaction_id_input)
                results["remote_stop"] = tester.test_remote_stop_transaction(charge_point_id, transaction_id)
            except ValueError:
                print("Transaction ID必须是整数，跳过RemoteStop测试")
        print()
    
    if args.test in ["reset", "all"]:
        print("=" * 60)
        print("测试 4: Reset")
        print("=" * 60)
        print()
        
        # 询问参数
        reset_type_input = input("请输入Reset类型 (Soft/Hard，默认: Soft): ").strip()
        reset_type = reset_type_input if reset_type_input in ["Soft", "Hard"] else "Soft"
        
        results["reset"] = tester.test_reset(charge_point_id, reset_type)
        print()
    
    # 总结
    print("=" * 60)
    print("测试总结")
    print("=" * 60)
    
    if "get_configuration" in results:
        result = results["get_configuration"]
        status = "✓ 成功" if result.get("success") else "✗ 失败"
        print(f"GetConfiguration: {status}")
    
    if "change_configuration" in results:
        result = results["change_configuration"]
        status = "✓ 成功" if result.get("success") else "✗ 失败"
        print(f"ChangeConfiguration: {status}")
    
    if "remote_start" in results:
        result = results["remote_start"]
        status = "✓ 成功" if result.get("success") else "✗ 失败"
        print(f"RemoteStartTransaction: {status}")
    
    if "remote_stop" in results:
        result = results["remote_stop"]
        status = "✓ 成功" if result.get("success") else "✗ 失败"
        print(f"RemoteStopTransaction: {status}")
    
    if "reset" in results:
        result = results["reset"]
        status = "✓ 成功" if result.get("success") else "✗ 失败"
        print(f"Reset: {status}")
    
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n\n程序出错: {e}")
        import traceback
        traceback.print_exc()

