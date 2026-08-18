#
# APP用户 - 扫码充电API
# 提供给终端用户通过扫码启动/结束充电的接口
#

import asyncio
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID

from app.core.logging_config import get_logger
from app.core.api_logging import log_api_request, log_api_response, log_api_error, log_business_operation
from app.core.auth import get_current_user
from app.database.base import get_db, SuperSessionLocal
from app.database.models import AppUser, ChargingSession, MeterValue, AppWalletTransaction, Tariff, ChargePoint, EVSEStatus, EVSE, Site, Invoice
from app.services.charging_payment_intent import (
    PaymentIntentError,
    find_intent_order,
    find_start_requested_order,
    write_intent,
)
from app.services.billing_service import BillingService
from app.services.pricing_service import PricingMode, PricingService
from app.services.meter_telemetry_service import meter_telemetry_service
from app.services.asset_lifecycle_service import (
    AssetNotOperationalError,
    require_charge_point_operational,
)
from app.services.qr_service import InvalidQrTokenError, resolve_qr_token
from app.services.financial_eligibility import (
    ChargingAdmissionPreflight,
    FinancialEligibilityEvaluator,
)

from app.api.v1.ocpp_control import (
    check_charger_connection,
    send_remote_start,
    send_remote_stop,
)

logger = get_logger("ocpp_csms")

router = APIRouter()


_start_attempts: dict[tuple[str, str, int], asyncio.Task] = {}
_start_attempts_guard = asyncio.Lock()
_ACCEPTED_START_REPLAY_SECONDS = 30.0


def _session_public_data(
    session: ChargingSession,
    charge_point: ChargePoint,
    connector_id: int,
) -> Dict[str, Any]:
    """Return the public data needed by the App to resume an active charge."""
    return {
        "session_id": str(session.id),
        "transaction_id": session.transaction_id,
        "charge_point_id": str(charge_point.id),
        "ocpp_identity": charge_point.ocpp_identity,
        "connector_id": connector_id,
        "start_time": session.start_time.isoformat() if session.start_time else None,
        "status": session.status,
        "meter_start": session.meter_start,
        "meter_stop": session.meter_stop,
    }


def _remote_start_payload(result: Any) -> Dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "dict"):
        return result.dict()
    if isinstance(result, dict):
        return dict(result)
    return {}


def _remote_device_status(payload: Dict[str, Any]) -> Optional[str]:
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return details.get("device_status") or data.get("status") or payload.get("status")


async def _coalesced_remote_start(
    key: tuple[str, str, int],
    charge_point_identity: str,
    id_tag: str,
    connector_id: int,
) -> Any:
    """Share one device command between concurrent identical App requests."""
    async with _start_attempts_guard:
        task = _start_attempts.get(key)
        if task is None:
            task = asyncio.create_task(
                send_remote_start(charge_point_identity, id_tag, connector_id)
            )
            _start_attempts[key] = task

    try:
        result = await asyncio.shield(task)
    except BaseException:
        async with _start_attempts_guard:
            if _start_attempts.get(key) is task:
                _start_attempts.pop(key, None)
        raise

    payload = _remote_start_payload(result)
    device_status = _remote_device_status(payload)
    if payload.get("success") and device_status == "Accepted":
        loop = asyncio.get_running_loop()

        def expire() -> None:
            if _start_attempts.get(key) is task:
                _start_attempts.pop(key, None)

        loop.call_later(_ACCEPTED_START_REPLAY_SECONDS, expire)
    else:
        async with _start_attempts_guard:
            if _start_attempts.get(key) is task:
                _start_attempts.pop(key, None)
    return result


def _business_error(status_code: int, code: str, message: str, **details: Any) -> HTTPException:
    exc = HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, **details},
    )
    exc.error_code = code
    return exc


def _has_global_unpaid_charging_bill(db: Session, app_user_id: UUID) -> bool:
    """Compatibility helper backed exclusively by the canonical evaluator."""
    return FinancialEligibilityEvaluator.evaluate(
        db, app_user_id=app_user_id
    ).status != "eligible"


def _reset_claimed_payment_intent(
    *,
    intent_id: str,
    app_user_id: Optional[UUID],
    connector_id: Optional[int],
) -> None:
    """Return an intent to ``ready`` only after a device command failed."""

    if app_user_id is None or connector_id is None:
        return
    db = SuperSessionLocal()
    try:
        matched = find_intent_order(
            db,
            intent_id=intent_id,
            app_user_id=app_user_id,
            connector_id=connector_id,
            lock=True,
        )
        if matched is None:
            return
        order, intent = matched
        if intent.status == "start_requested" and not intent.is_expired():
            write_intent(order, intent.with_state("ready"))
            db.commit()
    except Exception:
        db.rollback()
        logger.warning("Unable to reset failed charging payment intent", exc_info=True)
    finally:
        db.close()


def _resolve_operational_qr(db: Session, token: str):
    try:
        return resolve_qr_token(db=db, token=token)
    except AssetNotOperationalError as exc:
        raise _business_error(409, exc.code, exc.message) from exc
    except InvalidQrTokenError as exc:
        raise _business_error(400, exc.code, exc.message) from exc


def _require_operational_business_asset(charge_point: ChargePoint) -> None:
    try:
        require_charge_point_operational(charge_point)
    except AssetNotOperationalError as exc:
        raise _business_error(409, exc.code, exc.message) from exc


def _require_commissioned(charge_point: ChargePoint) -> None:
    if charge_point.commissioning_status != "commissioned":
        raise _business_error(
            409,
            "CHARGER_NOT_COMMISSIONED",
            "This charger is not commissioned for commercial charging.",
        )


async def get_current_app_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppUser:
    """
    获取当前平台终端用户对象（AppUser）
    """
    user_id = current_user_payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        user_id = UUID(str(user_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    app_user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not app_user:
        raise HTTPException(status_code=404, detail="User not found")

    return app_user


class StartChargingRequest(BaseModel):
    qr_token: str = Field(..., description="二维码 token（爆改测试版：token-only）", min_length=10)
    settlement_method: Literal["wallet", "direct_card"] = Field(
        "wallet",
        description="结算方式；未升级的客户端默认为 wallet",
    )
    payment_intent_id: Optional[str] = Field(
        None,
        min_length=16,
        max_length=128,
        description="charging_direct checkout confirm 返回的 opaque intent ID",
    )


class StopChargingRequest(BaseModel):
    qr_token: Optional[str] = Field(
        None,
        description="二维码 token；与 session_id 二选一",
        min_length=10,
    )
    session_id: Optional[UUID] = Field(
        None,
        description="当前认证 AppUser 的 ongoing charging session UUID；与 qr_token 二选一",
    )

    @model_validator(mode="after")
    def exactly_one_reference(self):
        if (self.qr_token is None) == (self.session_id is None):
            raise ValueError("Exactly one of qr_token or session_id must be provided")
        return self


class SettleChargingRequest(BaseModel):
    session_id: UUID = Field(..., description="charging_sessions.id UUID（停止后用该session结算）")


@router.post("/start", summary="扫码启动充电（终端用户）")
async def start_charging_by_scan(
    req: StartChargingRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """Resolve a QR token and wait for the device's RemoteStart response."""
    claimed_intent_id: Optional[str] = None
    claimed_intent_connector: Optional[int] = None
    claimed_intent_user: Optional[UUID] = None
    try:
        log_api_request(
            method="POST",
            path="/api/v1/app/charging/start",
            operation="start_charging",
            current_user=current_user_obj,
            params={"qr_token": "[REDACTED]"}
        )
        
        lookup_db = SuperSessionLocal()
        try:
            token_rec = _resolve_operational_qr(db=lookup_db, token=req.qr_token)
        except HTTPException:
            raise
        except Exception as e:
            log_api_error(
                method="POST",
                path="/api/v1/app/charging/start",
                operation="start_charging",
                error=e,
                current_user=current_user_obj,
                params={"qr_token": "[REDACTED]"}
            )
            raise HTTPException(status_code=400, detail=f"Invalid QR token: {e}")
        finally:
            lookup_db.close()

        # App users are platform identities. QR ownership, not a client-selected
        # tenant, defines the operator scope for this command.
        sdb = SuperSessionLocal()
        try:
            app_user = sdb.query(AppUser).filter(AppUser.id == current_user_obj.id).first()
            charge_point = sdb.query(ChargePoint).filter(
                ChargePoint.id == token_rec.charge_point_id,
                ChargePoint.tenant_id == token_rec.operator_tenant_id,
            ).with_for_update().first()
            if not charge_point:
                raise HTTPException(status_code=404, detail="Charge point not found")
            _require_operational_business_asset(charge_point)
            charge_point_identity = charge_point.ocpp_identity
            charge_point_uuid = charge_point.id

            evse = sdb.query(EVSE).filter(
                EVSE.charge_point_id == charge_point.id,
                EVSE.evse_id == token_rec.connector_id,
            ).first()
            if not evse:
                raise HTTPException(status_code=422, detail="QR connector does not exist")

            active_session = (
                sdb.query(ChargingSession)
                .filter(
                    ChargingSession.tenant_id == charge_point.tenant_id,
                    ChargingSession.charge_point_id == charge_point.id,
                    ChargingSession.evse_id == evse.id,
                    ChargingSession.status == "ongoing",
                    ChargingSession.end_time.is_(None),
                )
                .order_by(ChargingSession.start_time.desc())
                .first()
            )
            if active_session:
                is_owner = (
                    active_session.app_user_id == current_user_obj.id
                    or active_session.user_id == str(current_user_obj.id)
                )
                if is_owner:
                    return {
                        "success": True,
                        "status": "already_active",
                        "ocpp_identity": charge_point.ocpp_identity,
                        "session": _session_public_data(
                            active_session, charge_point, token_rec.connector_id
                        ),
                    }
                raise _business_error(
                    409,
                    "CONNECTOR_OCCUPIED",
                    "The connector already has an active charging session.",
                    ocpp_identity=charge_point.ocpp_identity,
                    connector_id=token_rec.connector_id,
                )

            _require_commissioned(charge_point)
            pricing = PricingService.resolve(
                sdb, charge_point.tenant_id, charge_point.id
            )
            if not pricing.is_available:
                raise _business_error(
                    409,
                    "TARIFF_NOT_CONFIGURED",
                    "This charger is not currently available for commercial charging.",
                )

            if not app_user:
                raise HTTPException(status_code=404, detail="User not found")

            admission = ChargingAdmissionPreflight.evaluate(
                sdb,
                app_user_id=current_user_obj.id,
                qr_token=req.qr_token,
                settlement_method=req.settlement_method,
            )
            if admission.decision != "allowed":
                financial = admission.financial_eligibility
                if financial.status != "eligible":
                    if financial.status == "blocked":
                        raise _business_error(
                            402,
                            "FINANCIAL_ELIGIBILITY_BLOCKED",
                            "Financial eligibility does not allow charging.",
                            reason_codes=list(financial.reason_codes),
                            blocking_resources=list(financial.blocking_resources),
                            version=financial.decision_version,
                        )
                    if financial.status == "recheck_required":
                        raise _business_error(
                            409,
                            "FINANCIAL_RECHECK_REQUIRED",
                            "Financial facts are still being reconciled.",
                            reason_codes=list(financial.reason_codes),
                            version=financial.decision_version,
                        )
                    raise _business_error(
                        503,
                        "RECOVERY_UNKNOWN",
                        "Financial facts are not currently known.",
                        reason_codes=list(financial.reason_codes),
                        version=financial.decision_version,
                    )
                if admission.rail_eligibility.status == "closed":
                    raise _business_error(
                        503,
                        "RAIL_CLOSED",
                        "Paid charging admission is temporarily closed.",
                        matched_scope_refs=list(admission.rail_eligibility.matched_scope_refs),
                        version=admission.rail_eligibility.version,
                    )
                raise _business_error(
                    503,
                    "RAIL_STATE_UNKNOWN",
                    "Paid charging admission state is not currently known.",
                    matched_scope_refs=list(admission.rail_eligibility.matched_scope_refs),
                    version=admission.rail_eligibility.version,
                )

            # The QR record is authoritative for tenant, charge point and
            # connector.  A paid direct-card request must claim the matching
            # server-created Order before a device command is sent.
            if pricing.pricing_mode is not PricingMode.FREE:
                if req.settlement_method == "direct_card":
                    if not req.payment_intent_id:
                        raise _business_error(
                            409,
                            "PAYMENT_INTENT_INVALID",
                            "A valid payment method is required before starting this charging session.",
                        )
                    try:
                        pending = find_start_requested_order(
                            sdb,
                            app_user_id=current_user_obj.id,
                            charge_point_id=charge_point.id,
                            operator_tenant_id=charge_point.tenant_id,
                            connector_id=token_rec.connector_id,
                        )
                        if pending is not None:
                            raise PaymentIntentError("Another payment intent is already starting")
                        matched = find_intent_order(
                            sdb,
                            intent_id=req.payment_intent_id,
                            app_user_id=current_user_obj.id,
                            charge_point_id=charge_point.id,
                            operator_tenant_id=charge_point.tenant_id,
                            connector_id=token_rec.connector_id,
                            lock=True,
                        )
                        if matched is None:
                            raise PaymentIntentError("Payment intent does not match this asset")
                        intent_order, intent = matched
                        if intent.is_expired():
                            write_intent(intent_order, intent.with_state("expired"))
                            sdb.commit()
                            raise PaymentIntentError("Payment intent expired")
                        if intent.status != "ready":
                            raise PaymentIntentError("Payment intent has already been used")
                        write_intent(intent_order, intent.with_state("start_requested"))
                        sdb.commit()
                        claimed_intent_id = intent.intent_id
                        claimed_intent_connector = intent.connector_id
                        claimed_intent_user = intent.app_user_id
                    except PaymentIntentError as exc:
                        sdb.rollback()
                        raise _business_error(
                            409,
                            "PAYMENT_INTENT_INVALID",
                            "A valid payment method is required before starting this charging session.",
                        ) from exc
                elif req.payment_intent_id:
                    raise _business_error(
                        409,
                        "PAYMENT_INTENT_INVALID",
                        "A payment intent can only be used with direct-card settlement.",
                    )

            # Existing activity is checked first so a low balance or newly
            # unpaid account can still recover its current session idempotently.
            # direct_card does not use the wallet start gate.
            from app.core.config import get_settings
            min_bal = Decimal(str(get_settings().min_wallet_balance_to_start))
            bal = Decimal(str(app_user.balance or 0)) if app_user else Decimal("0")
            if (
                pricing.pricing_mode != PricingMode.FREE
                and req.settlement_method == "wallet"
                and bal < min_bal
            ):
                error = HTTPException(
                    status_code=402,
                    detail={
                        "code": "INSUFFICIENT_BALANCE",
                        "message": (
                            f"Insufficient wallet balance (need at least {min_bal:.0f} COP). "
                            "Contact the operator to top up your account."
                        ),
                        "balance": str(bal),
                        "min_balance": str(min_bal),
                    },
                )
                log_api_error(
                    method="POST",
                    path="/api/v1/app/charging/start",
                    operation="start_charging",
                    error=error,
                    current_user=current_user_obj,
                    params={"balance": bal, "min_balance": min_bal},
                )
                raise error
        finally:
            sdb.close()

        # OCPP 1.6J 规定 idTag 最大长度为 20 个字符
        # 使用 APP (3字符) + UUID去掉连字符后的前17个字符 = 20字符
        user_uuid_str = str(current_user_obj.id).replace("-", "")
        id_tag = f"APP{user_uuid_str[:17]}"
        
        log_business_operation(
            operation="启动充电",
            entity_type="charge_point",
            entity_id=token_rec.charge_point_id,
            result="initiated",
            current_user=current_user_obj,
            details={"connector_id": token_rec.connector_id, "id_tag": id_tag}
    )

        attempt_key = (
            str(current_user_obj.id),
            str(token_rec.id),
            token_rec.connector_id,
        )
        result = await _coalesced_remote_start(
            attempt_key,
            charge_point_identity,
            id_tag,
            token_rec.connector_id,
        )
        payload = _remote_start_payload(result)
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        device_status = _remote_device_status(payload)
        workflow_status = details.get("workflow_status")

        if not payload.get("success") or device_status != "Accepted":
            if claimed_intent_id:
                _reset_claimed_payment_intent(
                    intent_id=claimed_intent_id,
                    app_user_id=claimed_intent_user,
                    connector_id=claimed_intent_connector,
                )
            code = "START_IN_PROGRESS" if workflow_status == "start_in_progress" else "REMOTE_START_REJECTED"
            message = (
                "A start request is already in progress for this connector."
                if code == "START_IN_PROGRESS"
                else "The charge point rejected the start request."
            )
            raise _business_error(
                409,
                code,
                message,
                ocpp_identity=charge_point_identity,
                connector_id=token_rec.connector_id,
                device_status=device_status or "Rejected",
            )
        
        log_api_response(
            method="POST",
            path="/api/v1/app/charging/start",
            operation="start_charging",
            result="success",
            current_user=current_user_obj,
            details={"charge_point_id": token_rec.charge_point_id, "connector_id": token_rec.connector_id, "status": "accepted"}
        )

        return {
            "success": True,
            "status": "accepted",
            "ocpp_identity": charge_point_identity,
            "charge_point_id": str(charge_point_uuid),
            "connector_id": token_rec.connector_id,
            "device_status": "Accepted",
        }
    except HTTPException:
        if claimed_intent_id:
            _reset_claimed_payment_intent(
                intent_id=claimed_intent_id,
                app_user_id=claimed_intent_user,
                connector_id=claimed_intent_connector,
            )
        raise
    except Exception as e:
        if claimed_intent_id:
            _reset_claimed_payment_intent(
                intent_id=claimed_intent_id,
                app_user_id=claimed_intent_user,
                connector_id=claimed_intent_connector,
            )
        log_api_error(
            method="POST",
            path="/api/v1/app/charging/start",
            operation="start_charging",
            error=e,
            current_user=current_user_obj,
            params={"qr_token": "[REDACTED]"}
        )
        raise


@router.get("/check", summary="检查充电桩状态（扫码后）")
def check_charger_status(
    qr_token: str = Query(..., description="二维码 token"),
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """
    扫码后检查充电桩状态：
    - 解析 qr_token 获取充电桩信息
    - 检查充电桩是否在线（last_seen 5分钟内）
    - 检查是否有活跃充电会话（区分当前用户和其他用户）
    - 返回充电桩状态和可操作提示
    """
    log_api_request(
        method="GET",
        path="/api/v1/app/charging/check",
        operation="check_charger_status",
        current_user=current_user_obj,
        params={"qr_token": "[REDACTED]"}
    )
    
    # 解析 QR token（使用 super session 绕过 RLS）
    sdb = SuperSessionLocal()
    try:
        try:
            token_rec = _resolve_operational_qr(db=sdb, token=qr_token)
            charge_point_id = token_rec.charge_point_id
            connector_id = token_rec.connector_id
            logger.info(f"[APP API] QR resolved: charge_point_id={charge_point_id}, connector_id={connector_id}")
        except HTTPException:
            raise
        except ValueError as e:
            logger.warning("[APP API] QR lookup rejected: %s", type(e).__name__)
            raise HTTPException(status_code=400, detail=f"Invalid QR token: {e}")
        except Exception as e:
            logger.error("[APP API] QR lookup failed: %s", type(e).__name__)
            raise HTTPException(status_code=400, detail=f"Invalid QR token: {e}")
    finally:
        sdb.close()

    # 使用 super session 查询充电桩信息（绕过 RLS）
    db = SuperSessionLocal()
    try:
        # 获取充电桩基本信息
        charger = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id).first()
        if not charger:
            logger.warning("[APP API] Charger not found: %s (resolved from QR)", charge_point_id)
            raise HTTPException(status_code=404, detail=f"Charger not found: {charge_point_id}")
        _require_operational_business_asset(charger)
        _require_commissioned(charger)
        
        logger.info(f"[APP API] Charger found: {charge_point_id}, tenant_id={charger.tenant_id}")

        # 获取站点信息
        site = charger.site if charger.site_id else None

        pricing = PricingService.resolve(db, charger.tenant_id, charger.id)
        if not pricing.is_available:
            raise _business_error(
                409,
                "TARIFF_NOT_CONFIGURED",
                "This charger is not currently available for commercial charging.",
            )

        # 检查充电桩是否在线（通过 last_seen）
        last_seen = db.query(func.max(EVSEStatus.last_seen)).filter(
            EVSEStatus.charge_point_id == charge_point_id
        ).scalar()

        is_online = False
        if last_seen:
            last_seen_utc = (
                last_seen.replace(tzinfo=timezone.utc)
                if last_seen.tzinfo is None
                else last_seen
            )
            time_diff = datetime.now(timezone.utc) - last_seen_utc
            is_online = time_diff.total_seconds() < 300  # 5分钟内更新过才认为在线

        # RemoteStart 依赖实时 WebSocket/MQTT，仅有 DB 心跳不够
        is_connected = check_charger_connection(charger.ocpp_identity)
        is_online = is_online and is_connected

        # D1 is a global billing fact, not a cached user flag or site-local query.
        user_id = str(current_user_obj.id)
        app_user = db.query(AppUser).filter(AppUser.id == current_user_obj.id).first()
        
        if app_user and _has_global_unpaid_charging_bill(db, current_user_obj.id):
            raise _business_error(
                402,
                "UNPAID_CHARGES",
                "Pay outstanding charging bills before starting another session.",
            )

        # 检查是否有活跃充电会话
        active_session = (
            db.query(ChargingSession)
            .filter(
                ChargingSession.charge_point_id == charge_point_id,
                ChargingSession.status == "ongoing",
                ChargingSession.end_time.is_(None),
            )
            .order_by(ChargingSession.start_time.desc())
            .first()
        )

        # 判断状态
        status = "offline"
        session_info = None

        if not is_online:
            status = "offline"
        elif active_session:
            status = "charging"
            is_current_user = active_session.user_id == user_id
            session_info = {
                "session_id": active_session.id,
                "user_id": active_session.user_id,
                "is_current_user": is_current_user,
                "start_time": active_session.start_time.isoformat() if active_session.start_time else None,
            }
        else:
            status = "available"

        # 获取连接器状态
        evse = db.query(EVSE).filter(
            EVSE.charge_point_id == charge_point_id,
            EVSE.evse_id == connector_id
        ).first()

        evse_status = None
        if evse:
            evse_status = db.query(EVSEStatus).filter(
                EVSEStatus.evse_id == evse.id
            ).first()

        connector_status = "Unknown"
        if evse_status:
            connector_status = evse_status.status or "Unknown"

        result = {
            "charger_id": str(charger.id),
            "charge_point_id": str(charger.id),
            "ocpp_identity": charger.ocpp_identity,
            "connector_id": connector_id,
            "status": status,
            "is_online": is_online,
            "last_seen": last_seen.isoformat() if last_seen else None,
            "connector_status": connector_status,
            "active_session": session_info,
            "charger_info": {
                "vendor": charger.vendor,
                "model": charger.model,
                "site_name": site.name if site else None,
                "site_address": site.address if site else None,
                "price_per_kwh": float(pricing.base_price_per_kwh or 0),
                "pricing": pricing.as_dict(),
            },
        }
        
        log_api_response(
            method="GET",
            path="/api/v1/app/charging/check",
            operation="check_charger_status",
            result="success",
            current_user=current_user_obj,
            details={
                "charge_point_id": str(charger.id),
                "ocpp_identity": charger.ocpp_identity,
                "status": status,
                "is_online": is_online,
            }
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="GET",
            path="/api/v1/app/charging/check",
            operation="check_charger_status",
            error=e,
            current_user=current_user_obj,
            params={"qr_token": "[REDACTED]"}
        )
        raise
    finally:
        db.close()


@router.get("/active", summary="获取当前进行中的充电会话（终端用户）")
def get_active_session(
    qr_token: Optional[str] = Query(
        None,
        description="可选二维码 token；不传时恢复当前 AppUser 的唯一 ongoing 会话",
    ),
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """
    返回当前用户的 ongoing 会话（如果存在）。
    - 不传 qr_token：跨租户查找当前认证 AppUser 的唯一 ongoing 会话
    - 传 qr_token：兼容旧客户端，并限定到二维码对应连接器
    注意：ChargingSession 是由协议事件（StartTransaction）创建的，所以 RemoteStart 后可能需要等待几秒才出现。
    """
    log_api_request(
        method="GET",
        path="/api/v1/app/charging/active",
        operation="get_active_session",
        current_user=current_user_obj,
        params={"qr_token": "[REDACTED]"}
    )
    
    # 平台用户跨租户：用 super session 读取（绕过 RLS），并按 session.user_id 过滤
    db = SuperSessionLocal()
    try:
        user_id = str(current_user_obj.id)
        user_id_tag = f"APP{user_id.replace('-', '')[:17]}"
        query = db.query(ChargingSession).filter(
            or_(
                ChargingSession.app_user_id == current_user_obj.id,
                ChargingSession.user_id == user_id,
                ChargingSession.id_tag == user_id_tag,
            ),
            ChargingSession.status == "ongoing",
            ChargingSession.end_time.is_(None),
        )

        token_rec = None
        if qr_token:
            try:
                token_rec = _resolve_operational_qr(db=db, token=qr_token)
            except HTTPException:
                raise
            except Exception as e:
                log_api_error(
                    method="GET",
                    path="/api/v1/app/charging/active",
                    operation="get_active_session",
                    error=e,
                    current_user=current_user_obj,
                    params={"qr_token": "[REDACTED]"},
                )
                raise HTTPException(status_code=400, detail=f"Invalid QR token: {e}")
            evse = db.query(EVSE).filter(
                EVSE.charge_point_id == token_rec.charge_point_id,
                EVSE.evse_id == token_rec.connector_id,
            ).first()
            if not evse:
                raise HTTPException(status_code=404, detail="QR connector not found")
            query = query.filter(
                ChargingSession.charge_point_id == token_rec.charge_point_id,
                ChargingSession.evse_id == evse.id,
            )

        sessions = query.order_by(ChargingSession.start_time.desc()).limit(2).all()
        if not sessions:
            log_api_error(
                method="GET",
                path="/api/v1/app/charging/active",
                operation="get_active_session",
                error=HTTPException(status_code=404, detail="No active session"),
                current_user=current_user_obj,
                params={"charge_point_id": token_rec.charge_point_id if token_rec else None},
            )
            raise HTTPException(status_code=404, detail="No active session")
        if not qr_token and len(sessions) > 1:
            raise _business_error(
                409,
                "MULTIPLE_ACTIVE_SESSIONS",
                "Multiple active sessions found; provide qr_token to select one.",
            )
        session = sessions[0]

        charge_point = db.query(ChargePoint).filter(
            ChargePoint.id == session.charge_point_id,
            ChargePoint.tenant_id == session.tenant_id,
        ).first()
        evse = db.query(EVSE).filter(
            EVSE.id == session.evse_id,
            EVSE.charge_point_id == session.charge_point_id,
        ).first()
        if not charge_point or not evse:
            raise HTTPException(status_code=404, detail="Active session asset not found")

        log_api_response(
            method="GET",
            path="/api/v1/app/charging/active",
            operation="get_active_session",
            result="success",
            current_user=current_user_obj,
            details={"session_id": session.id, "charge_point_id": session.charge_point_id}
        )

        return {
            "id": str(session.id),
            "transaction_id": session.transaction_id,
            "charge_point_id": str(session.charge_point_id),
            "ocpp_identity": charge_point.ocpp_identity,
            "evse_id": str(session.evse_id),
            "connector_id": evse.evse_id,
            "id_tag": session.id_tag,
            "start_time": session.start_time.isoformat() if session.start_time else None,
            "end_time": session.end_time.isoformat() if session.end_time else None,
            "status": session.status,
            "meter_start": session.meter_start,
            "meter_stop": session.meter_stop,
        }
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="GET",
            path="/api/v1/app/charging/active",
            operation="get_active_session",
            error=e,
            current_user=current_user_obj,
            params={"qr_token": "[REDACTED]"}
        )
        raise
    finally:
        db.close()


@router.post("/stop", summary="结束充电（终端用户）")
async def stop_charging(
    req: StopChargingRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """
    结束充电：
    - qr_token/session_id 二选一
    - 从认证 AppUser 查询本人 ongoing session，拿到 transaction_id
    - 再调用 RemoteStopTransaction
    """
    log_api_request(
        method="POST",
        path="/api/v1/app/charging/stop",
        operation="stop_charging",
        current_user=current_user_obj,
        params={
            "qr_token": "[REDACTED]" if req.qr_token else None,
            "session_id": str(req.session_id) if req.session_id else None,
        }
    )

    db = SuperSessionLocal()
    try:
        user_id = str(current_user_obj.id)
        user_id_tag = f"APP{user_id.replace('-', '')[:17]}"
        query = db.query(ChargingSession).filter(
            or_(
                ChargingSession.app_user_id == current_user_obj.id,
                ChargingSession.user_id == user_id,
                ChargingSession.id_tag == user_id_tag,
            ),
            ChargingSession.status == "ongoing",
            ChargingSession.end_time.is_(None),
        )

        if req.session_id:
            query = query.filter(ChargingSession.id == req.session_id)
        else:
            try:
                token_rec = _resolve_operational_qr(db=db, token=req.qr_token)
            except HTTPException:
                raise
            except Exception as e:
                log_api_error(
                    method="POST",
                    path="/api/v1/app/charging/stop",
                    operation="stop_charging",
                    error=e,
                    current_user=current_user_obj,
                    params={"qr_token": "[REDACTED]"},
                )
                raise HTTPException(status_code=400, detail=f"Invalid QR token: {e}")
            evse = db.query(EVSE).filter(
                EVSE.charge_point_id == token_rec.charge_point_id,
                EVSE.evse_id == token_rec.connector_id,
            ).first()
            if not evse:
                raise HTTPException(status_code=404, detail="QR connector not found")
            query = query.filter(
                ChargingSession.charge_point_id == token_rec.charge_point_id,
                ChargingSession.evse_id == evse.id,
            )

        session = query.order_by(ChargingSession.start_time.desc()).first()
        if not session:
            log_api_error(
                method="POST",
                path="/api/v1/app/charging/stop",
                operation="stop_charging",
                error=HTTPException(status_code=404, detail="No active session to stop"),
                current_user=current_user_obj,
                params={"session_id": str(req.session_id) if req.session_id else None}
            )
            raise HTTPException(status_code=404, detail="No active session to stop")

        charge_point_id = session.charge_point_id

        log_business_operation(
            operation="停止充电",
            entity_type="session",
            entity_id=session.id,
            result="initiated",
            current_user=current_user_obj,
            details={"charge_point_id": charge_point_id, "transaction_id": session.transaction_id}
        )

        charge_point = db.query(ChargePoint).filter(
            ChargePoint.id == charge_point_id,
            ChargePoint.tenant_id == session.tenant_id,
        ).first()
        if not charge_point:
            raise HTTPException(status_code=404, detail="Charge point not found")
        result = await send_remote_stop(charge_point.ocpp_identity, session.transaction_id)

        log_api_response(
            method="POST",
            path="/api/v1/app/charging/stop",
            operation="stop_charging",
            result="success",
            current_user=current_user_obj,
            details={"session_id": session.id, "charge_point_id": charge_point_id, "transaction_id": session.transaction_id}
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="POST",
            path="/api/v1/app/charging/stop",
            operation="stop_charging",
            error=e,
            current_user=current_user_obj,
            params={
                "qr_token": "[REDACTED]" if req.qr_token else None,
                "session_id": str(req.session_id) if req.session_id else None,
            }
        )
        raise
    finally:
        db.close()


@router.post("/settle", summary="结算充电费用（钱包、银行卡或免费分支）")
def settle_charging(
    req: SettleChargingRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """
    结算策略：
    - 仅允许结算当前用户自己的 session（通过 id_tag 归属）
    - 仅当 session 已结束（end_time 或 meter_stop 存在）才允许结算
    - 金额由 BillingService 从价格快照计算并由唯一 Invoice 固化
    - 钱包余额不足不扣款、不标记已支付
    - direct_card 只准备准确金额 PaymentOrder，不写钱包
    - free 只生成零金额审计 Payment，不创建 Provider 订单
    """
    try:
        log_api_request(
            method="POST",
            path="/api/v1/app/charging/settle",
            operation="settle_charging",
            current_user=current_user_obj,
            params={"session_id": req.session_id}
        )

        db = SuperSessionLocal()
        try:
            user_id = str(current_user_obj.id)
            session = (
                db.query(ChargingSession)
                .filter(
                    ChargingSession.id == req.session_id,
                    ChargingSession.user_id == user_id,
                )
                .first()
            )
            if not session:
                log_api_error(
                    method="POST",
                    path="/api/v1/app/charging/settle",
                    operation="settle_charging",
                    error=HTTPException(status_code=404, detail="Session not found"),
                    current_user=current_user_obj,
                    params={"session_id": req.session_id}
                )
                raise HTTPException(status_code=404, detail="Session not found")

            if session.end_time is None and session.meter_stop is None:
                raise HTTPException(status_code=400, detail="Session not finished")

            app_user = db.query(AppUser).filter(AppUser.id == current_user_obj.id).first()
            if not app_user:
                raise HTTPException(status_code=404, detail="User not found")

            try:
                result = BillingService.settle_session(db, session, app_user)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            log_business_operation(
                operation="结算充电费用",
                entity_type="session",
                entity_id=session.id,
                result="success",
                current_user=current_user_obj,
                details={
                    "energy_kwh": result.energy_kwh,
                    "cost": result.charged_amount,
                    "new_balance": result.balance,
                    "invoice_id": result.invoice_id,
                },
            )

            log_api_response(
                method="POST",
                path="/api/v1/app/charging/settle",
                operation="settle_charging",
                result="success",
                current_user=current_user_obj,
                details={
                    "session_id": session.id,
                    "cost": result.charged_amount,
                    "balance": result.balance,
                    "invoice_id": result.invoice_id,
                },
            )

            return {
                "already_settled": result.already_settled,
                "balance": result.balance,
                "currency": result.currency,
                "charged_amount": result.charged_amount,
                "energy_kwh": result.energy_kwh,
                "price_per_kwh": result.price_per_kwh,
                "invoice_id": result.invoice_id,
                "settlement_method": result.settlement_method,
                "payment_status": result.payment_status,
                "payment_order_id": result.payment_order_id,
                "next_action": result.next_action,
            }
        except HTTPException:
            raise
        except Exception as e:
            log_api_error(
                method="POST",
                path="/api/v1/app/charging/settle",
                operation="settle_charging",
                error=e,
                current_user=current_user_obj,
                params={"session_id": req.session_id}
            )
            raise
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="POST",
            path="/api/v1/app/charging/settle",
            operation="settle_charging",
            error=e,
            current_user=current_user_obj,
            params={"session_id": req.session_id}
        )
        raise


def _extract_first_numeric(sampled_values: Any, measurand: str) -> Optional[float]:
    """
    从 sampledValue 数组中提取指定 measurand 的数值（取第一个匹配项）。
    sampled_values: List[Dict[str,Any]] | None
    """
    if not sampled_values or not isinstance(sampled_values, list):
        return None
    for sv in sampled_values:
        try:
            if sv.get("measurand") == measurand:
                return float(sv.get("value"))
        except Exception:
            continue
    return None


@router.get("/meter-values", summary="获取充电过程实时数据（MeterValues）")
def get_meter_values(
    session_id: UUID = Query(..., description="charging_sessions.id UUID"),
    since_id: Optional[UUID] = Query(None, description="增量拉取起点 meter_values.id UUID"),
    limit: int = Query(50, ge=1, le=200),
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """
    返回某个 session 的实时 MeterValues（仅限当前用户）。
    输出字段包含：
    - id/timestamp/value_wh
    - energy_kwh（从 value_wh 计算）
    - power_kw/current_a/voltage_v/soc（从 sampled_value 解析）
    - sampled_value 原始数组（方便前端兼容）
    """
    log_api_request(
        method="GET",
        path="/api/v1/app/charging/meter-values",
        operation="get_meter_values",
        current_user=current_user_obj,
        params={"session_id": session_id, "since_id": since_id, "limit": limit}
    )

    db = SuperSessionLocal()
    try:
        user_id = str(current_user_obj.id)
        session = (
            db.query(ChargingSession)
            .filter(
                ChargingSession.id == session_id,
                ChargingSession.user_id == user_id,
            )
            .first()
        )

        if not session:
            log_api_error(
                method="GET",
                path="/api/v1/app/charging/meter-values",
                operation="get_meter_values",
                error=HTTPException(status_code=404, detail="Session not found"),
                current_user=current_user_obj,
                params={"session_id": session_id}
            )
            raise HTTPException(status_code=404, detail="Session not found")

        q = db.query(MeterValue).filter(MeterValue.session_id == session_id)
        if since_id:
            q = q.filter(MeterValue.id > since_id)

        rows = q.order_by(MeterValue.timestamp.asc()).limit(limit).all()

        result = []
        for r in rows:
            sv = r.sampled_value
            power_w = _extract_first_numeric(sv, "Power.Active.Import")
            current_a = _extract_first_numeric(sv, "Current.Import")
            voltage_v = _extract_first_numeric(sv, "Voltage")
            soc = _extract_first_numeric(sv, "SoC")

            energy_kwh = None
            try:
                energy_kwh = float(Decimal(str(r.value)) / Decimal("1000"))
            except Exception:
                energy_kwh = None

            result.append(
                {
                    "id": r.id,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "connector_id": r.connector_id,
                    "value_wh": r.value,
                    "energy_kwh": energy_kwh,
                    "power_kw": (power_w / 1000.0) if isinstance(power_w, (int, float)) else None,
                    "current_a": current_a,
                    "voltage_v": voltage_v,
                    "soc": soc,
                    "sampled_value": sv,
                    "source": "database",
                }
            )

        realtime = meter_telemetry_service.get_latest(
            tenant_id=session.tenant_id,
            session_id=session.id,
        )
        if realtime:
            realtime_timestamp = realtime.get("timestamp")
            realtime_comparison_timestamp = (
                realtime.get("received_at") or realtime_timestamp
            )
            realtime_dt = None
            if isinstance(realtime_comparison_timestamp, str):
                try:
                    realtime_dt = datetime.fromisoformat(
                        realtime_comparison_timestamp.replace("Z", "+00:00")
                    )
                except ValueError:
                    realtime_dt = None

            latest_db_dt = rows[-1].timestamp if rows else None
            if latest_db_dt and latest_db_dt.tzinfo is None:
                latest_db_dt = latest_db_dt.replace(tzinfo=timezone.utc)
            if realtime_dt and realtime_dt.tzinfo is None:
                realtime_dt = realtime_dt.replace(tzinfo=timezone.utc)

            if not latest_db_dt or not realtime_dt or realtime_dt > latest_db_dt:
                sv = realtime.get("sampled_value")
                power_w = _extract_first_numeric(sv, "Power.Active.Import")
                current_a = _extract_first_numeric(sv, "Current.Import")
                voltage_v = _extract_first_numeric(sv, "Voltage")
                soc = _extract_first_numeric(sv, "SoC")
                value_wh = int(realtime.get("value_wh", 0))
                result.append({
                    "id": realtime.get("id") or f"realtime:{realtime_timestamp}",
                    "timestamp": realtime_timestamp,
                    "connector_id": realtime.get("connector_id"),
                    "value_wh": value_wh,
                    "energy_kwh": float(Decimal(value_wh) / Decimal("1000")),
                    "power_kw": (
                        power_w / 1000.0
                        if isinstance(power_w, (int, float))
                        else None
                    ),
                    "current_a": current_a,
                    "voltage_v": voltage_v,
                    "soc": soc,
                    "sampled_value": sv,
                    "source": "realtime",
                })

        log_api_response(
            method="GET",
            path="/api/v1/app/charging/meter-values",
            operation="get_meter_values",
            result="success",
            current_user=current_user_obj,
            details={"session_id": session_id, "count": len(result)}
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        log_api_error(
            method="GET",
            path="/api/v1/app/charging/meter-values",
            operation="get_meter_values",
            error=e,
            current_user=current_user_obj,
            params={"session_id": session_id}
        )
        raise
    finally:
        db.close()
