#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# 查询指定 transaction_id 的所有相关数据
# 包括：充电会话、订单、发票、计量值、充电桩信息等
#

import argparse
import requests
import json
from datetime import datetime
from typing import Dict, Any, Optional, List


class TransactionDataQuery:
    """交易数据查询器"""
    
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip('/')
        self.base_url = f"{self.server_url}/api/v1"
        
    def print_header(self, title: str):
        """打印标题"""
        print("\n" + "=" * 80)
        print(f"{title}")
        print("=" * 80)
    
    def print_section(self, title: str):
        """打印小节标题"""
        print(f"\n{'─' * 80}")
        print(f"  {title}")
        print(f"{'─' * 80}")
    
    def query_charging_session(self, transaction_id: int, charge_point_id: Optional[str] = None) -> Optional[Dict]:
        """查询充电会话数据"""
        self.print_section("1. 充电会话数据 (ChargingSession)")
        
        try:
            params = {"limit": 1000}  # 增加限制以获取更多记录
            if charge_point_id:
                params["charge_point_id"] = charge_point_id
            
            print(f"正在查询交易数据 (transaction_id={transaction_id})...")
            if charge_point_id:
                print(f"  限定充电桩: {charge_point_id}")
            
            response = requests.get(
                f"{self.base_url}/transactions",
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                sessions = response.json()
                print(f"  查询到 {len(sessions)} 条会话记录，正在匹配...")
                
                # 查找匹配的 transaction_id
                session = None
                for s in sessions:
                    if s.get("transaction_id") == transaction_id:
                        session = s
                        break
                
                if session:
                    print("✓ 找到充电会话:")
                    print(f"  会话ID (session_id): {session.get('id')}")
                    print(f"  交易ID (transaction_id): {session.get('transaction_id')}")
                    print(f"  充电桩ID: {session.get('charge_point_id')}")
                    print(f"  用户标签 (id_tag): {session.get('id_tag')}")
                    print(f"  用户ID: {session.get('user_id')}")
                    print(f"  状态: {session.get('status')}")
                    print(f"  开始时间: {session.get('start_time')}")
                    print(f"  结束时间: {session.get('end_time')}")
                    print(f"  电量 (kWh): {session.get('energy_kwh'):.2f}" if session.get('energy_kwh') is not None else "  电量 (kWh): N/A")
                    print(f"  时长 (分钟): {session.get('duration_minutes'):.2f}" if session.get('duration_minutes') is not None else "  时长 (分钟): N/A")
                    return session
                else:
                    print(f"✗ 未找到 transaction_id={transaction_id} 的充电会话")
                    if charge_point_id:
                        print(f"  提示: 已查询充电桩 {charge_point_id} 的 {len(sessions)} 条记录，但未找到匹配的交易")
                    else:
                        print(f"  提示: 已查询 {len(sessions)} 条记录，但未找到匹配的交易")
                        print(f"  建议: 使用 --charge-point-id 参数指定充电桩ID以缩小查询范围")
                    return None
            else:
                print(f"✗ 查询失败: HTTP {response.status_code}, {response.text}")
                return None
        except Exception as e:
            print(f"✗ 查询异常: {e}")
            return None
    
    def query_meter_values(self, session_id: int) -> List[Dict]:
        """查询计量值数据"""
        self.print_section("2. 计量值数据 (MeterValue)")
        
        try:
            # 注意：这里需要直接查询数据库或使用内部API
            # 如果API不支持，我们可以尝试通过其他方式获取
            # 先尝试是否有专门的 meter_values 端点
            response = requests.get(
                f"{self.base_url}/meter-values",
                params={"session_id": session_id},
                timeout=10
            )
            
            if response.status_code == 200:
                meter_values = response.json()
                if meter_values:
                    print(f"✓ 找到 {len(meter_values)} 条计量值记录")
                    for i, mv in enumerate(meter_values[:10], 1):  # 只显示前10条
                        print(f"\n  记录 {i}:")
                        print(f"    ID: {mv.get('id')}")
                        print(f"    时间戳: {mv.get('timestamp')}")
                        print(f"    连接器ID: {mv.get('connector_id')}")
                        print(f"    值 (Wh): {mv.get('value')}")
                        if mv.get('sampled_value'):
                            print(f"    采样值: {json.dumps(mv.get('sampled_value'), ensure_ascii=False, indent=6)}")
                    if len(meter_values) > 10:
                        print(f"\n  ... 还有 {len(meter_values) - 10} 条记录未显示")
                    return meter_values
                else:
                    print("✗ 未找到计量值记录")
                    return []
            elif response.status_code == 404:
                print("⚠ API端点 /api/v1/meter-values 不存在，跳过计量值查询")
                print("  提示: 计量值数据可能需要直接查询数据库")
                return []
            else:
                print(f"✗ 查询失败: HTTP {response.status_code}, {response.text}")
                return []
        except Exception as e:
            print(f"✗ 查询异常: {e}")
            return []
    
    def query_order(self, session_id: int, charge_point_id: Optional[str] = None, session_start_time: Optional[str] = None) -> Optional[Dict]:
        """查询订单数据"""
        self.print_section("3. 订单数据 (Order)")
        
        try:
            # 优先通过 session_id 精确查询
            params = {"session_id": session_id, "limit": 1000}
            
            print(f"正在查询订单数据 (session_id={session_id})...")
            
            response = requests.get(
                f"{self.base_url}/orders",
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                orders = response.json()
                print(f"  查询到 {len(orders)} 条订单记录")
                
                if orders:
                    # 如果通过 session_id 找到了订单，直接使用第一个（应该只有一个）
                    order = orders[0]
                    print("✓ 找到订单:")
                    print(f"  订单ID: {order.get('id')}")
                    print(f"  会话ID: {order.get('session_id')}")
                    print(f"  充电桩ID: {order.get('charge_point_id')}")
                    print(f"  用户ID: {order.get('user_id')}")
                    print(f"  用户标签: {order.get('id_tag')}")
                    print(f"  状态: {order.get('status')}")
                    print(f"  开始时间: {order.get('start_time')}")
                    print(f"  结束时间: {order.get('end_time')}")
                    print(f"  电量 (kWh): {order.get('energy_kwh'):.2f}" if order.get('energy_kwh') is not None else "  电量 (kWh): N/A")
                    print(f"  时长 (分钟): {order.get('duration_minutes')}" if order.get('duration_minutes') is not None else "  时长 (分钟): N/A")
                    print(f"  总金额: {order.get('total_cost'):.2f} 元" if order.get('total_cost') is not None else "  总金额: N/A")
                    print(f"  创建时间: {order.get('created_at')}")
                    return order
                else:
                    # 如果通过 session_id 没找到，尝试通过 charge_point_id 查询（兼容旧逻辑）
                    print(f"  通过 session_id 未找到订单，尝试通过 charge_point_id 查询...")
                    if charge_point_id:
                        params = {"charge_point_id": charge_point_id, "limit": 1000}
                        response = requests.get(
                            f"{self.base_url}/orders",
                            params=params,
                            timeout=15
                        )
                        if response.status_code == 200:
                            orders = response.json()
                            print(f"  通过 charge_point_id 查询到 {len(orders)} 条订单记录")
                            
                            # 尝试通过时间匹配
                            order = None
                            if session_start_time:
                                for o in orders:
                                    order_start = o.get("start_time")
                                    if order_start and order_start[:16] == session_start_time[:16]:
                                        order = o
                                        break
                            
                            if order:
                                print("✓ 找到订单（通过时间和 charge_point_id 匹配）:")
                                print(f"  订单ID: {order.get('id')}")
                                print(f"  会话ID: {order.get('session_id', 'N/A')}")
                                print(f"  充电桩ID: {order.get('charge_point_id')}")
                                print(f"  状态: {order.get('status')}")
                                print(f"  总金额: {order.get('total_cost'):.2f} 元" if order.get('total_cost') is not None else "  总金额: N/A")
                                return order
                    
                    print("✗ 未找到关联的订单")
                    print(f"  可能原因:")
                    print(f"    1. 该交易可能没有创建订单（订单通常在特定业务条件下才创建）")
                    print(f"    2. 订单的 session_id 或 charge_point_id 不匹配")
                    print(f"    3. 订单可能已被删除或状态异常")
                    return None
            else:
                print(f"✗ 查询失败: HTTP {response.status_code}, {response.text}")
                return None
        except Exception as e:
            print(f"✗ 查询异常: {e}")
            return None
    
    def query_invoice(self, order_id: int) -> Optional[Dict]:
        """查询发票数据"""
        self.print_section("4. 发票数据 (Invoice)")
        
        try:
            # 尝试查询发票API（如果存在）
            response = requests.get(
                f"{self.base_url}/invoices",
                params={"order_id": order_id},
                timeout=10
            )
            
            if response.status_code == 200:
                invoices = response.json()
                if invoices:
                    invoice = invoices[0]
                    print("✓ 找到发票:")
                    print(f"  发票ID: {invoice.get('id')}")
                    print(f"  订单ID: {invoice.get('order_id')}")
                    print(f"  总金额: {invoice.get('total_amount'):.2f} 元" if invoice.get('total_amount') is not None else "  总金额: N/A")
                    print(f"  创建时间: {invoice.get('created_at')}")
                    return invoice
                else:
                    print("✗ 未找到发票")
                    return None
            elif response.status_code == 404:
                print("⚠ API端点 /api/v1/invoices 不存在，跳过发票查询")
                return None
            else:
                print(f"✗ 查询失败: HTTP {response.status_code}, {response.text}")
                return None
        except Exception as e:
            print(f"✗ 查询异常: {e}")
            return None
    
    def query_charge_point(self, charge_point_id: str) -> Optional[Dict]:
        """查询充电桩信息"""
        self.print_section("5. 充电桩信息 (ChargePoint)")
        
        try:
            response = requests.get(
                f"{self.base_url}/chargers/{charge_point_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                charger = response.json()
                print("✓ 找到充电桩:")
                print(f"  充电桩ID: {charger.get('id')}")
                print(f"  厂商: {charger.get('vendor', 'N/A')}")
                print(f"  型号: {charger.get('model', 'N/A')}")
                print(f"  序列号: {charger.get('serial_number', 'N/A')}")
                print(f"  固件版本: {charger.get('firmware_version', 'N/A')}")
                print(f"  状态: {charger.get('status', 'N/A')}")
                print(f"  最大功率: {charger.get('max_power_kw', 'N/A')} kW" if charger.get('max_power_kw') else "  最大功率: N/A")
                return charger
            else:
                print(f"✗ 查询失败: HTTP {response.status_code}, {response.text}")
                return None
        except Exception as e:
            print(f"✗ 查询异常: {e}")
            return None
    
    def query_all(self, transaction_id: int, charge_point_id: Optional[str] = None):
        """查询所有相关数据"""
        self.print_header(f"交易数据查询 - Transaction ID: {transaction_id}")
        print(f"查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"服务器: {self.server_url}")
        if charge_point_id:
            print(f"充电桩ID: {charge_point_id}")
        
        # 1. 查询充电会话
        session = self.query_charging_session(transaction_id, charge_point_id)
        
        if not session:
            print("\n✗ 未找到充电会话，无法继续查询其他数据")
            return
        
        session_id = session.get('id')
        charge_point_id = session.get('charge_point_id')
        
        # 2. 查询计量值
        meter_values = self.query_meter_values(session_id)
        
        # 3. 查询订单
        order = self.query_order(session_id, charge_point_id, session.get('start_time'))
        
        # 4. 查询发票（如果有订单）
        if order:
            order_id = order.get('id')
            invoice = self.query_invoice(order_id)
        
        # 5. 查询充电桩信息
        if charge_point_id:
            charger = self.query_charge_point(charge_point_id)
        
        # 汇总
        self.print_header("数据汇总")
        print(f"✓ 充电会话: {'已找到' if session else '未找到'}")
        print(f"✓ 计量值记录: {len(meter_values)} 条")
        print(f"✓ 订单: {'已找到' if order else '未找到'}")
        print(f"✓ 发票: {'已找到' if order and 'invoice' in locals() and invoice else '未找到'}")
        print(f"✓ 充电桩信息: {'已找到' if charge_point_id and 'charger' in locals() and charger else '未找到'}")
        
        # 保存到JSON文件
        report_data = {
            "transaction_id": transaction_id,
            "query_time": datetime.now().isoformat(),
            "server_url": self.server_url,
            "session": session,
            "meter_values": meter_values,
            "order": order,
            "charge_point": charger if charge_point_id and 'charger' in locals() else None,
        }
        
        report_file = f"transaction_data_{transaction_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"\n✓ 完整数据已保存到: {report_file}")


def main():
    parser = argparse.ArgumentParser(description="查询指定 transaction_id 的所有相关数据")
    parser.add_argument("--server", type=str, default="http://localhost:9000", help="CSMS服务器URL")
    parser.add_argument("--transaction-id", type=int, required=True, help="交易ID (transaction_id)")
    parser.add_argument("--charge-point-id", type=str, default=None, help="充电桩ID（可选，用于加速查询）")
    args = parser.parse_args()
    
    query = TransactionDataQuery(args.server)
    query.query_all(args.transaction_id, args.charge_point_id)


if __name__ == "__main__":
    main()

