#!/usr/bin/env python3
#
# 清理没有正确建立的充电桩数据
# 删除以下情况的充电桩及其相关数据：
# 1. ChargePoint关联的device_serial_number对应的Device不存在
# 2. ChargePoint关联的device_serial_number对应的Device未激活
#

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.base import SessionLocal
from app.database.models import (
    ChargePoint, Device, EVSE, EVSEStatus, DeviceEvent,
    ChargePointConfig, ChargingSession, MeterValue, Invoice, Payment, Order
)
from sqlalchemy import func

def cleanup_invalid_charge_points(dry_run=True):
    """
    清理没有正确建立的充电桩数据
    
    Args:
        dry_run: 如果为True，只显示将要删除的数据，不实际删除
    """
    db = SessionLocal()
    try:
        print("=" * 60)
        print("开始清理无效的充电桩数据")
        print("=" * 60)
        
        # 查找所有ChargePoint
        all_charge_points = db.query(ChargePoint).all()
        print(f"\n总共有 {len(all_charge_points)} 个充电桩")
        
        invalid_charge_points = []
        
        # 检查每个ChargePoint
        for cp in all_charge_points:
            is_invalid = False
            reason = []
            
            # 如果ChargePoint关联了device_serial_number
            if cp.device_serial_number:
                # 检查Device是否存在
                device = db.query(Device).filter(
                    Device.serial_number == cp.device_serial_number
                ).first()
                
                if not device:
                    is_invalid = True
                    reason.append(f"设备 {cp.device_serial_number} 不存在")
                elif not device.is_active:
                    is_invalid = True
                    reason.append(f"设备 {cp.device_serial_number} 未激活")
            
            if is_invalid:
                invalid_charge_points.append({
                    "charge_point": cp,
                    "reasons": reason
                })
        
        if not invalid_charge_points:
            print("\n✓ 没有发现无效的充电桩数据")
            return
        
        print(f"\n发现 {len(invalid_charge_points)} 个无效的充电桩：")
        print("-" * 60)
        
        total_deleted = {
            "charge_points": 0,
            "evses": 0,
            "evse_statuses": 0,
            "device_events": 0,
            "charge_point_configs": 0,
            "charging_sessions": 0,
            "meter_values": 0,
            "orders": 0,
            "invoices": 0,
            "payments": 0,
        }
        
        for item in invalid_charge_points:
            cp = item["charge_point"]
            reasons = item["reasons"]
            
            print(f"\n充电桩 ID: {cp.id}")
            print(f"  设备SN: {cp.device_serial_number or 'N/A'}")
            print(f"  厂商: {cp.vendor or 'N/A'}")
            print(f"  型号: {cp.model or 'N/A'}")
            print(f"  无效原因: {', '.join(reasons)}")
            
            # 统计相关数据
            evses = db.query(EVSE).filter(EVSE.charge_point_id == cp.id).all()
            evse_statuses = db.query(EVSEStatus).filter(EVSEStatus.charge_point_id == cp.id).all()
            device_events = db.query(DeviceEvent).filter(DeviceEvent.charge_point_id == cp.id).all()
            charge_point_configs = db.query(ChargePointConfig).filter(ChargePointConfig.charge_point_id == cp.id).all()
            
            # 统计充电会话相关数据
            evse_ids = [evse.id for evse in evses]
            charging_sessions = []
            meter_values = []
            orders = db.query(Order).filter(Order.charge_point_id == cp.id).all()
            invoices = []
            payments = []
            
            if evse_ids:
                charging_sessions = db.query(ChargingSession).filter(
                    ChargingSession.evse_id.in_(evse_ids)
                ).all()
                
                session_ids = [session.id for session in charging_sessions]
                if session_ids:
                    meter_values = db.query(MeterValue).filter(
                        MeterValue.session_id.in_(session_ids)
                    ).all()
                    
                    invoices = db.query(Invoice).filter(
                        Invoice.session_id.in_(session_ids)
                    ).all()
                    
                    invoice_ids = [invoice.id for invoice in invoices]
                    if invoice_ids:
                        payments = db.query(Payment).filter(
                            Payment.invoice_id.in_(invoice_ids)
                        ).all()
            
            # 统计订单相关的发票和支付
            order_ids = [order.id for order in orders]
            if order_ids:
                order_invoices = db.query(Invoice).filter(
                    Invoice.order_id.in_(order_ids)
                ).all()
                invoices.extend(order_invoices)
                
                order_invoice_ids = [invoice.id for invoice in order_invoices]
                if order_invoice_ids:
                    order_payments = db.query(Payment).filter(
                        Payment.invoice_id.in_(order_invoice_ids)
                    ).all()
                    payments.extend(order_payments)
            
            print(f"  相关数据统计:")
            print(f"    - EVSE: {len(evses)}")
            print(f"    - EVSE状态: {len(evse_statuses)}")
            print(f"    - 设备事件: {len(device_events)}")
            print(f"    - 充电桩配置: {len(charge_point_configs)}")
            print(f"    - 订单: {len(orders)}")
            print(f"    - 充电会话: {len(charging_sessions)}")
            print(f"    - 计量值: {len(meter_values)}")
            print(f"    - 发票: {len(invoices)}")
            print(f"    - 支付: {len(payments)}")
            
            if not dry_run:
                # 删除相关数据（按外键依赖顺序）
                # 1. 删除支付记录
                for payment in payments:
                    db.delete(payment)
                total_deleted["payments"] += len(payments)
                
                # 2. 删除发票
                for invoice in invoices:
                    db.delete(invoice)
                total_deleted["invoices"] += len(invoices)
                
                # 3. 删除计量值
                for meter_value in meter_values:
                    db.delete(meter_value)
                total_deleted["meter_values"] += len(meter_values)
                
                # 4. 删除充电会话
                for session in charging_sessions:
                    db.delete(session)
                total_deleted["charging_sessions"] += len(charging_sessions)
                
                # 5. 删除订单
                for order in orders:
                    db.delete(order)
                total_deleted["orders"] += len(orders)
                
                # 6. 删除EVSE状态
                for evse_status in evse_statuses:
                    db.delete(evse_status)
                total_deleted["evse_statuses"] += len(evse_statuses)
                
                # 7. 删除EVSE（会级联删除相关数据）
                for evse in evses:
                    db.delete(evse)
                total_deleted["evses"] += len(evses)
                
                # 8. 删除设备事件
                for event in device_events:
                    db.delete(event)
                total_deleted["device_events"] += len(device_events)
                
                # 9. 删除充电桩配置
                for config in charge_point_configs:
                    db.delete(config)
                total_deleted["charge_point_configs"] += len(charge_point_configs)
                
                # 10. 删除充电桩本身
                db.delete(cp)
                total_deleted["charge_points"] += 1
                
                print(f"    ✓ 已删除")
            else:
                print(f"    [预览模式，未实际删除]")
        
        if not dry_run:
            db.commit()
            print("\n" + "=" * 60)
            print("清理完成！删除统计：")
            print("=" * 60)
            for key, count in total_deleted.items():
                if count > 0:
                    print(f"  - {key}: {count}")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("这是预览模式，没有实际删除数据")
            print("要实际执行删除，请运行: python cleanup_invalid_charge_points.py --execute")
            print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ 清理过程中发生错误: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="清理没有正确建立的充电桩数据")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行删除操作（默认是预览模式）"
    )
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    if dry_run:
        print("⚠️  预览模式：将显示要删除的数据，但不会实际删除")
        print("   使用 --execute 参数来实际执行删除操作\n")
    else:
        print("⚠️  警告：将实际删除无效的充电桩数据！")
        response = input("确认要继续吗？(yes/no): ")
        if response.lower() != "yes":
            print("已取消操作")
            sys.exit(0)
        print()
    
    cleanup_invalid_charge_points(dry_run=dry_run)

