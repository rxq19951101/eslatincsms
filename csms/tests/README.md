# CSMS 单元测试

## 测试结构

```
tests/
├── __init__.py
├── conftest.py                    # Pytest配置和共享fixtures
├── test_charge_point_service.py  # 充电桩服务测试
├── test_ocpp_message_handler.py  # OCPP消息处理测试
├── test_api_chargers.py          # API端点测试
├── test_api_ocpp_control.py      # OCPP控制API测试
├── test_database_models.py       # 数据库模型测试
├── test_main.py                  # 主应用测试
├── test_user_charging_flow.py     # 用户充电流程测试
├── test_integration_user_behavior.py  # 用户行为集成测试
└── test_database_queries.py      # 数据库查询测试
```

## 运行测试

### 运行所有测试

```bash
cd csms
./tests/run_tests.sh
```

或直接使用pytest：

```bash
cd csms
pytest tests/ -v
```

### 运行特定测试文件

```bash
# 运行用户充电流程测试
pytest tests/test_user_charging_flow.py -v

# 运行集成测试
pytest tests/test_integration_user_behavior.py -v

# 运行数据库查询测试
pytest tests/test_database_queries.py -v
```

### 运行特定测试类或方法

```bash
# 运行特定测试类
pytest tests/test_user_charging_flow.py::TestUserChargingFlow -v

# 运行特定测试方法
pytest tests/test_user_charging_flow.py::TestUserChargingFlow::test_complete_charging_flow -v
```

### 运行带标记的测试

```bash
# 运行异步测试
pytest tests/ -v -m asyncio

# 运行集成测试
pytest tests/ -v -m integration
```

## 测试覆盖范围

### 用户充电流程测试 (`test_user_charging_flow.py`)
- ✅ 完整用户充电流程（扫码→授权→开始→充电→停止）
- ✅ 计量值存储和查询
- ✅ 充电统计信息
- ✅ 设备事件记录

### 用户行为集成测试 (`test_integration_user_behavior.py`)
- ✅ 完整流程的数据库验证
- ✅ 使用正确的列名查询计量值（session_id）
- ✅ 数据完整性验证
- ✅ 通过transaction_id查询计量值

### 数据库查询测试 (`test_database_queries.py`)
- ✅ 验证meter_values表使用正确的列名（session_id）
- ✅ 验证外键关系
- ✅ 测试各种查询方式
- ✅ 测试关系访问

## 重要注意事项

### 列名使用

**正确的列名**: `session_id`
**错误的列名**: `charging_session_id` ❌

在查询meter_values表时，必须使用 `session_id` 列名：

```python
# ✅ 正确
meters = db.query(MeterValue).filter(
    MeterValue.session_id == session.id
).all()

# ❌ 错误
meters = db.query(MeterValue).filter(
    MeterValue.charging_session_id == session.id  # 这个列不存在！
).all()
```

### 数据库模型关系

```python
# ChargingSession 和 MeterValue 的关系
session.meter_values  # 通过关系访问计量值
meter.session  # 通过关系访问会话

# 外键列名
MeterValue.session_id  # 指向 ChargingSession.id
```

## 测试数据

测试使用内存SQLite数据库，每个测试都会：
1. 创建新的数据库表
2. 运行测试
3. 清理数据

测试数据通过fixtures提供：
- `sample_site`: 测试站点
- `sample_device_type`: 设备类型
- `sample_device`: 设备
- `sample_charge_point`: 充电桩
- `sample_evse`: EVSE
- `sample_evse_status`: EVSE状态

## 覆盖率报告

运行测试时会生成覆盖率报告：

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

查看HTML报告：

```bash
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

## 常见问题

### Q: 测试失败，提示列名不存在
A: 确保使用正确的列名 `session_id`，而不是 `charging_session_id`

### Q: 如何测试异步函数？
A: 使用 `@pytest.mark.asyncio` 装饰器，并使用 `async def` 定义测试函数

### Q: 如何测试数据库操作？
A: 使用 `db_session` fixture，它提供隔离的数据库会话

### Q: 如何验证数据已保存？
A: 在测试中查询数据库，验证记录是否存在且数据正确
