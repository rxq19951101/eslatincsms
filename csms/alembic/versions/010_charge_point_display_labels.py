"""Add site-scoped public charge point labels.

Revision ID: 010_charge_point_display_labels
Revises: 009_ocpp_device_commissioning
"""

from alembic import op
import sqlalchemy as sa


revision = "010_charge_point_display_labels"
down_revision = "009_ocpp_device_commissioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("charge_points", sa.Column("display_code", sa.String(16), nullable=True))
    op.add_column("charge_points", sa.Column("display_name", sa.String(80), nullable=True))
    op.add_column("charge_points", sa.Column("location_hint", sa.String(160), nullable=True))

    # Existing assets receive deterministic, short labels within each site.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   'CP' || LPAD(ROW_NUMBER() OVER (
                       PARTITION BY site_id ORDER BY created_at, id
                   )::text, 3, '0') AS generated_code
            FROM charge_points
        )
        UPDATE charge_points AS cp
        SET display_code = ranked.generated_code
        FROM ranked
        WHERE cp.id = ranked.id
        """
    )
    op.execute(
        """
        UPDATE evses AS evse
        SET physical_reference = cp.display_code || '-' || evse.evse_id::text
        FROM charge_points AS cp
        WHERE evse.charge_point_id = cp.id
          AND (evse.physical_reference IS NULL OR BTRIM(evse.physical_reference) = '')
        """
    )
    op.alter_column("charge_points", "display_code", nullable=False)
    op.create_unique_constraint(
        "uq_charge_points_site_display_code",
        "charge_points",
        ["site_id", "display_code"],
    )
    op.create_check_constraint(
        "ck_charge_points_display_code_length",
        "charge_points",
        "length(display_code) BETWEEN 1 AND 16",
    )
    op.create_check_constraint(
        "ck_charge_points_display_code_format",
        "charge_points",
        "display_code ~ '^[A-Z][A-Z0-9-]{0,15}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_charge_points_display_code_format", "charge_points", type_="check")
    op.drop_constraint("ck_charge_points_display_code_length", "charge_points", type_="check")
    op.drop_constraint("uq_charge_points_site_display_code", "charge_points", type_="unique")
    op.drop_column("charge_points", "location_hint")
    op.drop_column("charge_points", "display_name")
    op.drop_column("charge_points", "display_code")
