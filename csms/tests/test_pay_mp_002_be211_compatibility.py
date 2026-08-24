"""BE-211 local/test schema and cleanup compatibility evidence.

These checks intentionally exercise ``Base.metadata.create_all`` only against
isolated test databases.  PAY-MP-002 production schema changes remain owned by
the existing migration/architecture gates and are not created here.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.database.base import Base
from app.database.models import Tenant


def test_be211_empty_schema_create_all_is_repeatable_and_non_destructive(tmp_path: Path):
    """An empty local schema can start twice without dropping unrelated rows."""

    database_path = tmp_path / "be211-empty.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}")

    Base.metadata.create_all(bind=engine)
    first_tables = set(inspect(engine).get_table_names())
    assert {"tenants", "outbox_events", "runtime_rail_controls"}.issubset(first_tables)

    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE be211_sentinel (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        )
        connection.execute(text("INSERT INTO be211_sentinel (value) VALUES ('keep-me')"))

    Base.metadata.create_all(bind=engine)
    second_tables = set(inspect(engine).get_table_names())
    assert first_tables.issubset(second_tables)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT value FROM be211_sentinel WHERE id = 1")
        ).scalar_one() == "keep-me"

    engine.dispose()


def test_be211_current_test_schema_repeat_does_not_clear_existing_fact(
    db_session, sample_tenant
):
    """The shared test schema keeps facts when startup initialization repeats."""

    tenant_count_before = db_session.query(Tenant).count()
    Base.metadata.create_all(bind=db_session.get_bind())
    db_session.expire_all()
    assert db_session.query(Tenant).count() == tenant_count_before
    assert db_session.get(Tenant, sample_tenant.id) is not None


def test_be211_cleanup_refuses_non_test_environment(monkeypatch):
    """The deterministic cleanup command cannot be pointed at production."""

    from scripts import cleanup_sim_e2e

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(SystemExit, match="disabled outside development/test"):
        cleanup_sim_e2e.ensure_safe_environment(apply=False)


def test_be211_cleanup_scope_is_allowlist_not_tenant_wide():
    """The cleanup predicate remains reference-ID based, not tenant based."""

    from app.database.models import Tenant
    from scripts import cleanup_sim_e2e

    predicate = cleanup_sim_e2e.table_scope_condition(Tenant.__table__)
    compiled = str(predicate.compile(compile_kwargs={"literal_binds": True}))
    assert "tenant_id" not in compiled
    assert "id IN" in compiled
