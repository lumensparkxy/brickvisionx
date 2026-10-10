# Insights

- 2026-10-10: Gradium docs index is at https://docs.gradium.ai/llms.txt; the OpenAPI reference is embedded in the endpoint .md pages.
- 2026-10-10: GET /voices/ without include_catalog returns [] for this account (no custom voices).
- 2026-10-10: Gradium credit balance is free to query; 1 credit corresponds to a unit of generated audio (see the Credits guide).
- 2026-10-10: GET /api/api-keys/token -> {token (22 chars), expires_at ~60 s}; single use; WS URL wss://api.gradium.ai/api/speech/{asr|tts}?token=...
- 2026-10-10: STT WS messages: ready, text, end_text, step (vad horizons 0.5/1/2/3 s), flushed, end_of_stream, error. Client: setup, audio(base64), flush{flush_id}, end_of_stream.
- 2026-10-10: Gradium streamed WAV header has a placeholder length; read raw bytes after the `data` chunk.
- 2026-10-10: Gemini voice reply latency ~3.7 s (low thinking); this is the dominant turn latency.
- 2026-10-10: Playwright fake mic: --use-fake-device-for-media-stream --use-file-for-fake-audio-capture=WAV (loops; pad with silence). Browsers in var/ms-playwright (PLAYWRIGHT_BROWSERS_PATH).
- 2026-10-10: The repo's run path needs uv plus Node >= 22.12; neither is set up on this machine.
- 2026-10-10: Without a `click` action Gemini honestly refused ("tap the prepare booklet button"); fixed list of actions = refusals for every unlisted button.
- 2026-10-10: All 10 catalogue sets have tutorial_available=false locally; scene endpoint 409. Synthetic fixture route-mocking (tests/e2e/viewer.spec.ts pattern) is the only way to test in-tutorial UI.
- 2026-10-10: A fixed overlay dock intercepted clicks on viewer Next and "Advanced corrections" (Playwright "subtree intercepts pointer events"). Run the software e2e suite after any floating UI change.
- 2026-10-10: "Review candidate" button relabels to "Close review" when open; assert the "Review workspace" dialog instead.
- 2026-10-10: Programmatic element.click() after an await works for buttons/tabs/summary; popups from target=_blank links may be blocked.
