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


def test_transport_schema_is_separately_recorded_and_original_output_validation_is_authoritative(tmp_path, transport):
    from guide2build.engine.contracts import strict_schema
    from guide2build.engine.panel_index import PageIndexV2
    from guide2build.engine.schema_transport import CONVERSION_VERSION, project_schema

    schema = strict_schema(PageIndexV2)
    original_bytes = json.dumps(schema, sort_keys=True, ensure_ascii=False).encode()
    value = {"schema_version": "2.0", "source_sha256": "a" * 64, "page_index": 0,
             "page_sha256": "b" * 64, "panels": [], "uncertainty": []}
    transport["text"] = json.dumps(value)
    assert GoogleAdkProvider().call("Synthetic page-index transport task", [], schema, tmp_path) == value
    projected = project_schema(schema)
    assert transport["requests"][0]["config"].response_json_schema == projected
    assert json.loads((tmp_path / "schema.json").read_text()) == schema
    assert json.loads((tmp_path / "transport_schema.json").read_text()) == projected
    assert json.dumps(schema, sort_keys=True, ensure_ascii=False).encode() == original_bytes
    receipt = json.loads((tmp_path / "invocation.json").read_text())
    assert receipt["schema_sha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert receipt["transport_schema_sha256"] == hashlib.sha256(
        json.dumps(projected, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert receipt["schema_conversion_version"] == CONVERSION_VERSION
    assert receipt["schema_sha256"] != receipt["transport_schema_sha256"]
    assert len(transport["requests"]) == 1


@pytest.mark.parametrize("invalid", [{"source_sha256": "not-a-sha256"}, {"uncertainty": [""]},
    {"uncertainty": ["x" * 2001]}, {"schema_version": "unrecognized"}, {"page_index": 2000}])
def test_original_page_index_constraints_still_reject_projected_output(tmp_path, transport, invalid):
    from guide2build.engine.contracts import strict_schema
    from guide2build.engine.panel_index import PageIndexV2

    value = {"schema_version": "2.0", "source_sha256": "a" * 64, "page_index": 0,
             "page_sha256": "b" * 64, "panels": [], "uncertainty": [], **invalid}
    transport["text"] = json.dumps(value)
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic invalid page-index task", [], strict_schema(PageIndexV2), tmp_path)
    assert failure.value.code == "invalid_output"
    assert len(transport["requests"]) == 1


def test_original_array_cap_remains_strict_after_variable_transport_cap_is_omitted(tmp_path, transport):
    from jsonschema.validators import validator_for
    from guide2build.engine.contracts import strict_schema
    from guide2build.engine.panel_index import PageIndexV2
    from guide2build.engine.schema_transport import CONVERSION_VERSION, project_schema

    schema = strict_schema(PageIndexV2)
    value = {"schema_version": "2.0", "source_sha256": "a" * 64, "page_index": 0,
        "page_sha256": "b" * 64, "panels": [], "uncertainty": ["synthetic note"] * 65}
    projected = project_schema(schema)
    assert "maxItems" not in projected["properties"]["uncertainty"]
    validator_for(projected)(projected).validate(value)
    transport["text"] = json.dumps(value)
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic array-budget postvalidation test", [], schema, tmp_path)
    assert failure.value.code == "invalid_output"
    assert len(transport["requests"]) == 1
    assert json.loads((tmp_path / "schema.json").read_text())["properties"]["uncertainty"]["maxItems"] == 64
    receipt = json.loads((tmp_path / "invocation.json").read_text())
    assert receipt["schema_conversion_version"] == CONVERSION_VERSION == "gemini-json-subset-v2"


def test_numeric_exclusive_constraint_remains_strict_after_wire_broadening(tmp_path, transport):
    schema = {"type": "object", "properties": {"value": {"type": "number", "exclusiveMaximum": 1}},
        "required": ["value"], "additionalProperties": False}
    transport["text"] = '{"value": 1}'
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic numeric boundary task", [], schema, tmp_path)
    assert failure.value.code == "invalid_output"
    assert transport["requests"][0]["config"].response_json_schema["properties"]["value"] == {
        "type": "number", "maximum": 1}
    assert len(transport["requests"]) == 1


@pytest.mark.parametrize("family", ["exploration", "comparison", "localized_comparison"])
def test_real_proposal_and_comparison_string_constraints_remain_local_authority(tmp_path, transport, family):
    from jsonschema.validators import validator_for
    from guide2build.engine.contracts import strict_schema
    from guide2build.engine.exploration import CandidateComparison, exploration_proposal_type
    from guide2build.engine.localized_review import CandidateComparison as LocalizedComparison
    from guide2build.engine.schema_transport import project_schema

    if family == "exploration":
        model = exploration_proposal_type()
        value = {"delta_json": None, "blockers": [], "observations": [], "connections": [], "roots": [],
            "source_views": [], "part_observations": [], "placement_hints": [], "sequence": [{
                "step_id": "synthetic-step", "kind": "attachment", "printed_label": None,
                "bbox": [0, 0, 1, 1], "explanation": ""}]}
    else:
        model = LocalizedComparison if family == "localized_comparison" else CandidateComparison
        value = {"selected_hypothesis_id": None, "reason": "", "reviews": [{"hypothesis_id": "synthetic",
            "coverage_agrees": True, "assembly_agrees": True, "findings": [], "visible_defects": []}]}
    schema = strict_schema(model)
    # The synthetic result fits the projected wire schema, while its empty
    # explanation/reason fails the original engine's omitted minLength bound.
    projected = project_schema(schema)
    validator_for(projected)(projected).validate(value)
    transport["text"] = json.dumps(value)
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic omitted-constraint test", [], schema, tmp_path)
    assert failure.value.code == "invalid_output"
    assert len(transport["requests"]) == 1


@pytest.mark.parametrize("schema", [
    {"$defs": {"loop": {"type": "object", "properties": {"self": {"$ref": "#/$defs/loop"}}}},
        "$ref": "#/$defs/loop"},
    {"type": "object", "properties": {"value": {"$ref": "https://untrusted.invalid/schema"}}}])
def test_untransportable_schema_never_creates_an_sdk_client_or_model_request(tmp_path, transport, schema):
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic rejected schema", [], schema, tmp_path)
    assert failure.value.code == "invalid_schema"
    assert not transport["requests"] and not transport["calls"]
    receipt = json.loads((tmp_path / "invocation.json").read_text())
    assert receipt["model_requests_started"] == 0
    assert "https://" not in receipt["failure"]["message"]


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
    (400, "Request contains an invalid argument.", "request_rejected"),
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


def test_private_api_diagnostic_survives_adk_error_events_without_http_objects(tmp_path, transport, caplog):
    transport["error"] = errors.ClientError(400, {
        "error": {"status": "INVALID_ARGUMENT", "message":
            "Rejected response_json_schema field; see https://private.invalid/path?key=private-url-key "
            "api_key=other-private-key synthetic-unit-test-key"},
        "headers": {"Authorization": "Bearer private-header-token", "x-goog-api-key": "private-header-key"},
        "request": {"url": "https://private.invalid/?key=private-url-key"}})
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path)
    assert failure.value.code == "invalid_schema"
    diagnostic = json.loads((tmp_path / "invocation.json").read_text())["diagnostic"]
    assert diagnostic == {"exception_class": "ClientError", "http_status": 400, "category": "api_response",
        "api_status": "INVALID_ARGUMENT", "api_message":
            "Rejected response_json_schema field; see [REDACTED_URL] credential=[REDACTED] [REDACTED]"}
    assert len(transport["requests"]) == 1
    for secret in ("private-url-key", "other-private-key", "private-header-token", "private-header-key",
                   "synthetic-unit-test-key", "private.invalid"):
        assert secret not in caplog.text
        assert all(secret not in path.read_text() for path in tmp_path.iterdir())
    assert "headers" not in diagnostic and "request" not in diagnostic and "response" not in diagnostic


def test_header_bearing_api_messages_are_replaced_with_category_not_header_data(tmp_path, transport):
    transport["error"] = errors.ClientError(503, {"error": {"status": "UNAVAILABLE", "message":
        'Upstream rejected headers={"Authorization":"Bearer unconfigured-private-key", '
        '"Cookie":"private-session"}; x-goog-api-key=private-key'}})
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path)
    assert failure.value.code == "provider_unavailable"
    diagnostic = json.loads((tmp_path / "invocation.json").read_text())["diagnostic"]
    assert diagnostic["api_message"] == "[REDACTED_HEADER_DIAGNOSTIC]"
    assert diagnostic["http_status"] == 503 and diagnostic["exception_class"] == "ClientError"
    assert len(transport["requests"]) == 1
    assert all("unconfigured-private-key" not in path.read_text() and "private-session" not in path.read_text()
               for path in tmp_path.iterdir())


def test_non_api_diagnostic_never_serializes_raw_exception_string(tmp_path, transport):
    transport["error"] = AttributeError("Unexpected object headers: Authorization=unknown-secret "
                                       "https://private.invalid/path?api_key=unknown-secret")
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path)
    assert failure.value.code == "provider_unavailable"
    assert json.loads((tmp_path / "invocation.json").read_text())["diagnostic"] == {
        "exception_class": "AttributeError", "category": "configuration"}
    assert len(transport["requests"]) == 1
    assert all("unknown-secret" not in path.read_text() for path in tmp_path.iterdir())


def test_api_message_is_bounded_and_unknown_status_is_not_copied(tmp_path, transport):
    transport["error"] = errors.ClientError(500, {"error": {"status": "synthetic-unit-test-key",
        "message": "Bounded diagnostic " + "x" * 3000}})
    with pytest.raises(ProviderFailure):
        GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path)
    diagnostic = json.loads((tmp_path / "invocation.json").read_text())["diagnostic"]
    assert len(diagnostic["api_message"]) == 1200 and "api_status" not in diagnostic
    assert diagnostic["http_status"] == 500
    assert len(transport["requests"]) == 1


def test_rpc_bad_request_details_are_allowlisted_redacted_and_carried_to_receipt(tmp_path, transport, caplog):
    transport["error"] = errors.ClientError(400, {"error": {"status": "INVALID_ARGUMENT",
        "message": "Request contains an invalid argument.", "details": [
            {"@type": "type.googleapis.com/google.rpc.BadRequest", "fieldViolations": [
                {"field": "generation_config.response_json_schema", "description": "Unsupported schema keyword."},
                {"field": "contents[0].parts[0]", "description":
                    "Rejected api_key=unknown-private-key https://private.invalid/?key=unknown-url-key synthetic-unit-test-key"},
                {"field": "https://private.invalid/?key=unknown-url-key", "description": {"secret": "nested-private-key"}},
                {"field": "contents[1]", "description": 'headers={"Authorization":"Bearer unknown-header-key"}'}],
             "metadata": {"Authorization": "Bearer metadata-private-key"}},
            {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "INVALID_ARGUMENT",
             "domain": "generativelanguage.googleapis.com", "metadata": {"api_key": "metadata-private-key"}},
            {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": {"headers": "nested-private-key"},
             "domain": "https://private.invalid/?key=unknown-url-key", "metadata": {"secret": "unknown-secret"}},
            {"@type": "type.googleapis.com/unknown.PrivateData", "headers": {"Authorization": "Bearer unknown-secret"}}
        ]}})
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path)
    # The diagnostic schema field is informative, but the generic API message
    # still receives the stable request-rejected classification without guesses.
    assert failure.value.code in {"request_rejected", "invalid_schema"}
    diagnostic = json.loads((tmp_path / "invocation.json").read_text())["diagnostic"]
    assert diagnostic["rpc_details"] == [
        {"type": "google.rpc.BadRequest", "field_violations": [
            {"field": "generation_config.response_json_schema", "description": "Unsupported schema keyword."},
            {"field": "contents[0].parts[0]", "description": "Rejected credential=[REDACTED] [REDACTED_URL] [REDACTED]"},
            {"field": "contents[1]", "description": "[REDACTED_HEADER_DIAGNOSTIC]"}]},
        {"type": "google.rpc.ErrorInfo", "reason": "INVALID_ARGUMENT", "domain": "generativelanguage.googleapis.com"}]
    assert len(transport["requests"]) == 1
    for secret in ("unknown-private-key", "unknown-url-key", "synthetic-unit-test-key", "nested-private-key",
                   "unknown-header-key", "metadata-private-key", "unknown-secret", "private.invalid"):
        assert secret not in caplog.text
        assert all(secret not in path.read_text() for path in tmp_path.iterdir())


def test_generic_http_400_is_fatal_request_rejection_and_pauses_provider(tmp_path, transport):
    from guide2build.engine.runtime import FATAL_PROVIDER_CODES, PAUSE_PROVIDER_CODES

    transport["error"] = errors.ClientError(400, {"error": {"status": "INVALID_ARGUMENT",
        "message": "Request contains an invalid argument."}})
    with pytest.raises(ProviderFailure) as failure:
        GoogleAdkProvider().call("Synthetic task", [], {"type": "object"}, tmp_path)
    assert failure.value.code == "request_rejected"
    assert failure.value.code in FATAL_PROVIDER_CODES and failure.value.code in PAUSE_PROVIDER_CODES
    assert len(transport["requests"]) == 1


def test_rpc_detail_counts_strings_and_symbolic_identifiers_are_bounded(tmp_path, transport):
    from guide2build.engine.provider import safe_provider_diagnostic

    error = errors.ClientError(400, {"error": {"message": "Invalid argument", "details": [
        {"@type": "google.rpc.BadRequest", "fieldViolations": [
            {"field": f"contents[{index}]", "description": "x" * 5000} for index in range(50)]},
        {"@type": "google.rpc.ErrorInfo", "reason": "BAD_REASON" + "X" * 100, "domain": "x" * 500},
        {"@type": "google.rpc.ErrorInfo", "reason": "INVALID_ARGUMENT", "domain": "googleapis.com"}]}})
    diagnostic = safe_provider_diagnostic(error)
    violations = diagnostic["rpc_details"][0]["field_violations"]
    assert len(violations) == 20 and all(len(value["description"]) == 600 for value in violations)
    assert diagnostic["rpc_details"][1] == {"type": "google.rpc.ErrorInfo", "reason": "INVALID_ARGUMENT",
                                            "domain": "googleapis.com"}
    assert len(diagnostic["rpc_details"]) == 2


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
