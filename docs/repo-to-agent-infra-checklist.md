# Repo-to-agent infra phase — completion checklist (V1)

Use this to confirm the hardening phase is complete. Details are in [repo-to-agent.md](repo-to-agent.md#infra-hardening-governance-and-validation).

- [x] End-to-end pipeline runs and returns `RepoToAgentResult`
- [x] Repo input normalized via `build_repo_workflow`; workflow steps fixed and ordered
- [x] Bundle/tool governance: workflow normalizes bundle and tools to catalog; validator enforces catalog; templates seeded from catalogs
- [x] Validator/grader: contract + catalog checks, optional repo-specific warnings; status pass / pass_with_warnings / fail
- [x] Tests passing for validation, workflow (including guardrails), agent_spec_bridge, persistence, and related modules
- [x] `scripts/run_repo_validation.py` runs on known repos and reports validation status; **PERSISTENCE** section in output (stored: yes/no; agent_id/version when stored)
- [x] **Persistence (V1)**: Validated agents are stored in the registry via `persist_if_valid`; retrievable via `get_agent` / `get_agent_as_stored`; only pass/pass_with_warnings are persisted
