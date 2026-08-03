#
# 充电桩管理API
# 提供充电桩的CRUD操作（使用新表结构）
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.database.base import get_db, tenant_id_context
from app.database.models import (
    Alert,
    AppWalletTransaction,
    AuditLog,
    ChargePoint,
    ChargePointConfig,
    ChargingSession,
    DeviceEvent,
    EVSE,
    EVSEStatus,
    Invoice,
    MeterValue,
    OCPPMessageEvent,
    Order,
    OutboxEvent,
    Payment,
    QrToken,
    Site,
    Tariff,
)
from app.core.logging_config import get_logger
from app.core.permissions import get_current_admin_user, require_permission
from app.core.asset_identifiers import (
    get_charge_point_by_reference,
    get_site_by_reference,
    get_tenant_charge_point_by_reference,
)
from app.api.validation import StrictRequestModel
from app.core.permissions import has_permission
from app.services.role_service import MembershipRoleService
from app.services.asset_lifecycle_service import (
    CHARGER_DELETE_ACTION,
    CHARGER_RESTORE_ACTION,
    CHARGER_RETIRE_ACTION,
    AssetNotOperationalError,
    LifecycleReasonError,
    add_lifecycle_audit,
    apply_charge_point_restored_state,
    apply_charge_point_retired_state,
    charge_point_lifecycle_status,
    latest_lifecycle_audit,
    normalize_lifecycle_reason,
    require_charge_point_operational,
)
from app.core.ocpp_auth import generate_ocpp_secret, hash_ocpp_secret
from datetime import datetime, timezone
from decimal import Decimal

logger = get_logger("ocpp_csms")

router = APIRouter()


class CreateChargerRequest(StrictRequestModel):
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    vendor: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    site_id: Optional[str] = None


class ChargerPricingUpdateRequest(BaseModel):
    """充电桩级覆盖价（优先于站点默认价）"""

    base_price_per_kwh: Decimal
    service_fee: Optional[Decimal] = None


class ChargerPricingResponse(BaseModel):
    charge_point_id: str
    tariff_id: str
    base_price_per_kwh: Decimal
    service_fee: Decimal
    valid_from: str


class ChargerLifecycleRequest(StrictRequestModel):
    reason: str = Field(..., min_length=3, max_length=500)


class PermanentDeleteChargerRequest(ChargerLifecycleRequest):
    confirmation: str = Field(..., min_length=1, max_length=64)


def _coded_http_exception(status_code: int, code: str, message: str, **details) -> HTTPException:
    exc = HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, **details},
    )
    exc.error_code = code
    return exc


def _normalized_reason(reason: str) -> str:
    try:
        return normalize_lifecycle_reason(reason)
    except LifecycleReasonError as exc:
        raise _coded_http_exception(422, "invalid_lifecycle_reason", str(exc)) from exc


def _require_operational_charger(charge_point: ChargePoint) -> None:
    try:
        require_charge_point_operational(charge_point)
    except AssetNotOperationalError as exc:
        raise _coded_http_exception(
            409,
            exc.code,
            exc.message,
            blockers=[],
        ) from exc


def _retirement_preflight(db: Session, charge_point: ChargePoint) -> dict:
    ongoing_sessions = (
        db.query(ChargingSession.id)
        .filter(
            ChargingSession.tenant_id == charge_point.tenant_id,
            ChargingSession.charge_point_id == charge_point.id,
            ChargingSession.status == "ongoing",
        )
        .all()
    )
    pending_commands = (
        db.query(OutboxEvent.id)
        .filter(
            OutboxEvent.tenant_id == charge_point.tenant_id,
            OutboxEvent.aggregate_type == "ChargePoint",
            OutboxEvent.aggregate_id == str(charge_point.id),
            OutboxEvent.status == "pending",
        )
        .all()
    )

    unsettled_records = []
    unsettled_sessions = (
        db.query(ChargingSession.id)
        .filter(
            ChargingSession.tenant_id == charge_point.tenant_id,
            ChargingSession.charge_point_id == charge_point.id,
            ChargingSession.status != "ongoing",
            ChargingSession.payment_status.in_(("pending", "unpaid")),
        )
        .all()
    )
    unsettled_records.extend(("charging_session", row.id) for row in unsettled_sessions)

    unsettled_orders = (
        db.query(Order.id)
        .filter(
            Order.tenant_id == charge_point.tenant_id,
            Order.charge_point_id == charge_point.id,
            Order.status.in_(("pending", "authorized", "ongoing")),
        )
        .all()
    )
    unsettled_records.extend(("order", row.id) for row in unsettled_orders)

    unsettled_invoices = (
        db.query(Invoice.id)
        .join(ChargingSession, Invoice.session_id == ChargingSession.id)
        .filter(
            Invoice.tenant_id == charge_point.tenant_id,
            ChargingSession.charge_point_id == charge_point.id,
            Invoice.status == "pending",
        )
        .all()
    )
    unsettled_records.extend(("invoice", row.id) for row in unsettled_invoices)

    unsettled_payments = (
        db.query(Payment.id)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .join(ChargingSession, Invoice.session_id == ChargingSession.id)
        .filter(
            Payment.tenant_id == charge_point.tenant_id,
            ChargingSession.charge_point_id == charge_point.id,
            Payment.status == "pending",
        )
        .all()
    )
    unsettled_records.extend(("payment", row.id) for row in unsettled_payments)

    blockers = [
        {"type": "ongoing_session", "resource_id": str(row.id)}
        for row in ongoing_sessions
    ]
    blockers.extend(
        {"type": "pending_remote_command", "resource_id": str(row.id)}
        for row in pending_commands
    )
    blockers.extend(
        {
            "type": "unsettled_business",
            "resource_type": resource_type,
            "resource_id": str(resource_id),
        }
        for resource_type, resource_id in unsettled_records
    )
    return {
        "charge_point_id": str(charge_point.id),
        "lifecycle_status": charge_point_lifecycle_status(charge_point),
        "can_retire_now": not blockers,
        "will_wait_for_sessions": False,
        "counts": {
            "ongoing_sessions": len(ongoing_sessions),
            "pending_remote_commands": len(pending_commands),
            "unsettled_business_records": len(unsettled_records),
        },
        "blockers": blockers,
    }


def _charger_lifecycle_response(db: Session, charge_point: ChargePoint) -> dict:
    retirement_audit = latest_lifecycle_audit(
        db,
        tenant_id=charge_point.tenant_id,
        resource_type="charge_point",
        resource_id=str(charge_point.id),
        actions=(CHARGER_RETIRE_ACTION,),
    )
    retired_at = retirement_audit.created_at.isoformat() if retirement_audit else None
    return {
        "charge_point_id": str(charge_point.id),
        "lifecycle_status": charge_point_lifecycle_status(charge_point),
        "retirement_requested_at": retired_at,
        "retired_at": retired_at,
    }


def _permanent_delete_blockers(db: Session, charge_point: ChargePoint) -> list[dict]:
    blockers: list[dict] = []

    def add_count(blocker_type: str, count: int) -> None:
        if count:
            blockers.append({"type": blocker_type, "count": count})

    if charge_point.is_active is not True or charge_point.commissioning_status != "draft":
        blockers.append({"type": "commissioning_history", "count": 1})
    elif any(
        (
            charge_point.commissioned_at,
            charge_point.last_acceptance_at,
            charge_point.acceptance_report,
        )
    ):
        blockers.append({"type": "commissioning_history", "count": 1})

    if charge_point.device_id or charge_point.device_serial_number:
        blockers.append({"type": "device_association", "count": 1})

    scoped_counts = (
        ("evse", EVSE, EVSE.charge_point_id == charge_point.id),
        ("evse_status", EVSEStatus, EVSEStatus.charge_point_id == charge_point.id),
        ("charging_session", ChargingSession, ChargingSession.charge_point_id == charge_point.id),
        ("order", Order, Order.charge_point_id == charge_point.id),
        ("tariff", Tariff, Tariff.charge_point_id == charge_point.id),
        ("qr_token", QrToken, QrToken.charge_point_id == charge_point.id),
        ("ocpp_message", OCPPMessageEvent, OCPPMessageEvent.charge_point_id == charge_point.id),
        ("device_event", DeviceEvent, DeviceEvent.charge_point_id == charge_point.id),
        ("alert", Alert, Alert.charge_point_id == charge_point.id),
        ("configuration", ChargePointConfig, ChargePointConfig.charge_point_id == charge_point.id),
        ("wallet_transaction", AppWalletTransaction, AppWalletTransaction.charge_point_id == charge_point.id),
    )
    for blocker_type, model, predicate in scoped_counts:
        add_count(blocker_type, db.query(model).filter(predicate).count())

    add_count(
        "remote_command",
        db.query(OutboxEvent)
        .filter(
            OutboxEvent.tenant_id == charge_point.tenant_id,
            OutboxEvent.aggregate_type == "ChargePoint",
            OutboxEvent.aggregate_id == str(charge_point.id),
        )
        .count(),
    )
    add_count(
        "audit_log",
        db.query(AuditLog)
        .filter(
            AuditLog.tenant_id == charge_point.tenant_id,
            AuditLog.resource_type == "charge_point",
            AuditLog.resource_id == str(charge_point.id),
        )
        .count(),
    )
    return blockers


def _get_scoped_charge_point(db: Session, reference: str, current_user_obj) -> ChargePoint:
    charge_point = get_charge_point_by_reference(db, reference)
    if not charge_point:
        raise HTTPException(status_code=404, detail=f"充电桩 {reference} 未找到")
    tenant_id = tenant_id_context.get()
    if tenant_id and charge_point.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Charge point belongs to another tenant")
    if not tenant_id and not current_user_obj.is_super_admin:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    return charge_point


def _get_visible_charge_point(db: Session, reference: str, current_user_obj) -> ChargePoint:
    """Resolve a read target without disclosing cross-tenant asset existence."""
    tenant_id = tenant_id_context.get()
    if tenant_id:
        charge_point = get_tenant_charge_point_by_reference(db, reference, tenant_id)
    elif current_user_obj.is_super_admin:
        charge_point = get_charge_point_by_reference(db, reference)
    else:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    if not charge_point:
        raise HTTPException(status_code=404, detail=f"充电桩 {reference} 未找到")
    return charge_point


@router.get("", summary="获取所有充电桩")
def list_chargers(
    filter_type: Optional[str] = Query(None, description="筛选类型: configured(已配置), unconfigured(未配置)"),
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> List[dict]:
    """
    获取充电桩列表（使用新表结构）
    
    支持筛选：
    - configured: 只返回已配置的充电桩（有位置和价格）
    - unconfigured: 只返回未配置的充电桩（缺少位置或价格）
    """
    logger.info(f"[API] GET /api/v1/chargers | 筛选类型: {filter_type or '全部'}")
    
    # 获取租户ID（RLS会自动过滤，但为了性能也在应用层过滤）
    tenant_id = tenant_id_context.get()
    
    query = db.query(ChargePoint).filter(
        ChargePoint.is_active.is_(True),
        ChargePoint.site.has(Site.is_active.is_(True)),
    )
    
    # 只要选择了租户，超级管理员也必须使用同一租户范围。
    if tenant_id:
        query = query.filter(ChargePoint.tenant_id == tenant_id)
    
    # 根据筛选类型过滤
    if filter_type == "configured":
        # 已配置：有位置和价格（通过站点和定价规则判断）
        query = query.join(Site).join(Tariff).filter(
            Site.latitude.isnot(None),
            Site.longitude.isnot(None),
            Tariff.is_active == True,
            Tariff.base_price_per_kwh > 0
        )
    elif filter_type == "unconfigured":
        # 未配置：缺少位置或价格
        query = query.outerjoin(Site).outerjoin(Tariff).filter(
            or_(
                Site.latitude.is_(None),
                Site.longitude.is_(None),
                Tariff.is_active == False,
                Tariff.base_price_per_kwh == 0
            )
        )
    
    charge_points = query.all()
    logger.info(f"[API] 查询到 {len(charge_points)} 个充电桩 | 筛选类型: {filter_type or '全部'}")
    
    result = []
    for cp in charge_points:
        # 获取站点信息
        site = cp.site if cp.site_id else None
        has_location = site and site.latitude is not None and site.longitude is not None
        
        # 获取定价信息（优先桩级，其次站点级；按 tenant_id + 有效期过滤）
        now = datetime.now(timezone.utc)
        tariff = (
            db.query(Tariff)
            .filter(
                Tariff.tenant_id == cp.tenant_id,
                Tariff.charge_point_id == cp.id,
                Tariff.is_active == True,  # noqa: E712
                Tariff.valid_from <= now,
            )
            .filter((Tariff.valid_until.is_(None)) | (Tariff.valid_until >= now))
            .order_by(Tariff.valid_from.desc())
            .first()
        )
        if not tariff and cp.site_id:
            tariff = (
                db.query(Tariff)
                .filter(
                    Tariff.tenant_id == cp.tenant_id,
                    Tariff.site_id == cp.site_id,
                    Tariff.charge_point_id.is_(None),
                    Tariff.is_active == True,  # noqa: E712
                    Tariff.valid_from <= now,
                )
                .filter((Tariff.valid_until.is_(None)) | (Tariff.valid_until >= now))
                .order_by(Tariff.valid_from.desc())
                .first()
            )
        has_pricing = tariff is not None and float(tariff.base_price_per_kwh or 0) > 0
        
        # 获取EVSE状态
        evse_status = db.query(EVSEStatus).filter(
            EVSEStatus.charge_point_id == cp.id
        ).first()
        last_seen = evse_status.last_seen if evse_status else None
        
        # 根据 last_seen 判断是否真正在线（超过5分钟未更新则认为离线）
        is_online = False
        if last_seen:
            time_diff = datetime.now(timezone.utc) - last_seen
            is_online = time_diff.total_seconds() < 300  # 5分钟内更新过才认为在线
        
        # 如果充电桩离线，即使status是Available也标记为Offline
        if not is_online:
            status = "Offline"
        else:
            status = evse_status.status if evse_status else "Unknown"
        
        is_configured = has_location and has_pricing
        
        result.append({
            "id": str(cp.id),
            "ocpp_identity": cp.ocpp_identity,
            "vendor": cp.vendor,
            "model": cp.model,
            "status": status,
            "last_seen": last_seen.isoformat() if last_seen else None,
            "location": {
                "latitude": site.latitude if site else None,
                "longitude": site.longitude if site else None,
                "address": site.address if site else None,
            },
            "price_per_kwh": float(tariff.base_price_per_kwh) if tariff else None,
            "is_configured": is_configured,
            "has_location": has_location,
            "has_pricing": has_pricing,
        })
    
    logger.info(f"[API] GET /api/v1/chargers 成功返回 {len(result)} 个充电桩")
    return result


@router.get("/{charge_point_id}", summary="获取充电桩详情")
def get_charger(
    charge_point_id: str,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> dict:
    """获取单个充电桩的详细信息（使用新表结构）"""
    logger.info(f"[API] GET /api/v1/chargers/{charge_point_id} | 请求充电桩详情")
    
    charge_point = _get_visible_charge_point(db, charge_point_id, current_user_obj)
    
    # 获取站点信息
    site = charge_point.site if charge_point.site_id else None
    
    # 获取定价信息（优先桩级，其次站点级；按 tenant_id + 有效期过滤）
    now = datetime.now(timezone.utc)
    tariff = (
        db.query(Tariff)
        .filter(
            Tariff.tenant_id == charge_point.tenant_id,
            Tariff.charge_point_id == charge_point.id,
            Tariff.is_active == True,  # noqa: E712
            Tariff.valid_from <= now,
        )
        .filter((Tariff.valid_until.is_(None)) | (Tariff.valid_until >= now))
        .order_by(Tariff.valid_from.desc())
        .first()
    )
    if not tariff and charge_point.site_id:
        tariff = (
            db.query(Tariff)
            .filter(
                Tariff.tenant_id == charge_point.tenant_id,
                Tariff.site_id == charge_point.site_id,
                Tariff.charge_point_id.is_(None),
                Tariff.is_active == True,  # noqa: E712
                Tariff.valid_from <= now,
            )
            .filter((Tariff.valid_until.is_(None)) | (Tariff.valid_until >= now))
            .order_by(Tariff.valid_from.desc())
            .first()
        )
    
    # 获取EVSE状态
    evse_status = db.query(EVSEStatus).filter(
        EVSEStatus.charge_point_id == charge_point.id
    ).first()
    last_seen = evse_status.last_seen if evse_status else None
    
    # 根据 last_seen 判断是否真正在线（超过5分钟未更新则认为离线）
    is_online_detail = False
    if last_seen:
        time_diff = datetime.now(timezone.utc) - last_seen
        is_online_detail = time_diff.total_seconds() < 300  # 5分钟内更新过才认为在线
    
    # 如果充电桩离线，即使status是Available也标记为Offline
    if not is_online_detail:
        status = "Offline"
    else:
        status = evse_status.status if evse_status else "Unknown"
    
    # 获取EVSE列表（包含 connector_type）
    evses = db.query(EVSE).filter(EVSE.charge_point_id == charge_point.id).all()
    evse_list = []
    default_connector_type = "Type2"  # 默认值
    for evse in evses:
        evse_status_item = db.query(EVSEStatus).filter(EVSEStatus.evse_id == evse.id).first()
        evse_list.append({
            "evse_id": evse.evse_id,
            "physical_reference": evse.physical_reference,
            "connector_type": evse.connector_type,  # 从 EVSE 获取 connector_type
            "max_power_kw": evse.max_power_kw,
            "status": evse_status_item.status if evse_status_item else "Unknown",
            "last_seen": evse_status_item.last_seen.isoformat() if evse_status_item and evse_status_item.last_seen else None,
        })
        # 使用第一个 EVSE 的 connector_type 作为默认值（向后兼容）
        if evse.evse_id == 1:
            default_connector_type = evse.connector_type

    retirement_audit = latest_lifecycle_audit(
        db,
        tenant_id=charge_point.tenant_id,
        resource_type="charge_point",
        resource_id=str(charge_point.id),
        actions=(CHARGER_RETIRE_ACTION,),
    )
    retirement_time = retirement_audit.created_at.isoformat() if retirement_audit else None
    retirement_reason = None
    if retirement_audit:
        retirement_reason = (retirement_audit.audit_metadata or {}).get("reason")
    
    return {
        "id": str(charge_point.id),
        "ocpp_identity": charge_point.ocpp_identity,
        "vendor": charge_point.vendor,
        "model": charge_point.model,
        "serial_number": charge_point.serial_number,
        "firmware_version": charge_point.firmware_version,
        "connector_type": default_connector_type,  # 从默认 EVSE (evse_id=1) 获取，用于向后兼容
        "status": status,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "location": {
            "latitude": site.latitude if site else None,
            "longitude": site.longitude if site else None,
            "address": site.address if site else None,
        },
        "price_per_kwh": float(tariff.base_price_per_kwh) if tariff else None,
        "evses": evse_list,  # 每个 EVSE 都有自己的 connector_type
        "lifecycle_status": charge_point_lifecycle_status(charge_point),
        "retirement_reason": retirement_reason,
        "retirement_requested_at": retirement_time,
        "retired_at": retirement_time,
        "original_site": {
            "id": str(site.id),
            "site_code": site.site_code,
            "name": site.name,
        } if site else None,
        "commissioning_status": charge_point.commissioning_status,
        "acceptance_report": charge_point.acceptance_report,
        "last_acceptance_at": charge_point.last_acceptance_at.isoformat() if charge_point.last_acceptance_at else None,
        "commissioned_at": charge_point.commissioned_at.isoformat() if charge_point.commissioned_at else None,
        "created_at": charge_point.created_at.isoformat() if charge_point.created_at else None,
        "updated_at": charge_point.updated_at.isoformat() if charge_point.updated_at else None,
    }
    
    logger.info(f"[API] GET /api/v1/chargers/{charge_point_id} 成功 | 状态: {status}")


@router.post("", summary="创建充电桩", status_code=201)
def create_charger(
    req: CreateChargerRequest,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> dict:
    """创建新的充电桩"""
    logger.info(f"[API] POST /api/v1/chargers | 充电桩ID: {req.id}")
    
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    
    # 检查是否已存在（按租户）
    existing = db.query(ChargePoint).filter(ChargePoint.ocpp_identity == req.id).first()
    if existing:
        logger.warning(f"[API] POST /api/v1/chargers | 充电桩 {req.id} 已存在")
        raise HTTPException(status_code=409, detail=f"充电桩 {req.id} 已存在")

    site = get_site_by_reference(db, req.site_id) if req.site_id else None
    if not site:
        raise HTTPException(status_code=422, detail="site_id must reference an existing site")
    if site.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Site belongs to another tenant")
    if site.is_active is not True:
        raise _coded_http_exception(
            409,
            "site_not_operational",
            "Cannot provision a charge point under an archived site",
        )
    
    # 创建新充电桩
    from app.core.ocpp_auth import generate_ocpp_secret, hash_ocpp_secret
    ocpp_secret = generate_ocpp_secret()
    charge_point = ChargePoint(
        ocpp_identity=req.id,
        tenant_id=tenant_id,
        vendor=req.vendor,
        model=req.model,
        site_id=site.id,
        ocpp_auth_secret_hash=hash_ocpp_secret(ocpp_secret),
        commissioning_status="draft",
        is_active=True
    )
    db.add(charge_point)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"充电桩 {req.id} 已存在") from exc
    db.refresh(charge_point)
    
    # 为已存在的EVSE生成二维码（爆改：token-only）
    qr_urls = []
    try:
        from app.services.qr_service import generate_qr_code, get_qr_code_url, get_qr_storage_dir, ensure_qr_token
        qr_storage_dir = get_qr_storage_dir()
        
        # 查询该充电桩的所有EVSE
        evses = db.query(EVSE).filter(EVSE.charge_point_id == charge_point.id).all()
        for evse in evses:
            try:
                generate_qr_code(
                    db=db,
                    charge_point_id=charge_point.id,
                    connector_id=evse.evse_id,
                    output_dir=qr_storage_dir,
                )
                token_rec = ensure_qr_token(db, charge_point.id, evse.evse_id)
                qr_url = get_qr_code_url(str(charge_point.id), evse.evse_id)
                qr_urls.append({
                    "connector_id": evse.evse_id,
                    "qr_token": token_rec.token,
                    "qr_url": qr_url,
                    "filename": f"{req.id}_connector_{evse.evse_id}.png"
                })
            except Exception as e:
                logger.warning(f"生成充电桩 {req.id} connector {evse.evse_id} 的二维码失败: {e}")
    except Exception as e:
        logger.error(f"生成二维码时出错: {e}", exc_info=True)
        # 二维码生成失败不影响充电桩创建
    
    logger.info(f"[API] POST /api/v1/chargers 成功 | 充电桩ID: {req.id}")
    return {
        "id": str(charge_point.id),
        "ocpp_identity": charge_point.ocpp_identity,
        "vendor": charge_point.vendor,
        "model": charge_point.model,
        "site_id": str(charge_point.site_id),
        "is_active": charge_point.is_active,
        "commissioning_status": charge_point.commissioning_status,
        "ocpp_credentials": {
            "username": charge_point.ocpp_identity,
            "secret": ocpp_secret,
            "query_url": f"/ocpp?id={charge_point.ocpp_identity}",
            "path_url": f"/ocpp/{charge_point.ocpp_identity}",
        },
        "qr_codes": qr_urls,  # 二维码URL列表（如果有EVSE）
    }


def _build_acceptance_report(db: Session, charge_point: ChargePoint) -> dict:
    """Build an evidence-based report; missing evidence always fails closed."""
    actions = {
        action: db.query(func.count(OCPPMessageEvent.id)).filter(
            OCPPMessageEvent.charge_point_id == charge_point.id,
            OCPPMessageEvent.action == action,
            OCPPMessageEvent.processing_status == "completed",
        ).scalar() or 0
        for action in (
            "BootNotification",
            "StartTransaction",
            "StopTransaction",
        )
    }
    heartbeat_seen = db.query(EVSEStatus.id).filter(
        EVSEStatus.charge_point_id == charge_point.id,
        EVSEStatus.last_seen.is_not(None),
    ).first() is not None
    meter_values_seen = db.query(MeterValue.id).join(
        ChargingSession,
        ChargingSession.id == MeterValue.session_id,
    ).filter(
        ChargingSession.charge_point_id == charge_point.id,
    ).first() is not None
    try:
        from app.api.v1.charger_management import check_charger_connection
        connected = check_charger_connection(charge_point.ocpp_identity)
    except Exception:
        connected = False
    evses = db.query(EVSE).filter(EVSE.charge_point_id == charge_point.id).order_by(EVSE.evse_id).all()
    checks = {
        "device_credential": bool(charge_point.ocpp_auth_secret_hash),
        "evse_configuration": bool(evses) and all(
            item.connector_type and item.max_power_kw and item.physical_reference for item in evses
        ),
        "boot_notification": actions["BootNotification"] >= 1,
        "heartbeat": heartbeat_seen,
        "remote_start_transaction": actions["StartTransaction"] >= 1,
        "meter_values": meter_values_seen,
        "remote_stop_transaction": actions["StopTransaction"] >= 1,
        # A second accepted boot is deterministic evidence that the simulator or
        # physical charger disconnected, reconnected and booted again.
        "disconnect_recovery": actions["BootNotification"] >= 2,
        "currently_connected": connected,
    }
    required = [key for key in checks if key != "currently_connected"]
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ocpp_identity": charge_point.ocpp_identity,
        "protocol": "OCPP 1.6J",
        "passed": all(checks[key] for key in required),
        "checks": checks,
        "evidence_counts": actions,
        "evses": [
            {
                "evse_id": item.evse_id,
                "physical_reference": item.physical_reference,
                "connector_type": item.connector_type,
                "max_power_kw": item.max_power_kw,
            }
            for item in evses
        ],
    }


@router.post("/{charge_point_id}/credentials/rotate", summary="轮换充电桩独立 OCPP 密钥")
def rotate_ocpp_credentials(
    charge_point_id: str,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> dict:
    charge_point = _get_scoped_charge_point(db, charge_point_id, current_user_obj)
    from app.core.ocpp_auth import generate_ocpp_secret, hash_ocpp_secret
    secret = generate_ocpp_secret()
    charge_point.ocpp_auth_secret_hash = hash_ocpp_secret(secret)
    charge_point.commissioning_status = "draft"
    charge_point.acceptance_report = None
    db.commit()
    return {
        "ocpp_identity": charge_point.ocpp_identity,
        "secret": secret,
        "query_url": f"/ocpp?id={charge_point.ocpp_identity}",
        "path_url": f"/ocpp/{charge_point.ocpp_identity}",
    }


@router.post("/{charge_point_id}/acceptance-report", summary="生成充电桩投运验收报告")
def generate_acceptance_report(
    charge_point_id: str,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> dict:
    charge_point = _get_scoped_charge_point(db, charge_point_id, current_user_obj)
    report = _build_acceptance_report(db, charge_point)
    charge_point.acceptance_report = report
    charge_point.last_acceptance_at = datetime.now(timezone.utc)
    charge_point.commissioning_status = "ready" if report["passed"] else "testing"
    db.commit()
    return report


@router.post("/{charge_point_id}/commission", summary="正式投运已通过验收的充电桩")
def commission_charge_point(
    charge_point_id: str,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> dict:
    charge_point = _get_scoped_charge_point(db, charge_point_id, current_user_obj)
    report = _build_acceptance_report(db, charge_point)
    if not report["passed"]:
        charge_point.acceptance_report = report
        charge_point.last_acceptance_at = datetime.now(timezone.utc)
        charge_point.commissioning_status = "testing"
        db.commit()
        raise HTTPException(status_code=409, detail={"message": "Acceptance checks failed", "report": report})
    charge_point.acceptance_report = report
    charge_point.last_acceptance_at = datetime.now(timezone.utc)
    charge_point.commissioning_status = "commissioned"
    charge_point.commissioned_at = datetime.now(timezone.utc)
    db.commit()
    return {"commissioning_status": "commissioned", "report": report}


class UpdateChargerRequest(StrictRequestModel):
    vendor: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)


@router.put("/{charge_point_id}", summary="更新充电桩")
def update_charger(
    charge_point_id: str,
    req: UpdateChargerRequest,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> dict:
    """更新充电桩信息"""
    logger.info(f"[API] PUT /api/v1/chargers/{charge_point_id}")
    
    charge_point = _get_scoped_charge_point(db, charge_point_id, current_user_obj)
    
    if req.vendor is not None:
        charge_point.vendor = req.vendor
    if req.model is not None:
        charge_point.model = req.model
    
    db.commit()
    db.refresh(charge_point)
    
    logger.info(f"[API] PUT /api/v1/chargers/{charge_point_id} 成功")
    return {
        "id": str(charge_point.id),
        "ocpp_identity": charge_point.ocpp_identity,
        "vendor": charge_point.vendor,
        "model": charge_point.model,
    }


@router.get("/{charge_point_id}/retirement-preflight", summary="充电桩退役预检")
def get_charger_retirement_preflight(
    charge_point_id: str,
    current_user_obj=Depends(require_permission("chargers.read")),
    db: Session = Depends(get_db),
) -> dict:
    charge_point = _get_scoped_charge_point(db, charge_point_id, current_user_obj)
    return _retirement_preflight(db, charge_point)


@router.post("/{charge_point_id}/retire", summary="退役充电桩")
def retire_charger(
    charge_point_id: str,
    req: ChargerLifecycleRequest,
    current_user_obj=Depends(require_permission("chargers.write")),
    db: Session = Depends(get_db),
) -> dict:
    charge_point = _get_scoped_charge_point(db, charge_point_id, current_user_obj)
    reason = _normalized_reason(req.reason)
    if charge_point_lifecycle_status(charge_point) == "retired":
        return _charger_lifecycle_response(db, charge_point)

    preflight = _retirement_preflight(db, charge_point)
    if not preflight["can_retire_now"]:
        raise _coded_http_exception(
            409,
            "charger_retirement_blocked",
            "Charger has active sessions, pending commands, or unsettled business records",
            blockers=preflight["blockers"],
        )

    before_data = {
        "lifecycle_status": charge_point_lifecycle_status(charge_point),
        "commissioning_status": charge_point.commissioning_status,
        "has_ocpp_credential": bool(charge_point.ocpp_auth_secret_hash),
    }
    apply_charge_point_retired_state(charge_point)
    now = datetime.now(timezone.utc)
    (
        db.query(QrToken)
        .filter(
            QrToken.operator_tenant_id == charge_point.tenant_id,
            QrToken.charge_point_id == charge_point.id,
            QrToken.revoked_at.is_(None),
        )
        .update({QrToken.revoked_at: now}, synchronize_session=False)
    )
    add_lifecycle_audit(
        db,
        tenant_id=charge_point.tenant_id,
        actor_id=current_user_obj.id,
        action=CHARGER_RETIRE_ACTION,
        resource_type="charge_point",
        resource_id=str(charge_point.id),
        reason=reason,
        before_data=before_data,
        after_data={
            "lifecycle_status": "retired",
            "commissioning_status": "suspended",
            "has_ocpp_credential": False,
        },
    )
    db.commit()
    db.refresh(charge_point)
    return _charger_lifecycle_response(db, charge_point)


@router.post("/{charge_point_id}/restore", summary="恢复退役充电桩")
def restore_charger(
    charge_point_id: str,
    req: ChargerLifecycleRequest,
    current_user_obj=Depends(require_permission("chargers.write")),
    db: Session = Depends(get_db),
) -> dict:
    charge_point = _get_scoped_charge_point(db, charge_point_id, current_user_obj)
    reason = _normalized_reason(req.reason)
    if charge_point_lifecycle_status(charge_point) != "retired":
        previous_restore = latest_lifecycle_audit(
            db,
            tenant_id=charge_point.tenant_id,
            resource_type="charge_point",
            resource_id=str(charge_point.id),
            actions=(CHARGER_RESTORE_ACTION,),
        )
        if previous_restore:
            return {
                "charge_point_id": str(charge_point.id),
                "lifecycle_status": "active",
                "commissioning_status": charge_point.commissioning_status,
                "ocpp_identity": charge_point.ocpp_identity,
                "ocpp_secret": None,
                "credential_rotated": False,
            }
        raise _coded_http_exception(
            409,
            "charger_not_retired",
            "Only a retired charger can be restored",
            blockers=[],
        )

    before_data = {
        "lifecycle_status": "retired",
        "commissioning_status": charge_point.commissioning_status,
        "has_ocpp_credential": bool(charge_point.ocpp_auth_secret_hash),
    }
    ocpp_secret = generate_ocpp_secret()
    apply_charge_point_restored_state(charge_point)
    charge_point.ocpp_auth_secret_hash = hash_ocpp_secret(ocpp_secret)
    add_lifecycle_audit(
        db,
        tenant_id=charge_point.tenant_id,
        actor_id=current_user_obj.id,
        action=CHARGER_RESTORE_ACTION,
        resource_type="charge_point",
        resource_id=str(charge_point.id),
        reason=reason,
        before_data=before_data,
        after_data={
            "lifecycle_status": "active",
            "commissioning_status": "testing",
            "has_ocpp_credential": True,
        },
    )
    db.commit()
    db.refresh(charge_point)
    return {
        "charge_point_id": str(charge_point.id),
        "lifecycle_status": "active",
        "commissioning_status": charge_point.commissioning_status,
        "ocpp_identity": charge_point.ocpp_identity,
        "ocpp_secret": ocpp_secret,
        "credential_rotated": True,
    }


@router.delete("/{charge_point_id}", summary="永久删除未使用的充电桩", status_code=200)
def delete_charger(
    charge_point_id: str,
    req: PermanentDeleteChargerRequest,
    current_user_obj=Depends(require_permission("chargers.write")),
    db: Session = Depends(get_db)
) -> dict:
    """仅永久删除误创建且完全未使用的草稿充电桩。"""
    logger.info(f"[API] DELETE /api/v1/chargers/{charge_point_id}")

    charge_point = _get_scoped_charge_point(db, charge_point_id, current_user_obj)
    reason = _normalized_reason(req.reason)
    if req.confirmation.strip() != charge_point.ocpp_identity:
        raise _coded_http_exception(
            422,
            "charger_delete_confirmation_mismatch",
            "confirmation must match the charger OCPP identity",
        )

    blockers = _permanent_delete_blockers(db, charge_point)
    if blockers:
        raise _coded_http_exception(
            409,
            "charger_permanent_delete_blocked",
            "Only an unused draft charger can be permanently deleted",
            blockers=blockers,
        )

    charge_point_uuid = str(charge_point.id)
    ocpp_identity = charge_point.ocpp_identity
    add_lifecycle_audit(
        db,
        tenant_id=charge_point.tenant_id,
        actor_id=current_user_obj.id,
        action=CHARGER_DELETE_ACTION,
        resource_type="charge_point",
        resource_id=charge_point_uuid,
        reason=reason,
        before_data={
            "lifecycle_status": "active",
            "commissioning_status": charge_point.commissioning_status,
            "ocpp_identity": ocpp_identity,
        },
        after_data=None,
    )
    db.delete(charge_point)
    db.commit()

    logger.info(f"[API] DELETE /api/v1/chargers/{charge_point_id} 成功")
    return {
        "message": f"充电桩 {charge_point_id} 已永久删除",
        "charge_point_id": charge_point_uuid,
        "ocpp_identity": ocpp_identity,
    }


@router.put("/{charge_point_id}/pricing", response_model=ChargerPricingResponse, summary="更新充电桩覆盖定价（Tariff）")
def update_charger_pricing(
    charge_point_id: str,
    req: ChargerPricingUpdateRequest,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> ChargerPricingResponse:
    """
    充电桩级覆盖定价：
    - 版本化：关闭旧 active tariff，新建一条 active tariff（charge_point_id 维度）
    - 租户隔离：仅允许更新当前租户的充电桩
    - 权限：tariffs.edit（super_admin 或 tenant.* 也可）
    """
    tenant_id = tenant_id_context.get()
    if not tenant_id and not current_user_obj.is_super_admin:
        raise HTTPException(status_code=403, detail="Tenant ID required")

    perms = MembershipRoleService.get_user_permissions(db=db, admin_user_id=current_user_obj.id, tenant_id=tenant_id) if tenant_id else []
    if not current_user_obj.is_super_admin and not has_permission(perms, "tariffs.edit"):
        raise HTTPException(status_code=403, detail="Permission denied")

    cp = _get_scoped_charge_point(db, charge_point_id, current_user_obj)

    now = datetime.now(timezone.utc)

    # 关闭旧的 active charger-level tariffs
    old_tariffs = (
        db.query(Tariff)
        .filter(
            Tariff.tenant_id == cp.tenant_id,
            Tariff.charge_point_id == cp.id,
            Tariff.is_active == True,  # noqa: E712
        )
        .all()
    )
    for t in old_tariffs:
        t.is_active = False
        if t.valid_until is None:
            t.valid_until = now

    service_fee = float(req.service_fee) if req.service_fee is not None else 0.0
    new_tariff = Tariff(
        tenant_id=cp.tenant_id,
        site_id=cp.site_id,
        charge_point_id=cp.id,
        name=f"充电桩覆盖定价-{cp.ocpp_identity}",
        base_price_per_kwh=req.base_price_per_kwh,
        service_fee=service_fee,
        valid_from=now,
        valid_until=None,
        is_active=True,
    )
    db.add(new_tariff)
    db.commit()
    db.refresh(new_tariff)

    return ChargerPricingResponse(
        charge_point_id=str(cp.id),
        tariff_id=str(new_tariff.id),
        base_price_per_kwh=float(new_tariff.base_price_per_kwh),
        service_fee=float(new_tariff.service_fee or 0),
        valid_from=new_tariff.valid_from.isoformat() if new_tariff.valid_from else "",
    )


@router.get("/{charge_point_id}/qr", summary="获取充电桩所有connector的二维码列表")
def get_charger_qr_codes(
    charge_point_id: str,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> dict:
    """获取充电桩所有connector的二维码URL列表"""
    charge_point = _get_visible_charge_point(db, charge_point_id, current_user_obj)
    
    # 查询所有EVSE
    evses = db.query(EVSE).filter(EVSE.charge_point_id == charge_point.id).order_by(EVSE.evse_id).all()
    
    from app.services.qr_service import get_qr_code_url, get_qr_code_path, get_qr_storage_dir
    
    qr_storage_dir = get_qr_storage_dir()
    qr_list = []
    
    for evse in evses:
        qr_path = get_qr_code_path(str(charge_point.id), evse.evse_id, qr_storage_dir)
        qr_url = get_qr_code_url(str(charge_point.id), evse.evse_id)
        
        # 检查文件是否存在
        exists = qr_path.exists()
        token_rec = (
            db.query(QrToken)
            .filter(
                QrToken.charge_point_id == charge_point.id,
                QrToken.connector_id == evse.evse_id,
                QrToken.revoked_at.is_(None),
            )
            .first()
        )
        
        qr_list.append({
            "connector_id": evse.evse_id,
            "qr_token": token_rec.token if token_rec else None,
            "qr_url": qr_url,
            "filename": qr_path.name,
            "exists": exists,
        })
    
    return {
        "charge_point_id": str(charge_point.id),
        "ocpp_identity": charge_point.ocpp_identity,
        "qr_codes": qr_list,
    }


@router.get("/{charge_point_id}/qr/{connector_id}", summary="获取指定connector的二维码")
def get_charger_qr_code(
    charge_point_id: str,
    connector_id: int,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> dict:
    """获取指定connector的二维码信息"""
    charge_point = _get_visible_charge_point(db, charge_point_id, current_user_obj)
    
    # 验证connector是否存在
    evse = db.query(EVSE).filter(
        EVSE.charge_point_id == charge_point.id,
        EVSE.evse_id == connector_id
    ).first()
    
    if not evse:
        raise HTTPException(status_code=404, detail=f"Connector {connector_id} 未找到")
    
    from app.services.qr_service import get_qr_code_url, get_qr_code_path, get_qr_storage_dir, build_qr_payload
    
    qr_storage_dir = get_qr_storage_dir()
    qr_path = get_qr_code_path(str(charge_point.id), connector_id, qr_storage_dir)
    qr_url = get_qr_code_url(str(charge_point.id), connector_id)
    token_rec = (
        db.query(QrToken)
        .filter(
            QrToken.charge_point_id == charge_point.id,
            QrToken.connector_id == connector_id,
            QrToken.revoked_at.is_(None),
        )
        .first()
    )
    payload = build_qr_payload(token_rec.token) if token_rec else None
    
    return {
        "charge_point_id": str(charge_point.id),
        "ocpp_identity": charge_point.ocpp_identity,
        "connector_id": connector_id,
        "qr_token": token_rec.token if token_rec else None,
        "qr_url": qr_url,
        "filename": qr_path.name,
        "payload": payload,  # 二维码内容（用于调试）
        "exists": qr_path.exists(),
    }


@router.post("/{charge_point_id}/qr/{connector_id}/generate", summary="生成指定connector的二维码")
def generate_charger_qr_code(
    charge_point_id: str,
    connector_id: int,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> dict:
    """为指定connector生成二维码"""
    charge_point = _get_scoped_charge_point(db, charge_point_id, current_user_obj)
    _require_operational_charger(charge_point)
    
    # 验证connector是否存在
    evse = db.query(EVSE).filter(
        EVSE.charge_point_id == charge_point.id,
        EVSE.evse_id == connector_id
    ).first()
    
    if not evse:
        raise HTTPException(status_code=404, detail=f"Connector {connector_id} 未找到")
    
    from app.services.qr_service import generate_qr_code, get_qr_code_url, get_qr_storage_dir, ensure_qr_token
    
    try:
        qr_storage_dir = get_qr_storage_dir()
        qr_path = generate_qr_code(
            db=db,
            charge_point_id=charge_point.id,
            connector_id=connector_id,
            output_dir=qr_storage_dir,
        )
        token_rec = ensure_qr_token(db, charge_point.id, connector_id)
        qr_url = get_qr_code_url(str(charge_point.id), connector_id)
        
        logger.info(f"[API] 成功生成二维码: {charge_point_id} connector {connector_id} -> {qr_path}")
        
        return {
            "charge_point_id": str(charge_point.id),
            "ocpp_identity": charge_point.ocpp_identity,
            "connector_id": connector_id,
            "qr_token": token_rec.token,
            "qr_url": qr_url,
            "filename": qr_path.name,
            "message": "二维码生成成功",
        }
    except Exception as e:
        logger.error(f"[API] 生成二维码失败: {charge_point_id} connector {connector_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成二维码失败: {str(e)}")


@router.post("/{charge_point_id}/qr/generate-all", summary="为充电桩所有connector生成二维码")
def generate_all_charger_qr_codes(
    charge_point_id: str,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> dict:
    """为充电桩所有connector生成二维码"""
    charge_point = _get_scoped_charge_point(db, charge_point_id, current_user_obj)
    _require_operational_charger(charge_point)
    
    # 查询所有EVSE
    evses = db.query(EVSE).filter(EVSE.charge_point_id == charge_point.id).order_by(EVSE.evse_id).all()
    
    if not evses:
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 没有找到任何connector")
    
    from app.services.qr_service import generate_qr_code, get_qr_code_url, get_qr_storage_dir, ensure_qr_token
    
    qr_storage_dir = get_qr_storage_dir()
    results = []
    errors = []
    
    for evse in evses:
        try:
            qr_path = generate_qr_code(
                db=db,
                charge_point_id=charge_point.id,
                connector_id=evse.evse_id,
                output_dir=qr_storage_dir,
            )
            token_rec = ensure_qr_token(db, charge_point.id, evse.evse_id)
            qr_url = get_qr_code_url(str(charge_point.id), evse.evse_id)
            results.append({
                "connector_id": evse.evse_id,
                "qr_token": token_rec.token,
                "qr_url": qr_url,
                "filename": qr_path.name,
                "success": True,
            })
        except Exception as e:
            logger.error(f"[API] 生成二维码失败: {charge_point_id} connector {evse.evse_id}: {e}", exc_info=True)
            errors.append({
                "connector_id": evse.evse_id,
                "error": str(e),
            })
    
    return {
        "charge_point_id": str(charge_point.id),
        "ocpp_identity": charge_point.ocpp_identity,
        "generated": results,
        "errors": errors,
        "total": len(evses),
        "success_count": len(results),
        "error_count": len(errors),
    }
