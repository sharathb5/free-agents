# Target Functionality Spec: Agent Registry API

This spec defines the **Agent Registry API**: read-only endpoints to list and fetch agent (preset) metadata. Agents are discovered from `app/presets/*.yaml`. The gateway continues to run a single active preset for `/invoke` (via `AGENT_PRESET`); the registry is for discovery only.

**Reference implementation:** `app/preset_loader.py` (Preset, load_preset, PRESETS_DIR). New routes live in `app/routers/` and follow the same error-envelope style as `app/routers/sessions.py`.

---

## 1. Requirements

### R1. GET /agents — List agents

- **Method/Path:** `GET /agents`
- **Success:** `200 OK`
- **Response body:** JSON object with key `agents`, value is an array of agent summary objects. Each summary has:
  - `id` (string): preset id
  - `name` (string): from preset name
  - `description` (string): from preset description
  - `primitive` (string): e.g. transform, extract, classify
  - `supports_memory` (boolean): from preset
- **Order:** Any stable order (e.g. by id).
- **Source:** Discover preset ids from `app/presets/*.yaml` (filename stem = id). For each id, call `load_preset(id)` and map to the summary shape. If `load_preset` raises for one file, that preset is skipped (log warning) and the rest are still returned; if all fail, return empty list or 500 per existing envelope style.
- **Errors:** Use existing envelope for 500 (e.g. INTERNAL_ERROR) only when appropriate (e.g. presets dir missing). No auth required.

### R2. GET /agents/{id} — Get one agent

- **Method/Path:** `GET /agents/{id}`
- **Path parameter:** `id` — preset id (e.g. summarizer, triage).
- **Success:** `200 OK`
- **Response body:** JSON object with full agent details:
  - `id`, `version`, `name`, `description`, `primitive`
  - `input_schema`, `output_schema` (objects)
  - `supports_memory` (boolean)
  - `memory_policy` (object or null): if preset has memory_policy, `{ "mode", "max_messages", "max_chars" }`; else `null`
- **Not found:** `404 Not Found` when preset id does not exist or `load_preset(id)` raises (e.g. file not found, invalid YAML). Response body: same error envelope as sessions (code NOT_FOUND, message, request_id).
- **No auth required.**

### R3. Consistency

- Use the same `build_error_envelope` / request_id pattern as in `app/main.py` and `app/routers/sessions.py` for 404/500.
- CORS: already applied at app level; no change.

---

## 2. Acceptance criteria (for tests)

| ID   | Requirement | Acceptance |
|------|-------------|------------|
| T1   | GET /agents returns 200 | Status 200, body has key `agents`, value is array. |
| T2   | GET /agents returns at least one agent | Length of `agents` >= 1; each element has `id`, `name`, `description`, `primitive`, `supports_memory`. |
| T3   | GET /agents/{id} returns 200 for valid id | For a known preset id (e.g. summarizer), status 200; body has `id`, `version`, `name`, `description`, `primitive`, `input_schema`, `output_schema`, `supports_memory`, `memory_policy`. |
| T4   | GET /agents/{id} returns 404 for unknown id | For id that does not exist (e.g. nonexistent-preset-123), status 404; body has error code (e.g. NOT_FOUND) and message. |
| T5   | GET /agents/{id} memory_policy shape | When preset has memory_policy (e.g. summarizer), response includes `memory_policy` with `mode`, `max_messages`, `max_chars`; when not set, `memory_policy` is null or omitted. |

---

## 3. Out of scope (this phase)

- Authentication/authorization on registry endpoints.
- Mutations (register/update/delete agents).
- Pagination or filtering on GET /agents (return all discovered presets).
