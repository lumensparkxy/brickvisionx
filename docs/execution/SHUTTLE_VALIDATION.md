# Isolated Space Shuttle ADK experiment

This report tracks the fresh `31134 / booklet-01` experiment. Historical Shuttle
scenes and responses are excluded. The configured key is valid: a read-only
`models.get` lookup, a bounded text generation and a bounded official-image
generation succeeded. Both generation diagnostics are charged to this job.
The corrected schema transport now returns page indexes validated against the
original engine schema. The experiment subsequently paused on a Gemini service
deadline; it has no reconstructed candidate yet.

## Frozen scope and source

- Experiment: `var/experiments/adk-31134-booklet01-20261010/`.
- Job: `2573f70cc20e45329bce1656bddf64d9`.
- Revision: `adk-31134-booklet01-20261010-v1`.
- Google ADK, `gemini-3.8-flash`, medium thinking, 120 seconds, one worker.
- Exploration with findings, baseline proposals, incremental context, at most
  two proposal attempts per instruction, 300 total requests across resume.
- SDK retries, tools, provider fallback and publication remain disabled.
- Official PDF copied read-only from the source repository, 12,890,144 bytes,
  60 pages, SHA-256
  `156045d1052fd105d873093918d41239641e96e40484cb35fa0b010587339d66`.
- [Official source](https://www.lego.com/cdn/product-assets/product.bi.core.pdf/6457820.pdf).
- All 60 source images rendered in the private cache. No prior scenes,
  placements, model responses or checkpoints were copied. The seed contains
  134 verified individual geometry resources and their provenance.

## Current gates

Four original engine attempts are retained and charged; HTTP 400
`INVALID_ARGUMENT` exposed a generic service message without rejected-field
details. Those calls reported no usage, which differs from measured zero tokens.
Requests 5 and 6 validated text and image generation (1,414 reported tokens).
Request 7 validated the original `PageIndexV2` using transport conversion
`gemini-json-subset-v2` (4,030 tokens, 15.03 seconds). Full booklet indexing then
reached 17/60 page records: 15 validated outputs and two retained failed indexes.
The next page, PDF index 17, returned HTTP 504 `DEADLINE_EXCEEDED` after 119.75
seconds. The engine stopped with `provider_unavailable` / `provider_blocked` and
the provider pause remains set. It was not resumed after this infrastructure
blocker, in accordance with the approved policy.

The final ledger contains **24/300 requests**, including all failed attempts and
both diagnostics. Reported usage is **83,490 tokens** (63,776 prompt, 5,376 output,
14,338 thinking), with 318.96 seconds of aggregate model invocation time. Usage
is partial: 19 calls reported usage and five did not. No zero-token or cost claim
is made for unreported calls. Every attempted invocation retains its receipt;
SDK retries, tools and provider fallback remain disabled.

**Processed instructions: 0. Reconstructed instructions: 0. Snapshots: 0.**
The runtime instruction denominator remains unknown because full indexing did
not finish. First-four candidate inspection, rendering, quantity/identity/
attachment checks and complete reconstruction are blocked. There is no partial
3D candidate to deliver; the partial source indexes and all raw evidence remain
available for an explicit resume.

The transport omits unsupported constraints and variable array caps while
preserving exact bbox/vector arity. The original engine schema remains the strict
output validator, including every original cap and identifier pattern. For
example, pages 4 and 5 returned identifiers containing underscores and failed
the original hyphen-only identifier pattern. Their raw responses and failures
remain preserved; no edited response is accepted. The model, budget and source
bindings remain fixed.
Fatal failed calls now remain fatal on resume. Explicit retries allocate fresh
evidence slots and charge another request before execution; they preserve all
earlier inputs and failure receipts. Correction seeds authenticate completed
retry chains. Failure diagnostics include bounded sanitized API/RPC fields;
credentials, headers, arbitrary HTTP objects and transport URLs are excluded.

## Software and preservation evidence

The final backend suite passed all 1,533 collected tests after transport v2.
Focused recovery/metrics checks, frontend 54 tests, app typecheck, build, schema
drift and Ruff checks passed. Nine synthetic browser regressions passed for
playback, navigation, findings and phone layout. These are software results,
not official Shuttle assembly accuracy results.

The opt-in real-data suite ran against the existing read-only preview on desktop
1440×900 and phone 390×844. **Both tests failed the explicit candidate-availability
gate**, showing the selected `31134 · Space Shuttle / Official booklet 1 of 3`
and the preserved provider failure. Each browser captured zero page errors,
console errors/warnings, network errors or unsafe requests, with 11 local GETs.
Source images, 3D loading, early/final steps, callouts, Previous/Next, seeking,
Replay, full playback and reload remain unperformed because no candidate exists.
Screenshots were inspected. An initial sandbox Chromium launch failure is
retained separately; the subsequent authorized browser launch rendered correctly.
Without the environment variable, both tests skip and start no servers or
inference. Ordinary CI never initiates inference.

All 160 protected red aeroplane assets/configuration/candidate files remain
byte-identical. Logical revision/database rows in `var/guide2build.sqlite3` and
`var/publication.sqlite3` remain unchanged, and no normal engine database has
been created. The existing application stays on ports 5173 and 8000. The isolated
read-only preview runs at http://127.0.0.1:4176 and currently returns
`candidate_available=false` and HTTP 409 for its release. Browser selection
visibly shows the Shuttle and its blocked state without exposing another
candidate.

The original Shuttle PDF was hashed again and remains identical. Independent
source-only agent inspection found main instructions 1–48 and 19 distinct
numbered internal callouts under mains 14, 39, 40, 44, 45, 46 and 48. Unnumbered
subassembly/attachment events also require coverage. First-four quantities are
2, 2, 1, 2 (cumulative 2, 4, 5, 7); no internal numbered callouts appear in those
four pages. Main 48 spans PDF indexes 53–56 / printed pages 54–57 and builds two
copies before attachment. Source trays total 144 expected physical pieces; 2×
subassembly labels must not multiply already aggregated tray counts again.
These observations were not supplied to the engine and are not human approval
or an assembly-accuracy score. Current coverage is 0/48 main steps and 0/19
numbered callouts, with all additional unnumbered-event gates blocked.

Human review, physical build, deployment, publication and GitHub push are
unperformed. The demo remains PDF-assisted; no automatic Shuttle reconstruction
success is claimed.

Entire remains enabled on `codex/migrate-google-adk`, with Codex session
`01a12572-6c99-7c42-a24b-73bc4f51e05c`. Local implementation checkpoint
`f9a9dc6730cd5426bcb8800a845a26b5ff0e9fb5` has trailer
`Entire-Checkpoint: 01M4JWPFPAWJTKN49C3YP4E6ES`. It records the tested provider,
resume/evidence, metrics and opt-in browser implementation. No push was made.

## Exact commands

Run from `/Users/admin/learn_python/brickvisionx`.

```sh
DATA=var/experiments/adk-31134-booklet01-20261010/data
JOB=2573f70cc20e45329bce1656bddf64d9

# Normal application startup when needed; already running on 5173/8000.
# Startup does not initiate inference. Do not start a second copy on those ports.
.venv/bin/python tools/dev.py

# Read-only progress and measured provider usage.
.venv/bin/python tools/engine.py --data-dir "$DATA" status
.venv/bin/python tools/engine.py --data-dir "$DATA" report

# Resume only after the provider blocker has been addressed. Each explicitly
# retried call stays charged; no failed evidence is overwritten.
.venv/bin/python tools/engine.py --data-dir "$DATA" resume "$JOB" \
  --provider --retry-provider-calls
.venv/bin/python tools/engine.py --data-dir "$DATA" step "$JOB"

# After inspecting the first four printed main steps and their callouts:
.venv/bin/python tools/engine.py --data-dir "$DATA" run --job-id "$JOB" --workers 1

# Selected-candidate read-only preview; already running during this experiment.
.venv/bin/python tools/preview_engine.py "$JOB" --data-dir "$DATA" --port 4176

# Opt-in real-data browser suite. No servers or inference are started.
GUIDE2BUILD_SHUTTLE_PREVIEW_URL=http://127.0.0.1:4176 \
  npx playwright test --config playwright.shuttle.config.ts

# Protection check reads the original files and semantic database records.
.venv/bin/python var/experiments/adk-31134-booklet01-20261010/prepare_experiment.py --verify
```

Preparation and live-call evidence are under the ignored experiment directory:
`evidence/preparation.json`, `evidence/key-verification.json`,
`evidence/minimal-generation-diagnostic.json`, `evidence/image-generation-diagnostic.json`,
`evidence/call-metrics.json`, `evidence/step-001.log` through `step-005.log`, private `exploration/calls/` receipts,
`evidence/protection-verification.json`, browser logs/screenshots and backend logs.

Focused evidence includes `evidence/key-source-verification.json` (runtime key
matches the ignored local `.env`, with no exported override and no secret logged),
`evidence/index-output-findings.json`, `evidence/review/v2-success-review.json`,
`evidence/browser/blocked-browser-review.json`, and desktop/phone
`evidence/browser/{desktop,phone}/blocked-selection.png`.
Independent final checks are in `evidence/review/final-receipt-budget-review.json`
(24 authenticated, charged requests; 15 original-schema-valid page indexes),
`evidence/review/source-coverage-review.json`, and
`evidence/review/preservation-after-final-pause.json`. Final loopback health checks
returned HTTP 200 for 5173, the API health route on 8000 and the private preview
on 4176; no service was restarted.

Software verification commands (no inference):

```sh
.venv/bin/python -m pytest tests/backend
.venv/bin/python tools/export_schema.py --check
.venv/bin/ruff check apps/api/src/guide2build/engine tests/backend tools/engine.py
npm test
npm run typecheck
npm run build
npx playwright test --project=software tests/e2e/exploration-preview.spec.ts \
  tests/e2e/chunked-playback.spec.ts tests/e2e/viewer.spec.ts
```

Resume is explicit after service recovery. It keeps the same source, model,
120-second deadline and 300-request ceiling, preserves failed receipts, and
charges a fresh request. Full reconstruction remains incomplete until all
required main steps, callouts and attachment events are represented and inspected.

## User-executed run without a client deadline

The user subsequently requested an independent Terminal command with the
120-second client deadline removed. `enqueue --provider-timeout none` now freezes
an explicit null deadline in a fresh job and clears the SDK timeout/header as
well. Cancellation and lease checks remain active. The original blocked job
and its measured results above are unchanged. No new paid inference ran while
preparing this option; no no-deadline reconstruction result is claimed.

The new `--share-budget-with` option binds a fresh same-source exploration
revision to the original 300-request ceiling. Read-only preflight verified the
official source hash and 24 charged calls, with 276 remaining. Roots identified
by either job configuration or checkpoint are checked, including correction
descendants. Sibling calls and cancelled reservations continue to count. Model,
thinking level, booklet and ceiling must match; active or exhausted roots reject
new runtime revisions. Start, resume and observation commands are in
[SHUTTLE_TERMINAL.md](SHUTTLE_TERMINAL.md). The existing preview still selects
the original blocked job.

No-deadline software verification passed: 1,558 backend tests, including 62
provider tests, plus Ruff, unchanged generated schemas and syntax validation of
all four Terminal command blocks. Offline SDK tests confirm timeout null and
absence of `X-Server-Timeout`; success, connection failure and rate-limit cases
use exactly one HTTP request through the explicitly injected zero-retry HTTPX
transport, including when aiohttp is available. Tests cover cancellation,
keyboard interruption, lease loss, immutable runtime choices, descendant-root
rejection and shared budgets. Read-only protection verification again confirmed
all 160 red aeroplane files and semantic database records unchanged. Evidence is
under `evidence/no-timeout-*` and `evidence/metrics/provider-httpx-no-retries-pytest.txt`
in the existing ignored experiment directory. These checks initiate no live
inference and do not establish assembly accuracy.
