"""Saved public charging sites for platform App users."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.app.chargers import get_current_app_user, get_public_charge_point_db
from app.api.v1.app.sites import _load_site_assets, _site_payload
from app.database.models import AppUser, AppUserFavoriteSite, Site


router = APIRouter()


@router.get("", summary="获取当前用户收藏的公开站点")
async def list_favorite_sites(
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_public_charge_point_db),
) -> list[dict]:
    rows = db.query(AppUserFavoriteSite).join(
        Site,
        AppUserFavoriteSite.site_id == Site.id,
    ).filter(
        AppUserFavoriteSite.app_user_id == current_user_obj.id,
        Site.is_active.is_(True),
    ).order_by(AppUserFavoriteSite.created_at.desc()).all()
    sites = [row.site for row in rows]
    charge_points_by_site, evses_by_cp, status_by_evse, tariff_by_site = _load_site_assets(db, sites)
    now = datetime.now(timezone.utc)
    result = []
    for site in sites:
        payload = _site_payload(
            site,
            charge_points_by_site.get(site.id, []),
            evses_by_cp,
            status_by_evse,
            tariff_by_site.get(site.id),
            now,
        )
        payload["is_favorite"] = True
        result.append(payload)
    return result


@router.put("/{site_id}", summary="收藏公开站点")
async def save_favorite_site(
    site_id: UUID,
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_public_charge_point_db),
) -> dict:
    site = db.query(Site).filter(Site.id == site_id, Site.is_active.is_(True)).first()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    existing = db.query(AppUserFavoriteSite.id).filter(
        AppUserFavoriteSite.app_user_id == current_user_obj.id,
        AppUserFavoriteSite.site_id == site_id,
    ).first()
    if existing is None:
        db.add(AppUserFavoriteSite(app_user_id=current_user_obj.id, site_id=site_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return {"site_id": str(site_id), "is_favorite": True}


@router.delete("/{site_id}", summary="取消收藏公开站点")
async def remove_favorite_site(
    site_id: UUID,
    current_user_obj: AppUser = Depends(get_current_app_user),
    db: Session = Depends(get_public_charge_point_db),
) -> dict:
    db.query(AppUserFavoriteSite).filter(
        AppUserFavoriteSite.app_user_id == current_user_obj.id,
        AppUserFavoriteSite.site_id == site_id,
    ).delete(synchronize_session=False)
    db.commit()
    return {"site_id": str(site_id), "is_favorite": False}
