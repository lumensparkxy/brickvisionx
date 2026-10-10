# BrickVisionX

Hackathon starter migrated from the current local Guide2Build code. Codex remains the development tool; Entire records development sessions. The reconstruction engine uses **Google ADK and the Gemini Developer API**, with explicit commands and bounded requests.

The viewer loads a labelled PDF-assisted candidate. The one-page ADK smoke proves the new provider integration; it does not prove complete automatic reconstruction or assembly accuracy.

## Start locally

```bash
uv sync --extra dev --frozen
npm ci
uv run python tools/doctor.py
uv run python tools/dev.py
```

Open http://127.0.0.1:5173 (API health: http://127.0.0.1:8000/api/v1/health). Choose **30669 → Alternate aeroplane — booklet 02 → Open tutorial**. Navigation, source panels, Replay and camera controls use the retained demo. Starting the app does not call Gemini.

On a fresh clone, run `uv run python tools/prepare_reference.py` once to download the official booklet and individual parts and create the labelled authored candidate. The migrated local checkout already has the verified assets. Downloads and generated data stay in ignored `var/`.

## Configure and test ADK

Copy `.env.example` to `.env` and enter `GOOGLE_API_KEY` locally. Keep `GOOGLE_GENAI_USE_VERTEXAI=FALSE`; the key is backend-only. Exported values take precedence. Never put the key in chat, a `VITE_*` variable, committed files, or job configuration. Obtain a key through [Google AI Studio](https://aistudio.google.com/app/apikey).

```bash
uv run python tools/adk_smoke.py
```

This explicitly sends verified zero-based page **1** of 30669/alt-02 through ADK and validates the engine's page-index schema. Default model: `gemini-3.8-flash`; thinking: `medium`; deadline: 120 seconds. Its durable experiment permits at most three requests including failed/interrupted attempts; a successful repeat reuses the retained response. Evidence lives under `var/adk-smoke/`.

The UI's existing conversion endpoint remains disabled for automatic requests. Full reconstruction is an explicit local engine experiment, separate from this starter:

```bash
uv run python tools/engine.py enqueue --set 30669 --guide alt-02 --thinking-level medium --max-model-calls 3 --revision adk-starter-01
uv run python tools/engine.py step JOB_ID
```

New jobs freeze model, thinking level, timeout and request budget. The default three calls may stop during booklet indexing; increase the ceiling explicitly only for a separately authorized full experiment. No application Codex inference or automatic provider fallback remains.

## Gradium voice (optional)

Backend-only [Gradium](https://docs.gradium.ai/) text-to-speech and speech-to-text client in `apps/api/src/guide2build/voice/gradium.py`. Set `GRADIUM_API_KEY` (or `GRADIUM`) in ignored `.env`; `tools/dev.py` strips both from the web process. Nothing calls Gradium on startup or in CI.

```bash
uv run python tools/gradium.py credits                       # free
uv run python tools/gradium.py voices                        # free; --custom-only hides catalog voices
uv run python tools/gradium.py tts --text "Attach the wing." --voice-id YTpq7expH9539ERJ   # spends credits
uv run python tools/gradium.py stt --audio var/gradium/tts-XXXX.wav --language en         # spends credits
```

Audio and keyless JSON receipts go to `var/gradium/`. Requests are not retried and have no provider fallback.

**Live voice chat (landing page).** The microphone button in the hero starts a conversation: browser mic → Gradium STT WebSocket (`model_name: default`, 24 kHz PCM, semantic-VAD turn end + flush) → `POST /api/v1/voice/reply` (Gemini `gemini-3.8-flash`, low thinking, short spoken answers, no tools) → Gradium TTS WebSocket (`model_name: default`, voice Emma `YTpq7expH9539ERJ`, `pcm_24000`) → speakers. The browser never sees the Gradium key; `POST /api/v1/voice/token` mints a single-use token per WebSocket. Replies are capped per API process by `GUIDE2BUILD_VOICE_MAX_REPLIES` (default 60). The microphone is only open while the button is on; the mute button next to it disables the mic track and sends silence without ending the session, so a reply already thinking or speaking finishes and typed commands are still answered aloud. Hidden in public/preview modes.

**Voice navigation.** Spoken or typed commands (hero, booklet dialog and a collapsible dock in the viewer) can move between screens ("find set 60400", "open the plane tutorial", "close the list", "go home", "how it works"), move through tutorial steps ("next step", "go to step 3", "replay", "play the full build") and press any visible, enabled button, tab or link ("prepare booklet", "zoom in", "review candidate"). The browser sends Gemini the current screen plus up to 80 on-screen controls (`c1`…`c80`, labels only; voice controls excluded; only the open dialog when one is modal). The server refuses ids that were not listed and step actions off the tutorial screen; the browser re-checks the control is still present and enabled before clicking. Clicks happen immediately, without confirmation, including buttons that start preparation or automatic conversion.

**Navigation by voice or typed command.** Gemini returns `{say, action}` (JSON schema). Screen actions: `find_set`, `open_tutorial`, `close_booklet`, `go_home`, `how_it_works`. Tutorial actions: `next_step`, `previous_step`, `go_to_step` (printed main-step number), `replay_step`, `play_build`. The server rejects sets/guides outside `config/sets.json`, tutorial actions off the tutorial screen and step numbers that do not exist; `open_tutorial` without a loadable scene falls back to `find_set` with an honest reply. Voice stays on across screens; the helper is in the hero, the booklet dialog and the viewer (a collapsed mic button until opened). Offline browser check: `tests/e2e/voice-navigation.spec.ts` (reply endpoint stubbed, synthetic scene).

## Verify

```bash
uv run python tools/check.py
npm run test:e2e -- --project=software
```

Tests are offline with synthetic provider responses; CI does not call paid models. [Migration evidence and current status](docs/migration/VALIDATION.md) distinguishes software checks, live ADK evidence and assembly accuracy. [Source snapshot](docs/migration/source-snapshot.json) records copied files and hashes.

## Provenance and limits

The source repository is untouched. This repository retains its own Git history, `origin` and Entire settings. Source commit and local modifications are recorded in the snapshot. Historical execution reports are retained as provenance; the ADK instructions in this README and `docs/execution/ENGINE.md` govern new runs.

Only the official booklet supplies assembly evidence. Individual LDraw geometry and notices are preserved. Authored/PDF-assisted candidates, automatic proposals, agent review, human review and physical-build proof remain distinct. No deployment or GitHub push is part of this migration. The internal Python package remains `guide2build`.
