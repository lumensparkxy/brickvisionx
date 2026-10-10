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

## Verify

```bash
uv run python tools/check.py
npm run test:e2e -- --project=software
```

Tests are offline with synthetic provider responses; CI does not call paid models. [Migration evidence and current status](docs/migration/VALIDATION.md) distinguishes software checks, live ADK evidence and assembly accuracy. [Source snapshot](docs/migration/source-snapshot.json) records copied files and hashes.

## Provenance and limits

The source repository is untouched. This repository retains its own Git history, `origin` and Entire settings. Source commit and local modifications are recorded in the snapshot. Historical execution reports are retained as provenance; the ADK instructions in this README and `docs/execution/ENGINE.md` govern new runs.

Only the official booklet supplies assembly evidence. Individual LDraw geometry and notices are preserved. Authored/PDF-assisted candidates, automatic proposals, agent review, human review and physical-build proof remain distinct. No deployment or GitHub push is part of this migration. The internal Python package remains `guide2build`.
