"""ADK runtime contract tests with intercepted transport; no live inference or credentials."""
import asyncio
import hashlib
import json
import time

from google.genai import errors, types
from PIL import Image
import pytest

from guide2build.engine.provider import GoogleAdkProvider, ProviderFailure


@pytest.fixture
def transport(monkeypatch):
    from guide2build.engine import adk_runtime
    from guide2build.core import environment

    monkeypatch.setattr(environment, "load_local_environment", lambda: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-unit-test-key")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://unexpected.invalid")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    state = {"text": "{}", "requests": [], "clients": [], "error": None,
             "delay": 0, "cancelled": False, "calls": []}
    original_client = adk_runtime.genai.Client

    async def generate_content(**kwargs):
        state["requests"].append(kwargs)
        try:
            if state["delay"]:
                await asyncio.sleep(state["delay"])
            if state["error"]:
                raise state["error"]
            parts = state.get("parts") or [types.Part.from_text(text=state["text"])]
            return types.GenerateContentResponse(candidates=[types.Candidate(
                content=types.Content(role="model", parts=parts), finish_reason="STOP")],
                usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=11,
                    candidates_token_count=7, thoughts_token_count=2, total_token_count=20))
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    def make_client(**kwargs):
        state["calls"].append(kwargs)
        client = original_client(**kwargs)
        state["clients"].append(client)
        monkeypatch.setattr(client.aio.models, "generate_content", generate_content)
        return client

    monkeypatch.setattr(adk_runtime.genai, "Client", make_client)
    return state


def test_real_adk_runner_sends_images_schema_and_one_developer_api_request(tmp_path, transport):
    page = tmp_path / "page.png"
    Image.new("RGB", (8, 8), "white").save(page)
    schema = {"type": "object", "properties": {"panels": {"type": "array", "items": {"type": "string"}}},
              "required": ["panels"], "additionalProperties": False}
    transport["text"] = '{"panels": ["synthetic-index"]}'
    evidence = tmp_path / "evidence"
    assert GoogleAdkProvider().call("Index the supplied synthetic instruction page.", [page], schema, evidence) == {
        "panels": ["synthetic-index"]}
    assert len(transport["requests"]) == 1
    request = transport["requests"][0]
    assert request["model"] == "gemini-3.8-flash"
    assert request["config"].response_json_schema == schema
    assert request["config"].response_mime_type == "application/json"
    assert request["config"].thinking_config.thinking_level == "MEDIUM"
    assert request["config"].automatic_function_calling.disable is True
    assert not request["config"].tools
    images = [part.inline_data for content in request["contents"] for part in content.parts if part.inline_data]
    assert len(images) == 1 and images[0].data == page.read_bytes() and images[0].mime_type == "image/png"
    client_config = transport["calls"][0]
    assert client_config["vertexai"] is False
    assert client_config["http_options"].base_url == "https://generativelanguage.googleapis.com"
    assert client_config["http_options"].timeout == 120_000
    assert client_config["http_options"].retry_options.attempts == 1
    assert request["config"].http_options.retry_options.attempts == 1
    assert client_config["debug_config"].client_mode is None
    receipt = json.loads((evidence / "invocation.json").read_text())
    assert receipt["images"][0]["sha256"] == hashlib.sha256(page.read_bytes()).hexdigest()
    assert receipt["schema_sha256"] == hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()
    assert receipt["status"] == "completed" and receipt["model_requests_started"] == 1
    assert receipt["reported_usage"] == {"prompt_token_count": 11, "candidates_token_count": 7,
        "thoughts_token_count": 2, "total_token_count": 20}
    assert receipt["tools_disabled"] is True and receipt["provider_fallback"] is False
    assert receipt["completion_or_accuracy_claim"] is False
    assert json.loads((evidence / "runtime-result.json").read_text()) == receipt


def test_each_invocation_has_isolated_context_and_session(tmp_path, transport):
    provider = GoogleAdkProvider(model="gemini-synthetic", thinking_level="low")
    for index, prompt in enumerate(("First synthetic task", "Second synthetic task")):
        assert provider.call(prompt, [], {"type": "object"}, tmp_path / str(index)) == {}
    assert len(transport["clients"]) == len(transport["requests"]) == 2
    second_contents = transport["requests"][1]["contents"]
    assert len(second_contents) == 1 and second_contents[0].parts[0].text == "Second synthetic task"
    assert transport["requests"][1]["config"].thinking_config.thinking_level == "LOW"
    receipts = [json.loads((tmp_path / str(index) / "events.jsonl").read_text().splitlines()[-1]) for index in range(2)]
    assert receipts[0]["invocation_id"] != receipts[1]["invocation_id"]


def test_missing_google_key_has_safe_receipt_and_no_fallback(tmp_path, transport, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-unused-fallback")
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path)
    assert failure.value.code == "authentication_required"
    assert not transport["requests"] and not transport["calls"]
    receipt = json.loads((tmp_path / "invocation.json").read_text())
    assert receipt["model_requests_started"] == 0 and receipt["failure"]["code"] == "authentication_required"


@pytest.mark.parametrize("text", ['{"count": "wrong-type"}', '{"count": 1, "extra": true}',
                                   'Not JSON', '[]', '{}'])
def test_original_engine_schema_rejects_bad_output_without_hidden_retry(tmp_path, transport, text):
    transport["text"] = text
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"],
              "additionalProperties": False}
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], schema, tmp_path)
    assert failure.value.code == "invalid_output"
    assert len(transport["requests"]) == 1
    assert (tmp_path / "response.json").read_text() == text


def test_invalid_local_schema_never_reaches_api(tmp_path, transport):
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], {"type": "nonexistent-json-type"}, tmp_path)
    assert failure.value.code == "invalid_schema"
    assert not transport["requests"] and not transport["calls"]


@pytest.mark.parametrize("status,message,expected", [
    (401, "Invalid authentication", "authentication_required"),
    (403, "Permission denied", "authentication_required"),
    (429, "Rate limit reached", "rate_limited"),
    (429, "Quota exceeded", "quota_exceeded"),
    (400, "response_json_schema invalid array items", "invalid_schema"),
    (404, "Requested model not found", "unsupported_model"),
    (503, "Temporary service failure", "provider_unavailable"),
])
def test_transport_failure_codes_are_sanitized_and_not_retried(tmp_path, transport, status, message, expected):
    transport["error"] = errors.ClientError(status, {"error": {"message":
        f"{message}; key=synthetic-unit-test-key", "status": "SYNTHETIC_ERROR"}})
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path)
    assert failure.value.code == expected
    assert "synthetic-unit-test-key" not in str(failure.value)
    assert failure.value.__suppress_context__ is True
    assert len(transport["requests"]) == 1
    assert all("synthetic-unit-test-key" not in path.read_text() for path in tmp_path.iterdir())
    assert json.loads((tmp_path / "invocation.json").read_text())["failure"]["code"] == expected


def test_timeout_cancels_running_adk_and_retains_actual_receipt(tmp_path, transport):
    transport["delay"] = 30
    started = time.monotonic()
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider(timeout=.08).call("Synthetic task", [], {"type": "object"}, tmp_path)
    assert failure.value.code == "provider_timeout"
    assert time.monotonic() - started < 2 and transport["cancelled"] is True
    receipt = json.loads((tmp_path / "invocation.json").read_text())
    assert receipt["elapsed_seconds"] >= .08 and receipt["status"] == "failed"
    assert receipt["timeout_seconds"] == .08 and receipt["model_requests_started"] == 1


def test_cancellation_check_interrupts_network_and_is_not_provider_failure(tmp_path, transport):
    transport["delay"] = 30
    checks = 0

    def check():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise InterruptedError("synthetic job cancellation")

    started = time.monotonic()
    with pytest.raises(InterruptedError, match="synthetic job cancellation"):
        GoogleAdkProvider(timeout=30).call("Synthetic task", [], {"type": "object"}, tmp_path, check)
    assert time.monotonic() - started < 2 and transport["cancelled"] is True
    assert json.loads((tmp_path / "invocation.json").read_text())["status"] == "cancelled"
    assert len(transport["requests"]) == 1


def test_fenced_lease_loss_cancels_inference_without_pausing_provider(tmp_path, transport):
    from guide2build.engine.store import LeaseLost

    transport["delay"] = 30
    lost = LeaseLost("synthetic-job")
    checks = 0

    def check():
        nonlocal checks
        checks += 1
        if checks == 3:
            raise lost

    with pytest.raises(LeaseLost) as failure:
        GoogleAdkProvider(timeout=30).call("Synthetic task", [], {"type": "object"}, tmp_path, check)
    assert failure.value is lost and transport["cancelled"] is True
    assert json.loads((tmp_path / "invocation.json").read_text())["status"] == "cancelled"


def test_secret_values_are_redacted_in_inputs_outputs_and_event_metadata(tmp_path, transport, monkeypatch):
    secret = "AIza" + "synthetic" * 5
    monkeypatch.setenv("GOOGLE_API_KEY", secret)
    transport["text"] = json.dumps({"note": secret})
    assert GoogleAdkProvider().call(f"Synthetic task with inadvertent key {secret}", [], {"type": "object"}, tmp_path) == {
        "note": "[REDACTED]"}
    assert "[REDACTED]" in transport["requests"][0]["contents"][0].parts[0].text
    assert all(secret not in path.read_text() for path in tmp_path.iterdir())


def test_thought_content_is_not_recorded_as_response(tmp_path, transport):
    transport["parts"] = [types.Part(text="Private thought data", thought=True), types.Part.from_text(text="{}")]
    assert GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path) == {}
    assert all("Private thought data" not in path.read_text() for path in tmp_path.iterdir())


def test_attempted_tool_call_is_rejected_without_execution_or_second_request(tmp_path, transport):
    transport["parts"] = [types.Part(function_call=types.FunctionCall(name="unexpected_tool", args={}))]
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path)
    assert failure.value.code == "invalid_output"
    assert len(transport["requests"]) == 1


@pytest.mark.parametrize("callback_error", [RuntimeError, ProviderFailure])
def test_unexpected_callback_errors_do_not_leak_credentials(tmp_path, transport, callback_error):
    def check():
        if callback_error is ProviderFailure:
            raise ProviderFailure("provider_unavailable", "Unexpected synthetic-unit-test-key diagnostic")
        raise RuntimeError("Unexpected synthetic-unit-test-key diagnostic")

    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path, check)
    assert "synthetic-unit-test-key" not in str(failure.value)
    assert all("synthetic-unit-test-key" not in path.read_text() for path in tmp_path.iterdir())
    assert not transport["requests"]


@pytest.mark.parametrize("options", [{"model": "gpt-synthetic"}, {"thinking_level": "medium; shell"},
    {"thinking_level": "minimal"},
    {"timeout": 0}, {"timeout": -1}, {"timeout": float("inf")}, {"timeout": float("nan")}, {"timeout": True}])
def test_provider_config_is_bounded_before_runtime_creation(options):
    with pytest.raises(ValueError):
        GoogleAdkProvider(**options)
