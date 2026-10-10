"""Offline Gradium client and CLI checks; every request is served by httpx.MockTransport."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest

from guide2build.voice.gradium import GradiumClient, GradiumError, resolve_api_key

KEY = "gsk_synthetic-not-a-credential"


def client_for(handler):
    return GradiumClient(api_key=KEY, transport=httpx.MockTransport(handler))


def test_tts_sends_documented_request_and_returns_audio():
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, content=b"RIFF....WAVE", headers={"content-type": "audio/wav"})

    audio = client_for(handler).tts("Place the red brick.", "YTpq7expH9539ERJ")
    request = seen["request"]
    assert audio == b"RIFF....WAVE"
    assert request.method == "POST" and request.url.path == "/api/post/speech/tts"
    assert request.headers["x-api-key"] == KEY
    assert json.loads(request.content) == {"text": "Place the red brick.", "voice_id": "YTpq7expH9539ERJ",
                                           "output_format": "wav", "only_audio": True}


def test_stt_joins_ndjson_text_segments():
    seen = {}

    def handler(request):
        seen["request"] = request
        lines = [{"type": "ready"}, {"type": "text", "text": "attach the"}, {"type": "text", "text": "wing"},
                 {"type": "end_text"}]
        return httpx.Response(200, text="\n".join(json.dumps(line) for line in lines),
                              headers={"content-type": "application/x-ndjson"})

    assert client_for(handler).stt(b"RIFFdata", language="en") == "attach the wing"
    request = seen["request"]
    assert request.url.path == "/api/post/speech/asr"
    assert json.loads(request.url.params["json_config"]) == {"language": "en"}
    assert request.headers["content-type"] == "audio/wav" and request.content == b"RIFFdata"


def test_stt_error_message_is_reported_and_redacted():
    def handler(request):
        return httpx.Response(200, text=json.dumps({"type": "error", "message": f"bad {KEY}"}))

    with pytest.raises(GradiumError) as caught:
        client_for(handler).stt(b"RIFFdata")
    assert caught.value.code == "provider_unavailable" and KEY not in str(caught.value)


@pytest.mark.parametrize("status,code", [(401, "authentication_required"), (403, "authentication_required"),
                                         (429, "quota_exceeded"), (422, "invalid_input"),
                                         (500, "provider_unavailable")])
def test_http_errors_map_to_fixed_codes_without_key(status, code):
    def handler(request):
        return httpx.Response(status, text=f"echo {KEY}")

    with pytest.raises(GradiumError) as caught:
        client_for(handler).credits()
    assert caught.value.code == code and KEY not in str(caught.value)


def test_input_limits_reject_before_any_request():
    def handler(request):
        raise AssertionError("no request expected")

    client = client_for(handler)
    for call in (lambda: client.tts("", "voice"), lambda: client.tts("x" * 5001, "voice"),
                 lambda: client.tts("hi", "voice", output_format="mp3"), lambda: client.stt(b""),
                 lambda: client.stt(b"x", content_type="text/plain")):
        with pytest.raises(GradiumError) as caught:
            call()
        assert caught.value.code == "invalid_input"


def test_missing_key_is_authentication_required(monkeypatch):
    monkeypatch.delenv("GRADIUM_API_KEY", raising=False)
    monkeypatch.delenv("GRADIUM", raising=False)
    with pytest.raises(GradiumError) as caught:
        GradiumClient()
    assert caught.value.code == "authentication_required"


def test_key_resolution_prefers_gradium_api_key():
    assert resolve_api_key({"GRADIUM_API_KEY": "a", "GRADIUM": "b"}) == "a"
    assert resolve_api_key({"GRADIUM": " b "}) == "b"
    assert resolve_api_key({}) == ""


def test_voices_and_credits_parse_json():
    def handler(request):
        if request.url.path == "/api/voices/":
            assert request.url.params["include_catalog"] == "true"
            return httpx.Response(200, json=[{"uid": "v1", "name": "Emma"}])
        return httpx.Response(200, json={"remaining_credits": 10, "allocated_credits": 20})

    client = client_for(handler)
    assert client.voices() == [{"uid": "v1", "name": "Emma"}]
    assert client.credits()["remaining_credits"] == 10


@pytest.fixture
def cli(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "tools"))
    spec = importlib.util.spec_from_file_location("gradium_cli_under_test", root / "tools/gradium.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "load_local_environment", lambda root: None)
    return module


def test_cli_tts_writes_audio_and_keyless_receipt(cli, tmp_path):
    def factory():
        return client_for(lambda request: httpx.Response(200, content=b"RIFFaudio",
                                                         headers={"content-type": "audio/wav"}))

    args = SimpleNamespace(command="tts", data_dir=tmp_path, text="Hello", voice_id="v1", format="wav", out=None)
    result = cli.run(args, client_factory=factory)
    assert result["status"] == "completed" and Path(result["output"]).read_bytes() == b"RIFFaudio"
    receipt = Path(result["receipt"]).read_text()
    assert KEY not in receipt and json.loads(receipt)["output_bytes"] == 9


def test_cli_failed_stt_still_writes_receipt(cli, tmp_path):
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"RIFFaudio")

    def factory():
        return client_for(lambda request: httpx.Response(429, text="slow down"))

    args = SimpleNamespace(command="stt", data_dir=tmp_path, audio=audio, language="en", content_type=None)
    with pytest.raises(GradiumError):
        cli.run(args, client_factory=factory)
    receipts = list((tmp_path / "gradium").glob("stt-*.json"))
    assert len(receipts) == 1 and json.loads(receipts[0].read_text())["code"] == "quota_exceeded"
