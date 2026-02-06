## Standardized Agent Runtime (MVP)

Run a **preset-based AI agent gateway** and call it immediately via a stable HTTP contract. The north-star workflow is: run the service locally/VM → call `POST /invoke` with JSON → get consistent JSON back (with discoverable docs at `GET /schema` and Swagger at `/docs`).

## Quickstart (pip)

All examples use **port 4280**.

```bash
pip install -e .

# Run a specific agent preset (presets are bundled in the package)
AGENT_PRESET=summarizer agent-toolbox
```

Or with host/port:

```bash
AGENT_PRESET=classifier PORT=4280 agent-toolbox
```

For other presets, set `AGENT_PRESET` to `meeting_notes`, `extractor`, `classifier`, or `triage`.

## Quickstart (Make, from repo)

All examples use **port 4280**.

```bash
git clone <REPO_URL>
cd agent-toolbox
make install

# Run a specific agent preset locally
AGENT_PRESET=summarizer make run
```

For other presets, change the `AGENT_PRESET` value (for example `meeting_notes`, `extractor`, `classifier`, `triage`).

### Docker (alternative)

```bash
make docker-up AGENT=summarizer
```

To stop containers:

```bash
make docker-down
```

---

## Quickstart (local, manual)

All examples use **port 4280**.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 4280
```

Open Swagger UI at `http://localhost:4280/docs`.

### Switch agent preset

Presets are bundled in the package under `app/presets/*.yaml`. Select one via `AGENT_PRESET`:

```bash
AGENT_PRESET=classifier PROVIDER=stub uvicorn app.main:app --host 0.0.0.0 --port 4280
```

## Quickstart (Docker Compose)

```bash
docker compose up --build
```

To switch presets:

```bash
AGENT_PRESET=triage docker compose up --build
```

## API surface (stable across presets)

- `GET /` – service metadata
- `GET /health` – health info
- `GET /schema` – active preset schemas (no provider calls)
- `POST /invoke` – core invocation
- `POST /stream` – **501 Not Implemented** in v1

## curl examples

All examples assume the server is running at `http://localhost:4280`.

### Health

```bash
curl http://localhost:4280/health
```

### Schema

```bash
curl http://localhost:4280/schema
```

### Invoke: summarizer

```bash
curl -X POST http://localhost:4280/invoke \
  -H "Content-Type: application/json" \
  -d '{"input": {"text": "Some long text to summarize."}}'
```

### Invoke: classifier

```bash
curl -X POST http://localhost:4280/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "items": [
        {"id": "1", "content": "Reset my password"},
        {"id": "2", "content": "Pricing question"}
      ],
      "categories": ["support", "sales", "other"]
    }
  }'
```

### Auth example (Clerk)

Mutating endpoints (like `POST /agents/register`) require a Clerk session token when Clerk is configured. Pass a Bearer token from your frontend session.

```bash
CLERK_JWKS_URL=https://<clerk-frontend-api>/.well-known/jwks.json \
CLERK_ISSUER=https://<clerk-frontend-api> \
uvicorn app.main:app --host 0.0.0.0 --port 4280

curl -X POST http://localhost:4280/invoke \
  -H "Authorization: Bearer <clerk-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"input": {"text": "hello"}}'
```

Legacy: setting `AUTH_TOKEN` enables a static bearer token for dev/tests.

## Context and session memory

You can pass optional **context** on `POST /invoke` to use session memory. Presets that support memory (e.g. `summarizer`, `triage`) use a **memory policy** (last N events, max chars) when building the prompt.

### Invoke with optional context

- **Backward compatible:** `{"input": {...}}` only is valid; no `context` required.
- **With session:** `{"input": {...}, "context": {"session_id": "<id>"}}` uses stored events for that session (and adds this invoke to the session when the preset supports memory).
- **With inline memory:** `{"input": {...}, "context": {"memory": [{"role": "user", "content": "..."}]}}` passes recent context without a session.
- **Empty context:** `{"input": {...}, "context": {}}` is accepted and does not fail.

When a session is used, the success response includes `meta.session_id` and `meta.memory_used_count`.

### Session Memory API

- **`POST /sessions`** – Create a new session. Body optional. Returns **201** with `{ "session_id": "<uuid>" }`. The active preset id is used as `agent_id`.
- **`POST /sessions/{id}/events`** – Append events. Body: `{ "events": [ { "role": "user", "content": "..." }, ... ] }`. Returns **200** with `{ "ok": true, "session_id": "<id>", "appended": N }`.
- **`GET /sessions/{id}`** – Get session. Returns **200** with `{ "session_id", "agent_id", "created_at", "events", "running_summary" }` or **404** when the session does not exist.

### Policy (last N events, max chars)

Presets that set `supports_memory: true` and `memory_policy` in YAML (e.g. summarizer, triage) apply:

- **max_messages:** only the last N events are included in the prompt.
- **max_chars:** total event content is truncated to this many characters.

Example: summarizer uses `max_messages: 2`, `max_chars: 8000` so the prompt contains at most 2 stored events (and up to 8000 chars).

### curl examples (session memory)

Create a session:

```bash
curl -X POST http://localhost:4280/sessions
# → 201 { "session_id": "..." }
```

Append an event (e.g. a note):

```bash
SESSION_ID="<paste session_id from above>"
curl -X POST "http://localhost:4280/sessions/${SESSION_ID}/events" \
  -H "Content-Type: application/json" \
  -d '{"events": [{"role": "user", "content": "Reminder: follow up on Q3 report"}]}'
# → 200 { "ok": true, "session_id": "...", "appended": 1 }
```

Invoke with session (success response includes `meta.session_id` and `meta.memory_used_count`):

```bash
curl -X POST http://localhost:4280/invoke \
  -H "Content-Type: application/json" \
  -d "{\"input\": {\"text\": \"Summarize my notes.\"}, \"context\": {\"session_id\": \"${SESSION_ID}\"}}"
```

Get session (events, agent_id, created_at):

```bash
curl "http://localhost:4280/sessions/${SESSION_ID}"
```

### CORS (frontend Session tab)

Set **`CORS_ORIGINS`** so the frontend can call the gateway (e.g. Session tab). Example: `CORS_ORIGINS=http://localhost:3000` or `*` for development.

---

## Configuration (environment variables)

- **`AGENT_PRESET`**: which preset to load (default: `summarizer`). Presets are YAML files bundled in the package (`app/presets`).
- **`PROVIDER`**: provider implementation (default: `stub`). Use `openrouter` for one API key and many models (recommended).
- **`AUTH_TOKEN`**: optional legacy bearer auth for dev/tests (`Authorization: Bearer <token>`).
- **`CLERK_JWKS_URL`**: Clerk JWKS URL for verifying session tokens (e.g. `https://<clerk-frontend-api>/.well-known/jwks.json`).
- **`CLERK_JWT_KEY`**: optional Clerk JWT public key (PEM). Use this instead of JWKS if you prefer.
- **`CLERK_ISSUER`**: expected token issuer (usually `https://<clerk-frontend-api>`).
- **`CLERK_AUDIENCE`**: optional audience to enforce in JWT verification.
- **`CLERK_AUTHORIZED_PARTIES`**: optional comma-separated `azp` allowlist.
- **`OPENROUTER_API_KEY`**: required when `PROVIDER=openrouter`. Get a key at [openrouter.ai/keys](https://openrouter.ai/keys).
- **`OPENROUTER_MODEL`**: optional model id (default: `openai/gpt-4o-mini`). See [openrouter.ai/models](https://openrouter.ai/models).
- **`OPENAI_API_KEY`** / **`OPENAI_MODEL`**: optional, for direct OpenAI when `PROVIDER=openai`.
- **`DATABASE_URL`**: Postgres connection string (Supabase). When set, Postgres is used for registry + sessions.
- **`DB_PATH`**: path to SQLite DB when `DATABASE_URL` is not set (default: `./data/gateway.db`).
- **`SESSION_DB_PATH`**: legacy alias for `DB_PATH` (still supported).
- **`CORS_ORIGINS`**: comma-separated origins for CORS (default: `*`). Use e.g. `http://localhost:3000` for the frontend Session tab.
- **`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`**: Clerk publishable key for the frontend.
- **`CLERK_SECRET_KEY`**: Clerk secret key for the frontend server.
- **`NEXT_PUBLIC_CLERK_JWT_TEMPLATE`**: optional Clerk JWT template name used when requesting tokens from the frontend.

## Providers

- **StubProvider (default)**: deterministic JSON output, runs with no API keys.
- **OpenRouterProvider (recommended)**: one API key for many models (OpenAI, Claude, Gemini, etc.). Set `PROVIDER=openrouter` and `OPENROUTER_API_KEY`.
- **OpenAIProvider (optional)**: direct OpenAI; set `PROVIDER=openai` and `OPENAI_API_KEY`.

## Architecture (request flow)

`POST /invoke` follows this pipeline:

1) auth (mutating endpoints only; Clerk session token when configured) →\
2) input validation (jsonschema) →\
3) engine/router selects primitive (`transform`/`extract`/`classify`) →\
4) provider call →\
5) output validation (jsonschema) →\
6) one repair attempt (if invalid) → response

In v1, `POST /stream` returns **501 Not Implemented** with a standard error envelope.

## Docker (direct)

```bash
docker build -t agent-gateway .
docker run --rm -p 4280:4280 \
  -e AGENT_PRESET=summarizer \
  -e PROVIDER=stub \
  agent-gateway
```
