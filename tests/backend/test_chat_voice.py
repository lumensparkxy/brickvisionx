"""Provider-free behaviour of the BrickBuddy chat and voice-token routes. No network, no keys."""
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from guide2build import chat, voice
from guide2build.main import create_app

VIEWER = {"current_step": 1, "total_steps": 12, "steps": []}
ASK = {"messages": [{"role": "user", "text": "zoom in"}], "viewer": VIEWER}


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GRADIUM_API_KEY", "BRICKVISIONX_CHAT_MODEL"):
        monkeypatch.delenv(name, raising=False)
    # Never read a developer's real .env from a test.
    monkeypatch.setattr(chat, "load_local_environment", lambda *args, **kwargs: None)
    monkeypatch.setattr(voice, "load_local_environment", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat, "_client", None)
    return TestClient(create_app(tmp_path))


def fake_model(monkeypatch, text):
    async def generate_content(**kwargs):
        return SimpleNamespace(text=text)
    monkeypatch.setattr(chat, "_gemini", lambda: SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))))


def test_chat_without_key_is_unavailable(client):
    response = client.post("/api/v1/chat", json=ASK)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_unavailable"


def test_chat_rejects_a_trailing_assistant_turn(client):
    body = {"messages": [{"role": "user", "text": "hi"}, {"role": "assistant", "text": "hello"}], "viewer": VIEWER}
    response = client.post("/api/v1/chat", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"


def test_chat_returns_reply_and_only_object_actions(client, monkeypatch):
    fake_model(monkeypatch, json.dumps({"reply": "Zooming in!", "actions": [{"type": "zoom", "direction": "in"}, "junk"]}))
    response = client.post("/api/v1/chat", json=ASK)
    assert response.status_code == 200
    assert response.json()["reply"] == "Zooming in!"
    assert response.json()["actions"] == [{"type": "zoom", "direction": "in"}]


@pytest.mark.parametrize("text", [None, "", '{"reply": "cut off', "[1, 2]"])
def test_chat_unreadable_model_output_is_a_provider_failure(client, monkeypatch, text):
    fake_model(monkeypatch, text)
    response = client.post("/api/v1/chat", json=ASK)
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "chat_failed"
    assert "Unterminated" not in detail["message"] and "line 1" not in detail["message"]


def test_part_names_resolve_moved_stubs(tmp_path, monkeypatch):
    resources = {"parts/3023.dat": {"description": "~Moved to 3023b"}, "parts/3023b.dat": {"description": "Plate  1 x  2"},
                 "parts/9999.dat": {"description": "~Obsolete helper"}, "parts/3020.dat": {"description": "=Plate  2 x  4"}}
    (tmp_path / "public/ldraw").mkdir(parents=True)
    (tmp_path / "public/ldraw/provenance.json").write_text(json.dumps({"resources": resources}))
    monkeypatch.setenv("GUIDE2BUILD_DATA_DIR", str(tmp_path))
    names = chat._part_names("1 x White (part 3023) 1 x Red (part 9999) 1 x Yellow (part 3020) (part 4242)")
    assert names == {"3020": "Plate  2 x  4", "3023": "Plate  1 x  2"}


def test_voice_token_without_key_is_unavailable(client):
    response = client.post("/api/v1/voice/token")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "voice_unavailable"


@pytest.mark.parametrize("status,payload", [(401, {"error": "nope"}), (200, {"expires_at": "soon"})])
def test_voice_token_failures_do_not_echo_the_key(client, monkeypatch, status, payload):
    secret = "test-key-not-real"
    monkeypatch.setenv("GRADIUM_API_KEY", secret)
    seen = {}

    def handler(request):
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(status, json=payload)

    real = httpx.AsyncClient
    monkeypatch.setattr(voice.httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))
    response = client.post("/api/v1/voice/token")
    assert seen["key"] == secret
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "voice_failed"
    assert secret not in response.text


def test_voice_token_success_passes_token_and_voice(client, monkeypatch):
    monkeypatch.setenv("GRADIUM_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GRADIUM_VOICE_ID", "voice-123")
    real = httpx.AsyncClient
    monkeypatch.setattr(voice.httpx, "AsyncClient", lambda **kwargs: real(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"token": "t0k", "expires_at": "soon"})), **kwargs))
    assert client.post("/api/v1/voice/token").json() == {"token": "t0k", "voice_id": "voice-123", "expires_at": "soon"}
