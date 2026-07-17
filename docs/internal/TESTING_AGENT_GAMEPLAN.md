# Testing Agent Game Plan

## 1. Purpose

This document is the **single source of truth** for the testing agent’s:
- Understanding of the runtime contract.
- Current test coverage status.
- Known gaps and next testing tasks.

The testing agent MUST:
- Read this file at the start of each session.
- Update it whenever it adds or significantly changes tests.

---

## 2. Runtime Contract (Read-Only Summary)

- **Service**: Standardized Agent Runtime (FastAPI)
- **Port**: 4280 (everywhere: uvicorn, Dockerfile, docker-compose, README examples)

### 2.1 Endpoints

- `GET /`  
  - Returns:  
    `{ "service": "agent-gateway", "agent": "<id>", "version": "<version>", "docs": "/docs", "schema": "/schema", "health": "/health" }`

- `GET /health`  
  - Normal: 200, includes at least `status`, `agent`, `version`.

- `GET /schema`  
  - Returns: `{ agent, version, primitive, input_schema, output_schema }`  
  - Must read ONLY from loaded preset (no provider calls).

- `POST /invoke`  
  - Request: `{ "input": <object> }` validated with jsonschema.
  - Flow: `auth → validate input → engine/router → primitive → provider → validate output → (repair once) → response`.

- `POST /stream`  
  - 501 Not Implemented with standard error envelope.

### 2.2 Envelopes & Status Codes

- **Success**:  
  `{ "output": <object>, "meta": { "request_id", "agent", "version", "latency_ms" } }`

- **Error**:  
  `{ "error": { "code", "message", "details" }, "meta": { "request_id", "agent", "version" } }`

- **Status codes + error.code**:
  - 400 → `"MALFORMED_REQUEST"`
  - 422 (input) → `"INPUT_VALIDATION_ERROR"`
  - 422 (output after repair) → `"OUTPUT_VALIDATION_ERROR"`
  - 401 → `"UNAUTHORIZED"`
  - 500 → `"INTERNAL_ERROR"`

### 2.3 Presets (Schema Highlights)

- `summarizer` (transform)  
  - input: `{ text: string }`  
  - output: `{ summary: string, bullets: string[] }`

- `meeting_notes` (extract)  
  - input: `{ transcript: string }`  
  - output: `{ summary: string, decisions: string[], action_items: { owner: string, task: string, deadline: string }[] }`

- `extractor` (extract)  
  - input: `{ text: string, schema: { [field_name: string]: string /* description */ } }`  
  - output: `{ data: object, confidence: number [0,1] }`  
  - `output.data` MUST include keys for each field_name in `input.schema`.

- `classifier` (classify)  
  - input: `{ items: { id: string, content: string }[], categories: string[] }`  
  - output: `{ classifications: { item_id: string, category: string, confidence: number [0,1] }[] }`

- `triage` (classify)  
  - input: `{ email_content: string, mailbox_context: string }`  
  - output: `{ category: string, priority: string, should_escalate: boolean, draft_response: string }`

---

## 3. Test Coverage Checklist

### 3.1 Preset YAML + Schemas

- [x] All preset YAMLs exist (`summarizer`, `meeting_notes`, `extractor`, `classifier`, `triage`).
- [x] Each preset has required keys: `id`, `version`, `primitive`, `input_schema`, `output_schema`, `prompt`.
- [x] `id` matches filename.
- [x] `input_schema` and `output_schema` pass `Draft7Validator.check_schema`.
- [x] `meeting_notes.action_items` shape verified.
- [x] `triage.mailbox_context` is `string`.
- [x] `classifier.items` / `classifications` shapes verified.
- [x] `extractor.schema` and `output.data`/`confidence` verified.

### 3.2 Auth

- [x] `AUTH_TOKEN` set + no Authorization → 401 `UNAUTHORIZED`.
- [x] `AUTH_TOKEN` set + wrong token → 401 `UNAUTHORIZED`.
- [x] `AUTH_TOKEN` unset/empty → `/invoke` without Authorization is **not** 401.
- [x] `AUTH_TOKEN` set + correct token → `/invoke` is **not** 401.

### 3.3 /invoke Success

- [x] With `PROVIDER=stub`, `AGENT_PRESET=summarizer` → valid input returns 200 + success envelope.
- [x] With `PROVIDER=stub`, `AGENT_PRESET=classifier` → valid input returns 200 + success envelope.
- [x] Meta fields (`request_id`, `agent`, `version`, `latency_ms`) asserted.

### 3.4 Input Errors

- [x] Malformed JSON → 400 `MALFORMED_REQUEST` + meta.
- [x] Missing required fields → 422 `INPUT_VALIDATION_ERROR` + non-empty `details`.

### 3.5 Output Validation & Repair

- [x] Test: first provider output invalid, repair output valid → 200, exactly one repair, output valid.
- [x] Test: both provider outputs invalid → 422 `OUTPUT_VALIDATION_ERROR` + meta.

### 3.6 Other Endpoints

- [x] `GET /` → 200, correct keys (`service`, `agent`, `version`, `docs`, `schema`, `health`).
- [x] `GET /schema` → 200, matches loaded preset.
- [x] `GET /health` → 200 with `status`, `agent`, `version`.
- [x] `POST /stream` → 501, standard error envelope present.

### 3.7 Meta & 500 Errors

- [x] At least one test induces 500 `INTERNAL_ERROR` and asserts error envelope + meta.

### 3.8 Port / Docs Consistency (later)

- [ ] Dockerfile, docker-compose, README all use port 4280; no 8000 left.

---

## 4. Progress Log

> The testing agent MUST append brief entries here as it works.

- YYYY-MM-DD HH:MM – [agent-id or “testing-agent”] – Short note about tests added/changed and which checklist items were completed.

Example:
- 2026-01-28 15:10 – testing-agent – Implemented auth tests and basic /invoke happy path; filled sections 3.2 and 3.3.

- 2026-01-28 15:30 – testing-agent – Added preset YAML/schema tests and /invoke auth, success path, and input error tests; checked off sections 3.1–3.4 and aligned auth/meta expectations with runtime contract.
- 2026-01-28 16:00 – testing-agent – Added tests for output validation/repair loop, 500 INTERNAL_ERROR surface, and endpoints /, /schema, /health, /stream; completed checklist items 3.5–3.7 and standardized 501 as NOT_IMPLEMENTED.

---

## 5. Open Gaps / Issues

> The monitoring agent can update this when it detects missing coverage or spec drift.  
> The testing agent should read and address these items.

- [ ] Example: No tests yet for /stream 501 behavior. (RESOLVED – covered by `test_stream_endpoint_not_implemented_returns_501` in `tests/test_invoke.py`; keep here as a template for future gaps.)
- [ ] Example: Output repair loop not covered; need positive + negative tests. (RESOLVED – covered by repair tests in `tests/test_invoke.py`; kept as example wording.)

---

## 6. Next Actions (for Testing Agent)

> Concrete, near-term tasks the testing agent should do next.  
> Updated by monitoring agent and testing agent as work progresses.

- [ ] Write any additional tests needed if the runtime implementation diverges from the current contract (monitor spec drift).
- [ ] Add future regression tests when new primitives, presets, or providers are introduced.

