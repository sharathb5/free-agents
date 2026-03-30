#!/usr/bin/env python3
"""
Free Agents — Demo invocation script
Invokes a repo-derived agent against langchain-ai/open-agent-platform and prints a clean response.
"""



import json
import sys
import time
import urllib.request
import urllib.error

GATEWAY_URL = "http://localhost:4280"
AGENT_ID    = "langchain_ai_open_agent_platform"
DEMO_AGENT_VERSION = "0.1.0-0fbf08824d"  # deterministic per langchain-ai/open-agent-platform
ENDPOINT    = f"{GATEWAY_URL}/agents/{AGENT_ID}/invoke?version={DEMO_AGENT_VERSION}"

DEFAULT_QUESTION = (
    "How does open-agent-platform define and expose agents, "
    "and what does the tool registry pattern look like?"
)

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
            "owner": "langchain-ai",
            "repo": "open-agent-platform",
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
        # LangChain-style structured outputs often arrive as `output.parameters`.
        parameters = output.get("parameters")
        if isinstance(parameters, dict):
            # Prefer well-known fields first for readability.
            ordered_fields = ["agentsDefinition", "toolRegistryPattern"]
            printed_any = False

            def _print_multiline(label: str, value: str) -> None:
                nonlocal printed_any
                printed_any = True
                print(f"\n  {label}:")
                for line in value.split("\n"):
                    print(f"    {line}" if line.strip() else "")

            for field in ordered_fields:
                v = parameters.get(field)
                if isinstance(v, str) and v.strip():
                    _print_multiline(field, v.strip())

            # Fallback: print any string fields in parameters.
            if not printed_any:
                for k, v in parameters.items():
                    if isinstance(v, str) and v.strip():
                        _print_multiline(str(k), v.strip())
                        break

            # Optionally also show key files if provided.
            key_files = output.get("key_files", [])
            if isinstance(key_files, list) and key_files:
                print(f"\n  Key files:")
                for f in key_files:
                    print(f"    • {f}")
                printed_any = True

            # Final fallback: show raw parameters so the demo never looks blank.
            if not printed_any:
                print("\n  Output parameters:")
                print(json.dumps(parameters, indent=2, ensure_ascii=False)[:4000])
        else:
            # Legacy/freeform outputs.
            printed_any = False

            # Sometimes we get JSON-schema-like wrappers: { "properties": { "answer": "..." } }
            properties = output.get("properties")
            if isinstance(properties, dict):
                wrapped_answer = properties.get("answer")
                if isinstance(wrapped_answer, str) and wrapped_answer.strip():
                    print()
                    for line in wrapped_answer.split("\n"):
                        print(f"  {line}")
                    printed_any = True
                else:
                    # Fallback: print any string field in properties.
                    for k, v in properties.items():
                        if isinstance(v, str) and v.strip():
                            print(f"\n  {k}:")
                            for line in v.split("\n"):
                                print(f"    {line}")
                            printed_any = True
                            break

            if not printed_any:
                answer = output.get("answer", "")
                key_files = output.get("key_files", [])

                if isinstance(answer, str) and answer.strip():
                    print()
                    for line in answer.split("\n"):
                        print(f"  {line}")
                    printed_any = True

                if isinstance(key_files, list) and key_files:
                    print(f"\n  Key files:")
                    for f in key_files:
                        print(f"    • {f}")
                    printed_any = True

            # Final fallback: show raw output.
            if not printed_any:
                print("\n  Output:")
                print(json.dumps(output, indent=2, ensure_ascii=False)[:4000])
    else:
        print(f"\n  {output}")

    print(f"\n{DIVIDER}")
    print(f"  ✓  Done in {elapsed:.1f}s")
    print(DIVIDER)


def main():
    question = " ".join(sys.argv[1:]).strip() or DEFAULT_QUESTION

    print(f"\n{DIVIDER}")
    print(f"  Free Agents — Live Demo")
    print(f"  Repo: langchain-ai/open-agent-platform")
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
