"""Remove the retired tenant-scoped EndUser model.

The platform now uses AppUser as the only app account model. Development data
was intentionally reset, so the retired tables can be dropped without a data
migration.
"""

from alembic import op
import sqlalchemy as sa


revision = "003_remove_legacy_end_users"
down_revision = "002_app_user_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # wallet_transactions references end_users, so it must be removed first.
    if "wallet_transactions" in tables:
        op.drop_table("wallet_transactions")
    if "end_users" in tables:
        op.drop_table("end_users")


def downgrade() -> None:
    # The old account model is intentionally not recreated. Restoring it would
    # reintroduce a second user authority and violate the current domain model.
    pass
