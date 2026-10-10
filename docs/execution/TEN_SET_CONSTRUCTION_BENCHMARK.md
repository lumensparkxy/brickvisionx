# Ten-set actual construction attempts and renderer benchmark

Measured 3 October 2026. **Ten sets attempted; eleven partial booklet candidates; zero complete or accepted tutorials.** The earlier source-preparation benchmark did not measure construction. This report supersedes any interpretation that a prepared PDF becomes an accurate 3D tutorial in five seconds.

## Method and evidence boundaries

Three workers independently inspected the selected official PDFs, identified individual LDraw geometry, and authored source-derived candidate steps. Complete community models, existing reference coordinates and finished assembly sequences were not used. This is **PDF-assisted agent authoring**, not the application's automatic reconstruction service. That service remains disabled; no paid provider was invoked. Existing production 30669/alt-02 remains unchanged and is not counted as a fresh success.

Official PDFs and page images were already cached before the authoring timers. Part acquisition, source inspection, pose reasoning, corrections, local previews and waiting are included. Each worker interleaved several cases. Their elapsed intervals overlap; they cannot be summed or treated as exclusive per-set processing times. Deterministic script execution is replay of authored coordinates, not PDF interpretation. No timing below establishes a service-level conversion latency.

Candidates were staged in a separate local API/viewer, using actual source receipts, page hashes and verified individual geometry. All eleven passed schema/provenance/dependency validation. Every candidate snapshot was visited in a real browser; replay, source-panel identity, part counts derived from the manifest, desktop and phone layout were exercised. The UI checks establish that the manifest is displayed consistently, not that its contents agree with the official assembly.

## Construction outcomes

Complexity is the original 3 small / 3 medium / 4 large test grouping, not a page-count-only classification. Counts below mean **authored candidate coverage**, not correct or accepted steps. All outcomes are incomplete/needs_review.

| Group | Set / selected build | PDF pages | Candidate main steps | Main obstacles |
|---|---|---:|---:|---|
| Small | 30669 Red Plane, main | 2 poster pages | 8 / 18 | Inverted part origin, root spread and elevation; dependent wing attachment |
| Small | 60400 Go-Karts, both booklets | 32 + 36 | 20 / 23 and 21 / 25 | Steering components, printed pieces and figures absent; bumper orientation visibly wrong |
| Small | 31134 Space Shuttle, booklet 1 | 60 | 8 / 48 | Wing handedness/position, clip and side-stud alignment |
| Medium | 42163 Heavy-Duty Bulldozer | 76 | 7 / 57 | Transmission attachment direction/depth and next gear mapping |
| Medium | 76920 Ford Mustang Dark Horse | 100 | 6 / 105 car steps | Dashboard/sticker mapping and chassis offsets; four-step minifigure prelude also missing |
| Medium | 31129 Majestic Tiger, booklet 1 | 132 | 20 / 290 tiger steps | Side-panel pieces and attachment; 24 scenery steps also missing |
| Large | 42171 Mercedes-AMG F1 | 360 | 4 / 461 | Suspension-arm variant, axle depth and hinge frames |
| Large | 21343 Viking Village | 252 | 4 / 432 | Corner/slope poses, next pin-connector mapping |
| Large | 21061 Notre-Dame | 292 | 11 / 393 | Turned-over underside reinforcement positions |
| Large | 10316 Rivendell, all three booklets | 184 + 164 + 332 | 2 / 911 | Rotated-view depth ambiguity; multi-booklet source provenance unsupported in one scene |

Go-kart coverage has explicit gaps, not a contiguous complete prefix: yellow omits 18,19,21; turquoise omits 19–22. Figures/accessories are outside those vehicle counts and remain absent. Rivendell's candidate covers only book 1 steps 1–2; 911 is the complete three-booklet numbered-step denominator, with final unnumbered assembly also required. Alternate builds not selected for this matrix were not constructed.

| Authoring worker group | Recorded elapsed interval | Interpretation |
|---|---:|---|
| Three small cases | About 26.3 minutes | Shared/interleaved interval to partial candidates and reports |
| Three medium cases | About 22.7–24.2 minutes | Overlapping case intervals to partial candidates and reports |
| Four large cases | About 24.9 minutes | Same shared/interleaved interval across four cases |

**No full-booklet construction duration was obtained.** In particular, the 100-page Mustang produced only a six-car-step candidate, so a time to complete a 100-page tutorial remains unmeasured. These figures must not be linearly extrapolated by page count; even the two-page poster encountered substantial pose ambiguity.

## Actual rendering measurements

Native Apple M3, ANGLE Metal, Chromium 153, WebGL 2, DPR 1; local development build at 1440×900. Each case is one measured cold-HTTP load and one warm load, not a repeated load-latency distribution. GPU timer p95 is from sampled queries across mixed viewer work. Orbit rate uses about three seconds of actual rendered frames. Sources and geometry were already prepared on the server.

| Set / guide | Candidate parts | Cold load s | Warm load s | Orbit frames/s | GPU mixed p95 ms | Main-pass draw calls | Main-pass triangles |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10316 / booklet-01 | 3 | 0.955 | 0.955 | 59.95 | 0.904 | 11 | 5,222 |
| 21061 / main | 36 | 1.618 | 1.592 | 59.92 | 3.106 | 113 | 99,618 |
| 21343 / main | 9 | 1.095 | 1.090 | 59.95 | 0.983 | 31 | 7,440 |
| 30669 / main | 14 | 0.946 | 0.917 | 59.91 | 1.201 | 45 | 8,362 |
| 31129 / booklet-01 | 66 | 0.953 | 0.999 | 59.96 | 1.552 | 232 | 20,616 |
| 31134 / booklet-01 | 14 | 0.930 | 0.917 | 59.83 | 1.011 | 46 | 7,716 |
| 42163 / main | 16 | 0.929 | 0.903 | 59.94 | 1.181 | 58 | 16,810 |
| 42171 / main | 8 | 1.082 | 1.069 | 59.97 | 1.050 | 34 | 10,926 |
| 60400 / booklet-01 | 36 | 0.940 | 0.966 | 59.83 | 1.349 | 111 | 20,591 |
| 60400 / booklet-02 | 38 | 0.945 | 0.957 | 59.90 | 1.256 | 117 | 20,641 |
| 76920 / main | 19 | 0.932 | 0.918 | 59.97 | 1.143 | 58 | 11,938 |

All eleven browser tests passed in 1.7 minutes. No browser JavaScript errors were recorded. The captured disposed renderer reported zero remaining geometry/texture objects. This is not a global VRAM or memory-leak measurement. Phone screenshots use a 390×844 layout on the same desktop GPU, not physical phone hardware. Main-pass counts exclude shadow passes. CPU-submit samples, line counts, resource counts, discarded GPU queries and raw samples are retained in each renderer.json.

**These candidates contain only 3–66 pieces.** The smooth results do not establish GPU performance for thousands of pieces in complete complex sets. GPU utilization percentage, VRAM bytes, physical-phone behavior and full-set memory consumption were not measured.

## Failures and bottlenecks

1. **Part recognition and coordinate recovery dominate.** Similar-looking parts were confused; LDraw local origins, inverted pieces, handed pieces, half-stud offsets and Technic insertion depths caused real errors. Tiger revisions corrected 17 individual poses; this is corrected output, not unassisted success.
2. **Printed pieces and composite components need explicit mapping.** Missing decorated parts and minifigures cannot be silently replaced. A steering-wheel alias resolving to a Shortcut was rejected; wheels were instead built from separate permitted rim and tyre files.
3. **Source-to-render visual review is essential.** The Viking revision fixed initial overlapping pieces, but independent review found its 54200 cheese slope still floats 16 LDU above the base due to an incorrect local-origin height. The final go-kart step 11 renders its low front bumper upright as a fin, visibly differing from the official panel. The final plane also fails source alignment. Browser test success does not detect these semantic errors.
4. **Asset acquisition has rate limits.** A genuine HTTP 429 added 55.6 seconds to a Notre-Dame part fetch. Reusing verified individual-part caches helped. This is a dependency bottleneck, not PDF preparation or GPU time.
5. **Multi-booklet provenance is incomplete.** SceneManifest permits one source hash. Carrying Rivendell parts across three source booklets needs explicit linked-source support; falsifying one source identity is unacceptable.
6. **Automatic reconstruction remains unimplemented/configured off.** Raising PDF limits or hiding Prepare booklet cannot turn cached pages into correct assembly data.

No geometry/connector correctness pass, human acceptance or physical assembly test is claimed. The first-four-step accuracy gate remains unpassed for these fresh cases. This is a failed full-construction benchmark with usable partial evidence, not production readiness.

## Validation and reproducibility

- `.venv/bin/python tools/check.py`: 108 backend and 27 frontend tests passed; Ruff, schema check, typecheck and build passed. Existing large-chunk warning remains.
- Stage: `.venv/bin/python tools/stage_construction_benchmark.py var/evidence/ten-set-construction/benchmark-cases.json`.
- Browser: `RUN_CONSTRUCTION_AUDIT=1 CONSTRUCTION_HEADED=1 CONSTRUCTION_EVIDENCE=var/evidence/ten-set-construction/browser-final npm run test:e2e -- tests/e2e/construction-audit.spec.ts --workers=1`.
- Private runtime startup commands/configuration: `var/evidence/ten-set-construction/runtime-processes.json` and `vite.config.mjs`.
- Exact frozen case revisions and asset directories: `var/evidence/ten-set-construction/final-staged-cases.json`.
- Machine-readable aggregate: `var/evidence/ten-set-construction/summary.json`.
- Per-case report.json files contain source hashes, attempted resolutions, timings and validation commands; old candidate revisions and correction records are preserved.
- Browser evidence: `var/evidence/ten-set-construction/browser-final/<set>-<guide>/renderer.json`, every-step PNGs and desktop/phone captures.
- Independent review: `var/evidence/ten-set-construction/independent-review.md`.

The next release gate is one complete source-matched reconstruction with reproducible accuracy checks, then repeating that process across the matrix. Prepared, reviewed tutorials should be cached for users; no on-demand completion-time promise is supported by this run.

Temporary benchmark servers on8001/5174 were stopped after the run; listeners were verified closed. Main app8000/5173 remained available. Evidence: `var/evidence/ten-set-construction/runtime-final-listeners.json`.
