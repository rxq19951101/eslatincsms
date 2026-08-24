#!/usr/bin/env python3
"""Safely remove only the deterministic SIM-E2E local/test dataset."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import and_, delete, func, not_, or_, select
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.database.base import Base, SessionLocal, database_access_scope
from app.database.models import ChargingSession, Invoice
try:
    from scripts.seed_sim_e2e import stable_id
except ImportError:  # pragma: no cover - direct script execution
    from seed_sim_e2e import stable_id


ALLOWED_ENVIRONMENTS = {"development", "test"}
LOCAL_DATABASE_HOSTS = {None, "", "localhost", "127.0.0.1", "::1", "db"}
SEEDED_TABLE_IDS = {
    "tenants": ("tenant", "tenant-b"),
    "admin_users": ("admin", "readonly-admin"),
    "app_users": ("app-user", "low-balance-app-user", "other-app-user"),
    "roles": ("role", "readonly-role"),
    "tenant_memberships": ("membership", "readonly-membership"),
    "tenant_membership_roles": ("membership-role", "readonly-membership-role"),
    "sites": ("site", "tenant-b-site"),
    "charge_points": ("charge-point", "other-charge-point", "tenant-b-charge-point"),
    "evses": ("evse", "other-evse", "tenant-b-evse"),
    "evse_statuses": ("evse-status", "other-evse-status", "tenant-b-evse-status"),
    "tariffs": ("tariff",),
    "qr_tokens": ("qr", "other-qr", "tenant-b-qr"),
    "charging_sessions": ("ownership-session",),
    "payment_orders": ("charging-payment-order", "top-up-payment-order"),
    "alerts": ("fault-alert",),
    "app_wallet_transactions": ("wallet-top-up",),
}

REFERENCE_NAMES = {
    "site_id": ("site", "tenant-b-site"),
    "charge_point_id": ("charge-point", "other-charge-point", "tenant-b-charge-point"),
    "evse_id": ("evse", "other-evse", "tenant-b-evse"),
    "current_session_id": ("ownership-session",),
    "session_id": ("ownership-session",),
    "payment_order_id": ("charging-payment-order", "top-up-payment-order"),
    "membership_id": ("membership", "readonly-membership"),
    "role_id": ("role", "readonly-role"),
    "admin_user_id": ("admin", "readonly-admin"),
    "adjusted_by_admin_id": ("admin", "readonly-admin"),
    "app_user_id": ("app-user", "low-balance-app-user", "other-app-user"),
}

ACTOR_IDS = (
    "admin", "readonly-admin", "app-user", "low-balance-app-user", "other-app-user"
)

SIM_INVOICE_REFERENCE_PREFIX = "inv_SIM-E2E-"
SIM_PAYMENT_REFERENCE_PREFIX = "pay_SIM-E2E-"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run cleanup of deterministic SIM-E2E local/test data by default."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete matched data. Without this switch no rows are changed.",
    )
    return parser.parse_args()


def ensure_safe_environment(apply: bool) -> str:
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        raise SystemExit("SIM-E2E cleanup is disabled outside development/test")

    database_url = make_url(get_settings().database_url)
    if apply:
        if database_url.get_backend_name() != "postgresql":
            raise SystemExit("--apply requires the local PostgreSQL development database")
        if database_url.host not in LOCAL_DATABASE_HOSTS:
            raise SystemExit(
                "--apply refused: database host is not an approved local/Compose host"
            )
    return environment


def uuid_values(names: Iterable[str]) -> tuple:
    return tuple(stable_id(name) for name in names)


def table_scope_condition(
    table,
    extra_session_ids: Iterable[uuid.UUID] = (),
    extra_invoice_ids: Iterable[uuid.UUID] = (),
):
    """Build an exact-ID/reference allowlist; never expand by tenant or email."""
    clauses = []
    references = {
        **{name: uuid_values(values) for name, values in REFERENCE_NAMES.items()},
        "actor_id": uuid_values(ACTOR_IDS),
    }
    session_ids = tuple(set(uuid_values(("ownership-session",))) | set(extra_session_ids))
    references["session_id"] = session_ids
    references["current_session_id"] = session_ids

    for column_name, values in references.items():
        if values and column_name in table.c:
            column = table.c[column_name]
            try:
                is_uuid_column = column.type.python_type is uuid.UUID
            except (AttributeError, NotImplementedError):
                is_uuid_column = False
            if is_uuid_column:
                clauses.append(column.in_(values))

    direct_names = SEEDED_TABLE_IDS.get(table.name)
    if direct_names and "id" in table.c:
        clauses.append(table.c.id.in_(uuid_values(direct_names)))

    if table.name == "refresh_tokens":
        clauses.append(table.c.user_id.in_(uuid_values(ACTOR_IDS)))

    # Outbox aggregate_id is a string rather than a foreign key. Restrict it
    # to the exact matched SIM session IDs and the expected aggregate type.
    if table.name == "outbox_events" and session_ids:
        clauses.append(and_(
            table.c.aggregate_type == "ChargingSession",
            table.c.aggregate_id.in_(tuple(str(value) for value in session_ids)),
        ))

    # Payments have no session_id. They are allowlisted only through an exact
    # invoice FK whose invoice belongs to a matched SIM session. Stable
    # inv_SIM-E2E-/pay_SIM-E2E- references remain diagnostic identifiers and
    # never widen this relational boundary on their own.
    invoice_ids = tuple(set(extra_invoice_ids))
    if table.name == "payments" and invoice_ids:
        clauses.append(table.c.invoice_id.in_(invoice_ids))

    return or_(*clauses) if clauses else None


def discover_sim_session_ids(db) -> tuple[uuid.UUID, ...]:
    charge_point_ids = uuid_values(SEEDED_TABLE_IDS["charge_points"])
    app_user_ids = uuid_values(SEEDED_TABLE_IDS["app_users"])
    return tuple(
        db.execute(
            select(ChargingSession.id).where(
                ChargingSession.charge_point_id.in_(charge_point_ids),
                or_(
                    ChargingSession.app_user_id.in_(app_user_ids),
                    ChargingSession.user_id.in_(tuple(str(value) for value in app_user_ids)),
                    ChargingSession.id_tag.like("SIM-E2E-%"),
                    ChargingSession.transaction_id == 900001,
                ),
            )
        ).scalars()
    )


def discover_sim_invoice_ids(
    db,
    session_ids: Iterable[uuid.UUID],
) -> tuple[uuid.UUID, ...]:
    session_ids = tuple(set(session_ids))
    if not session_ids:
        return ()
    return tuple(
        db.execute(
            select(Invoice.id).where(Invoice.session_id.in_(session_ids))
        ).scalars()
    )


def _resolved_invoice_ids(
    db,
    session_ids: Iterable[uuid.UUID],
    invoice_ids: Optional[Iterable[uuid.UUID]],
) -> tuple[uuid.UUID, ...]:
    if invoice_ids is None:
        return discover_sim_invoice_ids(db, session_ids)
    return tuple(set(invoice_ids))


def matched_counts(
    db,
    extra_session_ids: Iterable[uuid.UUID] = (),
    extra_invoice_ids: Optional[Iterable[uuid.UUID]] = None,
) -> dict[str, int]:
    extra_session_ids = tuple(set(extra_session_ids))
    invoice_ids = _resolved_invoice_ids(db, extra_session_ids, extra_invoice_ids)
    counts = {}
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        condition = table_scope_condition(table, extra_session_ids, invoice_ids)
        if condition is None:
            continue
        count = db.execute(
            select(func.count()).select_from(table).where(condition)
        ).scalar_one()
        if count:
            counts[table.name] = count
    return counts


def unmatched_tenant_counts(
    db,
    extra_session_ids: Iterable[uuid.UUID],
    extra_invoice_ids: Optional[Iterable[uuid.UUID]] = None,
) -> dict[str, int]:
    """Refuse cleanup if deleting a seeded tenant could cascade non-whitelisted rows."""
    extra_session_ids = tuple(set(extra_session_ids))
    invoice_ids = _resolved_invoice_ids(db, extra_session_ids, extra_invoice_ids)
    tenant_ids = uuid_values(SEEDED_TABLE_IDS["tenants"])
    counts: dict[str, int] = {}
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        tenant_clauses = []
        for column_name in ("tenant_id", "operator_tenant_id"):
            if column_name in table.c:
                tenant_clauses.append(table.c[column_name].in_(tenant_ids))
        if not tenant_clauses:
            continue
        tenant_condition = or_(*tenant_clauses)
        allowlisted = table_scope_condition(table, extra_session_ids, invoice_ids)
        condition = (
            and_(tenant_condition, not_(allowlisted))
            if allowlisted is not None
            else tenant_condition
        )
        count = db.execute(
            select(func.count()).select_from(table).where(condition)
        ).scalar_one()
        if count:
            counts[table.name] = count
    return counts


def delete_allowlisted_rows(
    db,
    extra_session_ids: Iterable[uuid.UUID],
    extra_invoice_ids: Optional[Iterable[uuid.UUID]] = None,
) -> dict[str, int]:
    extra_session_ids = tuple(set(extra_session_ids))
    invoice_ids = _resolved_invoice_ids(db, extra_session_ids, extra_invoice_ids)
    deleted_rows: dict[str, int] = {}
    for table in reversed(Base.metadata.sorted_tables):
        condition = table_scope_condition(table, extra_session_ids, invoice_ids)
        if condition is None:
            continue
        deleted = db.execute(delete(table).where(condition)).rowcount or 0
        if deleted:
            deleted_rows[table.name] = deleted
    return deleted_rows


@database_access_scope("system")
def main() -> None:
    args = parse_args()
    environment = ensure_safe_environment(args.apply)
    db = SessionLocal()
    try:
        sim_session_ids = discover_sim_session_ids(db)
        sim_invoice_ids = discover_sim_invoice_ids(db, sim_session_ids)
        before = matched_counts(db, sim_session_ids, sim_invoice_ids)
        unmatched = unmatched_tenant_counts(db, sim_session_ids, sim_invoice_ids)
        if not args.apply:
            db.rollback()
            print(json.dumps({
                "mode": "dry-run",
                "environment": environment,
                "matched_rows": before,
                "matched_total": sum(before.values()),
                "unmatched_tenant_rows": unmatched,
            }, sort_keys=True))
            return

        if unmatched:
            raise RuntimeError(
                "Cleanup refused because seeded tenants contain non-whitelisted rows: "
                f"{unmatched}"
            )

        deleted_rows = delete_allowlisted_rows(db, sim_session_ids, sim_invoice_ids)

        remaining = matched_counts(db, sim_session_ids, sim_invoice_ids)
        if remaining:
            raise RuntimeError(
                f"Cleanup left deterministic SIM-E2E rows; transaction rolled back: {remaining}"
            )
        db.commit()
        print(json.dumps({
            "mode": "apply",
            "environment": environment,
            "matched_before": before,
            "deleted_scoped_total": sum(before.values()),
            "deleted_rows": deleted_rows,
            "remaining": remaining,
        }, sort_keys=True))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
