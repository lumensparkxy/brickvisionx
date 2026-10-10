# Ten-set release evaluation

Date: 3 October 2026. Local testing only; no publication, paid inference or completed community models.

> Historical baseline before the authorized ingestion changes. Current source support is ten sets,
> nineteen booklets and2,231rendered pages: see [LARGE_SOURCE_PREPARATION.md](LARGE_SOURCE_PREPARATION.md).
> The missing reconstruction/acceptance gates below remain unresolved.

## Release decision

**The ten-set rendering and reconstruction-correctness release gate is blocked.** The current app can
open one PDF-assisted candidate, 30669/alt-02. The other nine selected set numbers stop at catalogue
lookup, before a 3D scene exists. A passing negative-flow test is not a successful set reconstruction.
The accepted-tutorial endpoint for 30669 also returns 409 because its candidate has not been accepted.

This is a functional coverage limitation, not evidence of GPU failure. Creating catalogue entries alone
would not solve it: assisted preparation currently renders source pages and loads an existing authored
scene; automatic conversion explicitly returns 503 provider_unavailable.

## Evaluation set selection

The official-source matrix is [TEN_SET_SOURCE_MATRIX.md](TEN_SET_SOURCE_MATRIX.md). These workload tiers
are ours, not LEGO ratings. Advertised box counts are not selected-build BOM or rendering complexity.

| Tier | Set | Name | Advertised pieces | Current application outcome |
|---|---|---|---:|---|
| Simple |30669|Iconic Red Plane|51|One 32-piece alternate candidate available; needs review|
| Simple |60400|Go-Karts and Race Drivers|99|404 unsupported_set; rendering blocked|
| Simple |31134|Space Shuttle|144|404 unsupported_set; rendering blocked|
| Medium |42163|Heavy-Duty Bulldozer|195|404 unsupported_set; rendering blocked|
| Medium |76920|Ford Mustang Dark Horse Sports Car|344|404 unsupported_set; rendering blocked|
| Medium |31129|Majestic Tiger|755|404 unsupported_set; rendering blocked|
| Complex |42171|Mercedes-AMG F1 W14 E Performance|1,643|404 unsupported_set; rendering blocked|
| Complex |21343|Viking Village|2,103|404 unsupported_set; rendering blocked|
| Complex |21061|Notre-Dame de Paris|4,383|404 unsupported_set; rendering blocked|
| Complex |10316|THE LORD OF THE RINGS: RIVENDELL|6,167|404 unsupported_set; rendering blocked|

## Correctness boundary

The available revision, pdf-assisted-30669-alt02-v3, contains 12 main steps, 16 microsteps and 32 unique
physical pieces. Both subassembly attachment steps introduce zero new pieces. Current source identity
is verified against retained official bytes. UI navigation/replay restoration tests do not establish
connector validity, strength or physical assembly. Geometry/connector/physical fields remain not_run,
with unresolved source/contact/part-variant findings retained. Human acceptance is not recorded.
No automatic-conversion accuracy was measured, because no runtime provider/generic reconstruction exists.

## Bottlenecks identified in code

- Catalogue coverage and absent generic perception/pose solving are the first blockers.
- Source parsing caps: 20 MiB PDF, 250 pages, 150 million total raster pixels, 90s wall, 60s CPU and approximately
  1.5 GiB parsing memory. Large booklets need staged, resumable processing within deliberate resource limits.
- Complete snapshot poses and traversal of every visible part across every instruction make scene JSON
  and startup bounds work grow with cumulative part appearances, not only final piece count.
- Distinct part/color assets load/parse sequentially, and thumbnails are generated eagerly before the
  viewer becomes ready. Physical parts use mesh clones rather than GPU instancing; larger scenes need
  real workload measurements before choosing batching or level-of-detail optimizations.
- The default source worker processes jobs sequentially; ten preparations queue. No batch throughput
  or large-set render capacity can be claimed from this one small candidate.
- Public production has additional gates: the API is intentionally local-only and unauthenticated.
  Public authentication, authorization, resource/cost controls and source/asset distribution policy are
  separate work. Safari and physical phone GPUs are not covered by desktop Chromium emulation.

Raw evidence is under var/evidence/ten-set-release; original failed/partial measurement attempts are retained with their labels.


## Measured PDF ingestion

The existing production downloader and bounded renderer were run against one selected, explicitly
observed official link for each set. For 30669 this was the supported alternate 02. For the others it was
the first main booklet, not all alternatives/sequential books. No production catalogue entry was added.

| Set | Download | PDF pages rendered | Download seconds | Render seconds |
|---|---|---:|---:|---:|
|30669|Passed; 2,386,631 bytes|8|0.18|0.40|
|60400|Passed; 6,047,337 bytes|32|0.49|0.50|
|31134|Passed; 12,890,144 bytes|60|0.28|0.73|
|31129|Blocked: existing 20 MiB size limit|Not run|—|—|
|42163|Passed; 7,679,400 bytes|76|0.59|0.68|
|76920|Blocked: existing 20 MiB size limit|Not run|—|—|
|42171|Blocked: existing 20 MiB size limit|Not run|—|—|
|21343|Blocked: existing 20 MiB size limit|Not run|—|—|
|21061|Blocked: existing 20 MiB size limit|Not run|—|—|
|10316|Blocked: existing 20 MiB size limit|Not run|—|—|

Four PDFs downloaded and all 176 pages rasterized. Covers for 60400, 31134 and 42163 were visually checked
against their printed set numbers and intended models. These are source-ingestion passes, not 3D scene
or full-set correctness passes. Six sources were rejected by the actual downloader's size limit; no
resource ceiling was relaxed. Official page sizes/links are in the source matrix. Downloads, actual
SHA-256 receipts and rendered page manifests remain in ignored private evidence.

## Measured rendering on the available candidate

Production Vite build on loopback 4173; existing local API/source/parts/reconstruction cache. Chromium 153,
macOS 26.6.2, actual Apple M3 through ANGLE Metal. Desktop 1440×900 DPR 1; phone 390×844 DPR 2 is emulated
on the same Mac GPU. Each profile exercised all 16 instructions, active final-model orbit, settled idle
and five close/reopen cycles. Cold means HTTP cache cleared, not server/OS/driver caches cleared.
One cold and one warm workflow measurement per profile are individual observations, not percentiles.

| Metric | Desktop | Phone emulation, same GPU |
|---|---:|---:|
|HTTP-cold Find-to-usable|2.395 s|0.997 s|
|HTTP-warm Find-to-usable|0.922 s|0.907 s|
|Actual render submissions during orbit|59.864 /s|59.730 /s|
|Orbit frame interval p95|17.700 ms|17.600 ms|
|CPU render submission p95|0.600 ms|0.700 ms|
|GPU render time p95, mixed workload|1.617 ms|1.248 ms|

- Final assembly: 98 main-pass draw calls, 13,967 triangles and 13,126 lines. Shadow passes are excluded from
  these Three.js counters; GPU/CPU render timing includes actual rendering work.
- GPU timer results are real asynchronous EXT_disjoint_timer_query_webgl2 samples: 155 desktop and 154
  phone samples, no disjoint discards. They mix initialization, thumbnails, replay and orbit; they are
  not orbit-specific or browser-compositing times. GPU utilization percentage and VRAM bytes were not measured.
- After all steps: 87 uploaded geometry resources / 1 texture. Five identical final-step-only reopens each
  reached 56 geometry resources / 1 texture (earlier outlines were never uploaded), one live canvas, and
  disposed counts 0/0. Compare identical workloads. This is not proof of zero browser/driver memory leaks.
- Stationary renderer:zero submissions over about 1.5 s once damping settled. Damping continued for
  approximately 4.95 s after the native-GPU drag; a responsiveness/battery optimization candidate.
- Native desktop cold initialization: 351 ms geometry work and 506 ms eager thumbnail generation, versus
  103 ms and 51 ms warm. Phase totals do not separately isolate network, shader compilation or readback.
- Software fallback was also measured: SwiftShader desktop 26.68 render submissions/s (below the proposed
  30 FPS target), versus 36.95 for the smaller phone viewport. It is not Apple GPU evidence.

The native small-model result meets the proposed three-second cached-source load and 30 FPS targets on
this baseline. It does not predict performance for the missing medium/complex scenes or physical phones.
Safari, long thermal sessions, WAN loading and public-hosting throughput remain untested.

Full method, data and screenshots: var/evidence/ten-set-release/performance/README.md and hardware/*.json.
The first idle test incorrectly used a fixed two-second wait while damping was active; original evidence
is retained. The corrected test waits for observed settling and records it; product behavior was unchanged.

## Next release gates, in order

1. Prepare nine additional source-backed scenes or implement and evaluate a generic conversion pipeline;
   record raw and corrected output separately. No paid provider was configured or invoked in this audit.
2. Add explicit model/booklet identity plus staged, bounded, resumable processing for larger PDFs. Do not
   simply remove safety limits; test cancellation, recovery, disk/RAM budgets and sequential books.
3. Compare every actual assembly and step against its official source, resolve mapping/contact findings,
   and obtain the required human acceptance. Current candidate remains needs_review.
4. Repeat the renderer audit on those real scenes, low-end/physical devices and Safari. Use actual
   bottlenecks to choose lazy thumbnails, asset concurrency, bounds caching, instancing or level of detail.
5. Complete separately authorized public deployment/security/rights/operational gates before publishing.

## Validation and changes

- `.venv/bin/python tools/check.py`:78 backend tests,26 frontend tests, schema freshness, lint,
  TypeScript and production build passed. Evidence:check.log. Existing large Three.js chunk advisory remains.
- `npm run test:e2e -- --workers=1`:27 passed,2 performance cases intentionally skipped in the ordinary
  suite. Both were separately enabled for software and native hardware (four passing profile runs).
  Evidence:regression.log and performance reports. Existing exact-snapshot, source/BOM, camera,
  callout/replay, cancellation/retry, review, accessibility and narrow-layout regressions passed.
- The final ten-set audit used the actual frontend/API and confirmed one catalogue hit/nine404s.
  The provider boundary returned503 without creating an inference job. Exact responses/screenshots:
  set-outcomes.json and lookup-*.png. An earlier159-piece Super Robot selection was replaced with the
  755-piece Tiger for a wider workload spread; that preliminary audit remains separately labelled.
- Source test command: `.venv/bin/python var/evidence/ten-set-release/run_source_audit.py`;
  ten bounded attempts, four PDF/render passes and six explicit size rejections. Source cache and actual
  receipts are private ignored files; no model or manual was published.
- Product code change is opt-in renderer diagnostics (`?benchmark=1`), not an assembly/UI change.
  It adds bounded CPU/GPU/resource sampling only when explicitly enabled. Repeatable benchmark and
  ten-set audit tests were added. Production catalogue, provider and source ceilings are unchanged.
- Independent review checked generalization gates and metric interpretation. GPU mixed-workload scope,
  main-pass counter scope and first-ready-frame timing are explicitly labelled in final evidence.

Verdict: local small-candidate software/performance evidence is positive. Ten-set rendering/correctness,
large-booklet ingestion, generic conversion, human acceptance and public-production gates are not passed.
