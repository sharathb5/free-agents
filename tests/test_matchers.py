"""
Tests for Part 6 eval matchers: exact_json, subset_json, string_contains, schema_valid.
"""

from __future__ import annotations

import pytest

from app.evals.matchers import score_case


# --- exact_json ---


def test_matcher_exact_json_pass() -> None:
    """exact_json: equal values pass."""
    r = score_case({"a": 1, "b": 2}, {"a": 1, "b": 2}, {"type": "exact_json"})
    assert r["status"] == "passed"
    assert r["score"] == 1.0


def test_matcher_exact_json_pass_primitives() -> None:
    """exact_json: equal primitives pass."""
    assert score_case(42, 42, {"type": "exact_json"})["status"] == "passed"
    assert score_case("hello", "hello", {"type": "exact_json"})["status"] == "passed"
    assert score_case(True, True, {"type": "exact_json"})["status"] == "passed"
    assert score_case(None, None, {"type": "exact_json"})["status"] == "passed"


def test_matcher_exact_json_fail() -> None:
    """exact_json: unequal values fail."""
    r = score_case({"a": 1}, {"a": 2}, {"type": "exact_json"})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


def test_matcher_exact_json_fail_type_mismatch() -> None:
    """exact_json: type mismatch fails."""
    r = score_case(1, "1", {"type": "exact_json"})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


def test_matcher_exact_json_fail_extra_keys() -> None:
    """exact_json: extra keys in actual fail (strict equality)."""
    r = score_case({"a": 1}, {"a": 1, "b": 2}, {"type": "exact_json"})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


# --- subset_json ---


def test_matcher_subset_json_pass() -> None:
    """subset_json: expected object is subset of actual passes."""
    r = score_case({"a": 1}, {"a": 1, "b": 2}, {"type": "subset_json"})
    assert r["status"] == "passed"
    assert r["score"] == 1.0


def test_matcher_subset_json_pass_nested() -> None:
    """subset_json: nested objects work."""
    expected = {"x": {"y": 1}}
    actual = {"x": {"y": 1, "z": 2}, "w": 3}
    r = score_case(expected, actual, {"type": "subset_json"})
    assert r["status"] == "passed"
    assert r["score"] == 1.0


def test_matcher_subset_json_pass_empty_expected() -> None:
    """subset_json: empty expected {} is subset of any object."""
    r = score_case({}, {"a": 1}, {"type": "subset_json"})
    assert r["status"] == "passed"
    assert r["score"] == 1.0


def test_matcher_subset_json_fail_missing_key() -> None:
    """subset_json: missing key in actual fails."""
    r = score_case({"a": 1, "c": 3}, {"a": 1, "b": 2}, {"type": "subset_json"})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


def test_matcher_subset_json_fail_value_mismatch() -> None:
    """subset_json: value mismatch fails."""
    r = score_case({"a": 1}, {"a": 2, "b": 3}, {"type": "subset_json"})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


def test_matcher_subset_json_fail_actual_not_object() -> None:
    """subset_json: actual not an object fails."""
    r = score_case({"a": 1}, "not an object", {"type": "subset_json"})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


def test_matcher_subset_json_error_expected_not_object() -> None:
    """subset_json: expected not an object returns error."""
    r = score_case([1, 2], {"a": 1}, {"type": "subset_json"})
    assert r["status"] == "error"
    assert r["score"] == 0.0


# --- string_contains ---


def test_matcher_string_contains_pass() -> None:
    """string_contains: expected substring in actual passes."""
    r = score_case("world", "hello world", {"type": "string_contains"})
    assert r["status"] == "passed"
    assert r["score"] == 1.0


def test_matcher_string_contains_pass_exact() -> None:
    """string_contains: exact match passes."""
    r = score_case("hello", "hello", {"type": "string_contains"})
    assert r["status"] == "passed"
    assert r["score"] == 1.0


def test_matcher_string_contains_pass_with_field() -> None:
    """string_contains: options.field extracts string from actual."""
    actual = {"output": "The result is 42", "meta": {}}
    r = score_case("42", actual, {"type": "string_contains", "options": {"field": "output"}})
    assert r["status"] == "passed"
    assert r["score"] == 1.0


def test_matcher_string_contains_fail() -> None:
    """string_contains: expected not in actual fails."""
    r = score_case("xyz", "hello world", {"type": "string_contains"})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


def test_matcher_string_contains_fail_actual_not_string() -> None:
    """string_contains: actual not a string fails."""
    r = score_case("x", {"a": 1}, {"type": "string_contains"})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


def test_matcher_string_contains_fail_field_missing() -> None:
    """string_contains: options.field missing in actual fails."""
    actual = {"other": "value"}
    r = score_case("x", actual, {"type": "string_contains", "options": {"field": "output"}})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


# --- schema_valid ---


def test_matcher_schema_valid_pass() -> None:
    """schema_valid: actual conforms to schema passes."""
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
    r = score_case(None, {"a": 1}, {"type": "schema_valid", "options": {"schema": schema}})
    assert r["status"] == "passed"
    assert r["score"] == 1.0


def test_matcher_schema_valid_pass_array() -> None:
    """schema_valid: array valid against schema passes."""
    schema = {"type": "array", "items": {"type": "string"}}
    r = score_case(None, ["x", "y"], {"type": "schema_valid", "options": {"schema": schema}})
    assert r["status"] == "passed"
    assert r["score"] == 1.0


def test_matcher_schema_valid_fail() -> None:
    """schema_valid: actual violates schema fails."""
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
    r = score_case(None, {"a": "not an int"}, {"type": "schema_valid", "options": {"schema": schema}})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


def test_matcher_schema_valid_fail_wrong_type() -> None:
    """schema_valid: wrong type fails."""
    schema = {"type": "object"}
    r = score_case(None, "not an object", {"type": "schema_valid", "options": {"schema": schema}})
    assert r["status"] == "failed"
    assert r["score"] == 0.0


def test_matcher_schema_valid_error_missing_schema() -> None:
    """schema_valid: missing options.schema returns error."""
    r = score_case(None, {"a": 1}, {"type": "schema_valid"})
    assert r["status"] == "error"
    assert r["score"] == 0.0
    assert "schema" in r["message"].lower()


def test_matcher_schema_valid_error_invalid_schema() -> None:
    """schema_valid: invalid schema returns error."""
    r = score_case(None, {"a": 1}, {"type": "schema_valid", "options": {"schema": {"type": "invalid"}}})
    assert r["status"] == "error"
    assert r["score"] == 0.0


# --- unknown matcher ---


def test_matcher_unknown_type_returns_error() -> None:
    """Unknown matcher type returns error."""
    r = score_case(1, 1, {"type": "unknown_matcher"})
    assert r["status"] == "error"
    assert r["score"] == 0.0


def test_matcher_empty_type_returns_error() -> None:
    """Empty matcher type returns error."""
    r = score_case(1, 1, {})
    assert r["status"] == "error"
    assert r["score"] == 0.0
