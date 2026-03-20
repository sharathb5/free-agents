from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from app.catalog.loader import CatalogError, load_bundles_catalog, load_tools_catalog

from .models import (
    AgentDraftOutput,
    AgentReviewOutput,
    RepoArchitectureOutput,
    RepoScoutOutput,
)

JSONSchema = Dict[str, Any]


def _bundle_ids_for_prompt() -> List[str]:
    """
    Load bundle_ids from the real bundles catalog.

    This keeps agent_designer recommendations aligned with the catalog, without
    hardcoding a second list.
    """
    try:
        catalog = load_bundles_catalog()
    except CatalogError:
        # Keep prompt usable even if catalog can't be loaded in some environments.
        return []
    bundle_ids: List[str] = []
    for b in catalog.get("bundles") or []:
        if isinstance(b, dict) and isinstance(b.get("bundle_id"), str):
            bid = b["bundle_id"].strip()
            if bid:
                bundle_ids.append(bid)
    # Stable prompt content across runs.
    return sorted(set(bundle_ids))


_BUNDLE_IDS_FOR_PROMPT: List[str] = _bundle_ids_for_prompt()


def _tool_ids_for_prompt() -> List[str]:
    """
    Load tool_ids from the real tools catalog.

    This keeps agent_designer recommendations aligned with the catalog, without
    hardcoding a second list.
    """
    try:
        catalog = load_tools_catalog()
    except CatalogError:
        # Keep prompt usable even if catalog can't be loaded in some environments.
        return []
    tool_ids: List[str] = []
    for t in catalog.get("tools") or []:
        if isinstance(t, dict) and isinstance(t.get("tool_id"), str):
            tid = t["tool_id"].strip()
            if tid:
                tool_ids.append(tid)
    # Stable prompt content across runs.
    return sorted(set(tool_ids))


_TOOL_IDS_FOR_PROMPT: List[str] = _tool_ids_for_prompt()


@dataclass
class AgentTemplate:
    """
    Template for a specialist agent in the repo-to-agent workflow.

    This is a Free-Agents–owned configuration object and is intentionally
    decoupled from any specific execution backend (e.g. OpenAI Agents SDK).
    """

    id: str
    role: str
    description: str
    prompt: str
    input_schema: JSONSchema
    output_schema: JSONSchema
    allowed_tools: List[str]


_REPO_COORDS_PROPERTIES: JSONSchema = {
    "owner": {
        "type": "string",
        "description": "GitHub owner/org/user name (e.g. 'openai').",
    },
    "repo": {
        "type": "string",
        "description": "GitHub repository name (e.g. 'agent-toolbox').",
    },
    "ref": {
        "type": "string",
        "description": "Optional git ref such as branch name or commit SHA.",
    },
}


REPO_SCOUT_INPUT_SCHEMA: JSONSchema = {
    "title": "RepoScoutInput",
    "type": "object",
    "properties": dict(_REPO_COORDS_PROPERTIES),
    "required": ["owner", "repo"],
    "additionalProperties": False,
}


REPO_ARCHITECT_INPUT_SCHEMA: JSONSchema = {
    "title": "RepoArchitectInput",
    "type": "object",
    "properties": {
        **_REPO_COORDS_PROPERTIES,
        "scout_summary": {
            "type": "object",
            "description": (
                "Optional RepoScoutOutput JSON from repo_scout. Use it to decide "
                "which files/paths to inspect more deeply."
            ),
        },
    },
    "required": ["owner", "repo"],
    "additionalProperties": False,
}


REPO_TOOL_DISCOVERY_INPUT_SCHEMA: JSONSchema = {
    "title": "RepoToolDiscoveryInput",
    "type": "object",
    "properties": {
        **_REPO_COORDS_PROPERTIES,
        "scout": {
            "type": "object",
            "description": "RepoScoutOutput JSON from the repo_scout specialist.",
        },
        "architecture": {
            "type": "object",
            "description": "RepoArchitectureOutput JSON from the repo_architect specialist.",
        },
    },
    "required": ["owner", "repo", "scout", "architecture"],
    "additionalProperties": False,
}

AGENT_DESIGNER_INPUT_SCHEMA: JSONSchema = {
    "title": "AgentDesignerInput",
    "type": "object",
    "properties": {
        **_REPO_COORDS_PROPERTIES,
        "scout": {
            "type": "object",
            "description": "RepoScoutOutput JSON from the repo_scout specialist.",
        },
        "architecture": {
            "type": "object",
            "description": "RepoArchitectureOutput JSON from the repo_architect specialist.",
        },
        "discovered_repo_tools": {
            "type": "array",
            "description": "Discovered tools in the repo (for awareness only; do not auto-add to agent).",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "tool_type": {"type": "string"},
                    "command": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "source_path": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        },
        "wrapped_repo_tools": {
            "type": "array",
            "description": "Wrapped repo tools (executable metadata; low-risk may be auto-exposed).",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "tool_type": {"type": "string"},
                    "command": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "source_path": {"type": "string"},
                    "wrapper_kind": {"type": "string"},
                    "args_schema": {"type": "object"},
                    "safe_to_auto_expose": {"type": "boolean"},
                    "risk_level": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        },
    },
    "required": ["owner", "repo", "scout", "architecture"],
    "additionalProperties": False,
}


AGENT_REVIEWER_INPUT_SCHEMA: JSONSchema = {
    "title": "AgentReviewerInput",
    "type": "object",
    "properties": {
        **_REPO_COORDS_PROPERTIES,
        "scout": {
            "type": "object",
            "description": "RepoScoutOutput JSON from the repo_scout specialist.",
        },
        "architecture": {
            "type": "object",
            "description": "RepoArchitectureOutput JSON from the repo_architect specialist.",
        },
        "draft": {
            "type": "object",
            "description": "AgentDraftOutput JSON from the agent_designer specialist.",
        },
    },
    "required": ["owner", "repo", "scout", "architecture", "draft"],
    "additionalProperties": False,
}


REPO_SCOUT_TEMPLATE = AgentTemplate(
    id="repo_scout",
    role="repo_scout",
    description="Lightweight GitHub repo scout that summarizes the codebase and key files.",
    prompt=(
        "You are a repo scout. Given a GitHub repository (owner, repo, optional ref), "
        "use the github_repo_read tool in overview and sample modes to:\n"
        "- Understand the top-level layout and important files.\n"
        "- Infer likely languages and frameworks from filenames and sampled content.\n"
        "\n"
        "Grounding rules (critical):\n"
        "- You MUST base your summary and lists on evidence from github_repo_read.\n"
        "- Do NOT rely on prior knowledge of popular repositories.\n"
        "- Use github_repo_read at most 15 times (overview, sample, and a few file reads). Then return the JSON. Do not keep exploring.\n"
        "- Treat your tool calls as operating under a strict token budget: prefer overview/tree for breadth, "
        "then read only a small number of short, high-signal files. Avoid large configs/logs/vendor trees and "
        "avoid repeatedly reading the same paths.\n"
        "- If you cannot inspect the repo (tool error, rate limit, missing permissions), return:\n"
        "  - repo_summary: a short sentence explaining you could not inspect due to the tool error\n"
        "  - important_files/language_hints/framework_hints: empty lists\n"
        "Return a concise JSON object matching the RepoScoutOutput schema. Do not include "
        "any fields that are not in the schema."
    ),
    input_schema=REPO_SCOUT_INPUT_SCHEMA,
    output_schema=RepoScoutOutput.model_json_schema(),
    allowed_tools=["github_repo_read"],
)


# Specialist: repo_architect
# - Purpose: derive a grounded architectural map of the repo (languages/frameworks/services/entrypoints/integrations).
# - Boundaries: do not design an agent; do not propose bundles/tools/prompts/evals beyond what fits the schema.
# - Tooling: may use github_repo_read (and only that tool) for inspection.
REPO_ARCHITECT_TEMPLATE = AgentTemplate(
    id="repo_architect",
    role="repo_architect",
    description="Architecture specialist that derives languages, services, entrypoints, and integrations from a repo.",
    prompt=(
        "You are **repo_architect**: an architecture analyst for a GitHub repository.\n\n"
        "## Your responsibility\n"
        "- Build a grounded mental model of the repo’s architecture: languages, frameworks, services, "
        "entrypoints, integrations, and key paths.\n"
        "- You are **not** designing an agent. Do **not** propose bundles/tools, prompts, evals, or an AgentSpec.\n\n"
        "## Grounding rules (critical)\n"
        "- You MUST base every item you output on evidence from `github_repo_read` results.\n"
        "- Do NOT rely on prior knowledge of popular repositories or libraries.\n"
        "- Only list file paths that you have confirmed exist via `overview`/`tree`/`file`.\n"
        "- If you cannot inspect the repo (tool error, rate limit, missing permissions), return EMPTY lists for "
        "`languages`, `frameworks`, `services`, `entrypoints`, `integrations`, and `key_paths`.\n\n"
        "## Inputs\n"
        "- You will receive `owner`, `repo`, optional `ref`, and an optional `scout_summary` (RepoScoutOutput).\n"
        "- Use `scout_summary` only to prioritize where to look; do not copy it verbatim.\n\n"
        "## Tooling\n"
        "- You may use **only** `github_repo_read`. Use github_repo_read at most 15 times. Prefer `tree`/`overview` "
        "to map the surface area, then selectively `file` read a small set of high-signal entrypoints, configs, "
        "and dependency manifests. Assume a strict token budget: use short slices, avoid oversized files (logs, "
        "generated/vendor assets), and stop exploring once you have enough evidence to fill the schema.\n\n"
        "## Output (MUST be valid JSON matching RepoArchitectureOutput exactly)\n"
        "- `languages`: primary implementation languages (e.g. Python, TypeScript).\n"
        "- `frameworks`: major frameworks/runtime stacks (e.g. FastAPI, React).\n"
        "- `services`: distinct deployable/runtime components (e.g. api, worker, web, cli).\n"
        "- `entrypoints`: concrete executable entry files/commands (paths when possible).\n"
        "- `integrations`: external systems/APIs (e.g. GitHub, Postgres, Stripe) inferred from code/config.\n"
        "- `key_paths`: a curated list of the most important paths to understand the architecture.\n\n"
        "Return **only** the JSON object. No prose. No extra keys."
    ),
    input_schema=REPO_ARCHITECT_INPUT_SCHEMA,
    output_schema=RepoArchitectureOutput.model_json_schema(),
    allowed_tools=["github_repo_read"],
)


# Step: repo_tool_discovery (deterministic, no LLM; runner executes discovery and returns discovered_tools)
REPO_TOOL_DISCOVERY_OUTPUT_SCHEMA: JSONSchema = {
    "type": "object",
    "properties": {
        "discovered_tools": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "tool_type": {"type": "string"},
                    "command": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "source_path": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "tool_type", "source_path", "confidence"],
            },
        },
    },
    "required": ["discovered_tools"],
}

REPO_TOOL_DISCOVERY_TEMPLATE = AgentTemplate(
    id="repo_tool_discovery",
    role="repo_tool_discovery",
    description="Deterministic discovery of tools present in the repo (CLI, scripts, OpenAPI, MCP).",
    prompt="(Internal step: no prompt; runner executes rule-based discovery.)",
    input_schema=REPO_TOOL_DISCOVERY_INPUT_SCHEMA,
    output_schema=REPO_TOOL_DISCOVERY_OUTPUT_SCHEMA,
    allowed_tools=["github_repo_read"],
)


# Step: code_tool_discovery (deterministic; runner fetches source paths and runs code pattern detection)
CODE_TOOL_DISCOVERY_OUTPUT_SCHEMA: JSONSchema = {
    "type": "object",
    "properties": {
        "code_tools": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "tool_type": {"type": "string"},
                    "command": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "source_path": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "tool_type", "source_path", "confidence"],
            },
        },
    },
    "required": ["code_tools"],
}

CODE_TOOL_DISCOVERY_TEMPLATE = AgentTemplate(
    id="code_tool_discovery",
    role="code_tool_discovery",
    description="Deterministic discovery of code-defined tools (LangChain @tool, MCP, etc.).",
    prompt="(Internal step: no prompt; runner executes rule-based code pattern detection.)",
    input_schema=REPO_TOOL_DISCOVERY_INPUT_SCHEMA,
    output_schema=CODE_TOOL_DISCOVERY_OUTPUT_SCHEMA,
    allowed_tools=["github_repo_read"],
)


# Specialist: agent_designer
# - Purpose: turn scout + architecture into a draft Free-Agents agent spec and starter eval cases.
# - Boundaries: do not perform review/critique; assume no tools are available at design time.
AGENT_DESIGNER_TEMPLATE = AgentTemplate(
    id="agent_designer",
    role="agent_designer",
    description="Agent designer that turns repo analysis into a draft Free-Agents AgentSpec and eval ideas.",
    prompt=(
        "You are **agent_designer**: you turn repo analysis into a useful draft Free-Agents agent.\n\n"
        "## Your responsibility\n"
        "- Design a focused agent that helps a developer work effectively in this repo.\n"
        "- You are **not** reviewing quality. Do not critique; produce a best-effort draft.\n\n"
        "## Inputs\n"
        "- You will receive `owner`, `repo`, optional `ref`, plus:\n"
        "  - `scout` (RepoScoutOutput)\n"
        "  - `architecture` (RepoArchitectureOutput)\n"
        "- Treat these as your grounding. Do not invent frameworks/services not supported by inputs.\n\n"
        "## Tooling\n"
        "- Assume **no tools are available**. Do not request tool calls.\n\n"
        "## Output (MUST be valid JSON matching AgentDraftOutput exactly)\n"
        "- `recommended_bundle`: MUST be exactly one of these bundle_id values from the catalog:\n"
        + "\n".join([f"  - {bid}" for bid in _BUNDLE_IDS_FOR_PROMPT])
        + ("\n" if _BUNDLE_IDS_FOR_PROMPT else "")
        + "  - For a codebase that developers will navigate or contribute to, prefer `repo_to_agent` or "
        "`github_reader` so the agent can use repo inspection. Use `no_tools_writer` only when the repo "
        "is docs-only or the agent needs no tool access.\n"
        "- `recommended_additional_tools`: list of tool_id strings.\n"
        "  - MUST be a subset of these allowed tool_id values from the catalog:\n"
        + "\n".join([f"    - {tid}" for tid in _TOOL_IDS_FOR_PROMPT])
        + ("\n" if _TOOL_IDS_FOR_PROMPT else "")
        + "  - If none are appropriate, return an empty list `[]`.\n"
        "  - Only add a tool_id when there is a clear repo-specific reason (e.g. the repo does HTTP client "
        "work or API fetching and would benefit from `http_request`). Otherwise keep `[]`.\n"
        "- `draft_agent_spec`: a registry-shaped dict with at least:\n"
        "  - `id`, `version`, `name`, `description`, `primitive`, `input_schema`, `output_schema`, `prompt`\n"
        "  - In `description`, mention at least one concrete path, entrypoint, or workflow from `architecture`/"
        "`scout` (e.g. key paths or entrypoints) so the spec is clearly tied to this repo.\n"
        "  - Keep the prompt narrowly scoped to the repo’s actual workflows (based on `architecture` + `scout`).\n"
        "- `starter_eval_cases`: 3–8 small eval case dicts. Each dict should include:\n"
        "  - `name`: short identifier\n"
        "  - `input`: representative user request (string or object)\n"
        "  - `expected`: what “good” looks like (acceptance criteria)\n"
        "  - `notes`: any setup/assumptions\n"
        "  - Ground cases in this repo: reference specific files or paths from `architecture.key_paths` or "
        "`scout.important_files` where possible. Include at least one navigation/contribution-style case "
        "(e.g. \"Where is X implemented?\", \"How do I add or extend Y?\") rather than only generic usage questions.\n\n"
        "Return **only** the JSON object. No prose. No extra keys."
    ),
    input_schema=AGENT_DESIGNER_INPUT_SCHEMA,
    output_schema=AgentDraftOutput.model_json_schema(),
    allowed_tools=[],
)


# Specialist: agent_reviewer
# - Purpose: critique the draft for grounding/scope/tooling/evals clarity and surface risks/open questions.
# - Boundaries: do not redesign the whole agent; provide targeted review notes only. No tools.
AGENT_REVIEWER_TEMPLATE = AgentTemplate(
    id="agent_reviewer",
    role="agent_reviewer",
    description="Reviewer that critiques a proposed agent design and surfaces risks and open questions.",
    prompt=(
        "You are **agent_reviewer**: you review a proposed agent draft for grounding, scope, and safety.\n\n"
        "## Your responsibility\n"
        "- Critique the design based on the repo evidence provided.\n"
        "- Identify risks, missing constraints, unclear prompt/spec choices, and weak eval coverage.\n"
        "- You are **not** redesigning the agent from scratch. Suggest targeted edits and questions.\n\n"
        "## Inputs\n"
        "- You will receive `owner`, `repo`, optional `ref`, plus:\n"
        "  - `scout` (RepoScoutOutput)\n"
        "  - `architecture` (RepoArchitectureOutput)\n"
        "  - `draft` (AgentDraftOutput)\n\n"
        "## Tooling\n"
        "- Assume **no tools are available**. Do not request tool calls.\n\n"
        "## Review focus areas\n"
        "- **Grounding**: does `draft_agent_spec` claim capabilities/tools that aren’t supported by the repo?\n"
        "- **Tool scope**: are `recommended_additional_tools` over-broad or unjustified?\n"
        "- **Prompt clarity**: is the agent’s prompt specific, bounded, and aligned with repo workflows?\n"
        "- **Schemas**: do `input_schema`/`output_schema` in `draft_agent_spec` look coherent and realistic?\n"
        "- **Evals**: are `starter_eval_cases` concrete, testable, and representative? Prefer cases that "
        "reference specific repo paths or contribution/navigation tasks; note if evals are mostly generic "
        "usage with no repo-specific grounding. Any obvious gaps?\n\n"
        "## Output (MUST be valid JSON matching AgentReviewOutput exactly)\n"
        "- `review_notes`: bullet-style strings with targeted improvements.\n"
        "- `risks`: concrete failure modes (tool misuse, hallucination vectors, security/safety concerns).\n"
        "- `open_questions`: decisions blockers / clarifications needed before publishing.\n\n"
        "Return **only** the JSON object. No prose. No extra keys."
    ),
    input_schema=AGENT_REVIEWER_INPUT_SCHEMA,
    output_schema=AgentReviewOutput.model_json_schema(),
    allowed_tools=[],
)

