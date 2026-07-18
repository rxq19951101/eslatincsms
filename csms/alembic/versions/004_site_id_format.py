"""Require opaque public codes for UUID-backed sites.

Development databases containing legacy name-derived IDs must be reset before
this migration is applied. Business names remain in ``sites.name`` only.
"""

from alembic import op
import sqlalchemy as sa


revision = "004_site_id_format"
down_revision = "003_remove_legacy_end_users"
branch_labels = None
depends_on = None


CONSTRAINT_NAME = "ck_sites_code_format"


def _constraint_exists() -> bool:
    constraints = sa.inspect(op.get_bind()).get_check_constraints("sites")
    return any(item.get("name") == CONSTRAINT_NAME for item in constraints)


def upgrade() -> None:
    if not _constraint_exists():
        op.create_check_constraint(
            CONSTRAINT_NAME,
            "sites",
            "site_code ~ '^site_[0-9a-f]{16}$'",
        )


def downgrade() -> None:
    if _constraint_exists():
        op.drop_constraint(CONSTRAINT_NAME, "sites", type_="check")
