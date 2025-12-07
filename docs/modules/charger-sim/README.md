# Charger Simulator - 充电桩模拟器

OCPP 1.6 充电桩模拟器，支持 WebSocket 和 MQTT 协议。

## 功能特性

- ✅ WebSocket 模拟器
- ✅ MQTT 模拟器
- ✅ 交互式控制
- ✅ 完整 OCPP 1.6 协议支持
- ✅ 自动生成二维码

## 快速开始

### 安装依赖

```bash
cd charger-sim
pip install -r requirements.txt
```

### WebSocket 模拟器

```bash
# 基本用法
python ocpp_simulator.py --id CP-001

# 交互式控制
python interactive.py --id CP-001

# 设置位置
python interactive.py --id CP-001 --lat 39.9 --lng 116.4 --address "北京市"
```

### MQTT 模拟器

```bash
# 确保 MQTT broker 运行
docker run -it -p 1883:1883 eclipse-mosquitto

# 运行模拟器
python mqtt_simulator.py --id CP-MQTT-001
```

## 依赖

- Python 3.10+
- websockets
- paho-mqtt
- qrcode

## 许可证

[您的许可证]
