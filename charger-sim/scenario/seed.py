from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Mapping


class SeedContractError(ValueError):
    pass


def normalize_seed(seed: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate development/test seed output without logging sensitive values."""
    value = copy.deepcopy(dict(seed))
    version = str(value.get("schema_version", ""))
    if version not in {"1.0", "1.1"}:
        raise SeedContractError("seed schema_version must be 1.0 or 1.1")
    if str(value.get("environment", "")).lower() not in {"development", "test"}:
        raise SeedContractError("seed is accepted only for development/test")
    def add_qr_token(qr: Any) -> None:
        if isinstance(qr, dict) and "token" not in qr:
            payload = qr.get("payload")
            if isinstance(payload, str) and payload.startswith("qr:") and len(payload) > 3:
                qr["token"] = payload[3:]

    add_qr_token(value.get("qr"))
    fixtures = value.get("fixtures")
    if version == "1.1":
        required = {
            "tenants": {"tenant_a", "tenant_b"},
            "admins": {"operator", "readonly"},
            "app_users": {"funded", "low_balance", "other"},
            "charge_points": {"primary", "other", "tenant_b"},
            "qrs": {"primary", "other", "tenant_b"},
        }
        if not isinstance(fixtures, Mapping):
            raise SeedContractError("seed 1.1 requires fixtures")
        for group, names in required.items():
            items = fixtures.get(group)
            if not isinstance(items, Mapping):
                raise SeedContractError(f"seed 1.1 requires fixtures.{group}")
            missing = sorted(name for name in names if not isinstance(items.get(name), Mapping))
            if missing:
                raise SeedContractError(
                    f"seed 1.1 missing fixtures.{group}: {', '.join(missing)}"
                )
        for name in ("ownership_session", "fake_top_up_order", "fault_alert"):
            if not isinstance(fixtures.get(name), Mapping):
                raise SeedContractError(f"seed 1.1 requires fixtures.{name}")

    if isinstance(fixtures, dict):
        qrs = fixtures.get("qrs")
        if isinstance(qrs, dict):
            for qr in qrs.values():
                add_qr_token(qr)
            value.setdefault("other_qr", qrs.get("other"))
        app_users = fixtures.get("app_users")
        if isinstance(app_users, dict):
            value.setdefault("app_user", app_users.get("funded"))
            value.setdefault("low_balance_app_user", app_users.get("low_balance"))
            value.setdefault("other_app_user", app_users.get("other"))
        admins = fixtures.get("admins")
        if isinstance(admins, dict):
            value.setdefault("admin", admins.get("operator"))
            value.setdefault("readonly_admin", admins.get("readonly"))
        tenants = fixtures.get("tenants")
        charge_points = fixtures.get("charge_points")
        if isinstance(tenants, dict) and isinstance(charge_points, dict):
            value.setdefault("tenant_id", (tenants.get("tenant_a") or {}).get("id"))
            value.setdefault("charge_point", charge_points.get("primary"))
            tenant_b = dict(tenants.get("tenant_b") or {})
            tenant_b["charge_point"] = charge_points.get("tenant_b")
            value.setdefault("tenant_b", tenant_b)
        if isinstance(qrs, dict):
            value.setdefault("qr", qrs.get("primary"))
        value.setdefault("ownership_session", fixtures.get("ownership_session"))
        value.setdefault("fake_top_up_order", fixtures.get("fake_top_up_order"))
        value.setdefault("fault_alert", fixtures.get("fault_alert"))
    return value


def load_seed_json(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SeedContractError(f"unable to read seed JSON: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise SeedContractError("seed JSON must be an object")
    return normalize_seed(raw)
