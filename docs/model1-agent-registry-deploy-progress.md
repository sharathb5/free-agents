# Model 1 — Agent Registry + “Deploy” (Register Spec) — Progress

**Plan:** `/Users/sharath/.cursor/plans/agent_registry_deploy_flow_57d86e13.plan.md`  
**Last updated:** 2026-02-02  
**Goal:** One running gateway hosts many agents (specs-only). Users register agent specs (YAML/JSON) into a registry, UI lists them, clients invoke any agent by id via `POST /agents/{id}/invoke`. Keep legacy `/invoke` unchanged.

---

## 0) Source-of-truth API surface (Model 1)

- `POST /agents/register`
- `GET /agents` (supports: `q`, `primitive`, `supports_memory`, `latest_only=true|false`; returns **envelope** `{ "agents": [...] }`)
- `GET /agents/{id}` (supports: `?version=...`, default: latest = **most recently registered** by `created_at`, not semver)
- `GET /agents/{id}/schema` (supports: `?version=...`; same shape as legacy `/schema`)
- `POST /agents/{id}/invoke` (supports: `?version=...`; same body as legacy `/invoke`)
- Optional: `POST /agents/{id}/stream` -> 501

**Auth default:** When `AUTH_TOKEN` is set, require Bearer auth for `POST /invoke`, `POST /agents/{id}/invoke`, `POST /agents/register` (and optionally everything except `GET /health` and `GET /docs`).

**Storage default:** One DB file by default: `DB_PATH=./data/gateway.db` containing tables `sessions`, `events`, `agents`.

---

## 1) Implementation checklist (Backend Agent)

| ID | Item | Status | Notes |
|----|------|--------|-------|
| A | Config: add `DB_PATH` support (single gateway db path) | ✅ | `DB_PATH` added; sessions now use unified `db_path` with `SESSION_DB_PATH` compatibility. |
| B | Storage: registry store (`agents` table + indexes) | ✅ | `app/storage/registry_store.py` added with WAL/busy_timeout + indexes. |
| C | Spec parsing: accept YAML string OR JSON object | ✅ | `POST /agents/register` accepts YAML string or JSON object. |
| D | Spec validation: id/version/prompt/schema checks | ✅ | Regex + size/depth limits + Draft7/root type enforced. |
| E | Registry semantics: (id, version) immutable | ✅ | Duplicate returns 409 `AGENT_VERSION_EXISTS`. |
| F | “Latest” semantics: by `created_at` | ✅ | `list_agents` returns latest by `created_at` when `latest_only=true`. |
| G | Registry routes: `POST /agents/register` | ✅ | Auth gate + success shape + error envelopes. |
| H | Registry routes: `GET /agents` + filters | ✅ | Registry-only envelope list with filters. |
| I | Registry routes: `GET /agents/{id}` (+ `?version=`) | ✅ | Registry-only; full spec + metadata; 404 `AGENT_NOT_FOUND`. |
| J | Registry routes: `GET /agents/{id}/schema` (+ `?version=`) | ✅ | Schema shape implemented. |
| K | Engine adapter: `spec_to_preset(spec)->Preset` | ✅ | Adapter added in `app/registry_adapter.py`. |
| L | Engine entrypoint: `process_invoke_for_preset(...)` | ✅ | Refactor complete; `/invoke` delegates to preset-specific pipeline. |
| M | Invocation route: `POST /agents/{id}/invoke` | ✅ | Loads registry spec, converts to preset, uses engine pipeline. |
| N | Sessions/memory integration | ✅ | Uses existing session_store logic in shared pipeline. |
| O | Seeding: populate registry from `app/presets/*.yaml` | ✅ | Seed-on-empty implemented in lifespan. |
| P | Error envelopes + new error codes | ✅ | Implemented in registry routes with standardized envelopes. |
| Q | README update | ⬜ | Document endpoints, DB_PATH, auth behavior, “latest” semantics, curl examples. |

---

## 2) Test coverage checklist (Testing Agent)

Create `tests/test_registry.py` and extend `tests/test_invoke.py`.

| ID | Requirement | Test location | Status | Notes |
|----|-------------|---------------|--------|-------|
| T1 | Register valid agent spec as YAML string | test_registry.py | ✅ | `test_register_valid_yaml_spec_returns_200` |
| T2 | Register valid agent spec as JSON object | test_registry.py | ✅ | `test_register_valid_json_spec_returns_200` |
| T3 | Register same (id, version) again -> 409 | test_registry.py | ✅ | `test_register_duplicate_id_version_returns_409_agent_version_exists` |
| T4 | List agents default latest_only=true | test_registry.py | ✅ | `test_get_agents_default_latest_only_returns_one_version_per_id` |
| T5 | “Latest” is by created_at, not semver | test_registry.py | ✅ | `test_latest_is_by_created_at_not_semver` |
| T6 | Filters: q / primitive / supports_memory | test_registry.py | ✅ | `test_get_agents_filters_q_primitive_supports_memory` |
| T7 | Get agent by id returns latest | test_registry.py | ✅ | `test_get_agent_by_id_returns_latest_version` |
| T8 | Get agent by id + version returns exact | test_registry.py | ✅ | `test_get_agent_by_id_and_version_returns_exact_version` |
| T9 | Schema endpoint matches stored schemas | test_registry.py | ✅ | `test_get_agent_schema_matches_stored_spec_schemas` |
| T10 | Spec validation failures -> 400 AGENT_SPEC_INVALID | test_registry.py | ✅ | `test_register_invalid_spec_returns_400_agent_spec_invalid` (parametrized cases: bad id, missing fields, invalid schema, oversize spec, too-deep schema) |
| T11 | Invoke registry agent -> 200 envelope + meta.agent/version | test_invoke.py | ✅ | `test_registry_invoke_returns_200_and_meta_matches_agent_and_version` |
| T12 | Invoke missing agent -> 404 AGENT_NOT_FOUND | test_invoke.py | ✅ | `test_registry_invoke_missing_agent_returns_404_agent_not_found` |
| T13 | Invoke respects AUTH_TOKEN (same as /invoke) | test_invoke.py | ✅ | `test_registry_invoke_requires_auth_when_token_set`, `test_registry_invoke_succeeds_with_correct_bearer_token` |
| T14 | Session memory works with registry agent | test_invoke.py | ✅ | `test_registry_invoke_with_session_memory_behaves_like_preset_invoke` |

---

## 3) Frontend checklist (UI Agent / Frontend Agent)

| ID | Item | Status | Notes |
|----|------|--------|-------|
| F1 | Marketplace lists agents from `GET /agents` | ⬜ | Replace hardcoded `frontend/lib/agents.ts` usage (or make it fallback). |
| F2 | Agent detail modal loads `GET /agents/{id}` | ⬜ | Overview metadata (name/desc/tags/etc). |
| F3 | Schema tab loads `GET /agents/{id}/schema` | ⬜ | Display JSON schemas in UI. |
| F4 | “Upload Agent” (register) UI -> `POST /agents/register` | ⬜ | Textarea for YAML/JSON + submit; show ok/error. |
| F5 | Gateway URL config | ⬜ | Use `NEXT_PUBLIC_GATEWAY_URL` (or existing pattern) consistently. |

---

## 4) Notes / guardrails

- **Registry-only**: platform endpoints read from registry; seeding provides built-in agents.\n+- **No code upload**: specs-only.\n+- **Safe defaults**: size limits, schema depth guard, consistent envelopes.\n+- **Latest**: by created_at; document explicitly.\n+
