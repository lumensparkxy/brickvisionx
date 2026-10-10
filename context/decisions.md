# Decisions

- 2026-10-10: Gradium via plain httpx REST, not the `gradium` SDK (async/websocket; avoids a new dependency).
- 2026-10-10: Scope = TTS + STT + credits + voices, CLI only. No UI, no API endpoint, no websocket streaming, no voice cloning.
- 2026-10-10: No retries or fallback; fixed error codes authentication_required / quota_exceeded / invalid_input / invalid_output / provider_unavailable; the key is redacted from messages.
- 2026-10-10: Limits: TTS text up to 5,000 chars, STT audio up to 25 MB, response up to 50 MB.
- 2026-10-10: voices() defaults include_catalog=true (the API default false returned 0 voices).
- 2026-10-10: Voice chat architecture: browser talks directly to Gradium WS with per-socket single-use tokens from the backend (per Gradium browser guide); the LLM reply goes through the backend (Gemini; Gradium has no LLM). Rejected: Gradbot (separate Python server, needs an OpenAI-compatible LLM) and a backend WS relay (more code, added latency).
- 2026-10-10: Models: Gradium STT `default`, TTS `default` (stable; `gradium-tts-beta` alias skipped). Voice Emma YTpq7expH9539ERJ (friendly/conversational tags). Gemini gemini-3.8-flash, thinking low, max 400 output tokens, 20 s timeout, 1 attempt.
- 2026-10-10: Single AudioContext at 24 kHz for capture (STT `pcm`) and playback (TTS `pcm_24000`). Turn end = 3 consecutive VAD steps with 1 s-horizon inactivity > 0.6, then flush.
- 2026-10-10: Voice UI hidden in publicMode/previewMode (the cloud API has no voice routes).
- 2026-10-10: User asked to keep the Gradium key in `.env.example` and to copy it to `.env` (not move it).
- 2026-10-10: Navigation = Gemini returns JSON {say, action}; named actions for screens/steps (find_set, open_tutorial, close_booklet, go_home, how_it_works, next/previous/go_to/replay_step, play_build). Server validates against catalogue + screen; `open_tutorial` without a loadable scene falls back to `find_set` with honest text.
- 2026-10-10: "All page navigable" (user): generic `click {control_id}` over controls listed by the browser (`apps/web/src/voice/controls.ts`), chosen over one named action per button (rejected: needs code per future button). User chose NO confirmation, even for prepare/automatic conversion/save/cancel.
- 2026-10-10: Controls: button, [role=tab], summary, a[href]; excluded disabled/inert/hidden/.voice-chat; scoped to open `dialog`; max 80; duplicate labels get `data-voice-scope` suffix (guide rows, preparation section). Form fields and selects excluded (find_set/go_to_step cover them).
- 2026-10-10: Viewer voice dock is collapsible (starts as a 56px mic button, bottom 128px) because the open card covered Next and review controls. Rejected: in-flow dock (workspace is a fixed 100dvh grid).
- 2026-10-10: Mute = `VoiceSession.setMuted()`: track.enabled=false + silence to STT; STT/TTS sockets stay open, thinking/speaking continue, typed input still spoken. Muting mid-utterance lets VAD end the turn (partial is answered, not dropped). Stop resets mute. Rejected: closing the STT socket (would need a new token + setup on unmute).
- 2026-10-10: Control-collection tested in Playwright (real browser), not Vitest: no jsdom/happy-dom installed; did not add a dependency.
