# Contributing to free-agents

Thank you for your interest in contributing! This guide covers how to set up a development environment, run tests, and submit changes.

## Development Setup

**Requirements:** Python 3.10+, Git

```bash
git clone https://github.com/sharathb5/free-agents.git
cd free-agents

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

Copy the environment template and fill in at least `AGENT_PRESET` and `PROVIDER`:

```bash
cp .env.example .env
```

## Running the Server

```bash
source .venv/bin/activate
AGENT_PRESET=summarizer uvicorn app.main:app --host 0.0.0.0 --port 4280
```

Swagger UI is available at `http://localhost:4280/docs`. Health check: `GET /health`.

## Running Tests

```bash
# Unit + integration tests
pytest tests/

# Or with the dev extra
pip install -e ".[dev]"
pytest tests/
```

The test suite lives in `tests/`. Integration tests start a `TestClient` in-process — no running server needed.

## Repo Structure

```
app/            FastAPI application (routes, providers, engine)
app/presets/    Bundled YAML agent presets
tests/          Pytest test suite
frontend/       Next.js UI (optional, see frontend/README if present)
docs/           Public-facing documentation
docs/internal/  Internal working notes (not published)
scripts/        Bootstrap and utility scripts
presets/        Additional preset files
mcp/            MCP (Model Context Protocol) bridge tooling
evals/          Evaluation harness
```

## Submitting a Pull Request

1. Fork the repo and create a branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. Make your changes and add tests for new behaviour.
3. Ensure `pytest tests/` passes locally.
4. Open a PR against `main`. Fill out the PR template.
5. A maintainer will review within a few days.

## Commit Style

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(presets): add meeting_notes memory policy
fix(auth): handle missing CLERK_ISSUER gracefully
docs: update configuration section
chore: bump httpx to 0.27.1
```

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`

## Code Style

- Python: no formatter enforced yet — match the surrounding code.
- Keep changes focused; one concern per PR.
- Do not commit `.env` files or secrets.

## Questions?

Open a [Discussion](https://github.com/sharathb5/free-agents/discussions) or a GitHub Issue.
