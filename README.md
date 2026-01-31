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

### Auth example (optional)

Auth is **optional** and enabled only when `AUTH_TOKEN` is set. When enabled, requests must include `Authorization: Bearer <token>`.

```bash
AUTH_TOKEN=secret-token uvicorn app.main:app --host 0.0.0.0 --port 4280

curl -X POST http://localhost:4280/invoke \
  -H "Authorization: Bearer secret-token" \
  -H "Content-Type: application/json" \
  -d '{"input": {"text": "hello"}}'
```

## Configuration (environment variables)

- **`AGENT_PRESET`**: which preset to load (default: `summarizer`). Presets are YAML files bundled in the package (`app/presets`).
- **`PROVIDER`**: provider implementation (default: `stub`). Use `openrouter` for one API key and many models (recommended).
- **`AUTH_TOKEN`**: if set, enables bearer auth (`Authorization: Bearer <token>`).
- **`OPENROUTER_API_KEY`**: required when `PROVIDER=openrouter`. Get a key at [openrouter.ai/keys](https://openrouter.ai/keys).
- **`OPENROUTER_MODEL`**: optional model id (default: `openai/gpt-4o-mini`). See [openrouter.ai/models](https://openrouter.ai/models).
- **`OPENAI_API_KEY`** / **`OPENAI_MODEL`**: optional, for direct OpenAI when `PROVIDER=openai`.

## Providers

- **StubProvider (default)**: deterministic JSON output, runs with no API keys.
- **OpenRouterProvider (recommended)**: one API key for many models (OpenAI, Claude, Gemini, etc.). Set `PROVIDER=openrouter` and `OPENROUTER_API_KEY`.
- **OpenAIProvider (optional)**: direct OpenAI; set `PROVIDER=openai` and `OPENAI_API_KEY`.

## Architecture (request flow)

`POST /invoke` follows this pipeline:

1) auth (optional via `AUTH_TOKEN`) →\
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

