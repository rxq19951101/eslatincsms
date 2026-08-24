#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export REVIEW_EMAIL="${REVIEW_EMAIL:-review@eslatin.com.co}"
export REVIEW_PASSWORD="${REVIEW_PASSWORD:-Review2026!}"
export REVIEW_BALANCE="${REVIEW_BALANCE:-50000}"
python3 scripts/create_app_review_account.py
