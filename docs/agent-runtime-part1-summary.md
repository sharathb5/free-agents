# Agent Runtime Part 1 — Summary

Runner loop, run/step persistence, and API endpoints. Tools are stubbed (tool calls fail with a clear message); runtime is structured for plugging in tools next.

## Files changed / added

- **app/models.py** — Added Pydantic models `Run` and `RunStep`.
- **app/config.py** — Added `max_steps` (default 10) and `max_wall_time_seconds` (default 60), env `AGENT_MAX_STEPS` and `AGENT_MAX_WALL_TIME_SECONDS`.
- **app/storage/run_store.py** — New: `init_run_db()`, `create_run()`, `set_run_status()`, `increment_run_step_count()`, `append_run_step()`, `get_run()`, `list_run_steps()`. Tables `runs` and `run_steps` with indexes.
- **app/storage/__init__.py** — Unchanged (run_store not re-exported; routers import from `app.storage.run_store`).
- **app/engine.py** — Extracted `write_back_session_events()`; `process_invoke_for_preset` calls it. Runner uses it after a successful run when session_id and supports_memory are set.
- **app/runtime/__init__.py** — New package; exports `run_runner`.
- **app/runtime/runner.py** — New: action contract (final / tool_call), `ToolRegistry` protocol, `run_runner()` loop with wall-time and max_steps; tools disabled (tool_call → error step and fail).
- **app/routers/runs.py** — New: `GET /runs/{run_id}`, `GET /runs/{run_id}/result`, `GET /runs/{run_id}/steps` (with `verbose` query).
- **app/routers/agents.py** — Added `POST /agents/{agent_id}/runs` (body: input, session_id?, agent_version?, wait?); wait=true runs synchronously, wait=false starts background thread and returns run_id + status queued.
- **app/main.py** — Lifespan: `run_store.init_run_db()`; included `runs_router`.
- **tests/test_runs.py** — New: `test_create_run_wait_true_returns_output_and_succeeded`, `test_run_steps_persisted_and_ordered`, `test_tool_call_action_fails_gracefully_when_tools_disabled`, `test_wait_false_returns_run_id_and_status_then_run_completes`.

## How to run tests

From the project root (agent-toolbox):

```bash
# With venv
source .venv/bin/activate
python -m pytest tests/test_runs.py -v

# Or use Make
make test
```

SQLite is used when `DATABASE_URL` and `SUPABASE_DATABASE_URL` are unset; tests set a temp DB path and seed the registry so agents exist.

## Example curl (wait=true)

```bash
# Start server (e.g. AGENT_PRESET=summarizer PROVIDER=stub)
# Then:

curl -s -X POST http://localhost:4280/agents/summarizer/runs \
  -H "Content-Type: application/json" \
  -d '{"input": {"text": "Hello world"}, "wait": true}'
```

Example response:

```json
{
  "run_id": "uuid-here",
  "status": "succeeded",
  "output": { ... },
  "meta": { "step_count": 1, "session_id": null }
}
```

## Example curl (wait=false)

```bash
curl -s -X POST http://localhost:4280/agents/summarizer/runs \
  -H "Content-Type: application/json" \
  -d '{"input": {"text": "Hello"}, "wait": false}'
```

Example response:

```json
{
  "run_id": "uuid-here",
  "status": "queued"
}
```

Then poll for result:

```bash
curl -s http://localhost:4280/runs/{run_id}/result
# 202 + {"status": "running"} or {"status": "queued"} until done, then 200 + {"output": ...}
```

Get run details and steps:

```bash
curl -s http://localhost:4280/runs/{run_id}
curl -s "http://localhost:4280/runs/{run_id}/steps?verbose=true"
```
