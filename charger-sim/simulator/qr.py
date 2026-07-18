from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import qrcode


QR_PREREGISTRATION_HINT = (
    "Missing server-assigned QR input. Pre-register the charger in Admin, obtain "
    "the connector qr_token or scan URL, then pass --qr-token or --scan-url."
)


@dataclass(frozen=True)
class QROptions:
    out_dir: Path


def build_qr_payload(*, qr_token: Optional[str] = None, scan_url: Optional[str] = None) -> str:
    """Build only a server-authorized QR payload; never derive one from charger identity."""
    if bool(qr_token) == bool(scan_url):
        if not qr_token and not scan_url:
            raise ValueError(QR_PREREGISTRATION_HINT)
        raise ValueError("Provide exactly one of qr_token or scan_url")

    if qr_token is not None:
        token = qr_token.strip()
        if not token or any(char.isspace() for char in token):
            raise ValueError("qr_token must be a non-empty server-assigned token without whitespace")
        if token.lower().startswith("qr:"):
            raise ValueError("Pass the raw server qr_token without the 'qr:' prefix")
        return f"qr:{token}"

    url = scan_url.strip() if scan_url is not None else ""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("scan_url must be an absolute http(s) URL assigned by the server")
    return url


def generate_connector_qr_png(
    ocpp_identity: str,
    connector_id: int,
    opts: QROptions,
    *,
    qr_token: Optional[str] = None,
    scan_url: Optional[str] = None,
) -> Path:
    payload = build_qr_payload(qr_token=qr_token, scan_url=scan_url)
    opts.out_dir.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(payload)
    out_path = opts.out_dir / f"{ocpp_identity}_connector_{connector_id}.png"
    img.save(str(out_path))
    return out_path
