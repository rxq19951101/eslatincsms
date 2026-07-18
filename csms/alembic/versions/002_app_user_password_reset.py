"""Add one-time AppUser password reset token fields."""

from alembic import op
import sqlalchemy as sa


revision = "002_app_user_password_reset"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("app_users")}
    if "password_reset_token_hash" not in columns:
        op.add_column(
            "app_users",
            sa.Column("password_reset_token_hash", sa.String(length=64), nullable=True),
        )
    if "password_reset_expires_at" not in columns:
        op.add_column(
            "app_users",
            sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "password_reset_requested_at" not in columns:
        op.add_column(
            "app_users",
            sa.Column("password_reset_requested_at", sa.DateTime(timezone=True), nullable=True),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("app_users")}
    if "ix_app_users_password_reset_token_hash" not in indexes:
        op.create_index(
            "ix_app_users_password_reset_token_hash",
            "app_users",
            ["password_reset_token_hash"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_app_users_password_reset_token_hash", table_name="app_users")
    op.drop_column("app_users", "password_reset_requested_at")
    op.drop_column("app_users", "password_reset_expires_at")
    op.drop_column("app_users", "password_reset_token_hash")
