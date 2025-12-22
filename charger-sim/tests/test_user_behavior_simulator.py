#!/usr/bin/env python3
#
# 用户行为模拟器单元测试
#

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from user_behavior_simulator import (
    UserBehaviorSimulator, UserBehavior, ChargerStatus
)


class TestUserBehavior:
    """用户行为测试类"""
    
    def test_user_behavior_creation(self):
        """测试创建用户行为"""
        behavior = UserBehavior("USER_001", "TAG_001", 30)
        
        assert behavior.user_id == "USER_001"
        assert behavior.id_tag == "TAG_001"
        assert behavior.charging_duration_minutes == 30
        assert behavior.start_time is None
        assert behavior.end_time is None
    
    def test_user_behavior_timing(self):
        """测试用户行为时间记录"""
        behavior = UserBehavior("USER_001", "TAG_001", 30)
        
        start = datetime.now(timezone.utc)
        behavior.start_time = start
        
        # 模拟30分钟后
        end = start.replace(minute=start.minute + 30)
        behavior.end_time = end
        
        duration = (behavior.end_time - behavior.start_time).total_seconds() / 60
        assert duration == 30


class TestUserBehaviorSimulator:
    """用户行为模拟器测试类"""
    
    @pytest.fixture
    def simulator(self):
        """创建模拟器实例"""
        with patch('paho.mqtt.client.Client'):
            sim = UserBehaviorSimulator(
                charger_id="CP-TEST-001",
                broker_host="localhost",
                broker_port=1883,
                type_code="zcf",
                serial_number="123456789012345",
                charging_power_kw=7.0
            )
            return sim
    
    def test_simulator_initialization(self, simulator):
        """测试模拟器初始化"""
        assert simulator.charger_id == "CP-TEST-001"
        assert simulator.serial_number == "123456789012345"
        assert simulator.charging_power_kw == 7.0
        assert simulator.status == ChargerStatus.UNAVAILABLE
        assert simulator.transaction_id is None
        assert simulator.meter_value == 0
    
    def test_add_user_behavior(self, simulator):
        """测试添加用户行为"""
        simulator.add_user_behavior("USER_001", "TAG_001", 30)
        
        assert len(simulator.user_behaviors) == 1
        behavior = simulator.user_behaviors[0]
        assert behavior.user_id == "USER_001"
        assert behavior.id_tag == "TAG_001"
        assert behavior.charging_duration_minutes == 30
    
    def test_add_multiple_user_behaviors(self, simulator):
        """测试添加多个用户行为"""
        simulator.add_user_behavior("USER_001", "TAG_001", 30)
        simulator.add_user_behavior("USER_002", "TAG_002", 45)
        simulator.add_user_behavior("USER_003", "TAG_003", 60)
        
        assert len(simulator.user_behaviors) == 3
        assert simulator.user_behaviors[0].user_id == "USER_001"
        assert simulator.user_behaviors[1].user_id == "USER_002"
        assert simulator.user_behaviors[2].user_id == "USER_003"
    
    @pytest.mark.asyncio
    async def test_simulate_user_charging_flow(self, simulator):
        """测试模拟用户充电流程"""
        behavior = UserBehavior("USER_001", "TAG_001", 1)  # 1分钟测试
        
        # Mock MQTT客户端
        simulator.client = Mock()
        simulator.client.publish = Mock(return_value=Mock(rc=0))
        
        # 运行充电流程（使用较短的1分钟）
        await simulator.simulate_user_charging_flow(behavior)
        
        # 验证状态变化
        assert simulator.status == ChargerStatus.AVAILABLE
        assert behavior.start_time is not None
        assert behavior.end_time is not None
        assert simulator.transaction_id is None  # 充电完成后应该清空
    
    def test_meter_value_calculation(self, simulator):
        """测试计量值计算"""
        # 模拟充电10秒
        simulator.charging_power_kw = 7.0
        simulator.meter_report_interval = 10
        
        # 计算10秒应该产生的电量（Wh）
        # 7kW * (10秒 / 3600秒) * 1000 = 19.44 Wh
        expected_energy_wh = 7.0 * (10 / 3600.0) * 1000
        
        # 模拟一次计量值更新
        initial_meter = simulator.meter_value
        energy_increment_wh = simulator.charging_power_kw * (simulator.meter_report_interval / 3600.0) * 1000
        simulator.meter_value += int(energy_increment_wh)
        
        assert simulator.meter_value > initial_meter
        assert abs(simulator.meter_value - initial_meter - expected_energy_wh) < 1  # 允许1Wh误差
    
    @pytest.mark.asyncio
    async def test_status_transitions(self, simulator):
        """测试状态转换"""
        # 初始状态
        assert simulator.status == ChargerStatus.UNAVAILABLE
        
        # 变为Available
        simulator.status = ChargerStatus.AVAILABLE
        assert simulator.status == ChargerStatus.AVAILABLE
        
        # 变为Preparing
        simulator.status = ChargerStatus.PREPARING
        assert simulator.status == ChargerStatus.PREPARING
        
        # 变为Charging
        simulator.status = ChargerStatus.CHARGING
        assert simulator.status == ChargerStatus.CHARGING
        
        # 变为Finishing
        simulator.status = ChargerStatus.FINISHING
        assert simulator.status == ChargerStatus.FINISHING
        
        # 恢复为Available
        simulator.status = ChargerStatus.AVAILABLE
        assert simulator.status == ChargerStatus.AVAILABLE
    
    @pytest.mark.asyncio
    async def test_handle_remote_start_transaction(self, simulator):
        """测试处理远程启动交易请求"""
        simulator.client = Mock()
        simulator.client.publish = Mock(return_value=Mock(rc=0))
        simulator.loop = asyncio.get_event_loop()
        
        payload = {
            "idTag": "TAG_001",
            "connectorId": 1
        }
        
        await simulator._handle_request("RemoteStartTransaction", payload)
        
        # 验证状态变化
        assert simulator.status == ChargerStatus.CHARGING
        assert simulator.transaction_id is not None
        assert simulator.current_id_tag == "TAG_001"
        assert simulator.meter_value == 0  # 初始计量值为0
    
    @pytest.mark.asyncio
    async def test_handle_remote_stop_transaction(self, simulator):
        """测试处理远程停止交易请求"""
        simulator.client = Mock()
        simulator.client.publish = Mock(return_value=Mock(rc=0))
        simulator.loop = asyncio.get_event_loop()
        
        # 先设置充电状态
        simulator.status = ChargerStatus.CHARGING
        simulator.transaction_id = 12345
        simulator.meter_value = 1000  # 模拟已充电1kWh
        
        payload = {
            "transactionId": 12345
        }
        
        await simulator._handle_request("RemoteStopTransaction", payload)
        
        # 验证状态变化
        assert simulator.status == ChargerStatus.AVAILABLE
        assert simulator.transaction_id is None
        assert simulator.current_id_tag is None
    
    @pytest.mark.asyncio
    async def test_meter_values_loop(self, simulator):
        """测试计量值循环"""
        simulator.client = Mock()
        simulator.client.publish = Mock(return_value=Mock(rc=0))
        simulator.status = ChargerStatus.CHARGING
        simulator.transaction_id = 12345
        simulator.meter_value = 0
        simulator.meter_report_interval = 1  # 1秒间隔用于测试
        
        # 启动计量值循环
        task = asyncio.create_task(simulator._meter_values_loop())
        
        # 等待3秒（应该发送3次计量值）
        await asyncio.sleep(3.5)
        
        # 停止循环
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # 验证计量值已增加
        assert simulator.meter_value > 0
        
        # 验证发送了多次消息
        assert simulator.client.publish.call_count >= 3
    
    def test_qr_code_generation(self, simulator):
        """测试二维码生成"""
        # 这个方法应该不抛出异常
        try:
            simulator.print_qr_code()
            assert True
        except Exception as e:
            pytest.fail(f"二维码生成失败: {e}")


class TestChargingFlowIntegration:
    """充电流程集成测试"""
    
    @pytest.mark.asyncio
    async def test_complete_charging_flow(self):
        """测试完整的充电流程"""
        with patch('paho.mqtt.client.Client'):
            simulator = UserBehaviorSimulator(
                charger_id="CP-INTEGRATION-001",
                broker_host="localhost",
                broker_port=1883
            )
            
            simulator.client = Mock()
            simulator.client.publish = Mock(return_value=Mock(rc=0))
            simulator.loop = asyncio.get_event_loop()
            
            # 创建用户行为（1分钟测试）
            behavior = UserBehavior("USER_INTEGRATION", "TAG_INTEGRATION", 1)
            
            # 运行完整流程
            await simulator.simulate_user_charging_flow(behavior)
            
            # 验证最终状态
            assert simulator.status == ChargerStatus.AVAILABLE
            assert behavior.start_time is not None
            assert behavior.end_time is not None
            assert simulator.meter_value >= 0  # 应该有计量值记录
            
            # 验证时间记录
            duration = (behavior.end_time - behavior.start_time).total_seconds() / 60
            assert duration >= 1.0  # 至少1分钟
    
    @pytest.mark.asyncio
    async def test_multiple_users_sequential(self):
        """测试多个用户顺序充电"""
        with patch('paho.mqtt.client.Client'):
            simulator = UserBehaviorSimulator(
                charger_id="CP-MULTI-001",
                broker_host="localhost",
                broker_port=1883
            )
            
            simulator.client = Mock()
            simulator.client.publish = Mock(return_value=Mock(rc=0))
            simulator.loop = asyncio.get_event_loop()
            
            # 添加多个用户
            behaviors = [
                UserBehavior("USER_001", "TAG_001", 1),
                UserBehavior("USER_002", "TAG_002", 1),
                UserBehavior("USER_003", "TAG_003", 1),
            ]
            
            # 顺序执行
            for behavior in behaviors:
                await simulator.simulate_user_charging_flow(behavior)
                # 验证每次充电后状态都恢复为Available
                assert simulator.status == ChargerStatus.AVAILABLE
                assert simulator.transaction_id is None

