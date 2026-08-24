#!/usr/bin/env bash
# Legacy compatibility wrapper. Keep all bootstrap behavior in the canonical
# Python script so hashing, password bounds, and secret handling cannot drift.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

docker compose -f "$REPO_ROOT/docker-compose.yml" run --rm --no-deps \
    --entrypoint python csms /app/scripts/create_initial_data.py
