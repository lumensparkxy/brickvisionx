# Guide2Build implementation and validation

## Test-suite optimization — 4 October 2026

Added an explicitly labelled quick development scope: **105 selected backend cases**, schema, Ruff,
frontend type checking and all **52 frontend tests**. The first quick backend run passed in 3.31 seconds;
independent final backend-only quick verification passed in 1.75 seconds. The no-flag command and
unchanged CI still run the full regression and build; quick/browser combination is rejected before startup.

Consolidated three identical setup workflows into one prompt-contract test while retaining every
assertion, removed unused checkpoint snapshots, made needed recovery snapshots opt-in, and replaced
durable source/geometry/job setup with equivalent in-memory inputs in six pure scoring and sixteen
malformed-request tests. All distinct input variants remain. The frontend check now runs TypeScript once.

Final full check passed **1,041 backend cases**, **52 frontend tests**, schema, Ruff, TypeScript and build.
The baseline was 1,043 cases / 31.76 seconds; final full pytest reported 28.06 seconds. These are single
observations of changed test setup, not a causal performance benchmark. Independent review verified
case mapping, correction input equivalence, recovery snapshot consumers and full/quick command scope.

All 40 pinned saved scenes/sources, all 24 live job rows and all 14 pinned engine/command files are
unchanged. Local app ports remain closed. No inference, app/browser startup, publication or model/scene
change occurred. This work reduces development-check overhead; tests do not run during generation or
saved-model playback. See [TEST_SUITE_OPTIMIZATION.md](TEST_SUITE_OPTIMIZATION.md) and
`var/evidence/test-suite-optimization-20261004/` for exact commands, JUnit, mappings, pins and limits.

## Engine efficiency implementation — 4 October 2026

Implemented actionable assembly repairs, exact packed model context, invocation-local diagnostic
prefix reuse, immutable candidate checkpoint files and an explicit two-worker option for different
sets. Instructions and same-set booklets remain ordered. Existing jobs retain their legacy policy;
model/provider choices, saved SceneV2 data and production playback are unchanged.

The final check passed **1,043 backend tests**, **52 frontend tests**, schema, Ruff, TypeScript and
build. Independent review reproduced and resolved partial nested-group repair scope, unnecessary
unnumbered-attachment repair and expired-owner cancellation. The real local runner with synthetic
providers retains accepted checkpoints and consumed attempts after two-worker Ctrl-C/provider pause.
No browser/server was started, preserving the user's stopped-local-app request.

Final retained-trial measurements: assembly input 60,005 → 45,195 bytes (24.68% smaller), complete
initial prompts 1,402,221 → 1,394,719 bytes (0.535% smaller), and local main-4 search median 0.9905 →
0.8725 seconds (11.9% faster) with identical complete diagnostic/search output. Original synthetic
checkpoint tests reduce SQLite row payload by over 99.8%; immutable candidate files remain separate,
so this is not a total-disk-space claim. There were zero new provider calls. Full-booklet generation
speed and new reconstruction accuracy are unmeasured. Human review and physical build remain
`not_run`; no publication or production change occurred.

See [ENGINE_EFFICIENCY.md](ENGINE_EFFICIENCY.md) and `var/evidence/engine-efficiency-20261004/` for
exact measurements, fixed budgets, legacy compatibility, implementation pins and preservation
checks. Dated reports below retain earlier outcomes; local web applications are currently stopped.

## Historical generation and local overhead cleanup — 4 October 2026

Retained search output is unchanged while local search time falls from about 2.09 to
0.99 seconds; catalogue verifications fall from 107 to two. Warm saved-preview status
computation falls from 220.67 to 1.25 ms with an identical canonical response. Fifteen
historical JSON files retain their exact readable paths and hashes while saving
1,073,291,264 allocated bytes through lossless transparent compression. Three obsolete
previews and an idle worker were stopped; previews 4176 and 4179 remained available at this earlier
checkpoint and were subsequently stopped at the user's request.

All **912 backend tests**, schema, Ruff, whitespace checks and the focused browser
regression pass. Actual saved-model browser inspection records zero JavaScript errors.
All 161 checked saved-state files and all fifteen compression targets preserve their
original byte hashes. No new inference, model accuracy measurement, human/physical review
or publication occurred. See [OVERHEAD_CLEANUP.md](OVERHEAD_CLEANUP.md) and
`var/evidence/overhead-cleanup-20261004/` for measured scope and limitations.

## Complete-booklet accuracy iteration — 4 October 2026

The new exploration policy, bounded alternatives, source comparisons, immutable correction
forks and per-instruction preview findings are implemented. The source-only 30669 /
alt-02 run completed all 13 indexed panels: 12 numbered main steps, 18 snapshots and
32 pieces. One immutable assisted correction pass repairs both wing mounts, the first
callout tile and two attachment-group labels. Fixed-camera main 3 silhouette overlap
improves from 0.7583 to 0.9259; invalid grouping and unexplained-movement observations
fall from two and three to zero. All 18 snapshots have source/before/after evidence and
were exercised in the actual browser at desktop and phone sizes.

The existing `gpt-6-astra` / high provider and shared 100-call ceiling stayed fixed:
52 shared reservations, including the retained failed trial; correction added no engine
provider calls. The frozen alpha remains a comparison input, not a generator input or
independent truth. Current measurements and remaining work are in
[`ACCURACY_ITERATION.md`](ACCURACY_ITERATION.md) and `PROGRESS.json`.

The final integrated backend regression passed **637 tests** in 17.44 seconds, with no
failures or skips. Ruff, schema and whitespace checks passed, including the later selection,
segmentation, contact localization and interrupted-trial recovery fixes. Frontend typecheck, **52 tests**
and build passed. Five exploration/viewer browser regressions passed, and the later
inherited-findings labeling change passed its targeted backend and browser checks.
Evidence is retained under `var/evidence/accuracy-30669-20261004/`.

Source-only agent annotations cover all 12 main-instruction quantities (32 pieces),
26 exact design identities and 22 colours, plus 10 qualitative visible relationships.
Unannotated attributes, human review and physical verification are not inferred.
The same qualitative rubric improves from eight pass / one fail / one unknown to nine /
zero / one, matching the assisted alpha on this limited checklist. Eight localized nominal
connector conflicts remain in the corrected final model. The tail's missing center-tube
receiver was added from pinned individual geometry without changing its pose; nominal
reachability is not a physical-build claim. No publication or production change was made.
The dated entries below preserve earlier checkpoints; their former provider and gate
limitations are not the current engine status.

## Historical local change — alpha image tolerance, 3 October 2026

Implemented opt-in `--quality-profile alpha` (8 px landmark RMS, 12 px point cap); the strict default stays
4/12 px. Persisted job/receipt policy prevents changing tolerance during resume. Alpha camera fits retain
their strict failure and measured errors, and preview/viewer labels identify unverified alpha samples.
Independent review identified future-step measurements appearing in an older open snapshot; filtering by
the displayed scene's step IDs fixed it and the final browser check exercises that regression.

The source-backed **offline** re-evaluation of rejected instruction-2 trial
`69451c531c524ef5a5be037aad9f8a40` measured **7.76334236688578 px RMS** and **9.859492970123659 px maximum**.
It fails strict and passes alpha camera fitting without competing-camera ambiguity. An actual Three.js
render used the fitted camera and verified its matrices/hashes. Visual inspection finds a nearly edge-on
view, inconsistent with the source's above view. This is still an unresolved candidate; no successful
instruction-2 visual review, accepted checkpoint, complete alpha sample or automatic-accuracy claim follows.

| Check | Result and evidence |
|---|---|
| Backend, schema, lint, frontend typecheck/test/build | Passed: `.venv/bin/python tools/check.py`; 237 backend / 41 frontend tests. `var/evidence/alpha-tolerance-30669-01/checks.log`. |
| Final frontend after metadata filtering | Passed: `npm run check`; 41 tests. `frontend-final-checks.log`. |
| New CLI option | Passed: enqueue into isolated `var/evidence/alpha-tolerance-30669-01/cli-smoke`; live job queue unchanged, worker not run. |
| Source fit and render | Numerical alpha fit passed; source-view interpretation unresolved. `assess.py --render`, `tolerance-comparison.json`, `alpha-fit-render/report.json`, `alpha-fit-render/step-0002.png`. |
| Browser labels and interaction | Passed: `node var/evidence/alpha-tolerance-30669-01/portal-qa.mjs`; Chromium 153, 1440×1000 and 390×844, temporary `http://127.0.0.1:4185/`. |
| Browser scope | Actual retained strict candidate/source/parts, **synthetic alpha quality metadata** for UI states; not a generated alpha sample or complete alpha E2E proof. Browser plugin absent, regular Playwright used. |
| Page health | Passed: correct title/URL, meaningful content, no framework overlay, zero console errors or failed network responses. `portal-qa.json`. |
| Interaction | Passed: set lookup → open candidate → unverified label and quality details → rotate/reset → mobile source/3D tabs; future-step measurements excluded. |
| Screenshots inspected | Desktop and phone labels/details; actual fitted-camera image compared with official page 2. `alpha-details-desktop.png`, `alpha-details-mobile.png`, `alpha-viewer-mobile.png`. |
| Services | Temporary preview/render processes stopped. Ports 4175, 4185, 5173 and 8000 have no listeners. |
| Reconstruction coverage | Unchanged: strict job `2ad572af542a40c1bdcf4b08a5899046`, 1/12 main steps, 1 snapshot, 3 pieces. Original rejected evidence and attempt budgets retained. |
| Fresh alpha inference / tester delivery | Not run. No new provider calls, sample promotion, sharing, deployment or publication. |
| Human / physical review | Not run. |

Remaining limits: alpha tolerance does not resolve incorrect landmark identities or prove assembly
correctness. The complete booklet and broader geometry/connector checks remain outstanding. Safari and
full-browser regression suites were not rerun for this small change; targeted Chromium UI checks were run.
The pre-existing Starlette deprecation and frontend chunk-size warnings remain non-fatal.

## Historical prototype outcome — 2 October 2026

A runnable local application now supports set lookup, official-source preparation, persistent assisted jobs,
and an interactive, synchronized **PDF-assisted candidate** for all 12 printed main steps.
**Full Version I acceptance is not achieved.** The reference remains `needs_review`; runtime automatic
reconstruction is unavailable, and the first-four geometry/connector gate has not passed. No human or
physical verification is claimed.

| Dimension | Actual outcome |
|---|---|
| Scaffold/environment | Passed: real Python/npm installs and lockfiles; doctor; baseline 37 tests. |
| Local software E2E | Passed in the tested Chromium scope: real backend/source/geometry, candidate viewing, durable assisted job, correction contracts and UI. Not every acceptance item is complete. |
| PDF-assisted reference | Candidate represents 12/12 main steps, 16 microsteps, 32 physical instances, 18 candidate part designs. No main step has full geometry acceptance. |
| First four | Source-aligned candidate, 8 microsteps and 11 physical instances; 14 declared contact-frame coincidences pass. Hidden sockets and narrow-phase intersections remain unchecked. |
| Automatic conversion | Blocked/not run. No configured/authorized runtime provider. API returns 503 `provider_unavailable`; it does not replay the reference as an automatic result. |
| Human review | Not run; automated and declared local corrections cannot establish human acceptance. |
| Physical build | Not run. |

## Environment and reproducibility

macOS 26.6.2 arm64; Python 3.11.14; Node 22.14.0; npm 11.4.1; uv 0.9.2;
Codex CLI 0.158.0; Playwright Chromium 153.0.8010.12. No Git metadata exists in this folder,
so there is no branch/commit or GitHub issue mapping. No push, PR, publication, cloud resource or paid inference.

The sandbox denied uv cache access, then uv crashed in macOS system configuration even with a local cache.
Approved execution outside the sandbox completed installation. Loopback server/browser commands also needed
approved execution outside the sandbox. Normal local terminal startup uses the commands below.
An npm optional-peer resolver failure during the upgrade was repaired; the standard `npm install --cache
.cache/npm` was subsequently verified successful with zero audit vulnerabilities. No global installation.

## Official source and geometry

- Set **30669**, alternate booklet **02**, 8 pages and 12 printed main instructions.
- Official PDF: https://www.lego.com/cdn/product-assets/product.bi.additional.extra.pdf/30669_02_BI_Build_Alt.pdf
- Actual SHA-256: `6cb3e669fef3662dfd498cba0e631f1d9ec082c2bf8c0fb0a0febe303680a6b6`.
- Actual downloaded length: 2,386,631 bytes.
- Bytes/receipt: `var/sources/30669/alt-02/source.pdf`, `source.receipt.json`.
- Rendered pages: `var/public/pages/<source-hash>/`; page manifest records pixel sizes, hashes,
  renderer pypdfium2/5.13.0, scale 1.5 and top-left coordinates after page rotation.
- Geometry: 18 individual physical-part roots, **134 reachable part/primitive files plus one LDConfig**.
  `config/parts-30669-alt-02.json` pins origins/hashes. `var/public/ldraw/provenance.json` retains
  dependency relationships and actual notices. No complete community model or assembly sequence was obtained.
- Material-file notices are preserved as supplied; a missing file-specific license line is not invented.

## Reference revisions, source coverage and uncertainty

Current revision: **`pdf-assisted-30669-alt02-v3`**. All placements are labelled `pdf_assisted_authoring`.
Every instance has source evidence and pose rationale in `var/observations/30669-alt-02.json`.
The current scene and seven specific unresolved findings are in `var/reconstructions/30669/alt-02/`.
The API also retains generic candidate-mapping findings; 40 total items are currently returned.

Main steps 3 and 4 each preserve the booklet's two internal callout stages and attachment, with stable
physical IDs and zero newly counted pieces on attachment. Step 5's yellow inset is a single tapered-plate
orientation cue, not a connected subassembly; it stays visible in the source crop and real-part thumbnails.
No fictitious detached connected group was added for that inset.

Real rendered comparison caused two explicit correction rounds affecting **13 distinct physical instances**:

1. v1 → v2: seven instances corrected for actual transparent colour code, canopy origin, transverse tail
   jumpers, slope orientation and tailplane placement.
2. v2 → v3: six wing-subassembly instances corrected so main step 3 attaches the far wing and main step 4
   the near wing, matching the source sequence.

Original authored snapshots are retained in `config/reference-30669-alt-02-v1.json` and `-v2.json`.
Exact prior/new values, reasons and source references are in the `config/reference-corrections-*-v2.json`
and `-v3.json` logs; ignored revision archives and immutable SQLite revisions are also retained.
This is a corrected authored reference, **not unassisted reconstruction accuracy**.

Remaining findings: hidden first-four contacts; angled nose-tile origin; clear versus pale-blue canopy colour;
canopy contact/origin validation; jumper underside mould variant; and tailplane half-stud centring/contact.
LDraw code 40 was verified as transparent brown and replaced with candidate clear code 47; codes 39 and 43 remain
explicit alternatives. Fourteen developer-authored matching connector frames do not validate all connection
families, collision geometry, placement paths or physical strength. Global connector/geometry checks remain
`not_run` in the scene. These unresolved checks block acceptance even where the silhouette appears aligned.

## Implemented application and checks

- Curated set/guide validation; malformed and unsupported states; official source links; no upload UI.
- Atomic, bounded source download; preserved hash versions; redirect/type/signature/encoding controls;
  per-guide concurrent-write lock; isolated PDF rasterization with time/CPU/file/page/pixel limits.
  macOS memory control is a sampled RSS watchdog, not a hard address-space guarantee.
- WAL SQLite queue, transactional leases, events, cancellation, retry and source/reference-aware idempotency.
  Source hashes are checked before current-guide reads. Historical immutable revisions remain accessible.
- Typed corrections with expected revision, idempotency, actor/source/reason/prior-value audit, and structural
  revalidation; source-specific findings survive corrections. Reviewed and draft scene pointers are separate.
- Runtime scene/status validation; synchronized original crop/3D/parts; thumbnails from actual geometry;
  stable BOM; detached callouts and rigid attachment replay; seek, keyboard navigation, camera controls,
  reduced motion, responsive tabs, revision-scoped progress, named asset errors and WebGL fallback.
- Viewport cleanup disposes geometry/materials/listeners and stops its animation loop.

Independent review reproduced and repaired: unreceipted DAT files receiving official provenance;
root-only validation overlooking tampered primitives; compressed response allocation before byte checks;
and malformed job error objects crashing React. Regression tests cover those relevant boundaries.
Browser testing additionally found and repaired missing LDConfig, missing Three.js conditional-line material,
incorrect camera direction, and phone navigation overlapping camera controls.

## Actual test evidence

| Command/procedure | Result | Scope/evidence |
|---|---|---|
| `UV_CACHE_DIR=.cache/uv uv sync --extra dev` | Passed | Project-local .venv and real uv.lock. |
| `npm install --cache .cache/npm` | Passed | Real package-lock; final audit zero vulnerabilities. |
| `UV_CACHE_DIR=.cache/uv uv run python tools/doctor.py` | Passed | `var/evidence/setup/doctor.txt`. |
| `UV_CACHE_DIR=.cache/uv uv run python tools/check.py` | Passed | 78 Python tests; schema current; Ruff; TypeScript; 12 frontend tests; production build. `var/evidence/check-final.txt`. |
| `npm run test:e2e` | Passed | 9 Chromium tests, including real source/backend and clearly separate synthetic UI fixtures. All 16 source labels/crops/new-piece totals asserted. The final CSS phone refinement passed 2 targeted real integration tests, then the complete 9-test suite passed again; log: `var/evidence/browser-final.txt`. |
| Actual camera/replay checks | Passed | PNG changes after rotate/zoom/pan; reset restores baseline; detached and attached replay return exact settled pixels. |
| Real assisted worker | Passed, result `needs_review` | `var/evidence/integration/real-worker.json`: revision v3, six persisted events, duplicate submission same job, explicit source findings. v1/v2 results retained separately. |
| `uv run python tools/prepare_reference.py` | Passed on cached local assets | Reproduces labelled authored candidate after source/dependency hash checks. `var/evidence/integration/prepare-reference.txt`; this is not automatic inference. |
| Source/asset safety regressions | Passed | Concurrent writes, changed source, malformed/encoded PDF, invalid scale, traversal, missing/tampered dependencies/materials and missing receipts. |
| Durable recovery/cancellation | Passed in deterministic tests | Expired lease recovery, stale worker rejection, retained checkpoints, cancellation/retry. Actual process termination mid-render was not exercised. |
| Correction workflow | Passed in API and isolated browser tests | Immutable old revision, conflict, prior-value audit, invalid mapping, source finding retention; no fake human review of the target. |

Tests with synthetic scenes verify software only; they never constitute target reconstruction evidence.
Final warnings: Starlette's httpx test-client deprecation and a lazy Three.js viewer chunk above Vite's 500-kB
warning threshold. Neither warning was suppressed. The chunk is approximately 548 kB minified / 141 kB gzip.

## Browser evidence and performance limits

Desktop 1440×900 and phone 390×844 tested. Browser tool entry also inspected in the Codex in-app browser.
The standalone Browser plugin was not installed; the repository Playwright suite supplied repeatable testing.

- `var/evidence/browser/`: lookup, source found, early build, detached/attached callout, review, final candidate,
  phone layout and performance record.
- `var/evidence/browser/steps/`: all 16 source/render comparisons; `revision.json` identifies revision v3.
- `var/evidence/browser-v1/`: preserved pre-correction browser evidence.
- `var/evidence/reconstruction/`: `agent-inspection-v3.json` records actual inspection of all 16 browser states with a changes-requested decision; enlarged original panels, authoring comparisons and bounded check outputs.
  Offline painter images have occlusion artifacts; actual Three.js screenshots are the browser comparison evidence.

Measured values are in `var/evidence/browser/performance.json`. The observed cached load is 1.619 seconds;
requestAnimationFrame cadence 46.04 FPS; reopened renderer geometry counts 55, 55, 55.
This is a local headless Chromium sample, not a calibrated GPU/orbit benchmark, complete GPU-memory leak test,
or cross-device performance guarantee. Safari, a physical touch device and actual physical construction were
not tested. Browser fixtures cover unavailable WebGL/missing geometry/processing failures without faking the target.

## Exact local startup

From this folder:

```sh
uv sync --extra dev
npm install
uv run python tools/doctor.py
uv run python tools/prepare_reference.py  # first setup or rebuilding the authored candidate
uv run python tools/dev.py
```

Open **http://127.0.0.1:5173**, enter **30669**, and open **Alternate aeroplane — booklet 02**.
API health: **http://127.0.0.1:8000/api/v1/health**. The launcher starts API, worker and web server;
Ctrl-C stops their process groups. `UV_CACHE_DIR=.cache/uv` keeps uv's cache project-local.
After setup, `.venv/bin/python tools/dev.py` is an equivalent startup path when sandboxed uv itself fails.

```sh
uv run python tools/check.py
npx playwright install chromium
npm run test:e2e
```

## Remaining work / next executable action

Inspect the source-specific review findings alongside the saved v3 comparisons. Complete independently
supported connector metadata and narrow-phase intersection checks, resolve the remaining source ambiguities,
and use revisioned corrections for any changes. Do not promote the current candidate solely because its
software tests pass. A real authorized provider adapter, clean-source automatic evaluation and cost budget
are separate unfinished work; no automatic accuracy percentage can currently be reported. Human and physical
verification require actual external actions and remain `not_run`.

## Camera controls follow-up — 2 October 2026

User reported incorrect toolbar behavior while Reset view worked. Live-browser reproduction confirmed
that Zoom in moved the camera inside the final assembly. Both rotate and zoom handlers used a chained
Vector3 mutation which copied the orbit target into camera.position before calculating the offset;
the offset was therefore zero. Earlier screenshot-change checks missed this: a broken view also changes pixels.

Repair in `apps/web/src/camera.ts` and `components/AssemblyViewport.tsx`:
- Capture the camera-to-target vector before modifying the camera; preserve distance/elevation during rotation.
- Apply reciprocal zoom factors with model-relative minimum/maximum distances, shared with scroll zoom.
- Pan camera/target together by 10% of visible width, using the current camera orientation; add toolbar tooltips.
- Clear pending drag inertia using OrbitControls' public update API before buttons and reset, retaining the current
  displayed position. Reset retains the original framing and can cancel a moving drag.

Verification:
- `npm run check`: 18 frontend tests pass (6 new numerical camera regressions), TypeScript and production build pass.
  Evidence: `var/evidence/camera-check.txt`. Existing bundle-size advisory remains.
- Dedicated real-part browser regression passes: all six buttons, inverse pairs, 24 rotation clicks, 30 clicks at
  each zoom direction/limit, post-drag rotation, scroll then zoom/pan, and reset after a right-drag. Zoom limits
  stop additional motion; the model does not collapse or disappear. Evidence: `var/evidence/camera-browser.txt`.
- Rendered silhouette measured 35,874 pixels at reset, 54,384 after one zoom-in and 23,794 after zoom-out;
  pan changes horizontal centroid by about 69 pixels in the 692-pixel-wide canvas. Both rotations retain a
  bounded, visible model. Measurements and screenshots: `var/evidence/camera-controls/`.
- Live in-app browser also exercised all six controls and reset after reloading current code. A tab open during
  development retained the old handler until reload; users should refresh once to load the repair.
- Test development exposed an initial wait that completed before the lazy viewport mounted, capturing a temporary
  part thumbnail; now waits for the visible canvas and completion of geometry loading. The default 30-second
  test timeout was insufficient for the stress sequence under parallel rendering; this test allows 90 seconds.

This repair concerns camera interaction only. Source reconstruction, human review and physical verification
retain their previously documented incomplete status. No Python/backend changes were made in this follow-up.

Final combined rerun: `npm run test:e2e` — **10 passed in 47.2 seconds**, including existing
navigation, replay, persistence, mobile layout and error-state tests. Evidence: `var/evidence/camera-browser-full.txt`.

## Review panel usability follow-up — 2 October 2026

User correctly identified the repeated warning list as confusing. The API generated one default mapping
finding for each of the 32 physical instances; the UI discarded the displayed identities and rendered the
same message 32 times. The technical editor also lacked a clear explanation of its audience and purpose.

The panel now describes its optional reviewer/correction purpose, defaults to findings for the current
instruction, and supports All instructions. The real v3 revision retains **40 records**, displayed as
**9 grouped topics** when showing all instructions. Grouping uses kind, message and status; distinct
messages/statuses are never collapsed together or resolved. Individual record IDs, piece IDs, part/colour
values and source-page links remain expandable. Mapping findings with empty step_ids link to the step
that introduces that physical instance. Inspect links navigate the synchronized source/assembly and
select the relevant piece in the correction editor. Multi-piece details and Advanced corrections are
collapsed initially. Whole-assembly status remains separate from successful structural validation.

Loading, load failure with Retry, and a genuinely empty response have separate states. The empty state
explicitly does not establish verification. No backend findings, poses, source evidence, review status,
correction semantics or immutable revision records were changed.

Validation commands and evidence:
- `npm run check`: frontend numerical/grouping tests, TypeScript and production build.
  `var/evidence/review-check.txt`.
- `npm run test:e2e -- tests/e2e/review.spec.ts tests/e2e/viewer.spec.ts`: real v3 40-record/9-topic counts,
  32 separately expandable mapping records, final-step-to-first-step navigation, selected physical piece,
  current-instruction filtering, desktop/phone layout, load-failure retry, plus existing synthetic
  correction conflict/draft retention, new revision, navigation, persistence, and error-state checks.
  `var/evidence/review-browser.txt`. Synthetic fixtures prove UI behavior, not reconstruction accuracy.
- Rendered screenshots inspected: `var/evidence/review-panel/current-instruction.png`, `all-topics.png`,
  and `phone.png`. Screenshots show the actual candidate; all original reconstruction limitations remain.

Test development: exact getByLabel matching included nested select-option text, so the browser assertion
uses the accessible combobox role. The failure fixture originally answered only its first request with an
error, but React StrictMode performs a development remount; it now retains failure until explicit Retry.
Neither issue represents a fabricated service failure or a change to source findings.

Final review follow-up results: **21 frontend tests pass**, TypeScript/build pass (existing bundle-size
advisory remains), and **6 targeted browser tests pass in 6.7 seconds**. No Python changes or backend test rerun.

## Stable Next/Previous positions — 2 October 2026

Reproduced the reported 11 → 12 transition (printed main steps 7 → 8). At a 1440×1100 browser viewport,
Next and Previous moved from y=852.59375 to y=909.15625: **56.5625 pixels downward**. The extra part-list
rows expanded the grid. Shared piece poses were unchanged in the underlying snapshots.

The workspace now has stable row heights at desktop/tablet sizes and a stable active-panel height on
phones. Guide and parts panels scroll independently and can receive keyboard focus. Long content remains
available without stretching the workspace and moving navigation. Phone 3D height adapts inside its pane.
This change does not alter assembly snapshots or existing camera behavior.

Verification:
- Exact button rectangles match at **y=854 px** through 11 → 12 → 11 after repair at 1440×1100.
- All 16 instructions checked at widths 1440, 900 and 390; document-space button positions stay constant.
  Phone Guide/Pieces/3D tab switches also retain navigation position. No horizontal page overflow.
- `npm run check`: **21 frontend tests pass**, TypeScript and production build pass; existing bundle advisory.
- `npm run test:e2e -- tests/e2e/navigation.spec.ts tests/e2e/integration.spec.ts tests/e2e/viewer.spec.ts`:
  **7 tests pass in 28.6 seconds**, including real-source navigation/replay/persistence, phone viewport bounds,
  correction conflict handling and error states.
- Evidence: `var/evidence/navigation-check.txt`, `navigation-browser.txt`, and `navigation-position/`.
  `before-repair.json` preserves original movement; `positions.json` records repaired rectangles.
  Instruction 11/12 and desktop/tablet/phone captures retained. Desktop instruction 12 and phone screenshots
  visually inspected. Source reconstruction and acceptance limitations remain as previously recorded.

## Full-build playback — 3 October 2026

Added a separate **Play full build** button below the ordinary navigation, available at every instruction.
It restarts at the first snapshot and plays every instruction in order, using 1.8-second placement
animations and a 1-second hold per completed instruction. The existing Replay remains a 700 ms replay
of the current instruction. Pieces introduced together in one instruction animate together; existing
rigid subassembly attachments remain rigid. Motion is a visual aid, not a verified physical insertion path.

Full playback uses one camera framing covering all snapshot positions and the placement approach area.
Source crop, parts list, instruction selection and saved progress follow the current snapshot. Pause
freezes animation time and advancement; Resume continues, Stop settles the current snapshot. Next,
Previous, keyboard navigation, seeking or current-instruction Replay end full playback. Opening review
pauses it; a hidden tab also requests pause. Geometry loading/errors disable starting full playback.
Reduced motion uses completed snapshots with the hold between instructions, without moving pieces.
Finishing playback does not change candidate, review, geometry or physical verification status.

Verified with real source and local geometry:
- Full 16-instruction run, including both subassembly attachment steps, observed in order. Run duration
  46,724 ms including the tested pause; no page errors. Source crop/step IDs and introduced-piece quantities
  checked at each step. Reset final camera then pixel-compare with the manually selected final snapshot:
  exact match. Reload retains the final instruction and does not restart autoplay.
- During a mid-animation pause, screenshot stayed identical for 700 ms and the instruction stayed fixed.
- Phone: Stop cancels motion and timers; seeking cancels advancement; ordinary Replay still works;
  restarting begins at instruction 1; Next exits full playback. No horizontal overflow.
- Reduced-motion playback advances without animation and pauses on its current instruction.
- Missing geometry and unavailable WebGL keep full playback disabled.
- `npm run check`: **21 frontend tests pass**, TypeScript and production build pass. Existing bundle-size
  advisory remains. `var/evidence/full-build-check.txt`.
- `npm run test:e2e -- tests/e2e/full-build.spec.ts tests/e2e/viewer.spec.ts`: **7 passed**.
  `var/evidence/full-build-browser.txt`. The complete real-source test took 50.6 seconds including setup/reload.
- Evidence: `var/evidence/full-build/complete-run.json`, paused/callout/attachment/final/phone screenshots.
  Attachment and phone captures visually inspected. Tab-hide pause is implemented but not separately
  exercised by these tests. No automatic reconstruction or physical assembly acceptance is implied.

Related regression rerun: `npm run test:e2e -- tests/e2e/integration.spec.ts tests/e2e/navigation.spec.ts`
— **3 passed in 22.0 seconds**. Existing source/parts sync, callout Replay, progress persistence, phone
viewport bounds and stable Next/Previous positions remain verified. Evidence: `var/evidence/full-build-regression.txt`.

## Compact status — 3 October 2026

Removed the large candidate banner at the user's request. Origin/review status remains a small label
beside the title; coverage, authorship, human acceptance and physical status moved to the existing
collapsed Source, revision and checks section. No source/review data or verification states changed.

`npm run build`: TypeScript and production build pass; existing bundle-size advisory remains.
`npm run test:e2e -- tests/e2e/integration.spec.ts tests/e2e/viewer.spec.ts`: **6 passed in 14.9 seconds**.
Updated tests explicitly verify the compact label, absence of the old banner and retained expanded details.
Actual desktop and phone renders inspected. Evidence: `var/evidence/compact-status-build.txt`,
`var/evidence/compact-status-browser.txt`, and `var/evidence/compact-status/{desktop,phone}.png`.

## Source-aware placement animation — 3 October 2026

The user's instruction 9 report was correct: printed step 5 (official PDF page 4) puts the two red
plates beneath the white wings. The former universal +60 Y starting offset animated those plates
through the model. A callout arrow points to the destination; it must not be interpreted as a literal
physical insertion trajectory. All official step panels on pages 2–7 were inspected during this repair.

Implemented source/revision-bound, agent-authored presentation annotations in
`config/placement-30669-alt-02-v3.json`. These are source-assisted display directions, not automatic
reconstruction or verified physical assembly paths. Changed source/revision/active identities or unknown
steps fall back to in-place highlighting. Snapshot coordinates, source evidence and review status are unchanged.

`placement.ts` checks a proposed straight, axis-aligned approach against the real loaded part bounds.
The swept bounds cannot intersect an existing part beyond their final contact envelope. If that conservative
broad-phase check rejects an approach, the entire active group highlights at its final pose. It does not
try another guessed direction. This may reject physically possible routes through hollow geometry.
It does not prove narrow-phase clearance, connector engagement, physical feasibility, or final-pose validity.
Known underside annotations use -60 Y starts and move upward. Group members share the same offset and
retain final orientation; there is no unreviewed rotation or interpolation across the existing main assembly.

Actual 16-instruction browser audit:
- Instruction 9 translates from below. Red pixels' centroid moves from y=302.57 in an approach capture
  to y=273.93 at rest; the settled red-pixel count/centroid exactly match the initial final-state capture.
  Approach and final renders visually inspected side by side.
- Instructions 2, 5 and 8 use the blocked-approach fallback. This is conservative uncertainty, not a
  physical collision verdict. Instructions 1, 3 and 6 show starting pieces in place. Remaining steps
  translate from their source-assisted upper approach. Individual outcomes retained in `placement/audit.json`.
- Both ordinary Replay and full-build playback use the same policy. Unknown direction shows
  “Shown in place — follow the guide for attachment.” Initial pieces show “Start with the highlighted pieces.”
- Full 16-instruction playback, pause/resume, stop, manual cancellation, reduced motion and final snapshot
  equality pass. Full playback framing includes approach space above and below. Physical/candidate status
  remains unchanged.

Validation:
- `npm run check`: **26 frontend tests pass**, including lower-vs-upper travel, intervening obstacle,
  whole-group rejection, unsupported diagonal travel and source/revision pinning. TypeScript/build pass;
  existing bundle advisory remains. `var/evidence/placement-check.txt`.
- `npm run test:e2e -- tests/e2e/placement.spec.ts tests/e2e/full-build.spec.ts --workers=1`:
  **4 passed**. Complete playback test 50.3 seconds; all-step motion audit 17.4 seconds.
  `var/evidence/placement-browser.txt` and `var/evidence/placement/`.
- Test development: element-screenshot stability waits missed the 700 ms Replay while rendering in
  parallel. The motion capture now uses a page screenshot clipped to the viewport immediately after
  Replay. The old full-playback assertion expected the starting pieces to fly; it now explicitly checks
  the in-place policy, while the red-piece test checks visible travel. Final-state equality remains required.

Final related regression: `npm run test:e2e -- tests/e2e/integration.spec.ts` — **2 passed in 12.7 seconds**.
Source synchronization, callout final snapshots, camera controls, navigation, persistence and phone layout
remain verified. Evidence: `var/evidence/placement-regression.txt`.

## Open Studio redesign — 3 October 2026

Implemented the user's selected second concept: compact header, single left instruction/source/parts rail, large pale model stage, floating camera toolbar and one bottom navigation dock. Twelve main-step buttons preserve all sixteen microsteps and detached/attachment callouts. Phone panels retain common instruction context, keyboard tab navigation and stable controls. Review stays beside the model on wide desktops and uses a native modal dialog at overlay widths, with Escape, focus restoration and dismissal when inspecting a finding.

Real source crops, real individual LDraw geometry and material names remain authoritative. The generated concept is visual guidance only. No assembly identities, poses, source hashes, review events or provider behavior were changed. The renderer uses refined lighting, reduced ordinary edge opacity, per-part framing and a subtle presentation-only shadow receiver excluded from assembly bounds. Shadows are cached, and unchanged/paused/hidden views no longer redraw continuously; damping and playback still tick.

Validation on final code:
- Existing `.venv/bin/python tools/check.py`: 78 Python tests, generated-schema freshness, lint, 26 frontend tests, TypeScript and production build pass. `var/evidence/open-studio/full-check.txt`.
- Final `npm run check`: 26 frontend tests, TypeScript and production build pass. `var/evidence/open-studio/frontend-final-check.txt`. The existing large Three.js bundle advisory remains.
- Final `npm run test:e2e -- --workers=1`: **18 passed in 2.3 minutes**, no skips. Includes all real instructions, source/BOM synchronization, callouts, camera stress, playback/pause/stop/reduced motion, exact final snapshots, reviewer conflict/retry, responsive layout, grouped main steps and keyboard/modal semantics. `var/evidence/open-studio/browser-verified.txt`.
- Manual live inspection: desktop at 1488×1056, phone at 390×844, source and parts panels, detached callout, wide/overlay review; Inspect closes phone review and exposes its instruction. Final browser error/warning log empty. Independent code recheck closed all three prior P2 review/tab findings.
- Design comparison: selected-reference.png and desktop-final.png at matching 1488×1056; phone-callout-final.png, phone-guide-final.png and phone-pieces-final.png confirm final mobile spacing and legibility. Earlier rejected screenshots are retained and identified in `design-qa.md`.

Test repair evidence: the first broad run had two global timeouts and a 700ms replay screenshot arriving after motion had ended. Long-run timeout budgets were adjusted; navigation rectangle reads batched; placement uses the browser clock to capture a known 100ms rendered frame. Exact pixel assertions remain. Floating overlay UI is hidden only for renderer-only PNG comparisons. After the dirty-render gate, camera stress fell from 2.7 minutes to 17.9 seconds in this local run; this is test timing, not a general GPU benchmark. Final complete suite is green.

This validates the implemented UI and software flows. Assembly remains `needs_review`; automatic reconstruction accuracy, human acceptance, connector/physical validity and physical testing are unchanged. Safari, real-device touch and a complete screen-reader audit were not run. No deployment or publication performed.

## Brick Playground landing — 3 October 2026

Implemented the first selected landing concept: yellow hero, colourful brick-plane illustration, prominent
set-number search, direct supported-plane shortcut, and three illustrated workflow steps. The shortcut
resolves the real catalogue entry and alt-02 guide through existing APIs, retains unavailable-reconstruction
preparation, and never manufactures a scene. Results and errors receive focus; returning from the tutorial
focuses the found set, while entering the tutorial resets page scroll.

Four individually generated decorative images were converted to WebP (556,990 bytes total); originals
and selected reference remain in ignored evidence. Visible labels distinguish artwork from source/model
evidence. Inter is self-hosted under a landing-only font alias with its OFL license. No new dependency,
tutorial renderer/style change, assembly edit or external runtime font request was introduced.

Validation:
- `npm run check`: 26 frontend tests, TypeScript and production build pass.
  `var/evidence/landing-playground/check-final.txt`. Final CSS build also passes (`build-final.txt`).
- `npm run test:e2e -- tests/e2e/landing.spec.ts tests/e2e/starter.spec.ts tests/e2e/integration.spec.ts --workers=1`:
  8 passed in 19.2 seconds. Covers valid/malformed/unsupported lookup, direct example, unavailable-scene
  preparation, retry/cancel, result/error focus, return, all 16 real tutorial instructions, source/BOM,
  camera/callout/review, reload and resume. `browser-final.txt` in the same evidence directory.
- Focused responsive/shortcut rerun: 3 passed in 3.8 seconds (`responsive-final.txt`).
- Browser widths 1199, 768, 390 and 320: no horizontal overflow; images load, search stays visible and
  How it works reaches the explanation. Manual desktop/tablet/phone, lookup response and tutorial entry
  inspected. Final captured browser error/warning log empty.
- Paired comparison with the chosen reference passed. Fixed initial headline/image crowding, tablet
  cropping and small-phone caption overlap. `design-qa.md` records iterations and intentional differences.

Limits: viewport-emulated Chromium only; Safari, physical phone touch and full screen-reader audit not
run. Existing Three.js bundle advisory remains. Backend/Python implementation unchanged and its tests
were not rerun for this frontend-only slice. Source coverage, reconstruction accuracy, human acceptance,
connector/physical verification and automated provider status remain unchanged. No deployment/publishing.

## Yellow-blue consistency and substep fixes — 3 October 2026

Applied the selected Brick Playground palette and self-hosted font across the tutorial header,
instruction context, navigation, mobile tabs, reviewer heading and preparation workflow. Neutral
source/model surfaces and actual LDraw colours remain legible. Find my set now opens a compact
native booklet dialog with a yellow heading and blue tutorial action, bounded phone scrolling,
keyboard focus wrapping, Escape/close and focus restoration. Malformed/unsupported lookup errors
remain inline. Dismissed asynchronous work cannot reopen the tutorial, disable the next lookup or
overwrite its error; server-side preparation remains resumable.

Reproduction found a 52.8px downward shift in Step 3's substep buttons/source panel at 1440px,
caused by longer Attach copy. Invisible, aria-hidden sibling text now reserves the actual required
height without truncating instructions; phone context also reserves room. Part 1/Part 2/Attach use
shared immutable snapshot bounds for framing and lighting, preserving manual orbit between siblings.
The attachment's true geometry still moves to its authored pose; its camera no longer jumps.

Replay was firing, but starting-pieces/blocked-approach steps had only a subtle 700ms outline.
These now give two visible pulses over 1.8s on the actual part surfaces plus explanatory status.
Original part materials/poses are restored exactly. The conservative path guard remains intact;
translated replay remains 700ms and full-build timing remains 1.8s per instruction. Reduced-motion
mode stays still and explains the result. Replay is disabled until geometry is ready.

Evidence and final check counts are recorded in PROGRESS.json and var/evidence/theme-consistency/.
No assembly/source data, human-review status, provider setup or physical-test status was changed.

Checks:
- Existing `.venv/bin/python tools/check.py`: 78 backend tests, schema freshness, lint, 26 frontend
  tests, TypeScript and build passed (`check.log`). `uv` could not access its global cache in the
  sandbox; the already-installed project virtual environment ran the same check script.
- Final `npm run check`: 26 frontend tests, TypeScript and production build passed (`frontend-final.log`).
- Full browser run: 23/26 passed. Three older test assumptions were corrected: wait for Replay to
  enter playing before waiting for idle; select visible instruction copy rather than hidden sizing
  paragraphs; assert Replay disabled when the synthetic fixture deliberately has no geometry.
  All seven tests in the three affected files then passed (`updated-regressions.log`). All 26 unique
  browser tests have passed, with no skipped coverage. Original failure log retained.
- New checks: desktop/phone dialog focus cycle, Escape/restoration, 320px fit; delayed-request
  dismissal; exact substep/panel/control rectangles across 1440/900/390/320px for Steps 3 and 4;
  actual camera frame stability/manual orbit; rendered replay pulses, exact final PNG restoration,
  reduced motion. Existing all-16 motion-outcome and full-build checks pass.
- Manual live inspection: final popup, Step 3/Attach, replay status, desktop review and 390×844
  phone Attach. Final browser error/warning log empty. Screenshots in theme-consistency directory.
- Independent code review found the pending-dismiss issue; corrected and independently rechecked.

Limitations: Chromium viewport emulation, not physical-device/Safari or complete screen-reader testing.
Existing Three.js large-chunk build advisory remains. No deployment or publication performed.

## Ten-set release audit — 3 October 2026

See TEN_SET_RELEASE_REPORT.md and TEN_SET_SOURCE_MATRIX.md for the complete measured matrix.
Actual app/API audit: one candidate available, nine unsupported; zero accepted tutorials; automatic
conversion503provider_unavailable. Selected3simple/3medium/4complex sets were all exercised. Four
selected official PDFs downloaded/rendered176pages; six rejected by the existing20MiB cap. No source
limit/catalogue/provider was changed and no missing model was substituted.

Production-preview native Apple M3/Metal: desktop59.86 actual render submissions/s, GPU mixed-workload
p951.617ms, cold-HTTP workflow2.395s/warm0.922s. Phone emulation on the same GPU59.73/s and GPU p951.248ms;
physical phones untested. All16microsteps exercised, five reopen cycles stable, disposal counts0/0,
and stationary idle0render submissions. Software fallback desktop26.68/s misses30FPS; report separates
that SwiftShader result from native GPU. VRAM bytes/utilization not measured. Performance is one32-piece
candidate, not evidence of large-set rendering or reconstruction correctness.

Checks:78 Python +26 frontend tests; schema/lint/typecheck/build pass;27 browser regressions pass.
Two opt-in benchmark cases are skipped in normal suites and passed separately in bothsoftware/native
profiles (four runs). Evidence:var/evidence/ten-set-release. Full-source/model/human/physical acceptance
remains unchanged and blocked as recorded. No production deployment/publication performed.

## Bounded ten-set source preparation — 3 October 2026

Authorized limits and reliability changes completed. The current catalogue resolves all ten selected
sets and19observed official booklets. Fresh worker jobs using private source snapshots prepared all
2,231pages; finalpage API checks passed19/19, including indices above249. Real42171 cancellation retained
25verified pages; retry completed360pages without rewriting the first retained page.

Configurable256MiB/1000-page budgets retain24MP/page,150MP/batch,1.5GiB child memory and60CPU/90wall seconds.
Source checksums, cancellation, lease heartbeats, output quotas and manifest-only page access remain
bounded. Three independent review findings were fixed:static access bypass, initial source identity
race, and changed-source resume poisoning. Reviewer independently reproduced their resolution.

`.venv/bin/python tools/check.py`:108backend tests,27frontend tests, schema/lint/typecheck/build pass.
Full browser suite:28passed,2opt-in performance cases skipped; final wording recheck:1passed. Actual
booklet selection/prepared state inspected on desktop and mocked mobile lifecycle tested/inspected.
Evidence and per-set totals:[LARGE_SOURCE_PREPARATION.md](LARGE_SOURCE_PREPARATION.md), with raw receipts,
source outcomes, livejobs, cancellation events, browser results and screenshots in
`var/evidence/large-source-pipeline/`. Original smaller-limit audit is preserved separately.

Source preparation is passed; nine new3Dreconstructions remain unavailable. Existing30669candidate
and all assembly acceptance fields are unchanged. No new GPU workload, automatic-conversion accuracy,
human acceptance, physical-build result or public production release is claimed.

## Actual ten-set construction attempts — 3 October 2026
Fresh PDF-assisted construction was attempted for 3 small, 3 medium and 4 large sets. Eleven partial candidates passed structural/provenance checks and actual native-GPU browser rendering; all remained incomplete and needs_review. Zero complete or accepted tutorials, zero unassisted automatic conversion runs. The final browser pass was 11/11; the software check passed 108 backend and 27 frontend tests plus lint/schema/typecheck/build.

Native Apple M3 orbit rendering was 59.83–59.97 frames/s, HTTP-cold prepared-candidate loading 0.929–1.618 seconds, and sampled mixed-workload GPU p95 0.904–3.106 ms. Scope is only 3–66 real pieces per candidate; full-set GPU/VRAM and full 100-page construction latency are not established. Source-versus-render review found real assembly failures despite renderer passes.

Full outcomes, denominators, overlapping authoring intervals, exact evidence and blockers: [TEN_SET_CONSTRUCTION_BENCHMARK.md](TEN_SET_CONSTRUCTION_BENCHMARK.md). Production catalogue and existing30669alt02 scene unchanged.

## Cloud/batch checkpoint — 3 October 2026

See [CLOUD_RELEASE_REPORT.md](CLOUD_RELEASE_REPORT.md) for the current implementation, exact cloud endpoints, 19-booklet inventory and incomplete acceptance gates.

159 backend +34 frontend +31 browser tests pass; three opt-in benchmarks skipped. The full browser suite used isolated artifacts after earlier overlapping runs collided. A real source-panel collapse during Part/Attach was repaired; no physical assembly claim follows from layout tests. Exact frozen-snapshot playback assertions remain.

Public Cloud Run desktop/phone browser checks pass, private preview rejects anonymous traffic, authenticated proxy works, persisted requests were read back from the dedicated requests database, and no PDF or crop bytes were requested by the public UI. Existing Krishi spec/generation and default Firestore configuration are unchanged. Website code is live; zero tutorials are approved/published.

Fresh automatic pilot:2/12 main steps,5 pieces,16 model calls/781.253 active seconds including development retries. Complete-set latency and native-GPU measurements remain unestablished. The deterministic assembly-checker registry is empty and fails closed; all other18 jobs stay queued behind the pilot gate. This does not meet full reconstruction or end-to-end accepted-content pipeline acceptance.

### Resume and context-input repair

Verified actual restart from the saved two-panel checkpoint. First call reproduced attachment/tile ambiguity; second used bounded hash-checked Subpart definitions and preceding-page context. It still blocked on attachment offset/height, so no additional panel or tutorial success is claimed.161backend tests, schema drift check and changed-file Ruff checks passed; frontend was unchanged. A wrapper/subpart tamper-and-budget regression and resumed cross-page image-order regression cover the repair. Raw calls and final metrics are retained in `var/evidence/engine-resume-result.json`; no cloud deployment/publication was performed for these local engine changes.

## Fresh engine playground — 3 October 2026

User command: `.venv/bin/python tools/engine.py enqueue --set 30669 --guide alt-02 --revision fresh-30669-01`.
Job: `61b5afbe8c8d4991a0fac863a9039a47`. Five engine passes, then stopped at the requested ceiling.
Official source SHA-256: `6cb3e669fef3662dfd498cba0e631f1d9ec082c2bf8c0fb0a0febe303680a6b6`.
Eight pages indexed, 12 main panels found. No authored assembly coordinates entered model context.

Implemented fixes: bounded verified individual stud-mesh landmarks; explicit seating-plane and image-relative
attachment-order guidance; visible/active piece semantics; known coverage before first successful proposal;
actual rendered source comparison before checkpoint advancement; isolated read-only engine preview with
verified source and geometry assets, correct font serving, candidate labels and viewport-preserving layout.

Iteration evidence:
- Attempt 1: outer sandbox denied Codex startup. Retried with required process permission, retaining the
  child read-only sandbox, disabled tools and no paid API fallback.
- Attempt 2: source indexed; instruction 1 blocked on relative offsets.
- Attempt 3: instruction 1 proposed, instruction 2 blocked. Independent mesh review found an 8-LDU seating
  rim gap (studs stopped 4 LDU below the socket); candidate quarantined.
- Attempt 4: regenerated seating gap resolved; first two panels independently checked for bounded visible
  layout/seating. Main step 3/5 microsteps/8 pieces reached, but its attachment was on the opposite wing to
  the printed sequence. Run cancelled and candidate quarantined. This is rejected coverage, not success.
- Attempt 5 (`codex-source-context-v6`): actual render gate rejected instruction 1's reversed intermediate
  attachment order. Final arrangement agreed with the model reviewer, but sequence did not. Raw draft has
  2 microsteps/3 pieces; current checkpoint remains 0/12 main steps, with no accepted scene. Human review and
  physical build remain `not_run`; no tutorial publication or general connector certification.

Verification commands/results:
- `.venv/bin/python tools/check.py`: exit 0; 171 backend, 34 frontend; schema, Ruff, types and build pass.
- `npm run test:e2e -- --workers=1 --output=var/evidence/fresh-30669-01/regression-browser`: exit 0;
  31 pass / 3 optional audits skipped. Existing reference UI regression coverage is separate from new engine accuracy.
- `node var/evidence/fresh-30669-01/portal-qa.mjs`: real preview at port4175; Chromium153.0.8010.12;
  1440x1000 desktop, 390x844 phone. Candidate seeking, source sync, camera state changes, replay, subassembly
  attachment, phone tabs and viewport fit exercised. Final blocked state displayed with no open-candidate
  action. No console errors, failed asset requests, framework overlay or blank page in final checks.
- Actual engine renderer exercised on the two-step snapshot and in attempt5; source/scene/PNG hashes retained.
- Independent gate audit verifies failed second-panel review leaves earlier checkpoint/scene bytes untouched;
  bad scene hashes, step counts/order and escaping screenshot paths are rejected.
- Final no-candidate scene-revision label follow-up: 5 preview API tests and production build pass.

Evidence root: `var/evidence/fresh-30669-01/`. Read `result.json`, `iterations.json`, `final-engine-report.json`,
`panel-gate-independent-audit.json`, `panel-gate-render-binding-probe.json`, assembly review JSONs, QA logs,
`attempt-3-browser/`, `attempt-4-browser/final-verified/`, and `portal-blocked-{desktop,mobile}.png`.
Raw model calls, proposals, rejections and actual gate renders remain under the private job directory.
Receipt totals exclude timing for the cancelled call; do not claim complete experiment latency from them.

Scaffold/software checks passed for exercised scope. Full automatic conversion is incomplete. The existing
PDF-assisted reference was not used as input or relabelled as engine success. Safari, physical assembly,
general connector/collision validation and numeric automatic reconstruction accuracy remain unverified.
The Browser plugin was unavailable; repository Playwright was used. No cloud changes were made.

Local restart: `npm run build`, then `.venv/bin/python tools/preview_engine.py 61b5afbe8c8d4991a0fac863a9039a47 --port 4175`.
Open http://127.0.0.1:4175. It shows the real blocker; previous rejected 3D candidates remain in evidence.

## Spatial correction engine — 3 October 2026

Implemented nominal connector-derived placement, source-camera fitting and per-instruction targeted repair.
The model selects real part/connector identities and source landmarks; deterministic code computes mating
poses and rejects unsupported/free/occupied contacts or incomplete/nonrigid groups. Accepted history is
immutable. Raw proposals, solved snapshots, source observations, camera/PNG hashes, reviews and every rejected
trial are retained separately. Source labels distinguish printed callouts from invented intermediate steps.

Six individual designs are supported: 3022, 13547, 35044, 3020, 3710 and25269. Individual mesh and full dependency
hashes are pinned. The 13547 regression derives originY16 from its true underside rim, correcting the oldY24
proposal; no target assembly coordinates are imported. The successful live trial happened to propose the
same poses as the solver (zero deterministic pose corrections); the corrected-run label refers to the
retained earlier trials and repaired source correspondence, not a claimed automatic pose edit in that trial.

Independent review found three concrete solver defects during implementation: hidden parts freeing studs,
ordinary additions escaping detached-group membership, and extreme coordinates overflowing grid arithmetic.
All were reproduced and repaired with fresh/resumed regressions. Recovery also verifies accepted evidence
before promoting a reviewed final-budget trial without more inference. Live provider testing exposed tuple
schemas using unsupported prefixItems; homogeneous tuples now keep their exact bounds via items schemas.
Schema rejection is classified as an engine error and no longer pauses unrelated jobs as a provider outage.

| Check | Result | Evidence |
|---|---|---|
| `.venv/bin/python tools/check.py` | Pass:225 backend,39 frontend; Ruff/schema/typecheck/build | `var/evidence/spatial-30669-01/final-checks.log` |
| `npm run test:e2e -- --workers=1 --output=var/evidence/spatial-30669-01/browser-test-results` | Pass:31;3 optional audits skipped | `browser-regressions.log` in same folder |
| Deterministic source-camera transport | Pass: actual matrices and PNG hashes; default render unchanged | `var/evidence/source-camera-20261003/verification.json` |
| Actual candidate portal desktop1440×1000 / phone390×844 | Pass: lookup, source crop, camera, replay, tabs; no console/network failures | `portal-qa.json`, `portal-step-1.png`, `portal-mobile.png` |
| Final blocked job with usable prior candidate | Pass: correct selected job and retained1-step candidate | `portal-final-qa.log`, `portal-final-status-desktop.png`, `portal-final-status-mobile.png` |
| In-app browser | Pass:30669lookup→open currentcandidate→rotate/reset/replay; retained visible tab | Same job/source/scene as saved portal evidence |
| Fresh automatic source index |8/8 pages;12 main panels | Retained jobc0c7e33c25164510a3179ffd346e2abe |
| Corrected automatic instruction1 | Pass limited source/nominal contact review:1snapshot,3pieces,RMS0.326px | `independent-review.json`; proposalc306309520ae4d77a447d07cd42fe22f |
| Instruction2 | Blocked:2trials;RMS27.21→7.76px, threshold4px | `result.json`; proposal69451c531c524ef5a5be037aad9f8a40 |
| Complete automatic booklet | Blocked:1/12main steps | Current job2ad572af542a40c1bdcf4b08a5899046 |
| General geometry/connector validity | Not run; nominal contacts and broad-phase candidates only | Spatial receipts and unchanged globalnot_runflags |
| Human review / physical build / publication | Not run / not run / not performed | No approval or publication claims |

The first run used three instruction1 trials, including its schema failure. A separate recorded continuation
allowed two further trials and reused only automatic source-index/rejected-proposal evidence, with no accepted
reference. It passed instruction1 on its first trial. The next instruction's own two-trial budget exhausted and
the worker stopped. The successful first-step camera uses six visible landmarks on the base and already seated
slope; the second slope's final pose is inferred from the official arrow. An independent agent recomputed the
fit and checked visible count/layout/seating and hash bindings, but did not independently redigitize the points.

Browser plugin skill was absent, so the repository's Playwright suite supplied reproducible desktop/phone QA;
CUA additionally verified the user-facing in-app tab. Software E2E is separate from full assembly accuracy.
No world pose is changed to make a camera comparison fit. No visual tolerance was relaxed, no rejected trial
was promoted, and no general collision, hidden-contact, human or physical correctness is certified.

## Assisted alpha pilot generation — 3 October 2026

Set **30669 / alt-02** reached **7/12 main instructions, 11 viewer snapshots and 19 physical pieces**.
Instruction 8 exhausted its five persisted trials on unresolved transparent clear versus transparent
light-blue colour identity. The selected official booklet has pale-cyan artwork but no colour identifier
or legend that settles this distinction. All five proposals returned no scene delta. Generation stopped;
no colour was guessed, accepted scene edited, exhausted counter reset or further reconstruction call made.
Independent inspection counted 32 pieces in the full booklet; instructions 8–12 and 13 pieces remain absent.

The candidate is an `assisted_alpha_continuation`, job `a5cc1e914bb84df2a211a52d62cbb281`, experiment
`alpha-30669-pilot-01`. It reuses the strict parent's automatic eight-page index and accepted first
instruction. Recorded agent assistance corrected instruction 2's near/far slope landmark IDs only;
assembly poses were unchanged. The parent `2ad572af542a40c1bdcf4b08a5899046` remains blocked at 1/12.
This is partial generation with recorded assistance, not unassisted conversion or a complete alpha tutorial.

- Source SHA-256: `6cb3e669fef3662dfd498cba0e631f1d9ec082c2bf8c0fb0a0febe303680a6b6`.
- Accepted scene SHA-256: `7ca4b36fd68cedf71d0036aa1206ccd6c1fccf95625d0264fc626b70b6485a58`.
- Alpha source-image policy: 8 px RMS / 12 px per landmark. All ten newly accepted snapshots also pass
  the strict 4/12 px limits: worst RMS **0.703443 px**, worst individual landmark **1.180446 px**;
  **zero relaxed acceptances**. The inherited first snapshot retains separate evidence.
- Runtime generation used 26 provider invocations and 2,038.327 active provider seconds. This excludes
  reused source indexing/first-step work and independent review; it is not full-booklet completion latency.
- Independent source review confirms the accepted prefix's visible layout, printed callouts, persistent
  physical identities and counts. Some retained instruction 3/4 text still uses technical axes.

Engine changes expand individual-part connector metadata to 18 designs through 19 hash-pinned records,
with 141 nominal frames. The original six records retain their semantics. Independent review covers
part-local geometry and supported stud/socket locations; it does not certify arbitrary contacts, global
collisions, placement paths, strength or a physical build. The report now preserves assisted lineage.

Repeated near/far correspondence mistakes also exposed missing accepted camera context in subsequent
proposal prompts. A bounded helper now verifies accepted receipt/scene/source/image hashes, camera
dimensions, visible-instance identity and individual geometry before supplying six named world/image
landmarks from this candidate's last snapshot. It passes 31 focused tests and an actual-candidate offline
probe. It was integrated after the running instruction had already claimed its work, so **no subsequent
live reconstruction measured its effect**. Camera-boundary probing remains a separate diagnostic, not a
new production rejection gate. An administrative claim pause was cleared after generation blocked;
it was not a provider outage, and the final job has no active owner or provider pause.

Actual portal QA found full-build playback cancelling when a streamed snapshot temporarily made the
renderer unavailable. The viewer now retains playback/pause intent, waits for geometry readiness before
replay, and pauses with an explicit retry on chunk-load failure. Stop and manual seeking remain available.
Two new browser regressions use original synthetic transport fixtures and are separate from reconstruction
evidence. Existing and new software checks pass:

| Check | Result | Evidence under `var/evidence/pilot-alpha-30669-01/` |
|---|---|---|
| `.venv/bin/python -m pytest` | 279 passed | `backend-final.log` |
| Ruff and generated-schema check | Passed | `software-checks-final.log`, `generation-result.json` |
| `npm run check` | 41 frontend tests, typecheck and production build passed | `frontend-checks.log` |
| `npm run test:e2e -- --workers=2` | 33 passed; 3 opt-in audits skipped | `e2e-regressions.log` |
| New streamed-playback regressions | Both passed, also included in full suite | `tests/e2e/chunked-playback.spec.ts` |
| Independent source/BOM review | Accepted prefix passed; full booklet blocked | `independent-final-source-review.json`, `independent-booklet-bom.json` |
| Independent connector audit | Passed for stated part-local scope | `connector-independent-review.json` |
| Actual partial-candidate desktop/phone QA | Passed: all 11 available snapshots | `portal-qa.json`, `portal-desktop-instruction-11.png`, `portal-mobile-3d.png` |

Actual QA used the rebuilt portal at temporary loopback port 4185, without request mocks or new provider
calls, in headless Chromium at desktop 1440×1000 and phone 390×844. It exercised all 11 snapshots, four
callout snapshots, two attachments, source synchronization, active piece IDs, the 19-piece list, camera
controls, reduced-motion replay, full playback from the final snapshot, pause/resume/stop and saved-position
reopening. Primary and portal agents inspected the actual desktop/phone captures. The source and accepted
job remained unchanged. Safari, real touch hardware and animated placement/collision paths were not tested.

There were zero application console errors and zero HTTP error responses, with four GPU readback warnings.
Chromium also reported 242 cancelled DAT requests across 81 URLs during navigation. Every affected asset
had a successful readback with the expected provenance hash; 49 URLs additionally had recorded completed
browser-load body hashes. The cancellations remain in `portal-qa.json` and are not relabelled successful
requests. Earlier selector, playback and resize-timing QA failures were preserved. The final phone check
waits for ResizeObserver layout to settle rather than accepting a stale desktop-sized canvas measurement.

All task web services were stopped. Final `lsof` checks found no listeners on 4175, 4185, 5173, 8000 or 8002;
the preview's shutdown also passed its connection check. `final-state-check.json` verifies unchanged job
and accepted scene hashes, no active job owner and no provider pause. The full reconstruction remains
blocked regardless of the successful software/portal checks.

Detailed candidate lineage, attempts, fits and timing are in `generation-result.json`. The handoff and
local startup command are in `var/evidence/pilot-alpha-30669-01/README.md`. Rejected proposals, gate renders
and receipts remain in the job directory. Browser regressions reused some legacy evidence paths; the
previous captures were preserved and both generations are copied into this pilot's evidence directory.

Software checks do not establish full reconstruction accuracy. Human review and physical build remain
`not_run`; global geometry/connector checks remain `not_run`. No tutorial was approved, published or
deployed. The colour ambiguity requires additional permitted evidence or an explicit representation of
unresolved materials for alpha candidates; reducing image precision cannot resolve it.

## Ten-set playable alpha campaign — in progress, 3 October 2026

The new `alpha_fast` mode uses compact direct part/pose patches from selected official PDF page batches.
It accepts source-supported material/pose/camera uncertainty as notes, while still requiring real individual
DAT geometry, pinned source bytes, stable physical IDs and truthful provenance. Strict jobs and their
exhausted counters retain their previous semantics. No approval or publication is granted.

The source-assisted complete plane has 12 main instructions, 16 snapshots and 32 physical pieces. Its
scene digest is `16c2239b5bc1ad616dbd621eebef1f6f255c6a9c0a24daa1081338a278eaf818`. The original
19 pieces and 11 snapshots are unchanged; 13 source-derived pieces and five snapshots were added.
Clear/light-blue material, grey edition, tail offset and camera approximation remain explicit review notes.
Actual Three.js renders and source comparisons are in `var/evidence/alpha-ten-set/30669-alt-02/`.

The multi-job local alpha portal passed an actual desktop/phone check for the plane: every snapshot,
source synchronization, BOM, cameras, callouts, playback, restart, resume and reopen. All ten set lookups
and 13 guide identities were checked for correct own availability; this does not mean all models exist.
Structured uncertainty notes and assisted lineage are displayed. There were zero JavaScript/HTTP errors.
Rapid navigation cancelled 277 DAT requests across 106 URLs; subsequent body readbacks matched provenance,
with no unresolved assets. Four GPU readback warnings were retained. Port 4195 is closed, and the plane's
job row digest was unchanged. Evidence: `var/evidence/alpha-ten-set/portal/README.md` and `portal-qa.json`.

Backend integration review reproduced an aggregate 512-resource rejection despite individually bounded
valid designs, and a failed assisted import leaving a live global lease. The fixes retain per-design
dependency/hash/path verification, count the actual union under 8192-resource/256-MB assembly bounds,
and release a failed import's lease without discarding old counters or frozen inputs. A real synthetic
514-design test reproduces the old rejection and verifies the union count and tamper rejection; import
failure tests prove other jobs can claim and partial scenes cannot claim full source coverage.

Full software regression results, subsequent model generation and final multi-model portal checks will be
recorded at the next checkpoint. Current status: one complete assisted model; the ten-set campaign remains
in progress. Human review and physical build remain `not_run`.

### Ten-set alpha checkpoint: source covers and complete go-karts

Three full booklets across two sets are registered: plane 30669/alt-02 (12 mains,16 snapshots,32 pieces) and both 60400 booklets (25/28 numbered section/main pairs,33/36 snapshots,53/60 individual components). Figure components are decomposed, so these counts are not retail inventory counts. The go-kart candidates preserve real source-page hashes and individual geometry; portal inspection is in progress. All three are explicitly PDF-assisted, needs_review, with human/physical checks not_run.

Actual first-six-page inspection of 42171,21343 and10316 booklet01 confirmed noninstruction pages. Their false whole-model blockers were corrected in separate agent-labelled receipts, removing only blockers while retaining source observations, all five original proposal attempts and frozen policy. Normal accepted-batch replay advanced six pages with inference disabled. This is agent assistance, not automatic success or assembly approval. Evidence: `var/evidence/alpha-ten-set/source-cover-review/`. The campaign resumed with authored-prefix sets excluded.

Latest full backend run:378 passed,zero failures/errors/skips; Ruff,schema regeneration check and git diff whitespace checks passed. Evidence: `var/evidence/alpha-ten-set/backend-after-cover-correction.xml` and `.log`. Existing frontend and browser regression evidence remains separately recorded.

42163/main is now source-assisted complete and registered:57 numbered mains,88 snapshots,195 pieces (48 tread links),44 real designs,209 selected geometry dependency resources,all76 official pages reviewed/hash-bound. Source comparison and frozen canonical scene: `var/evidence/alpha-ten-set/42163-main/`, SHA29e9ba62ee348e2d9b7de36fa669dbd2d288d951400626574d9c954f932d4a6d. Geometry/connectors/camera/human/physical certification remains not_run; hidden seating and track articulation remain disclosed alpha notes. Actual portal QA is running.

Both 60400 booklets pass actual desktop/phone portal QA against frozen real transport:69 snapshots, all source crops/pages/active IDs and BOMs, six camera controls/reset/replay, full playback with pause/resume and saved-progress reopening. Completed job rows are byte-hash unchanged. Zero application errors/HTTP errors/mutations/external requests.564 DAT request aborts during rapid navigation are retained;283 distinct resource URLs read back and hash-matched to actual provenance. Evidence: `var/evidence/alpha-ten-set/kart-portal/portal-qa.json`. The two preserved initial failures were QA adapter field/order assumptions, corrected without model mutation. Latest frontend45 tests and typecheck/build passed after final-assembly label/count correction.

42163 actual portal QA passed:all88 snapshots and real source/active IDs/BOM transport,57 numbered mains,195 parts, six camera actions/reset/replay, full playback with pause/resume, phone panels and reopening. Source-assisted scene/job unchanged by row hashes. Zero application JS/HTTP errors or mutations/external requests.119 distinct aborted DAT resource URLs read back with exact provenance hashes. Root viewed final source comparison, desktop and phone frames. Evidence: `var/evidence/alpha-ten-set/bulldozer-portal/portal-qa.json`. Full assembly/camera/mechanical correctness remains unverified.

After completed-model portal QA, the owned browser and temporary4195 preview were stopped. Listener checks confirmed4175,4195,5173,8000 and8002 closed. Generation and bounded source-authoring work remain in progress; this is not a full ten-set completion claim. A focused synthetic cumulative-booklet regression additionally confirms assisted registration binds the current source/numbered section count while retaining the first primary source and all inherited snapshots.

Fast-alpha runtime change:actual Astra/medium source batches hit the300-second bound. Future calls were explicitly changed via fenced, audited checkpoint runtime overrides without altering job config/fingerprint, source/scene or trials/budgets. The real gpt-6.1-sol/low invocation then failed in2.71s with CLI400:that model is unsupported for this ChatGPT account. Its attempt/raw invocation remains retained. The global pause was cleared only after identifying that model-specific configuration error; all remaining booklets now use the already working gpt-6-astra at low effort. New classification unsupported_model blocks its affected job immediately without retrying five identical calls or pausing unrelated jobs. Timeout/interruption evidence now preserves requested runtime and actual child termination, even without structured output. Focused tests pass; full backend before the classification addition386 passed. No API fallback or attempt reset.

Five complete set samples (six booklets) are now registered:30669,60400 (both),31134,42163,76920. Shuttle canonical SHA526913601ed48d8bf279f31686185af9f748e3f0d5e8832d5d23367490cb77f5 (48 main keys/78 snapshots/144 components); Mustang canonical SHAbb5a443283e0e7294efd806741a1670b75c11523332d1ec6f81e88bdf32e6dc4 (109 main keys/151 snapshots/357 component instances, remaining retail-count discrepancy disclosed). Actual portal QA is in progress; do not claim completion yet. The automatic21343 call was interrupted cleanly with fifth consumed trial retained; all further large-source work uses explicit assisted lineage. Frozen parent candidates remain unchanged. The prior391-test full backend pass is retained in backend-final.xml; subsequent reporting fixes passed48 focused checks, and grouped uncertainty import/resume now passes its regression. That real import failure preserved the old prefix and released its lease before retry.

Actual shuttle/Mustang portal QA now passed all229 snapshots, source crops, physical IDs, new/full BOM, camera/replay, full reduced-motion playback/pause/resume, phone panels and revision reopen. Both job rows remained byte-equivalent under canonical hashes.706 navigation-cancelled requests remain recorded; all349 unique URLs (including chunks/material) were read back and matched real frozen pins. The first DAT-only adapter failure is retained separately. No JS/HTTP errors, mutations or external requests. Root visually inspected both final desktop screens and Mustang phone3D. Evidence:var/evidence/alpha-ten-set/shuttle-mustang-portal/portal-qa.json. Temporary4195 and owned browser stopped after QA.

The frozen Tiger (31129/booklet-01) is registered with canonical scene `99447f7013c463bdbf4a1dec8ed70c96dc7499a15e5589a4dcbcde02b66bf8d0`: 314 numbered section/main pairs,437 snapshots,756 geometry components and all132 official page pins. Actual Playwright CLI portal QA passed all437 snapshots/source panels, active/new/full BOM views, camera controls, replay, complete playback pause/resume,390px phone tabs and revision-scoped reopen. No application/HTTP/console errors, external requests or mutations were captured;1345 navigation-cancelled requests remain recorded with283 unique resources read back against frozen hashes. All17 persistent job rows matched before/after. The initial browser open logged a missing favicon404 outside the model QA capture. Prominent body/head/neck seating gaps and the +1 inventory discrepancy remain visible alpha limitations; this is not a geometry/connector/camera agreement, human review or physical-build pass. Evidence: `var/evidence/alpha-ten-set/tiger-portal/portal-qa.json`.

The rendered follow-up check reproduced the source-coverage display-string/raw-enum wiring bug. The separate raw flag is now passed from App to ViewerWorkspace. Actual shuttle/Mustang final footers and their unnumbered instructions passed the repeated Playwright CLI check (`tiger-portal/coverage-copy-qa.json`); the failed first check is retained. TypeScript/build passed after this edit. Persistent jobs remained unchanged through the follow-up.

2026-10-04 alpha continuation: current backend suite passed392tests (`var/evidence/alpha-ten-set/backend-complete-current.xml`); latest frontend45tests and TypeScript/Vite build remain passing. Notre-Dame393numbered instructions/4421components (4381source units +40 hinge expansions) is frozen/registered with all292official page hashes. Root inspected its final source comparison: recognizable cathedral with materially rough seating, no accuracy certification. Rivendellbook01 full246 numbered keys/278snapshots/1233components is frozen/registered, canonicalSHA875043b88d3713fa98baccf93aa4d4cdb9b8828686e3e13b0a6cfceae877d27b. Root reviewed all184source pages and actual draft/frozen Three.js views. Long-part axes, palette, turret-quarter centres and tower translation were corrected; seating, relative proportions and mould/quantity uncertainty remain substantial. Original10Frodo descriptors and2snapshots are exact. Canonical candidate renderer hash now preserves signedzero by sending original UTF-8 JSON to Python; exact frozen Rivendell render SHA matches candidate. Portal QA of both new booklets is running in a temporary read-only loopback session. Neither artifact claims human/physical/connector/camera review.


2026-10-04 large-candidate integration checkpoint: nine selected sets are complete assisted alpha candidates across eleven booklets; Rivendell booklets02/03 remain in progress. F1 is frozen at canonicalSHA f6325768a2ad0f32918a774a79705f8880f2d4e95ed43a268d0123cdf2efff14 (461 numbered mains,462 snapshots,1648 geometry components representing1640 supplied units); Viking Village is frozen at171cdbe13602bfff3b411580003c1bea4b9f21079fec1cc14a3a7860dde3dc6d (432 numbered mains,444 snapshots,2178 geometry components). All360 F1 and252 Village official pages are hash-bound in their completion reports. Their source-derived poses remain coarse, with visible overlaps and seating gaps.

The first large-model portal run failed with ECONNRESET while fetching Notre-Dame chunk23. The process was still alive at98.5percent CPU/approximately1.7GB RSS, repeatedly parsing unchanged checkpoint/scene JSON; it was not an observed OOM kill. The failed report and server log are retained in remaining-portal/portal-qa-first-failed.json and server.log. Root cached job reads against SQLite mainDB/WAL file identities and validated scenes against confined scene-file identity plus the current job object. Live official PDF/receipt checks remain required. Regressions exercise checkpoint changes without updated timestamps, modified scene bytes and modified official PDF bytes against warmed caches. Actual warm full-campaign status requests took22.42/21.86ms; selected Notre-Dame status1.42–2.25ms and860336-byte source-page delivery4.76–7.16ms, after a9.51-second cold campaign validation. This is local timing evidence, not sustained load certification (remaining-portal/preview-response-timings.json). A new real portal QA run is in progress.

Assisted import now reads report uncertainty_notes and alpha_notes in addition to the existing formats. Fenced same-canonical-scene note refreshes merge/de-duplicate warnings while retaining candidate hashes, config/fingerprint, original exhausted trials and leases. The four actual existing candidate refreshes are recorded in assisted-note-refresh.json. Regressions cover both note formats, preserved exhausted5-trial budgets and repeat-call idempotency. Current complete backend suite:396 passed,one existing Starlette warning (backend-latest.xml/log). Ruff, generated schema drift and git diff whitespace checks passed. Latest viewer45 unit tests and TypeScript check pass after static whole-assembly outlines are suppressed only for inspect snapshots that add no pieces; actual rendered follow-up remains pending.

Large renderer normalization now reads the original hash-pinned scene directly in Python and writes canonical scene/camera files to a uniquely created private temporary directory. Only small integrity metadata crosses stdout; Node verifies sizes/hashes and removes only its own temporary files. The production timeout is60seconds with SIGKILL and bounded diagnostics. Actual frozen44.9MB Viking default and supplied-camera renders passed with exact canonical scene SHA/no console errors; normalization took6.15/5.63seconds,stdout345/409bytes. Three render attempts were used, including the retained first camera comparison failure caused only by property ordering. Final comparison ignores object property order while checking all values. Focused V1/signed-zero, stale-input rejection, actual timeout/temporary cleanup and camera-value checks passed. Evidence:render-normalization/verification-report.json. This does not certify camera fitting, connector validity or assembly correctness.


Independent cache/note review reproduced an actual legacy checkpoint shape from the frozen plane:four historical uncertainty records existed without an alpha_review_notes key. Root corrected both append import and same-scene refresh to merge both historical fields before new report notes. The independent in-memory replay now exposes all four original IDs plus the new warning through the actual preview.status formatter, keeps the exact candidate/trials, releases its lease and makes no second claim on repeat. Exact live-row hashes match before/after; no live DB write was performed (cache-note-review/legacy-note-fixed-evidence.json and review-report.json). New same-scene and prefix-import regressions pass.

Current post-compact full backend suite:398 passed,one existing Starlette warning (backend-post-compact.xml/log). New assisted scene persistence uses an opt-in compact atomic JSON writer; original frozen scene files are unchanged, and parsed canonical imported scene hashes are regression-checked. This reduces formatting expansion without increasing the existing256MB candidate limit. Focused runner/campaign checks33 passed (compact-import-tests.log). Root also directly inspected the official Rivendell book03 joining step405 on source page319:it shows tower01 at left, hall03 in the middle and pavilion02 at right. The inherited earlier snapshots remain exact; the source-supported descendant assembly may reposition the prior modules.


Actual four-model portal QA checked every1,577 snapshot for Viking Village444, F1 462, Notre-Dame393 and Rivendellbook01 278; correct source crop/page/active IDs, introduced/full BOM, camera/reset/replay, full reduced-motion playback with pause/resume, phone3D/Guide/Pieces and revision reopening were exercised. There were zero application/console/HTTP errors, mutations or external requests, and all17 job rows were exactly unchanged. The initial end-of-run network audit failed because14 late ERR_ABORTED events arrived after its readback URL list was captured. That original failure remains in portal-qa-second.json. A separate actual follow-up waited for the final view to finish loading and read all14 late URLs with their real frozen provenance hashes. All1,505 navigation-cancelled requests now have coverage across806 unique successful hash-checked readbacks; they remain recorded as cancelled requests, not successful original loads. Combined report:remaining-portal/portal-qa.json; late-abort-verification.json and job-stability-second.json retain the additional proof. This is functional software verification, not physical/source-angle/connector correctness.

After the bounded source-copy/overview change, the final frontend check passed45tests,TypeScript and Vite production build (overview-final-frontend-checks.log; existing587KB chunk warning retained). Actual rebuilt-portal follow-up passed on frozen Viking Village and Rivendellbook01: static full-assembly boxes are removed from inspect snapshots, ordinary build outlines remain, source-complete details no longer contradict coverage, all23/12 disclosed warning texts are visible, and desktop/phone views render without application/console/HTTP errors.895 navigation cancellations remain recorded;420 unique assets read back with their real frozen hashes. All17 job rows are still exact (overview-qa.json,job-stability-after-overview.json). Root inspected the improved real desktop/phone captures; substantial model seating/proportion gaps remain explicitly unverified.

Rivendell booklet02 is now frozen and registered at canonicalSHAe78447009a42d5839953f379e3f7825be86bea7e4c8cd59f7623f9fb5d68786e:242 current-source numbered mains,255 current-source snapshots,533 cumulative snapshots,2611 geometry components,201 individual designs/663 dependency files. Root independently rechecked all164 official-page pins, exact original1233 descriptors/278 snapshots with canonical signed-zero comparison, source receipt/hash and individual asset closures. Original job configuration/fingerprint and consumed trials are preserved. Root actually inspected the final official-source/Three.js comparison; recognizably coarse river/tree/pavilion module with substantial terrain/bridge/roof/seating differences remains needs_review. Three full render/correction iterations and six representative frozen snapshots are retained. No human, connector or physical certification. Evidence:10316-booklet-02/root-validation.json,registration.json,completion-report.json and representative-render-addendum.json. Actual portal QA is in progress.

Actual Rivendellbook02 portal QA passed255 current-source snapshots plus2 inherited-prefix boundary views (257 actual views), every533 real transport snapshot/hash,242 selected-source numbered mains,2611 introduced-history components and all visible uncertainty notes. Source panels/active IDs/new/full BOM,cameras/reset/replay,31-instruction representative playback with pause/resume/stop,phone3D/Guide/Pieces and revision reopening were checked. Full533-step playback was not repeated; the exact278-step inherited prefix already passed fullbook01 playback. No app/console/HTTP errors, mutations or external requests. All17 job rows were unchanged;1093 navigation-aborted requests remain recorded with374 unique resource URLs successfully read back against frozen hashes. Root inspected actual final desktop and phone3D captures. Evidence:rivendell-portal/portal-booklet02-qa.json,job-stability-booklet02.json.

Final Rivendellbook03 source-assisted candidate is frozen/registered at canonicalSHA458d982e780e05e7a191c3fb468563c2a17b3ed9cf205ef5de2ee025b4889dbd (42,489,635 bytes):423 current-source mains,434 new-source snapshots,332 official-page hashes and3286 new geometry components. Cumulative967 snapshots/5897 components/911 numbered mains retain the exact previous2611 descriptors and533 snapshots, including signed zero and source records. Source405 joins the three modules in descendant snapshots; original parent arrays are unchanged. Root independently verified every frozen evidence/page/source pin and318 individual designs/933 closure files, and viewed actual finalv3 plus official page319. Coarse roof/trim/terrain/chair/rack seating, default-angle limitations and270-component retail discrepancy are explicitly retained;13 representative actual v3 renders were inspected with zero console errors. Individual geometry/structural evidence does not establish connectors, camera agreement, strength, human review or physical construction. All10 sets/13 selected sources now have full assisted alpha candidates; final portal verification is in progress.

Root metadata addenda preserve five detailed original Frodo part/pose/material records and their IDs/alternatives beyond inherited author-report summaries. Fenced same-scene refresh changes only note fields and report SHA:book02 15→20notes,book03 58→63notes, with original scenes/source/report pins/config/fingerprints/trials and released leases preserved. Earlier cover-batch observations remain in original source01 history, where later full source coverage is recorded; they are not new incomplete-coverage claims. Evidence:inherited-note-refresh.json,10316-booklet-02/root-inherited-note-addendum.json and10316-booklet-03/registration.json. Actual final-note display follow-up is pending.

Final ten-set local alpha handoff — 4 October2026. All10 selected sets and13 booklets are generated/frozen/registered as PDF-assisted alpha candidates with2,028 actual selected-source page hashes. Current complete backend suite399 passed,zero failures/errors (backend-final-alpha.xml/log); latest frontend45 tests,TypeScript and Vite build remain passing. Ruff and whitespace checks pass. The final independent review has13 candidates passed/zero unresolved findings/zero pending and verifies all original queued configs/fingerprints/max_chunk_attempts5 against actual engine_events; consumed unique trial directories, accepted source receipts and available pre-registration prefixes/histories are retained. This is integrity/software evidence, not accurate or physically buildable assembly certification.

Actual book03 portal QA passed434 new-source snapshots plus2 inherited-prefix boundary views, all967 cumulative transport snapshots/hashes,423 selected-source mains and5897 components. All63 disclosed warnings were visible; source crop/page/active IDs, introduced/full BOM, six camera controls/reset, current-source replay,31-instruction playback pause/resume/stop,phone3D/Guide/Pieces and progress reopening passed. Full967-step cumulative playback was not repeated. No app/page/console/HTTP errors, mutations or external requests.1262 navigation cancellations remain recorded with381 unique real asset/chunk URLs successfully read back against frozen hashes. All17 persistent rows were unchanged (rivendell-portal/portal-booklet03-qa.json,job-stability-booklet03.json). Root viewed actual final desktop/phone and source join comparisons; default edge-on angle and coarse contact/roof/terrain/chair gaps remain known limitations.

Final audit found a stale pilot report: frozen30669 completion-report contains8 source page pins/full_source_review, while its older registered alpha-report retained7 pins. The importer now checks both merged notes and input report SHA before skipping a same-scene refresh, and new imports pin that SHA. Synthetic actual-PNG receipt regression reproduces7→8 metadata synchronization with unchanged notes/candidate/config/exhausted5-trial history and no-op repeat. Actual fenced pilot refresh verified/copied all8 official page receipts; only alpha_review_notes and assisted_note_report_sha256 changed. The prior registered report and original row were archived in30669-alt-02; exact scene/source/geometry/config/fingerprint/policy/runtime/trials remain unchanged. Independent pilot-only recheck passed (pilot-report-sync.json,final-integrity-review/pilot-sync-verification.json).

Final actual lookup sweep passed all10 set lookups/13 playable booklet links and all20 inherited book02 warning texts without app/console/HTTP errors, mutations or external requests; all17 rows remained exact. The first sweep's missing-dialog-close adapter timeout is retained in final-availability-first-failed.json and browser-final-availability.log; the corrected sweep explicitly closes each modal and passed (rivendell-portal/final-availability-qa.json,job-stability-final-availability.json). Aggregate actual software coverage:3,109 snapshot views across candidate revisions;3,916 full transport snapshots/hash bindings. Earlier11 candidates have full playback evidence; final cumulative two check every new-source view and representative playback rather than redoing unchanged earlier sequences.

Owned browser and4195 preview are stopped. Actual loopback checks confirm4175,4195,5173,8000 and8002 reject connections, and no matching owned preview/generation process remains (service-shutdown-final.json). Frozen models remain needs_review, human/physical/source-camera/connector checks not_run. No cloud publication, deployment, Git push or paid API inference was performed. Handoff:var/evidence/alpha-ten-set/README.md; exact local startup command is documented there.

User timeout follow-up: the Codex provider and alpha runner now share a fifteen-minute (900-second)
default instead of five minutes. Explicit alpha/provider timeout overrides and the existing cancellation
checks/five-second termination grace remain intact. Focused backend regressions passed117 tests across
provider, strict runner, alpha reconstruction and campaign store. A simulated301-second call now completes
beyond the former deadline; an actual local sleeping stub is terminated under an explicit0.05-second
override and retains its timeout/termination evidence. No real model call or fifteen-minute wait occurred.
Ruff and whitespace checks passed. Read-only live DB comparison confirms all17 selected job
config/checkpoint/owner/state records are unchanged, with zero leased jobs and no explicit timeout overrides.
The new default applies on future inference; no jobs were resumed and no web service was restarted.
Evidence:var/evidence/inference-timeout-15m/verification.json,backend.xml,backend.log,ruff.log,jobs-after.json.

2026-10-04 user web-test follow-up: actual read-only campaign portal running at127.0.0.1:4175, current
Chrome154.0.8037.93 at1440x900/1440x1000 and390x844, plus the actual existing Codex in-app tab. Browser
plugin absent; used the existing cached Playwright CLI and installed Chrome. Frontend45 tests, TypeScript
and Vite build pass;46 preview/API/contracts tests and generated schema drift pass. Existing587KB viewer
bundle warning and Starlette test-client deprecation remain. No provider/source generation, publication or
job mutations occurred. Read-only SELECT* hashes of all17 job rows exactly match before/after.

Two reproduced defects corrected: missing favicon caused startup404; an original local SVG is explicitly
linked below the existing confined images path. Repeated tutorial/chunk replacement left browser WebGL
contexts active despite Three.js disposal; cleanup now releases the old context after listeners/resources
are disposed. The repeated13-booklet recheck has zero page/console/HTTP errors and zero context warnings.
Original404s, context warnings, and failed browser adapters remain in the evidence folder.

Real UI checks passed10 set lookups/13 booklets,26 first/final snapshots and all16 pilot instruction views,
actual hash-bound chunks/source crops, active IDs, introduced/full BOM and attachment identity. Six camera
controls/exact reset, keyboard navigation, reduced-motion full pilot playback pause/resume/stop, frozen
revision reopening/reload, phone3D/Guide/Pieces/bounds and modal focus/Escape passed. Largest Rivendell
opening took16.3seconds and playback restart14.7seconds; phone representative playback then passed. The
initial12-second test deadline expired during loading; later actual state showed playing instruction197
with no alert or loading state, so no playback stall is claimed. Five explicitly injected browser-only
failure cases passed: settings503/retry, release503/retry, missing individual geometry, source image503,
and WebGL unavailable. These injections did not modify real sources, jobs or model data.

Campaign navigation produced3935 net::ERR_ABORTED events across2312 unique URLs. All were successfully
read back against their real frozen geometry/chunk hashes; they remain recorded cancellations. Initial
geometry-only audit rejected a cancelled instruction chunk;27 remaining URLs were verified in an actual
follow-up. Pilot's own recorded cancellations/readbacks remain in pilot-browser.json. This is not a zero
cancelled-request claim. Combined evidence:var/evidence/web-app-test-2026-10-04/verification.json,
campaign-browser.json,campaign-network-followup.json,pilot-browser.json,failure-browser.json,jobs-after.json.

Root inspected actual desktop/phone source/render captures: UI controls/source/model are visible, while
coarse large-model spatial, proportion and default-angle differences remain alpha limitations. This run
samples large-model endpoints and representative playback; all967 Rivendell instructions were not
replayed. Safari, real touch-device performance, source-camera accuracy, human/physical acceptance remain
not_run. Rebuilt actual in-app tab resumes plane instruction2 with loaded real source/geometry and empty
error/warning logs. The requested4175 loopback preview stays available; separate QA browser is closed.


## Home set dropdown and code release preflight — 4 October 2026

The home field is now a native `Your set number` dropdown with ten options derived from the curated
catalogue as `number - name`. The large alpha/button block is removed. The compact supported note,
collapsed booklet review details and tutorial provenance retain unverified-model, human-review and
physical-build disclosures. The small-screen selector and Find action use separate rows so long names
have the available width. Actual4175 preview lookups opened the correct10 sets/13 selected booklets;
return/focus, loading disablement, plane geometry/source, and source/config failure recovery passed.

| Check | Result | Evidence |
| --- | --- | --- |
| `.venv/bin/python tools/check.py` |400 backend tests,45 frontend tests, schema/lint/type/build passed | `var/evidence/home-set-dropdown/local-check.log` and `final-check.log` |
| `npm run test:e2e` with serial projects |33 passed,3 explicit opt-in audits skipped; all36 tests retained | `serial-full-e2e.log` |
| Data-free isolated checkout software check |398 backend passed,2 explicit real-cache geometry skips;45 frontend/schema/lint/build passed | `data-free-checkout.json`, `data-free-software-check.log` |
| Data-free `CI=1 npm run test:e2e -- --project=software` |14 passed with no cached PDFs, geometry or reference scene | `data-free-browser-check.log` |
| Live alpha preview desktop/phone |10 lookups/13 booklets,320/390/768/1440 widths, normal app errors0; deliberate503 recovery passed | `ten-set-lookups.txt`, `responsive-keyboard-viewer.json`, desktop/mobile screenshots |
| Independent review |No remaining dropdown/CI blocker; single-job sample-count overclaim repaired to `10 set choices` | Reviewer messages in this chat; actual rendered evidence above |
| Cloud preflight and upload allowlist |Scoped account/project/billing/resources verified; connector metadata included, var/credentials/env excluded | `cloud-preflight.log`, `cloud-upload-files.txt` |
| Engine state |All17 job rows unchanged across UI and browser checks | `engine-before.json`, `engine-after.json` |

The first browser run retained stale text-field test failures; adaptations preserve malformed/unsupported
API checks and original synthetic identifier99999. A later parallel run had camera silhouette and native
review-focus failures; both passed isolated, and the complete serial suite passed. Those logs/traces remain
in the evidence folder. Screenshot capture produced four GPU driver ReadPixels stall warnings, recorded
separately from app errors. macOS CDP did not change the native picker through ArrowDown; retain that
automation limitation without claiming keyboard selection. Focus, Tab/Enter, details and Escape passed.
`uv run` panicked in the restricted macOS environment; checks used the already installed project venv.
No dependency installation, inference, source/scene edits or content approval occurred.

Fresh CI now creates the project `.venv` used by both API servers and runs the explicit cache-independent
software browser project. Default local acceptance still runs both projects; the reference candidate
assertion fails when its required cache is absent. The isolated check reused the installed Python/Node
runtimes through symlinks; it is data-free validation, not a fresh dependency-installation claim.

The user's GitHub/production request authorizes a code release after verification. Stated defaults are a
private `lumensparkxy/brickguide-3d` repository and website code only. Existing publication gates reject the
13 `pdf_assisted_alpha_completion` candidates; they remain local, needs_review and unverified. Public
alpha availability requires a separate release category/API, content-use resolution and exact-release
user approval. No alpha tutorial has been published or marked human/physically verified.

Private GitHub repository created and checkpoint `e90fdd2dc0d7f6c604d151b81d965028ca620663` pushed.
Fresh Ubuntu/Python3.12/Node22 Actions [run37181459986](https://github.com/lumensparkxy/brickguide-3d/actions/runs/37181459986)
passed dependency installation, software checks and the14 cache-independent browser cases.
Container inspection found the new catalogue import must be explicitly copied into the frontend build
stage; that dependency is now included. The existing live cloud smoke script uses native selection,
compares ten labels/API identities and uses real supported sets for desktop/mobile UI checks. Unknown
set verification is a read-only API lookup. Deployment-safety regressions6 passed, script syntax and
whitespace checks passed; actual Cloud Build/production verification remains pending at this checkpoint.

Final release verification completed on4 October2026. Code commit
`d2b45cd9ef9c1c27d138c603fc643be79ecd993c` passed fresh GitHub [run37181678182](https://github.com/lumensparkxy/brickguide-3d/actions/runs/37181678182):
398 backend tests,2 explicitly skipped real-cache geometry comparisons,45 frontend tests and14 software
browser cases. Logs are `github-ci-d2b45cd.log`. The deployment reran local software checks successfully.
Actual Cloud Build `31d81269-2919-46c9-a61d-3803635dba6b` succeeded and returned immutable digest
`sha256:568a31fe6125b3eb94fae4be2a224440575faeb52e0f344191b6dd523241235b`.
Authenticated preview, tagged public revision and final public HTTP smoke checks all passed.

[Production](https://guide2build-web-i2tso5lznq-ew.a.run.app) serves revision
`guide2build-web-00006-voz` at100% traffic; the previous traffic receipt is retained for rollback.
Actual Chromium153.0.8010.12 desktop1440x1000 and mobile390x844 checks passed. All10 option labels and
API identities/19 configured official booklet entries match the source catalogue. Real plane and kart
lookups/request confirmation, duplicate request handling, unknown-set GET, mobile no-overflow and six
private-route404 probes passed. The private cloud preview returns403 without authentication. Browser
page/console errors and warnings are0. Controlled40ms/5Mbps conditions measured interactive portal
readiness at1071ms cold/36ms warm; this is not a tutorial load, image-ready or GPU performance measure.

The first desktop screenshot preceded artwork decoding. It remains as
`production-desktop-initial-capture.png`; the smoke script now waits for all four images and fonts before
capturing full pages. Root inspected the final loaded desktop/mobile images and confirmed the labelled
dropdown, expected art and removal of the home sample-button block. Actual evidence under
`var/evidence/home-set-dropdown/`: `production-build.json`, `production-release.json`,
`production-live-service.json`, `cloud-deploy.log`, `production-browser.json`,
`production-desktop.png`, `production-mobile.png` and `production-booklets.png`.

The final documentation/screenshot-readiness checkpoint does not change application/container inputs;
the deployed code remains the tested `d2b45cd` image. The private GitHub repository contains the code
checkpoint; the13 source-assisted alpha booklets stay in the running4175 loopback preview. Production
reports no available tutorials for these ten sets; no alpha content, PDF crops or reconstruction engine
is exposed. Reconstruction accuracy, human review and physical-build status remain unchanged/unverified.
Safari and real touch-device checks were not run. No new provider inference or source/scene edits occurred.

## Alpha models published and verified — 4 October 2026

The user approved the exact 13-release campaign identified by SHA-256
`4bdd5f6ec3f9dc6ff64e60d9515d02f44d26b4c1f4596180627d505903d13f82`. All 13 immutable
public transfers and compare-and-swap head promotions completed. Independent live readback matches
the exact authorized hashes in the ten-set catalogue, publication heads and authenticated approval
records. The 19 official booklet choices now include 13 available `alpha_unverified` models; six
unpublished choices remain unavailable. Distribution approval does not establish assembly correctness.

Application commit `88e27ea6540c3f581a80cdb059260d80b0a20604` passed fresh GitHub CI
(470 backend tests, 2 cache-dependent skips, 48 frontend tests, 17 software browser cases). Local
checks passed 472 backend and 48 frontend tests; the full serial browser suite passed 36 cases with
3 optional performance audits skipped. Focused alpha cases passed again after final label/parser
changes. Cloud Build `92334e1c-cf2e-4ce6-8d36-93d3b682323f` succeeded; production revision
`guide2build-web-00008-vof` serves 100% traffic with service maximum 1 instance and unchanged minimum 0.

Real production Chromium 153.0.8010.12 checked every public release's first and final geometry view
(26 views), exact manifest hash, alpha labels, disclosed review state, component count and official
booklet/page link. Desktop 1440×1000 and plane/final Rivendell phone 390×844 checks passed. Observed
application/JavaScript errors, HTTP error responses and application warnings were zero. Four Chromium
GPU pixel-readback warnings are retained separately; the earlier warning-sensitive failure remains
in the evidence. No private source/review APIs or PDF/crop resources were fetched. Private-route
404 and unauthenticated private preview 403 checks passed. Root inspected representative actual
production desktop and phone captures; large-scene coarse placements and seating gaps remain visible.

Live Rivendell booklet 3 first geometry readiness took 53.6 seconds from release lookup; combined
first/final and phone inspection took 73.7 seconds. These are single browser QA observations, not
GPU/network benchmarks. Safari, real touch devices, assembly acceptance and physical builds were not run.

Exact frozen scenes, source pins, original render bindings and all 17 engine-job rows are unchanged.
Assets contain verified individual-part geometry closure and original notices; no complete community
assemblies, PDFs/crops, prompts, private completion reports, credentials or engine jobs were exported.
The reviewed-tutorial gates remain strict; these are separately labelled PDF-assisted unverified alpha
releases. Their reported coverage does not constitute independently verified reconstruction accuracy.

Temporary verification tags and the owned 4186 inspection server were removed without deleting assets
or rollback revisions. The requested 4175 local preview remains available. Final ledger and browser
diagnostic changes are excluded from the application build context; the deployed application still
matches `88e27ea`. No further deployment, inference or pose changes were needed for this checkpoint.

See [the exact release report](ALPHA_PRODUCTION_RELEASE.md). Evidence is retained under
`var/evidence/alpha-production/`: `publication-receipts.json`, `final-state.json`,
`live-service-final.json`, `production-model-browser/report.json`,
`production-alpha-portal-browser/report.json`, `engine-preserved.json` and `service-cleanup.json`.

## Production alpha opening: missing origin and cached CORS headers — 4 October 2026

The user reported `Let’s try again / Failed to fetch` after `Open alpha model`.
Actual in-app browser interaction reproduced it on
`https://guide2build-web-989917723212.europe-west1.run.app/`; the same plane release
opened on `https://guide2build-web-i2tso5lznq-ew.a.run.app/`. The earlier release
verification used the latter address and did not cover the project-number alias.

The public asset bucket allowed only the hashed public/preview origins. A real
HEAD request for the plane's first chunk returned 200 without
`Access-Control-Allow-Origin` for the project-number alias. The same request from
the hashed alias returned its expected permission header. Cloud Run advertises
both formats in `run.googleapis.com/urls`; the deployment tool previously used
only `status.url` when configuring the asset bucket.

The live bucket CORS configuration now includes all four actual public/preview
origins, retaining GET/HEAD and the existing exposed headers. Bucket ownership was
checked from raw Google metadata and the update was read back. The first repair
attempt refused to mutate because formatted gcloud output omits the project
number; the raw metadata correction preserves that ownership guard. No IAM,
publication heads, model bytes or Cloud Run traffic were changed by this update.

The original public asset URL still returns cached old headers with one-year
immutable caching, so the failing browser tab still cannot open it. A stable
`?g2b-transport=2` URL returns the corrected permission header for the exact same
object generation. This matches Google's documented [cache consistency limits](https://docs.cloud.google.com/storage/docs/consistency#cache_control_and_consistency).
The client repair adds that stable query only to the trusted public storage origin
for chunks, provenance, materials and nested individual geometry. Existing byte
counts, SHA-256 checks, dependency confinement and local URL behaviour remain.
The deployment tool now obtains aliases and active verification tags from actual
service metadata and applies their CORS configuration before smoke/traffic checks.

| Check | Result and scope | Evidence under `var/evidence/alpha-fetch-repair/` |
|---|---|---|
| Real production reproduction | Failed on project-number alias; same plane opened on hashed alias | `production-error.png`, `cors-before.json` |
| Live bucket correction | Applied and verified; original configuration retained | `bucket-raw-before.json`, `cors-apply-verified.log`; readback in `var/evidence/cloud-release/cors-readback.json` |
| Cache diagnosis | Original URL still lacks permission header; versioned URL has it, same generation | `cors-after-headers.json`, `cache-version-probe.json` |
| Local full checks | 490 backend tests, schema, Ruff, 48 then 51 frontend tests, typecheck and production build passed | `full-software-check.log`, `frontend-transport-check.log` |
| Focused browser regression | Six cases passed, including a synthetic stale-CORS response and nested geometry dependency | `browser-transport-loopback.log` |
| Actual public asset requests | 104 HEAD checks passed across 13 exact release hashes and both public aliases; plane first-chunk byte count/SHA verified | `all-release-cors-verification.json` |
| Rebuilt real-data viewer | Plane first/final loaded, previous navigation worked, desktop 1440×900 and phone 390×844 inspected; captured console errors/warnings zero | `local-desktop-final.png`, `local-phone-final.png` |
| Production client rollout | User approved; Cloud Build succeeded; revision `guide2build-web-00012-pej` serves 100% traffic | `deployment-authorization.json`, `cloud-build-final.json`, `services-final.json` |
| Previously failing production URL | All 13 real published models opened; first/final instructions (26 desktop views) and two phone views passed against exact existing hashes; no application errors, HTTP failures or private source requests | `production-numeric-models/report.json` and its screenshots |
| Both production aliases, direct browser inspection | Plane first/final instructions loaded, Replay enabled, final Next disabled; desktop 1440×900 and phone 390×844 rendered; captured console errors/warnings zero | `production-manual-browser.json`, `production-desktop-final.png`, `production-phone-final.png`, `production-alternate-final.png`, `production-alternate-phone.png` |
| Privacy boundaries | Eight public private-route probes returned 404; unauthenticated private preview returned 403; authenticated deployment smoke passed | `privacy-probes.json`, `cloud-deploy.log` |
| Verification cleanup | Removed only `verify-29c7afef9e7d`; four active service origins verified, same image/revision at 100% traffic; rollback revisions retained | `cleanup-readback.json`, `services-final.json`, `bucket-final.json` |

Retained earlier failures include an initial local command-handler indentation
error, a Playwright CLI argument error, and sandbox loopback bind restrictions.
They were corrected before the passing checks above; logs are retained. The
existing Three.js bundle-size advisory and TestClient deprecation warning remain.
One direct-browser locator wait expired while the alternate alias was loading;
subsequent accessibility and rendered observations showed ready geometry with no
application errors. The all-model Chromium run recorded four GPU pixel-readback
warnings separately, with zero application warnings.

The HTTP probes verify CORS headers and release identities, not browser rendering
or assembly correctness. The local actual model inspection and six synthetic
software cases are separate evidence. All alpha accuracy/human/physical labels
retain their prior unverified or `not_run` state. This repair performs no inference
or reconstruction. The production incident is resolved after the approved rollout
and live browser checks above. Application inputs are local commit
`29c7afef9e7dac9d8a34fa6642520f3443c9ecb7`; Cloud Build
`2063b640-0c63-41f5-8b65-9372502cd881` finished successfully at
`2026-10-04T08:17:29.555838Z`, producing image digest
`sha256:46012ade24c0b1431f9d07735699f6bd8abfe003f0953560b2626046d985cc70`.
The private preview is revision `guide2build-preview-00004-64h`. Both services use
the same verified image. The temporary 4186 inspection server was stopped. Final
listener checks find neither 4186 nor the separate 4175 preview listening; this
repair did not start or stop 4175, and its files remain (see
`var/evidence/alpha-fetch-repair/final-listener-check.json`). No GitHub push, PR or
merge was performed for this repair.
# Accuracy improvement implementation — 4 October 2026

Validation passed: 889 backend tests, 52 frontend tests, schema drift check, Ruff,
typecheck/build and one focused Playwright preview regression. Actual inspection
covered 12 Three.js alternative images and the saved 30669 model's findings preview.
All 5,277 historical files in the initial preservation inventory remain unchanged.
The same model and inference ceilings are retained; no new model calls or publication
occurred. Feedback-size and receiver-coverage benefits are measured offline; fresh
automatic reconstruction accuracy and runtime benefits remain unmeasured. Human
review and physical build are `not_run`. See `ENGINE_ACCURACY_IMPROVEMENTS.md` and
`var/evidence/engine-accuracy-improvements-20261004/` for evidence and limitations.


## Current shuttle only: batch stopped incomplete — 5 October 2026

The user-restricted31134/booklet-01 exploration pass is blocked at47/58 processed
and reconstructed events, with110 parts and55 accepted snapshots through printed
main44. The raw parent is preserved separately from the assisted source-schema
recovery child. Its two new model calls finished (188 shared including186 inherited),
then the engine exited naturally. The exact blocker is `Verified catalogue inputs
changed during hypothesis search`; the error names no changed resource. One private
45.006857-second audit timed out, leaving safe resume unproven. No further retry,
set, booklet, correction or improvement cycle follows.

The stopped child, source PDF/all60 checkpoint-bound PNGs, raw/corrected history,
prompts, calls, trial failures, findings and logical database/checkpoint are retained.
All338 child final-manifest entries verify; the partial evaluation is independently
rehash-verified and its387 selected inputs are unchanged. One actual Three.js overview
and official page48 show one correlated wrong-end thruster placement defect.
Completed quantity rows match44/44; four unfinished mains account for34 pieces.
Eleven indexed events remain unprocessed. Exact identity/colour/pose/connection and
collision accuracy are unscored; repeated findings are not unique defect counts.
Human review and physical build remain `not_run`; no publication occurred.

All four campaign rows match the saved stop and have no owner/lease. Final scoped
process inspection finds no task-owned engine, renderer or recovery helper.
Previous model originals are untouched. Red-aeroplane and raw second-car exact
backups verify, with separate readable recovery scene copies saved; their latest
primary-path local read failures remain recorded without claiming fresh primary
verification. The first-car and corrected second-car primary scenes verify.

Full locations, remaining issues, hashes, preservation limits and shutdown evidence:
`var/evidence/next-nine-20261005/STOPPED_RUN_REPORT.md`. This records a preserved,
inspectable partial result and a clean stop, not complete-booklet success.


## Sol shuttle production replacement — 6 October 2026

The unchanged job 130e66b0cfda443094061195ef8cea9a candidate is published only for 31134/booklet-01 as exploration_candidate / explore / unverified_alpha. The full release gate passed 1408 backend and 53 frontend tests plus schema, lint, typecheck and build. Actual production first/final rendering passed on both aliases, with coverage/provenance disclosure, phone panels and unchanged red aeroplane loading. All 240 new asset files were independently hash/size verified; other 12 catalogue entries and old rollback release preserved. Main 39 remains unresolved; attachment, group, overlap and camera findings remain. Source accuracy scoring, human review and physical build remain unverified/not_run. No new model calls or correction forks. Evidence: var/evidence/publish-sol-shuttle-20261006T102855Z/REPORT.md and verification.json.

## Piece fly-in and Replay repair — 6 October 2026

Production reproduction confirmed shuttle Replay returned `highlight / unreviewed_direction`:
authored entry paths applied only to the older 30669 reference revision, and ordinary
navigation applied snapshots without animation. The local renderer now starts entry
motion on open/step change and repeats it on Replay. Source-bound approaches retain
their existing collision guard; other paths use a labelled camera-relative visual
preview, without a physical-attachment claim. Additions move only introduced pieces,
attachments retain their existing physical IDs, and inspect-only overviews stay still.
Adjacent chunk updates do not cancel an active animation. Snapshots remain canonical.

| Check | Result and evidence |
|---|---|
| Frontend tests, TypeScript, production build | Passed: `npm run check`, 54 tests; `var/evidence/fly-in-20261006/frontend-check.log`. Existing Vite chunk-size warning retained. |
| Playback regression suite | Passed: four Chromium tests in 28.8s, `npx playwright test --config /private/tmp/g2b-e2e.config.ts`; `playback-check.log`. Pixel movement, repeated Replay, stationary support, same-instance attachment, reduced motion, normal-motion pause/resume/stop, chunk loading/retry checked. |
| Actual published shuttle data | Passed on local frontend `http://127.0.0.1:5173/`, desktop 1440x900 and phone 390x844; `shuttle-validation.json`. Release `386a5046f112b8251b2c4673ab9a448d1fa6a10ec60e3231d05e43ec4f2c22ff`, `page-5-main-2`: only `31134-side-brick-002` and `31134-side-brick-003` move. Three replays and previous/next restore identical pixels. |
| Page identity, content, overlays, console/network | Passed: Guide2Build 3D title and meaningful workspace; no framework overlay, page errors or failed requests. Four Chromium GPU readback warnings from screenshot capture retained. |
| Rendered desktop/phone inspection | Passed: `shuttle-desktop-moving.png`, `shuttle-phone-moving.png`; movement visible, controls and preview disclosure readable, no phone horizontal overflow. |
| Diff whitespace | Passed for changed viewer/test/plan files. |
| Full reference-booklet browser run / Safari | Not run in this scoped repair. Existing reference test expectations updated for automatic entry and preview mode; source-directed placement unit checks still pass. |
| Production publication | Initially local-only; subsequently authorized and deployed. See production release record below. |
| Reconstruction accuracy, human review, physical build | Not established by animation QA; physical build remains `not_run`. |

Browser plugin was not available, so existing Playwright/Chromium was used. The local
preview proxies GET-only production catalogue responses and exact public asset bytes;
manifest asset URL roots are rebased only in the temporary loopback proxy so a normal
browser can load the preview. Scene and geometry bytes remain unchanged. No engine worker, inference,
saved-model correction or publishing was started. Existing iCloud dataless dependency
reads initially broke module loading; reading installed files and an isolated temporary
Vite cache restored testing without installing/upgrading dependencies. Failed expanded
test evidence (a phone tab visibility expectation) is preserved in `expanded-attempt-1/`
and `playback-expanded-attempt-1.log` under `var/evidence/fly-in-20261006/`.

## Fly-in and Replay production publication — 6 October 2026

User authorized production deployment after local verification. Isolated source
`3348d94493f421f5cb8a35f7ab66a56e99bbc351` overlays only six verified viewer/test files
on prior production source. Full gates pass: 1,405 backend tests, 3 skips, 54 frontend
tests, schema drift, Ruff, TypeScript and build. Cloud Build succeeds; immutable image
`sha256:0b7ff52668a1017c548ae25188f12fb47130b65cb1839b29e9f257e3f4353f14` serves
100% public traffic at `guide2build-web-00018-cud`. Old revision `00015-fuj` is retained.

Real Chromium checks on both production aliases pass opening/navigation fly-in,
Replay movement, three byte-identical settled replay frames, previous/next restoration,
full-build pause/resume/stop, 390x844 phone/no overflow, and reduced motion. Only
introduced shuttle pieces move on step 2. Desktop/phone screenshots inspected. No API,
asset or header mocks; actual GCS browser loads pass. Zero page errors, failed requests
or HTTP failures. Four Chromium GPU ReadPixels warnings retained. Normal-clock loading
passes separately. Test-clock initialization and moving-frame-phase attempts are retained
and explained in the release report; no production source change was required.

All 13 model release/source/revision hashes remain unchanged. Temporary verification
tag removed; final traffic and asset CORS readback plus HTTP smoke pass. No inference
or model publication, no primary-repository commit/GitHub push. Reconstruction accuracy
remains unverified; human review and physical build remain `not_run`. Full reference
booklet/Safari browser runs remain `not_run`. Detailed evidence and rollback:
`var/evidence/fly-in-production-20261006/REPORT.md`, `verification.json`,
`production-browser.json`, `cloud-deploy/`, `final-state/` and screenshots.

## MIT open-source publication — 6 October 2026

Public repository and MIT license verified anonymously at `0d154028d9317d124b6129ea5e06ee4e05ca6867`.
Hosted CI passes at https://github.com/lumensparkxy/brickguide-3d/actions/runs/37526381075. Local release checks passed 1,405 backend tests
(3 skipped), 54 frontend tests and all 20 software browser tests. The publication snapshot
preserves production application runtime, adds public documentation/license/notices, and
retains original Git history after a credential/asset audit. Three original synthetic PNG
fixtures and a 90-second comprehensive pixel-test limit fix hosted-test portability without
changing prompt goldens or application behavior. Primary workspace and model data remain
preserved. Detailed scope, failed attempts, readbacks and draft: `var/evidence/open-source-20261006/REPORT.md`.
