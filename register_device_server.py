#!/usr/bin/env python3
#
# 在服务器上注册设备并验证返回数据
#

import requests
import json
import sys

# 服务器配置
SERVER_URL = "http://47.236.134.99:9000"

# 设备信息
DEVICE_INFO = {
    "serial_number": "861076087029615",
    "device_type_code": "zcf"
}

def register_device():
    """注册设备到服务器"""
    url = f"{SERVER_URL}/api/v1/devices"
    
    print("=" * 60)
    print("设备注册到服务器")
    print("=" * 60)
    print(f"服务器地址: {SERVER_URL}")
    print(f"设备序列号: {DEVICE_INFO['serial_number']}")
    print(f"设备类型: {DEVICE_INFO['device_type_code']}")
    print("=" * 60)
    print()
    
    try:
        print(f"📤 正在发送注册请求...")
        print(f"   URL: {url}")
        print(f"   数据: {json.dumps(DEVICE_INFO, indent=2, ensure_ascii=False)}")
        print()
        
        response = requests.post(
            url,
            json=DEVICE_INFO,
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        
        print(f"📥 收到响应:")
        print(f"   状态码: {response.status_code}")
        print(f"   响应头: {dict(response.headers)}")
        print()
        
        if response.status_code == 201:
            try:
                data = response.json()
                print("✅ 设备注册成功！")
                print("=" * 60)
                print("返回的设备信息:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                print("=" * 60)
                print()
                
                # 验证返回的数据
                print("🔍 数据验证:")
                print("-" * 60)
                
                required_fields = [
                    "serial_number",
                    "device_type_code",
                    "mqtt_client_id",
                    "mqtt_username",
                    "mqtt_password"
                ]
                
                all_valid = True
                for field in required_fields:
                    if field in data:
                        value = data[field]
                        print(f"  ✅ {field}: {value}")
                        
                        # 特殊验证
                        if field == "mqtt_client_id":
                            expected = f"zcf&861076087029615"
                            if value == expected:
                                print(f"     ✅ 格式正确: {expected}")
                            else:
                                print(f"     ❌ 格式错误，期望: {expected}")
                                all_valid = False
                        
                        if field == "mqtt_username":
                            expected = "861076087029615"
                            if value == expected:
                                print(f"     ✅ 格式正确: {expected}")
                            else:
                                print(f"     ❌ 格式错误，期望: {expected}")
                                all_valid = False
                        
                        if field == "mqtt_password":
                            if len(value) == 12:
                                print(f"     ✅ 密码长度正确: 12位")
                            else:
                                print(f"     ❌ 密码长度错误，期望12位，实际: {len(value)}")
                                all_valid = False
                    else:
                        print(f"  ❌ 缺少字段: {field}")
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
                
                return True, data
            except json.JSONDecodeError as e:
                print(f"❌ JSON解析失败: {e}")
                print(f"响应内容: {response.text}")
                return False, None
        else:
            print(f"❌ 设备注册失败")
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
    success, data = register_device()
    sys.exit(0 if success else 1)

