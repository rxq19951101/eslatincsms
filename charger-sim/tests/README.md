# 充电桩模拟器测试

## 测试结构

```
tests/
├── __init__.py
├── test_user_behavior_simulator.py  # 用户行为模拟器测试
└── test_charging_scenarios.py       # 充电场景测试
```

## 运行测试

### 方法1: 使用测试脚本（推荐）

```bash
cd charger-sim
./tests/run_tests.sh
```

### 方法2: 直接使用pytest

```bash
cd charger-sim
pytest tests/ -v
```

### 方法3: 运行特定测试文件

```bash
cd charger-sim
pytest tests/test_user_behavior_simulator.py -v
```

## 测试覆盖范围

### 用户行为模拟器测试
- ✅ 用户行为创建和管理
- ✅ 模拟器初始化
- ✅ 用户行为队列
- ✅ 完整充电流程模拟
- ✅ 计量值计算
- ✅ 状态转换
- ✅ 远程启动/停止交易处理
- ✅ 计量值循环

### 充电场景测试
- ✅ 快速充电场景（15分钟）
- ✅ 正常充电场景（30分钟）
- ✅ 长时间充电场景（60分钟）
- ✅ 高功率充电（11kW）
- ✅ 低功率充电（3.7kW）
- ✅ 多用户排队充电
- ✅ 远程停止充电
- ✅ 充电统计信息

## 使用用户行为模拟器

### 基本用法

```bash
cd charger-sim
python3 user_behavior_simulator.py --id CP-USER-001
```

### 自动生成用户行为

```bash
# 自动生成5个用户，每个用户间隔60秒
python3 user_behavior_simulator.py \
  --id CP-USER-001 \
  --auto-users 5 \
  --user-interval 60
```

### 指定充电功率

```bash
# 使用11kW充电功率
python3 user_behavior_simulator.py \
  --id CP-USER-001 \
  --power 11.0
```

## 用户行为流程

1. **用户扫码** - 模拟用户扫描充电桩二维码
2. **授权请求** - 发送Authorize消息验证用户ID标签
3. **插枪准备** - 状态变为Preparing
4. **开始充电** - 发送StartTransaction，状态变为Charging
5. **充电过程** - 定期发送MeterValues（每10秒）
6. **停止充电** - 用户拔枪，发送StopTransaction
7. **充电完成** - 状态恢复为Available，生成统计信息

## 注意事项

1. 测试使用Mock MQTT客户端，不会实际连接MQTT broker
2. 充电时长测试使用较短的1分钟，实际使用可以设置更长
3. 计量值计算考虑了功率波动（±2%随机变化）
4. 所有时间相关的测试都允许一定的误差范围

