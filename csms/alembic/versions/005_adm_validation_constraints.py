"""Frozen ADM validation constraints for fresh development databases.

Revision ID: 005_adm_validation
Revises: 004_site_id_format
"""

from alembic import op
import sqlalchemy as sa


revision = "005_adm_validation"
down_revision = "004_site_id_format"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "ck_charge_points_ocpp_identity_format"


def _constraint_exists() -> bool:
    constraints = sa.inspect(op.get_bind()).get_check_constraints("charge_points")
    return any(item.get("name") == CONSTRAINT_NAME for item in constraints)


def upgrade() -> None:
    if not _constraint_exists():
        op.create_check_constraint(
            CONSTRAINT_NAME,
            "charge_points",
            "ocpp_identity ~ '^[A-Za-z0-9._:-]{1,64}$'",
        )


def downgrade() -> None:
    if _constraint_exists():
        op.drop_constraint(CONSTRAINT_NAME, "charge_points", type_="check")
