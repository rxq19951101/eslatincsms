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
    bind = op.get_bind()
    if "app_user_favorite_sites" not in sa.inspect(bind).get_table_names():
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

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("app_user_favorite_sites")}
    expected_indexes = {
        "ix_app_user_favorite_sites_app_user_id": ["app_user_id"],
        "ix_app_user_favorite_sites_site_id": ["site_id"],
        "idx_app_user_favorite_sites_user_created": ["app_user_id", "created_at"],
    }
    for name, columns in expected_indexes.items():
        if name not in indexes:
            op.create_index(name, "app_user_favorite_sites", columns)


def downgrade() -> None:
    op.drop_index("idx_app_user_favorite_sites_user_created", table_name="app_user_favorite_sites")
    op.drop_index("ix_app_user_favorite_sites_site_id", table_name="app_user_favorite_sites")
    op.drop_index("ix_app_user_favorite_sites_app_user_id", table_name="app_user_favorite_sites")
    op.drop_table("app_user_favorite_sites")
