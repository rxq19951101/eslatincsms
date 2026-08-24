"""Add OCPP replay outcomes and automatic-alert dedupe keys.

Revision ID: 007_sim_e2e_ocpp_events_alerts
Revises: 006_payment_provider_ids_unique
"""

from alembic import op
import sqlalchemy as sa


revision = "007_sim_e2e_ocpp_events_alerts"
down_revision = "006_payment_provider_ids_unique"
branch_labels = None
depends_on = None


OCPP_COLUMNS = {
    "unique_id": sa.Column("unique_id", sa.String(length=255), nullable=True),
    "response_payload": sa.Column("response_payload", sa.JSON(), nullable=True),
    "response_message_type": sa.Column("response_message_type", sa.Integer(), nullable=True),
    "processing_status": sa.Column(
        "processing_status", sa.String(length=20), nullable=False, server_default="processing"
    ),
    "outcome": sa.Column("outcome", sa.String(length=50), nullable=True),
    "processed_at": sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
}


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _constraint_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {
        item["name"]
        for item in inspector.get_unique_constraints(table)
        if item.get("name")
    }


def _index_names(table: str) -> set[str]:
    return {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_indexes(table)
        if item.get("name")
    }


def upgrade() -> None:
    existing = _column_names("ocpp_message_events")
    for name, column in OCPP_COLUMNS.items():
        if name not in existing:
            op.add_column("ocpp_message_events", column)

    if "dedupe_key" not in _column_names("alerts"):
        op.add_column("alerts", sa.Column("dedupe_key", sa.String(length=255), nullable=True))

    if "uq_ocpp_message_event_unique_id" not in _constraint_names("ocpp_message_events"):
        op.create_unique_constraint(
            "uq_ocpp_message_event_unique_id",
            "ocpp_message_events",
            ["tenant_id", "charge_point_id", "unique_id"],
        )
    if "uq_alerts_tenant_dedupe_key" not in _constraint_names("alerts"):
        op.create_unique_constraint(
            "uq_alerts_tenant_dedupe_key", "alerts", ["tenant_id", "dedupe_key"]
        )
    if "idx_ocpp_message_events_unique_id" not in _index_names("ocpp_message_events"):
        op.create_index(
            "idx_ocpp_message_events_unique_id", "ocpp_message_events", ["unique_id"]
        )


def downgrade() -> None:
    if "idx_ocpp_message_events_unique_id" in _index_names("ocpp_message_events"):
        op.drop_index("idx_ocpp_message_events_unique_id", table_name="ocpp_message_events")
    if "uq_alerts_tenant_dedupe_key" in _constraint_names("alerts"):
        op.drop_constraint("uq_alerts_tenant_dedupe_key", "alerts", type_="unique")
    if "uq_ocpp_message_event_unique_id" in _constraint_names("ocpp_message_events"):
        op.drop_constraint(
            "uq_ocpp_message_event_unique_id", "ocpp_message_events", type_="unique"
        )
    if "dedupe_key" in _column_names("alerts"):
        op.drop_column("alerts", "dedupe_key")
    existing = _column_names("ocpp_message_events")
    for name in reversed(tuple(OCPP_COLUMNS)):
        if name in existing:
            op.drop_column("ocpp_message_events", name)
