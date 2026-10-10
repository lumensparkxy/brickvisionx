# Generation and local overhead cleanup — 4 October 2026

Implemented bounded catalogue reuse and preview findings caching, reduced cold evidence
storage, and stopped redundant local services. Saved scenes, historical evidence bytes,
source integrity, candidate limits and the generator model remain unchanged. No new
inference, publication or deployment occurred.

## Measured results

| Area | Before | After | Evidence |
|---|---|---|---|
| Retained main 4 placement search | 2.084–2.101 seconds | 0.987–0.988 seconds | Canonical full-result equality; same 64 evaluations, eight beam entries and three renders. |
| Full catalogue verifications per search | 107 | 2 | Invocation-local reuse with an unconditional final file check. |
| Catalogue/geometry file opens | 9,937 | 337 | Includes the final rereads; no process-wide trust cache. |
| Warm saved-preview status computation | 220.67 ms mean | 1.25 ms mean | Twenty read-only polls per implementation; identical canonical response SHA. |
| Fifteen cold evidence files | 1,213,517,176 readable bytes | Same readable bytes | 1,073,291,264 allocated bytes saved through transparent APFS compression. |
| Idle local services | Three historical previews and one conversion worker | Stopped | Current preview on 4176 and saved final model preview on 4179 retained. |

Timings are local, bounded software measurements. The search replay retains the raw
proposal and candidate alternatives; no selection or accuracy mechanism was removed.
The status measurement excludes HTTP transport. End-to-end generation time and new
autonomous reconstruction accuracy were not measured.

## Implementation and boundaries

`verification_cache.py` creates a context only for one hypothesis enumeration. Catalogue
metadata, provenance and connector dependency inputs are hash-verified initially, then
their exact bytes, file identities and ancestor paths are checked again on every exit,
including a raw fallback or an exception. Cached parsed values are copied for each caller;
the cache is bounded and discarded at exit. Standalone catalogue and diagnostic calls
remain fresh. Unsupported-part symmetry meshes read through `perception.py` retain their
existing independent verifier; they are outside this new catalogue exit fence.

`preview.py` caches only the public findings projection for an unchanged authenticated
job object. A committed SQLite change invalidates that projection. Candidate/source
validation remains live, and returned projections are independent copies. The response
still exposes uncertainty and distinguishes pre-correction findings from a fresh review.

Cold JSON evidence was copied using macOS `ditto --hfsCompression`, verified against its
original SHA-256, then atomically replaced only after the unchanged-source identity,
permissions and modification time were confirmed. Every path remains an ordinary readable
file. This changes storage representation, not JSON, scene poses, receipts or audit hashes.
Allocated-byte savings are file-level measurements, not a claim about filesystem-wide
free capacity or snapshot retention. No archive extraction is needed to read the evidence.
An ordinary copy on another filesystem retains the complete original bytes.

The stopped services were preview ports 4175, 4177 and 4178, plus the idle conversion
worker. Their exact process arguments and empty worker leases were checked before graceful
SIGINT. Only failed/needs-review conversion jobs existed; no active or queued work was
interrupted. Historical candidates remain stored and can be previewed again with
`tools/preview_engine.py JOB_ID --data-dir DATA_DIR --port PORT`.

## Validation and preservation

- `.venv/bin/python tools/check.py --python-only`: **912 passed**, one existing Starlette
  deprecation warning; generated schemas current.
- `.venv/bin/python -m ruff check apps/api tools tests/backend`: passed.
- `git diff --check`: passed.
- `npm run test:e2e -- --project=software tests/e2e/exploration-preview.spec.ts`: **one
  passed**, including unresolved instruction navigation and the phone findings layout.
- Actual browser on a temporary updated preview: saved detached module and final
  17th snapshot rendered; findings and their pre-correction label remained visible;
  zero recorded JavaScript errors. Temporary tab/service cleaned up afterward.
- **161 saved-state files** checked byte-for-byte: all live engine scenes and databases,
  reconstruction scenes, frozen pilot scenes, and selected source/geometry receipts
  unchanged. All fifteen compressed evidence files separately hash-verified afterward.
- Final saved R2 file SHA:
  `fa13022eb0f109d6b7a8f644e25eb12e448d8ae0b07fb339d907facf90b3cb0d`.

A wider historical-file scan was stopped after slow reads; this report does not claim a
complete whole-workspace comparison. Preservation checks cover saved state and every
actual compression target. No models or historical evidence were deleted. Frontend source
was unchanged; the prior frontend checks were not rerun as though they were new evidence.
Human and physical verification remain `not_run`.

Evidence: `var/evidence/overhead-cleanup-20261004/`, including search replay, before/after
status profiles, compression receipts, process records, test logs, preservation records,
browser inspection and actual screenshots.

## Remaining overhead

Full-history diagnostics still repeat across placement candidates; reusing accepted-prefix
state would require a separate output-equivalence and correction-invalidation change.
Model/provider calls remain the larger unmeasured component of new full-booklet runs.

Copied old E2E backups contain unique screenshots and referenced hash manifests; their
whole-tree redundancy was not established, so they remain readable. Installed dependencies,
the cloud SDK and source PDF version aliases remain available. Sixteen PDF/version pairs
already share inodes; deleting those aliases would not recover their apparent duplicate
size. No new runtime dependency or cleanup service was added.
