"""Helpers for keeping database identifiers separate from public asset references."""

from __future__ import annotations

import re
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.models import ChargePoint, Site


OCPP_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def parse_uuid(value: object) -> Optional[UUID]:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def get_charge_point_by_internal_id(db: Session, internal_id: object) -> Optional[ChargePoint]:
    """Resolve only the database UUID; never interpret it as an OCPP identity."""
    parsed = parse_uuid(internal_id)
    if parsed is None:
        return None
    return db.query(ChargePoint).filter(ChargePoint.id == parsed).first()


def get_charge_point_by_ocpp_identity(db: Session, identity: object) -> Optional[ChargePoint]:
    """Resolve only the exact public OCPP identity, including UUID-shaped identities."""
    if identity is None:
        return None
    return db.query(ChargePoint).filter(ChargePoint.ocpp_identity == str(identity)).first()


def get_charge_point_by_reference(db: Session, reference: object) -> Optional[ChargePoint]:
    """Resolve a public boundary reference.

    Exact OCPP identity wins before UUID fallback. This preserves valid UUID-shaped
    OCPP identities; internal-only call sites must use get_charge_point_by_internal_id.
    """
    by_identity = get_charge_point_by_ocpp_identity(db, reference)
    if by_identity is not None:
        return by_identity
    return get_charge_point_by_internal_id(db, reference)


def get_tenant_charge_point_by_reference(
    db: Session,
    reference: object,
    tenant_id: UUID,
) -> Optional[ChargePoint]:
    """Resolve a public reference while enforcing tenant ownership in each query."""
    if reference is None:
        return None
    by_identity = db.query(ChargePoint).filter(
        ChargePoint.tenant_id == tenant_id,
        ChargePoint.ocpp_identity == str(reference),
    ).first()
    if by_identity is not None:
        return by_identity
    internal_id = parse_uuid(reference)
    if internal_id is None:
        return None
    return db.query(ChargePoint).filter(
        ChargePoint.tenant_id == tenant_id,
        ChargePoint.id == internal_id,
    ).first()


def get_site_by_reference(db: Session, reference: object) -> Optional[Site]:
    """Resolve either an internal UUID or the stable public site code."""
    internal_id = parse_uuid(reference)
    if internal_id is not None:
        return db.query(Site).filter(Site.id == internal_id).first()
    return db.query(Site).filter(Site.site_code == str(reference)).first()


def charge_point_identity(charge_point: ChargePoint) -> str:
    return charge_point.ocpp_identity


def site_reference(site: Site) -> str:
    return site.site_code
