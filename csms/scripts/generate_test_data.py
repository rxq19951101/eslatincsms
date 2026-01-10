#!/usr/bin/env python3
"""
测试数据生成脚本
生成完整的测试数据，用于前端页面展示和统计
"""

import sys
import os
import random
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database.models import (
    Tenant, Site, ChargePoint, EVSE, EVSEStatus, Device,
    ChargingSession, MeterValue, Order, Invoice, Tariff,
    EndUser, Alert
)
from app.core.auth import get_password_hash


class TestDataGenerator:
    """测试数据生成器"""
    
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        SessionLocal = sessionmaker(bind=self.engine)
        self.db = SessionLocal()
        self.tenant_id = None
        
        # 配置：生成数据的数量
        self.config = {
            'sites': 5,  # 5个站点
            'charge_points_per_site': 4,  # 每个站点4个充电桩
            'evses_per_charge_point': 2,  # 每个充电桩2个枪
            'users': 50,  # 50个用户
            'days_of_history': 30,  # 30天的历史数据
            'sessions_per_day': 20,  # 每天20个充电会话
            'alerts_count': 30,  # 30条告警
        }
        
        # 城市和地址数据
        self.cities = [
            {'name': '深圳市南山区', 'lat': 22.5364, 'lng': 113.9454},
            {'name': '深圳市福田区', 'lat': 22.5213, 'lng': 114.0541},
            {'name': '深圳市罗湖区', 'lat': 22.5485, 'lng': 114.1315},
            {'name': '深圳市龙岗区', 'lat': 22.7211, 'lng': 114.2478},
            {'name': '深圳市宝安区', 'lat': 22.5549, 'lng': 113.8838},
        ]
        
        self.site_names = [
            '科技园充电站', '市民中心充电站', '火车站充电站',
            '机场充电站', '商业中心充电站', '住宅小区充电站',
            '工业园充电站', '大学城充电站'
        ]
        
        self.user_names = [
            '张三', '李四', '王五', '赵六', '钱七', '孙八', '周九', '吴十',
            '郑一', '陈二', '褚三', '卫四', '蒋五', '沈六', '韩七', '杨八'
        ]
    
    def get_tenant_id(self):
        """获取默认租户ID"""
        if self.tenant_id:
            return self.tenant_id
        
        tenant = self.db.query(Tenant).filter(Tenant.name == "默认租户").first()
        if not tenant:
            print("❌ 未找到默认租户，请先运行 create_initial_data.py")
            sys.exit(1)
        
        self.tenant_id = tenant.id
        print(f"✓ 找到租户: {tenant.name} (ID: {self.tenant_id})")
        return self.tenant_id
    
    def generate_sites(self):
        """生成站点数据"""
        print(f"\n1. 生成 {self.config['sites']} 个站点...")
        tenant_id = self.get_tenant_id()
        sites = []
        
        for i in range(self.config['sites']):
            city = self.cities[i % len(self.cities)]
            site_name = f"{city['name']}{self.site_names[i % len(self.site_names)]}"
            
            # 添加一些随机偏移
            lat_offset = random.uniform(-0.05, 0.05)
            lng_offset = random.uniform(-0.05, 0.05)
            
            site = Site(
                id=f"SITE_{i+1:03d}",
                tenant_id=tenant_id,
                name=site_name,
                address=f"{city['name']}某某路{random.randint(1, 999)}号",
                latitude=city['lat'] + lat_offset,
                longitude=city['lng'] + lng_offset,
                is_active=True,
                operating_hours="00:00-24:00"
            )
            self.db.add(site)
            sites.append(site)
        
        self.db.commit()
        print(f"✓ 成功生成 {len(sites)} 个站点")
        return sites
    
    def generate_devices(self, count):
        """生成MQTT设备"""
        print(f"\n2. 生成 {count} 个MQTT设备...")
        tenant_id = self.get_tenant_id()
        devices = []
        
        for i in range(count):
            serial_number = f"DEV{i+1:06d}"
            device = Device(
                serial_number=serial_number,
                tenant_id=tenant_id,
                type_code="default",
                mqtt_client_id=f"default&{serial_number}",
                mqtt_username=serial_number,
                master_secret_encrypted="encrypted_secret_placeholder",  # 实际应用中需要加密
                is_active=True,
                last_connected=datetime.now(timezone.utc) - timedelta(hours=random.randint(0, 24))
            )
            self.db.add(device)
            devices.append(device)
        
        self.db.commit()
        print(f"✓ 成功生成 {len(devices)} 个设备")
        return devices
    
    def generate_charge_points(self, sites, devices):
        """生成充电桩"""
        print(f"\n3. 生成充电桩...")
        tenant_id = self.get_tenant_id()
        charge_points = []
        device_index = 0
        
        vendors = ['特来电', 'ABB', '星星充电', '小鹏汽车', '蔚来']
        models = ['60kW直流快充', '120kW超级快充', '7kW交流慢充', '180kW超快充']
        
        for site in sites:
            for i in range(self.config['charge_points_per_site']):
                cp_id = f"CP_{site.id}_{i+1:02d}"
                vendor = random.choice(vendors)
                model = random.choice(models)
                max_power = float(model.split('kW')[0])
                
                charge_point = ChargePoint(
                    id=cp_id,
                    tenant_id=tenant_id,
                    site_id=site.id,
                    vendor=vendor,
                    model=model,
                    serial_number=f"SN{len(charge_points)+1:08d}",
                    firmware_version=f"v{random.randint(1,3)}.{random.randint(0,9)}.{random.randint(0,9)}",
                    max_power_kw=max_power,
                    device_serial_number=devices[device_index].serial_number if device_index < len(devices) else None,
                    is_active=True
                )
                self.db.add(charge_point)
                charge_points.append(charge_point)
                device_index += 1
        
        self.db.commit()
        print(f"✓ 成功生成 {len(charge_points)} 个充电桩")
        return charge_points
    
    def generate_evses_and_status(self, charge_points):
        """生成EVSE和状态"""
        print(f"\n4. 生成EVSE和状态...")
        tenant_id = self.get_tenant_id()
        evses = []
        
        connector_types = ['Type2', 'CCS', 'CHAdeMO', 'GB/T']
        statuses = ['Available', 'Charging', 'Offline', 'Faulted']
        # 权重：大部分可用，少数充电中，少数离线/故障
        status_weights = [0.6, 0.25, 0.1, 0.05]
        
        for cp in charge_points:
            for evse_num in range(1, self.config['evses_per_charge_point'] + 1):
                evse = EVSE(
                    tenant_id=tenant_id,
                    charge_point_id=cp.id,
                    evse_id=evse_num,
                    connector_type=random.choice(connector_types),
                    max_power_kw=cp.max_power_kw / self.config['evses_per_charge_point']
                )
                self.db.add(evse)
                self.db.flush()  # 获取evse.id
                
                # 创建状态
                status = random.choices(statuses, weights=status_weights)[0]
                evse_status = EVSEStatus(
                    tenant_id=tenant_id,
                    evse_id=evse.id,
                    charge_point_id=cp.id,
                    status=status,
                    last_seen=datetime.now(timezone.utc) - timedelta(minutes=random.randint(0, 30))
                )
                self.db.add(evse_status)
                evses.append(evse)
        
        self.db.commit()
        print(f"✓ 成功生成 {len(evses)} 个EVSE及其状态")
        return evses
    
    def generate_users(self):
        """生成终端用户"""
        print(f"\n5. 生成 {self.config['users']} 个用户...")
        tenant_id = self.get_tenant_id()
        users = []
        
        for i in range(self.config['users']):
            phone = f"138{random.randint(10000000, 99999999)}"
            name = random.choice(self.user_names) + str(i+1)
            
            user = EndUser(
                # id字段是UUID，使用默认值自动生成
                tenant_id=tenant_id,
                phone=phone,
                id_tag=f"RFID_{i+1:08d}",
                full_name=name,  # 使用full_name而不是nickname
                balance=Decimal(str(random.uniform(0, 500))),  # Decimal需要字符串
                status='active',
                last_login_at=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 7))
            )
            self.db.add(user)
            users.append(user)
        
        self.db.commit()
        print(f"✓ 成功生成 {len(users)} 个用户")
        return users
    
    def generate_tariff(self, sites):
        """生成定价规则"""
        print(f"\n6. 生成定价规则...")
        tenant_id = self.get_tenant_id()
        tariffs = []
        
        for site in sites:
            tariff = Tariff(
                tenant_id=tenant_id,
                site_id=site.id,
                name=f"{site.name}基础定价",
                base_price_per_kwh=Decimal('1.50'),
                service_fee=Decimal('0.80'),
                valid_from=datetime.now(timezone.utc) - timedelta(days=365),  # 一年前生效
                valid_until=None,  # 永久有效
                is_active=True
            )
            self.db.add(tariff)
            tariffs.append(tariff)
        
        self.db.commit()
        print(f"✓ 成功生成 {len(tariffs)} 个定价规则")
        return tariffs
    
    def generate_charging_sessions_and_orders(self, evses, users, tariffs):
        """生成充电会话、订单和发票"""
        print(f"\n7. 生成历史充电数据...")
        tenant_id = self.get_tenant_id()
        
        sessions_count = self.config['days_of_history'] * self.config['sessions_per_day']
        print(f"   将生成约 {sessions_count} 个充电会话...")
        
        sessions = []
        orders = []
        invoices = []
        
        # 使用第一个tariff（如果有）
        default_tariff = tariffs[0] if tariffs else None
        if not default_tariff:
            print("⚠️  没有找到定价规则，跳过发票生成")
            return sessions, orders, invoices
        
        # 生成过去N天的数据
        for day in range(self.config['days_of_history']):
            date = datetime.now(timezone.utc) - timedelta(days=day)
            
            for _ in range(self.config['sessions_per_day']):
                evse = random.choice(evses)
                user = random.choice(users)
                
                # 充电时长：10分钟到4小时
                duration_minutes = random.randint(10, 240)
                start_time = date.replace(
                    hour=random.randint(0, 23),
                    minute=random.randint(0, 59)
                )
                end_time = start_time + timedelta(minutes=duration_minutes)
                
                # 充电量：根据功率和时长计算
                power_kw = evse.max_power_kw or 60
                energy_kwh = power_kw * (duration_minutes / 60) * random.uniform(0.7, 0.95)  # 效率因子
                meter_start = random.randint(0, 1000000)
                meter_stop = meter_start + int(energy_kwh * 1000)  # Wh
                
                # 充电会话
                transaction_id = len(sessions) + 1
                session = ChargingSession(
                    tenant_id=tenant_id,
                    evse_id=evse.id,
                    charge_point_id=evse.charge_point_id,
                    transaction_id=transaction_id,
                    id_tag=user.id_tag,
                    user_id=str(user.id),  # 转换UUID为字符串
                    start_time=start_time,
                    end_time=end_time,
                    meter_start=meter_start,
                    meter_stop=meter_stop,
                    status='completed'
                )
                self.db.add(session)
                self.db.flush()
                sessions.append(session)
                
                # 订单
                order = Order(
                    id=f"ORD_{transaction_id:010d}",
                    tenant_id=tenant_id,
                    session_id=session.id,
                    charge_point_id=evse.charge_point_id,
                    user_id=str(user.id),  # 转换UUID为字符串
                    id_tag=user.id_tag,
                    created_at=start_time - timedelta(minutes=5),
                    start_time=start_time,
                    end_time=end_time,
                    status='completed'
                )
                self.db.add(order)
                self.db.flush()
                orders.append(order)
                
                # 先创建pricing_snapshot
                from app.database.models import PricingSnapshot
                pricing_snapshot = PricingSnapshot(
                    tenant_id=tenant_id,
                    tariff_id=default_tariff.id,  # 使用实际的tariff ID
                    session_id=session.id,
                    order_id=order.id,
                    price_per_kwh=default_tariff.base_price_per_kwh,
                    service_fee=default_tariff.service_fee,
                    snapshot_data={
                        'base_price': float(default_tariff.base_price_per_kwh),
                        'service_fee': float(default_tariff.service_fee)
                    }
                )
                self.db.add(pricing_snapshot)
                self.db.flush()
                
                # 发票
                energy_cost = Decimal(str(energy_kwh)) * Decimal('1.50')
                service_fee_amount = Decimal('0.80')
                total_amount = energy_cost + service_fee_amount
                
                invoice = Invoice(
                    id=f"INV_{transaction_id:010d}",
                    tenant_id=tenant_id,
                    order_id=order.id,
                    session_id=session.id,
                    pricing_snapshot_id=pricing_snapshot.id,
                    energy_kwh=Decimal(str(energy_kwh)),
                    duration_minutes=Decimal(str(duration_minutes)),
                    charging_rate_kw=Decimal(str(power_kw)),
                    energy_cost=energy_cost,
                    service_fee=service_fee_amount,
                    total_amount=total_amount,
                    issued_at=end_time,
                    paid_at=end_time + timedelta(minutes=5),
                    status='paid'
                )
                self.db.add(invoice)
                invoices.append(invoice)
                
                # 生成一些表计数据（每10分钟一个）
                for minute_offset in range(0, duration_minutes, 10):
                    meter_time = start_time + timedelta(minutes=minute_offset)
                    progress = minute_offset / duration_minutes
                    meter_value = meter_start + int((meter_stop - meter_start) * progress)
                    
                    meter = MeterValue(
                        tenant_id=tenant_id,
                        session_id=session.id,
                        connector_id=evse.evse_id,
                        timestamp=meter_time,
                        value=meter_value,
                        sampled_value={
                            'value': str(meter_value),
                            'unit': 'Wh',
                            'measurand': 'Energy.Active.Import.Register'
                        }
                    )
                    self.db.add(meter)
        
        self.db.commit()
        print(f"✓ 成功生成:")
        print(f"  - {len(sessions)} 个充电会话")
        print(f"  - {len(orders)} 个订单")
        print(f"  - {len(invoices)} 个发票")
        print(f"  - 约 {len(sessions) * (240 // 10)} 条表计数据")
        
        return sessions, orders, invoices
    
    def generate_alerts(self, charge_points):
        """生成告警数据"""
        print(f"\n8. 生成 {self.config['alerts_count']} 条告警...")
        tenant_id = self.get_tenant_id()
        alerts = []
        
        alert_types = {
            'offline': {'severity': 'critical', 'title': '设备离线', 'description': '充电桩失去连接'},
            'faulted': {'severity': 'critical', 'title': '设备故障', 'description': '充电桩报告故障状态'},
            'temperature': {'severity': 'warning', 'title': '温度告警', 'description': '设备温度过高'},
            'overcurrent': {'severity': 'warning', 'title': '过流告警', 'description': '检测到过流情况'},
            'payment_failed': {'severity': 'info', 'title': '支付失败', 'description': '用户支付失败'},
            'connection_lost': {'severity': 'info', 'title': '连接中断', 'description': '网络连接临时中断'},
        }
        
        statuses = ['pending', 'acknowledged', 'resolved']
        status_weights = [0.3, 0.3, 0.4]  # 30%新告警，30%已确认，40%已解决
        
        for i in range(self.config['alerts_count']):
            cp = random.choice(charge_points)
            alert_type = random.choice(list(alert_types.keys()))
            alert_info = alert_types[alert_type]
            
            created_at = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 7))
            status = random.choices(statuses, weights=status_weights)[0]
            
            alert = Alert(
                tenant_id=tenant_id,
                charge_point_id=cp.id,
                evse_id=None,  # 可选：可以关联到specific EVSE
                alert_type=alert_type,
                severity=alert_info['severity'],
                title=alert_info['title'],
                description=f"{cp.id} - {alert_info['description']}",
                alert_metadata={'charge_point_id': cp.id, 'site_id': cp.site_id},
                status=status,
                created_at=created_at,
                acknowledged_at=created_at + timedelta(hours=1) if status in ['acknowledged', 'resolved'] else None,
                resolved_at=created_at + timedelta(hours=random.randint(2, 24)) if status == 'resolved' else None
            )
            self.db.add(alert)
            alerts.append(alert)
        
        self.db.commit()
        print(f"✓ 成功生成 {len(alerts)} 条告警")
        return alerts
    
    def clear_existing_data(self):
        """清空现有测试数据"""
        print("\n0. 清空现有数据...")
        try:
            # 按照依赖关系的逆序删除
            from app.database.models import (
                PricingSnapshot, Payment, Invoice, MeterValue,
                ChargingSession, Order, EVSEStatus, EVSE,
                ChargePoint, Site, Device, Tariff, EndUser, Alert
            )
            
            tables = [
                ('payments', Payment),           # 1. 最外层
                ('invoices', Invoice),           # 2. 引用pricing_snapshots和session
                ('pricing_snapshots', PricingSnapshot),  # 3. 引用tariff和session
                ('meter_values', MeterValue),    # 4. 引用session
                ('orders', Order),               # 5. 引用session（必须在session之前删除）
                ('charging_sessions', ChargingSession),  # 6. 被多表引用
                ('evse_status', EVSEStatus),     # 7. 引用evse
                ('evses', EVSE),                 # 8. 引用charge_point
                ('charge_points', ChargePoint),  # 9. 引用site和device
                ('tariffs', Tariff),             # 10. 引用site
                ('sites', Site),                 # 11. 被charge_points和tariffs引用
                ('devices', Device),             # 12. 被charge_points引用
                ('end_users', EndUser),          # 13. 独立
                ('alerts', Alert),               # 14. 引用charge_point
            ]
            
            for table_name, model in tables:
                count = self.db.query(model).delete()
                if count > 0:
                    print(f"  - 删除 {table_name}: {count} 条")
            
            self.db.commit()
            print("✓ 现有数据已清空")
        except Exception as e:
            print(f"⚠️  清空数据时出错（可能无数据）: {e}")
            self.db.rollback()
    
    def generate_all(self):
        """生成所有测试数据"""
        print("="*60)
        print("开始生成测试数据...")
        print("="*60)
        
        try:
            # 0. 清空现有数据
            self.clear_existing_data()
            
            # 1. 生成站点
            sites = self.generate_sites()
            
            # 2. 生成设备
            total_charge_points = self.config['sites'] * self.config['charge_points_per_site']
            devices = self.generate_devices(total_charge_points)
            
            # 3. 生成充电桩
            charge_points = self.generate_charge_points(sites, devices)
            
            # 4. 生成EVSE
            evses = self.generate_evses_and_status(charge_points)
            
            # 5. 生成用户
            users = self.generate_users()
            
            # 6. 生成定价
            tariffs = self.generate_tariff(sites)
            
            # 7. 生成充电历史
            sessions, orders, invoices = self.generate_charging_sessions_and_orders(evses, users, tariffs)
            
            # 8. 生成告警
            alerts = self.generate_alerts(charge_points)
            
            print("\n" + "="*60)
            print("✅ 测试数据生成完成！")
            print("="*60)
            print("\n📊 数据统计:")
            print(f"  - 站点: {len(sites)}")
            print(f"  - 充电桩: {len(charge_points)}")
            print(f"  - EVSE: {len(evses)}")
            print(f"  - 用户: {len(users)}")
            print(f"  - 充电会话: {len(sessions)}")
            print(f"  - 订单: {len(orders)}")
            print(f"  - 发票: {len(invoices)}")
            print(f"  - 告警: {len(alerts)}")
            print(f"  - 总收入: ¥{sum(inv.total_amount for inv in invoices):.2f}")
            print(f"  - 总充电量: {sum(inv.energy_kwh for inv in invoices):.2f} kWh")
            
        except Exception as e:
            print(f"\n❌ 生成测试数据失败: {e}")
            import traceback
            traceback.print_exc()
            self.db.rollback()
            sys.exit(1)
        finally:
            self.db.close()


def main():
    """主函数"""
    # 数据库URL
    database_url = os.getenv(
        'DATABASE_URL',
        'postgresql://ocpp_user:ocpp_password@localhost:5432/ocpp'
    )
    
    print(f"连接数据库: {database_url.split('@')[1] if '@' in database_url else database_url}")
    
    generator = TestDataGenerator(database_url)
    generator.generate_all()


if __name__ == '__main__':
    main()
