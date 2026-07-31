"""Link wallet charge transactions to their authoritative invoices.

Revision ID: 011_app_wallet_invoice_link
Revises: 010_charge_point_display_labels
"""

from alembic import op
import sqlalchemy as sa


revision = "011_app_wallet_invoice_link"
down_revision = "010_charge_point_display_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_wallet_transactions",
        sa.Column("invoice_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_app_wallet_transactions_invoice_id",
        "app_wallet_transactions",
        "invoices",
        ["invoice_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_app_wallet_transactions_invoice_id",
        "app_wallet_transactions",
        ["invoice_id"],
        unique=True,
    )
    op.execute(
        """
        UPDATE app_wallet_transactions AS wallet
        SET invoice_id = invoice.id
        FROM invoices AS invoice
        WHERE wallet.type = 'charge'
          AND wallet.invoice_id IS NULL
          AND (
              wallet.transaction_number = 'wallet_' || invoice.invoice_number
              OR wallet.idempotency_key = 'charge:' || invoice.session_id::text
          )
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_app_wallet_transactions_invoice_id",
        table_name="app_wallet_transactions",
    )
    op.drop_constraint(
        "fk_app_wallet_transactions_invoice_id",
        "app_wallet_transactions",
        type_="foreignkey",
    )
    op.drop_column("app_wallet_transactions", "invoice_id")
