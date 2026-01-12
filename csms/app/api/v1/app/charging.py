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
from app.database.base import get_db, tenant_id_context
from app.database.models import EndUser, ChargingSession, MeterValue, WalletTransaction, Tariff, ChargePoint

from app.api.v1.ocpp_control import (
    RemoteStartRequest,
    RemoteStopRequest,
    remote_start,
    remote_stop,
)

logger = get_logger("ocpp_csms")

router = APIRouter()


async def get_current_end_user(
    current_user_payload: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EndUser:
    """
    获取当前终端用户对象
    （与 app.chargers.py 保持一致：从 JWT payload 的 user_id 查询 EndUser）
    """
    user_id = current_user_payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    end_user = db.query(EndUser).filter(EndUser.id == user_id).first()
    if not end_user:
        raise HTTPException(status_code=404, detail="User not found")

    return end_user


class StartChargingRequest(BaseModel):
    charge_point_id: str = Field(..., description="充电桩ID（二维码内容解析后得到）")
    connector_id: int = Field(..., description="连接器ID（一个二维码对应一个connector）", ge=1)


class StopChargingRequest(BaseModel):
    charge_point_id: str = Field(..., description="充电桩ID")


class SettleChargingRequest(BaseModel):
    session_id: int = Field(..., description="charging_sessions.id（停止后用该session结算）", ge=1)


@router.post("/start", summary="扫码启动充电（终端用户）")
async def start_charging_by_scan(
    req: StartChargingRequest,
    current_user_obj: EndUser = Depends(get_current_end_user),
):
    """
    通过扫码启动充电：
    - 使用终端用户的 id_tag（若为空则回退到 email）作为 OCPP idTag
    - 实际 RemoteStart 结果只代表“请求已发送/是否被接受”，不一定立即产生 transactionId
    """
    id_tag = (getattr(current_user_obj, "id_tag", None) or current_user_obj.email or str(current_user_obj.id)).strip()
    logger.info(
        f"[APP API] POST /api/v1/app/charging/start | user={current_user_obj.id} "
        f"charge_point_id={req.charge_point_id} connector_id={req.connector_id} id_tag={id_tag}"
    )

    # 复用 ocpp_control 的实现
    return await remote_start(
        RemoteStartRequest(
            chargePointId=req.charge_point_id,
            idTag=id_tag,
            connectorId=req.connector_id,
        )
    )


@router.get("/active", summary="获取当前进行中的充电会话（终端用户）")
def get_active_session(
    charge_point_id: str = Query(..., description="充电桩ID"),
    current_user_obj: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    """
    返回当前用户在某个充电桩上的 ongoing 会话（如果存在）。
    注意：ChargingSession 是由协议事件（StartTransaction）创建的，所以 RemoteStart 后可能需要等待几秒才出现。
    """
    tenant_id = tenant_id_context.get()
    id_tag = (getattr(current_user_obj, "id_tag", None) or current_user_obj.email or str(current_user_obj.id)).strip()

    query = db.query(ChargingSession).filter(
        ChargingSession.charge_point_id == charge_point_id,
        ChargingSession.id_tag == id_tag,
        ChargingSession.status == "ongoing",
        ChargingSession.end_time.is_(None),
    )
    if tenant_id:
        query = query.filter(ChargingSession.tenant_id == tenant_id)

    session = query.order_by(ChargingSession.start_time.desc()).first()
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


@router.post("/stop", summary="结束充电（终端用户）")
async def stop_charging(
    req: StopChargingRequest,
    current_user_obj: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    """
    结束充电：
    - 先在 DB 查询该用户在此桩的 ongoing session，拿到 transaction_id
    - 再调用 RemoteStopTransaction
    """
    tenant_id = tenant_id_context.get()
    id_tag = (getattr(current_user_obj, "id_tag", None) or current_user_obj.email or str(current_user_obj.id)).strip()

    query = db.query(ChargingSession).filter(
        ChargingSession.charge_point_id == req.charge_point_id,
        ChargingSession.id_tag == id_tag,
        ChargingSession.status == "ongoing",
        ChargingSession.end_time.is_(None),
    )
    if tenant_id:
        query = query.filter(ChargingSession.tenant_id == tenant_id)

    session = query.order_by(ChargingSession.start_time.desc()).first()
    if not session:
        raise HTTPException(status_code=404, detail="No active session to stop")

    logger.info(
        f"[APP API] POST /api/v1/app/charging/stop | user={current_user_obj.id} "
        f"charge_point_id={req.charge_point_id} transaction_id={session.transaction_id} id_tag={id_tag}"
    )

    return await remote_stop(
        RemoteStopRequest(
            chargePointId=req.charge_point_id,
            transactionId=session.transaction_id,
        )
    )


@router.post("/settle", summary="结算充电费用并写入钱包流水（终端用户）")
def settle_charging(
    req: SettleChargingRequest,
    current_user_obj: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
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
    tenant_id = tenant_id_context.get() or current_user_obj.tenant_id
    id_tag = (getattr(current_user_obj, "id_tag", None) or current_user_obj.email or str(current_user_obj.id)).strip()

    session = (
        db.query(ChargingSession)
        .filter(ChargingSession.id == req.session_id, ChargingSession.id_tag == id_tag)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if tenant_id:
        if session.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="TENANT_ACCESS_DENIED")

    # 必须已结束
    if session.end_time is None and session.meter_stop is None:
        raise HTTPException(status_code=400, detail="Session not finished")

    tx_id = f"charge_{session.id}"
    existing = db.query(WalletTransaction).filter(WalletTransaction.id == tx_id).first()
    if existing:
        # 已结算：直接返回当前余额
        bal = Decimal(str(current_user_obj.balance or 0))
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

    # 扣余额（不足扣到0）
    bal = Decimal(str(current_user_obj.balance or 0))
    new_bal = bal - cost
    if new_bal < 0:
        new_bal = Decimal("0")
    current_user_obj.balance = new_bal

    # 写入流水（amount 为负表示扣费）
    tx = WalletTransaction(
        id=tx_id,
        tenant_id=tenant_id,
        end_user_id=current_user_obj.id,
        charge_point_id=session.charge_point_id,
        type="charge",
        amount=(Decimal("0") - cost),
        description=f"充电扣费（session {session.id}）",
    )

    db.add(tx)
    db.add(current_user_obj)
    db.commit()
    db.refresh(current_user_obj)

    logger.info(
        f"[APP API] settle session={session.id} user={current_user_obj.id} energy_kwh={energy_kwh} "
        f"price={price_per_kwh} cost={cost} balance={current_user_obj.balance}"
    )

    return {
        "already_settled": False,
        "balance": float(current_user_obj.balance or 0),
        "currency": "USD",
        "charged_amount": float(cost),
        "energy_kwh": float(energy_kwh),
        "price_per_kwh": float(price_per_kwh),
    }


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
    current_user_obj: EndUser = Depends(get_current_end_user),
    db: Session = Depends(get_db),
):
    """
    返回某个 session 的实时 MeterValues（仅限当前用户）。
    输出字段包含：
    - id/timestamp/value_wh
    - energy_kwh（从 value_wh 计算）
    - power_kw/current_a/voltage_v/soc（从 sampled_value 解析）
    - sampled_value 原始数组（方便前端兼容）
    """
    tenant_id = tenant_id_context.get() or current_user_obj.tenant_id
    id_tag = (getattr(current_user_obj, "id_tag", None) or current_user_obj.email or str(current_user_obj.id)).strip()

    session = (
        db.query(ChargingSession)
        .filter(ChargingSession.id == session_id, ChargingSession.id_tag == id_tag)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if tenant_id and session.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="TENANT_ACCESS_DENIED")

    q = db.query(MeterValue).filter(MeterValue.session_id == session_id)
    if tenant_id:
        q = q.filter(MeterValue.tenant_id == tenant_id)
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

