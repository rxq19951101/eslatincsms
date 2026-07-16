#!/usr/bin/env bash
# Production iOS build + submit (run after: eas login, secrets, Gate2, U5 in eas.json)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Checking eas.json Apple placeholders"
if grep -q 'YOUR_APPLE_ID@example.com\|YOUR_TEAM_ID\|"ascAppId": "0000000000"' eas.json; then
  echo "ERROR: Fill submit.production.ios in eas.json (appleId, appleTeamId, ascAppId) before submit."
  echo "You can still build without submit. Continuing build only..."
  BUILD_ONLY=1
else
  BUILD_ONLY=0
fi

echo "==> eas build --profile production --platform ios"
npx eas-cli@latest build --profile production --platform ios --non-interactive

if [[ "$BUILD_ONLY" -eq 0 ]]; then
  echo "==> eas submit --platform ios --profile production"
  npx eas-cli@latest submit --platform ios --profile production --latest --non-interactive
else
  echo "Skipped submit. After filling Apple fields, run:"
  echo "  npx eas-cli@latest submit --platform ios --profile production --latest"
fi
