import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, List

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """
    Import the FastAPI app from the runtime.

    The implementation is expected to expose `app` at `app.main`.
    If the contract changes, update this fixture.
    """
    from app.main import app as fastapi_app  # type: ignore

    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app)


@contextmanager
def env_vars(env: Dict[str, str]):
    """
    Temporarily set environment variables for a test.

    Restores previous values afterwards, even if the test fails.
    """
    old_values: Dict[str, Any] = {}
    for key, value in env.items():
        old_values[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, old in old_values.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _assert_error_envelope(resp_json: Dict[str, Any], expected_code: str):
    assert "error" in resp_json, "Error responses must include 'error' envelope"
    assert "meta" in resp_json, "Error responses must include 'meta' envelope"

    error = resp_json["error"]
    meta = resp_json["meta"]

    assert error.get("code") == expected_code
    # Minimal meta contract: request_id, agent, version
    assert isinstance(meta.get("request_id"), str)
    assert isinstance(meta.get("agent"), str)
    assert isinstance(meta.get("version"), str)


def _load_preset_yaml(preset_id: str) -> Dict[str, Any]:
    """
    Helper to load the active preset YAML, mirroring tests in test_presets.

    This is used by endpoint tests (e.g. /schema) to assert the runtime
    reflects the underlying preset configuration.
    """
    presets_dir = Path(__file__).parent.parent / "app" / "presets"
    preset_path = presets_dir / f"{preset_id}.yaml"
    assert preset_path.exists(), f"Preset file not found: {preset_path}"
    import yaml

    with preset_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


### 2) Auth behavior ###########################################################


def test_invoke_requires_auth_when_token_set(client, monkeypatch):
    """
    When AUTH_TOKEN is set, POST /invoke without Authorization must return 401.
    """

    with env_vars(
        {
            "AUTH_TOKEN": "secret-token",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        resp = client.post("/invoke", json={"input": {"text": "hello"}})
        assert resp.status_code == 401
        data = resp.json()
        _assert_error_envelope(data, expected_code="UNAUTHORIZED")


def test_invoke_wrong_token_rejected(client, monkeypatch):
    """
    When AUTH_TOKEN is set, wrong bearer token must return 401.
    """
    with env_vars(
        {
            "AUTH_TOKEN": "secret-token",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        resp = client.post(
            "/invoke",
            headers={"Authorization": "Bearer not-the-token"},
            json={"input": {"text": "hello"}},
        )
        assert resp.status_code == 401
        data = resp.json()
        _assert_error_envelope(data, expected_code="UNAUTHORIZED")


def test_invoke_succeeds_without_auth_when_token_unset(client):
    """
    When AUTH_TOKEN is unset, /invoke must accept requests without Authorization.
    """
    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        resp = client.post("/invoke", json={"input": {"text": "hello"}})
        # Exact behavior (200 vs validation errors) is covered elsewhere;
        # here we only assert that lack of Authorization header does NOT
        # result in 401 when AUTH_TOKEN is not enforced.
        assert resp.status_code != 401


def test_invoke_succeeds_with_correct_token(client):
    """
    When AUTH_TOKEN is set and Authorization: Bearer <token> provided,
    the request should proceed to normal processing (non-401).
    """
    with env_vars(
        {
            "AUTH_TOKEN": "secret-token",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        resp = client.post(
            "/invoke",
            headers={"Authorization": "Bearer secret-token"},
            json={"input": {"text": "hello"}},
        )
        assert resp.status_code != 401


### 3) Invoke success path with StubProvider ###################################


def _assert_success_meta(meta: Dict[str, Any], expected_agent: str, expected_version: str):
    assert isinstance(meta.get("request_id"), str)
    assert meta.get("agent") == expected_agent
    assert meta.get("version") == expected_version
    assert isinstance(meta.get("latency_ms"), (int, float))


@pytest.mark.parametrize("preset_id,input_body", [
    ("summarizer", {"input": {"text": "Some long text to summarize."}}),
    # Using classifier as an example of classify/extract style preset
    ("classifier", {"input": {"items": [{"id": "1", "content": "foo"}]}}),
])
def test_invoke_returns_valid_output_with_stub_provider(client, preset_id, input_body):
    """
    For each preset (at least summarizer and one classify/extract preset),
    POST /invoke with a valid input must:
    - return 200
    - include 'output' and 'meta'
    - meta contains { request_id, agent, version, latency_ms }
    - output is expected to validate against the preset's output_schema

    NOTE: The actual JSON-schema validation of the runtime output is not
    re-done here to avoid over-coupling test and implementation; we assume
    the runtime validates against the same preset.output_schema that the
    preset tests already check for correctness.
    """
    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": preset_id,
        }
    ):
        resp = client.post("/invoke", json=input_body)
        assert resp.status_code == 200
        data = resp.json()

        assert "output" in data
        assert "meta" in data
        meta = data["meta"]

        # We can only assert that agent/version are consistent with the preset id;
        # exact version is runtime-defined but must be a string.
        assert meta.get("agent") == preset_id
        assert isinstance(meta.get("version"), str)
        assert isinstance(meta.get("request_id"), str)
        assert isinstance(meta.get("latency_ms"), (int, float))


### 4) Input validation failure ################################################


def test_invoke_malformed_json_returns_400_malformed_request(client):
    """
    Sending invalid JSON must result in:
    - HTTP 400
    - error.code == MALFORMED_REQUEST
    - meta contains request_id, agent, version
    """
    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        resp = client.post(
            "/invoke",
            content="{ this is not valid json }",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        _assert_error_envelope(data, expected_code="MALFORMED_REQUEST")


def test_invoke_semantically_invalid_input_returns_422_input_validation_error(client):
    """
    Sending syntactically valid JSON but wrong structure (missing required fields)
    must result in:
    - HTTP 422
    - error.code == INPUT_VALIDATION_ERROR
    - error.details includes at least one validation error description
    """
    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        # Assuming summarizer expects {"input": {"text": "..."}}
        # We omit 'text' to trigger validation failure.
        resp = client.post("/invoke", json={"input": {}})
        assert resp.status_code == 422
        data = resp.json()

        _assert_error_envelope(data, expected_code="INPUT_VALIDATION_ERROR")
        details = data["error"].get("details")
        assert isinstance(details, list) and len(details) > 0


### 5) Output validation and repair loop #######################################


class RecordingProvider:
    """
    Test double for the provider that returns a sequence of outputs.

    The runtime is expected to:
    - Call the provider once for the primary output.
    - If output-schema validation fails, call it at most once more to "repair".

    These tests therefore assert the call count to enforce a single repair loop.
    """

    def __init__(self, outputs: List[Dict[str, Any]]):
        self._outputs = outputs
        self.calls = 0

    def __call__(self, *args, **kwargs) -> Dict[str, Any]:
        idx = min(self.calls, len(self._outputs) - 1)
        self.calls += 1
        return self._outputs[idx]


class RaisingProvider:
    """Provider that always raises, to induce a controlled 500 INTERNAL_ERROR."""

    def __call__(self, *args, **kwargs):
        raise RuntimeError("provider failure for testing")


def _override_provider(app, provider):
    """
    Override the runtime's provider dependency with a test double.

    Contract for backend:
    - There must be a dependency function `get_provider` in `app.dependencies`
      that is used by the /invoke route via FastAPI's dependency injection.
    """
    from app.dependencies import get_provider  # type: ignore

    app.dependency_overrides[get_provider] = lambda: provider
    return get_provider


def test_invoke_repairs_invalid_output_once_then_succeeds(app, client):
    """
    Provider first returns output that violates the summarizer output_schema,
    then returns a valid output on the repair attempt.

    Expectations:
    - Runtime performs output-schema validation.
    - On first failure, it calls the provider exactly one more time.
    - Final response is 200 with standard success envelope.
    """
    invalid_output = {"summary": 123, "bullets": "not-an-array"}
    valid_output = {"summary": "ok summary", "bullets": ["point 1", "point 2"]}
    provider = RecordingProvider([invalid_output, valid_output])

    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post("/invoke", json={"input": {"text": "repair me"}})
        finally:
            # Clean up override so other tests see the real provider.
            app.dependency_overrides.pop(get_provider, None)

    assert provider.calls == 2, "Provider should be called exactly twice (primary + one repair)"
    assert resp.status_code == 200
    data = resp.json()
    assert "output" in data
    assert "meta" in data
    meta = data["meta"]
    assert meta.get("agent") == "summarizer"
    assert isinstance(meta.get("version"), str)
    assert isinstance(meta.get("request_id"), str)
    assert isinstance(meta.get("latency_ms"), (int, float))


def test_invoke_fails_when_output_invalid_after_repair(app, client):
    """
    When both the original and repair outputs violate the output_schema,
    runtime must respond with:
    - HTTP 422
    - error.code == OUTPUT_VALIDATION_ERROR
    - standard error/meta envelopes
    """
    invalid_output_1 = {"summary": 123, "bullets": "still-wrong"}
    invalid_output_2 = {"summary": None, "bullets": [1, 2, 3]}
    provider = RecordingProvider([invalid_output_1, invalid_output_2])

    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post("/invoke", json={"input": {"text": "still invalid"}})
        finally:
            app.dependency_overrides.pop(get_provider, None)

    assert provider.calls == 2, "Provider should be called at most twice (primary + one repair)"
    assert resp.status_code == 422
    data = resp.json()
    _assert_error_envelope(data, expected_code="OUTPUT_VALIDATION_ERROR")


def test_invoke_internal_error_from_provider_raises_500(app, client):
    """
    A provider-level failure should surface as:
    - HTTP 500
    - error.code == INTERNAL_ERROR
    - standard error/meta envelopes.
    """
    provider = RaisingProvider()

    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        get_provider = _override_provider(app, provider)
        try:
            resp = client.post("/invoke", json={"input": {"text": "boom"}})
        finally:
            app.dependency_overrides.pop(get_provider, None)

    assert resp.status_code == 500
    data = resp.json()
    _assert_error_envelope(data, expected_code="INTERNAL_ERROR")


### 6) Other endpoints: /, /schema, /health, /stream ###########################


def test_root_endpoint_returns_service_metadata(client):
    """
    GET / should return service metadata for the active preset.
    """
    preset_id = "summarizer"
    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": preset_id,
        }
    ):
        resp = client.get("/")

    assert resp.status_code == 200
    data = resp.json()
    for key in ["service", "agent", "version", "docs", "schema", "health"]:
        assert key in data

    assert data["service"] == "agent-gateway"
    assert data["agent"] == preset_id
    assert data["docs"] == "/docs"
    assert data["schema"] == "/schema"
    assert data["health"] == "/health"
    assert isinstance(data["version"], str)


def test_schema_endpoint_matches_preset(client):
    """
    GET /schema must reflect the loaded preset exactly.
    """
    preset_id = "summarizer"
    preset = _load_preset_yaml(preset_id)

    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": preset_id,
        }
    ):
        resp = client.get("/schema")

    assert resp.status_code == 200
    data = resp.json()

    for key in ["agent", "version", "primitive", "input_schema", "output_schema"]:
        assert key in data

    assert data["agent"] == preset["id"]
    assert data["version"] == preset["version"]
    assert data["primitive"] == preset["primitive"]
    assert data["input_schema"] == preset["input_schema"]
    assert data["output_schema"] == preset["output_schema"]


def test_health_endpoint_ok(client):
    """
    GET /health should return a simple status document when preset loads.
    """
    preset_id = "summarizer"
    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": preset_id,
        }
    ):
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    for key in ["status", "agent", "version"]:
        assert key in data

    assert data["agent"] == preset_id
    # Tighten contract: health.status should be "ok" in the happy path.
    assert data["status"] == "ok"
    assert isinstance(data["version"], str)


def test_stream_endpoint_not_implemented_returns_501(client):
    """
    POST /stream is not implemented yet.

    NOTE: We standardize `error.code` here as "NOT_IMPLEMENTED" for 501,
    keeping 500 reserved for "INTERNAL_ERROR" as per the main contract.
    """
    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        resp = client.post("/stream", json={"input": {"text": "stream me"}})

    assert resp.status_code == 501
    data = resp.json()
    _assert_error_envelope(data, expected_code="NOT_IMPLEMENTED")


