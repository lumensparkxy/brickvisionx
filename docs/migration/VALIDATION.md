# BrickVisionX migration validation

Verified on 2026-10-10 in `/Users/admin/learn_python/brickvisionx`, branch `codex/migrate-google-adk`.

**Current result:** the local application and offline ADK integration checks pass. The live one-page proof is waiting for a locally configured `GOOGLE_API_KEY`. The explicit smoke command stopped with `authentication_required` before making a model request. Migration completion requires a real validated response; it is not claimed yet.

## Snapshot and repository

- Source commit: `df62afc34f31a06516ecde1ce5def10061653040` on `codex/fix-alpha-model-loading`, including the captured local modifications and relevant untracked source files.
- Copied 394 maintained files after hashing; source `.git`, secrets, installations, build output, caches and runtime databases excluded. [Snapshot ledger](source-snapshot.json) records paths, sizes, hashes and local status. Independent review found all source hashes unchanged.
- Destination base commit: `73272a9456f4e30ab65381db98a638e7f97e640f`. Its existing files, Git history and `origin` (`git@github.com:lumensparkxy/brickvisionx.git`) remain preserved.
- Destination Entire settings and agent hooks remain present. `entire status --json` reports an active Codex session on the migration branch. Local checkpoint commit verification is recorded below after committing; nothing is pushed.
- Only 152 selected asset files (4,303,077 bytes) were reused. Hash validation passed. Official PDF SHA-256: `6cb3e669fef3662dfd498cba0e631f1d9ec082c2bf8c0fb0a0febe303680a6b6`. All eight rendered pages, receipt, labelled candidate and required individual part geometry were retained. Geometry dependency closure passes with 134 reachable files and one material file. This checks asset availability, not assembly correctness.
- Selected assets and `.env` are ignored. Target job databases started fresh. Source runtime databases were not imported.

## Runtime implementation

An isolated `agents-cli` ADK prototype scaffold in `/private/tmp/brickvisionx-adk-reference` informed the embedded adapter; it is not a deployment artifact. The backend retains `guide2build`, HTTP contracts, SQLite orchestration and deterministic checks. The UI retains its current Guide2Build product presentation.

The executable application Codex inference path is removed. Each `GoogleAdkProvider.call` runs an actual ADK `LlmAgent` and `Runner`, an isolated memory session, inline images and structured JSON; the original engine schema validates the result. Tools, transfers, SDK replay, hidden retries and fallback are disabled. Credentials go only to the fixed Gemini Developer API client.

New jobs freeze provider, `gemini-3.8-flash`, `medium` thinking, a 120-second deadline and a three-request ceiling. The durable budget includes failed/interrupted attempts and is enforced through resume, cancellation and correction lineage. Exported environment values take precedence over the ignored local `.env`. Evidence contains hashes, schema, timing, reported usage and sanitized failures. The frontend launcher strips exported provider credentials from the npm child environment.

The lockfiles resolve Google ADK 2.11.0 and google-genai 2.29.0. Official references: [ADK structured output](https://adk.dev/agents/llm-agents/), [Developer API setup](https://adk.dev/get-started/python/), [Gemini model](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash).

## Software verification

| Check | Result | Local evidence |
| --- | --- | --- |
| Imported backend baseline before provider replacement | 1,405 passed, 3 skipped | `var/evidence/migration/baseline-backend.log` |
| Imported frontend baseline | 54 tests passed; build passed | `var/evidence/migration/baseline-frontend.log` |
| Full migrated backend suite | 1,458 passed | `var/evidence/migration/final-check.log` |
| Original generated schemas and Ruff | Passed | `var/evidence/migration/final-check.log` |
| Frontend tests, typecheck and production build | 54 tests passed; checks passed | `var/evidence/migration/final-check.log`, `typecheck.log` |
| Final provider checks, including real ADK Runner with intercepted transport | 32 tests passed | `tests/backend/test_engine_provider.py` |
| Software browser suite | 20 passed | `var/evidence/migration/software-browser.log` |
| Selected real-demo playback/phone and placement browser checks | 2 passed | `var/evidence/migration/reference-browser.log` |
| Independent budget, lineage, provider and smoke review | 75 focused tests passed; no blocking finding | Independent reviewer report in development session |
| Doctor | Installed modules and manifests pass | `var/evidence/migration/doctor.log` |

The final provider check includes an additional lease-loss cancellation regression added after the full suite; all 32 provider tests pass. The smoke suite uses synthetic responses for its six offline cases. Ordinary startup and CI did not initiate inference.

Third-party deprecation warnings remain in FastAPI/Starlette, OpenTelemetry and ADK's compatibility handling of `GOOGLE_GENAI_USE_VERTEXAI`. Vite reports an existing viewer chunk above 500 kB. These warnings did not fail checks.

## Local application and viewer

Local API health and demo routes respond at `http://127.0.0.1:8000`; the viewer runs at `http://127.0.0.1:5173`. Booklet selection, the retained 30669/alt-02 demo, navigation, source crops, Replay and a 390×844 phone viewport were checked. Actual Codex in-app browser interaction also confirmed the final instruction, Replay and the official page crop; its captured warning/error list was empty.

Screenshots: `var/evidence/migration/iab-demo.png`, `iab-source.png`, and `var/evidence/full-build/phone.png`. The displayed candidate retains **PDF-assisted · needs review**. It is not an ADK-generated assembly.

## Live one-page smoke

Run explicitly after saving the key locally:

```bash
uv run python tools/adk_smoke.py
```

The default verified instruction page is zero-based page 1 (printed page 2), image SHA-256 `62c47a988acadae6d63943d74ecd8febb8250f89fab30a71682dcc065ee96a5f`. Inspection of this official image shows main steps 1 and 2; the step-1 arrow attaches the white hull pieces, and step 2 adds the white wing pieces. This observation is agent inspection, not human review.

Each command makes at most one request. Its durable experiment permits at most three lifetime reservations including failures/interruption; concurrent invocations are locked out, and a completed repeat reuses the saved response. Evidence is retained under `var/adk-smoke/<experiment>/` for comparison with the official image. Current command status is in `var/evidence/migration/live-smoke-status.json`: missing credentials, zero live requests made.

## Remaining boundaries

The real one-page ADK response and source comparison remain pending local credentials. Full automatic reconstruction, accuracy improvement, complete geometry/connector acceptance, human review and physical build were not run. Deployment, publication and GitHub push are deferred. Historical source execution reports describe earlier Guide2Build work and are not new BrickVisionX runtime or release evidence.
