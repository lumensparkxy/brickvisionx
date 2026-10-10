# Ten-set source preparation

3 October 2026. Local implementation and official-source validation; no paid inference or deployment.

The ten-set catalogue now resolves all ten sets and keeps their 19 observed official PDF booklets
separate. All 19 downloaded and rendered: 2,231 pages. The only available 3D candidate remains
30669/alt-02. Source preparation does not establish reconstructed parts, poses, assembly correctness,
human acceptance or physical assembly for the other booklets.

## Configuration

Set these environment variables before starting both the API and worker. Defaults already cover all
19 tested booklets; no local environment override is necessary. Values outside the ranges fail startup.

| Variable | Default | Allowed range | Scope |
|---|---:|---:|---|
| `GUIDE2BUILD_PDF_MAX_MIB` | 256 | 1–512 | One downloaded PDF |
| `GUIDE2BUILD_PDF_MAX_PAGES` | 1,000 | 1–2,000 | One booklet |
| `GUIDE2BUILD_PDF_DOWNLOAD_SECONDS` | 300 | 1–900 | Whole download and bounded lock wait |
| `GUIDE2BUILD_RENDER_BATCH_PAGES` | 25 | 1–25 | One render batch |
| `GUIDE2BUILD_RENDER_MAX_MIB` | 2,048 | 1–8,192 | Rendered output per booklet |

The 24-million-pixel limit remains per page; the 150-million-pixel limit now applies per batch.
Every PDF preflight/render child retains a 60-second CPU limit, 90-second wall limit and 1.5-GiB memory
ceiling. Files retain a 128-MiB ceiling. Disk checks retain a 256-MiB free-space reserve. These are
per-process/per-booklet limits, not a global deployment quota. The default worker remains sequential.
No GPU ceiling changed: source PDF rasterization is separate from Three.js scene rendering.

## Reliability and provenance

- Downloads retain exact official URLs, source hashes and receipts. Retained versions share file bytes
  via hard links; replacing the current PDF does not replace a retained version.
- Rendering uses a bounded private snapshot of the PDF. The expected receipt hash is checked before
  children run. The source hash, renderer version, scale and batch settings bind resume records.
- Completed batches are checksum-verified before reuse; corrupted batches are rerendered. The complete
  `pages.json` is published only after all pages finish. Source-change detection invalidates manifests.
- Cancellation checks interrupt download chunks, lock waits and active render children. A separate
  heartbeat renews the worker's 300-second lease every ten seconds; stolen/expired owners cannot commit.
- Progress reports actual completed/total pages. Retry retains verified batches. Preparation without
  an authored scene ends explicitly as source prepared / reconstruction unavailable.
- Source-page requests use the committed manifest and image hash, including pages above index 249.
  The static mount exposes only LDraw assets; it cannot bypass source-page validation.
- Catalogue page counts were measured from the exact downloaded PDFs. Main instruction counts remain
  unknown except for the existing 30669/alt-02 candidate; page count is not an instruction count.

## Evidence

Raw receipts, manifests, timings and verification records are under `var/evidence/large-source-pipeline/`.
Official source files remain private in ignored `var/sources/`; rendered pages remain in `var/public/pages/`
and are served only through the checked source API.

The original unchanged-limit baseline is preserved in [TEN_SET_RELEASE_REPORT.md](TEN_SET_RELEASE_REPORT.md).
Its nine unsupported-set errors and six size rejections describe the earlier run, not the current catalogue.
Current software results and exact source totals are recorded below.

## Final measured results

| Tier | Set | Registered booklets | Rendered PDF pages | 3D candidate |
|---|---|---:|---:|---|
|simple|30669 — Iconic Red Plane|3|19|30669/alt-02 only, needs review|
|simple|60400 — Go-Karts and Race Drivers|2|68|Unavailable|
|simple|31134 — Space Shuttle|3|140|Unavailable|
|medium|31129 — Majestic Tiger|3|244|Unavailable|
|medium|42163 — Heavy-Duty Bulldozer|1|76|Unavailable|
|medium|76920 — Ford Mustang Dark Horse Sports Car|1|100|Unavailable|
|complex|42171 — Mercedes-AMG F1 W14 E Performance|1|360|Unavailable|
|complex|21343 — Viking Village|1|252|Unavailable|
|complex|21061 — Notre-Dame de Paris|1|292|Unavailable|
|complex|10316 — THE LORD OF THE RINGS: RIVENDELL™|3|680|Unavailable|

All 19 fresh jobs completed using pipeline `assisted-batched-v3` and resume identity version 2. Each final page returned 200 through the checked API. All jobs correctly ended `needs_review`: eighteen lack authored scenes; the existing alternate candidate remains unaccepted.

Actual PDFs total 882,995,596 bytes; PNG output totals 884,107,042 bytes. Largest PDF: Notre-Dame, 193,037,136 bytes. Largest booklet: Formula 1, 360 pages. Six booklets exceeded the old 150-million-total-pixel ceiling; batching handled them within the unchanged per-page ceiling.

Final sequential worker verification took 96.357 s summed per-job wall time (including queue/poll overhead, using already downloaded PDFs); slowest job 14.836 s. This is one local Mac run, not a throughput guarantee. Snapshot copying adds bounded disk I/O and transient storage. Download/render timings from the initial preparation are separately retained in source-outcomes.json.

A real 42171 cancellation after 25 committed pages left no complete manifest. Retry completed 360 pages and reused page 0 without changing its modification time. Evidence: cancel-resume.json. Mid-render source replacement and cancellation/restoration tests compare actual raster hashes; independent review reproduced the fixes. Whole-worker process-kill recovery remains covered by deterministic lease tests, not an additional live crash run.

- `.venv/bin/python tools/check.py`: 108 backend tests, 27 frontend tests, schema freshness, Ruff, TypeScript and production build passed (`check.log`).
- `GUIDE2BUILD_AUDIT_DIR=var/evidence/large-source-pipeline npm run test:e2e -- --workers=1`: 28 passed; 2 opt-in performance tests skipped (`browser.log`).
- Final page-progress copy recheck: 1 browser test passed (`final-ui.log`). Real ten-set lookup/status audit results are `set-outcomes.json`.
- Live desktop Rivendell preparation inspected; 332/332 pages prepared and no 3D reconstruction explicitly shown (`live-rivendell-prepared.png`). Phone multi-booklet progress/resume/close layout inspected (`source-only-phone.png`, mocked lifecycle test).
- Original 30669 full playback, callout controls, source/BOM, review, replay, camera and responsive regressions passed. Assembly data was unchanged.
- Independent review: static-page bypass, source identity race and resume poisoning fixed and rechecked. No additional P1/P2 in that bounded review.

Existing Three.js chunk-size advisory and TestClient deprecation remain. GPU benchmarks were not repeated for this source-processing change; no new scenes exist to measure. The earlier real Apple M3 small-candidate results remain in TEN_SET_RELEASE_REPORT.md. Human review, physical assembly, nine additional 3D reconstructions, generic automatic conversion and public-production readiness remain unverified/blocked.
