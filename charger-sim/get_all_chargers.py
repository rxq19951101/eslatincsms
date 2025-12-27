#!/usr/bin/env python3
#
# 获取远程服务的所有连接充电桩信息
#

import requests
import json
import sys
from typing import Optional, Dict, Any, List


class ChargerInfoClient:
    """充电桩信息客户端"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.api_base = f"{self.base_url}/api/v1"
    
    def get_all_chargers(self) -> List[Dict[str, Any]]:
        """获取所有充电桩列表"""
        url = f"{self.api_base}/chargers"
        
        print(f"获取所有充电桩列表")
        print(f"  URL: {url}")
        print()
        
        try:
            response = requests.get(url, timeout=10)
            print(f"  状态码: {response.status_code}")
            
            if response.status_code == 200:
                chargers = response.json()
                print(f"  成功获取 {len(chargers)} 个充电桩")
                print()
                return chargers
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
    
    def get_charger_detail(self, charge_point_id: str) -> Optional[Dict[str, Any]]:
        """获取充电桩详情"""
        url = f"{self.api_base}/chargers/{charge_point_id}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"  获取充电桩 {charge_point_id} 详情失败: {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"  ✗ 请求失败: {e}")
            return None
    
    def get_connected_chargers(self) -> List[str]:
        """获取所有已连接的充电桩ID列表（通过健康检查端点）"""
        # 注意：这个方法可能需要根据实际的连接管理API来实现
        # 目前先返回所有充电桩的ID列表
        chargers = self.get_all_chargers()
        connected_ids = []
        for charger in chargers:
            if charger.get("id"):
                connected_ids.append(charger["id"])
        return connected_ids
    
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
    print("选择服务器")
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


def format_charger_info(charger: Dict[str, Any]) -> str:
    """格式化充电桩信息"""
    lines = []
    lines.append(f"  ID: {charger.get('id', 'N/A')}")
    lines.append(f"  厂商: {charger.get('vendor', 'N/A')}")
    lines.append(f"  型号: {charger.get('model', 'N/A')}")
    lines.append(f"  状态: {charger.get('status', 'N/A')}")
    
    if charger.get('last_seen'):
        lines.append(f"  最后在线: {charger['last_seen']}")
    
    location = charger.get('location', {})
    if location:
        lat = location.get('latitude')
        lng = location.get('longitude')
        if lat is not None and lng is not None:
            lines.append(f"  位置: ({lat}, {lng})")
        if location.get('address'):
            lines.append(f"  地址: {location['address']}")
    
    if charger.get('price_per_kwh'):
        lines.append(f"  价格: {charger['price_per_kwh']} COP/kWh")
    
    if charger.get('is_configured') is not None:
        lines.append(f"  已配置: {'是' if charger['is_configured'] else '否'}")
    
    return "\n".join(lines)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="获取远程服务的所有连接充电桩信息")
    parser.add_argument("--server", type=str, help="服务器地址 (例如: http://localhost:9000)")
    parser.add_argument("--detail", action="store_true", help="显示详细信息")
    parser.add_argument("--json", action="store_true", help="以JSON格式输出")
    parser.add_argument("--filter", type=str, choices=["configured", "unconfigured"], help="筛选类型: configured(已配置), unconfigured(未配置)")
    
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
    
    # 创建客户端
    client = ChargerInfoClient(base_url)
    
    # 测试健康状态
    print("测试服务器健康状态...")
    if not client.test_health():
        print("\n服务器不可用，请检查服务器地址和连接")
        sys.exit(1)
    print()
    
    # 获取所有充电桩
    filter_type = args.filter
    url = f"{client.api_base}/chargers"
    if filter_type:
        url += f"?filter_type={filter_type}"
    
    print("=" * 60)
    print(f"获取充电桩列表 (筛选: {filter_type or '全部'})")
    print("=" * 60)
    print()
    
    try:
        response = requests.get(url, timeout=10)
        print(f"状态码: {response.status_code}")
        print()
        
        if response.status_code == 200:
            chargers = response.json()
            
            if args.json:
                # JSON格式输出
                print(json.dumps(chargers, indent=2, ensure_ascii=False))
            else:
                # 格式化输出
                print(f"找到 {len(chargers)} 个充电桩:")
                print()
                
                for i, charger in enumerate(chargers, 1):
                    print(f"[{i}] {charger.get('id', 'N/A')}")
                    if args.detail:
                        print(format_charger_info(charger))
                    else:
                        # 简要信息
                        info_parts = []
                        if charger.get('vendor'):
                            info_parts.append(f"厂商: {charger['vendor']}")
                        if charger.get('status'):
                            info_parts.append(f"状态: {charger['status']}")
                        if charger.get('is_configured') is not None:
                            info_parts.append(f"已配置: {'是' if charger['is_configured'] else '否'}")
                        if info_parts:
                            print("  " + " | ".join(info_parts))
                    print()
                
                print("=" * 60)
                print(f"总计: {len(chargers)} 个充电桩")
                print("=" * 60)
        else:
            print(f"✗ 获取失败: {response.status_code}")
            try:
                error_data = response.json()
                print(json.dumps(error_data, indent=2, ensure_ascii=False))
            except:
                print(response.text)
            
    except requests.exceptions.RequestException as e:
        print(f"✗ 请求失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n\n程序出错: {e}")
        import traceback
        traceback.print_exc()

