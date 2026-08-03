#
# 站点管理 API
# 以站点（Site）为核心：CRUD + 站点详情聚合 + 绑定/迁移充电桩
#

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, literal, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.id_generator import generate_site_id
from app.core.asset_identifiers import OCPP_IDENTITY_PATTERN, get_charge_point_by_reference, get_site_by_reference
from app.core.logging_config import get_logger
from app.core.permissions import get_current_admin_user, require_permission
from app.database.base import get_db, tenant_id_context
from app.database.models import (
    AppUserFavoriteSite,
    AuditLog,
    ChargePoint,
    ChargingSession,
    EVSE,
    EVSEStatus,
    Invoice,
    Order,
    OutboxEvent,
    Payment,
    Site,
    Tariff,
)
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.api.validation import OperatingHours, SiteCoordinatesMixin, StrictRequestModel, TrimmedAddress, TrimmedSiteName

# 与站点详情、充电桩列表一致：5 分钟内有 EVSE 心跳视为在线
ONLINE_THRESHOLD_SECONDS = 300
from app.core.permissions import has_permission
from app.services.role_service import MembershipRoleService
from app.services.asset_lifecycle_service import (
    SITE_ARCHIVE_ACTION,
    SITE_DELETE_ACTION,
    SITE_RESTORE_ACTION,
    CHARGER_MOVE_ACTION,
    LifecycleReasonError,
    add_lifecycle_audit,
    apply_site_archived_state,
    apply_site_restored_state,
    latest_lifecycle_audit,
    normalize_lifecycle_reason,
    site_lifecycle_status,
)

logger = get_logger("ocpp_csms")

router = APIRouter()


class SiteCreateRequest(SiteCoordinatesMixin):
    name: TrimmedSiteName
    address: TrimmedAddress
    latitude: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(..., ge=-180, le=180, allow_inf_nan=False)
    is_active: bool = True
    operating_hours: Optional[OperatingHours] = None
    domain: Optional[str] = Field(None, max_length=200)  # 预留展示字段


class SiteUpdateRequest(SiteCoordinatesMixin):
    name: Optional[TrimmedSiteName] = None
    address: Optional[TrimmedAddress] = None
    is_active: Optional[bool] = None
    operating_hours: Optional[OperatingHours] = None
    domain: Optional[str] = Field(None, max_length=200)


class SiteListItem(BaseModel):
    id: str
    site_code: str
    name: str
    address: str
    latitude: float
    longitude: float
    is_active: bool
    operating_hours: Optional[str]
    domain: Optional[str]
    charge_points_count: int
    online_charge_points_count: int
    lifecycle_status: Literal["active", "archived"]
    archived_at: Optional[str] = None
    archive_reason: Optional[str] = None
    active_charge_points_count: int
    retiring_charge_points_count: int = 0
    retired_charge_points_count: int
    created_at: str
    updated_at: str


class SiteDetailChargePoint(BaseModel):
    id: str
    ocpp_identity: str
    display_code: str
    display_name: Optional[str]
    location_hint: Optional[str]
    vendor: Optional[str]
    model: Optional[str]
    status: str
    last_seen: Optional[str]
    site_id: str
    site_name: Optional[str] = None
    lifecycle_status: Literal["active", "retired"] = "active"


class SiteDetailResponse(BaseModel):
    id: str
    site_code: str
    name: str
    address: str
    latitude: float
    longitude: float
    is_active: bool
    operating_hours: Optional[str]
    domain: Optional[str]
    price_per_kwh: Optional[float] = None
    charge_points: List[SiteDetailChargePoint]
    lifecycle_status: Literal["active", "archived"]
    archived_at: Optional[str] = None
    archive_reason: Optional[str] = None
    active_charge_points_count: int
    retiring_charge_points_count: int = 0
    retired_charge_points_count: int
    created_at: str
    updated_at: str


class SitePricingUpdateRequest(BaseModel):
    """站点级基础电价（作为默认价）"""

    base_price_per_kwh: Decimal = Field(..., gt=0, description="基础电价（每kWh）")
    service_fee: Optional[Decimal] = Field(None, ge=0, description="服务费（可选）")


class SitePricingResponse(BaseModel):
    site_id: str
    tariff_id: str
    base_price_per_kwh: Decimal
    service_fee: Decimal
    valid_from: str


class SiteLifecycleRequest(StrictRequestModel):
    reason: str = Field(..., min_length=3, max_length=500)


class PermanentDeleteSiteRequest(SiteLifecycleRequest):
    confirmation: str = Field(..., min_length=1, max_length=100)


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


def _site_archive_audit(db: Session, site: Site):
    if site_lifecycle_status(site) != "archived":
        return None
    return latest_lifecycle_audit(
        db,
        tenant_id=site.tenant_id,
        resource_type="site",
        resource_id=str(site.id),
        actions=(SITE_ARCHIVE_ACTION,),
    )


def _site_lifecycle_fields(db: Session, site: Site) -> dict:
    archive_audit = _site_archive_audit(db, site)
    return {
        "lifecycle_status": site_lifecycle_status(site),
        "archived_at": archive_audit.created_at.isoformat() if archive_audit else None,
        "archive_reason": (
            (archive_audit.audit_metadata or {}).get("reason")
            if archive_audit else None
        ),
    }


def _require_tenant_id_for_create(current_user_obj) -> Optional[str]:
    """
    站点是租户级资产：创建时必须明确 tenant_id。
    非 super_admin 必须依赖 tenant middleware 注入；super_admin 也建议显式传 X-Tenant-Id。
    """
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    return str(tenant_id)


def _get_scoped_site(db: Session, reference: str, current_user_obj) -> Site:
    site = get_site_by_reference(db, reference)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    tenant_id = tenant_id_context.get()
    if tenant_id and site.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Site belongs to another tenant")
    if not tenant_id and not current_user_obj.is_super_admin:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    return site


def _site_archive_preflight(db: Session, site: Site) -> dict:
    active_charge_points = (
        db.query(ChargePoint.id, ChargePoint.display_code)
        .filter(
            ChargePoint.tenant_id == site.tenant_id,
            ChargePoint.site_id == site.id,
            ChargePoint.is_active.is_(True),
        )
        .all()
    )
    retired_charge_points = (
        db.query(ChargePoint.id)
        .filter(
            ChargePoint.tenant_id == site.tenant_id,
            ChargePoint.site_id == site.id,
            ChargePoint.is_active.is_(False),
        )
        .all()
    )
    ongoing_sessions = (
        db.query(ChargingSession.id)
        .join(ChargePoint, ChargingSession.charge_point_id == ChargePoint.id)
        .filter(
            ChargingSession.tenant_id == site.tenant_id,
            ChargePoint.site_id == site.id,
            ChargingSession.status == "ongoing",
        )
        .all()
    )

    unsettled_records = []
    unsettled_sessions = (
        db.query(ChargingSession.id)
        .join(ChargePoint, ChargingSession.charge_point_id == ChargePoint.id)
        .filter(
            ChargingSession.tenant_id == site.tenant_id,
            ChargePoint.site_id == site.id,
            ChargingSession.status != "ongoing",
            ChargingSession.payment_status.in_(("pending", "unpaid")),
        )
        .all()
    )
    unsettled_records.extend(("charging_session", row.id) for row in unsettled_sessions)

    unsettled_orders = (
        db.query(Order.id)
        .join(ChargePoint, Order.charge_point_id == ChargePoint.id)
        .filter(
            Order.tenant_id == site.tenant_id,
            ChargePoint.site_id == site.id,
            Order.status.in_(("pending", "authorized", "ongoing")),
        )
        .all()
    )
    unsettled_records.extend(("order", row.id) for row in unsettled_orders)

    unsettled_invoices = (
        db.query(Invoice.id)
        .join(ChargingSession, Invoice.session_id == ChargingSession.id)
        .join(ChargePoint, ChargingSession.charge_point_id == ChargePoint.id)
        .filter(
            Invoice.tenant_id == site.tenant_id,
            ChargePoint.site_id == site.id,
            Invoice.status == "pending",
        )
        .all()
    )
    unsettled_records.extend(("invoice", row.id) for row in unsettled_invoices)

    unsettled_payments = (
        db.query(Payment.id)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .join(ChargingSession, Invoice.session_id == ChargingSession.id)
        .join(ChargePoint, ChargingSession.charge_point_id == ChargePoint.id)
        .filter(
            Payment.tenant_id == site.tenant_id,
            ChargePoint.site_id == site.id,
            Payment.status == "pending",
        )
        .all()
    )
    unsettled_records.extend(("payment", row.id) for row in unsettled_payments)

    blockers = [
        {
            "type": "active_charge_point",
            "resource_id": str(row.id),
            "display_code": row.display_code,
        }
        for row in active_charge_points
    ]
    blockers.extend(
        {"type": "ongoing_session", "resource_id": str(row.id)}
        for row in ongoing_sessions
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
        "site_id": str(site.id),
        "lifecycle_status": site_lifecycle_status(site),
        "can_archive_now": not blockers,
        "counts": {
            "active_charge_points": len(active_charge_points),
            "retiring_charge_points": 0,
            "retired_charge_points": len(retired_charge_points),
            "ongoing_sessions": len(ongoing_sessions),
            "unsettled_business_records": len(unsettled_records),
        },
        "blockers": blockers,
    }


def _site_lifecycle_response(db: Session, site: Site) -> dict:
    fields = _site_lifecycle_fields(db, site)
    return {
        "site_id": str(site.id),
        "lifecycle_status": fields["lifecycle_status"],
        "archived_at": fields["archived_at"],
        "archive_reason": fields["archive_reason"],
    }


def _site_permanent_delete_blockers(db: Session, site: Site) -> list[dict]:
    blockers: list[dict] = []

    def add_count(blocker_type: str, count: int) -> None:
        if count:
            blockers.append({"type": blocker_type, "count": count})

    if site.is_active is not True:
        blockers.append({"type": "lifecycle_history", "count": 1})
    add_count(
        "charge_point",
        db.query(ChargePoint).filter(ChargePoint.site_id == site.id).count(),
    )
    add_count(
        "tariff",
        db.query(Tariff).filter(Tariff.site_id == site.id).count(),
    )
    add_count(
        "favorite",
        db.query(AppUserFavoriteSite).filter(AppUserFavoriteSite.site_id == site.id).count(),
    )
    add_count(
        "audit_log",
        db.query(AuditLog)
        .filter(
            AuditLog.tenant_id == site.tenant_id,
            AuditLog.resource_type == "site",
            AuditLog.resource_id == str(site.id),
        )
        .count(),
    )
    return blockers


def _charge_point_move_blockers(db: Session, charge_point: ChargePoint) -> list[dict]:
    blockers: list[dict] = []
    if charge_point.is_active is not True:
        blockers.append(
            {
                "type": "charger_not_operational",
                "resource_id": str(charge_point.id),
            }
        )

    sessions = (
        db.query(ChargingSession.id, ChargingSession.status)
        .filter(
            ChargingSession.tenant_id == charge_point.tenant_id,
            ChargingSession.charge_point_id == charge_point.id,
        )
        .all()
    )
    blockers.extend(
        {
            "type": (
                "ongoing_session"
                if row.status == "ongoing"
                else "charging_session_history"
            ),
            "resource_id": str(row.id),
        }
        for row in sessions
    )

    orders = (
        db.query(Order.id)
        .filter(
            Order.tenant_id == charge_point.tenant_id,
            Order.charge_point_id == charge_point.id,
        )
        .all()
    )
    blockers.extend(
        {"type": "order_history", "resource_id": str(row.id)}
        for row in orders
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
    blockers.extend(
        {"type": "pending_remote_command", "resource_id": str(row.id)}
        for row in pending_commands
    )
    return blockers


@router.get("", response_model=List[SiteListItem], summary="获取站点列表")
def list_sites(
    q: Optional[str] = Query(None, description="搜索：站点名称/地址/ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    include_inactive: bool = Query(False, description="是否包含已归档/未启用站点"),
    lifecycle_status: Optional[Literal["active", "archived"]] = Query(
        None,
        description="生命周期筛选",
    ),
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> List[SiteListItem]:
    tenant_id = tenant_id_context.get()

    base = db.query(Site)
    # 只要明确选择了租户，列表就必须进入该租户作用域；超级管理员只有在
    # 不携带租户上下文的“全平台”视图下才能看到全部站点。
    if tenant_id:
        base = base.filter(Site.tenant_id == tenant_id)

    if lifecycle_status == "active":
        base = base.filter(Site.is_active.is_(True))
    elif lifecycle_status == "archived":
        base = base.filter(Site.is_active.is_(False))
    elif not include_inactive:
        base = base.filter(Site.is_active == True)  # noqa: E712

    if q:
        like = f"%{q.strip()}%"
        base = base.filter(or_(Site.site_code.ilike(like), Site.name.ilike(like), Site.address.ilike(like)))

    # 统计：每站点的充电桩数量
    cp_count_sq = (
        db.query(ChargePoint.site_id.label("site_id"), func.count(ChargePoint.id).label("cp_count"))
        .filter(ChargePoint.is_active.is_(True))
        .group_by(ChargePoint.site_id)
        .subquery()
    )
    retired_cp_count_sq = (
        db.query(
            ChargePoint.site_id.label("site_id"),
            func.count(ChargePoint.id).label("retired_cp_count"),
        )
        .filter(ChargePoint.is_active.is_(False))
        .group_by(ChargePoint.site_id)
        .subquery()
    )
    # 统计：每站点的在线充电桩数量（5 分钟内有 EVSE 心跳）
    online_threshold = datetime.now(timezone.utc) - timedelta(seconds=ONLINE_THRESHOLD_SECONDS)
    online_cp_sq = (
        db.query(
            ChargePoint.site_id.label("site_id"),
            func.count(func.distinct(ChargePoint.id)).label("online_cp_count"),
        )
        .join(EVSEStatus, EVSEStatus.charge_point_id == ChargePoint.id)
        .filter(
            ChargePoint.is_active.is_(True),
            EVSEStatus.last_seen >= online_threshold,
            or_(EVSEStatus.status.is_(None), EVSEStatus.status != "Offline"),
        )
        .group_by(ChargePoint.site_id)
        .subquery()
    )

    rows = (
        base.outerjoin(cp_count_sq, cp_count_sq.c.site_id == Site.id)
        .outerjoin(retired_cp_count_sq, retired_cp_count_sq.c.site_id == Site.id)
        .outerjoin(online_cp_sq, online_cp_sq.c.site_id == Site.id)
        .order_by(Site.created_at.desc())
        .offset(skip)
        .limit(limit)
        .with_entities(
            Site,
            cp_count_sq.c.cp_count,
            retired_cp_count_sq.c.retired_cp_count,
            online_cp_sq.c.online_cp_count,
        )
        .all()
    )

    archived_resource_ids = [
        str(site.id)
        for site, _cp_count, _retired_cp_count, _online_cp_count in rows
        if site.is_active is False
    ]
    archive_audit_map = {}
    if archived_resource_ids:
        archive_audits = (
            db.query(AuditLog)
            .filter(
                AuditLog.resource_type == "site",
                AuditLog.resource_id.in_(archived_resource_ids),
                AuditLog.action == SITE_ARCHIVE_ACTION,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .all()
        )
        for audit in archive_audits:
            archive_audit_map.setdefault(audit.resource_id, audit)

    result: List[SiteListItem] = []
    for site, cp_count, retired_cp_count, online_cp_count in rows:
        archive_audit = archive_audit_map.get(str(site.id))
        lifecycle_fields = {
            "lifecycle_status": site_lifecycle_status(site),
            "archived_at": (
                archive_audit.created_at.isoformat() if archive_audit else None
            ),
            "archive_reason": (
                (archive_audit.audit_metadata or {}).get("reason")
                if archive_audit else None
            ),
        }
        # domain 目前不在 Site 表中；为了不影响 DB schema，这里仅从 settings/operating_hours 等扩展字段不读取。
        result.append(
            SiteListItem(
                id=str(site.id),
                site_code=site.site_code,
                name=site.name,
                address=site.address,
                latitude=site.latitude,
                longitude=site.longitude,
                is_active=bool(site.is_active),
                operating_hours=site.operating_hours,
                domain=None,
                charge_points_count=int(cp_count or 0),
                online_charge_points_count=int(online_cp_count or 0),
                lifecycle_status=lifecycle_fields["lifecycle_status"],
                archived_at=lifecycle_fields["archived_at"],
                archive_reason=lifecycle_fields["archive_reason"],
                active_charge_points_count=int(cp_count or 0),
                retiring_charge_points_count=0,
                retired_charge_points_count=int(retired_cp_count or 0),
                created_at=site.created_at.isoformat() if site.created_at else "",
                updated_at=site.updated_at.isoformat() if site.updated_at else "",
            )
        )
    return result


@router.post("", response_model=SiteDetailResponse, summary="创建站点", status_code=201)
def create_site(
    req: SiteCreateRequest,
    current_user_obj=Depends(require_permission("sites.write")),
    db: Session = Depends(get_db),
) -> SiteDetailResponse:
    _require_tenant_id_for_create(current_user_obj)
    if req.is_active is not True:
        raise _coded_http_exception(
            422,
            "site_lifecycle_endpoint_required",
            "New sites must be active; use the archive endpoint after creation",
        )
    tenant_id = tenant_id_context.get()
    assert tenant_id is not None

    site = Site(
        site_code=generate_site_id(req.name),
        tenant_id=tenant_id,
        name=req.name,
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude,
        is_active=req.is_active,
        operating_hours=req.operating_hours,
    )
    db.add(site)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Site identifier already exists") from exc
    db.refresh(site)

    return SiteDetailResponse(
        id=str(site.id),
        site_code=site.site_code,
        name=site.name,
        address=site.address,
        latitude=site.latitude,
        longitude=site.longitude,
        is_active=bool(site.is_active),
        operating_hours=site.operating_hours,
        domain=None,
        price_per_kwh=None,
        charge_points=[],
        lifecycle_status="active",
        archived_at=None,
        archive_reason=None,
        active_charge_points_count=0,
        retiring_charge_points_count=0,
        retired_charge_points_count=0,
        created_at=site.created_at.isoformat() if site.created_at else "",
        updated_at=site.updated_at.isoformat() if site.updated_at else "",
    )


@router.get("/{site_id}", response_model=SiteDetailResponse, summary="获取站点详情（含站点下充电桩）")
def get_site_detail(
    site_id: str = Path(..., description="站点ID"),
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> SiteDetailResponse:
    site = _get_scoped_site(db, site_id, current_user_obj)

    # 站点价格（站点级 tariff：取 active 的第一条）
    now = datetime.now(timezone.utc)
    tariff = (
        db.query(Tariff)
        .filter(
            Tariff.tenant_id == site.tenant_id,
            Tariff.site_id == site.id,
            Tariff.charge_point_id.is_(None),
            Tariff.is_active == True,  # noqa: E712
            Tariff.valid_from <= now,
        )
        .filter((Tariff.valid_until.is_(None)) | (Tariff.valid_until >= now))
        .order_by(Tariff.valid_from.desc())
        .first()
    )

    cps = db.query(ChargePoint).filter(
        ChargePoint.site_id == site.id,
        ChargePoint.is_active.is_(True),
    ).all()
    cp_ids = [cp.id for cp in cps]

    status_map: Dict[str, Dict[str, Any]] = {}
    if cp_ids:
        # 取每个 charge_point_id 的“最新 last_seen”记录作为展示
        # 简化实现：先取 max(last_seen)；status 取对应 max(last_seen) 的记录（Postgres 上用 distinct on 更佳，这里用两步法）
        latest_sq = (
            db.query(EVSEStatus.charge_point_id.label("cp_id"), func.max(EVSEStatus.last_seen).label("max_last_seen"))
            .filter(EVSEStatus.charge_point_id.in_(cp_ids))
            .group_by(EVSEStatus.charge_point_id)
            .subquery()
        )
        latest_rows = (
            db.query(EVSEStatus)
            .join(
                latest_sq,
                (EVSEStatus.charge_point_id == latest_sq.c.cp_id)
                & (EVSEStatus.last_seen == latest_sq.c.max_last_seen),
            )
            .all()
        )
        for r in latest_rows:
            status_map[r.charge_point_id] = {
                "status": r.status or "Unknown",
                "last_seen": r.last_seen,  # 保持 datetime 对象，后面再转换
            }

    charge_points: List[SiteDetailChargePoint] = []
    for cp in cps:
        st = status_map.get(cp.id) or {"status": "Unknown", "last_seen": None}
        
        # 根据 last_seen 判断是否真正在线（超过5分钟未更新则认为离线）
        status_to_use = st["status"]
        last_seen_dt = st["last_seen"]
        if last_seen_dt:
            time_diff = datetime.now(timezone.utc) - last_seen_dt.replace(tzinfo=timezone.utc) if last_seen_dt.tzinfo is None else datetime.now(timezone.utc) - last_seen_dt
            if time_diff.total_seconds() >= 300:  # 超过5分钟未更新则认为离线
                status_to_use = "Offline"
        
        charge_points.append(
            SiteDetailChargePoint(
                id=str(cp.id),
                ocpp_identity=cp.ocpp_identity,
                display_code=cp.display_code,
                display_name=cp.display_name,
                location_hint=cp.location_hint,
                vendor=cp.vendor,
                model=cp.model,
                status=status_to_use,
                last_seen=last_seen_dt.isoformat() if last_seen_dt else None,
                site_id=str(site.id),
                site_name=site.name,
                lifecycle_status="active",
            )
        )

    retired_charge_points_count = (
        db.query(func.count(ChargePoint.id))
        .filter(
            ChargePoint.site_id == site.id,
            ChargePoint.is_active.is_(False),
        )
        .scalar()
        or 0
    )
    lifecycle_fields = _site_lifecycle_fields(db, site)

    return SiteDetailResponse(
        id=str(site.id),
        site_code=site.site_code,
        name=site.name,
        address=site.address,
        latitude=site.latitude,
        longitude=site.longitude,
        is_active=bool(site.is_active),
        operating_hours=site.operating_hours,
        domain=None,
        price_per_kwh=float(tariff.base_price_per_kwh) if tariff else None,
        charge_points=charge_points,
        lifecycle_status=lifecycle_fields["lifecycle_status"],
        archived_at=lifecycle_fields["archived_at"],
        archive_reason=lifecycle_fields["archive_reason"],
        active_charge_points_count=len(charge_points),
        retiring_charge_points_count=0,
        retired_charge_points_count=int(retired_charge_points_count),
        created_at=site.created_at.isoformat() if site.created_at else "",
        updated_at=site.updated_at.isoformat() if site.updated_at else "",
    )


@router.put("/{site_id}", response_model=SiteDetailResponse, summary="更新站点")
def update_site(
    site_id: str,
    req: SiteUpdateRequest,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> SiteDetailResponse:
    site = _get_scoped_site(db, site_id, current_user_obj)

    if req.is_active is not None and req.is_active is not bool(site.is_active):
        raise _coded_http_exception(
            422,
            "site_lifecycle_endpoint_required",
            "Use the archive or restore endpoint to change site lifecycle",
        )

    final_latitude = req.latitude if req.latitude is not None else site.latitude
    final_longitude = req.longitude if req.longitude is not None else site.longitude
    if final_latitude == 0 and final_longitude == 0:
        raise HTTPException(
            status_code=422,
            detail=[{"type": "value_error", "loc": ["body", "latitude"], "msg": "latitude and longitude must not both be zero", "input": [final_latitude, final_longitude]}],
        )

    if req.name is not None:
        site.name = req.name
    if req.address is not None:
        site.address = req.address
    if req.latitude is not None:
        site.latitude = req.latitude
    if req.longitude is not None:
        site.longitude = req.longitude
    if req.operating_hours is not None:
        site.operating_hours = req.operating_hours

    db.commit()
    db.refresh(site)

    # 复用详情输出
    return get_site_detail(site_id=site.id, current_user_obj=current_user_obj, db=db)


@router.put("/{site_id}/pricing", response_model=SitePricingResponse, summary="更新站点默认定价（Tariff）")
def update_site_pricing(
    site_id: str,
    req: SitePricingUpdateRequest,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> SitePricingResponse:
    """
    站点级定价作为默认电价：
    - 版本化：关闭旧 active tariff，新建一条 active tariff
    - 租户隔离：仅允许更新当前租户下的站点
    - 权限：tariffs.edit（super_admin 或 tenant.* 也可）
    """
    tenant_id = tenant_id_context.get()
    if not tenant_id and not current_user_obj.is_super_admin:
        raise HTTPException(status_code=403, detail="Tenant ID required")

    perms = MembershipRoleService.get_user_permissions(db=db, admin_user_id=current_user_obj.id, tenant_id=tenant_id) if tenant_id else []
    if not current_user_obj.is_super_admin and not has_permission(perms, "tariffs.edit"):
        raise HTTPException(status_code=403, detail="Permission denied")

    site = _get_scoped_site(db, site_id, current_user_obj)

    now = datetime.now(timezone.utc)

    # 关闭旧的 active site-level tariffs
    old_tariffs = (
        db.query(Tariff)
        .filter(
            Tariff.tenant_id == site.tenant_id,
            Tariff.site_id == site.id,
            Tariff.charge_point_id.is_(None),
            Tariff.is_active == True,  # noqa: E712
        )
        .all()
    )
    for t in old_tariffs:
        t.is_active = False
        # 只在未设置有效期时补齐，避免覆盖历史数据
        if t.valid_until is None:
            t.valid_until = now

    service_fee = float(req.service_fee) if req.service_fee is not None else 0.0
    new_tariff = Tariff(
        tenant_id=site.tenant_id,
        site_id=str(site.id),
        charge_point_id=None,
        name="站点默认定价",
        base_price_per_kwh=req.base_price_per_kwh,
        service_fee=service_fee,
        valid_from=now,
        valid_until=None,
        is_active=True,
    )
    db.add(new_tariff)
    db.commit()
    db.refresh(new_tariff)

    return SitePricingResponse(
        site_id=str(site.id),
        tariff_id=str(new_tariff.id),
        base_price_per_kwh=float(new_tariff.base_price_per_kwh),
        service_fee=float(new_tariff.service_fee or 0),
        valid_from=new_tariff.valid_from.isoformat() if new_tariff.valid_from else "",
    )


@router.get("/{site_id}/archive-preflight", summary="站点归档预检")
def get_site_archive_preflight(
    site_id: str,
    current_user_obj=Depends(require_permission("sites.read")),
    db: Session = Depends(get_db),
) -> dict:
    site = _get_scoped_site(db, site_id, current_user_obj)
    return _site_archive_preflight(db, site)


@router.post("/{site_id}/archive", summary="归档站点")
def archive_site(
    site_id: str,
    req: SiteLifecycleRequest,
    current_user_obj=Depends(require_permission("sites.write")),
    db: Session = Depends(get_db),
) -> dict:
    site = _get_scoped_site(db, site_id, current_user_obj)
    reason = _normalized_reason(req.reason)
    if site_lifecycle_status(site) == "archived":
        return _site_lifecycle_response(db, site)

    preflight = _site_archive_preflight(db, site)
    if not preflight["can_archive_now"]:
        raise _coded_http_exception(
            409,
            "site_archive_blocked",
            "Site has active charge points or unfinished business",
            blockers=preflight["blockers"],
        )

    apply_site_archived_state(site)
    add_lifecycle_audit(
        db,
        tenant_id=site.tenant_id,
        actor_id=current_user_obj.id,
        action=SITE_ARCHIVE_ACTION,
        resource_type="site",
        resource_id=str(site.id),
        reason=reason,
        before_data={"lifecycle_status": "active"},
        after_data={"lifecycle_status": "archived"},
    )
    db.commit()
    db.refresh(site)
    return _site_lifecycle_response(db, site)


@router.post("/{site_id}/restore", summary="恢复归档站点")
def restore_site(
    site_id: str,
    req: SiteLifecycleRequest,
    current_user_obj=Depends(require_permission("sites.write")),
    db: Session = Depends(get_db),
) -> dict:
    site = _get_scoped_site(db, site_id, current_user_obj)
    reason = _normalized_reason(req.reason)
    if site_lifecycle_status(site) != "archived":
        previous_restore = latest_lifecycle_audit(
            db,
            tenant_id=site.tenant_id,
            resource_type="site",
            resource_id=str(site.id),
            actions=(SITE_RESTORE_ACTION,),
        )
        if previous_restore:
            return _site_lifecycle_response(db, site)
        raise _coded_http_exception(
            409,
            "site_not_archived",
            "Only an archived site can be restored",
            blockers=[],
        )

    apply_site_restored_state(site)
    add_lifecycle_audit(
        db,
        tenant_id=site.tenant_id,
        actor_id=current_user_obj.id,
        action=SITE_RESTORE_ACTION,
        resource_type="site",
        resource_id=str(site.id),
        reason=reason,
        before_data={"lifecycle_status": "archived"},
        after_data={"lifecycle_status": "active"},
    )
    db.commit()
    db.refresh(site)
    return _site_lifecycle_response(db, site)


@router.delete("/{site_id}", summary="永久删除未使用站点")
def delete_site(
    site_id: str,
    req: PermanentDeleteSiteRequest,
    current_user_obj=Depends(require_permission("sites.write")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    site = _get_scoped_site(db, site_id, current_user_obj)
    reason = _normalized_reason(req.reason)
    if req.confirmation.strip() != site.site_code:
        raise _coded_http_exception(
            422,
            "site_delete_confirmation_mismatch",
            "confirmation must match the site code",
        )

    blockers = _site_permanent_delete_blockers(db, site)
    if blockers:
        raise _coded_http_exception(
            409,
            "site_permanent_delete_blocked",
            "Only a completely unused site can be permanently deleted",
            blockers=blockers,
        )

    site_uuid = str(site.id)
    site_code = site.site_code
    add_lifecycle_audit(
        db,
        tenant_id=site.tenant_id,
        actor_id=current_user_obj.id,
        action=SITE_DELETE_ACTION,
        resource_type="site",
        resource_id=site_uuid,
        reason=reason,
        before_data={
            "lifecycle_status": "active",
            "site_code": site_code,
            "name": site.name,
        },
        after_data=None,
    )
    db.delete(site)
    db.commit()
    return {
        "message": "Site permanently deleted",
        "site_id": site_uuid,
        "site_code": site_code,
    }


@router.get(
    "/{site_id}/bindable-charge-points",
    response_model=List[SiteDetailChargePoint],
    summary="获取可绑定到该站点的充电桩列表",
)
def list_bindable_charge_points(
    site_id: str,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> List[SiteDetailChargePoint]:
    """
    返回“可绑定”的充电桩列表，默认策略：当前属于系统自动生成的单桩站点。
    - auto site: site.name == '站点-{charge_point_id}' 或 site.id == 'site-{charge_point_id}'
    """
    tenant_id = tenant_id_context.get()
    target_site = _get_scoped_site(db, site_id, current_user_obj)
    if target_site.is_active is not True:
        raise _coded_http_exception(
            409,
            "charger_move_blocked",
            "Charge points can only be moved to an active site",
            blockers=[
                {"type": "target_site_archived", "resource_id": str(target_site.id)}
            ],
        )

    cp_q = db.query(ChargePoint).join(Site, Site.id == ChargePoint.site_id).filter(
        ChargePoint.is_active.is_(True),
        Site.is_active.is_(True),
    )
    if tenant_id:
        cp_q = cp_q.filter(ChargePoint.tenant_id == tenant_id)

    # 排除已经属于目标站点的
    cp_q = cp_q.filter(ChargePoint.site_id != target_site.id)

    auto_site_rule = or_(
        Site.name == literal("站点-") + ChargePoint.ocpp_identity,
        Site.site_code == literal("site-") + ChargePoint.ocpp_identity,
    )
    cps = [
        cp
        for cp in cp_q.filter(auto_site_rule).all()
        if not _charge_point_move_blockers(db, cp)
    ]

    cp_ids = [cp.id for cp in cps]
    status_map: Dict[str, Dict[str, Any]] = {}
    if cp_ids:
        latest_sq = (
            db.query(EVSEStatus.charge_point_id.label("cp_id"), func.max(EVSEStatus.last_seen).label("max_last_seen"))
            .filter(EVSEStatus.charge_point_id.in_(cp_ids))
            .group_by(EVSEStatus.charge_point_id)
            .subquery()
        )
        latest_rows = (
            db.query(EVSEStatus)
            .join(
                latest_sq,
                (EVSEStatus.charge_point_id == latest_sq.c.cp_id)
                & (EVSEStatus.last_seen == latest_sq.c.max_last_seen),
            )
            .all()
        )
        for r in latest_rows:
            status_map[r.charge_point_id] = {
                "status": r.status or "Unknown",
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            }

    result: List[SiteDetailChargePoint] = []
    for cp in cps:
        st = status_map.get(cp.id) or {"status": "Unknown", "last_seen": None}
        # 这里拿不到 join 的 Site 实例（因为 cp.site 关系可用）
        curr_site = cp.site
        result.append(
            SiteDetailChargePoint(
                id=str(cp.id),
                ocpp_identity=cp.ocpp_identity,
                display_code=cp.display_code,
                display_name=cp.display_name,
                location_hint=cp.location_hint,
                vendor=cp.vendor,
                model=cp.model,
                status=st["status"],
                last_seen=st["last_seen"],
                site_id=str(cp.site_id),
                site_name=curr_site.name if curr_site else None,
            )
        )
    return result


class BindChargePointsRequest(StrictRequestModel):
    charge_point_ids: List[str] = Field(..., min_length=1, max_length=200)
    force_move: bool = False
    reason: Optional[str] = Field(None, max_length=500)

    @field_validator("charge_point_ids", mode="before")
    @classmethod
    def normalize_charge_point_ids(cls, value):
        if not isinstance(value, list):
            return value
        normalized = [str(item).strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("charge_point_ids must not contain blank values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("charge_point_ids must be unique")
        return normalized


@router.post("/{site_id}/bind-charge-points", summary="绑定/迁移充电桩到站点")
def bind_charge_points(
    site_id: str,
    req: BindChargePointsRequest,
    current_user_obj=Depends(require_permission("sites.write")),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    target_site = _get_scoped_site(db, site_id, current_user_obj)
    if target_site.is_active is not True:
        raise _coded_http_exception(
            409,
            "charger_move_blocked",
            "Charge points can only be moved to an active site",
            blockers=[
                {"type": "target_site_archived", "resource_id": str(target_site.id)}
            ],
        )
    reason = _normalized_reason(req.reason or "Charge point moved between sites")

    # 读取 charge points（按租户约束）
    cps = []
    missing = []
    for reference in req.charge_point_ids:
        cp = get_charge_point_by_reference(db, reference)
        if cp is None:
            missing.append(reference)
        else:
            cps.append(cp)
    if missing:
        raise _coded_http_exception(
            404,
            "charge_point_not_found",
            "Charge points not found",
            missing=missing,
        )

    # 跨租户保护：即使 super_admin，也禁止把不同 tenant 的 CP 绑到该站点
    conflicts_tenant = [cp.ocpp_identity for cp in cps if cp.tenant_id != target_site.tenant_id]
    if conflicts_tenant:
        raise _coded_http_exception(
            403,
            "charge_point_tenant_mismatch",
            "Charge point belongs to another tenant",
            conflicts=conflicts_tenant,
        )

    to_move = [cp for cp in cps if cp.site_id != target_site.id]
    if to_move and not req.force_move:
        raise _coded_http_exception(
            409,
            "charger_move_blocked",
            "Set force_move=true to confirm moving charge points from another site",
            blockers=[
                {
                    "type": "move_confirmation_required",
                    "resource_id": str(cp.id),
                    "ocpp_identity": cp.ocpp_identity,
                }
                for cp in to_move
            ],
        )

    blockers = []
    for cp in to_move:
        for blocker in _charge_point_move_blockers(db, cp):
            blockers.append(
                {
                    **blocker,
                    "charge_point_id": str(cp.id),
                    "ocpp_identity": cp.ocpp_identity,
                }
            )
    if blockers:
        raise _coded_http_exception(
            409,
            "charger_move_blocked",
            "One or more charge points have lifecycle or business history blockers",
            blockers=blockers,
        )

    moved_ids = [str(cp.id) for cp in to_move]
    unchanged_ids = [str(cp.id) for cp in cps if cp.site_id == target_site.id]
    # 所有设备通过预检后再统一修改，保证批量迁移原子性。
    for cp in to_move:
        source_site = cp.site
        before_data = {
            "site_id": str(cp.site_id),
            "site_code": source_site.site_code if source_site else None,
            "site_name": source_site.name if source_site else None,
        }
        cp.site_id = target_site.id
        add_lifecycle_audit(
            db,
            tenant_id=cp.tenant_id,
            actor_id=current_user_obj.id,
            action=CHARGER_MOVE_ACTION,
            resource_type="charge_point",
            resource_id=str(cp.id),
            reason=reason,
            before_data=before_data,
            after_data={
                "site_id": str(target_site.id),
                "site_code": target_site.site_code,
                "site_name": target_site.name,
            },
        )

    db.commit()
    return {
        "success": True,
        "site_id": str(target_site.id),
        "bound": [str(cp.id) for cp in cps],
        "moved": moved_ids,
        "unchanged": unchanged_ids,
    }


class CreateChargePointInSiteRequest(StrictRequestModel):
    """在站点下创建并预注册充电桩（用于 web 端录入硬件码）"""

    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$", description="OCPP identity（硬件码）")
    display_code: str = Field(..., min_length=1, max_length=16, pattern=r"^[A-Z][A-Z0-9-]{0,15}$")
    display_name: Optional[str] = Field(None, max_length=80)
    location_hint: Optional[str] = Field(None, max_length=160)
    vendor: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    connector_count: int = Field(1, ge=1, le=16, description="枪口数量/EVSE 数量")
    connector_type: Literal[
        "Type2", "CCS1", "CCS2", "CHAdeMO", "NACS", "GB_T_AC", "GB_T_DC"
    ] = Field("Type2", description="连接器类型（默认 Type2）")
    evses: Optional[List["EVSEProvisioningRequest"]] = None

    @field_validator("display_code", mode="before")
    @classmethod
    def normalize_display_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("display_name", "location_hint", mode="before")
    @classmethod
    def normalize_optional_label(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_evses(self):
        if self.evses:
            ids = [item.evse_id for item in self.evses]
            references = [item.physical_reference for item in self.evses]
            if len(ids) != len(set(ids)):
                raise ValueError("EVSE IDs must be unique")
            if len(references) != len(set(references)):
                raise ValueError("EVSE physical references must be unique")
        return self


class EVSEProvisioningRequest(StrictRequestModel):
    evse_id: int = Field(..., ge=1, le=16)
    physical_reference: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    connector_type: Literal[
        "Type2", "CCS1", "CCS2", "CHAdeMO", "NACS", "GB_T_AC", "GB_T_DC"
    ]
    max_power_kw: float = Field(..., gt=0, le=1000, allow_inf_nan=False)


CreateChargePointInSiteRequest.model_rebuild()


@router.post("/{site_id}/charge-points", summary="在站点下创建充电桩（预注册）", status_code=201)
def create_charge_point_in_site(
    site_id: str,
    req: CreateChargePointInSiteRequest,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")

    site = _get_scoped_site(db, site_id, current_user_obj)
    if site.is_active is not True:
        raise _coded_http_exception(
            409,
            "site_not_operational",
            "Cannot provision a charge point under an archived site",
        )

    # 确保 CP ID 合法（与 ws 严格模式一致）
    cp_id = (req.id or "").strip()
    existing = db.query(ChargePoint).filter(ChargePoint.ocpp_identity == cp_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Charge point already exists")
    duplicate_display_code = db.query(ChargePoint.id).filter(
        ChargePoint.site_id == site.id,
        ChargePoint.display_code == req.display_code,
    ).first()
    if duplicate_display_code:
        raise HTTPException(status_code=409, detail="Display code already exists in this site")

    # 创建 ChargePoint（直接绑定到站点）
    from app.core.ocpp_auth import generate_ocpp_secret, hash_ocpp_secret
    ocpp_secret = generate_ocpp_secret()
    charge_point = ChargePoint(
        ocpp_identity=cp_id,
        tenant_id=site.tenant_id,
        site_id=site.id,
        display_code=req.display_code,
        display_name=req.display_name,
        location_hint=req.location_hint,
        vendor=req.vendor,
        model=req.model,
        ocpp_auth_secret_hash=hash_ocpp_secret(ocpp_secret),
        commissioning_status="draft",
        is_active=True,
    )
    db.add(charge_point)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Charge point identity or display code already exists",
        ) from exc

    # 创建 EVSE + EVSEStatus
    evse_specs = req.evses or [
        EVSEProvisioningRequest(
            evse_id=evse_no,
            physical_reference=f"{req.display_code}-{evse_no}",
            connector_type=req.connector_type or "Type2",
            max_power_kw=7.0,
        )
        for evse_no in range(1, int(req.connector_count) + 1)
    ]
    for spec in evse_specs:
        evse = EVSE(
            tenant_id=site.tenant_id,
            charge_point_id=charge_point.id,
            evse_id=spec.evse_id,
            connector_type=spec.connector_type,
            max_power_kw=spec.max_power_kw,
            physical_reference=spec.physical_reference,
        )
        db.add(evse)
        db.flush()

        evse_status = EVSEStatus(
            tenant_id=site.tenant_id,
            evse_id=evse.id,
            charge_point_id=charge_point.id,
            status="Unknown",
            last_seen=datetime.now(timezone.utc),
        )
        db.add(evse_status)

    db.commit()

    # 为每个connector生成二维码（爆改：token-only）
    qr_urls = []
    try:
        from app.services.qr_service import generate_qr_code, get_qr_code_url, get_qr_storage_dir, ensure_qr_token
        qr_storage_dir = get_qr_storage_dir()
        
        for spec in evse_specs:
            evse_no = spec.evse_id
            try:
                generate_qr_code(
                    db=db,
                    charge_point_id=charge_point.id,
                    connector_id=evse_no,
                    output_dir=qr_storage_dir,
                )
                token_rec = ensure_qr_token(db, charge_point.id, evse_no)
                qr_url = get_qr_code_url(str(charge_point.id), evse_no)
                qr_urls.append({
                    "connector_id": evse_no,
                    "qr_token": token_rec.token,
                    "qr_url": qr_url,
                    "filename": f"{cp_id}_connector_{evse_no}.png"
                })
            except Exception as e:
                logger.warning(f"生成充电桩 {cp_id} connector {evse_no} 的二维码失败: {e}")
    except Exception as e:
        logger.error(f"生成二维码时出错: {e}", exc_info=True)
        # 二维码生成失败不影响充电桩创建

    return {
        "id": str(charge_point.id),
        "ocpp_identity": charge_point.ocpp_identity,
        "display_code": charge_point.display_code,
        "display_name": charge_point.display_name,
        "location_hint": charge_point.location_hint,
        "site_id": str(site.id),
        "tenant_id": str(site.tenant_id),
        "vendor": charge_point.vendor,
        "model": charge_point.model,
        "connector_count": len(evse_specs),
        "evses": [item.model_dump() for item in evse_specs],
        "commissioning_status": charge_point.commissioning_status,
        "ocpp_credentials": {
            "username": charge_point.ocpp_identity,
            "secret": ocpp_secret,
            "query_url": f"/ocpp?id={charge_point.ocpp_identity}",
            "path_url": f"/ocpp/{charge_point.ocpp_identity}",
        },
        "qr_codes": qr_urls,  # 二维码URL列表
    }
