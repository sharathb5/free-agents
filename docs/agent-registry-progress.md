# Agent Registry API — Progress

**Spec:** `docs/target-functionality-spec.md`  
**Last updated:** 2026-01-28 (backend implementation complete)

---

## 1. Requirements (R1–R3)

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| R1 | GET /agents — 200, body `{ "agents": [ ... ] }`; each summary has id, name, description, primitive, supports_memory | ✅ Done | `app/routers/agents.py`: discover ids via `list_preset_ids()`, load each with `load_preset(id)`, skip on PresetLoadError (log warning), return sorted list. |
| R2 | GET /agents/{id} — 200 with full details; 404 for unknown id with NOT_FOUND envelope | ✅ Done | GET `/{agent_id}`: `load_preset(agent_id)`; on PresetLoadError return `_agents_error(404, "NOT_FOUND", ...)`. Body: id, version, name, description, primitive, input_schema, output_schema, supports_memory, memory_policy. |
| R3 | Same error-envelope and request_id pattern as session routes | ✅ Done | `_agents_error()` uses `new_request_id()`, `get_active_preset()` for meta, `build_error_envelope()`, JSONResponse. |

---

## 2. Test coverage checklist (T1–T5)

| ID | Requirement | Test name | File | Status |
|----|-------------|-----------|------|--------|
| T1 | GET /agents returns 200; body has key `agents`, value is array | `test_get_agents_returns_200_with_agents_list` | tests/test_agents.py | ✅ Done |
| T2 | GET /agents returns at least one agent; each has id, name, description, primitive, supports_memory | `test_get_agents_returns_at_least_one_agent_with_required_fields` | tests/test_agents.py | ✅ Done |
| T3 | GET /agents/{id} returns 200 for valid id with full details | `test_get_agents_id_returns_200_for_valid_id` | tests/test_agents.py | ✅ Done |
| T4 | GET /agents/{id} returns 404 for unknown id with NOT_FOUND envelope | `test_get_agents_id_returns_404_for_unknown_id` | tests/test_agents.py | ✅ Done |
| T5 | GET /agents/{id} memory_policy shape (mode, max_messages, max_chars when set; null/omitted when not) | `test_get_agents_id_memory_policy_shape_when_preset_has_memory_policy`, `test_get_agents_id_memory_policy_null_or_omitted_when_preset_has_none` | tests/test_agents.py | ✅ Done |

---

## 3. Implementation notes

- **Router:** `app/routers/agents.py` with prefix `/agents`; registered in `app/main.py` (with agents_router before sessions_router).
- **Preset discovery:** `app/preset_loader.list_preset_ids()` added — returns sorted list of stems from `PRESETS_DIR.glob("*.yaml")`. No change to `load_preset` or `get_active_preset` contract.
- **memory_policy in YAML:** Preset only gets `memory_policy` set when the key is present in YAML; otherwise `memory_policy=None` so GET /agents/{id} returns `memory_policy: null` for presets like classifier (T5).
- **Run tests:** `pytest tests/ -v` — 38 tests pass (agents, invoke, presets, sessions).

---

## 4. Handoff notes

- **Backend agent (2026-01-28):** Agent Registry API implemented. GET /agents and GET /agents/{id} in place; all tests in tests/test_agents.py and full suite pass.
- **Testing agent:** Tests in tests/test_agents.py cover R1–R3 and T1–T5; no test changes required.
