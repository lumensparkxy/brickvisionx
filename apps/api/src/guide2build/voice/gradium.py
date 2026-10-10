"""Bounded Gradium REST client for text-to-speech and speech-to-text. No retries or fallback."""
from __future__ import annotations

import json
import os

import httpx

DEFAULT_BASE_URL = "https://api.gradium.ai/api"
DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_TTS_CHARACTERS = 5_000
MAX_STT_AUDIO_BYTES = 25_000_000
MAX_RESPONSE_BYTES = 50_000_000
OUTPUT_FORMATS = {"wav", "pcm", "opus", "pcm_8000", "pcm_16000", "pcm_22050", "pcm_24000", "pcm_44100",
                  "pcm_48000", "ulaw_8000", "mulaw_8000", "alaw_8000"}
AUDIO_CONTENT_TYPES = {"audio/wav", "audio/pcm", "audio/ogg", "audio/opus"}

_MESSAGES = {
    "authentication_required": "Configure a valid backend GRADIUM_API_KEY for the Gradium API.",
    "quota_exceeded": "Gradium credits or rate limits were exhausted; the request was not retried.",
    "invalid_input": "Gradium rejected the request input.",
    "invalid_output": "Gradium returned a response that could not be parsed.",
    "provider_unavailable": "The Gradium request failed; it was not retried.",
}


class GradiumError(RuntimeError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or _MESSAGES[code])


def resolve_api_key(environ=None) -> str:
    source = os.environ if environ is None else environ
    return (source.get("GRADIUM_API_KEY") or source.get("GRADIUM") or "").strip()


class GradiumClient:
    def __init__(self, api_key: str | None = None, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS, transport: httpx.BaseTransport | None = None):
        key = (api_key if api_key is not None else resolve_api_key()).strip()
        if not key:
            raise GradiumError("authentication_required")
        if not base_url.startswith("https://") and transport is None:
            raise ValueError("Gradium base URL must use HTTPS")
        self._key = key
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
                                    headers={"x-api-key": key}, follow_redirects=False)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def credits(self) -> dict:
        return self._json(self._request("GET", "/usages/credits"))

    def websocket_token(self) -> dict:
        """Single-use token so a browser can open one Gradium WebSocket without the API key."""
        value = self._json(self._request("GET", "/api-keys/token"))
        if not isinstance(value, dict) or not isinstance(value.get("token"), str) or not value["token"]:
            raise GradiumError("invalid_output")
        return {"token": value["token"], "expires_at": value.get("expires_at")}

    def voices(self, include_catalog: bool = True, limit: int = 100, skip: int = 0) -> list:
        params = {"include_catalog": str(include_catalog).lower(), "limit": limit, "skip": skip}
        value = self._json(self._request("GET", "/voices/", params=params))
        if isinstance(value, dict):
            value = value.get("voices", value.get("items", value))
        if not isinstance(value, list):
            raise GradiumError("invalid_output")
        return value

    def tts(self, text: str, voice_id: str, output_format: str = "wav", model_name: str | None = None) -> bytes:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TTS_CHARACTERS:
            raise GradiumError("invalid_input", f"Text must be 1-{MAX_TTS_CHARACTERS} characters.")
        if not isinstance(voice_id, str) or not voice_id.strip():
            raise GradiumError("invalid_input", "A Gradium voice_id is required.")
        if output_format not in OUTPUT_FORMATS:
            raise GradiumError("invalid_input", f"Output format must be one of {sorted(OUTPUT_FORMATS)}.")
        body = {"text": text, "voice_id": voice_id, "output_format": output_format, "only_audio": True}
        if model_name:
            body["model_name"] = model_name
        response = self._request("POST", "/post/speech/tts", json=body)
        if response.headers.get("content-type", "").startswith("application/json"):
            raise GradiumError("invalid_output", "Gradium returned JSON instead of audio.")
        if not response.content:
            raise GradiumError("invalid_output", "Gradium returned empty audio.")
        return response.content

    def stt(self, audio: bytes, content_type: str = "audio/wav", language: str = "en") -> str:
        if not isinstance(audio, (bytes, bytearray)) or not audio or len(audio) > MAX_STT_AUDIO_BYTES:
            raise GradiumError("invalid_input", f"Audio must be 1-{MAX_STT_AUDIO_BYTES} bytes.")
        if content_type not in AUDIO_CONTENT_TYPES:
            raise GradiumError("invalid_input", f"Content type must be one of {sorted(AUDIO_CONTENT_TYPES)}.")
        response = self._request("POST", "/post/speech/asr", content=bytes(audio),
                                 params={"json_config": json.dumps({"language": language})},
                                 headers={"Content-Type": content_type})
        segments = []
        for line in response.text.splitlines():
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                raise GradiumError("invalid_output") from None
            if not isinstance(message, dict):
                raise GradiumError("invalid_output")
            if message.get("type") == "error":
                raise GradiumError("provider_unavailable",
                                   self._redact(f"Gradium transcription error: {message.get('message', '')}"))
            if message.get("type") == "text" and isinstance(message.get("text"), str):
                segments.append(message["text"].strip())
        return " ".join(segment for segment in segments if segment)

    def _request(self, method, path, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException:
            raise GradiumError("provider_unavailable", "The Gradium request timed out; it was not retried.") from None
        except httpx.HTTPError:
            raise GradiumError("provider_unavailable") from None
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise GradiumError("invalid_output", "Gradium response exceeded its size limit.")
        status = response.status_code
        if status < 400:
            return response
        if status in (401, 403):
            code = "authentication_required"
        elif status in (402, 429):
            code = "quota_exceeded"
        elif status in (400, 404, 413, 415, 422):
            code = "invalid_input"
        else:
            code = "provider_unavailable"
        detail = response.text[:300].strip()
        message = _MESSAGES[code] + (f" HTTP {status}: {detail}" if detail else f" HTTP {status}.")
        raise GradiumError(code, self._redact(message))

    def _json(self, response: httpx.Response):
        try:
            return response.json()
        except ValueError:
            raise GradiumError("invalid_output") from None

    def _redact(self, text: str) -> str:
        return text.replace(self._key, "[REDACTED]")
