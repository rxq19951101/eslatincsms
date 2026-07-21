"""Add App user favorite sites.

Revision ID: 008_app_user_favorite_sites
Revises: 007_sim_e2e_ocpp_events_alerts
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "008_app_user_favorite_sites"
down_revision = "007_sim_e2e_ocpp_events_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_user_favorite_sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["app_user_id"], ["app_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_user_id", "site_id", name="uq_app_user_favorite_site"),
    )
    op.create_index(
        "ix_app_user_favorite_sites_app_user_id",
        "app_user_favorite_sites",
        ["app_user_id"],
    )
    op.create_index(
        "ix_app_user_favorite_sites_site_id",
        "app_user_favorite_sites",
        ["site_id"],
    )
    op.create_index(
        "idx_app_user_favorite_sites_user_created",
        "app_user_favorite_sites",
        ["app_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_app_user_favorite_sites_user_created", table_name="app_user_favorite_sites")
    op.drop_index("ix_app_user_favorite_sites_site_id", table_name="app_user_favorite_sites")
    op.drop_index("ix_app_user_favorite_sites_app_user_id", table_name="app_user_favorite_sites")
    op.drop_table("app_user_favorite_sites")
