#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/Users/sharath/agent-toolbox/agent-toolbox"
cd "$BASE_DIR"

source .venv/bin/activate

PORT=4280
BASE_URL="http://localhost:${PORT}"

# Function to test an agent
test_agent() {
    local preset=$1
    local input_json=$2
    local description=$3
    
    echo ""
    echo "=========================================="
    echo "Testing: $preset - $description"
    echo "=========================================="
    
    # Start server in background
    AGENT_PRESET="$preset" PROVIDER=stub uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > /tmp/uvicorn_${preset}.log 2>&1 &
    local server_pid=$!
    
    # Wait for server to start (check until ready)
    for i in {1..10}; do
        if curl -sS "${BASE_URL}/health" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # Test /health
    echo "→ GET /health"
    curl -sS "${BASE_URL}/health" | python3 -m json.tool || echo "FAILED"
    echo ""
    
    # Test /schema
    echo "→ GET /schema"
    curl -sS "${BASE_URL}/schema" | python3 -m json.tool | head -20 || echo "FAILED"
    echo ""
    
    # Test /invoke
    echo "→ POST /invoke"
    curl -sS -X POST "${BASE_URL}/invoke" \
        -H "Content-Type: application/json" \
        -d "$input_json" | python3 -m json.tool || echo "FAILED"
    echo ""
    
    # Kill server
    kill $server_pid 2>/dev/null || true
    sleep 1
}

# Test all 5 agents
test_agent "summarizer" \
    '{"input":{"text":"This is a test paragraph that should be summarized into a concise summary and bullet points."}}' \
    "Text summarization"

test_agent "classifier" \
    '{"input":{"items":[{"id":"1","content":"Reset my password"},{"id":"2","content":"Pricing question"}],"categories":["support","sales","other"]}}' \
    "Item classification"

test_agent "meeting_notes" \
    '{"input":{"transcript":"Today we decided to launch v1 next week and assign Alice to write the README. We also discussed the API contract."}}' \
    "Meeting notes extraction"

test_agent "extractor" \
    '{"input":{"text":"Acme Corp signed a contract on Jan 1, 2025 with a value of $10,000.","schema":{"customer_name":"Name of the customer","contract_date":"Date the contract was signed","contract_value":"Monetary value of the contract"}}}' \
    "Structured data extraction"

test_agent "triage" \
    '{"input":{"email_content":"Urgent: our production server is down.","mailbox_context":"On-call support mailbox"}}' \
    "Email triage"

echo ""
echo "=========================================="
echo "All agents tested!"
echo "=========================================="
