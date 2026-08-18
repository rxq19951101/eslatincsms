"""Add PAY-MP-002 BE-205 risk authority facts.

The migration is additive and intentionally has a non-destructive downgrade.
No Invoice, Payment, ChargingSession, MeterValue or OCPP fact is imported or
rewritten.  Runtime policy rows are created explicitly by an approved
operator/application workflow; this migration never seeds a default policy.
"""

from alembic import op

from app.database.models import Base


# Keep this identifier within the existing alembic_version.version_num(32)
# compatibility boundary.  It is unique in this migration graph.
revision = "013_be205_risk"
down_revision = "012_pay_mp_002_be201"
branch_labels = None
depends_on = None


RISK_TABLES = (
    "risk_policy_versions",
    "risk_exposure_balances",
    "risk_reservations",
    "risk_ledger_entries",
    "risk_stop_actions",
    "provider_resolutions",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in RISK_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    # Rollback disables the new runtime at application level.  Risk facts are
    # retained for audit, reconciliation and safe recovery; an explicit future
    # archival decision is required before any physical table removal.
    pass
