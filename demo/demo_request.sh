#!/usr/bin/env bash
# Free Agents — Demo curl invocation (langchain-ai/open-agent-platform)
# Usage: bash demo/demo_request.sh

GATEWAY_URL="http://localhost:4280"
AGENT_ID="langchain_ai_open_agent_platform"
AGENT_VERSION="0.1.0-0fbf08824d"

curl -s -X POST "${GATEWAY_URL}/agents/${AGENT_ID}/invoke?version=${AGENT_VERSION}" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "question": "How does open-agent-platform define and expose agents, and what does the tool registry pattern look like?",
      "owner": "langchain-ai",
      "repo": "open-agent-platform"
    }
  }' | python3 -m json.tool
