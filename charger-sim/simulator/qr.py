from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import qrcode


@dataclass(frozen=True)
class QROptions:
    out_dir: Path
    payload_format: str = "hash"  # hash|query|json


def build_qr_payload(charge_point_id: str, connector_id: int, payload_format: str) -> str:
    if payload_format == "hash":
        return f"{charge_point_id}#{connector_id}"
    if payload_format == "query":
        return f"{charge_point_id}?connector={connector_id}"
    if payload_format == "json":
        return f'{{"chargePointId":"{charge_point_id}","connectorId":{connector_id}}}'
    raise ValueError(f"Unsupported payload_format={payload_format}")


def generate_connector_qr_png(charge_point_id: str, connector_id: int, opts: QROptions) -> Path:
    opts.out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_qr_payload(charge_point_id, connector_id, opts.payload_format)
    img = qrcode.make(payload)
    out_path = opts.out_dir / f"{charge_point_id}_connector_{connector_id}.png"
    img.save(str(out_path))
    return out_path

