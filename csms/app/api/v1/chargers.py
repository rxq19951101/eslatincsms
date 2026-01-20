#
# 充电桩管理API
# 提供充电桩的CRUD操作（使用新表结构）
#

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.database.base import get_db, tenant_id_context
from app.database.models import ChargePoint, Site, EVSE, EVSEStatus, Tariff, QrToken
from app.core.logging_config import get_logger
from app.core.permissions import get_current_admin_user
from app.core.permissions import has_permission
from app.services.role_service import MembershipRoleService
from datetime import datetime, timezone

logger = get_logger("ocpp_csms")

router = APIRouter()


class CreateChargerRequest(BaseModel):
    id: str
    vendor: Optional[str] = None
    model: Optional[str] = None
    site_id: Optional[str] = None


class ChargerPricingUpdateRequest(BaseModel):
    """充电桩级覆盖价（优先于站点默认价）"""

    base_price_per_kwh: float
    service_fee: Optional[float] = None


class ChargerPricingResponse(BaseModel):
    charge_point_id: str
    tariff_id: int
    base_price_per_kwh: float
    service_fee: float
    valid_from: str


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
    
    query = db.query(ChargePoint)
    
    # 添加租户过滤（如果不是超级管理员）
    if tenant_id and not current_user_obj.is_super_admin:
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
        status = evse_status.status if evse_status else "Unknown"
        last_seen = evse_status.last_seen if evse_status else None
        
        is_configured = has_location and has_pricing
        
        result.append({
            "id": cp.id,
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
    
    tenant_id = tenant_id_context.get()
    query = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id)
    if tenant_id and not current_user_obj.is_super_admin:
        query = query.filter(ChargePoint.tenant_id == tenant_id)
    
    charge_point = query.first()
    if not charge_point:
        logger.warning(f"[API] GET /api/v1/chargers/{charge_point_id} | 充电桩未找到")
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
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
    status = evse_status.status if evse_status else "Unknown"
    last_seen = evse_status.last_seen if evse_status else None
    
    # 获取EVSE列表（包含 connector_type）
    evses = db.query(EVSE).filter(EVSE.charge_point_id == charge_point.id).all()
    evse_list = []
    default_connector_type = "Type2"  # 默认值
    for evse in evses:
        evse_status_item = db.query(EVSEStatus).filter(EVSEStatus.evse_id == evse.id).first()
        evse_list.append({
            "evse_id": evse.evse_id,
            "connector_type": evse.connector_type,  # 从 EVSE 获取 connector_type
            "max_power_kw": evse.max_power_kw,
            "status": evse_status_item.status if evse_status_item else "Unknown",
            "last_seen": evse_status_item.last_seen.isoformat() if evse_status_item and evse_status_item.last_seen else None,
        })
        # 使用第一个 EVSE 的 connector_type 作为默认值（向后兼容）
        if evse.evse_id == 1:
            default_connector_type = evse.connector_type
    
    return {
        "id": charge_point.id,
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
    query = db.query(ChargePoint).filter(ChargePoint.id == req.id)
    if tenant_id and not current_user_obj.is_super_admin:
        query = query.filter(ChargePoint.tenant_id == tenant_id)
    
    existing = query.first()
    if existing:
        logger.warning(f"[API] POST /api/v1/chargers | 充电桩 {req.id} 已存在")
        raise HTTPException(status_code=400, detail=f"充电桩 {req.id} 已存在")
    
    # 创建新充电桩
    charge_point = ChargePoint(
        id=req.id,
        tenant_id=tenant_id,
        vendor=req.vendor,
        model=req.model,
        site_id=req.site_id,
        is_active=True
    )
    db.add(charge_point)
    db.commit()
    db.refresh(charge_point)
    
    # 为已存在的EVSE生成二维码（爆改：token-only）
    qr_urls = []
    try:
        from app.services.qr_service import generate_qr_code, get_qr_code_url, get_qr_storage_dir, ensure_qr_token
        qr_storage_dir = get_qr_storage_dir()
        
        # 查询该充电桩的所有EVSE
        evses = db.query(EVSE).filter(EVSE.charge_point_id == req.id).all()
        for evse in evses:
            try:
                generate_qr_code(
                    db=db,
                    charge_point_id=req.id,
                    connector_id=evse.evse_id,
                    output_dir=qr_storage_dir,
                )
                token_rec = ensure_qr_token(db, req.id, evse.evse_id)
                qr_url = get_qr_code_url(req.id, evse.evse_id)
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
        "id": charge_point.id,
        "vendor": charge_point.vendor,
        "model": charge_point.model,
        "site_id": charge_point.site_id,
        "is_active": charge_point.is_active,
        "qr_codes": qr_urls,  # 二维码URL列表（如果有EVSE）
    }


class UpdateChargerRequest(BaseModel):
    vendor: Optional[str] = None
    model: Optional[str] = None


@router.put("/{charge_point_id}", summary="更新充电桩")
def update_charger(
    charge_point_id: str,
    req: UpdateChargerRequest,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> dict:
    """更新充电桩信息"""
    logger.info(f"[API] PUT /api/v1/chargers/{charge_point_id}")
    
    tenant_id = tenant_id_context.get()
    query = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id)
    if tenant_id and not current_user_obj.is_super_admin:
        query = query.filter(ChargePoint.tenant_id == tenant_id)
    
    charge_point = query.first()
    if not charge_point:
        logger.warning(f"[API] PUT /api/v1/chargers/{charge_point_id} | 充电桩未找到")
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    if req.vendor is not None:
        charge_point.vendor = req.vendor
    if req.model is not None:
        charge_point.model = req.model
    
    db.commit()
    db.refresh(charge_point)
    
    logger.info(f"[API] PUT /api/v1/chargers/{charge_point_id} 成功")
    return {
        "id": charge_point.id,
        "vendor": charge_point.vendor,
        "model": charge_point.model,
    }


@router.delete("/{charge_point_id}", summary="删除充电桩", status_code=200)
def delete_charger(
    charge_point_id: str,
    current_user_obj = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
) -> dict:
    """删除充电桩"""
    logger.info(f"[API] DELETE /api/v1/chargers/{charge_point_id}")
    
    tenant_id = tenant_id_context.get()
    query = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id)
    if tenant_id and not current_user_obj.is_super_admin:
        query = query.filter(ChargePoint.tenant_id == tenant_id)
    
    charge_point = query.first()
    if not charge_point:
        logger.warning(f"[API] DELETE /api/v1/chargers/{charge_point_id} | 充电桩未找到")
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    db.delete(charge_point)
    db.commit()
    
    logger.info(f"[API] DELETE /api/v1/chargers/{charge_point_id} 成功")
    return {"message": f"充电桩 {charge_point_id} 已删除"}


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

    q = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id)
    if tenant_id and not current_user_obj.is_super_admin:
        q = q.filter(ChargePoint.tenant_id == tenant_id)
    cp = q.first()
    if not cp:
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")

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
        name=f"充电桩覆盖定价-{cp.id}",
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
        charge_point_id=cp.id,
        tariff_id=new_tariff.id,
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
    tenant_id = tenant_id_context.get()
    query = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id)
    if tenant_id and not current_user_obj.is_super_admin:
        query = query.filter(ChargePoint.tenant_id == tenant_id)
    
    charge_point = query.first()
    if not charge_point:
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    # 查询所有EVSE
    evses = db.query(EVSE).filter(EVSE.charge_point_id == charge_point_id).order_by(EVSE.evse_id).all()
    
    from app.services.qr_service import get_qr_code_url, get_qr_code_path, get_qr_storage_dir
    
    qr_storage_dir = get_qr_storage_dir()
    qr_list = []
    
    for evse in evses:
        qr_path = get_qr_code_path(charge_point_id, evse.evse_id, qr_storage_dir)
        qr_url = get_qr_code_url(charge_point_id, evse.evse_id)
        
        # 检查文件是否存在
        exists = qr_path.exists()
        token_rec = (
            db.query(QrToken)
            .filter(
                QrToken.charge_point_id == charge_point_id,
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
        "charge_point_id": charge_point_id,
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
    tenant_id = tenant_id_context.get()
    query = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id)
    if tenant_id and not current_user_obj.is_super_admin:
        query = query.filter(ChargePoint.tenant_id == tenant_id)
    
    charge_point = query.first()
    if not charge_point:
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    # 验证connector是否存在
    evse = db.query(EVSE).filter(
        EVSE.charge_point_id == charge_point_id,
        EVSE.evse_id == connector_id
    ).first()
    
    if not evse:
        raise HTTPException(status_code=404, detail=f"Connector {connector_id} 未找到")
    
    from app.services.qr_service import get_qr_code_url, get_qr_code_path, get_qr_storage_dir, build_qr_payload
    
    qr_storage_dir = get_qr_storage_dir()
    qr_path = get_qr_code_path(charge_point_id, connector_id, qr_storage_dir)
    qr_url = get_qr_code_url(charge_point_id, connector_id)
    token_rec = (
        db.query(QrToken)
        .filter(
            QrToken.charge_point_id == charge_point_id,
            QrToken.connector_id == connector_id,
            QrToken.revoked_at.is_(None),
        )
        .first()
    )
    payload = build_qr_payload(token_rec.token) if token_rec else None
    
    return {
        "charge_point_id": charge_point_id,
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
    tenant_id = tenant_id_context.get()
    query = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id)
    if tenant_id and not current_user_obj.is_super_admin:
        query = query.filter(ChargePoint.tenant_id == tenant_id)
    
    charge_point = query.first()
    if not charge_point:
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    # 验证connector是否存在
    evse = db.query(EVSE).filter(
        EVSE.charge_point_id == charge_point_id,
        EVSE.evse_id == connector_id
    ).first()
    
    if not evse:
        raise HTTPException(status_code=404, detail=f"Connector {connector_id} 未找到")
    
    from app.services.qr_service import generate_qr_code, get_qr_code_url, get_qr_storage_dir, ensure_qr_token
    
    try:
        qr_storage_dir = get_qr_storage_dir()
        qr_path = generate_qr_code(
            db=db,
            charge_point_id=charge_point_id,
            connector_id=connector_id,
            output_dir=qr_storage_dir,
        )
        token_rec = ensure_qr_token(db, charge_point_id, connector_id)
        qr_url = get_qr_code_url(charge_point_id, connector_id)
        
        logger.info(f"[API] 成功生成二维码: {charge_point_id} connector {connector_id} -> {qr_path}")
        
        return {
            "charge_point_id": charge_point_id,
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
    tenant_id = tenant_id_context.get()
    query = db.query(ChargePoint).filter(ChargePoint.id == charge_point_id)
    if tenant_id and not current_user_obj.is_super_admin:
        query = query.filter(ChargePoint.tenant_id == tenant_id)
    
    charge_point = query.first()
    if not charge_point:
        raise HTTPException(status_code=404, detail=f"充电桩 {charge_point_id} 未找到")
    
    # 查询所有EVSE
    evses = db.query(EVSE).filter(EVSE.charge_point_id == charge_point_id).order_by(EVSE.evse_id).all()
    
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
                charge_point_id=charge_point_id,
                connector_id=evse.evse_id,
                output_dir=qr_storage_dir,
            )
            token_rec = ensure_qr_token(db, charge_point_id, evse.evse_id)
            qr_url = get_qr_code_url(charge_point_id, evse.evse_id)
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
        "charge_point_id": charge_point_id,
        "generated": results,
        "errors": errors,
        "total": len(evses),
        "success_count": len(results),
        "error_count": len(errors),
    }

