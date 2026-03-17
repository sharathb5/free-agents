# Agent Runtime Part 3: Observability + Streaming + Replay

This document summarizes the Part 3 additions: run-step observability metadata, SSE streaming, run replay, runner instrumentation (latency, error codes, prompt capping), and optional local tail logs.

## Schema (additive)

### run_steps

New nullable columns:

| Column            | Type    | Description                                      |
|-------------------|---------|--------------------------------------------------|
| `event_time`      | TEXT    | Canonical step time (same as created_at if not set) |
| `latency_ms`      | INTEGER | Model call or tool execution latency             |
| `tokens_prompt`   | INTEGER | Placeholder for prompt tokens                    |
| `tokens_completion` | INTEGER | Placeholder for completion tokens             |
| `cost_microusd`   | INTEGER | Placeholder for cost                             |
| `error_code`      | TEXT    | e.g. invalid_action_format, tool_execution_failed, max_steps_exceeded, timeout |

Existing `tool_latency_ms` remains for backward compatibility; `latency_ms` is set for both LLM and tool steps.

### runs

| Column           | Type | Description                    |
|------------------|-----|--------------------------------|
| `parent_run_id`  | TEXT | Set when run was created via replay |

---

## SSE: GET /runs/{run_id}/events

Server-Sent Events stream so clients can watch steps live.

### Query parameters

- **verbose** (default `false`): when true, step events include full `action_json` / `tool_result_json` (redacted and capped). When false, only summary and minimal fields.
- **heartbeat_seconds** (default `10`): send a comment line `: heartbeat` on this interval to keep the connection alive.

### Event types

- **event: run** — `data` JSON:
  - `run_started`: `{"event":"run_started","run_id":"...","status":"running"}`
  - `run_finished`: `{"event":"run_finished","run_id":"...","status":"succeeded"|"failed","error":...}`
- **event: step** — `data` JSON: `run_id`, `step_index`, `step_type`, `latency_ms`, `error_code`; if not verbose, `summary` (e.g. "200 OK (truncated)" for tool_result).
- **event: error** — e.g. run not found.

### Safety and redaction

- All payloads are redacted (secrets, URL tokens) and capped (field length limits).
- Non-verbose step events expose only summary and observability fields, not full tool results or actions.

### Example: curl SSE

```bash
# Start a run in the background (wait=false)
RUN_ID=$(curl -s -X POST http://localhost:4280/agents/summarizer/runs \
  -H "Content-Type: application/json" \
  -d '{"input":{"text":"hello"},"wait":false}' | jq -r '.run_id')

# Stream events (verbose=false, heartbeat every 10s)
curl -s -N "http://localhost:4280/runs/${RUN_ID}/events?heartbeat_seconds=10"
```

Example output:

```
event: run
data: {"event":"run_started","run_id":"...","status":"running"}

event: step
data: {"run_id":"...","step_index":1,"step_type":"llm_action","latency_ms":120}

event: step
data: {"run_id":"...","step_index":2,"step_type":"final","latency_ms":null}

event: run
data: {"event":"run_finished","run_id":"...","status":"succeeded"}
```

---

## Replay: POST /runs/{run_id}/replay

Re-execute a run with the same agent and input, creating a new run linked to the original.

### Body

- **wait** (default `true`): if true, run synchronously and return full result; if false, return immediately with `run_id` and status `queued`.
- **session_id_override** (optional): use this session instead of the original run’s session when writing back.
- **write_back** (default `false`): if true, write back to session (original or override); if false, do not write to session.

### Response

- **run_id**: new run id (≠ original).
- **status**, **output**, **error**, **meta** (when `wait=true`).
- **meta.parent_run_id**: original run id.
- GET /runs/{new_run_id} includes **parent_run_id**.

### Example: curl replay

```bash
# Create a run that succeeds
RESP=$(curl -s -X POST http://localhost:4280/agents/summarizer/runs \
  -H "Content-Type: application/json" \
  -d '{"input":{"text":"replay me"},"wait":true}')
RUN_ID=$(echo "$RESP" | jq -r '.run_id')

# Replay (wait=true, same output expected)
curl -s -X POST "http://localhost:4280/runs/${RUN_ID}/replay" \
  -H "Content-Type: application/json" \
  -d '{"wait":true}'
```

---

## Runner instrumentation

- **Model call latency**: measured per step and stored in `latency_ms` on `llm_action` steps.
- **Tool latency**: stored in both `tool_latency_ms` and `latency_ms` on `tool_result` steps.
- **Failures**: run `status` set to `failed`, `run.error` = `"<error_code>: <safe_message>"`, and an error step appended with `error_code` (e.g. `invalid_action_format`, `tool_execution_failed`, `max_steps_exceeded`, `timeout`).
- **Prompt capping**: `max_tool_prompt_chars` (default 8000) limits the tool result string injected into the prompt; full result is still stored in run_steps.
- **Normalized tool result for model**: HTTP tool result passed to the model includes only `status_code`, `content_type`, `body` (capped), `truncated`, and optional `url`; large header maps are omitted.

---

## Local tail logs (optional)

- **Env**: set `FREE_AGENTS_LOG_PATH` to a file path (e.g. `~/.free_agents/logs.jsonl`) to enable JSONL logging of run events.
- **Rotation**: when the file exceeds 5MB, it is rotated by keeping the last 10k lines.
- **Events**: `run_started`, step summaries (`step` with `summary`, `latency_ms`, `error_code`), `run_finished`. All content is redacted and capped; no secrets are logged.
- **CLI** (agent-toolbox):
  - `agent-toolbox logs tail [--n N]`: print last N lines (default 100) from the log file (default `~/.free_agents/logs.jsonl` if `FREE_AGENTS_LOG_PATH` is not set).
  - `agent-toolbox logs show <run_id>`: print lines that contain the given run_id.

---

## Tests (SQLite mode)

- **Streaming**: start a run with `wait=false`, consume GET /runs/{id}/events and assert at least one step event and a terminal `run_finished` event.
- **Replay**: create a successful run, POST /runs/{id}/replay with `wait=true`, assert new run_id ≠ original, output matches, and `parent_run_id` is present in response and GET run.
- **Latency**: assert a `tool_result` step has `latency_ms` set (mock tool returns quickly).
- **Observability fields**: GET /runs/{id}/steps returns `latency_ms`, `error_code`, `event_time` (or `created_at`) on steps.
- **Prompt cap**: run with a tool result body > `max_tool_prompt_chars` (e.g. 20k chars, cap 500); run succeeds and stored step keeps full result.

Run with SQLite:

```bash
DB_PATH=$(mktemp -d)/gateway.db DATABASE_URL= SUPABASE_DATABASE_URL= pytest -q tests/test_runs.py tests/test_tools_http.py
```
