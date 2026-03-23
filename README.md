## Standardized Agent Runtime (MVP)

![GHCR](https://img.shields.io/badge/ghcr-sharathb5%2Fagent--toolbox-blue)

Run a **preset-based AI agent gateway** and call it immediately via a stable HTTP contract. The north-star workflow is: run the service locally/VM → call `POST /invoke` with JSON → get consistent JSON back (with discoverable docs at `GET /schema` and Swagger at `/docs`).

## Quickstart (pipx recommended)

All examples use **port 4280**.

`agent-toolbox` requires **Python 3.10+**.

Install with pipx (recommended for CLI apps):

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install agent-toolbox
```

If you prefer a project-local environment, use bootstrap (creates `.venv`, upgrades pip, installs package):

```bash
./scripts/bootstrap.sh
```

Or run manually with venv:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install agent-toolbox
```

One-time setup helper (prints provider/env guidance):

```bash
agent-toolbox setup
```

### Homebrew Python note (macOS)

If global `pip install ...` fails (PEP 668 / externally-managed environment), use a venv with an explicit interpreter:

```bash
brew install python@3.10
/opt/homebrew/bin/python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install agent-toolbox
```

If you prefer Homebrew for pipx on macOS:

```bash
brew install pipx
pipx ensurepath
pipx install agent-toolbox
```

If `agent-toolbox` command is not found after install, run:

```bash
python -m pip show agent-toolbox
agent-toolbox doctor
```

Run a specific agent preset (presets are bundled in the package):

macOS/Linux (bash/zsh):

```bash
source .venv/bin/activate
AGENT_PRESET=summarizer agent-toolbox
```

Windows PowerShell:

```powershell
.\.venv\Scripts\activate
$env:AGENT_PRESET="summarizer"
agent-toolbox
```

WSL (Ubuntu bash):

```bash
source .venv/bin/activate
AGENT_PRESET=summarizer agent-toolbox
```

For other presets, set `AGENT_PRESET` to `meeting_notes`, `extractor`, `classifier`, or `triage`.

Open Swagger UI at `http://localhost:4280/docs`.

---

## Quickstart (repo/dev)

If you're contributing or running from source:

```bash
git clone <REPO_URL>
cd agent-toolbox
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
AGENT_PRESET=summarizer uvicorn app.main:app --host 0.0.0.0 --port 4280
```

### Docker (alternative)

```bash
make docker-up AGENT=summarizer
```

To stop containers:

```bash
make docker-down
```

### Docker (no repo)

Once the GHCR image is published, you can run without cloning:

```bash
docker run --rm -p 4280:4280 -e AGENT_PRESET=summarizer ghcr.io/sharathb5/agent-toolbox:latest
```

### Docker Compose

```bash
docker compose up --build
```

To switch presets:

```bash
AGENT_PRESET=triage docker compose up --build
```

### Render (hosted API)

Render injects **`PORT`** at runtime. The **Dockerfile** uses `uvicorn ... --port ${PORT:-4280}` so the process binds correctly on Render while staying **4280** locally.

If you use Render’s **native Python** runtime (no Docker), set the start command to:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**After a deploy shows Live:** confirm `GET /health` on your service URL, then `GET /github/oauth/debug` if you use GitHub OAuth (must return JSON, not 404).

**When to run the app locally**

- **Trying production:** you do **not** need the API on your machine—use the Render URL in the browser and set the frontend’s `NEXT_PUBLIC_GATEWAY_URL` to that API origin.
- **Developing the API:** run from repo (see Quickstart above) or `agent-toolbox` with `PORT` unset (defaults to 4280).
- **Developing the Next.js UI:** from `frontend/`, run `npm install` once, then `npm run dev` (typically after the API is up if you call localhost).

## API + Schema (stable across presets)

- `GET /` – service metadata
- `GET /health` – health info
- `GET /schema` – active preset schemas (no provider calls)
- `GET /examples` – plug-and-play input/output example for active preset
- `POST /invoke` – core invocation
- `POST /stream` – **501 Not Implemented** in v1

## Examples (plug-and-play)

All examples assume the server is running at `http://localhost:4280`.

### Health

```bash
curl http://localhost:4280/health
```

### Schema + examples

```bash
curl http://localhost:4280/schema
curl http://localhost:4280/examples
```

For a specific preset:

```bash
curl http://localhost:4280/agents/summarizer/examples
```

Example response (trimmed):

```json
{
  "agent": "summarizer",
  "example": {
    "input": {"text": "OpenAI released a new model that improves reasoning and tool use."},
    "output": {"summary": "A new OpenAI model improves reasoning and tool use.", "bullets": ["Improved reasoning", "Better tool use"]}
  }
}
```

### Invoke using the example input

```bash
curl -X POST http://localhost:4280/invoke \
  -H "Content-Type: application/json" \
  -d '{"input": {"text": "OpenAI released a new model that improves reasoning and tool use."}}'
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

### Clerk: `localhost` and production keys (`pk_live_`)

Clerk **does not allow** `pk_live_` / `sk_live_` on **`http://localhost:3000`** (or any origin outside your production setup). You’ll see:

`Production Keys are only allowed for domain "free-agents.xyz"` / Origin header errors.

- **Local `npm run dev`:** use your Clerk **Development** instance — `pk_test_` + `sk_test_` in **`frontend/.env.local`**, and set the repo root **gateway** **`CLERK_JWKS_URL`** + **`CLERK_SECRET_KEY`** to that **same** development application (same as `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`).
- **Deployed UI** (e.g. `https://free-agents.xyz`): use **`pk_live_`** / **`sk_live_`** and production JWKS/secret on the gateway.

Trying to use “production everywhere” on localhost conflicts with Clerk’s security model. For the rare case of debugging production-only behavior locally, see Clerk’s [using production keys in development](https://clerk.com/docs/guides/development/troubleshooting/using-production-keys-in-development) (subdomain + HTTPS on 443 — not routine).

---

## Configuration (environment variables)

Put a `.env` file in the **repository root** (next to the `app/` package). It is loaded there first even if you start uvicorn from another working directory; a `.env` in the current working directory is also loaded afterward if it differs. Values override same-named variables already set in your shell. Run `agent-toolbox setup` for hints.

- **`AGENT_PRESET`**: which preset to load (default: `summarizer`). Presets are YAML files bundled in the package (`app/presets`).
- **`PROVIDER`**: provider implementation (default: `stub`). Use `openrouter` for one API key and many models (recommended).
- **`AUTH_TOKEN`**: optional legacy bearer auth for dev/tests (`Authorization: Bearer <token>`).
- **`CLERK_JWKS_URL`**: Clerk JWKS URL for verifying session tokens (e.g. `https://<clerk-frontend-api>/.well-known/jwks.json`). Must be the **same Clerk application** as `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` in the Next.js app that calls the gateway—if the token `iss` is `https://foo-12.clerk.accounts.dev` but JWKS is your production custom domain, verification fails with “signing key” / `kid` errors.
- **`CLERK_JWT_KEY`**: optional Clerk JWT public key (PEM). Use this instead of JWKS if you prefer.
- **`CLERK_ISSUER`**: optional; must **exactly** match the session JWT **`iss`** claim (no trailing slash). If you see “issuer mismatch” in the UI, copy `iss` from the token or **remove `CLERK_ISSUER`** to skip issuer checks (signature still verified via JWKS).
- **`CLERK_AUDIENCE`**: optional. Clerk **session** tokens often have no `aud` or an unexpected value—**leave this unset** unless you know the claim. Setting it wrongly causes “JWT audience invalid”.
- **`CLERK_AUTHORIZED_PARTIES`**: optional comma-separated `azp` allowlist.
- **`OPENROUTER_API_KEY`**: required when `PROVIDER=openrouter`. Get a key at [openrouter.ai/keys](https://openrouter.ai/keys).
- **`OPENROUTER_MODEL`**: optional model id (default: `openai/gpt-4o-mini`). See [openrouter.ai/models](https://openrouter.ai/models).
- **`OPENAI_API_KEY`** / **`OPENAI_MODEL`**: optional, for direct OpenAI when `PROVIDER=openai`.
- **`DATABASE_URL`**: Postgres connection string (Supabase). When set, Postgres is used for registry + sessions.
- **`DB_PATH`**: path to SQLite DB when `DATABASE_URL` is not set (default: `./data/gateway.db`).
- **`SESSION_DB_PATH`**: legacy alias for `DB_PATH` (still supported).
- **`CORS_ORIGINS`**: comma-separated origins for CORS (default: `*`). Use e.g. `http://localhost:3000` for the frontend Session tab.
- **`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`**: Clerk publishable key for the frontend (`frontend/.env.local`). Use **`pk_test_`** for local dev on localhost; **`pk_live_`** only on your production web origin (see **Clerk: localhost and production keys** above).
- **`CLERK_SECRET_KEY`**: Clerk **secret** key (Dashboard → API Keys). Required on the **gateway** too if `/github/repos` should list repos from a GitHub account linked in Clerk (the API calls Clerk’s Backend API for the user’s GitHub token). Use **`GET /github/clerk-status`** to confirm `clerk_github_listing_ready` without exposing secrets.
- **`NEXT_PUBLIC_CLERK_JWT_TEMPLATE`**: optional named JWT template (e.g. for Supabase). **Not** used for calls to this repo’s gateway by default—template tokens often fail `CLERK_JWKS_URL` verification. Set **`NEXT_PUBLIC_GATEWAY_USE_CLERK_JWT_TEMPLATE=1`** only if the gateway is explicitly configured to verify that template’s `aud`/`iss`.
- **`GITHUB_CLIENT_ID`** / **`GITHUB_CLIENT_SECRET`** / **`GITHUB_OAUTH_REDIRECT_URI`**: optional; enable the **legacy popup** GitHub OAuth path (`/github/oauth/start` → `/github/oauth/callback`) for repo listing when not using Clerk’s GitHub token. The callback URL in GitHub’s app settings must **exactly** match `GITHUB_OAUTH_REDIRECT_URI`. Use **`GET /github/oauth/debug`** on the running API to see the exact values loaded. See [docs/github-oauth-local.md](docs/github-oauth-local.md).
- **`GITHUB_OAUTH_ALLOWED_RETURN_ORIGINS`**: optional comma-separated frontend origins allowed for the OAuth popup `postMessage` (e.g. `https://app.example.com`). Localhost / 127.0.0.1 are always allowed. If **`CORS_ORIGINS`** is not `*`, those origins are also accepted as `return_to` without duplicating them here.

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
