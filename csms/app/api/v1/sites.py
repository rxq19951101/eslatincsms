#
# 站点管理 API
# 以站点（Site）为核心：CRUD + 站点详情聚合 + 绑定/迁移充电桩
#

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.id_generator import generate_site_id
from app.core.logging_config import get_logger
from app.core.permissions import get_current_admin_user
from app.database.base import get_db, tenant_id_context
from app.database.models import ChargePoint, EVSE, EVSEStatus, Site, Tariff
from datetime import datetime, timezone
from app.core.permissions import has_permission
from app.services.role_service import MembershipRoleService

logger = get_logger("ocpp_csms")

router = APIRouter()


class SiteCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    address: str = Field(..., min_length=1)
    latitude: float
    longitude: float
    is_active: bool = True
    operating_hours: Optional[str] = None
    domain: Optional[str] = None  # 预留字段（与 tenants.domain 区分，仅做展示/过滤用途）


class SiteUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    address: Optional[str] = Field(None, min_length=1)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = None
    operating_hours: Optional[str] = None
    domain: Optional[str] = None


class SiteListItem(BaseModel):
    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    is_active: bool
    operating_hours: Optional[str]
    domain: Optional[str]
    charge_points_count: int
    online_charge_points_count: int
    created_at: str
    updated_at: str


class SiteDetailChargePoint(BaseModel):
    id: str
    vendor: Optional[str]
    model: Optional[str]
    status: str
    last_seen: Optional[str]
    site_id: str
    site_name: Optional[str] = None


class SiteDetailResponse(BaseModel):
    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    is_active: bool
    operating_hours: Optional[str]
    domain: Optional[str]
    price_per_kwh: Optional[float] = None
    charge_points: List[SiteDetailChargePoint]
    created_at: str
    updated_at: str


class SitePricingUpdateRequest(BaseModel):
    """站点级基础电价（作为默认价）"""

    base_price_per_kwh: float = Field(..., gt=0, description="基础电价（每kWh）")
    service_fee: Optional[float] = Field(None, ge=0, description="服务费（可选）")


class SitePricingResponse(BaseModel):
    site_id: str
    tariff_id: int
    base_price_per_kwh: float
    service_fee: float
    valid_from: str


def _require_tenant_id_for_create(current_user_obj) -> Optional[str]:
    """
    站点是租户级资产：创建时必须明确 tenant_id。
    非 super_admin 必须依赖 tenant middleware 注入；super_admin 也建议显式传 X-Tenant-Id。
    """
    tenant_id = tenant_id_context.get()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID required")
    return str(tenant_id)


@router.get("", response_model=List[SiteListItem], summary="获取站点列表")
def list_sites(
    q: Optional[str] = Query(None, description="搜索：站点名称/地址/ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    include_inactive: bool = Query(True, description="是否包含未启用站点"),
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> List[SiteListItem]:
    tenant_id = tenant_id_context.get()

    base = db.query(Site)
    if tenant_id and not current_user_obj.is_super_admin:
        base = base.filter(Site.tenant_id == tenant_id)

    if not include_inactive:
        base = base.filter(Site.is_active == True)  # noqa: E712

    if q:
        like = f"%{q.strip()}%"
        base = base.filter(or_(Site.id.ilike(like), Site.name.ilike(like), Site.address.ilike(like)))

    # 统计：每站点的充电桩数量
    cp_count_sq = (
        db.query(ChargePoint.site_id.label("site_id"), func.count(ChargePoint.id).label("cp_count"))
        .group_by(ChargePoint.site_id)
        .subquery()
    )
    # 统计：每站点的“在线”充电桩数量（近似：存在任一 EVSEStatus 且 status != Unavailable）
    online_cp_sq = (
        db.query(
            ChargePoint.site_id.label("site_id"),
            func.count(func.distinct(ChargePoint.id)).label("online_cp_count"),
        )
        .join(EVSEStatus, EVSEStatus.charge_point_id == ChargePoint.id)
        .filter(EVSEStatus.status != "Unavailable")
        .group_by(ChargePoint.site_id)
        .subquery()
    )

    rows = (
        base.outerjoin(cp_count_sq, cp_count_sq.c.site_id == Site.id)
        .outerjoin(online_cp_sq, online_cp_sq.c.site_id == Site.id)
        .order_by(Site.created_at.desc())
        .offset(skip)
        .limit(limit)
        .with_entities(Site, cp_count_sq.c.cp_count, online_cp_sq.c.online_cp_count)
        .all()
    )

    result: List[SiteListItem] = []
    for site, cp_count, online_cp_count in rows:
        # domain 目前不在 Site 表中；为了不影响 DB schema，这里仅从 settings/operating_hours 等扩展字段不读取。
        result.append(
            SiteListItem(
                id=site.id,
                name=site.name,
                address=site.address,
                latitude=site.latitude,
                longitude=site.longitude,
                is_active=bool(site.is_active),
                operating_hours=site.operating_hours,
                domain=None,
                charge_points_count=int(cp_count or 0),
                online_charge_points_count=int(online_cp_count or 0),
                created_at=site.created_at.isoformat() if site.created_at else "",
                updated_at=site.updated_at.isoformat() if site.updated_at else "",
            )
        )
    return result


@router.post("", response_model=SiteDetailResponse, summary="创建站点", status_code=201)
def create_site(
    req: SiteCreateRequest,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> SiteDetailResponse:
    _require_tenant_id_for_create(current_user_obj)
    tenant_id = tenant_id_context.get()
    assert tenant_id is not None

    site_id = generate_site_id(req.name)
    site = Site(
        id=site_id,
        tenant_id=tenant_id,
        name=req.name,
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude,
        is_active=req.is_active,
        operating_hours=req.operating_hours,
    )
    db.add(site)
    db.commit()
    db.refresh(site)

    return SiteDetailResponse(
        id=site.id,
        name=site.name,
        address=site.address,
        latitude=site.latitude,
        longitude=site.longitude,
        is_active=bool(site.is_active),
        operating_hours=site.operating_hours,
        domain=None,
        price_per_kwh=None,
        charge_points=[],
        created_at=site.created_at.isoformat() if site.created_at else "",
        updated_at=site.updated_at.isoformat() if site.updated_at else "",
    )


@router.get("/{site_id}", response_model=SiteDetailResponse, summary="获取站点详情（含站点下充电桩）")
def get_site_detail(
    site_id: str = Path(..., description="站点ID"),
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> SiteDetailResponse:
    tenant_id = tenant_id_context.get()
    q = db.query(Site).filter(Site.id == site_id)
    if tenant_id and not current_user_obj.is_super_admin:
        q = q.filter(Site.tenant_id == tenant_id)
    site = q.first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

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

    cps = db.query(ChargePoint).filter(ChargePoint.site_id == site.id).all()
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
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            }

    charge_points: List[SiteDetailChargePoint] = []
    for cp in cps:
        st = status_map.get(cp.id) or {"status": "Unknown", "last_seen": None}
        charge_points.append(
            SiteDetailChargePoint(
                id=cp.id,
                vendor=cp.vendor,
                model=cp.model,
                status=st["status"],
                last_seen=st["last_seen"],
                site_id=site.id,
                site_name=site.name,
            )
        )

    return SiteDetailResponse(
        id=site.id,
        name=site.name,
        address=site.address,
        latitude=site.latitude,
        longitude=site.longitude,
        is_active=bool(site.is_active),
        operating_hours=site.operating_hours,
        domain=None,
        price_per_kwh=float(tariff.base_price_per_kwh) if tariff else None,
        charge_points=charge_points,
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
    tenant_id = tenant_id_context.get()
    q = db.query(Site).filter(Site.id == site_id)
    if tenant_id and not current_user_obj.is_super_admin:
        q = q.filter(Site.tenant_id == tenant_id)
    site = q.first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if req.name is not None:
        site.name = req.name
    if req.address is not None:
        site.address = req.address
    if req.latitude is not None:
        site.latitude = req.latitude
    if req.longitude is not None:
        site.longitude = req.longitude
    if req.is_active is not None:
        site.is_active = req.is_active
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

    q = db.query(Site).filter(Site.id == site_id)
    if tenant_id and not current_user_obj.is_super_admin:
        q = q.filter(Site.tenant_id == tenant_id)
    site = q.first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

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
        site_id=site.id,
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
        site_id=site.id,
        tariff_id=new_tariff.id,
        base_price_per_kwh=float(new_tariff.base_price_per_kwh),
        service_fee=float(new_tariff.service_fee or 0),
        valid_from=new_tariff.valid_from.isoformat() if new_tariff.valid_from else "",
    )


@router.delete("/{site_id}", summary="删除站点")
def delete_site(
    site_id: str,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    tenant_id = tenant_id_context.get()
    q = db.query(Site).filter(Site.id == site_id)
    if tenant_id and not current_user_obj.is_super_admin:
        q = q.filter(Site.tenant_id == tenant_id)
    site = q.first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    cp_count = db.query(func.count(ChargePoint.id)).filter(ChargePoint.site_id == site.id).scalar() or 0
    if cp_count > 0:
        raise HTTPException(status_code=400, detail="Site has charge points, cannot delete")

    db.delete(site)
    db.commit()
    return {"message": "Site deleted successfully"}


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
    site_q = db.query(Site).filter(Site.id == site_id)
    if tenant_id and not current_user_obj.is_super_admin:
        site_q = site_q.filter(Site.tenant_id == tenant_id)
    target_site = site_q.first()
    if not target_site:
        raise HTTPException(status_code=404, detail="Site not found")

    cp_q = db.query(ChargePoint).join(Site, Site.id == ChargePoint.site_id)
    if tenant_id and not current_user_obj.is_super_admin:
        cp_q = cp_q.filter(ChargePoint.tenant_id == tenant_id)

    # 排除已经属于目标站点的
    cp_q = cp_q.filter(ChargePoint.site_id != site_id)

    auto_site_rule = or_(
        Site.name == func.concat("站点-", ChargePoint.id),
        Site.id == func.concat("site-", ChargePoint.id),
    )
    cps = cp_q.filter(auto_site_rule).all()

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
                id=cp.id,
                vendor=cp.vendor,
                model=cp.model,
                status=st["status"],
                last_seen=st["last_seen"],
                site_id=cp.site_id,
                site_name=curr_site.name if curr_site else None,
            )
        )
    return result


class BindChargePointsRequest(BaseModel):
    charge_point_ids: List[str] = Field(..., min_length=1)
    force_move: bool = False


@router.post("/{site_id}/bind-charge-points", summary="绑定/迁移充电桩到站点")
def bind_charge_points(
    site_id: str,
    req: BindChargePointsRequest,
    current_user_obj=Depends(get_current_admin_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    tenant_id = tenant_id_context.get()

    site_q = db.query(Site).filter(Site.id == site_id)
    if tenant_id and not current_user_obj.is_super_admin:
        site_q = site_q.filter(Site.tenant_id == tenant_id)
    target_site = site_q.first()
    if not target_site:
        raise HTTPException(status_code=404, detail="Site not found")

    # 读取 charge points（按租户约束）
    cp_q = db.query(ChargePoint).filter(ChargePoint.id.in_(req.charge_point_ids))
    if tenant_id and not current_user_obj.is_super_admin:
        cp_q = cp_q.filter(ChargePoint.tenant_id == tenant_id)
    cps = cp_q.all()
    found_ids = {cp.id for cp in cps}
    missing = [cp_id for cp_id in req.charge_point_ids if cp_id not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail={"message": "Charge points not found", "missing": missing})

    # 跨租户保护：即使 super_admin，也禁止把不同 tenant 的 CP 绑到该站点
    conflicts_tenant = [cp.id for cp in cps if str(cp.tenant_id) != str(target_site.tenant_id)]
    if conflicts_tenant:
        raise HTTPException(
            status_code=400,
            detail={"message": "Tenant mismatch between site and charge points", "conflicts": conflicts_tenant},
        )

    # 冲突：已经在其他站点
    move_conflicts = [cp.id for cp in cps if cp.site_id != site_id]
    if move_conflicts and not req.force_move:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Some charge points already belong to another site. Set force_move=true to move.",
                "conflicts": move_conflicts,
            },
        )

    # 执行绑定/迁移
    for cp in cps:
        cp.site_id = site_id

    db.commit()
    return {"success": True, "site_id": site_id, "bound": [cp.id for cp in cps]}


class CreateChargePointInSiteRequest(BaseModel):
    """在站点下创建并预注册充电桩（用于 web 端录入硬件码）"""

    id: str = Field(..., min_length=1, description="charge_point_id（硬件码）")
    vendor: Optional[str] = None
    model: Optional[str] = None
    connector_count: int = Field(1, ge=1, le=16, description="枪口数量/EVSE 数量")
    connector_type: str = Field("Type2", description="连接器类型（默认 Type2）")


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

    site_q = db.query(Site).filter(Site.id == site_id)
    if tenant_id and not current_user_obj.is_super_admin:
        site_q = site_q.filter(Site.tenant_id == tenant_id)
    site = site_q.first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # 确保 CP ID 合法（与 ws 严格模式一致）
    cp_id = (req.id or "").strip()
    if not cp_id or not cp_id.isalnum():
        raise HTTPException(status_code=400, detail="charge_point_id must be alphanumeric")

    existing = db.query(ChargePoint).filter(ChargePoint.id == cp_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Charge point already exists")

    # 创建 ChargePoint（直接绑定到站点）
    charge_point = ChargePoint(
        id=cp_id,
        tenant_id=site.tenant_id,
        site_id=site.id,
        vendor=req.vendor,
        model=req.model,
        is_active=True,
    )
    db.add(charge_point)
    db.flush()

    # 创建 EVSE + EVSEStatus
    for evse_no in range(1, int(req.connector_count) + 1):
        evse = EVSE(
            tenant_id=site.tenant_id,
            charge_point_id=cp_id,
            evse_id=evse_no,
            connector_type=req.connector_type or "Type2",
        )
        db.add(evse)
        db.flush()

        evse_status = EVSEStatus(
            tenant_id=site.tenant_id,
            evse_id=evse.id,
            charge_point_id=cp_id,
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
        
        for evse_no in range(1, int(req.connector_count) + 1):
            try:
                generate_qr_code(
                    db=db,
                    charge_point_id=cp_id,
                    connector_id=evse_no,
                    output_dir=qr_storage_dir,
                )
                token_rec = ensure_qr_token(db, cp_id, evse_no)
                qr_url = get_qr_code_url(cp_id, evse_no)
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
        "id": charge_point.id,
        "site_id": site.id,
        "tenant_id": str(site.tenant_id),
        "vendor": charge_point.vendor,
        "model": charge_point.model,
        "connector_count": int(req.connector_count),
        "connector_type": req.connector_type,
        "qr_codes": qr_urls,  # 二维码URL列表
    }

