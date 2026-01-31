#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:4280}"

echo "==> GET /health"
curl -sS "${BASE_URL}/health" | python3 -m json.tool || true
echo

echo "==> GET /schema"
curl -sS "${BASE_URL}/schema" | python3 -m json.tool || true
echo

echo "==> POST /invoke (summarizer)"
curl -sS -X POST "${BASE_URL}/invoke" \
  -H "Content-Type: application/json" \
  -d '{"input":{"text":"This is a demo input. Please summarize it into a short summary and a few bullets."}}' \
  | python3 -m json.tool || true
echo

echo "==> POST /invoke (classifier)"
curl -sS -X POST "${BASE_URL}/invoke" \
  -H "Content-Type: application/json" \
  -d '{"input":{"items":[{"id":"1","content":"Reset my password"},{"id":"2","content":"Pricing question"}],"categories":["support","sales","other"]}}' \
  | python3 -m json.tool || true
echo

echo "Done."

