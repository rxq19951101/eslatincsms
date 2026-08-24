#!/usr/bin/env python3
"""Upgrade the database schema through the sole supported entry point: Alembic."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    command.upgrade(config, "head")
    print("✓ 数据库 schema 已升级到 Alembic head")


if __name__ == "__main__":
    main()
