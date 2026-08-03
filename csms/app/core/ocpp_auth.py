#
# OCPP 连接安全校验
#

import base64
import hashlib
import hmac
import os
import secrets
import logging
from app.core.asset_identifiers import OCPP_IDENTITY_PATTERN
from typing import Optional

logger = logging.getLogger("ocpp_csms")


def is_pre_registration_required() -> bool:
    return os.getenv("OCPP_WS_REQUIRE_PRE_REGISTERED", "true").lower() in ("true", "1", "yes")


def verify_charge_point_pre_registered(charge_point_id: str) -> bool:
    """校验充电桩是否已在系统中预注册。"""
    if not charge_point_id or not OCPP_IDENTITY_PATTERN.fullmatch(charge_point_id):
        return False
    try:
        from app.database.base import SuperSessionLocal
        from app.database.models import ChargePoint, Site

        # Pre-registration is a system lookup by transport identity, before a
        # tenant can be derived from the registered asset.
        db = SuperSessionLocal()
        try:
            return (
                db.query(ChargePoint.id).filter(
                    ChargePoint.ocpp_identity == charge_point_id,
                    ChargePoint.is_active.is_(True),
                    ChargePoint.site.has(Site.is_active.is_(True)),
                ).first()
                is not None
            )
        finally:
            db.close()
    except Exception as exc:
        logger.error("预注册校验失败 charge_point_id=%s: %s", charge_point_id, exc)
        return False


def generate_ocpp_secret() -> str:
    """Return a high-entropy credential that is shown exactly once."""
    return secrets.token_urlsafe(32)


def hash_ocpp_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _presented_secret(headers: dict, charge_point_id: str) -> Optional[str]:
    api_key = headers.get("x-api-key") or headers.get("X-API-Key")
    if api_key:
        return str(api_key).strip()
    authorization = str(headers.get("authorization") or headers.get("Authorization") or "").strip()
    if authorization.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(authorization.split(None, 1)[1], validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
            return password if username == charge_point_id else None
        except (ValueError, UnicodeDecodeError):
            return None
    if authorization.lower().startswith("bearer "):
        return authorization.split(None, 1)[1].strip()
    return None


def verify_ocpp_device_credential(charge_point_id: str, headers: dict) -> bool:
    """Verify the credential assigned to one pre-registered charge point."""
    presented = _presented_secret(headers, charge_point_id)
    if not presented:
        return False
    try:
        from app.database.base import SuperSessionLocal
        from app.database.models import ChargePoint, Site

        db = SuperSessionLocal()
        try:
            charge_point = db.query(ChargePoint).filter(
                ChargePoint.ocpp_identity == charge_point_id,
                ChargePoint.is_active == True,  # noqa: E712
                ChargePoint.site.has(Site.is_active.is_(True)),
            ).first()
            if not charge_point or not charge_point.ocpp_auth_secret_hash:
                return False
            return hmac.compare_digest(
                charge_point.ocpp_auth_secret_hash,
                hash_ocpp_secret(presented),
            )
        finally:
            db.close()
    except Exception as exc:
        logger.error("OCPP device credential lookup failed identity=%s: %s", charge_point_id, exc)
        return False


def _charge_point_has_device_credential(charge_point_id: str) -> bool:
    try:
        from app.database.base import SuperSessionLocal
        from app.database.models import ChargePoint, Site

        db = SuperSessionLocal()
        try:
            return db.query(ChargePoint.id).filter(
                ChargePoint.ocpp_identity == charge_point_id,
                ChargePoint.is_active.is_(True),
                ChargePoint.site.has(Site.is_active.is_(True)),
                ChargePoint.ocpp_auth_secret_hash.isnot(None),
            ).first() is not None
        finally:
            db.close()
    except Exception as exc:
        logger.error("OCPP credential presence lookup failed identity=%s: %s", charge_point_id, exc)
        return True


def is_secure_ocpp_websocket(headers: dict, scheme: str) -> bool:
    forwarded = str(headers.get("x-forwarded-proto") or headers.get("X-Forwarded-Proto") or "")
    effective_scheme = forwarded.split(",", 1)[0].strip().lower() or scheme.lower()
    return effective_scheme == "wss" or effective_scheme == "https"


def verify_ocpp_api_key(headers: dict, charge_point_id: Optional[str] = None) -> bool:
    """
    API Key 校验。生产环境必须配置并匹配 OCPP_API_KEYS。
    """
    if charge_point_id:
        # Lifecycle eligibility is mandatory even when pre-registration is
        # disabled at the transport layer or a non-production migration key is
        # configured. A retired charger/archived site must fail closed.
        if not verify_charge_point_pre_registered(charge_point_id):
            return False
        if verify_ocpp_device_credential(charge_point_id, headers):
            return True
        # Once a per-device credential exists, a wrong presented value must
        # never fall through to a development/global migration key.
        if _charge_point_has_device_credential(charge_point_id):
            return False

    keys_env = os.getenv("OCPP_API_KEYS", "").strip()
    if not keys_env:
        return os.getenv("ENVIRONMENT", "development").lower() != "production"
    valid_keys = {k.strip() for k in keys_env.split(",") if k.strip()}
    if not valid_keys:
        return os.getenv("ENVIRONMENT", "development").lower() != "production"
    api_key = (
        headers.get("x-api-key")
        or headers.get("X-API-Key")
        or headers.get("authorization", "").replace("Bearer ", "").strip()
    )
    # Global keys are migration-only and are never accepted in production.
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        return False
    return api_key in valid_keys
