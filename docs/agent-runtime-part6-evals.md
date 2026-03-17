# Agent Runtime Part 6: Eval Harness

This document describes the Part 6 eval harness: a system for defining, running, and scoring test cases against agents. It supports deterministic scoring, regression testing, and future marketplace quality assurance.

## Concepts

### Eval Suite

An **eval suite** is a saved set of test cases for an agent. Each suite has:

- `id` (UUID)
- `agent_id` – the agent under test
- `agent_version` (optional) – pin to a specific version
- `name`, `description` (optional)
- `cases_json` – list of test cases

### Eval Run

An **eval run** is one execution of a suite against a specific agent version. Each run has:

- `id` (UUID)
- `eval_suite_id`
- `agent_id`, `agent_version`
- `status`: `queued` | `running` | `succeeded` | `failed`
- `summary_json` – aggregate scores when complete
- `error` – set when the run fails (e.g. infrastructure error)

### Eval Case Result

Each case in a run produces an **eval case result**:

- `case_index`, `status`: `passed` | `failed` | `error`
- `score` (0.0 or 1.0 for deterministic matchers)
- `expected_json`, `actual_json` (for debugging)
- `matcher_type`, `message`
- `run_id` – reference to the underlying runtime run for traceability

---

## Case Schema

Each case in `cases_json` has:

| Field       | Type   | Required | Description                                      |
|-------------|--------|----------|--------------------------------------------------|
| `name`      | string | no       | Human-readable case name                          |
| `input`     | object | yes      | Input payload passed to the agent                 |
| `session_id`| string | no       | Optional session for multi-turn cases             |
| `expected`  | any    | no       | Expected value for scoring                        |
| `matcher`   | object | yes      | `{ "type": "...", "options"?: {...} }`           |
| `notes`     | string | no       | Optional notes                                   |

### Matcher Types

| Type           | Description                                                                 |
|----------------|-----------------------------------------------------------------------------|
| `exact_json`   | Strict equality on parsed JSON values. Score 1.0 if equal else 0.0.        |
| `subset_json`  | Expected object must be a recursive subset of actual. Score 1.0 or 0.0.     |
| `string_contains` | Actual (or `options.field`) must be a string; expected must be substring. |
| `schema_valid` | Validate actual against `matcher.options.schema` (Draft 7 JSON Schema).    |

For `schema_valid`, `matcher.options.schema` is required.

---

## Sync vs Async Eval Runs

- **wait=true** (default): Run synchronously. The request blocks until all cases complete. Returns `eval_run_id`, `status`, and `summary`.
- **wait=false**: Start a background thread and return immediately with `eval_run_id` and `status: "running"`. Poll `GET /eval-runs/{eval_run_id}` until `status` is `succeeded` or `failed`. On infrastructure failure, the run is set to `failed` with an error message so it never stays stuck in `running`.

---

## Continue-on-Error

If a single case fails (e.g. agent invocation errors, run fails), that case is marked `error` and the suite continues. Only infrastructure failures (suite not found, agent not found, runner crash) fail the whole eval run.

---

## API Endpoints

| Method | Path                          | Description                              |
|--------|-------------------------------|------------------------------------------|
| POST   | /agents/{agent_id}/evals      | Create eval suite                        |
| GET    | /agents/{agent_id}/evals      | List eval suites for agent               |
| GET    | /evals/{eval_suite_id}        | Get suite metadata and cases             |
| POST   | /evals/{eval_suite_id}/run    | Run suite (wait=true/false)               |
| GET    | /eval-runs/{eval_run_id}      | Get eval run status and summary          |
| GET    | /eval-runs/{eval_run_id}/results | Get all case results                  |

---

## Error Payloads

All evals API errors use the standard envelope:

```json
{
  "error": { "code": "...", "message": "...", "details": null },
  "meta": { "request_id": "...", "agent": "...", "version": "..." }
}
```

Codes: `MALFORMED_REQUEST`, `VALIDATION_ERROR`, `AGENT_NOT_FOUND`, `EVAL_SUITE_NOT_FOUND`, `EVAL_RUN_NOT_FOUND`, `EVAL_ERROR`.

---

## Regression Testing and Marketplace Quality

- **Regression**: Run eval suites before/after agent changes to catch regressions.
- **Marketplace**: Future marketplace agents can be scored with eval suites before publication.
- **Deterministic first**: Matchers are deterministic (no LLM-as-judge yet). LLM judges can be added later as additional matcher types.

---

## Example curl flows

Assume the server runs at `http://localhost:4280` and agent `summarizer` exists (e.g. from presets).

### Create an eval suite

```bash
curl -s -X POST http://localhost:4280/agents/summarizer/evals \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Smoke tests",
    "description": "Basic output checks",
    "cases": [
      {
        "name": "empty input",
        "input": {},
        "expected": {},
        "matcher": {"type": "exact_json"}
      },
      {
        "name": "text input",
        "input": {"text": "hello"},
        "expected": {"summary": "ok"},
        "matcher": {"type": "subset_json"}
      }
    ]
  }'
```

Response (201): `{"id": "<suite-uuid>", "agent_id": "summarizer", "name": "Smoke tests", ...}`

### List suites for agent

```bash
curl -s http://localhost:4280/agents/summarizer/evals
```

### Get suite with cases

```bash
SUITE_ID="<suite-id-from-create>"
curl -s "http://localhost:4280/evals/$SUITE_ID"
```

### Run suite (wait=true, synchronous)

```bash
curl -s -X POST "http://localhost:4280/evals/$SUITE_ID/run" \
  -H "Content-Type: application/json" \
  -d '{"wait": true}'
```

Response: `{"eval_run_id": "<run-uuid>", "status": "succeeded", "summary": {"total_cases": 2, "passed": 1, "failed": 0, "errored": 1, ...}}`

### Run suite (wait=false, async)

```bash
curl -s -X POST "http://localhost:4280/evals/$SUITE_ID/run" \
  -H "Content-Type: application/json" \
  -d '{"wait": false}'
```

Response: `{"eval_run_id": "<run-uuid>", "status": "running"}`

### Get eval run status

```bash
EVAL_RUN_ID="<eval-run-id>"
curl -s "http://localhost:4280/eval-runs/$EVAL_RUN_ID"
```

### Get case results

```bash
curl -s "http://localhost:4280/eval-runs/$EVAL_RUN_ID/results"
```
