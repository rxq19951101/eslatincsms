#!/usr/bin/env python3
"""
最小自测脚本（不依赖后台 UI）：
- 启动一个模拟桩（WebSocket /ocpp）
- 调用 csms 的 RemoteStart/RemoteStop HTTP 接口

注意：
1) 本脚本假定 csms 对外地址是 http://localhost:9000
2) OCPP WS 地址是 ws://localhost:9000/ocpp
3) 该项目后端 RemoteStart/Stop 路由为 /api/v1/ocpp/remote-start-transaction 与 /api/v1/ocpp/remote-stop-transaction
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import requests

from simulator.charge_point import connect_and_run
from simulator.profiles import ChargePointProfile, MeteringProfile


async def run_sim(ws: str, charge_point_id: str, connector_id: int) -> None:
    profile = ChargePointProfile(charge_point_id=charge_point_id, serial_number=charge_point_id)
    meterings = [MeteringProfile(connector_id=connector_id, power_kw=7.0, meter_values_interval_sec=3)]
    await connect_and_run(profile=profile, meterings=meterings, ws_base=ws)


def remote_start(api: str, charge_point_id: str, id_tag: str, connector_id: int) -> None:
    url = f"{api}/api/v1/ocpp/remote-start-transaction"
    r = requests.post(url, json={"chargePointId": charge_point_id, "idTag": id_tag, "connectorId": connector_id}, timeout=10)
    print("remote-start", r.status_code, r.text)


def remote_stop(api: str, charge_point_id: str, transaction_id: int) -> None:
    url = f"{api}/api/v1/ocpp/remote-stop-transaction"
    r = requests.post(url, json={"chargePointId": charge_point_id, "transactionId": transaction_id}, timeout=10)
    print("remote-stop", r.status_code, r.text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:9000")
    ap.add_argument("--ws", default="ws://localhost:9000/ocpp")
    ap.add_argument("--charge-point-id", default="SIM_CP_001")
    ap.add_argument("--connector-id", type=int, default=1)
    ap.add_argument("--id-tag", default="TEST_TAG_001")
    args = ap.parse_args()

    # 启动模拟器（后台任务）
    loop = asyncio.get_event_loop()
    sim_task = loop.create_task(run_sim(args.ws, args.charge_point_id, args.connector_id))

    # 等待连接稳定
    time.sleep(2)

    # 发起远程启动
    remote_start(args.api, args.charge_point_id, args.id_tag, args.connector_id)

    print("waiting 10s for meter values...")
    time.sleep(10)

    # 无法可靠拿到 transactionId（取决于后端实现/日志），此处仅提供手动提示
    print("If you want to test remote-stop, call it with a known transactionId from server logs.")
    print("Done.")

    # 结束
    sim_task.cancel()
    try:
        loop.run_until_complete(sim_task)
    except Exception:
        pass


if __name__ == "__main__":
    main()

