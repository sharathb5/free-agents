# Backend Agent Prompt

Use this prompt **after** the testing agent has added tests for the Agent Registry API. Give it to the **backend agent** so it implements the feature and gets all new tests passing.

---

## Prompt

You are the backend agent for the agent-toolbox project (FastAPI, Python). Implement the **Agent Registry API** described in the spec so that the existing pytest tests for it pass. Do not change test expectations; fix the implementation instead.

**Target functionality spec:** Read `docs/target-functionality-spec.md` in this repo. Summary:

- **GET /agents** — 200, body `{ "agents": [ { "id", "name", "description", "primitive", "supports_memory" }, ... ] }`. Discover presets from `app/presets/*.yaml`; for each id call `load_preset(id)` and map to summary. Skip presets that fail to load (log warning).
- **GET /agents/{id}** — 200 with full details (id, version, name, description, primitive, input_schema, output_schema, supports_memory, memory_policy); 404 with NOT_FOUND envelope for unknown or invalid id.
- Use the same `build_error_envelope` and request_id pattern as `app/routers/sessions.py` and `app/main.py`.

**Reference:**

- Progress/checklist: After implementation, create or update `docs/agent-registry-progress.md` mapping requirement IDs (R1, R2, R3) and test IDs (T1–T5) to implementation notes.
- Existing patterns: Session routes in `app/routers/sessions.py` (prefix, error envelope, JSONResponse). Add a new router under `app/routers/` for agents (e.g. `agents.py` with prefix `/agents`), and include it in `app/main.py`.
- Preset loading: `app/preset_loader.py` — `load_preset(id)`, `Preset` dataclass, `PRESETS_DIR`. You may add a function to list preset ids (e.g. from `PRESETS_DIR.glob("*.yaml")` stem) if not already present; do not change the existing contract of `load_preset` or `get_active_preset`.
- Run the test suite: `pytest tests/test_agents.py tests/test_sessions.py tests/test_invoke.py -v` (or `pytest tests/ -v`). All tests must pass.

**Constraints:**

- Keep the API stable: response shapes and status codes must match the spec and the tests.
- 404 for GET /agents/{id} must return a body with the same envelope shape as session 404 (e.g. code NOT_FOUND, message, request_id).
- No auth on these read-only endpoints unless the rest of the app already enforces it for GET.

**Deliverables:**

1. New router `app/routers/agents.py` implementing GET /agents and GET /agents/{id}, registered in `app/main.py`.
2. Any helper (e.g. list preset ids) in `app/preset_loader.py` or in the router, without breaking existing behaviour.
3. All tests in `tests/test_agents.py` (and the rest of `tests/`) passing.
4. Brief update to `docs/agent-registry-progress.md` (or the progress doc the testing agent created) marking R1–R3 and T1–T5 as done.
