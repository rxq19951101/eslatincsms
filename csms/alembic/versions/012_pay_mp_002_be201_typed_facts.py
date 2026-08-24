"""Add PAY-MP-002 BE-201 typed and immutable financial facts.

Revision ID: 012_pay_mp_002_be201
Revises: 011_app_wallet_invoice_link

The migration is intentionally additive. Its downgrade is non-destructive because
ADR-005 requires financial facts to survive an application rollback.
"""

from alembic import op
import sqlalchemy as sa

from app.database.models import Base


revision = "012_pay_mp_002_be201"
down_revision = "011_app_wallet_invoice_link"
branch_labels = None
depends_on = None


BE201_TABLES = (
    "recovery_attempts",
    "payment_allocations",
    "financial_eligibility_decisions",
    "refund_cases",
    "refund_approvals",
    "refund_attempts",
    "chargeback_cases",
    "reconciliation_runs",
    "reconciliation_items",
    "reconciliation_exceptions",
    "runtime_rail_controls",
    "support_cases",
    "support_case_events",
)


BE201_CURRENCY_CHECKS = {
    "recovery_attempts": "ck_recovery_attempt_currency",
    "payment_allocations": "ck_payment_allocation_currency",
    "refund_cases": "ck_refund_case_currency",
    "refund_approvals": "ck_refund_approval_currency",
    "refund_attempts": "ck_refund_attempt_currency",
    "chargeback_cases": "ck_chargeback_currency",
    "reconciliation_items": "ck_reconciliation_item_currency",
}


SUPPORT_RESOURCE_OWNERS = (
    (
        "invoice_id",
        "invoices",
        "uq_invoices_id_tenant",
        "fk_support_case_invoice_owner",
    ),
    (
        "session_id",
        "charging_sessions",
        "uq_charging_sessions_id_tenant",
        "fk_support_case_session_owner",
    ),
    (
        "refund_case_id",
        "refund_cases",
        "uq_refund_case_id_tenant",
        "fk_support_case_refund_owner",
    ),
    (
        "chargeback_case_id",
        "chargeback_cases",
        "uq_chargeback_case_id_tenant",
        "fk_support_case_chargeback_owner",
    ),
    (
        "rail_control_id",
        "runtime_rail_controls",
        "uq_runtime_rail_control_id_tenant",
        "fk_support_case_rail_owner",
    ),
)


OUTBOX_SCOPE_CHECK = (
    "(scope_type = 'platform' AND tenant_id IS NULL AND scope_ref = 'platform:eslatin') OR "
    "(scope_type = 'tenant' AND tenant_id IS NOT NULL AND length(scope_ref) = 43 "
    "AND substr(scope_ref, 1, 7) = 'tenant:' "
    "AND substr(scope_ref, 16, 1) = '-' AND substr(scope_ref, 21, 1) = '-' "
    "AND substr(scope_ref, 26, 1) = '-' AND substr(scope_ref, 31, 1) = '-' "
    "AND replace(substr(scope_ref, 8), '-', '') = replace(CAST(tenant_id AS VARCHAR), '-', ''))"
)


def _constraint_names(inspector, table_name: str, kind: str) -> set[str]:
    getter = {
        "unique": inspector.get_unique_constraints,
        "check": inspector.get_check_constraints,
        "foreign_key": inspector.get_foreign_keys,
    }[kind]
    return {item.get("name") for item in getter(table_name) if item.get("name")}


def _expand_resource_owner_keys(bind) -> None:
    inspector = sa.inspect(bind)
    uniques = _constraint_names(inspector, "invoices", "unique")
    if "uq_invoices_id_session_tenant" not in uniques:
        op.create_unique_constraint(
            "uq_invoices_id_session_tenant",
            "invoices",
            ["id", "session_id", "tenant_id"],
        )
    site_uniques = _constraint_names(sa.inspect(bind), "sites", "unique")
    if "uq_sites_id_tenant" not in site_uniques:
        op.create_unique_constraint(
            "uq_sites_id_tenant",
            "sites",
            ["id", "tenant_id"],
        )


def _ensure_support_target_owner_keys(bind) -> None:
    """Create owner candidate keys for every support target that exists.

    On a real P001/011 schema only invoices and charging_sessions exist at the
    start of revision 012, so their keys must be installed before any BE-201
    table can be created from current metadata. Refund, chargeback, and rail
    targets are added later in dependency order; a second call then closes
    their keys before support_cases is created. The existence check also keeps
    partial and repeated 012 applications idempotent.
    """
    existing_tables = set(sa.inspect(bind).get_table_names())
    for _, target_table, unique_name, _ in SUPPORT_RESOURCE_OWNERS:
        if target_table not in existing_tables:
            continue
        target_uniques = _constraint_names(
            sa.inspect(bind), target_table, "unique"
        )
        if unique_name not in target_uniques:
            op.create_unique_constraint(
                unique_name,
                target_table,
                ["id", "tenant_id"],
            )


def _ensure_support_case_owner_key(bind) -> None:
    """Make an existing partial support_cases table a valid Event FK target."""
    if "support_cases" not in set(sa.inspect(bind).get_table_names()):
        return
    support_uniques = _constraint_names(
        sa.inspect(bind), "support_cases", "unique"
    )
    if "uq_support_case_id_tenant" not in support_uniques:
        op.create_unique_constraint(
            "uq_support_case_id_tenant",
            "support_cases",
            ["id", "tenant_id"],
        )


def _expand_outbox_scope(bind) -> None:
    inspector = sa.inspect(bind)
    columns = {item["name"]: item for item in inspector.get_columns("outbox_events")}

    if "scope_type" not in columns:
        op.add_column("outbox_events", sa.Column("scope_type", sa.String(20), nullable=True))
    if "scope_ref" not in columns:
        op.add_column("outbox_events", sa.Column("scope_ref", sa.String(100), nullable=True))

    # Existing rows are deterministically tenant-scoped. No synthetic/system
    # tenant is introduced for future platform events.
    op.execute(
        sa.text(
            "UPDATE outbox_events "
            "SET scope_type = 'tenant', scope_ref = 'tenant:' || CAST(tenant_id AS VARCHAR) "
            "WHERE scope_type IS NULL OR scope_ref IS NULL"
        )
    )

    inspector = sa.inspect(bind)
    uniques = _constraint_names(inspector, "outbox_events", "unique")
    if "uq_outbox_tenant_idempotency" in uniques:
        op.drop_constraint("uq_outbox_tenant_idempotency", "outbox_events", type_="unique")

    # Replace the legacy CASCADE FK if present so delivery facts cannot vanish
    # through tenant deletion. The current fresh baseline already has RESTRICT.
    foreign_keys = inspector.get_foreign_keys("outbox_events")
    tenant_fk = next(
        (
            item
            for item in foreign_keys
            if item.get("constrained_columns") == ["tenant_id"]
            and item.get("referred_table") == "tenants"
        ),
        None,
    )
    if tenant_fk and tenant_fk.get("name"):
        ondelete = str((tenant_fk.get("options") or {}).get("ondelete") or "").upper()
        if ondelete != "RESTRICT":
            op.drop_constraint(tenant_fk["name"], "outbox_events", type_="foreignkey")
            op.create_foreign_key(
                "fk_outbox_events_tenant_id",
                "outbox_events",
                "tenants",
                ["tenant_id"],
                ["id"],
                ondelete="RESTRICT",
            )

    columns = {item["name"]: item for item in sa.inspect(bind).get_columns("outbox_events")}
    if columns["tenant_id"].get("nullable") is False:
        op.alter_column("outbox_events", "tenant_id", existing_type=sa.UUID(), nullable=True)
    if columns["scope_type"].get("nullable", True):
        op.alter_column("outbox_events", "scope_type", existing_type=sa.String(20), nullable=False)
    if columns["scope_ref"].get("nullable", True):
        op.alter_column("outbox_events", "scope_ref", existing_type=sa.String(100), nullable=False)

    inspector = sa.inspect(bind)
    uniques = _constraint_names(inspector, "outbox_events", "unique")
    if "uq_outbox_scope_idempotency" not in uniques:
        op.create_unique_constraint(
            "uq_outbox_scope_idempotency",
            "outbox_events",
            ["scope_type", "scope_ref", "idempotency_key"],
        )
    checks = _constraint_names(inspector, "outbox_events", "check")
    if "ck_outbox_scope_ownership" not in checks:
        op.create_check_constraint(
            "ck_outbox_scope_ownership",
            "outbox_events",
            OUTBOX_SCOPE_CHECK,
        )
    indexes = {item["name"] for item in inspector.get_indexes("outbox_events")}
    if "idx_outbox_scope_status_available" not in indexes:
        op.create_index(
            "idx_outbox_scope_status_available",
            "outbox_events",
            ["scope_type", "scope_ref", "status", "available_at"],
        )

    if bind.dialect.name == "postgresql":
        # A rolled-back P001 application omits the additive scope columns. Keep
        # that legacy tenant insert compatible without manufacturing a platform
        # tenant or weakening the canonical scope CHECK.
        op.execute(
            """
            CREATE OR REPLACE FUNCTION be201_set_outbox_tenant_scope()
            RETURNS trigger AS $$
            BEGIN
                IF NEW.scope_type IS NULL AND NEW.tenant_id IS NOT NULL THEN
                    NEW.scope_type := 'tenant';
                END IF;
                IF NEW.scope_ref IS NULL
                   AND NEW.scope_type = 'tenant'
                   AND NEW.tenant_id IS NOT NULL THEN
                    NEW.scope_ref := 'tenant:' || NEW.tenant_id::text;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_be201_outbox_tenant_scope ON outbox_events")
        op.execute(
            """
            CREATE TRIGGER trg_be201_outbox_tenant_scope
            BEFORE INSERT ON outbox_events
            FOR EACH ROW EXECUTE FUNCTION be201_set_outbox_tenant_scope()
            """
        )


def _enforce_cop_currency_constraints(bind) -> None:
    """Keep every BE-201 monetary fact bound to the frozen COP-only contract."""
    for table_name, constraint_name in BE201_CURRENCY_CHECKS.items():
        checks = {
            item.get("name"): str(item.get("sqltext") or "")
            for item in sa.inspect(bind).get_check_constraints(table_name)
        }
        current_sql = checks.get(constraint_name, "")

        if bind.dialect.name == "postgresql":
            # Revision 001 builds current metadata on an empty database. Replace
            # the named CHECK here as well so a legacy P001 baseline cannot keep
            # the earlier weak three-uppercase rule.
            if constraint_name in checks:
                op.drop_constraint(constraint_name, table_name, type_="check")
            op.create_check_constraint(
                constraint_name,
                table_name,
                "currency = 'COP'",
            )
            continue

        normalized = "".join(current_sql.split()).replace('"', "")
        if normalized not in {"currency='COP'", "(currency='COP')"}:
            raise RuntimeError(
                f"{table_name}.{constraint_name} must enforce currency = 'COP'"
            )


def _enforce_reconciliation_allocation_ownership(bind) -> None:
    """Bind tenant reconciliation facts to same-tenant allocations in the DB.

    The existing single-column FK remains authoritative for allocation
    existence. The composite MATCH SIMPLE FK additionally binds tenant-scoped
    rows; a platform-scoped row has tenant_id NULL and may legally reconcile an
    allocation from any tenant while still satisfying the single-column FK.
    """
    allocation_unique = "uq_payment_allocation_id_tenant"
    owner_fk = "fk_reconciliation_item_allocation_owner"
    inspector = sa.inspect(bind)
    allocation_uniques = _constraint_names(
        inspector, "payment_allocations", "unique"
    )
    item_fks = _constraint_names(
        inspector, "reconciliation_items", "foreign_key"
    )

    if bind.dialect.name != "postgresql":
        missing = {
            name
            for name, present in (
                (allocation_unique, allocation_unique in allocation_uniques),
                (owner_fk, owner_fk in item_fks),
            )
            if not present
        }
        if missing:
            raise RuntimeError(
                "BE-201 metadata must create reconciliation allocation ownership "
                f"constraints before migration: {sorted(missing)}"
            )
        return

    if owner_fk not in item_fks:
        mismatch_count = bind.execute(
            sa.text(
                "SELECT count(*) "
                "FROM reconciliation_items ri "
                "JOIN payment_allocations pa ON pa.id = ri.payment_allocation_id "
                "WHERE ri.payment_allocation_id IS NOT NULL "
                "AND ri.scope_type = 'tenant' "
                "AND ri.tenant_id IS DISTINCT FROM pa.tenant_id"
            )
        ).scalar_one()
        if mismatch_count:
            raise RuntimeError(
                "Cannot add fk_reconciliation_item_allocation_owner: "
                f"{mismatch_count} cross-tenant reconciliation allocation link(s) exist"
            )

    if allocation_unique not in allocation_uniques:
        op.create_unique_constraint(
            allocation_unique,
            "payment_allocations",
            ["id", "tenant_id"],
        )

    if owner_fk not in item_fks:
        op.create_foreign_key(
            owner_fk,
            "reconciliation_items",
            "payment_allocations",
            ["payment_allocation_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="RESTRICT",
            match="SIMPLE",
        )


def _enforce_support_case_link_ownership(bind) -> None:
    """Bind every tenant SupportCase link and event to the same tenant.

    Support cases are tenant-scoped facts. Nullable links remain legal through
    MATCH SIMPLE; a non-null link must identify a resource owned by the case
    tenant. Platform/provider rail controls therefore cannot be attached to a
    tenant case because their tenant_id is NULL.
    """
    inspector = sa.inspect(bind)
    support_fks = _constraint_names(inspector, "support_cases", "foreign_key")
    event_fks = _constraint_names(inspector, "support_case_events", "foreign_key")
    expected = {
        unique_name
        for _, _, unique_name, _ in SUPPORT_RESOURCE_OWNERS
    } | {
        fk_name
        for _, _, _, fk_name in SUPPORT_RESOURCE_OWNERS
    } | {
        "uq_support_case_id_tenant",
        "fk_support_case_event_owner",
    }

    if bind.dialect.name != "postgresql":
        present = set(support_fks) | set(event_fks)
        present |= _constraint_names(inspector, "support_cases", "unique")
        for _, target_table, _, _ in SUPPORT_RESOURCE_OWNERS:
            present |= _constraint_names(inspector, target_table, "unique")
        missing = expected - present
        if missing:
            raise RuntimeError(
                "BE-201 metadata must create support ownership constraints "
                f"before migration: {sorted(missing)}"
            )
        return

    # Validate all direct ownership links before issuing any support-related
    # DDL. Alembic's PostgreSQL transaction makes this failure atomic: dirty
    # facts remain untouched and the revision cannot advance.
    dirty_links: list[str] = []
    for local_column, target_table, _, fk_name in SUPPORT_RESOURCE_OWNERS:
        if fk_name in support_fks:
            continue
        mismatch_count = bind.execute(
            sa.text(
                f"SELECT count(*) FROM support_cases sc "
                f"JOIN {target_table} linked ON linked.id = sc.{local_column} "
                f"WHERE sc.{local_column} IS NOT NULL "
                "AND sc.tenant_id IS DISTINCT FROM linked.tenant_id"
            )
        ).scalar_one()
        if mismatch_count:
            dirty_links.append(f"{local_column}={mismatch_count}")

    if "fk_support_case_event_owner" not in event_fks:
        mismatch_count = bind.execute(
            sa.text(
                "SELECT count(*) FROM support_case_events sce "
                "JOIN support_cases sc ON sc.id = sce.support_case_id "
                "WHERE sce.tenant_id IS DISTINCT FROM sc.tenant_id"
            )
        ).scalar_one()
        if mismatch_count:
            dirty_links.append(f"support_case_event={mismatch_count}")

    if dirty_links:
        raise RuntimeError(
            "Cannot add BE-201 SupportCase tenant ownership constraints: "
            + ", ".join(dirty_links)
        )

    _ensure_support_target_owner_keys(bind)
    _ensure_support_case_owner_key(bind)

    support_fks = _constraint_names(
        sa.inspect(bind), "support_cases", "foreign_key"
    )
    for local_column, target_table, _, fk_name in SUPPORT_RESOURCE_OWNERS:
        if fk_name not in support_fks:
            op.create_foreign_key(
                fk_name,
                "support_cases",
                target_table,
                [local_column, "tenant_id"],
                ["id", "tenant_id"],
                ondelete="RESTRICT",
                match="SIMPLE",
            )

    event_fks = _constraint_names(
        sa.inspect(bind), "support_case_events", "foreign_key"
    )
    if "fk_support_case_event_owner" not in event_fks:
        op.create_foreign_key(
            "fk_support_case_event_owner",
            "support_case_events",
            "support_cases",
            ["support_case_id", "tenant_id"],
            ["id", "tenant_id"],
            ondelete="RESTRICT",
        )


def upgrade() -> None:
    bind = op.get_bind()
    _expand_resource_owner_keys(bind)
    # Real revision 011 schemas do not contain current metadata's support owner
    # candidate keys. Install the two existing P001 target keys before creating
    # any BE-201 table so later composite FKs have valid PostgreSQL targets.
    _ensure_support_target_owner_keys(bind)
    _expand_outbox_scope(bind)

    # Build all non-Support BE-201 facts first. Their order follows FK
    # dependencies (attempt -> allocation -> refund/chargeback/reconciliation;
    # rail depends only on P001 sites). SupportCase is intentionally excluded
    # until every linked-resource candidate key exists.
    existing = set(sa.inspect(bind).get_table_names())
    for table_name in BE201_TABLES[:-2]:
        if table_name not in existing:
            Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)
            existing.add(table_name)

    # New refund/chargeback/rail targets now exist. This is also the repair
    # point for a partial 012 schema whose target table predates its unique key.
    _ensure_support_target_owner_keys(bind)

    if "support_cases" not in existing:
        Base.metadata.tables["support_cases"].create(bind=bind, checkfirst=True)
        existing.add("support_cases")
    _ensure_support_case_owner_key(bind)
    if "support_case_events" not in existing:
        Base.metadata.tables["support_case_events"].create(
            bind=bind, checkfirst=True
        )
        existing.add("support_case_events")

    _enforce_cop_currency_constraints(bind)
    _enforce_reconciliation_allocation_ownership(bind)
    _enforce_support_case_link_ownership(bind)


def downgrade() -> None:
    # Application rollback closes PAY-MP-002 reads/writes and preserves every
    # financial/audit fact. A later, separately approved archival migration is
    # required before any physical table or constraint removal.
    pass
