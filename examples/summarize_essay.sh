#!/usr/bin/env bash
# Summarize the essay(s) in essays.txt via the summarizer agent.
# Usage: ./summarize_essay.sh   (from repo root or examples/)
# Requires: backend running on http://localhost:4280 (AGENT_PRESET=summarizer)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ESSAY_FILE="${SCRIPT_DIR}/essays.txt"
BASE_URL="${BASE_URL:-http://localhost:4280}"

if [[ ! -f "$ESSAY_FILE" ]]; then
  echo "Error: $ESSAY_FILE not found."
  exit 1
fi

# Build JSON with Python so quotes/newlines in the file are safe
PAYLOAD=$(python3 -c '
import json, sys
with open(sys.argv[1], "r") as f:
    text = f.read()
print(json.dumps({"input": {"text": text}}))
' "$ESSAY_FILE")

echo "==> POST /invoke (summarizer) with essays.txt"
curl -sS -X POST "${BASE_URL}/invoke" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  | python3 -m json.tool || true
echo
echo "Done."
