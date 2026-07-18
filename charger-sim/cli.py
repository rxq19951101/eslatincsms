#!/usr/bin/env python3
"""
EsLatin 充电桩模拟器（OCPP 1.6J WebSocket）

用法示例：
  - 单桩：
    python cli.py run-one --ws ws://localhost:9000/ocpp --ocpp-identity CP_SITE_001_01 --connector-id 1

  - 批量（yaml/json）：
    python cli.py run-many --config chargers.yml

  - 生成二维码：
    python cli.py gen-qr --ocpp-identity CP_SITE_001_01 --connector-id 1 \
      --qr-token SERVER_ASSIGNED_TOKEN --out-dir ./out/qr
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from simulator.charge_point import connect_and_run
from simulator.profiles import ChargePointProfile, MeteringProfile
from simulator.qr import QR_PREREGISTRATION_HINT, QROptions, generate_connector_qr_png


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
        charge_point_id=args.ocpp_identity,
        vendor=args.vendor,
        model=args.model,
        firmware_version=args.firmware_version,
        serial_number=args.serial_number,
        heartbeat_interval_sec=args.heartbeat_interval,
        enable_payment_simulation=args.enable_payment,
        payment_delay_seconds=args.payment_delay,
        payment_amount=args.payment_amount,
        payment_test_card=args.payment_test_card,
        backend_api_url=args.backend_api_url,
        backend_api_token=args.backend_api_token,
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
        for cid, qr_token, scan_url in resolve_qr_sources(
            connector_ids, args.qr_token, args.scan_url
        ):
            out = generate_connector_qr_png(
                args.ocpp_identity,
                cid,
                QROptions(out_dir=Path(args.qr_out_dir)),
                qr_token=qr_token,
                scan_url=scan_url,
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
        cp_id = c.get("ocpp_identity") or c.get("charge_point_id")
        if not cp_id:
            raise SystemExit("Each charger requires ocpp_identity (legacy charge_point_id is also accepted)")
        connector_ids = c.get("connector_ids") or [c.get("connector_id", 1)]
        connector_ids = [int(x) for x in connector_ids]
        profile = ChargePointProfile(
            charge_point_id=cp_id,
            vendor=c.get("vendor", "EsLatin"),
            model=c.get("model", "EsLatin-Sim-1.0"),
            firmware_version=c.get("firmware_version", "1.0.0"),
            serial_number=c.get("serial_number"),
            heartbeat_interval_sec=int(c.get("heartbeat_interval", 30)),
            enable_payment_simulation=args.enable_payment if hasattr(args, "enable_payment") else c.get("enable_payment_simulation", True),
            payment_delay_seconds=args.payment_delay if hasattr(args, "payment_delay") else c.get("payment_delay_seconds", 5),
            payment_amount=args.payment_amount if hasattr(args, "payment_amount") else c.get("payment_amount"),
            payment_test_card=args.payment_test_card if hasattr(args, "payment_test_card") else c.get("payment_test_card", "visa_approved"),
            backend_api_url=args.backend_api_url if hasattr(args, "backend_api_url") else c.get("backend_api_url"),
            backend_api_token=args.backend_api_token if hasattr(args, "backend_api_token") else c.get("backend_api_token"),
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


def resolve_qr_sources(
    connector_ids: List[int],
    qr_tokens: Optional[List[str]],
    scan_urls: Optional[List[str]],
) -> List[Tuple[int, Optional[str], Optional[str]]]:
    """Pair one server-controlled QR source with each connector, preserving CLI order."""
    if qr_tokens and scan_urls:
        raise ValueError("Use either --qr-token or --scan-url, not both")
    sources = qr_tokens or scan_urls
    if not sources:
        raise ValueError(QR_PREREGISTRATION_HINT)
    if len(sources) != len(connector_ids):
        option = "--qr-token" if qr_tokens else "--scan-url"
        raise ValueError(
            f"Provide exactly one {option} per --connector-id in the same order "
            f"({len(connector_ids)} connectors, {len(sources)} sources)"
        )
    return [
        (connector_id, source if qr_tokens else None, source if scan_urls else None)
        for connector_id, source in zip(connector_ids, sources)
    ]


def gen_qr(args) -> None:
    for cid, qr_token, scan_url in resolve_qr_sources(
        args.connector_id, args.qr_token, args.scan_url
    ):
        out = generate_connector_qr_png(
            args.ocpp_identity,
            cid,
            QROptions(out_dir=Path(args.out_dir)),
            qr_token=qr_token,
            scan_url=scan_url,
        )
        print(f"QR saved: {out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("run-one")
    p1.add_argument("--ws", required=True, help="例如 ws://localhost:9000/ocpp")
    p1.add_argument(
        "--ocpp-identity",
        "--charge-point-id",
        dest="ocpp_identity",
        required=True,
        help="WebSocket/OCPP identity；--charge-point-id 为兼容别名",
    )
    p1.add_argument("--connector-id", required=True, type=int, action="append", help="可重复传多次：--connector-id 1 --connector-id 2")
    p1.add_argument("--vendor", default="EsLatin")
    p1.add_argument("--model", default="EsLatin-Sim-1.0")
    p1.add_argument("--firmware-version", default="1.0.0")
    p1.add_argument(
        "--serial-number",
        default=None,
        help="BootNotification chargePointSerialNumber；默认与 OCPP identity 相同",
    )
    p1.add_argument("--heartbeat-interval", type=int, default=30)
    p1.add_argument("--meter-interval", type=int, default=5)
    p1.add_argument("--power-kw", type=float, default=7.0)
    p1.add_argument("--voltage-v", type=float, default=220.0)
    p1.add_argument("--current-a", type=float, default=16.0)
    p1.add_argument("--soc-start", type=float, default=20.0)
    p1.add_argument("--soc-end", type=float, default=90.0)
    p1.add_argument("--gen-qr", action="store_true")
    p1.add_argument("--qr-out-dir", default="./out/qr")
    p1.add_argument(
        "--qr-token",
        action="append",
        help="Admin 预注册后返回的原始 qr_token；每个 connector 按顺序重复一次",
    )
    p1.add_argument(
        "--scan-url",
        action="append",
        help="服务端分配的扫码 URL；每个 connector 按顺序重复一次",
    )
    # 支付模拟参数
    p1.add_argument("--enable-payment", action="store_true", default=True, help="启用支付模拟（默认启用）")
    p1.add_argument("--disable-payment", action="store_false", dest="enable_payment", help="禁用支付模拟")
    p1.add_argument("--payment-delay", type=int, default=5, help="支付延迟时间（秒，模拟用户操作）")
    p1.add_argument("--payment-amount", type=float, default=None, help="支付金额（COP），默认 10000")
    p1.add_argument("--payment-test-card", default="visa_approved", choices=["visa_approved", "master_approved", "pending", "rejected"], help="测试卡类型")
    p1.add_argument("--backend-api-url", default=None, help="后端 API URL（例如 http://localhost:9000）")
    p1.add_argument("--backend-api-token", default=None, help="后端 API 认证 token（如果需要）")

    p2 = sub.add_parser("run-many")
    p2.add_argument("--config", required=True, help="yaml/json")
    p2.add_argument("--ws", default=None, help="可覆盖 config.ws")

    p3 = sub.add_parser("gen-qr")
    p3.add_argument(
        "--ocpp-identity",
        "--charge-point-id",
        dest="ocpp_identity",
        required=True,
        help="仅用于输出文件名，不用于合成二维码内容",
    )
    p3.add_argument("--connector-id", required=True, type=int, action="append")
    p3.add_argument("--out-dir", required=True)
    p3.add_argument(
        "--qr-token",
        action="append",
        help="Admin 预注册后返回的原始 qr_token；每个 connector 按顺序重复一次",
    )
    p3.add_argument(
        "--scan-url",
        action="append",
        help="服务端分配的扫码 URL；每个 connector 按顺序重复一次",
    )

    return p


async def main_async() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)
    if args.cmd == "run-one":
        try:
            await run_one(args)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.cmd == "run-many":
        await run_many(args)
    elif args.cmd == "gen-qr":
        try:
            gen_qr(args)
        except ValueError as exc:
            parser.error(str(exc))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
