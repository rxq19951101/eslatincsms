#!/usr/bin/env python3
#
# 设置并测试真实充电桩的完整流程
# 1. 添加设备信息到服务器
# 2. 连接MQTT并运行
# 3. 使用测试脚本测试功能
#

import argparse
import requests
import json
import sys
import time
import subprocess
import random
from typing import Optional

class RealChargerSetup:
    """真实充电桩设置和测试"""
    
    @staticmethod
    def generate_serial_number() -> str:
        """生成15位随机序列号"""
        # 生成15位数字序列号
        return ''.join([str(random.randint(0, 9)) for _ in range(15)])
    
    def __init__(self, server_url: str, serial_number: Optional[str] = None, type_code: str = "zcf"):
        self.server_url = server_url.rstrip('/')
        # 如果未提供序列号，自动生成
        if serial_number is None:
            serial_number = self.generate_serial_number()
            print(f"自动生成序列号: {serial_number}")
        self.serial_number = serial_number
        self.type_code = type_code
        self.base_url = f"{self.server_url}/api/v1"
        
    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 80)
        print(title)
        print("=" * 80)
    
    def step1_add_device(self) -> Optional[dict]:
        """步骤1: 添加设备信息到服务器"""
        self.print_header("步骤 1: 添加设备信息到服务器")
        
        payload = {
            "serial_number": self.serial_number,
            "device_type_code": self.type_code
        }
        
        try:
            print(f"设备序列号: {self.serial_number}")
            print(f"设备类型: {self.type_code}")
            print(f"\n正在添加设备到服务器: {self.server_url}")
            
            response = requests.post(
                f"{self.base_url}/devices",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 201:
                device_info = response.json()
                print("✓ 设备添加成功")
                print(f"\n设备信息:")
                print(f"  序列号: {device_info.get('serial_number')}")
                print(f"  类型: {device_info.get('device_type_code')}")
                print(f"  MQTT客户端ID: {device_info.get('mqtt_client_id')}")
                print(f"  MQTT用户名: {device_info.get('mqtt_username')}")
                print(f"  MQTT密码: {device_info.get('mqtt_password')}")
                print(f"  状态: {'激活' if device_info.get('is_active') else '未激活'}")
                return device_info
            elif response.status_code == 400:
                error = response.json()
                if "已存在" in error.get("detail", ""):
                    print("⚠ 设备已存在，获取设备信息...")
                    # 获取现有设备信息
                    response = requests.get(
                        f"{self.base_url}/devices/{self.serial_number}",
                        timeout=10
                    )
                    if response.status_code == 200:
                        device_info = response.json()
                        print("✓ 获取设备信息成功")
                        print(f"\n设备信息:")
                        print(f"  序列号: {device_info.get('serial_number')}")
                        print(f"  类型: {device_info.get('device_type_code')}")
                        print(f"  MQTT客户端ID: {device_info.get('mqtt_client_id')}")
                        print(f"  MQTT用户名: {device_info.get('mqtt_username')}")
                        print(f"  MQTT密码: {device_info.get('mqtt_password')}")
                        return device_info
                else:
                    print(f"✗ 添加设备失败: {error.get('detail', '未知错误')}")
                    return None
            else:
                print(f"✗ 添加设备失败: HTTP {response.status_code}")
                try:
                    error = response.json()
                    print(f"  错误: {error}")
                except:
                    print(f"  错误: {response.text}")
                return None
        except Exception as e:
            print(f"✗ 请求失败: {e}")
            return None
    
    def step2_get_mqtt_config(self, device_info: dict) -> Optional[dict]:
        """步骤2: 获取MQTT配置信息"""
        self.print_header("步骤 2: 获取MQTT配置")
        
        # 从设备信息中提取MQTT配置
        mqtt_config = {
            "client_id": device_info.get("mqtt_client_id"),
            "username": device_info.get("mqtt_username"),
            "password": device_info.get("mqtt_password"),
            "type_code": device_info.get("device_type_code"),
            "serial_number": device_info.get("serial_number")
        }
        
        print("MQTT 配置:")
        print(f"  客户端ID: {mqtt_config['client_id']}")
        print(f"  用户名: {mqtt_config['username']}")
        print(f"  密码: {mqtt_config['password']}")
        print(f"  设备类型: {mqtt_config['type_code']}")
        print(f"  序列号: {mqtt_config['serial_number']}")
        
        # 构建topic
        mqtt_config["up_topic"] = f"{mqtt_config['type_code']}/{mqtt_config['serial_number']}/user/up"
        mqtt_config["down_topic"] = f"{mqtt_config['type_code']}/{mqtt_config['serial_number']}/user/down"
        
        print(f"\nTopic 配置:")
        print(f"  发送主题: {mqtt_config['up_topic']}")
        print(f"  接收主题: {mqtt_config['down_topic']}")
        
        return mqtt_config
    
    def step3_connect_mqtt(self, mqtt_config: dict, mqtt_broker: str = "47.236.134.99", mqtt_port: int = 1883):
        """步骤3: 连接MQTT并运行"""
        self.print_header("步骤 3: 连接MQTT并运行")
        
        print(f"MQTT Broker: {mqtt_broker}:{mqtt_port}")
        print(f"设备序列号: {self.serial_number}")
        print("\n正在启动MQTT连接...")
        print("提示: 按 Ctrl+C 停止连接")
        print("=" * 80)
        
        # 使用持续运行的模拟器脚本
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        cmd = [
            "python3",
            os.path.join(script_dir, "run_real_charger_simulator.py"),
            "--broker", mqtt_broker,
            "--port", str(mqtt_port),
            "--client-id", mqtt_config["client_id"],
            "--username", mqtt_config["username"],
            "--password", mqtt_config["password"],
            "--type-code", mqtt_config["type_code"],
            "--serial-number", mqtt_config["serial_number"],
            "--up-topic", mqtt_config["up_topic"],
            "--down-topic", mqtt_config["down_topic"]
        ]
        
        try:
            # 运行MQTT连接脚本
            subprocess.run(cmd)
        except KeyboardInterrupt:
            print("\n连接已停止")
        except Exception as e:
            print(f"\n✗ 连接失败: {e}")
    
    def step4_test_functions(self, charge_point_id: Optional[str] = None):
        """步骤4: 使用测试脚本测试功能"""
        self.print_header("步骤 4: 测试充电桩功能")
        
        if not charge_point_id:
            charge_point_id = self.serial_number
        
        print(f"充电桩ID: {charge_point_id}")
        print(f"服务器: {self.server_url}")
        print("\n正在运行功能测试...")
        print("=" * 80)
        
        # 构建命令
        cmd = [
            "python3",
            "test_charge_point_functions.py",
            "--server", self.server_url,
            "--charge-point-id", charge_point_id
        ]
        
        try:
            subprocess.run(cmd, cwd="charger-sim")
        except Exception as e:
            print(f"\n✗ 测试失败: {e}")
    
    def run_full_setup(self, mqtt_broker: str = "47.236.134.99", mqtt_port: int = 1883, 
                       skip_connection: bool = False, skip_test: bool = False):
        """运行完整设置流程"""
        print("\n" + "=" * 80)
        print("真实充电桩设置和测试流程")
        print("=" * 80)
        print(f"服务器: {self.server_url}")
        print(f"设备序列号: {self.serial_number}")
        print(f"设备类型: {self.type_code}")
        print("=" * 80)
        
        # 步骤1: 添加设备
        device_info = self.step1_add_device()
        if not device_info:
            print("\n✗ 设备添加失败，无法继续")
            return False
        
        time.sleep(1)
        
        # 步骤2: 获取MQTT配置
        mqtt_config = self.step2_get_mqtt_config(device_info)
        if not mqtt_config:
            print("\n✗ 获取MQTT配置失败，无法继续")
            return False
        
        time.sleep(1)
        
        # 步骤3: 连接MQTT（如果不需要跳过）
        if not skip_connection:
            print("\n提示: 正在启动MQTT连接...")
            print("请等待设备连接成功并发送 BootNotification 后，再运行测试")
            print("按 Ctrl+C 停止连接")
            time.sleep(2)  # 给用户2秒时间看到提示
            self.step3_connect_mqtt(mqtt_config, mqtt_broker, mqtt_port)
        else:
            print("\n跳过MQTT连接步骤")
            print(f"\n手动连接命令:")
            print(f"python3 charger-sim/test_remote_mqtt_ocpp.py \\")
            print(f"  --broker {mqtt_broker} \\")
            print(f"  --port {mqtt_port} \\")
            print(f"  --client-id {mqtt_config['client_id']} \\")
            print(f"  --username {mqtt_config['username']} \\")
            print(f"  --password {mqtt_config['password']} \\")
            print(f"  --type-code {mqtt_config['type_code']} \\")
            print(f"  --serial-number {mqtt_config['serial_number']} \\")
            print(f"  --up-topic {mqtt_config['up_topic']} \\")
            print(f"  --down-topic {mqtt_config['down_topic']}")
        
        # 步骤4: 测试功能（如果不需要跳过）
        if not skip_test:
            print("\n提示: 功能测试步骤已跳过（需要在设备连接后手动运行）")
            print(f"\n手动测试命令:")
            print(f"python3 charger-sim/test_charge_point_functions.py \\")
            print(f"  --server {self.server_url} \\")
            print(f"  --charge-point-id {self.serial_number}")
        else:
            print("\n跳过功能测试步骤")
            print(f"\n手动测试命令:")
            print(f"python3 charger-sim/test_charge_point_functions.py \\")
            print(f"  --server {self.server_url} \\")
            print(f"  --charge-point-id {self.serial_number}")
        
        print("\n" + "=" * 80)
        print("设置完成！")
        print("=" * 80)
        return True


def main():
    parser = argparse.ArgumentParser(
        description="设置并测试真实充电桩的完整流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 完整流程（自动生成序列号 -> 添加设备 -> 连接 -> 测试）
  python setup_and_test_real_charger.py \\
    --server http://47.236.134.99:9000 \\
    --type-code zcf
  
  # 使用指定序列号
  python setup_and_test_real_charger.py \\
    --server http://47.236.134.99:9000 \\
    --serial 861076087029615 \\
    --type-code zcf
  
  # 只添加设备，不连接和测试
  python setup_and_test_real_charger.py \\
    --server http://47.236.134.99:9000 \\
    --skip-connection \\
    --skip-test
        """
    )
    
    parser.add_argument(
        "--server",
        type=str,
        default="http://47.236.134.99:9000",
        help="CSMS 服务器地址"
    )
    parser.add_argument(
        "--serial",
        type=str,
        default=None,
        help="设备序列号（15位，如果不提供则自动生成）"
    )
    parser.add_argument(
        "--type-code",
        type=str,
        default="zcf",
        help="设备类型代码（默认: zcf）"
    )
    parser.add_argument(
        "--mqtt-broker",
        type=str,
        default="47.236.134.99",
        help="MQTT Broker 地址（默认: 47.236.134.99）"
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=1883,
        help="MQTT Broker 端口（默认: 1883）"
    )
    parser.add_argument(
        "--skip-connection",
        action="store_true",
        help="跳过MQTT连接步骤"
    )
    parser.add_argument(
        "--skip-test",
        action="store_true",
        help="跳过功能测试步骤"
    )
    
    args = parser.parse_args()
    
    # 如果提供了序列号，验证长度
    if args.serial and len(args.serial) != 15:
        print(f"✗ 错误: 设备序列号必须是15位，当前为 {len(args.serial)} 位")
        sys.exit(1)
    
    setup = RealChargerSetup(
        server_url=args.server,
        serial_number=args.serial,
        type_code=args.type_code
    )
    
    setup.run_full_setup(
        mqtt_broker=args.mqtt_broker,
        mqtt_port=args.mqtt_port,
        skip_connection=args.skip_connection,
        skip_test=args.skip_test
    )


if __name__ == "__main__":
    main()

