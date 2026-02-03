from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Tuple

from fastapi import Request
from jsonschema import Draft7Validator

from .config import get_settings
from .dependencies import AuthError
from .models import InvokeContext, MemoryPolicy
from .preset_loader import Preset, PresetLoadError, get_active_preset
from .providers import BaseProvider, ProviderResult
from .storage import session_store

logger = logging.getLogger("agent-gateway")


class ErrorEnvelope(Exception):
    """
    Custom exception used internally to simplify control flow.

    Handlers in `app.main` convert this into the standardized error envelope.
    """

    def __init__(self, status_code: int, code: str, message: str, details: Any = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


def new_request_id() -> str:
    return str(uuid.uuid4())


def build_success_envelope(
    output: Dict[str, Any],
    *,
    request_id: str,
    preset: Preset,
    latency_ms: float,
    session_id: str | None = None,
    memory_used_count: int | None = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "request_id": request_id,
        "agent": preset.id,
        "version": preset.version,
        "latency_ms": latency_ms,
    }
    if session_id is not None:
        meta["session_id"] = session_id
    if memory_used_count is not None:
        meta["memory_used_count"] = memory_used_count
    return {"output": output, "meta": meta}


def build_error_envelope(
    *,
    request_id: str,
    preset: Preset | None,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> Tuple[int, Dict[str, Any]]:
    meta = {
        "request_id": request_id,
        "agent": preset.id if preset else "unknown",
        "version": preset.version if preset else "unknown",
    }
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "meta": meta,
    }
    return status_code, body


def _validate_with_schema(instance: Any, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    validator = Draft7Validator(schema)
    errors: List[Dict[str, Any]] = []
    for err in validator.iter_errors(instance):
        errors.append(
            {
                "path": list(err.path),
                "message": err.message,
            }
        )
    return errors


def _call_provider(provider: BaseProvider, prompt: str, schema: Dict[str, Any]) -> ProviderResult:
    """
    Invoke the provider.

    Tests override the provider with simple callables that return Dicts; in
    that case we adapt the return value into a ProviderResult.
    """
    # If the override is a simple callable without `complete_json`, call it directly.
    if not hasattr(provider, "complete_json") or not callable(getattr(provider, "complete_json", None)):
        # type: ignore[call-arg]
        raw = provider(prompt=prompt, schema=schema)  # type: ignore[misc]
        if isinstance(raw, dict):
            return ProviderResult(parsed_json=raw, raw_text=json.dumps(raw))
        return ProviderResult(parsed_json={}, raw_text=json.dumps(raw))

    result = provider.complete_json(prompt, schema=schema)
    if isinstance(result, ProviderResult):
        return result

    # Allow providers to return raw JSON dicts for convenience.
    if isinstance(result, dict):
        return ProviderResult(parsed_json=result, raw_text=json.dumps(result))

    raise RuntimeError("Provider returned unsupported result type")


def _merge_and_truncate_memory(
    stored_events: List[Dict[str, Any]],
    context_memory: List[Dict[str, Any]] | None,
    policy: MemoryPolicy | None,
) -> List[Dict[str, Any]]:
    """Merge stored_events first, then context.memory; apply max_messages and max_chars."""
    if policy is None:
        policy = MemoryPolicy(mode="last_n", max_messages=10, max_chars=8000)
    combined: List[Dict[str, Any]] = []
    for e in stored_events:
        combined.append({"role": e.get("role", "user"), "content": e.get("content", "")})
    if context_memory:
        for e in context_memory:
            combined.append({"role": e.get("role", "user"), "content": e.get("content", "")})
    # Last N by max_messages
    n = max(0, policy.max_messages)
    combined = combined[-n:] if n else combined
    # Truncate by max_chars (total content length)
    if policy.max_chars > 0:
        total = 0
        out: List[Dict[str, Any]] = []
        for e in reversed(combined):
            total += len(e.get("content", ""))
            if total <= policy.max_chars:
                out.append(e)
            else:
                break
        combined = list(reversed(out))
    return combined


def _memory_segment_text(events: List[Dict[str, Any]]) -> str:
    """Format events as a memory segment for the prompt."""
    if not events:
        return ""
    lines = ["# Memory (recent context):"]
    for e in events:
        role = e.get("role", "user")
        content = (e.get("content") or "").strip()
        lines.append(f"{role}: {content}")
    return "\n".join(lines) + "\n\n"


def run_primitive(
    preset: Preset,
    provider: BaseProvider,
    input_payload: Any,
    memory_events: List[Dict[str, Any]] | None = None,
    knowledge: List[Dict[str, Any]] | None = None,
) -> ProviderResult:
    """
    Dispatch to the primitive-specific behavior.

    Builds prompt: preset instructions, memory segment (memory_events, already merged/truncated),
    knowledge (if any), input JSON, then instruction to respond with JSON only.
    """
    pretty_input = json.dumps(input_payload, indent=2, sort_keys=True)
    parts = [preset.prompt.strip(), "", f"# Primitive: {preset.primitive}"]

    if memory_events:
        seg = _memory_segment_text(memory_events)
        parts.append(seg)
    if knowledge:
        k_lines = ["# Knowledge:", json.dumps(knowledge, indent=2)]
        parts.append("\n".join(k_lines) + "\n\n")
    parts.append(f"# Input JSON:\n{pretty_input}\n\n")
    parts.append("Respond ONLY with a single JSON object that matches the provided output_schema.")
    prompt = "\n".join(parts)
    return _call_provider(provider, prompt=prompt, schema=preset.output_schema)


def _postprocess_output_for_contract(preset: Preset, input_payload: Any, output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply small, contract-driven post-processing steps.

    Currently:
    - extractor: ensure output.data includes a key for every field_name in input.schema.
      (The output_schema does not strictly enforce this, but the runtime contract does.)
    """
    if preset.id != "extractor":
        return output

    if not isinstance(input_payload, dict):
        return output

    schema_map = input_payload.get("schema")
    if not isinstance(schema_map, dict):
        return output

    data = output.get("data")
    if not isinstance(data, dict):
        data = {}
        output["data"] = data

    for field_name in schema_map.keys():
        data.setdefault(str(field_name), "")

    return output


async def process_invoke_request(
    *,
    request: Request,
    provider: BaseProvider,
) -> Dict[str, Any]:
    """
    Core /invoke processing pipeline.

    This function is intentionally free of FastAPI Response types so it is
    straightforward to test and reason about.
    """
    try:
        preset = get_active_preset()
    except PresetLoadError as exc:
        request_id = new_request_id()
        status_code, body = build_error_envelope(
            request_id=request_id,
            preset=None,
            status_code=500,
            code="INTERNAL_ERROR",
            message=str(exc),
            details=None,
        )
        return {"status_code": status_code, "body": body}

    return await process_invoke_for_preset(request=request, provider=provider, preset=preset)


async def process_invoke_for_preset(
    *,
    request: Request,
    provider: BaseProvider,
    preset: Preset,
) -> Dict[str, Any]:
    """
    Core invocation pipeline for a specific preset (registry or active preset).
    """
    request_id = new_request_id()
    start = time.monotonic()
    settings = get_settings()

    try:
        # 1) Enforce auth (if enabled).
        try:
            from .dependencies import enforce_auth

            enforce_auth(request)
        except AuthError as exc:
            raise ErrorEnvelope(
                status_code=401,
                code="UNAUTHORIZED",
                message=str(exc),
            ) from exc

        # 2) Parse JSON body, handling malformed JSON explicitly.
        try:
            body_bytes = await request.body()
        except Exception:
            # If we cannot even read the body, treat as malformed.
            raise ErrorEnvelope(
                status_code=400,
                code="MALFORMED_REQUEST",
                message="Failed to read request body",
            )

        raw_text = body_bytes.decode("utf-8") if isinstance(body_bytes, (bytes, bytearray)) else str(body_bytes)

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ErrorEnvelope(
                status_code=400,
                code="MALFORMED_REQUEST",
                message="Request body must be valid JSON",
                details={"message": str(exc)},
            ) from exc

        if not isinstance(payload, dict) or "input" not in payload:
            raise ErrorEnvelope(
                status_code=422,
                code="INPUT_VALIDATION_ERROR",
                message="Request body must have top-level 'input' object",
                details=[{"path": [], "message": "Missing 'input' field"}],
            )

        input_payload = payload["input"]

        # Optional context: accept context={} without error.
        context: InvokeContext | None = None
        raw_context = payload.get("context")
        if raw_context is not None:
            if isinstance(raw_context, dict):
                context = InvokeContext(
                    session_id=raw_context.get("session_id"),
                    memory=raw_context.get("memory") if isinstance(raw_context.get("memory"), list) else None,
                    knowledge=raw_context.get("knowledge") if isinstance(raw_context.get("knowledge"), list) else None,
                )
            # else leave context None (invalid shape ignored for backward compat)

        # Resolve stored events and merge with context.memory; apply policy.
        merged_events: List[Dict[str, Any]] = []
        memory_used_count = 0
        session_id_used: str | None = None
        if context and (context.session_id or context.memory):
            stored: List[Dict[str, Any]] = []
            if context.session_id:
                session_id_used = context.session_id
                session = session_store.get_session(context.session_id)
                if session and session.get("events"):
                    stored = [
                        {"role": e.get("role", "user"), "content": e.get("content", "")}
                        for e in session["events"]
                    ]
                elif session is None:
                    logger.warning(
                        "context.session_id=%s but session not found; using stored_events=[]",
                        context.session_id,
                    )
            context_memory = context.memory if isinstance(context.memory, list) else []
            policy = getattr(preset, "memory_policy", None) or MemoryPolicy(mode="last_n", max_messages=10, max_chars=8000)
            merged_events = _merge_and_truncate_memory(stored, context_memory, policy)
            memory_used_count = len(merged_events)
        knowledge_list = context.knowledge if context and isinstance(context.knowledge, list) else None

        # 3) Validate input against preset.input_schema
        input_errors = _validate_with_schema(input_payload, preset.input_schema)
        if input_errors:
            raise ErrorEnvelope(
                status_code=422,
                code="INPUT_VALIDATION_ERROR",
                message="Input failed validation against preset input_schema",
                details=input_errors,
            )

        # 4) Engine/Router: run primitive via provider.
        try:
            result = run_primitive(
                preset,
                provider,
                input_payload,
                memory_events=merged_events if merged_events else None,
                knowledge=knowledge_list,
            )
        except Exception as exc:
            # Provider-level unexpected failures surface as INTERNAL_ERROR.
            raise ErrorEnvelope(
                status_code=500,
                code="INTERNAL_ERROR",
                message="Provider failure",
                details={"message": str(exc)},
            ) from exc

        # 5) Output validation & repair.
        output = _attempt_output_with_repair(preset, provider, input_payload, result)

        # 6) If session_id and supports_memory: append user + assistant events. On failure log only, still 200.
        if session_id_used and getattr(preset, "supports_memory", False):
            user_summary = json.dumps(input_payload)[:500] if input_payload else "invoke"
            assistant_content = result.raw_text[:2000] if result.raw_text else json.dumps(output)[:2000]
            try:
                session_store.append_events(
                    session_id_used,
                    [
                        {"role": "user", "content": user_summary, "meta": {"input": input_payload, "agent": preset.id}},
                        {"role": "assistant", "content": assistant_content, "meta": {"output": output}},
                    ],
                )
            except Exception as exc:
                logger.warning("append_events failed for session_id=%s: %s", session_id_used, exc)

        latency_ms = (time.monotonic() - start) * 1000.0
        status_code = 200
        envelope = build_success_envelope(
            output,
            request_id=request_id,
            preset=preset,
            latency_ms=latency_ms,
            session_id=session_id_used,
            memory_used_count=memory_used_count if session_id_used is not None else None,
        )

        _log_invoke(
            request_id=request_id,
            preset=preset,
            provider_name=settings.provider_name,
            status_code=status_code,
            latency_ms=latency_ms,
        )
        return {"status_code": status_code, "body": envelope}

    except ErrorEnvelope as exc:
        latency_ms = (time.monotonic() - start) * 1000.0
        status_code, body = build_error_envelope(
            request_id=request_id,
            preset=preset,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        _log_invoke(
            request_id=request_id,
            preset=preset,
            provider_name=get_settings().provider_name,
            status_code=status_code,
            latency_ms=latency_ms,
        )
        return {"status_code": status_code, "body": body}


def _attempt_output_with_repair(
    preset: Preset,
    provider: BaseProvider,
    input_payload: Any,
    initial_result: ProviderResult,
) -> Dict[str, Any]:
    """Validate provider output, performing at most one repair attempt."""
    # First attempt.
    errors = _validate_with_schema(initial_result.parsed_json, preset.output_schema)
    if not errors:
        return _postprocess_output_for_contract(preset, input_payload=input_payload, output=initial_result.parsed_json)

    # Build concise repair prompt.
    error_summary = "; ".join(err["message"] for err in errors)
    repair_prompt = (
        "The previous JSON output did not validate against the required output_schema.\n"
        f"Validation errors: {error_summary}\n\n"
        "Previous raw output:\n"
        f"{initial_result.raw_text}\n\n"
        "Please respond again with ONLY a valid JSON object that matches the following output_schema:\n"
        f"{json.dumps(preset.output_schema, indent=2, sort_keys=True)}"
    )

    repair_result = _call_provider(provider, prompt=repair_prompt, schema=preset.output_schema)
    repair_errors = _validate_with_schema(repair_result.parsed_json, preset.output_schema)
    if not repair_errors:
        return _postprocess_output_for_contract(preset, input_payload=input_payload, output=repair_result.parsed_json)

    # Still invalid after repair – caller will surface as OUTPUT_VALIDATION_ERROR.
    raise ErrorEnvelope(
        status_code=422,
        code="OUTPUT_VALIDATION_ERROR",
        message="Provider output did not validate against output_schema after one repair attempt",
        details=repair_errors,
    )


def _log_invoke(
    *,
    request_id: str,
    preset: Preset,
    provider_name: str,
    status_code: int,
    latency_ms: float,
) -> None:
    logger.info(
        "invoke request_id=%s agent=%s provider=%s status=%s latency_ms=%.2f",
        request_id,
        preset.id,
        provider_name,
        status_code,
        latency_ms,
    )
