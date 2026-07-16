"""Initial schema baseline

Revision ID: 001_baseline
Revises:
Create Date: 2026-06-09

Existing deployments created via init_db()/create_all should stamp this revision:
  alembic stamp 001_baseline
Fresh installs run upgrade to create tables via SQLAlchemy metadata.
"""

from alembic import op
import sqlalchemy as sa

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Baseline: schema managed by app.database.models + init_db on first boot.
    # Use `alembic stamp 001_baseline` on DBs already initialized with create_all.
    pass


def downgrade() -> None:
    pass
