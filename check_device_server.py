#!/usr/bin/env python3
#
# 查询服务器上的设备信息并验证
#

import requests
import json
import sys

# 服务器配置
SERVER_URL = "http://47.236.134.99:9000"
SERIAL_NUMBER = "861076087029615"

def check_device():
    """查询设备信息"""
    url = f"{SERVER_URL}/api/v1/devices/{SERIAL_NUMBER}"
    
    print("=" * 60)
    print("查询服务器设备信息")
    print("=" * 60)
    print(f"服务器地址: {SERVER_URL}")
    print(f"设备序列号: {SERIAL_NUMBER}")
    print("=" * 60)
    print()
    
    try:
        print(f"📤 正在查询设备信息...")
        print(f"   URL: {url}")
        print()
        
        response = requests.get(
            url,
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        
        print(f"📥 收到响应:")
        print(f"   状态码: {response.status_code}")
        print()
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ 设备查询成功！")
                print("=" * 60)
                print("设备信息:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                print("=" * 60)
                print()
                
                # 验证返回的数据
                print("🔍 数据验证:")
                print("-" * 60)
                
                # 验证必需字段
                checks = {
                    "serial_number": ("861076087029615", "设备序列号"),
                    "device_type_code": ("zcf", "设备类型代码"),
                    "mqtt_client_id": ("zcf&861076087029615", "MQTT客户端ID"),
                    "mqtt_username": ("861076087029615", "MQTT用户名"),
                    "mqtt_password": (None, "MQTT密码（12位）"),
                }
                
                all_valid = True
                for field, (expected, desc) in checks.items():
                    if field in data:
                        value = data[field]
                        print(f"  ✅ {desc}: {value}")
                        
                        # 特殊验证
                        if expected and value != expected:
                            print(f"     ❌ 值不匹配，期望: {expected}")
                            all_valid = False
                        elif expected:
                            print(f"     ✅ 值匹配: {expected}")
                        
                        if field == "mqtt_password":
                            if len(value) == 12:
                                print(f"     ✅ 密码长度正确: 12位")
                            else:
                                print(f"     ❌ 密码长度错误，期望12位，实际: {len(value)}")
                                all_valid = False
                    else:
                        print(f"  ❌ 缺少字段: {desc}")
                        all_valid = False
                
                print("-" * 60)
                if all_valid:
                    print("✅ 所有数据验证通过！")
                else:
                    print("⚠️  部分数据验证失败")
                
                print()
                print("=" * 60)
                print("📋 MQTT连接信息:")
                print("=" * 60)
                print(f"  Broker地址: 47.236.134.99:1883")
                print(f"  Client ID: {data.get('mqtt_client_id')}")
                print(f"  Username: {data.get('mqtt_username')}")
                print(f"  Password: {data.get('mqtt_password')}")
                print(f"  发送Topic: {data.get('device_type_code')}/{data.get('serial_number')}/user/up")
                print(f"  接收Topic: {data.get('device_type_code')}/{data.get('serial_number')}/user/down")
                print("=" * 60)
                print()
                
                # 验证MQTT连接信息格式
                print("🔌 MQTT连接信息格式验证:")
                print("-" * 60)
                
                client_id = data.get('mqtt_client_id', '')
                username = data.get('mqtt_username', '')
                password = data.get('mqtt_password', '')
                type_code = data.get('device_type_code', '')
                serial = data.get('serial_number', '')
                
                # 验证Client ID格式
                expected_client_id = f"{type_code}&{serial}"
                if client_id == expected_client_id:
                    print(f"  ✅ Client ID格式正确: {client_id}")
                else:
                    print(f"  ❌ Client ID格式错误")
                    print(f"     期望: {expected_client_id}")
                    print(f"     实际: {client_id}")
                
                # 验证Username格式
                if username == serial:
                    print(f"  ✅ Username格式正确: {username}")
                else:
                    print(f"  ❌ Username格式错误")
                    print(f"     期望: {serial}")
                    print(f"     实际: {username}")
                
                # 验证密码长度
                if len(password) == 12:
                    print(f"  ✅ Password长度正确: {len(password)}位")
                else:
                    print(f"  ❌ Password长度错误: {len(password)}位（期望12位）")
                
                # 验证Topic格式
                expected_up_topic = f"{type_code}/{serial}/user/up"
                expected_down_topic = f"{type_code}/{serial}/user/down"
                print(f"  ✅ 发送Topic: {expected_up_topic}")
                print(f"  ✅ 接收Topic: {expected_down_topic}")
                
                print("-" * 60)
                print()
                
                return True, data
            except json.JSONDecodeError as e:
                print(f"❌ JSON解析失败: {e}")
                print(f"响应内容: {response.text}")
                return False, None
        elif response.status_code == 404:
            print(f"❌ 设备不存在: {SERIAL_NUMBER}")
            return False, None
        else:
            print(f"❌ 查询失败")
            print(f"状态码: {response.status_code}")
            try:
                error_data = response.json()
                print(f"错误信息: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"响应内容: {response.text}")
            return False, None
            
    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到服务器: {SERVER_URL}")
        print("请检查:")
        print("  1. 服务器是否运行")
        print("  2. 网络连接是否正常")
        print("  3. 防火墙是否允许访问")
        return False, None
    except requests.exceptions.Timeout:
        print(f"❌ 请求超时: {SERVER_URL}")
        return False, None
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False, None

if __name__ == "__main__":
    success, data = check_device()
    sys.exit(0 if success else 1)

