# Repo-to-Agent

This document describes the repo-to-agent feature (V1): turning a GitHub repository into a draft Free-Agents agent spec, validating it, and **persisting validated agents** to the registry so they are stored and reusable.

## Architecture overview

- **Domain models** (`app/repo_to_agent/models.py`) are the source of truth: `RepoScoutOutput`, `RepoArchitectureOutput`, `AgentDraftOutput`, `AgentReviewOutput`, `RepoToAgentResult`.
- **Templates** (`app/repo_to_agent/templates.py`) define reusable specialists (repo_scout, repo_architect, agent_designer, agent_reviewer) with prompts, input/output schemas, and `allowed_tools`. They are backend-agnostic.
- **Workflow** (`app/repo_to_agent/workflow.py`) is SDK-agnostic: it normalizes repo input into a `RepoWorkflowPlan`, runs an ordered sequence of specialists via an injected **runner** `(template, input_payload) -> dict`, and aggregates results into `RepoToAgentResult`. No tools or LLM are called inside the workflow.
- **Service** (`app/repo_to_agent/service.py`) is the thin entrypoint: `generate_agent_from_repo(repo_input, runner)` builds the plan and runs the workflow with the given runner.
- **Internal runner** (`app/repo_to_agent/internal_runner.py`) is a concrete execution backend that does **not** use the OpenAI Agents SDK. It uses `github_repo_read` as the primitive (via `app.runtime.tools`) and deterministic synthesis or stubs for specialists that have no tools. Where true reasoning is not yet available, the code uses clear TODOs for future LLM integration.
- **App flow** (`app/repo_to_agent/app_flow.py`) is the top-level application entry: `run_repo_to_agent(repo_input, execution_backend="internal")` builds the workflow, injects the internal runner for `execution_backend="internal"`, and returns `RepoToAgentResult`. It is kept thin so an OpenAI backend can be added later.
- **Agent spec bridge** (`app/repo_to_agent/agent_spec_bridge.py`) normalizes and validates `AgentDraftOutput.draft_agent_spec` into the Free-Agents registry–compatible shape (`normalize_draft_agent_spec`, `validate_draft_agent_spec_for_registry`). Catalog resolution is performed at registration time by `registry_store.register_agent`.
- **Persistence** (`app/repo_to_agent/persistence.py`) wires validated results to the registry: `persist_if_valid(result, owner, repo)` runs validation and, when status is pass or pass_with_warnings, normalizes the draft spec and calls `registry_store.register_agent()`. `persist_validated_agent(result, owner, repo)` persists without re-validating (for callers that already validated). Stored agents include `repo_owner`, `repo_name`, and `eval_cases` in the spec and are retrievable via `get_agent(agent_id)` or `get_agent_as_stored(agent_id)` (returns a `StoredAgent` model). `prepare_repo_to_agent_persistence_payload(result)` remains available for handoff use cases.

## Module responsibilities

| Module | Responsibility |
|--------|----------------|
| `models` | Pydantic models for scout, architect, draft, review, and aggregated result. |
| `templates` | `AgentTemplate` and built-in templates (repo_scout, repo_architect, agent_designer, agent_reviewer) with `allowed_tools`. |
| `workflow` | `build_repo_workflow`, `run_repo_to_agent_workflow(plan, runner)`; validation and aggregation. |
| `service` | `generate_agent_from_repo(repo_input, runner)`. |
| `internal_runner` | `run_specialist_with_internal_runner(template, input_payload)`; uses `github_repo_read` and stubs; agent_designer uses `tool_discovery`. |
| `tool_discovery` | `discover_tools_from_repo(scout, architecture)`; heuristics for bundle + additional tools from repo signals. |
| `app_flow` | `run_repo_to_agent(repo_input, execution_backend="internal")`. |
| `openai_adapter` | Placeholder for OpenAI Agents SDK (build config, run specialist); unchanged except for interface consistency. |
| `agent_spec_bridge` | Normalize/validate draft spec for registry; catalog resolution at register time. |
| `persistence` | `persist_if_valid(result, owner, repo)` (validate then store); `persist_validated_agent(...)` (store only); `prepare_repo_to_agent_persistence_payload(result)` for handoff. |

## Repo → specialist workflow

1. **Input**: `repo_input` with `owner`, `repo`, and optional `ref` or `url`.
2. **Plan**: `build_repo_workflow(repo_input)` → `RepoWorkflowPlan` with fixed steps: `repo_scout` → `repo_architect` → `agent_designer` → `agent_reviewer`.
3. **Execution**: For each step, the workflow calls `runner(template, input_payload)`. The runner is responsible for producing a dict that validates against the step’s output model.
4. **Aggregation**: Outputs are validated and merged into `RepoToAgentResult`.

## Internal runner path

- For **repo_scout** and **repo_architect**, the internal runner uses the existing **`github_repo_read`** primitive (via `app.runtime.tools.registry.DefaultToolRegistry` and `build_run_context`). It runs a fixed sequence of calls (e.g. overview + sample for scout; overview + tree for architect) and synthesizes the corresponding output from tool results. No change is made to `github_repo_read` behavior.
- For **agent_designer** and **agent_reviewer** (no tools), the internal runner returns deterministic stubs derived from the input payload. TODOs mark where real reasoning (LLM or OpenAI Agents SDK) should be plugged in.
- Template `allowed_tools` are respected: only tools listed on the template (currently `github_repo_read`) are used; tool execution goes through the same registry and policy as the rest of the app.

### Repo tool discovery

The **tool discovery** module (`app/repo_to_agent/tool_discovery.py`) recommends `bundle_id` and `recommended_additional_tools` from scout + architect output using deterministic heuristics. The internal runner uses it in the agent_designer stub so recommendations are data-driven instead of fixed.

- **Inputs**: `RepoScoutOutput` and `RepoArchitectureOutput` (or dict equivalents).
- **Logic**: If the repo has no code signals (no languages, entrypoints, or code-like paths), it recommends `no_tools_writer`. Otherwise it recommends `repo_to_agent` (or `github_reader` if `repo_to_agent` is missing from the catalog). If integrations or paths suggest HTTP/API usage (e.g. `api`, `client`, `http`, `rest` in paths or integrations), it adds `http_request` to `recommended_additional_tools` (only if that tool is in the catalog and not already in the chosen bundle).
- **Output**: `bundle_id`, `additional_tools` (catalog-valid only), and `rationale` (short explanation strings). All recommendations are constrained to the tool and bundle catalogs.
- **Usage**: `discover_tools_from_repo(scout, architecture)`; optional `tools_catalog` and `bundles_catalog` kwargs to avoid loading catalogs repeatedly.

## Infra hardening (governance and validation)

This section describes the governance and validation layer added during the repo-to-agent infra phase. It is the single place for contributors to understand what is guaranteed, what is normalized at runtime, and what the current limits are.

### Validator guarantees

The **validator** (`app/repo_to_agent/validation.py`) grades a `RepoToAgentResult` after the pipeline runs. It does not modify the result.

- **Contract checks (errors → fail)**  
  - `repo_summary`, `important_files`, `architecture` (with `languages`, `key_paths`), `recommended_bundle`, `draft_agent_spec` (non-empty `name`, `description`), `starter_eval_cases` (each with `name`, `input`, `expected`), and `recommended_additional_tools` must be present and correctly typed.
  - `recommended_bundle` must be a **bundle_id** present in `app/catalog/bundles.yaml`.
  - Every entry in `recommended_additional_tools` must be a **tool_id** present in `app/catalog/tools.yaml`. If the tools catalog cannot be loaded, validation fails with a clear error.
- **Repo-specific sanity (warnings only)**  
  For a small set of known repos (e.g. `psf/requests`, `encode/httpx`, `pallets/flask`), the validator warns if `important_files` / `architecture.key_paths` contain too few expected path substrings (e.g. `requests/api`, `flask/app.py`). This helps catch generic or low-quality output; it does not affect pass/fail.
- **Outcomes**  
  - `fail`: any contract or catalog check failed.  
  - `pass_with_warnings`: no errors, one or more warnings.  
  - `pass`: no errors, no warnings.

Use `validate_repo_to_agent_result(result, owner=..., repo=...)` (e.g. from `scripts/run_repo_validation.py`) to run the validator.

### Workflow normalization

**Workflow** (`app/repo_to_agent/workflow.py`) normalizes repo input and applies guardrails during execution.

- **Repo input normalization**  
  `build_repo_workflow(repo_input)` accepts `owner`, `repo`, and optional `ref` or `url`. If `url` is provided and owner/repo are missing, it derives them from the GitHub URL (e.g. `https://github.com/owner/repo` or `.../repo/tree/branch`). It returns a `RepoWorkflowPlan` with fixed steps: `repo_scout` → `repo_architect` → `agent_designer` → `agent_reviewer`. Invalid or missing owner/repo raise `ValueError`/`TypeError`.
- **Guardrails after agent_designer**  
  Before passing the draft to agent_reviewer and aggregating:
  - **Bundle**: If `recommended_bundle` is not in the bundles catalog, it is replaced by a fallback (`repo_to_agent` if present, else `no_tools_writer`). A note is appended to `review_notes`.
  - **Tools**: `recommended_additional_tools` is filtered to only catalog `tool_id`s; tools already in the chosen bundle are removed. Invalid and redundant removals are recorded in `review_notes`.

So the pipeline always produces a result whose `recommended_bundle` and `recommended_additional_tools` are catalog-valid; the validator can then confirm the same without modifying data.

### Bundle and tool catalog governance

- **Catalogs**  
  - `app/catalog/tools.yaml`: list of tools with `tool_id`, optional `category`, `default_policy`, etc.  
  - `app/catalog/bundles.yaml`: list of bundles with `bundle_id`, `tools` (list of `tool_id`), optional `execution_limits`, `policy_overrides`.  
  - `app/catalog/loader.py` loads and exposes these; `validate_catalogs(tools_catalog, bundles_catalog)` ensures every bundle references only tool_ids that exist in the tools catalog.
- **Where governance is applied**  
  - **Templates**: Agent_designer prompts are seeded with bundle_ids and tool_ids from the catalogs so recommendations stay aligned.  
  - **Workflow**: After agent_designer, bundle and tool lists are normalized against the catalogs (see above).  
  - **Validator**: Final result is checked against the same catalogs; unknown bundle_id or tool_id causes fail.  
  - **Runtime**: Tool resolution (`app/catalog/resolution.py`) uses the same catalogs for allowed tools and policies when an agent is run; repo-to-agent does not perform resolution itself but produces specs that resolution can consume.

Adding a new tool or bundle requires updating the YAML files; once updated, workflow guardrails and the validator use the new entries.

### Persistence (V1)

- **When**: After the pipeline runs, `scripts/run_repo_validation.py` (and any caller) can call `persist_if_valid(result, owner, repo)`. Persistence runs **only** when validation status is `pass` or `pass_with_warnings`; failed or invalid results are not stored.
- **What**: The normalized draft spec (from `validate_draft_agent_spec_for_registry`) is enriched with `repo_owner`, `repo_name`, and `eval_cases`, then passed to `registry_store.register_agent()`. The registry stores the full spec (including tool resolution via catalog) in the existing agents table; `spec_json` holds the optional repo provenance fields.
- **Retrieval**: Stored agents can be retrieved with `registry_store.get_agent(agent_id)` (full spec dict) or `registry_store.get_agent_as_stored(agent_id)` (returns a `StoredAgent` model: `agent_id`, `name`, `description`, `bundle_id`, `tools`, `eval_cases`, `repo_owner`, `repo_name`, `created_at`). No versioning or complex metadata in V1.

### Current limitations

- **Agent spec bridge**: `normalize_draft_agent_spec` / `validate_draft_agent_spec_for_registry` produce a registry-compatible spec; tool resolution (e.g. `bundle_id` → allowed tools) is performed by `registry_store._normalize_spec()` when `register_agent()` is called.
- **Execution backends**: Only `internal` and `openai` are supported. The internal runner uses deterministic synthesis/stubs for agent_designer and agent_reviewer; the OpenAI path uses the SDK for scout, architect, and designer, and the internal runner for reviewer.
- **Repo-specific checks**: The validator’s repo-specific path signals are maintained by hand for a small set of repos; they are for sanity checks only, not a full quality model.

### Definition of done (infra phase)

- [x] End-to-end pipeline runs and returns `RepoToAgentResult`.
- [x] Repo input normalized via `build_repo_workflow`; workflow steps fixed and ordered.
- [x] Bundle/tool governance: workflow normalizes bundle and tools to catalog; validator enforces catalog; templates seeded from catalogs.
- [x] Validator/grader: contract checks, catalog checks, optional repo-specific warnings; status pass / pass_with_warnings / fail.
- [x] Tests for validation, workflow (including guardrails), agent_spec_bridge, and related modules.
- [x] `run_repo_validation.py` runs on known repos and reports validation status; prints a **PERSISTENCE** section (stored: yes/no and agent_id/version when stored).
- [x] **Persistence (V1)**: Validated results are stored via `persist_if_valid`; agents are registered in the registry and retrievable via `get_agent` / `get_agent_as_stored`. Set `REPO_VALIDATION_BACKEND=internal` to run the script without OpenAI (stub output may fail validation; use OpenAI backend for real runs that can persist).

## Where the OpenAI SDK will plug in later

- **Runner**: Implement a runner that, for each `(template, input_payload)`, uses `openai_adapter.run_specialist_with_openai_agent(template, input_payload, client)` (or the real SDK equivalent). That runner can be passed to `generate_agent_from_repo(repo_input, runner)`.
- **App flow**: In `run_repo_to_agent`, add a branch for `execution_backend="openai"` that builds the same workflow and injects the OpenAI-based runner instead of `run_specialist_with_internal_runner`.
- **No change** to workflow, models, or templates is required; only the runner and app_flow backend selection need to be extended.

## How `github_repo_read` stays a primitive

- Repo-to-agent does **not** redefine or replace `github_repo_read`. It reuses `app.runtime.tools.github_tool.execute_github_repo_read` and the existing policy (e.g. `GithubRepoReadPolicy`) through `DefaultToolRegistry` and a minimal `Preset` built from the specialist template.
- All repo inspection is done by calling the same tool with the same contract (owner, repo, ref, mode, path, etc.). Product logic (what to do with the result) lives in the workflow and the internal runner’s synthesis, not inside the GitHub tool.
