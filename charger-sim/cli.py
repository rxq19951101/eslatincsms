#!/usr/bin/env python3
"""
EsLatin 充电桩模拟器（OCPP 1.6J WebSocket）

用法示例：
  - 单桩：
    python cli.py run-one --ws ws://localhost:9000/ocpp --charge-point-id CP_SITE_001_01 --connector-id 1

  - 批量（yaml/json）：
    python cli.py run-many --config chargers.yml

  - 生成二维码：
    python cli.py gen-qr --charge-point-id CP_SITE_001_01 --connector-id 1 --out-dir ./out/qr
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

from simulator.charge_point import connect_and_run
from simulator.profiles import ChargePointProfile, MeteringProfile
from simulator.qr import QROptions, generate_connector_qr_png


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def load_config(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in [".yaml", ".yml"]:
        return yaml.safe_load(raw)
    return json.loads(raw)


async def run_one(args) -> None:
    profile = ChargePointProfile(
        charge_point_id=args.charge_point_id,
        vendor=args.vendor,
        model=args.model,
        firmware_version=args.firmware_version,
        serial_number=args.serial_number or args.charge_point_id,
        heartbeat_interval_sec=args.heartbeat_interval,
    )
    connector_ids = args.connector_id
    meterings = [
        MeteringProfile(
            connector_id=cid,
            power_kw=args.power_kw,
            voltage_v=args.voltage_v,
            current_a=args.current_a,
            soc_start=args.soc_start,
            soc_end=args.soc_end,
            meter_values_interval_sec=args.meter_interval,
        )
        for cid in connector_ids
    ]

    if args.gen_qr:
        for cid in connector_ids:
            out = generate_connector_qr_png(
                args.charge_point_id,
                cid,
                QROptions(out_dir=Path(args.qr_out_dir), payload_format=args.qr_format),
            )
            print(f"QR saved: {out}")

    await connect_and_run(profile=profile, meterings=meterings, ws_base=args.ws)


async def run_many(args) -> None:
    cfg = load_config(Path(args.config))
    ws = cfg.get("ws") or args.ws
    chargers: List[Dict[str, Any]] = cfg.get("chargers") or []
    if not ws:
        raise SystemExit("Missing ws in config or --ws")
    if not chargers:
        raise SystemExit("No chargers in config")

    tasks = []
    for c in chargers:
        cp_id = c["charge_point_id"]
        connector_ids = c.get("connector_ids") or [c.get("connector_id", 1)]
        connector_ids = [int(x) for x in connector_ids]
        profile = ChargePointProfile(
            charge_point_id=cp_id,
            vendor=c.get("vendor", "EsLatin"),
            model=c.get("model", "EsLatin-Sim-1.0"),
            firmware_version=c.get("firmware_version", "1.0.0"),
            serial_number=c.get("serial_number") or cp_id,
            heartbeat_interval_sec=int(c.get("heartbeat_interval", 30)),
        )
        meterings = [
            MeteringProfile(
                connector_id=cid,
                power_kw=float(c.get("power_kw", 7.0)),
                voltage_v=float(c.get("voltage_v", 220.0)),
                current_a=float(c.get("current_a", 16.0)),
                soc_start=float(c.get("soc_start", 20.0)),
                soc_end=float(c.get("soc_end", 90.0)),
                meter_values_interval_sec=int(c.get("meter_interval", 5)),
            )
            for cid in connector_ids
        ]
        tasks.append(connect_and_run(profile=profile, meterings=meterings, ws_base=ws))

    await asyncio.gather(*tasks)


def gen_qr(args) -> None:
    for cid in args.connector_id:
        out = generate_connector_qr_png(
            args.charge_point_id,
            cid,
            QROptions(out_dir=Path(args.out_dir), payload_format=args.format),
        )
        print(f"QR saved: {out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("run-one")
    p1.add_argument("--ws", required=True, help="例如 ws://localhost:9000/ocpp")
    p1.add_argument("--charge-point-id", required=True)
    p1.add_argument("--connector-id", required=True, type=int, action="append", help="可重复传多次：--connector-id 1 --connector-id 2")
    p1.add_argument("--vendor", default="EsLatin")
    p1.add_argument("--model", default="EsLatin-Sim-1.0")
    p1.add_argument("--firmware-version", default="1.0.0")
    p1.add_argument("--serial-number", default=None)
    p1.add_argument("--heartbeat-interval", type=int, default=30)
    p1.add_argument("--meter-interval", type=int, default=5)
    p1.add_argument("--power-kw", type=float, default=7.0)
    p1.add_argument("--voltage-v", type=float, default=220.0)
    p1.add_argument("--current-a", type=float, default=16.0)
    p1.add_argument("--soc-start", type=float, default=20.0)
    p1.add_argument("--soc-end", type=float, default=90.0)
    p1.add_argument("--gen-qr", action="store_true")
    p1.add_argument("--qr-out-dir", default="./out/qr")
    p1.add_argument("--qr-format", default="hash", choices=["hash", "query", "json"])

    p2 = sub.add_parser("run-many")
    p2.add_argument("--config", required=True, help="yaml/json")
    p2.add_argument("--ws", default=None, help="可覆盖 config.ws")

    p3 = sub.add_parser("gen-qr")
    p3.add_argument("--charge-point-id", required=True)
    p3.add_argument("--connector-id", required=True, type=int, action="append")
    p3.add_argument("--out-dir", required=True)
    p3.add_argument("--format", default="hash", choices=["hash", "query", "json"])

    return p


async def main_async() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)
    if args.cmd == "run-one":
        await run_one(args)
    elif args.cmd == "run-many":
        await run_many(args)
    elif args.cmd == "gen-qr":
        gen_qr(args)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

