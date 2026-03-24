#!/usr/bin/env bash
# Free Agents — Demo curl invocation
# Usage: bash demo/demo_request.sh

GATEWAY_URL="http://localhost:4280"
AGENT_ID="draft-from-repo"

curl -s -X POST "${GATEWAY_URL}/agents/${AGENT_ID}/invoke" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "question": "How does this repository support multi-agent orchestration and tool use?",
      "owner": "openai",
      "repo": "openai-agents-python"
    }
  }' | python3 -m json.tool
