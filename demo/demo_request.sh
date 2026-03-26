#!/usr/bin/env bash
# Free Agents — Demo curl invocation (langchain-ai/open-agent-platform)
# Usage: bash demo/demo_request.sh

GATEWAY_URL="http://localhost:4280"
AGENT_ID="draft-from-repo"

curl -s -X POST "${GATEWAY_URL}/agents/${AGENT_ID}/invoke" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "question": "How does open-agent-platform define and expose agents, and what does the tool registry pattern look like?",
      "owner": "langchain-ai",
      "repo": "open-agent-platform"
    }
  }' | python3 -m json.tool
