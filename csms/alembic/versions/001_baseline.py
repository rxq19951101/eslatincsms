"""Initial schema baseline

Revision ID: 001_baseline
Revises:
Create Date: 2026-06-09

Existing databases created by the development bootstrap can stamp this revision:
  alembic stamp 001_baseline
Fresh installs create the current model metadata through this migration.
"""

from alembic import op
import sqlalchemy as sa
from app.database import Base

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
