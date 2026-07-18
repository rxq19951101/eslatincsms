#!/usr/bin/env python3
"""Lightweight model metadata audit; schema creation belongs to Alembic."""

from sqlalchemy.dialects.postgresql import UUID

from app.database.base import Base
import app.database.models  # noqa: F401 - register all tables


def test_models():
    assert Base.metadata.tables
    for table in Base.metadata.sorted_tables:
        primary_keys = list(table.primary_key.columns)
        assert primary_keys, f"{table.name} has no primary key"
        assert all(isinstance(column.type, UUID) for column in primary_keys), (
            f"{table.name} has a non-UUID primary key"
        )


if __name__ == "__main__":
    test_models()
    print("✓ model metadata audit passed")
