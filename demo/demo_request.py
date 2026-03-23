#!/usr/bin/env python3
"""
Free Agents — Demo invocation script
Sends a question to the openai-agents-python agent and prints a clean response.
"""



import json
import sys
import time
import urllib.request
import urllib.error

GATEWAY_URL = "http://localhost:4280"
AGENT_ID    = "draft-from-repo"
ENDPOINT    = f"{GATEWAY_URL}/agents/{AGENT_ID}/invoke"

DEFAULT_QUESTION = "How does this repository support multi-agent orchestration and tool use?"

DIVIDER = "─" * 56


def check_gateway():
    try:
        urllib.request.urlopen(f"{GATEWAY_URL}/agents/{AGENT_ID}", timeout=3)
    except urllib.error.HTTPError:
        pass  # 4xx is fine — gateway is up
    except Exception as e:
        print(f"\n  ✗  Gateway not reachable at {GATEWAY_URL}")
        print(f"     Start it with:  AGENT_PRESET={AGENT_ID} agent-toolbox")
        print(f"     or:             make run AGENT={AGENT_ID}\n")
        sys.exit(1)


def invoke(question: str) -> dict:
    ###
    # free-agents logic: POST to the agent invoke endpoint with a structured input payload.
    # The agent was generated from a real GitHub repo and is now callable as an API.
    payload = json.dumps({
        "input": {
            "question": question,
            "owner": "openai",
            "repo": "openai-agents-python",
        }
    }).encode()

    ###
    # free-agents logic: the endpoint format is /agents/{agent_id}/invoke —
    # every saved agent gets its own callable HTTP endpoint through the local gateway.
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def print_response(data: dict, elapsed: float):
    output = data.get("output", data)

    print(f"\n{DIVIDER}")
    print(f"  Agent: {AGENT_ID}")
    print(DIVIDER)

    if isinstance(output, dict):
        answer = output.get("answer", "")
        key_files = output.get("key_files", [])

        if answer:
            print()
            for line in answer.split("\n"):
                print(f"  {line}")

        if key_files:
            print(f"\n  Key files:")
            for f in key_files:
                print(f"    • {f}")
    else:
        print(f"\n  {output}")

    print(f"\n{DIVIDER}")
    print(f"  ✓  Done in {elapsed:.1f}s")
    print(DIVIDER)


def main():
    question = " ".join(sys.argv[1:]).strip() or DEFAULT_QUESTION

    print(f"\n{DIVIDER}")
    print(f"  Free Agents — Live Demo")
    print(f"  POST {ENDPOINT}")
    print(f"{DIVIDER}")
    print(f"\n  Question: {question}\n")

    check_gateway()

    print("  → Invoking agent...", flush=True)
    t0 = time.time()

    try:
        data = invoke(question)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\n  ✗  HTTP {e.code}: {body}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ✗  Error: {e}\n")
        sys.exit(1)

    print_response(data, time.time() - t0)


if __name__ == "__main__":
    main()
