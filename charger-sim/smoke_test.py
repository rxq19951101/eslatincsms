#!/usr/bin/env python3
"""本地 OCPP WebSocket 闭环自测。

流程：连接 -> BootNotification/StatusNotification -> RemoteStartTransaction
-> StartTransaction/MeterValues -> RemoteStopTransaction -> StopTransaction。

示例：
  python smoke_test.py --api http://localhost:9000 --ws ws://localhost:9000/ocpp
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any, Dict

import requests

from simulator.charge_point import connect_and_run
from simulator.profiles import ChargePointProfile, MeteringProfile


logger = logging.getLogger("charger_sim_smoke")


def require_successful_response(response: requests.Response, operation: str) -> Dict[str, Any]:
    """Fail a smoke stage with the backend validation body preserved for diagnosis."""
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"{operation} HTTP {response.status_code}: {response.text}"
        ) from exc
    body = response.json()
    if body.get("success") is False:
        raise RuntimeError(f"{operation} rejected: {body}")
    return body


def login(api: str, username: str, password: str) -> Dict[str, str]:
    response = requests.post(
        f"{api}/api/v1/admin/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    body = require_successful_response(response, "login")
    token = body.get("access_token")
    if not token:
        raise RuntimeError("login response did not contain access_token")
    return {"Authorization": f"Bearer {token}"}


def call_remote_start(
    api: str,
    ocpp_identity: str,
    id_tag: str,
    connector_id: int,
    headers: Dict[str, str],
) -> None:
    response = requests.post(
        f"{api}/api/v1/ocpp/remote-start-transaction",
        json={"charge_point_id": ocpp_identity, "id_tag": id_tag, "connector_id": connector_id},
        headers=headers,
        timeout=10,
    )
    require_successful_response(response, "remote-start")


def call_remote_stop(
    api: str,
    ocpp_identity: str,
    transaction_id: int,
    headers: Dict[str, str],
) -> None:
    response = requests.post(
        f"{api}/api/v1/ocpp/remote-stop-transaction",
        json={"charge_point_id": ocpp_identity, "transaction_id": transaction_id},
        headers=headers,
        timeout=10,
    )
    require_successful_response(response, "remote-stop")


async def wait_until(predicate, timeout: float, description: str) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for {description}")


async def run(args: argparse.Namespace) -> None:
    runtime: Dict[str, Any] = {}
    ready = asyncio.Event()
    profile = ChargePointProfile(
        charge_point_id=args.ocpp_identity,
        serial_number=args.serial_number,
        heartbeat_interval_sec=args.heartbeat_interval,
    )
    meterings = [
        MeteringProfile(
            connector_id=args.connector_id,
            power_kw=args.power_kw,
            meter_values_interval_sec=args.meter_interval,
        )
    ]
    simulator_task = asyncio.create_task(
        connect_and_run(
            profile=profile,
            meterings=meterings,
            ws_base=args.ws,
            runtime_holder=runtime,
            ready_event=ready,
        )
    )
    try:
        await asyncio.wait_for(ready.wait(), timeout=args.timeout)
        logger.info(
            "PASS connected and boot notification completed (identity=%s serial=%s)",
            profile.ocpp_identity,
            profile.boot_serial_number,
        )

        headers = await asyncio.to_thread(login, args.api, args.username, args.password)
        logger.info("PASS authenticated admin API")

        await asyncio.to_thread(
            call_remote_start,
            args.api,
            args.ocpp_identity,
            args.id_tag,
            args.connector_id,
            headers,
        )
        cp = runtime["charge_point"]
        connector = cp.state.connectors[args.connector_id]
        await wait_until(lambda: connector.transaction_id is not None, args.timeout, "StartTransaction")
        transaction_id = int(connector.transaction_id)
        logger.info("PASS remote start, transaction_id=%s", transaction_id)

        await asyncio.sleep(args.duration)
        meter_before_stop = connector.meter.meter_wh
        if meter_before_stop <= 0:
            raise RuntimeError("MeterValues did not advance")
        logger.info("PASS meter values advanced, meter_wh=%s", meter_before_stop)

        await asyncio.to_thread(
            call_remote_stop,
            args.api,
            args.ocpp_identity,
            transaction_id,
            headers,
        )
        await wait_until(lambda: connector.transaction_id is None, args.timeout, "StopTransaction")
        logger.info("PASS remote stop and StopTransaction completed")
    finally:
        simulator_task.cancel()
        try:
            await simulator_task
        except asyncio.CancelledError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:9000")
    parser.add_argument("--ws", default="ws://localhost:9000/ocpp")
    parser.add_argument("--username", default="admin", help="管理员用户名")
    parser.add_argument("--password", default="admin123", help="本地测试管理员密码")
    parser.add_argument(
        "--ocpp-identity",
        "--charge-point-id",
        dest="ocpp_identity",
        default="SIM_CP_SMOKE_001",
        help="预先在 Admin 注册的 WebSocket/OCPP identity",
    )
    parser.add_argument(
        "--serial-number",
        default="SIM_SERIAL_SMOKE_9001",
        help="BootNotification chargePointSerialNumber（smoke 默认故意与 identity 不同）",
    )
    parser.add_argument("--connector-id", type=int, default=1)
    parser.add_argument("--id-tag", default="TEST_TAG_001")
    parser.add_argument("--duration", type=float, default=10, help="充电计量持续秒数")
    parser.add_argument("--timeout", type=float, default=20, help="每个阶段最大等待秒数")
    parser.add_argument("--heartbeat-interval", type=int, default=30)
    parser.add_argument("--meter-interval", type=int, default=2)
    parser.add_argument("--power-kw", type=float, default=7.0)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
