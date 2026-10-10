"""Gradium voice for BrickBuddy: mint one short-lived token per browser WebSocket.

The browser talks to Gradium speech-to-text and text-to-speech directly with this single-use
token; the API key stays on the backend. Neither the key nor the token is ever logged.
"""
from __future__ import annotations

import os

import httpx

from .core.environment import load_local_environment

DEFAULT_BASE_URL = "https://api.gradium.ai/api"
DEFAULT_VOICE_ID = "YTpq7expH9539ERJ"  # Emma, en-US


class VoiceUnavailable(Exception):
    pass


async def mint_token() -> dict:
    load_local_environment()
    api_key = (os.environ.get("GRADIUM_API_KEY") or "").strip()
    if not api_key:
        raise VoiceUnavailable("Voice needs a backend GRADIUM_API_KEY in .env.")
    base_url = (os.environ.get("GRADIUM_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{base_url}/api-keys/token", headers={"x-api-key": api_key})
    if response.status_code != 200:
        # Deliberately not raise_for_status(): keep the request (and its key header) out of tracebacks.
        raise RuntimeError(f"Gradium token request returned HTTP {response.status_code}")
    data = response.json()
    token = data.get("token") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("Gradium token response had no token")
    return {"token": token,
            "voice_id": (os.environ.get("GRADIUM_VOICE_ID") or DEFAULT_VOICE_ID).strip(),
            "expires_at": data.get("expires_at")}
