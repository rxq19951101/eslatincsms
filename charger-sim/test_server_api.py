#!/usr/bin/env python3
#
# 脚本2：测试服务器API
# - 选择IP地址测试服务器
# - 测试指定charge_id的GetConfiguration
# - 测试指定charge_id的RemoteStartTransaction
#

import requests
import json
import sys
from typing import Optional, Dict, Any


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
    parser.add_argument("--test", type=str, choices=["getconf", "remotestart", "both"], default="both",
                        help="测试类型: getconf, remotestart, both (默认: both)")
    
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
    
    if args.test in ["getconf", "both"]:
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
    
    if args.test in ["remotestart", "both"]:
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
    
    # 总结
    print("=" * 60)
    print("测试总结")
    print("=" * 60)
    
    if "get_configuration" in results:
        result = results["get_configuration"]
        status = "✓ 成功" if result.get("success") else "✗ 失败"
        print(f"GetConfiguration: {status}")
    
    if "remote_start" in results:
        result = results["remote_start"]
        status = "✓ 成功" if result.get("success") else "✗ 失败"
        print(f"RemoteStartTransaction: {status}")
    
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

