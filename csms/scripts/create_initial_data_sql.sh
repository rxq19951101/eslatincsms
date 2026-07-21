#!/usr/bin/env bash
# Legacy compatibility wrapper. The Python bootstrap is the only supported
# implementation and requires explicit CSMS_BOOTSTRAP_* password variables.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

docker compose -f "$REPO_ROOT/docker-compose.yml" run --rm --no-deps \
    --entrypoint python csms /app/scripts/create_initial_data.py
