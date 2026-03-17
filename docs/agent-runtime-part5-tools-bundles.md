# Agent Runtime Part 5: Tool Catalog, Bundles, and Categorized Allowlist

This document describes the Part 5 product layer for tool configuration: a global **tool catalog**, **bundles** (toolsets with optional execution limits and policy overrides), **agent-idea → bundle recommendation**, and **spec normalization** that resolves effective allowed tools and policies from catalog + bundle + agent overrides.

## Tool catalog

The **tool catalog** is the single source of truth for first-party tools. It lives in `app/catalog/tools.yaml`.

- Each tool has: `tool_id`, `category`, `description`, `safety_level`, `input_schema_ref`, and `default_policy` (a dict of tool-specific settings, e.g. `http_timeout_seconds`, `http_max_response_chars` for `http_request`).
- Categories are used to group tools in the UI (e.g. "Web & Research", "GitHub").
- Only tools listed in the catalog can be assigned to agents. This avoids arbitrary or user-uploaded tools and keeps security and behaviour predictable.

## Bundles

**Bundles** are predefined toolsets with optional metadata and overrides. They live in `app/catalog/bundles.yaml`.

- Each bundle has: `bundle_id`, `title`, `description`, `category` (for UI filtering and analytics), `tools` (list of `tool_id`s), optional `execution_limits` (e.g. `max_tool_calls`, `max_steps`, `max_wall_time_seconds`), and optional `policy_overrides` (per-tool, tool-specific policy only).
- **Execution limits** are global to the run (not tied to a specific tool). They are merged with catalog/default and agent-level limits.
- **Policy overrides** in a bundle are tool-specific only (e.g. `http_timeout_seconds` for `http_request`). Run-level limits like `max_tool_calls` belong in `execution_limits`, not in per-tool policy.
- Examples: `research_basic` (web research, `http_request`, `max_tool_calls: 3`), `no_tools_writer` (no tools), `github_reader`, `data_analysis` (stubs for recommendation).

## Recommendation flow

The **recommendation** API suggests a bundle (and optional additional tools) from a short agent idea string.

- **MVP**: keyword-based heuristic (e.g. "research", "web", "article" → `research_basic`; "write", "draft" → `no_tools_writer`; "github", "repo" → `github_reader`). Returns `bundle_id`, `confidence`, `rationale`, and `suggested_additional_tools`.
- **Later**: this can be replaced or augmented by an LLM classifier without changing the API.

## Spec normalization and resolution

When an agent spec is registered or updated, the registry **normalizes** it using the catalog and resolution logic.

1. **Inputs** (from raw spec): optional `bundle_id`, `additional_tools` (or legacy `extra_tools`), legacy `allowed_tools`, `tool_policies`, `execution_limits`.
2. **Resolution**:
   - **Allowed tools**: If `bundle_id` is set, base tools come from that bundle; otherwise, from legacy `allowed_tools`. Then `additional_tools` (only catalog tool ids, up to `MAX_EXTRA_TOOLS`, e.g. 3) are appended and the list is deduped and sorted.
   - **Tool policies**: For each allowed tool, merge in order: (A) catalog `default_policy`, (B) bundle `policy_overrides`, (C) agent `tool_policies`. Only tool-specific keys are kept (no run-level limits in per-tool policy).
   - **Execution limits**: Merge: (A) config/settings defaults, (B) bundle `execution_limits`, (C) agent `execution_limits`. Result is stored as `resolved_execution_limits` (e.g. `max_tool_calls`, `max_steps`, `max_wall_time_seconds`).
3. **Validation**: Any tool id (from bundle, `additional_tools`, or `allowed_tools`) must exist in the catalog; otherwise the spec is rejected with 400. `additional_tools` length must not exceed `MAX_EXTRA_TOOLS`.
4. **Stored spec** includes: `allowed_tools` (resolved list), `tool_policies` (resolved, tool-specific), `resolved_execution_limits`, `bundle_id`, `additional_tools` (normalized for UI traceability). The runtime reads these resolved values; no resolution is done at run time.

## Why user-uploaded tools are disallowed

- **Clarity**: A single catalog gives a clear, auditable set of tools and categories.
- **Security**: Arbitrary or user-uploaded tools would require executing or trusting user-defined code or URLs; the catalog restricts tools to first-party, reviewed implementations (and later, GitHub import will produce specs that reference existing catalog tools only).
- **Consistency**: Bundles and recommendations only reference catalog tools, so behaviour and policies are predictable.

## API endpoints

- **GET /catalog/tools**: Tools grouped by category (for UI).
- **GET /catalog/bundles**: List of bundles with `bundle_id`, `title`, `description`, `category`, `tools`.
- **POST /catalog/recommend**: Body `{ "agent_idea": "..." }`; returns `bundle_id`, `confidence`, `rationale`, `suggested_additional_tools`.
- **POST /catalog/tools/resolve**: Body `{ "spec": { ... } }`; returns resolved allowed tools, tool policies, execution limits, and warnings without persisting (for UI preview).

## Runtime behaviour

The runner and tool registry do not change their contracts: they still read `allowed_tools`, `http_allowed_domains`, and (now) `tool_policies` and `resolved_execution_limits` from the preset/spec. Resolution happens only at spec normalization time; the stored spec is the single source for the run.
