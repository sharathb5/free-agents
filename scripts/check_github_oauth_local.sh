#!/usr/bin/env bash
# Hit a running gateway and print GitHub OAuth wiring. Usage:
#   ./scripts/check_github_oauth_local.sh
#   ./scripts/check_github_oauth_local.sh http://127.0.0.1:4280
# Optional: GITHUB_OAUTH_RETURN_TO=http://127.0.0.1:3000
set -euo pipefail
BASE="${1:-http://localhost:4280}"
RT="${GITHUB_OAUTH_RETURN_TO:-http://localhost:3000}"

echo "=== GET ${BASE}/github/oauth/debug ==="
curl -sS "${BASE}/github/oauth/debug" | python3 -m json.tool
echo
echo "=== GET oauth/start (return_to=${RT}) ==="
curl -sS -G "${BASE}/github/oauth/start" --data-urlencode "return_to=${RT}" | python3 -m json.tool
