"""Make payment-provider transaction identifiers unique.

Revision ID: 006_payment_provider_ids_unique
Revises: 005_adm_validation
"""

from alembic import op
import sqlalchemy as sa


revision = "006_payment_provider_ids_unique"
down_revision = "005_adm_validation"
branch_labels = None
depends_on = None


CONSTRAINTS = {
    "uq_payment_orders_wompi_transaction_id": ["wompi_transaction_id"],
    "uq_payment_orders_mercadopago_payment_id": ["mercadopago_payment_id"],
}


def _existing_unique_constraints() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    constraints = inspector.get_unique_constraints("payment_orders")
    return {item["name"] for item in constraints if item.get("name")}


def upgrade() -> None:
    existing = _existing_unique_constraints()
    for name, columns in CONSTRAINTS.items():
        if name not in existing:
            op.create_unique_constraint(name, "payment_orders", columns)


def downgrade() -> None:
    existing = _existing_unique_constraints()
    for name in CONSTRAINTS:
        if name in existing:
            op.drop_constraint(name, "payment_orders", type_="unique")
