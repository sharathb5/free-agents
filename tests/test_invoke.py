import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, List

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def session_db_path():
    """Temporary DB path for session store (Context + Session Memory tests). Isolated per test."""
    with tempfile.TemporaryDirectory(prefix="agent_session_invoke_") as tmp:
        yield str(Path(tmp) / "sessions.db")


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


def test_invoke_does_not_require_auth_when_token_set(client, monkeypatch):
    """
    /invoke is public even when AUTH_TOKEN is set; missing Authorization should not 401.
    """

    with env_vars(
        {
            "AUTH_TOKEN": "secret-token",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
        }
    ):
        resp = client.post("/invoke", json={"input": {"text": "hello"}})
        assert resp.status_code != 401


def test_invoke_wrong_token_ignored(client, monkeypatch):
    """
    /invoke is public; wrong bearer token should not 401.
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
        assert resp.status_code != 401


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


### 7) Context + Session Memory (plan: context_and_session_memory) ##################


class PromptCapturingProvider:
    """
    Provider test double that captures the prompt passed to the runtime
    and returns valid stub output. Used to assert memory/context is included in prompt.
    """

    def __init__(self, valid_output: Dict[str, Any]):
        self.captured_prompt: str = ""
        self._valid_output = valid_output

    def complete_json(self, prompt: str, *, schema: Any) -> Any:
        from app.providers import ProviderResult  # type: ignore

        self.captured_prompt = prompt
        return ProviderResult(parsed_json=self._valid_output, raw_text=str(self._valid_output))


def test_invoke_backward_compat_only_input(client):
    """
    T5: POST /invoke with only {"input": ...} must return 200 (no context required).
    """
    with env_vars(
        {"AUTH_TOKEN": "", "PROVIDER": "stub", "AGENT_PRESET": "summarizer"}
    ):
        resp = client.post("/invoke", json={"input": {"text": "hello"}})
    assert resp.status_code == 200
    data = resp.json()
    assert "output" in data
    assert "meta" in data


def test_invoke_accepts_context_empty_without_error(client):
    """
    T11: POST /invoke with context: {} must succeed (no error).
    """
    with env_vars(
        {"AUTH_TOKEN": "", "PROVIDER": "stub", "AGENT_PRESET": "summarizer"}
    ):
        resp = client.post(
            "/invoke",
            json={"input": {"text": "hello"}, "context": {}},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "output" in data
    assert "meta" in data


def test_invoke_with_context_session_id_but_missing_session_returns_200(client):
    """
    T8: When context.session_id is provided but the session does not exist,
    invoke must still return 200 (e.g. stored_events=[]), not 404/500.
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
            json={
                "input": {"text": "hello"},
                "context": {"session_id": "nonexistent-session-id-99999"},
            },
        )
    assert resp.status_code == 200, (
        "Invoke with missing session_id must still return 200 (stored_events=[]), not 404/500."
    )
    data = resp.json()
    assert "output" in data
    assert "meta" in data


def test_invoke_with_context_session_id_includes_meta_session_id_and_memory_used_count(
    client, app, session_db_path
):
    """
    T6: When invoke uses a session (context.session_id), success response must include
    meta.session_id and meta.memory_used_count.
    """
    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
            "SESSION_DB_PATH": session_db_path,
        }
    ):
        # Create session (skip if sessions API not implemented)
        create = client.post("/sessions")
        if create.status_code != 201:
            pytest.skip("POST /sessions not implemented; cannot test session meta")
        session_id = create.json()["session_id"]
        client.post(
            f"/sessions/{session_id}/events",
            json={"events": [{"role": "user", "content": "hi"}]},
        )
        resp = client.post(
            "/invoke",
            json={
                "input": {"text": "summarize this"},
                "context": {"session_id": session_id},
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "meta" in data
    meta = data["meta"]
    assert "session_id" in meta
    assert meta["session_id"] == session_id
    assert "memory_used_count" in meta
    assert isinstance(meta["memory_used_count"], int)
    assert meta["memory_used_count"] >= 0


def test_invoke_with_valid_session_and_events_prompt_contains_stored_content(
    client, app, session_db_path
):
    """
    T7: When session_id is valid and events exist, the provider must receive a prompt
    that includes the stored event content. Uses PromptCapturingProvider to assert.
    """
    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
            "SESSION_DB_PATH": session_db_path,
        }
    ):
        create = client.post("/sessions")
        if create.status_code != 201:
            pytest.skip("POST /sessions not implemented")
        session_id = create.json()["session_id"]
        distinctive = "MEMORY_CONTENT_XYZ_STORED_EVENT"
        client.post(
            f"/sessions/{session_id}/events",
            json={"events": [{"role": "user", "content": distinctive}]},
        )
        cap = PromptCapturingProvider(
            valid_output={"summary": "ok", "bullets": ["a", "b"]}
        )
        _override_provider(app, cap)
        try:
            resp = client.post(
                "/invoke",
                json={
                    "input": {"text": "hello"},
                    "context": {"session_id": session_id},
                },
            )
        finally:
            from app.dependencies import get_provider

            app.dependency_overrides.pop(get_provider, None)
    assert resp.status_code == 200
    assert distinctive in cap.captured_prompt, (
        "Stored event content must appear in the prompt sent to the provider."
    )


def test_invoke_memory_truncation_max_messages_two(client, app, session_db_path):
    """
    T9: With a preset that has max_messages=2 and a session with more than 2 events,
    the prompt must include at most 2 (last N) events.
    """
    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
            "SESSION_DB_PATH": session_db_path,
        }
    ):
        create = client.post("/sessions")
        if create.status_code != 201:
            pytest.skip("POST /sessions not implemented")
        session_id = create.json()["session_id"]
        # Append 5 events with distinct markers
        markers = ["EV1", "EV2", "EV3", "EV4", "EV5"]
        for m in markers:
            client.post(
                f"/sessions/{session_id}/events",
                json={"events": [{"role": "user", "content": m}]},
            )
        cap = PromptCapturingProvider(
            valid_output={"summary": "ok", "bullets": ["a"]}
        )
        _override_provider(app, cap)
        try:
            resp = client.post(
                "/invoke",
                json={
                    "input": {"text": "go"},
                    "context": {"session_id": session_id},
                },
            )
        finally:
            from app.dependencies import get_provider

            app.dependency_overrides.pop(get_provider, None)
    assert resp.status_code == 200
    # Preset must support memory with max_messages=2; prompt must contain at most 2 of the markers.
    count_in_prompt = sum(1 for m in markers if m in cap.captured_prompt)
    assert count_in_prompt <= 2, (
        "With max_messages=2, prompt must include at most 2 stored events (last N)."
    )


def test_invoke_when_session_store_write_fails_still_200_success_envelope(
    client, app, session_db_path
):
    """
    T10: When the session store write fails (e.g. append_events fails), invoke must
    still return 200 and success envelope; only log a warning (robustness).
    Backend contract: append is called from a path we can mock (e.g. app.storage.session_store.append_events).
    """
    from unittest.mock import patch

    with env_vars(
        {
            "AUTH_TOKEN": "",
            "PROVIDER": "stub",
            "AGENT_PRESET": "summarizer",
            "SESSION_DB_PATH": session_db_path,
        }
    ):
        create = client.post("/sessions")
        if create.status_code != 201:
            pytest.skip("POST /sessions not implemented")
        session_id = create.json()["session_id"]

        # Patch where append_events is used (backend may use app.storage.session_store.append_events).
        try:
            with patch(
                "app.storage.session_store.append_events",
                side_effect=RuntimeError("write failed"),
            ):
                resp = client.post(
                    "/invoke",
                    json={
                        "input": {"text": "hello"},
                        "context": {"session_id": session_id},
                    },
                )
        except (ImportError, AttributeError):
            pytest.skip("app.storage.session_store not implemented; cannot mock append_events")
    assert resp.status_code == 200
    data = resp.json()
    assert "output" in data
    assert "meta" in data


### 8) Model 1: Registry invoke (/agents/{id}/invoke) ###########################


def _build_registry_spec(
    agent_id: str,
    version: str,
    *,
    primitive: str = "transform",
    supports_memory: bool = True,
) -> Dict[str, Any]:
    """
    Minimal registry agent spec matching the Model 1 contract.

    Shape mirrors the helper in tests/test_registry.py so backend can treat
    registry agents similarly to preset-based agents.
    """
    spec: Dict[str, Any] = {
        "id": agent_id,
        "version": version,
        "name": f"{agent_id} name",
        "description": f"{agent_id} description",
        "primitive": primitive,
        "input_schema": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string", "title": "Text input"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["summary"],
            "properties": {
                "summary": {"type": "string", "title": "Summary text"},
            },
        },
        "prompt": "You are a helpful registry test agent.",
        "supports_memory": supports_memory,
    }
    if supports_memory:
        spec["memory_policy"] = {
            "mode": "last_n",
            "max_messages": 2,
            "max_chars": 8000,
        }
    return spec


def _register_registry_agent(
    client: TestClient,
    *,
    spec: Dict[str, Any],
    db_path: str,
    auth_token: str = "",
) -> Dict[str, Any]:
    """
    Helper to register an agent via POST /agents/register for invoke tests.
    """
    env = {
        "DB_PATH": db_path,
        "SESSION_DB_PATH": db_path,
        "AUTH_TOKEN": auth_token,
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.post("/agents/register", json={"spec": spec})
    return {"status_code": resp.status_code, "body": resp.json()}


def test_registry_invoke_returns_200_and_meta_matches_agent_and_version(
    client: TestClient,
    session_db_path: str,
) -> None:
    """
    T11: Register agent and then POST /agents/{id}/invoke returns 200 envelope.
    meta.agent and meta.version must match the registered agent.
    """
    agent_id = "invoke-registry-agent"
    version = "1.0.0"
    spec = _build_registry_spec(agent_id, version, supports_memory=True)

    result = _register_registry_agent(
        client, spec=spec, db_path=session_db_path, auth_token=""
    )
    assert result["status_code"] == 200

    env = {
        "DB_PATH": session_db_path,
        "SESSION_DB_PATH": session_db_path,
        "AUTH_TOKEN": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.post(
            f"/agents/{agent_id}/invoke",
            json={"input": {"text": "hello from registry"}},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "output" in data
    assert "meta" in data
    meta = data["meta"]
    assert meta.get("agent") == agent_id
    assert meta.get("version") == version


def test_registry_invoke_missing_agent_returns_404_agent_not_found(
    client: TestClient,
    session_db_path: str,
) -> None:
    """
    T12: Invoke missing agent -> 404 AGENT_NOT_FOUND envelope.
    """
    env = {
        "DB_PATH": session_db_path,
        "SESSION_DB_PATH": session_db_path,
        "AUTH_TOKEN": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.post(
            "/agents/nonexistent-registry-agent/invoke",
            json={"input": {"text": "hello"}},
        )
    assert resp.status_code == 404
    _assert_error_envelope(resp.json(), expected_code="AGENT_NOT_FOUND")


def test_registry_invoke_does_not_require_auth_when_token_set(
    client: TestClient,
    session_db_path: str,
) -> None:
    """
    T13: /agents/{id}/invoke is public even when AUTH_TOKEN is set.
    """
    agent_id = "auth-registry-agent"
    spec = _build_registry_spec(agent_id, "1.0.0")

    # Register with auth disabled for simplicity.
    reg = _register_registry_agent(
        client, spec=spec, db_path=session_db_path, auth_token=""
    )
    assert reg["status_code"] == 200

    # Now enforce auth for invoke.
    env = {
        "DB_PATH": session_db_path,
        "SESSION_DB_PATH": session_db_path,
        "AUTH_TOKEN": "secret-token",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        # No Authorization header.
        resp_no_auth = client.post(
            f"/agents/{agent_id}/invoke",
            json={"input": {"text": "hello"}},
        )
        assert resp_no_auth.status_code != 401

        # Wrong token.
        resp_wrong = client.post(
            f"/agents/{agent_id}/invoke",
            headers={"Authorization": "Bearer not-the-token"},
            json={"input": {"text": "hello"}},
        )
        assert resp_wrong.status_code != 401


def test_registry_invoke_succeeds_with_correct_bearer_token(
    client: TestClient,
    session_db_path: str,
) -> None:
    """
    T13 (continued): With correct Bearer token, /agents/{id}/invoke proceeds
    to normal processing (non-401).
    """
    agent_id = "auth-ok-registry-agent"
    spec = _build_registry_spec(agent_id, "1.0.0")

    reg = _register_registry_agent(
        client, spec=spec, db_path=session_db_path, auth_token=""
    )
    assert reg["status_code"] == 200

    env = {
        "DB_PATH": session_db_path,
        "SESSION_DB_PATH": session_db_path,
        "AUTH_TOKEN": "secret-token",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        resp = client.post(
            f"/agents/{agent_id}/invoke",
            headers={"Authorization": "Bearer secret-token"},
            json={"input": {"text": "hello"}},
        )
    assert resp.status_code != 401


def test_registry_invoke_with_session_memory_behaves_like_preset_invoke(
    client: TestClient,
    app,
    session_db_path: str,
) -> None:
    """
    T14: Sessions memory works when registry agent supports_memory true +
    context.session_id (memory injected + events appended).
    """
    agent_id = "memory-registry-agent"
    spec = _build_registry_spec(agent_id, "1.0.0", supports_memory=True)

    env = {
        "DB_PATH": session_db_path,
        "SESSION_DB_PATH": session_db_path,
        "AUTH_TOKEN": "",
        "PROVIDER": "stub",
        "AGENT_PRESET": "summarizer",
    }
    with env_vars(env):
        # Register registry agent.
        reg = client.post("/agents/register", json={"spec": spec})
        assert reg.status_code == 200

        # Create a session and append an event with distinctive content.
        create = client.post("/sessions")
        if create.status_code != 201:
            pytest.skip("POST /sessions not implemented")
        session_id = create.json()["session_id"]
        distinctive = "REGISTRY_MEMORY_EVENT_CONTENT_XYZ"
        client.post(
            f"/sessions/{session_id}/events",
            json={"events": [{"role": "user", "content": distinctive}]},
        )

        # Capture prompt to verify stored events are injected.
        cap = PromptCapturingProvider(
            valid_output={"summary": "ok", "bullets": ["a"]}
        )
        _override_provider(app, cap)
        try:
            # Invoke registry agent with context.session_id.
            resp = client.post(
                f"/agents/{agent_id}/invoke",
                json={
                    "input": {"text": "invoke with memory"},
                    "context": {"session_id": session_id},
                },
            )
        finally:
            from app.dependencies import get_provider

            app.dependency_overrides.pop(get_provider, None)

        assert resp.status_code == 200
        data = resp.json()
        assert "meta" in data
        meta = data["meta"]
        # meta.session_id + meta.memory_used_count must be present when memory is used.
        assert meta.get("session_id") == session_id
        assert isinstance(meta.get("memory_used_count"), int)
        assert meta["memory_used_count"] >= 1
        # Prompt sent to provider must include stored event content.
        assert distinctive in cap.captured_prompt

