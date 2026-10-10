# Isolated Space Shuttle ADK experiment

This report tracks the fresh `31134 / booklet-01` experiment. Historical Shuttle
scenes and responses are excluded. The configured key is valid: a read-only
`models.get` lookup, a bounded text generation and a bounded official-image
generation succeeded. Both generation diagnostics are charged to this job.
The corrected schema transport now returns page indexes validated against the
original engine schema. Booklet indexing is in progress.

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
`gemini-json-subset-v2` (4,030 tokens, 15.03 seconds). It started full booklet
indexing under the same 300-request ceiling. First-four reconstruction, candidate
rendering and real-data playback gates await the reconstruction checkpoint.

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

The opt-in desktop/390×844 real-data suite is implemented. Without its environment
variable, both tests skip and start no servers or inference. It requires an actual
candidate before navigation, callout and playback gates can pass.

All 160 protected red aeroplane assets/configuration/candidate files remain
byte-identical. Logical revision/database rows in `var/guide2build.sqlite3` and
`var/publication.sqlite3` remain unchanged, and no normal engine database has
been created. The existing application stays on ports 5173 and 8000. The isolated
read-only preview runs at http://127.0.0.1:4176 and currently returns
`candidate_available=false` and HTTP 409 for its release. Browser selection
visibly shows the Shuttle and its blocked state without exposing another
candidate.

Human review, physical build, deployment, publication and GitHub push are
unperformed. Entire checkpoint references will be recorded after verification.

## Exact commands

Run from `/Users/admin/learn_python/brickvisionx`.

```sh
DATA=var/experiments/adk-31134-booklet01-20261010/data
JOB=2573f70cc20e45329bce1656bddf64d9

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
