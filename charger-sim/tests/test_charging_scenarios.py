#!/usr/bin/env python3
#
# 充电场景测试
# 测试各种用户充电场景
#

import pytest
import asyncio
from unittest.mock import Mock, patch
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from user_behavior_simulator import (
    UserBehaviorSimulator, UserBehavior, ChargerStatus
)


class TestChargingScenarios:
    """充电场景测试类"""
    
    @pytest.fixture
    def simulator(self):
        """创建模拟器实例"""
        with patch('paho.mqtt.client.Client'):
            sim = UserBehaviorSimulator(
                charger_id="CP-SCENARIO-001",
                broker_host="localhost",
                broker_port=1883
            )
            sim.client = Mock()
            sim.client.publish = Mock(return_value=Mock(rc=0))
            sim.loop = asyncio.get_event_loop()
            return sim
    
    @pytest.mark.asyncio
    async def test_quick_charge_scenario(self, simulator):
        """测试快速充电场景（15分钟）"""
        behavior = UserBehavior("USER_QUICK", "TAG_QUICK", 15)
        
        await simulator.simulate_user_charging_flow(behavior)
        
        # 验证快速充电完成
        assert simulator.status == ChargerStatus.AVAILABLE
        duration = (behavior.end_time - behavior.start_time).total_seconds() / 60
        assert 14 <= duration <= 16  # 允许1分钟误差
    
    @pytest.mark.asyncio
    async def test_normal_charge_scenario(self, simulator):
        """测试正常充电场景（30分钟）"""
        behavior = UserBehavior("USER_NORMAL", "TAG_NORMAL", 30)
        
        await simulator.simulate_user_charging_flow(behavior)
        
        # 验证正常充电完成
        assert simulator.status == ChargerStatus.AVAILABLE
        duration = (behavior.end_time - behavior.start_time).total_seconds() / 60
        assert 29 <= duration <= 31  # 允许1分钟误差
    
    @pytest.mark.asyncio
    async def test_long_charge_scenario(self, simulator):
        """测试长时间充电场景（60分钟）"""
        behavior = UserBehavior("USER_LONG", "TAG_LONG", 60)
        
        await simulator.simulate_user_charging_flow(behavior)
        
        # 验证长时间充电完成
        assert simulator.status == ChargerStatus.AVAILABLE
        duration = (behavior.end_time - behavior.start_time).total_seconds() / 60
        assert 59 <= duration <= 61  # 允许1分钟误差
    
    @pytest.mark.asyncio
    async def test_high_power_charging(self, simulator):
        """测试高功率充电（11kW）"""
        simulator.charging_power_kw = 11.0
        
        behavior = UserBehavior("USER_HIGH_POWER", "TAG_HIGH_POWER", 30)
        
        await simulator.simulate_user_charging_flow(behavior)
        
        # 验证高功率充电
        assert simulator.meter_value > 0
        # 11kW * 0.5小时 = 5.5kWh = 5500Wh
        # 允许10%误差
        expected_min = 5500 * 0.9
        expected_max = 5500 * 1.1
        assert expected_min <= simulator.meter_value <= expected_max
    
    @pytest.mark.asyncio
    async def test_low_power_charging(self, simulator):
        """测试低功率充电（3.7kW）"""
        simulator.charging_power_kw = 3.7
        
        behavior = UserBehavior("USER_LOW_POWER", "TAG_LOW_POWER", 30)
        
        await simulator.simulate_user_charging_flow(behavior)
        
        # 验证低功率充电
        assert simulator.meter_value > 0
        # 3.7kW * 0.5小时 = 1.85kWh = 1850Wh
        # 允许10%误差
        expected_min = 1850 * 0.9
        expected_max = 1850 * 1.1
        assert expected_min <= simulator.meter_value <= expected_max
    
    @pytest.mark.asyncio
    async def test_concurrent_users_queue(self, simulator):
        """测试多个用户排队充电"""
        # 添加多个用户到队列
        simulator.add_user_behavior("USER_1", "TAG_1", 1)
        simulator.add_user_behavior("USER_2", "TAG_2", 1)
        simulator.add_user_behavior("USER_3", "TAG_3", 1)
        
        assert len(simulator.user_behaviors) == 3
        
        # 处理第一个用户
        behavior1 = simulator.user_behaviors.pop(0)
        await simulator.simulate_user_charging_flow(behavior1)
        assert simulator.status == ChargerStatus.AVAILABLE
        
        # 处理第二个用户
        behavior2 = simulator.user_behaviors.pop(0)
        await simulator.simulate_user_charging_flow(behavior2)
        assert simulator.status == ChargerStatus.AVAILABLE
        
        # 处理第三个用户
        behavior3 = simulator.user_behaviors.pop(0)
        await simulator.simulate_user_charging_flow(behavior3)
        assert simulator.status == ChargerStatus.AVAILABLE
    
    @pytest.mark.asyncio
    async def test_remote_stop_during_charging(self, simulator):
        """测试充电过程中远程停止"""
        # 先启动充电
        behavior = UserBehavior("USER_REMOTE_STOP", "TAG_REMOTE_STOP", 30)
        simulator.status = ChargerStatus.CHARGING
        simulator.transaction_id = 12345
        simulator.current_id_tag = behavior.id_tag
        simulator.meter_value = 5000  # 已充电5kWh
        
        # 模拟远程停止
        payload = {"transactionId": 12345}
        await simulator._handle_request("RemoteStopTransaction", payload)
        
        # 验证已停止
        assert simulator.status == ChargerStatus.AVAILABLE
        assert simulator.transaction_id is None
        assert simulator.current_id_tag is None
    
    @pytest.mark.asyncio
    async def test_charging_statistics(self, simulator):
        """测试充电统计信息"""
        behavior = UserBehavior("USER_STATS", "TAG_STATS", 30)
        simulator.charging_power_kw = 7.0
        
        await simulator.simulate_user_charging_flow(behavior)
        
        # 验证统计信息
        assert behavior.start_time is not None
        assert behavior.end_time is not None
        
        duration_seconds = (behavior.end_time - behavior.start_time).total_seconds()
        duration_minutes = duration_seconds / 60
        
        # 验证时长
        assert 29 <= duration_minutes <= 31
        
        # 验证电量
        energy_kwh = simulator.meter_value / 1000.0
        expected_energy = 7.0 * (duration_minutes / 60.0)
        assert abs(energy_kwh - expected_energy) < 0.5  # 允许0.5kWh误差

