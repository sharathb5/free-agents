# Testing Agent Prompt

Copy the text below and give it to the **testing agent** to build tests for the target functionality defined in the spec. Run the testing agent first; then use the backend agent prompt so the backend is implemented to pass these tests.

---

## Prompt

You are the testing agent for the agent-toolbox backend (FastAPI, Python). Your job is to write a strict pytest test suite that defines the target behaviour for the **Agent Registry API**. Do not implement backend code; only add or extend tests under `tests/`.

**Target functionality spec:** Read `docs/target-functionality-spec.md` in this repo. It defines:

- **R1.** `GET /agents` — returns 200 with body `{ "agents": [ ... ] }`; each agent summary has `id`, `name`, `description`, `primitive`, `supports_memory`.
- **R2.** `GET /agents/{id}` — returns 200 with full agent details (id, version, name, description, primitive, input_schema, output_schema, supports_memory, memory_policy); 404 for unknown id with error envelope (e.g. NOT_FOUND).
- **R3.** Same error-envelope and request_id pattern as existing session routes.

The spec also lists acceptance criteria **T1–T5** in §2. Your tests must cover every requirement (R1, R2, R3) and every acceptance criterion (T1–T5).

**Constraints:**

- Use the existing app: `from fastapi.testclient import TestClient` and the app from `app.main` (e.g. `from app.main import app`). Ensure the test client is used so that lifespan runs and any DB is initialized if needed.
- Add a new test file `tests/test_agents.py` for the registry endpoints. Do not modify existing session or invoke behaviour.
- Each of T1–T5 should map to at least one clearly named test (e.g. `test_get_agents_returns_200_with_agents_list`, `test_get_agents_id_returns_404_for_unknown_id`).
- Tests must not depend on a specific number of presets (e.g. assert `len(data["agents"]) >= 1` for T2, or use a known preset id like `summarizer` that exists in `app/presets/`).
- For T5 (memory_policy shape), use a preset that has `memory_policy` in YAML (e.g. summarizer) and optionally one that does not; assert on presence and shape of `memory_policy` in the response.

**Deliverables:**

1. New file `tests/test_agents.py` containing pytest tests that implement T1–T5 and cover R1–R3.
2. A short checklist in `docs/agent-registry-progress.md` (or append to an existing progress doc) mapping T1–T5 to test names and file paths.
3. Run `pytest tests/test_agents.py -v`. Tests should fail with clear errors (e.g. 404 Not Found, or no route GET /agents) until the backend implements the Agent Registry API.

Do not implement the registry routes or change `app/preset_loader.py` beyond what is needed to make the tests runnable; the backend agent will implement the feature.
