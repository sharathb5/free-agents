# Agent Runtime Part 2 — First Real Tool (HTTP) + Tool Execution Loop

Summary of the HTTP tool implementation, tool registry, runner integration, and how to enable tools locally.

## What was added

- **Config** ([app/config.py](app/config.py)): `tools_enabled`, `max_tool_calls`, `http_timeout_seconds`, `http_max_response_chars`, `http_allowed_domains_default` (env: `AGENT_TOOLS_ENABLED`, `AGENT_MAX_TOOL_CALLS`, `AGENT_HTTP_TIMEOUT_SECONDS`, `AGENT_HTTP_MAX_RESPONSE_CHARS`, `AGENT_HTTP_ALLOWED_DOMAINS`).
- **Preset/registry**: Optional `allowed_tools` (e.g. `["http_request"]`) and `http_allowed_domains` (e.g. `["api.example.com"]`) on presets and stored in agent spec.
- **app/runtime/tools/http_tool.py**: `execute_http_request(args, policy)`, `HttpPolicy`, `ToolExecutionError`. Validates method/url/headers/query/json/data; enforces https and domain allowlist; strips Authorization/Cookie; applies timeout and response cap; returns redacted result.
- **app/runtime/tools/registry.py**: `DefaultToolRegistry`, `RunContext`, `build_run_context`. Registry executes `http_request` and enforces tools_enabled, allowed_tools, max_tool_calls, and domain allowlist.
- **Runner** ([app/runtime/runner.py](app/runtime/runner.py)): When `tool_registry` is set, tool_call steps are executed, tool_result steps appended, and tool results are fed back into the prompt for the next step until final or limits.
- **Runs API**: Run response meta includes `tool_calls_used` and `max_tool_calls`. Steps and tool args/results remain redacted/capped when using `?verbose=true`.

## How to enable tools locally

1. **Environment**
   - Set `AGENT_TOOLS_ENABLED=true` (or leave unset; default is true).
   - Set `AGENT_HTTP_ALLOWED_DOMAINS` to a comma-separated list of allowed hostnames, e.g.:
     - `AGENT_HTTP_ALLOWED_DOMAINS=api.open-meteo.com,api.example.com`
   - Optional: `AGENT_MAX_TOOL_CALLS=5`, `AGENT_HTTP_TIMEOUT_SECONDS=15`, `AGENT_HTTP_MAX_RESPONSE_CHARS=50000`.

2. **Per-agent allowlist**
   - In the agent preset/spec (YAML or registry), set:
     - `allowed_tools: ["http_request"]`
     - `http_allowed_domains: ["api.foo.com", "example.com"]`
   - If `http_allowed_domains` is omitted, the config default `AGENT_HTTP_ALLOWED_DOMAINS` is used (empty = deny all unless set).

3. **Example: run with tools**
   - Use an agent that has `allowed_tools: ["http_request"]` and at least one domain in `http_allowed_domains` (or in `AGENT_HTTP_ALLOWED_DOMAINS`).
   - Start the server and call `POST /agents/{agent_id}/runs` with `wait=true` or `wait=false` as in Part 1.

## Example curl (agent that uses http_request)

Prerequisite: an agent (e.g. `tool_agent` from `app/presets/tool_agent.yaml`) with `allowed_tools: ["http_request"]` and `http_allowed_domains` including a domain you allow (e.g. `example.com`). Start the server with tools enabled and the same DB so the agent is seeded.

```bash
# Start server (tools enabled by default; set allowed domains if needed)
export AGENT_HTTP_ALLOWED_DOMAINS=example.com,api.open-meteo.com
# Optional: AGENT_TOOLS_ENABLED=true
uvicorn app.main:app --host 0.0.0.0 --port 4280
```

```bash
# Run (synchronous). The model will receive instructions to use http_request when needed.
curl -s -X POST http://localhost:4280/agents/tool_agent/runs \
  -H "Content-Type: application/json" \
  -d '{"input": {"query": "Fetch the weather for Paris"}, "wait": true}'
```

Example response shape (run that used the tool):

```json
{
  "run_id": "...",
  "status": "succeeded",
  "output": { "result": "..." },
  "meta": {
    "step_count": 3,
    "tool_calls_used": 1,
    "max_tool_calls": 5
  }
}
```

Get steps (including tool_call and tool_result):

```bash
curl -s "http://localhost:4280/runs/{run_id}/steps?verbose=true"
```

## Safety model

- **Allowlist**: Only hostnames in `http_allowed_domains` (per agent or config default) are allowed. Exact match or suffix match (e.g. `.example.com` for subdomains) depending on implementation.
- **HTTPS**: Requests must use `https` unless the host is localhost and allowlist includes it (for dev/tests).
- **Headers**: `Authorization` and `Cookie` are never sent; they are stripped from the request. Stored tool args are redacted (e.g. via `redact_secrets`) before persistence.
- **Caps**: Response body is truncated to `http_max_response_chars`; response and stored step data are redacted and capped for logs/API.
- **Limits**: `max_tool_calls` per run and `http_timeout_seconds` per request to avoid runaway or long-lived calls.

## Tests

Run runtime and HTTP tool tests (SQLite, mocked HTTP):

```bash
source .venv/bin/activate
python -m pytest tests/test_runs.py tests/test_tools_http.py -v
```

Or the full suite:

```bash
python -m pytest tests/ -q
```

## Files touched (Part 2)

| Area | Files |
|------|--------|
| Config | [app/config.py](app/config.py) — tool-related settings and env |
| Preset / registry | [app/preset_loader.py](app/preset_loader.py), [app/registry_adapter.py](app/registry_adapter.py), [app/storage/registry_store.py](app/storage/registry_store.py) — allowed_tools, http_allowed_domains |
| Tools | [app/runtime/tools/http_tool.py](app/runtime/tools/http_tool.py), [app/runtime/tools/registry.py](app/runtime/tools/registry.py), [app/runtime/tools/__init__.py](app/runtime/tools/__init__.py) |
| Runner | [app/runtime/runner.py](app/runtime/runner.py) — tool execution loop, prompt with tool results |
| API | [app/routers/agents.py](app/routers/agents.py) — pass DefaultToolRegistry when tools_enabled; meta tool_calls_used, max_tool_calls |
| Presets | [app/presets/tool_agent.yaml](app/presets/tool_agent.yaml) — test preset with http_request allowed |
| Tests | [tests/test_tools_http.py](tests/test_tools_http.py) — happy path, domain deny, header stripping, max_tool_calls, timeout |
