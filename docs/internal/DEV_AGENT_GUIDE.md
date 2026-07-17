# Dev Agent Guide

## 1. Purpose

This document defines the **implementation contract** and working style for the backend dev agent.
It must be treated as the primary guide when creating or modifying backend code.

The dev agent SHOULD:
- Read this file at the start of each session.
- Keep implementation aligned with the runtime contract and the tests in `tests/`.
- Prefer the simplest implementation that fully satisfies the external contract.

---

## 2. High-Level Architecture

- **Service**: Standardized Agent Runtime (FastAPI gateway).
- **Port**: 4280 for all runtime entrypoints:
  - Uvicorn `--port 4280`.
  - Dockerfile `EXPOSE 4280`.
  - docker-compose service port 4280.
  - README curl examples use `http://localhost:4280`.

### 2.1 Endpoints

The FastAPI app must expose:

- `GET /`
  - Returns a small metadata document:
    ```json
    {
      "service": "agent-gateway",
      "agent": "<id>",
      "version": "<version>",
      "docs": "/docs",
      "schema": "/schema",
      "health": "/health"
    }
    ```

- `GET /health`
  - Normal case: 200, JSON includes at least:
    - `status` (string, `"ok"` on happy path),
    - `agent` (current preset id),
    - `version` (preset version string).

- `GET /schema`
  - Returns:
    ```json
    {
      "agent": "<preset id>",
      "version": "<preset version>",
      "primitive": "transform" | "extract" | "classify",
      "input_schema": { /* JSON Schema */ },
      "output_schema": { /* JSON Schema */ }
    }
    ```
  - MUST read from the **loaded preset only** (no provider calls).

- `POST /invoke`
  - Request body:
    ```json
    { "input": { /* payload validated with jsonschema */ } }
    ```
  - Flow (in order):
    1. Generate `request_id` (UUID4).
    2. Enforce auth if `AUTH_TOKEN` env var is set.
    3. Parse JSON; on failure return 400 `MALFORMED_REQUEST`.
    4. Validate `input` against `preset.input_schema` using `jsonschema`.
       - On failure: 422 `INPUT_VALIDATION_ERROR` with structured `details`.
    5. Engine/router:
       - Choose primitive by `preset.primitive` (`transform`, `extract`, `classify`).
       - Delegate to the corresponding primitive runner.
    6. Primitive runner:
       - Build prompt from preset prompt + pretty-printed `input`.
       - Call provider via a common abstraction (see 2.3).
    7. Output validation and repair:
       - Validate provider output against `preset.output_schema`.
       - On failure:
         - Perform **exactly one** repair attempt, then re-validate.
         - If still invalid: 422 `OUTPUT_VALIDATION_ERROR`.
    8. On success:
       - Compute `latency_ms` using a monotonic clock.
       - Return 200 with success envelope.

- **Async body parsing requirement (critical)**:
  - If `/invoke` is implemented as an `async def` route (FastAPI default), then request body reads MUST be await-safe:
    - Prefer `body_bytes = await request.body()` inside async code.
    - Avoid mixing sync/async request body access (e.g., calling `request.body()` without awaiting).
    - Do NOT use `anyio.run(...)` from within an async request path to read the body; it is error-prone and can deadlock or return a coroutine object.
  - Recommended shape:
    - Make the core pipeline `process_invoke_request(...)` an `async def` and call `await request.body()` inside it.
    - In the route handler: `result = await process_invoke_request(...)`.

- `POST /stream`
  - For v1: always 501 Not Implemented with error envelope:
    - `error.code == "NOT_IMPLEMENTED"`.
    - `meta` includes `request_id`, `agent`, `version`.

### 2.2 Envelopes & Status Codes

**Success envelope:**
```json
{
  "output": { /* validated output object */ },
  "meta": {
    "request_id": "uuid4 string",
    "agent": "<preset id>",
    "version": "<preset version>",
    "latency_ms": 12.3
  }
}
```

**Error envelope:**
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "human readable summary",
    "details": [ /* optional list of structured validation/provider errors */ ]
  },
  "meta": {
    "request_id": "uuid4 string",
    "agent": "<preset id or 'unknown'>",
    "version": "<preset version or 'unknown'>"
  }
}
```

**Status codes and `error.code`:**
- 400 → `"MALFORMED_REQUEST"` (invalid JSON body).
- 422 (input) → `"INPUT_VALIDATION_ERROR"`.
- 422 (output after repair) → `"OUTPUT_VALIDATION_ERROR"`.
- 401 → `"UNAUTHORIZED"` (when `AUTH_TOKEN` is set and header missing/invalid).
- 500 → `"INTERNAL_ERROR"` (unexpected backend/provider failure).
- 501 → `"NOT_IMPLEMENTED"` (for `/stream`).

`meta` MUST always include `request_id`, `agent`, `version` (both success and error).

### 2.3 Providers & Repair Loop

- Implement a provider abstraction with a `get_provider` dependency used by `/invoke`:
  - `get_provider` should live in `app.dependencies` (as assumed by tests).
  - Tests will override this via `app.dependency_overrides[get_provider]`.

- Provider interface:
  - At minimum, expose a method or callable used by the runtime to get **JSON-like output**.
  - The tests use simple callables (e.g. `RecordingProvider`) as drop-in replacements.

- Output validation and repair:
  - Validate provider output against `preset.output_schema` using `jsonschema`.
  - If invalid:
    - Call the provider (or a dedicated repair function) **one more time** only.
    - Revalidate; if still invalid → 422 `OUTPUT_VALIDATION_ERROR`.
  - Tests assert:
    - Provider is called exactly twice in the “repair succeeds” case.
    - Provider is called at most twice in the “still invalid” case.

Implementation detail (flexible):
- You may implement a richer interface (e.g. `ProviderResult(parsed_json, raw_text)`), but the behavior observed by tests must match:
  - Single repair attempt.
  - Correct status codes and envelopes.

---

## 3. Presets & Schemas

- Presets live under `app/presets/*.yaml` (bundled with the package).
- Env var `AGENT_PRESET` selects the active preset (e.g. `summarizer`, `meeting_notes`, `extractor`, `classifier`, `triage`).
- Each preset YAML must define:
  - `id`, `version`, `primitive`, `input_schema`, `output_schema`, `prompt`.
  - `id` must match the filename (e.g. `summarizer.yaml` → `id: summarizer`).
- Use `jsonschema.Draft7Validator.check_schema` at startup to validate schemas.

Schema highlights to preserve (see `tests/test_presets.py` for exact expectations):
- `meeting_notes.output_schema.properties.action_items`:
  - Array of objects with `{ owner, task, deadline }`.
- `triage.input_schema.properties.mailbox_context`:
  - Type `"string"`.
- `classifier`:
  - `items`: array of `{ id, content }`.
  - `classifications`: array of `{ item_id, category, confidence }`.
- `extractor`:
  - `input_schema.properties.schema`: type `"object"`.
  - `output_schema.properties` includes `"data"` and `"confidence"`.

The runtime must:
- Validate incoming `input` against `input_schema`.
- Validate provider `output` against `output_schema` as described in 2.3.

### 3.1 Test-derived clarifications (keep aligned with `tests/`)

- **classifier input_schema and tests**:
  - `tests/test_invoke.py` sends a minimal classifier payload containing only `{"items": [...]}`.
  - Therefore, the `classifier` preset **must not require** `categories` for the request to be considered valid by the runtime.
  - The `categories` field may still be supported as an optional hint for real usage.

---

## 4. Auth Behavior

- If `AUTH_TOKEN` env var is **set and non-empty**:
  - `POST /invoke` (and `/stream` if applicable) MUST require:
    - Header: `Authorization: Bearer <token>`.
  - Missing or wrong token:
    - HTTP 401 with `error.code == "UNAUTHORIZED"`.
  - Correct token:
    - Request proceeds to normal processing (must NOT return 401).

- If `AUTH_TOKEN` is unset or empty:
  - `/invoke` must **not** enforce auth (no 401 for missing header).

Tests in `tests/test_invoke.py` encode this behavior; implementation must match.

---

## 5. Structure & Modules

Recommended structure (some files may already exist or have different names; keep them aligned with tests and contract):

- `app/main.py`
  - Creates FastAPI app.
  - Includes routes for `/`, `/health`, `/schema`, `/invoke`, `/stream`.
  - Wires dependencies (e.g. settings, provider, preset loader).

- `app/config.py`
  - Env-driven settings (already present).
  - Keep `http_port=4280`, `service_name="agent-gateway"`.

- `app/preset_loader.py`
  - Load preset YAML from `app/presets/` (package data).
  - Return an in-memory object or dict with `id`, `version`, `primitive`, `input_schema`, `output_schema`, `prompt`.

- `app/dependencies.py`
  - `get_settings()` and `get_provider()` dependency functions.
  - `get_provider` is what tests override.

- `app/engine.py` (or similar)
  - Engine/router that:
    - Reads `preset.primitive`.
    - Calls corresponding primitive runner (`run_transform`, `run_extract`, `run_classify`).

- `app/primitives/`
  - `transform.py`, `extract.py`, `classify.py` with simple prompt-building helpers.

- `app/validation.py`
  - Input/output validation helpers using `jsonschema`.
  - Helpers to convert validation errors into `error.details`.

These names are suggestions; adherence to the **tests** and contract is more important than exact filenames, except where tests import specific symbols (e.g. `from app.main import app`, `from app.dependencies import get_provider`).

---

## 6. Logging & Safety

- For each `/invoke`:
  - Log:
    - `request_id`,
    - `agent` (preset id),
    - `provider` type (e.g. `"stub"` or `"openai"`),
    - `status_code`,
    - `latency_ms`.
- Avoid logging full input payloads by default:
  - Either omit inputs or truncate them.
- Do not leak secrets (e.g. `AUTH_TOKEN`, `OPENAI_API_KEY`) to logs.

---

## 7. Working Style for the Dev Agent

- **Follow tests and contracts**:
  - Treat `tests/test_invoke.py`, `tests/test_presets.py`, and this guide as the executable spec.
  - If a test fails, prefer adjusting the implementation rather than weakening the test, unless the test clearly contradicts the agreed contract.

- **Keep scope tight**:
  - No message brokers, gRPC, sandboxing, or extra services.
  - Single FastAPI app, single process, preset-based configuration.

- **Favor clarity over cleverness**:
  - Small, focused functions.
  - Clear error-handling paths that map directly to the status codes above.

- **When in doubt**:
  - Re-read this guide and the tests.
  - Prefer the simplest code that passes all tests and keeps the external API stable.

