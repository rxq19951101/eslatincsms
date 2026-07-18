#
# OCPP 连接安全校验
#

import os
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
        from app.database.base import SessionLocal
        from app.database.models import ChargePoint

        db = SessionLocal()
        try:
            return (
                db.query(ChargePoint.id).filter(ChargePoint.ocpp_identity == charge_point_id).first()
                is not None
            )
        finally:
            db.close()
    except Exception as e:
        logger.error("预注册校验失败 charge_point_id=%s: %s", charge_point_id, e)
        return False


def verify_ocpp_api_key(headers: dict) -> bool:
    """
    API Key 校验。生产环境必须配置并匹配 OCPP_API_KEYS。
    """
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
    return api_key in valid_keys
