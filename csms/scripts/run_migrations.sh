#!/usr/bin/env bash
# Run Alembic migrations (upgrade to head)
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
alembic upgrade head
