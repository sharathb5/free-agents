"""
Eval matchers (Part 6): deterministic scoring of expected vs actual output.

Matcher types: exact_json, subset_json, string_contains, schema_valid.
"""

from __future__ import annotations

from typing import Any, Dict

from jsonschema import Draft7Validator, SchemaError


def score_case(
    expected: Any,
    actual: Any,
    matcher: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Score a single eval case. Returns {status, score, message}.

    status: "passed" | "failed" | "error"
    score: 1.0 for pass, 0.0 for fail, 0.0 for error
    message: human-readable description
    """
    matcher_type = (matcher.get("type") or "").strip().lower()
    options = matcher.get("options") or {}

    if matcher_type == "exact_json":
        return _match_exact_json(expected, actual)
    if matcher_type == "subset_json":
        return _match_subset_json(expected, actual)
    if matcher_type == "string_contains":
        return _match_string_contains(expected, actual, options)
    if matcher_type == "schema_valid":
        return _match_schema_valid(expected, actual, options)

    return {
        "status": "error",
        "score": 0.0,
        "message": f"Unknown matcher type: {matcher.get('type')}",
    }


def _match_exact_json(expected: Any, actual: Any) -> Dict[str, Any]:
    """Strict equality on JSON values. Score 1.0 if equal else 0.0."""
    if _json_equal(expected, actual):
        return {"status": "passed", "score": 1.0, "message": "Exact match"}
    return {"status": "failed", "score": 0.0, "message": "Values do not match exactly"}


def _json_equal(a: Any, b: Any) -> bool:
    """Deep equality for JSON-serializable values."""
    if type(a) != type(b):
        return False
    if a is None or isinstance(a, (bool, int, float, str)):
        return a == b
    if isinstance(a, dict):
        if len(a) != len(b):
            return False
        for k, v in a.items():
            if k not in b or not _json_equal(v, b[k]):
                return False
        return True
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_json_equal(x, y) for x, y in zip(a, b))
    return False


def _match_subset_json(expected: Any, actual: Any) -> Dict[str, Any]:
    """Expected object must be a recursive subset of actual. Score 1.0 if subset else 0.0."""
    if not isinstance(expected, dict):
        return {"status": "error", "score": 0.0, "message": "subset_json requires expected to be an object"}
    if not isinstance(actual, dict):
        return {"status": "failed", "score": 0.0, "message": "Actual is not an object"}

    if _is_subset(expected, actual):
        return {"status": "passed", "score": 1.0, "message": "Expected is subset of actual"}
    return {"status": "failed", "score": 0.0, "message": "Expected is not a subset of actual"}


def _is_subset(expected: Any, actual: Any) -> bool:
    """True if expected is a recursive subset of actual."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k, v in expected.items():
            if k not in actual:
                return False
            if not _is_subset(v, actual[k]):
                return False
        return True
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) > len(actual):
            return False
        for i, ev in enumerate(expected):
            if i >= len(actual) or not _is_subset(ev, actual[i]):
                return False
        return True
    return _json_equal(expected, actual)


def _match_string_contains(expected: Any, actual: Any, options: Dict[str, Any]) -> Dict[str, Any]:
    """Actual must be string or contain options.field; expected string must be substring."""
    target = actual
    field = options.get("field")
    if field is not None and isinstance(actual, dict):
        target = actual.get(field)
    if not isinstance(target, str):
        return {"status": "failed", "score": 0.0, "message": "Actual (or target field) is not a string"}
    expected_str = str(expected) if expected is not None else ""
    if expected_str in target:
        return {"status": "passed", "score": 1.0, "message": "Expected string found in actual"}
    return {"status": "failed", "score": 0.0, "message": "Expected string not found in actual"}


def _match_schema_valid(expected: Any, actual: Any, options: Dict[str, Any]) -> Dict[str, Any]:
    """Validate actual against JSON schema in options.schema. Score 1.0 if valid else 0.0."""
    schema = options.get("schema")
    if schema is None:
        return {"status": "error", "score": 0.0, "message": "schema_valid requires matcher.options.schema"}
    if not isinstance(schema, dict):
        return {"status": "error", "score": 0.0, "message": "Schema must be a JSON object"}

    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as e:
        return {"status": "error", "score": 0.0, "message": f"Invalid schema: {e}"}

    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(actual))
    if not errors:
        return {"status": "passed", "score": 1.0, "message": "Valid against schema"}
    first = errors[0]
    return {"status": "failed", "score": 0.0, "message": first.message}
