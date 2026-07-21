"""Add per-device OCPP credentials and commissioning metadata.

Revision ID: 009_ocpp_device_commissioning
Revises: 008_app_user_favorite_sites
"""

from alembic import op
import sqlalchemy as sa


revision = "009_ocpp_device_commissioning"
down_revision = "008_app_user_favorite_sites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("charge_points", sa.Column("ocpp_auth_secret_hash", sa.String(64), nullable=True))
    op.add_column(
        "charge_points",
        sa.Column("commissioning_status", sa.String(20), nullable=False, server_default="draft"),
    )
    op.add_column("charge_points", sa.Column("acceptance_report", sa.JSON(), nullable=True))
    op.add_column("charge_points", sa.Column("last_acceptance_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("charge_points", sa.Column("commissioned_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_charge_points_commissioning_status",
        "charge_points",
        "commissioning_status IN ('draft', 'testing', 'ready', 'commissioned', 'suspended')",
    )
    op.add_column("evses", sa.Column("physical_reference", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_evses_charge_point_physical_reference",
        "evses",
        ["charge_point_id", "physical_reference"],
    )
    op.create_check_constraint("ck_evses_max_power_positive", "evses", "max_power_kw IS NULL OR max_power_kw > 0")


def downgrade() -> None:
    op.drop_constraint("ck_evses_max_power_positive", "evses", type_="check")
    op.drop_constraint("uq_evses_charge_point_physical_reference", "evses", type_="unique")
    op.drop_column("evses", "physical_reference")
    op.drop_constraint("ck_charge_points_commissioning_status", "charge_points", type_="check")
    op.drop_column("charge_points", "commissioned_at")
    op.drop_column("charge_points", "last_acceptance_at")
    op.drop_column("charge_points", "acceptance_report")
    op.drop_column("charge_points", "commissioning_status")
    op.drop_column("charge_points", "ocpp_auth_secret_hash")
