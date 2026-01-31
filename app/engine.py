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
from .preset_loader import Preset, PresetLoadError, get_active_preset
from .providers import BaseProvider, ProviderResult

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
) -> Dict[str, Any]:
    return {
        "output": output,
        "meta": {
            "request_id": request_id,
            "agent": preset.id,
            "version": preset.version,
            "latency_ms": latency_ms,
        },
    }


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


def run_primitive(preset: Preset, provider: BaseProvider, input_payload: Any) -> ProviderResult:
    """
    Dispatch to the primitive-specific behavior.

    For this runtime, all primitives share the same underlying implementation:
    they build a prompt from the preset's base prompt plus a pretty-printed
    JSON of the input payload and ask the provider for structured JSON that
    conforms to preset.output_schema.
    """
    pretty_input = json.dumps(input_payload, indent=2, sort_keys=True)
    prompt = (
        f"{preset.prompt.strip()}\n\n"
        f"# Primitive: {preset.primitive}\n"
        f"# Input JSON:\n{pretty_input}\n\n"
        "Respond ONLY with a single JSON object that matches the provided output_schema."
    )
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
    request_id = new_request_id()
    start = time.monotonic()
    preset: Preset | None = None
    settings = get_settings()

    try:
        # 1) Load preset for metadata and schemas.
        try:
            preset = get_active_preset()
        except PresetLoadError as exc:
            raise ErrorEnvelope(
                status_code=500,
                code="INTERNAL_ERROR",
                message=str(exc),
            ) from exc

        # 2) Enforce auth (if enabled).
        try:
            from .dependencies import enforce_auth

            enforce_auth(request)
        except AuthError as exc:
            raise ErrorEnvelope(
                status_code=401,
                code="UNAUTHORIZED",
                message=str(exc),
            ) from exc

        # 3) Parse JSON body, handling malformed JSON explicitly.
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

        # 4) Validate input against preset.input_schema
        input_errors = _validate_with_schema(input_payload, preset.input_schema)
        if input_errors:
            raise ErrorEnvelope(
                status_code=422,
                code="INPUT_VALIDATION_ERROR",
                message="Input failed validation against preset input_schema",
                details=input_errors,
            )

        # 5) Engine/Router: run primitive via provider.
        try:
            result = run_primitive(preset, provider, input_payload)
        except Exception as exc:
            # Provider-level unexpected failures surface as INTERNAL_ERROR.
            raise ErrorEnvelope(
                status_code=500,
                code="INTERNAL_ERROR",
                message="Provider failure",
                details={"message": str(exc)},
            ) from exc

        # 6) Output validation & repair.
        output = _attempt_output_with_repair(preset, provider, input_payload, result)

        latency_ms = (time.monotonic() - start) * 1000.0
        status_code = 200
        envelope = build_success_envelope(
            output,
            request_id=request_id,
            preset=preset,
            latency_ms=latency_ms,
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
            preset=preset or Preset(
                id=get_settings().agent_preset,
                version="unknown",
                name="unknown",
                description="",
                primitive="transform",
                input_schema={},
                output_schema={},
                prompt="",
            ),
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

