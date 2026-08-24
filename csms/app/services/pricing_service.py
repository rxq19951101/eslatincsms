"""Canonical tariff parsing, resolution and snapshot creation.

PRC-MODE-001 deliberately stores explicit pricing metadata in the existing
``Tariff.time_based_rules`` JSON column so the change remains migration-free.
Every business consumer must use this service instead of querying Tariff
directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import ChargePoint, PricingSnapshot, Tariff


class PricingMode(str, Enum):
    PAID = "paid"
    FREE = "free"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ResolvedPricing:
    pricing_mode: PricingMode
    pricing_source: str
    tariff: Optional[Tariff]
    base_price_per_kwh: Optional[Decimal]
    service_fee: Optional[Decimal]
    free_reason: Optional[str]
    valid_from: Optional[datetime]
    valid_until: Optional[datetime]
    rules: list[dict[str, Any]]

    @property
    def is_available(self) -> bool:
        return self.pricing_mode in (PricingMode.PAID, PricingMode.FREE)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pricing_mode": self.pricing_mode.value,
            "pricing_source": self.pricing_source,
            "tariff_id": str(self.tariff.id) if self.tariff else None,
            "base_price_per_kwh": (
                format(self.base_price_per_kwh, ".2f")
                if self.base_price_per_kwh is not None
                else None
            ),
            "service_fee": (
                format(self.service_fee, ".2f")
                if self.service_fee is not None
                else None
            ),
            "currency": "COP",
            "free_reason": self.free_reason,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
        }


class PricingService:
    SCHEMA_VERSION = 1

    @staticmethod
    def metadata(
        mode: PricingMode | str,
        *,
        free_reason: Optional[str] = None,
        rules: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": PricingService.SCHEMA_VERSION,
            "pricing_mode": PricingMode(mode).value,
            "free_reason": free_reason,
            "rules": rules or [],
        }

    @staticmethod
    def _parse_tariff(tariff: Tariff, source: str) -> ResolvedPricing:
        raw = tariff.time_based_rules
        rules: list[dict[str, Any]] = []
        free_reason = None
        mode: PricingMode

        if isinstance(raw, dict) and raw.get("pricing_mode") in {
            item.value for item in PricingMode
        }:
            mode = PricingMode(raw["pricing_mode"])
            free_reason = raw.get("free_reason")
            candidate_rules = raw.get("rules")
            if isinstance(candidate_rules, list):
                rules = [item for item in candidate_rules if isinstance(item, dict)]
        else:
            # Legacy arrays remain valid time rules. Legacy zero-price rows are
            # intentionally unavailable and must never silently become free.
            if isinstance(raw, list):
                rules = [item for item in raw if isinstance(item, dict)]
            mode = (
                PricingMode.PAID
                if Decimal(str(tariff.base_price_per_kwh or 0)) > 0
                else PricingMode.UNAVAILABLE
            )

        if mode == PricingMode.PAID:
            price = Decimal(str(tariff.base_price_per_kwh or 0))
            service_fee = Decimal(str(tariff.service_fee or 0))
        elif mode == PricingMode.FREE:
            price = Decimal("0.00")
            service_fee = Decimal("0.00")
        else:
            price = None
            service_fee = None

        return ResolvedPricing(
            pricing_mode=mode,
            pricing_source=source,
            tariff=tariff,
            base_price_per_kwh=price,
            service_fee=service_fee,
            free_reason=free_reason,
            valid_from=tariff.valid_from,
            valid_until=tariff.valid_until,
            rules=rules,
        )

    @staticmethod
    def unavailable(source: str = "none", tariff: Optional[Tariff] = None) -> ResolvedPricing:
        if tariff is not None:
            return PricingService._parse_tariff(tariff, source)
        return ResolvedPricing(
            pricing_mode=PricingMode.UNAVAILABLE,
            pricing_source=source,
            tariff=None,
            base_price_per_kwh=None,
            service_fee=None,
            free_reason=None,
            valid_from=None,
            valid_until=None,
            rules=[],
        )

    @staticmethod
    def _current_query(db: Session, tenant_id, at_time: datetime):
        return (
            db.query(Tariff)
            .filter(
                Tariff.tenant_id == tenant_id,
                Tariff.is_active.is_(True),
                Tariff.valid_from <= at_time,
            )
            .filter(
                (Tariff.valid_until.is_(None))
                | (Tariff.valid_until >= at_time)
            )
        )

    @staticmethod
    def resolve(
        db: Session,
        tenant_id,
        charge_point_id,
        at_time: Optional[datetime] = None,
    ) -> ResolvedPricing:
        at_time = at_time or datetime.now(timezone.utc)
        charge_point = (
            db.query(ChargePoint)
            .filter(
                ChargePoint.id == charge_point_id,
                ChargePoint.tenant_id == tenant_id,
            )
            .first()
        )
        if not charge_point:
            return PricingService.unavailable()

        charger_tariff = (
            PricingService._current_query(db, tenant_id, at_time)
            .filter(Tariff.charge_point_id == charge_point.id)
            .order_by(Tariff.valid_from.desc(), Tariff.created_at.desc())
            .first()
        )
        if charger_tariff:
            # Explicit charger unavailable is a hard override and does not fall
            # through to the site's commercial price.
            return PricingService._parse_tariff(charger_tariff, "charger")

        if charge_point.site_id:
            site_tariff = (
                PricingService._current_query(db, tenant_id, at_time)
                .filter(
                    Tariff.site_id == charge_point.site_id,
                    Tariff.charge_point_id.is_(None),
                )
                .order_by(Tariff.valid_from.desc(), Tariff.created_at.desc())
                .first()
            )
            if site_tariff:
                return PricingService._parse_tariff(site_tariff, "site")

        return PricingService.unavailable()

    @staticmethod
    def resolve_site(
        db: Session,
        tenant_id,
        site_id,
        at_time: Optional[datetime] = None,
    ) -> ResolvedPricing:
        at_time = at_time or datetime.now(timezone.utc)
        tariff = (
            PricingService._current_query(db, tenant_id, at_time)
            .filter(Tariff.site_id == site_id, Tariff.charge_point_id.is_(None))
            .order_by(Tariff.valid_from.desc(), Tariff.created_at.desc())
            .first()
        )
        return PricingService._parse_tariff(tariff, "site") if tariff else PricingService.unavailable()

    @staticmethod
    def price_for_time(pricing: ResolvedPricing, at_time: datetime) -> Decimal:
        if pricing.pricing_mode == PricingMode.FREE:
            return Decimal("0.00")
        for rule in pricing.rules:
            start_h = rule.get("start_hour", 0)
            end_h = rule.get("end_hour", 24)
            if start_h <= at_time.hour < end_h and rule.get("price_per_kwh") is not None:
                return Decimal(str(rule["price_per_kwh"]))
        return Decimal(str(pricing.base_price_per_kwh or 0))

    @staticmethod
    def create_session_snapshot(
        db: Session,
        session,
        pricing: Optional[ResolvedPricing] = None,
    ) -> PricingSnapshot:
        existing = (
            db.query(PricingSnapshot)
            .filter(
                PricingSnapshot.tenant_id == session.tenant_id,
                PricingSnapshot.session_id == session.id,
            )
            .order_by(PricingSnapshot.snapshot_time.asc())
            .first()
        )
        if existing:
            return existing

        pricing = pricing or PricingService.resolve(
            db,
            session.tenant_id,
            session.charge_point_id,
            session.start_time,
        )
        if not pricing.is_available or not pricing.tariff:
            raise ValueError("TARIFF_NOT_CONFIGURED")

        price = PricingService.price_for_time(pricing, session.start_time)
        snapshot = PricingSnapshot(
            tenant_id=session.tenant_id,
            tariff_id=pricing.tariff.id,
            session_id=session.id,
            price_per_kwh=price,
            service_fee=pricing.service_fee or Decimal("0.00"),
            snapshot_data={
                **pricing.as_dict(),
                "base_price_per_kwh": format(price, ".2f"),
                "rules": pricing.rules,
            },
            snapshot_time=session.start_time,
        )
        db.add(snapshot)
        db.flush()
        return snapshot
