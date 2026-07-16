#!/usr/bin/env bash
# Gate 2 probe: production API + legal pages
set -euo pipefail
BASE="${EXPO_PUBLIC_API_URL:-https://api.eslatin.com.co}"
BASE="${BASE%/}"

check() {
  local url="$1"
  local code
  code=$(curl -sL -o /dev/null -w "%{http_code}" --connect-timeout 10 "$url" || echo "000")
  printf "%s  %s\n" "$code" "$url"
  [[ "$code" =~ ^2 ]]
}

ok=0
echo "Probing $BASE ..."
check "$BASE/legal/privacy.html" && ok=$((ok+1)) || true
check "$BASE/legal/terms.html" && ok=$((ok+1)) || true
check "$BASE/docs" && ok=$((ok+1)) || true
check "$BASE/health" && ok=$((ok+1)) || true
check "$BASE/api/v1/health" && ok=$((ok+1)) || true

echo "---"
if [[ "$ok" -ge 2 ]]; then
  echo "Gate2 legal/API: PARTIAL/OK ($ok endpoints returned 2xx)"
  exit 0
fi
echo "Gate2 legal/API: FAIL (need deploy HTTPS + /legal/*.html)"
exit 1
