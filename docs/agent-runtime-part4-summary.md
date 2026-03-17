# Agent Runtime Part 4: Memory & Context Robustness

This document summarizes the Part 4 additions: rolling session summaries, tool-aware memory injection, and context compaction for long-lived tool-using agents.

## Schema (additive)

### sessions

New nullable/optional columns:

| Column                 | Type   | Description                                              |
|------------------------|--------|----------------------------------------------------------|
| `running_summary`      | TEXT   | Concise rolling summary of the session (default `\"\"`) |
| `summary_updated_at`   | TEXT   | ISO timestamp of last summary update                    |
| `summary_message_count`| INTEGER| How many events have been summarized so far (default 0) |

All changes are additive and applied via `ALTER TABLE` migrations for both SQLite and Postgres.

---

## Running summary (rolling_summary)

### Storage helpers

`app/storage/session_store.py` adds:

- `get_session_summary(session_id) -> {running_summary, summary_updated_at, summary_message_count}`
- `update_session_summary(session_id, new_summary, summarized_count)` – best-effort, no-op if session missing.

`get_session(session_id)` now returns:

- `running_summary`, `summary_updated_at`, `summary_message_count` alongside `events`.

### Summarizer logic

New module: `app/memory/summarizer.py` with:

```python
maybe_update_running_summary(
    provider: BaseProvider,
    preset: Preset,
    session_id: str,
    events: List[Dict[str, Any]],
) -> None
```

**Trigger conditions:**

- `new_events_since_summary >= summary_batch_size` (default **12**, overridable via `AGENT_SUMMARY_BATCH_SIZE`), **OR**
- approximate total chars in user/assistant memory exceed **70%** of `MemoryPolicy.max_chars`.

**Behavior:**

- Summarizes only an older slice of events, **excluding the most recent K** (`memory_recent_k`, default **8**).
- Uses the active provider with a fixed, safe prompt to produce a concise bullet summary:
  - Focus on user goals, preferences, and key facts.
  - Uses `redact_secrets` and `cap_text` to avoid secrets and unbounded growth.
- Appends the new summary to existing `running_summary`, capped by `summary_max_chars` (default **1500**, `AGENT_SUMMARY_MAX_CHARS`).
- Persists `running_summary` and `summary_message_count` via `update_session_summary`.
- Any failure is logged and **never** breaks `/invoke` or runs.

**Integration points:**

- After successful `/invoke` write-back (`write_back_session_events`), `process_invoke_for_preset` calls `maybe_update_running_summary(...)`.
- After successful agent runtime run with `session_id`, `run_runner` calls `maybe_update_running_summary(...)`.

---

## Tool-aware memory injection & context compaction

### MemoryPolicy extensions

`app/models.py` `MemoryPolicy` now includes:

- `memory_include_tool_results: bool = False`
- `memory_tool_result_mode: str = "summary"`  # `"exclude"` \| `"summary"` \| `"full"`

Presets can configure these via YAML `memory_policy`; `_coerce_memory_policy` in `preset_loader.py` handles defaults.

### Core merging logic

`app/engine._merge_and_truncate_memory(stored_events, context_memory, policy)` now:

- **Merges** stored session events and `context.memory` events.
- **Tool-aware filtering**:
  - Infers `event_type` from `role` when missing.
  - If `event_type` is `tool_call` or `tool_result`:
    - When `memory_include_tool_results=False` (default) → **excluded**.
    - When `memory_include_tool_results=True`:
      - `memory_tool_result_mode="exclude"` → excluded.
      - `memory_tool_result_mode="summary"` → included as a short assistant summary like `"tool result: <capped text>"`.
      - `memory_tool_result_mode="full"` → included as-is (subject to `max_chars`).
- **Always keeps the last `memory_recent_k` messages** (config, default **8**) even under char pressure.
- Applies:
  - `max_messages` (but at least `memory_recent_k`),
  - `max_chars`, biasing truncation toward older messages and preserving recent ones.

### Memory block construction

**Config defaults (from `Settings` / env):**

- `memory_recent_k` (default **8**, `AGENT_MEMORY_RECENT_K`)
- `summary_batch_size` (default **12**, `AGENT_SUMMARY_BATCH_SIZE`)
- `summary_max_chars` (default **1500**, `AGENT_SUMMARY_MAX_CHARS`)

**Prompt formatting:**

- For `/invoke` (`run_primitive` in `app/engine.py`):
  - When a session has a summary:
    - `# Memory (summary):\n<running_summary>\n`
  - Then recent context:
    - `# Memory (recent context):\n<role>: <content>\n...`
- For agent runtime runs (`app/runtime/runner.py`):
  - Same two-block pattern is used via `_build_prompt`:
    - Optional `# Memory (summary):` followed by recent context segment.

**Determinism:**

- Given a fixed set of events and the same `MemoryPolicy` + settings, `_merge_and_truncate_memory` output is deterministic (verified in tests).

---

## Tool-aware defaults

- By default, **tool_result**/**tool_call** events are **not** part of memory injection:
  - They are neither written back as full session events by the runtime, nor included by `_merge_and_truncate_memory` when `memory_include_tool_results=False`.
- If a preset opts into including tool results (e.g. for debugging or specialized agents), `"summary"` mode provides a short, capped textual summary instead of raw bodies.

---

## New endpoint: session summary

### GET `/sessions/{id}/summary`

Returns only the summary metadata:

```json
{
  "session_id": "session-123",
  "running_summary": "user wants weather updates...",
  "summary_updated_at": "2026-03-03T12:34:56Z",
  "summary_message_count": 24
}
```

- 404 if session is missing.
- Existing `/sessions/{id}` continues to return full session details, now including summary fields.

---

## Tests (SQLite mode)

New tests in `tests/test_memory_summary.py` (run with `DB_PATH`/`SESSION_DB_PATH` pointing at the same SQLite file):

1. **running_summary updates after enough events**
   - Create a session, append > `summary_batch_size` events, then call `/invoke` with `context.session_id`.
   - Provider stub returns a fixed summary; assert `running_summary` is non-empty and `summary_message_count` increased.

2. **Tool_result excluded by default**
   - Call `_merge_and_truncate_memory` with a `tool_result` event and default `MemoryPolicy`.
   - Assert merged content does **not** contain the raw tool body.

3. **Determinism**
   - Given a fixed set of events and `MemoryPolicy`, `_merge_and_truncate_memory` returns identical outputs on repeated calls.

To run the memory tests in SQLite mode:

```bash
DB_PATH=$(mktemp -d)/gateway.db SESSION_DB_PATH=$DB_PATH DATABASE_URL= SUPABASE_DATABASE_URL= pytest -q tests/test_memory_summary.py
```

