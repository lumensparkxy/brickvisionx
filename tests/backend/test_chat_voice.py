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
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GRADIUM_API_KEY", "BRICKVISIONX_CHAT_MODEL", "BRICKVISIONX_CHAT_MAX_REPLIES"):
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


def ask(client, monkeypatch, actions, app=None, reply="Sure!"):
    fake_model(monkeypatch, json.dumps({"reply": reply, "actions": actions}))
    body = {"messages": [{"role": "user", "text": "do it"}], "viewer": VIEWER}
    if app is not None:
        body["app"] = app
    response = client.post("/api/v1/chat", json=body)
    assert response.status_code == 200
    return response.json()


def test_viewer_actions_are_refused_outside_a_tutorial(client, monkeypatch):
    result = ask(client, monkeypatch, [{"type": "go_to_step", "step": 3}], app={"screen": "landing"})
    assert result["actions"] == []
    assert "Open a 3D tutorial first" in result["reply"]


def test_viewer_actions_pass_on_the_tutorial_screen_and_by_default(client, monkeypatch):
    actions = [{"type": "go_to_step", "step": 3}, {"type": "rotate", "direction": "left", "degrees": 90}]
    assert ask(client, monkeypatch, actions, app={"screen": "tutorial"})["actions"] == actions
    assert ask(client, monkeypatch, actions)["actions"] == actions


def test_sets_outside_the_catalogue_are_refused(client, monkeypatch):
    result = ask(client, monkeypatch, [{"type": "open_tutorial", "set_number": "99999"}], app={"screen": "landing"})
    assert result["actions"] == []
    assert "catalogue" in result["reply"]


def test_open_tutorial_without_a_scene_falls_back_to_the_booklets(client, monkeypatch):
    # tmp_path has no reconstruction, so no tutorial can open: BrickBuddy must say so and show the booklets.
    result = ask(client, monkeypatch, [{"type": "open_tutorial", "set_number": "30669"}, {"type": "go_to_step", "step": 5}],
                 app={"screen": "landing"}, reply="Opening the plane!")
    assert result["actions"] == [{"type": "find_set", "set_number": "30669"}]
    assert "No 3D tutorial is ready" in result["reply"] and "Opening" not in result["reply"]


def test_open_tutorial_with_a_ready_scene_allows_following_viewer_actions(monkeypatch):
    app_state = chat.AppState(screen="landing")
    actions, refusal = chat.check_actions(
        [{"type": "open_tutorial", "set_number": "30669"}, {"type": "go_to_step", "step": 5}], app_state,
        ready_guide=lambda set_number, guide_id: "alt-02")
    assert refusal is None
    assert actions == [{"type": "open_tutorial", "set_number": "30669", "guide_id": "alt-02"}, {"type": "go_to_step", "step": 5}]


def test_close_booklet_only_applies_on_the_booklet_screen():
    assert chat.check_actions([{"type": "close_booklet"}], chat.AppState(screen="landing")) == ([], None)
    assert chat.check_actions([{"type": "close_booklet"}], chat.AppState(screen="booklet")) == ([{"type": "close_booklet"}], None)


def test_reply_budget_caps_paid_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "load_local_environment", lambda *args, **kwargs: None)
    monkeypatch.setenv("BRICKVISIONX_CHAT_MAX_REPLIES", "1")
    limited = TestClient(create_app(tmp_path))
    fake_model(monkeypatch, json.dumps({"reply": "ok", "actions": []}))
    assert limited.post("/api/v1/chat", json=ASK).status_code == 200
    second = limited.post("/api/v1/chat", json=ASK)
    assert second.status_code == 429
    assert second.json()["detail"]["code"] == "chat_budget_exhausted"


def test_requests_that_never_reach_the_model_do_not_use_the_budget(tmp_path, monkeypatch):
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(chat, "load_local_environment", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat, "_client", None)
    monkeypatch.setenv("BRICKVISIONX_CHAT_MAX_REPLIES", "1")
    limited = TestClient(create_app(tmp_path))
    for _ in range(3):  # no key: unavailable every time, never "limit reached"
        assert limited.post("/api/v1/chat", json=ASK).status_code == 503
    trailing = {"messages": [{"role": "user", "text": "hi"}, {"role": "assistant", "text": "hello"}], "viewer": VIEWER}
    fake_model(monkeypatch, json.dumps({"reply": "ok", "actions": []}))
    assert limited.post("/api/v1/chat", json=trailing).status_code == 422
    assert limited.post("/api/v1/chat", json=ASK).status_code == 200
    assert limited.post("/api/v1/chat", json=ASK).status_code == 429
