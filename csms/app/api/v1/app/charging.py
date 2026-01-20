#
# APP用户 - 扫码充电API
# 提供给终端用户通过扫码启动/结束充电的接口
#

from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from decimal import Decimal

from app.core.logging_config import get_logger
from app.core.auth import get_current_user
from app.database.base import get_db, tenant_id_context, SuperSessionLocal
from app.database.models import AppUser, ChargingSession, MeterValue, AppWalletTransaction, Tariff, ChargePoint
from app.services.qr_service import resolve_qr_token

from app.api.v1.ocpp_control import (
    RemoteStartRequest,
    RemoteStopRequest,
    remote_start,
    remote_stop,
)

logger = get_logger("ocpp_csms")

router = APIRouter()


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

    app_user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not app_user:
        raise HTTPException(status_code=404, detail="User not found")

    return app_user


class StartChargingRequest(BaseModel):
    qr_token: str = Field(..., description="二维码 token（爆改测试版：token-only）", min_length=10)


class StopChargingRequest(BaseModel):
    qr_token: str = Field(..., description="二维码 token（爆改测试版：token-only）", min_length=10)


class SettleChargingRequest(BaseModel):
    session_id: int = Field(..., description="charging_sessions.id（停止后用该session结算）", ge=1)


@router.post("/start", summary="扫码启动充电（终端用户）")
async def start_charging_by_scan(
    req: StartChargingRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_db),
):
    """
    通过扫码启动充电：
    - 解析 qr_token -> (operator_tenant_id, charge_point_id, connector_id)
    - 使用平台用户 id 作为 OCPP idTag：APPUSER:{uuid}
    - 实际 RemoteStart 结果只代表“请求已发送/是否被接受”，不一定立即产生 transactionId
    """
    try:
        token_rec = resolve_qr_token(db=db, token=req.qr_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid QR token: {e}")

    id_tag = f"APPUSER:{current_user_obj.id}"
    logger.info(
        f"[APP API] POST /api/v1/app/charging/start | user={current_user_obj.id} "
        f"charge_point_id={token_rec.charge_point_id} connector_id={token_rec.connector_id} token={req.qr_token}"
    )

    # 复用 ocpp_control 的实现
    return await remote_start(
        RemoteStartRequest(
            chargePointId=token_rec.charge_point_id,
            idTag=id_tag,
            connectorId=token_rec.connector_id,
        )
    )


@router.get("/active", summary="获取当前进行中的充电会话（终端用户）")
def get_active_session(
    qr_token: str = Query(..., description="二维码 token（爆改测试版：token-only）"),
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """
    返回当前用户在某个充电桩上的 ongoing 会话（如果存在）。
    注意：ChargingSession 是由协议事件（StartTransaction）创建的，所以 RemoteStart 后可能需要等待几秒才出现。
    """
    # token-only：通过 qr_token 解析得到 charge_point_id
    sdb = SuperSessionLocal()
    try:
        token_rec = resolve_qr_token(db=sdb, token=qr_token)
        charge_point_id = token_rec.charge_point_id
    finally:
        sdb.close()

    # 平台用户跨租户：用 super session 读取（绕过 RLS），并按 session.user_id 过滤
    db = SuperSessionLocal()
    try:
        user_id = str(current_user_obj.id)
        session = (
            db.query(ChargingSession)
            .filter(
                ChargingSession.charge_point_id == charge_point_id,
                ChargingSession.user_id == user_id,
                ChargingSession.status == "ongoing",
                ChargingSession.end_time.is_(None),
            )
            .order_by(ChargingSession.start_time.desc())
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="No active session")

        return {
            "id": session.id,
            "transaction_id": session.transaction_id,
            "charge_point_id": session.charge_point_id,
            "evse_id": session.evse_id,
            "id_tag": session.id_tag,
            "start_time": session.start_time.isoformat() if session.start_time else None,
            "end_time": session.end_time.isoformat() if session.end_time else None,
            "status": session.status,
            "meter_start": session.meter_start,
            "meter_stop": session.meter_stop,
        }
    finally:
        db.close()


@router.post("/stop", summary="结束充电（终端用户）")
async def stop_charging(
    req: StopChargingRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """
    结束充电：
    - 先在 DB 查询该用户在此桩的 ongoing session，拿到 transaction_id
    - 再调用 RemoteStopTransaction
    """
    sdb = SuperSessionLocal()
    try:
        token_rec = resolve_qr_token(db=sdb, token=req.qr_token)
        charge_point_id = token_rec.charge_point_id

        db = SuperSessionLocal()
        try:
            user_id = str(current_user_obj.id)
            session = (
                db.query(ChargingSession)
                .filter(
                    ChargingSession.charge_point_id == charge_point_id,
                    ChargingSession.user_id == user_id,
                    ChargingSession.status == "ongoing",
                    ChargingSession.end_time.is_(None),
                )
                .order_by(ChargingSession.start_time.desc())
                .first()
            )
            if not session:
                raise HTTPException(status_code=404, detail="No active session to stop")

            logger.info(
                f"[APP API] POST /api/v1/app/charging/stop | user={current_user_obj.id} "
                f"charge_point_id={charge_point_id} transaction_id={session.transaction_id}"
            )

            return await remote_stop(
                RemoteStopRequest(
                    chargePointId=charge_point_id,
                    transactionId=session.transaction_id,
                )
            )
        finally:
            db.close()
    finally:
        sdb.close()


@router.post("/settle", summary="结算充电费用并写入钱包流水（终端用户）")
def settle_charging(
    req: SettleChargingRequest,
    current_user_obj: AppUser = Depends(get_current_app_user),
):
    """
    结算策略（简化版）：
    - 仅允许结算当前用户自己的 session（通过 id_tag 归属）
    - 仅当 session 已结束（end_time 或 meter_stop 存在）才允许结算
    - 根据 Tariff（优先桩级，其次站点级）读取 price_per_kwh
    - 费用 = energy_kwh * price_per_kwh（无电量则为0）
    - 钱包：EndUser.balance -= 费用（不足则扣到 0，避免出现负余额）
    - 流水幂等：WalletTransaction.id 固定为 charge_{session_id}，重复调用不会重复扣费
    """
    # 平台用户跨租户：用 super session（绕过 RLS），并按 session.user_id 绑定
    db = SuperSessionLocal()
    try:
        user_id = str(current_user_obj.id)
        session = (
            db.query(ChargingSession)
            .filter(ChargingSession.id == req.session_id, ChargingSession.user_id == user_id)
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        tenant_id = session.tenant_id

        # 必须已结束
        if session.end_time is None and session.meter_stop is None:
            raise HTTPException(status_code=400, detail="Session not finished")

        tx_id = f"charge_{session.id}"
        existing = db.query(AppWalletTransaction).filter(AppWalletTransaction.id == tx_id).first()
        if existing:
            # 已结算：直接返回平台余额
            app_user = db.query(AppUser).filter(AppUser.id == current_user_obj.id).first()
            bal = Decimal(str((app_user.balance if app_user else 0) or 0))
            return {
                "already_settled": True,
                "balance": float(bal),
                "currency": "USD",
                "charged_amount": float(abs(existing.amount)),
            }

        # 计算电量
        energy_kwh = Decimal("0")
        if session.meter_stop is not None and session.meter_start is not None:
            try:
                wh = Decimal(str(session.meter_stop - session.meter_start))
                if wh > 0:
                    energy_kwh = wh / Decimal("1000")
            except Exception:
                energy_kwh = Decimal("0")

        now = datetime.now(timezone.utc)
        # 读取定价：优先 charge_point_id，其次 site_id
        tariff = (
            db.query(Tariff)
            .filter(
                Tariff.is_active == True,  # noqa: E712
                Tariff.tenant_id == tenant_id,
                Tariff.charge_point_id == session.charge_point_id,
                Tariff.valid_from <= now,
            )
            .filter((Tariff.valid_until.is_(None)) | (Tariff.valid_until >= now))
            .order_by(Tariff.valid_from.desc())
            .first()
        )

        if not tariff:
            cp = db.query(ChargePoint).filter(ChargePoint.id == session.charge_point_id).first()
            if cp and cp.site_id:
                tariff = (
                    db.query(Tariff)
                    .filter(
                        Tariff.is_active == True,  # noqa: E712
                        Tariff.tenant_id == tenant_id,
                        Tariff.site_id == cp.site_id,
                        Tariff.valid_from <= now,
                    )
                    .filter((Tariff.valid_until.is_(None)) | (Tariff.valid_until >= now))
                    .order_by(Tariff.valid_from.desc())
                    .first()
                )

        price_per_kwh = Decimal("0")
        if tariff and tariff.base_price_per_kwh is not None:
            price_per_kwh = Decimal(str(tariff.base_price_per_kwh))

        cost = (energy_kwh * price_per_kwh).quantize(Decimal("0.01"))

        # 扣余额（平台钱包，不足扣到0）
        app_user = db.query(AppUser).filter(AppUser.id == current_user_obj.id).first()
        if not app_user:
            raise HTTPException(status_code=404, detail="User not found")

        bal = Decimal(str(app_user.balance or 0))
        new_bal = bal - cost
        if new_bal < 0:
            new_bal = Decimal("0")
        app_user.balance = new_bal

        # 写入流水（amount 为负表示扣费）
        tx = AppWalletTransaction(
            id=tx_id,
            app_user_id=current_user_obj.id,
            operator_tenant_id=tenant_id,
            charge_point_id=session.charge_point_id,
            type="charge",
            amount=(Decimal("0") - cost),
            description=f"充电扣费（session {session.id}）",
        )

        db.add(tx)
        db.add(app_user)
        db.commit()
        db.refresh(app_user)

        logger.info(
            f"[APP API] settle session={session.id} user={current_user_obj.id} energy_kwh={energy_kwh} "
            f"price={price_per_kwh} cost={cost} balance={app_user.balance}"
        )

        return {
            "already_settled": False,
            "balance": float(app_user.balance or 0),
            "currency": "USD",
            "charged_amount": float(cost),
            "energy_kwh": float(energy_kwh),
            "price_per_kwh": float(price_per_kwh),
        }
    finally:
        db.close()


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
    session_id: int = Query(..., ge=1, description="charging_sessions.id"),
    since_id: Optional[int] = Query(None, ge=1, description="增量拉取：只返回 id > since_id 的数据"),
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
    # 平台用户跨租户：用 super session（绕过 RLS），并按 session.user_id 绑定
    db = SuperSessionLocal()
    try:
        user_id = str(current_user_obj.id)
        session = (
            db.query(ChargingSession)
            .filter(ChargingSession.id == session_id, ChargingSession.user_id == user_id)
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        q = db.query(MeterValue).filter(MeterValue.session_id == session_id)
        if since_id:
            q = q.filter(MeterValue.id > since_id)

    # 按时间顺序返回（前端画曲线/列表更直观）
        rows = q.order_by(MeterValue.timestamp.asc()).limit(limit).all()

        result = []
        for r in rows:
            sv = r.sampled_value
        # OCPP 常见 measurand：
        # - Power.Active.Import (W)
        # - Current.Import (A)
        # - Voltage (V)
        # - SoC (%)
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
                }
            )
        return result
    finally:
        db.close()

