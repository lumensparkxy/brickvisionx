# Complete-booklet accuracy iteration — 4 October 2026

## Result

The first improvement milestone is complete: a fresh unaided run processed and reconstructed
all **13 indexed instruction panels**, including the enlarged attachment detail, with **12
numbered main steps, 18 snapshots and 32 physical pieces**. One source-derived correction
pass repaired both wing mounts, the first callout's corner tile and the attachment grouping.
The original and corrected candidates are separately inspectable. This establishes improvement
against this unaided run; it does **not** establish superiority to the existing assisted production
alpha, exact correctness, human review or physical build validity.

| Measure | Unaided | Corrected | Scope |
|---|---:|---:|---|
| Processed / reconstructed panels | 13 / 13 | 13 / 13 | No unreconstructed panel |
| Numbered main instructions | 12 / 12 | 12 / 12 | Source-reviewed numbering |
| Snapshots / physical pieces | 18 / 32 | 18 / 32 | Two extra inspection/detail snapshots relative to the 16-snapshot annotation |
| Main-instruction quantities | 12 / 12 | 12 / 12 | All 32 expected pieces; zero count mismatches |
| Identifiable pieces by instruction | 26 / 26 | 26 / 26 | Six exact identities remain unknown |
| Supported colours by instruction | 22 / 22 | 22 / 22 | Ten remain unknown |
| Invalid attachment-group observations | 2 | 0 | Deterministic snapshot checks |
| Unexplained historical movements | 3 | 0 | Deterministic snapshot checks |
| Exact duplicate whole-part placements | 0 | 0 | Exact coincidence check only |
| Qualitative source relationships | 8 pass / 1 fail / 1 unknown | 9 pass / 0 fail / 1 unknown | Same ten-relationship rubric; matches assisted baseline |
| Main 3 silhouette overlap | 0.7583 | 0.9259 | Same source, XY camera, crop, exclusions and segmentation policy |
| Main 3 edge F1 | 0.4274 | 0.7449 | Same controlled image comparison |

The image measures are local source agreement, not whole-model accuracy percentages. Source
annotations were agent-reviewed and excluded from the unaided generator. Quantity evaluation
also checks 20 part-design count constraints: its JSON denominator of 32 is **32 constraints**,
not 32 independent per-instance correspondences. Exact placement and grouping are unscored
where no independent annotation exists.

The independent raw review was frozen before its reviewer opened corrected views. The two failed
clauses concerned the first callout's receiving side and its later relocation; both are resolved.
The remaining unknown is an exact aligned wing-outline check, which perspective overviews cannot
establish. The assisted production alpha has the same nine-pass/one-unknown result on this rubric.

## What changed in the model

The final full-pass views exposed white callout strips crossing the body at the wrong height.
Earlier official views and verified individual-part geometry then localized the defects:

1. The main 3 corner tile was at the wrong endpoint and yaw. Its local position is corrected
   from `[-30, 8, -10]` to `[30, 8, -10]` LDU with a positive 90-degree Y rotation.
2. Both three-piece wing callouts belong underneath the curved wing plates, one stud farther
   outward. Their base anchors are now `[60, 0, 0]` and `[-60, 0, 0]`, replacing the generated
   16-LDU-higher, 20-LDU-inset placements. The main 3 attachment also moves to the source-shown side.
3. Two attachment snapshots now reference their actual detached groups. Two explicit replay
   resets prevent the raw main 4 estimate from applying its historical relocation a second time.

Seven correction commands affect six physical pieces. All other poses remain unchanged. All
18 snapshots and 32 stable IDs remain present; the corrected transforms propagate through every
dependent snapshot. Fifteen affected snapshots were freshly rendered and three unchanged prefix
snapshots reused after hash/lineage checks. Source, before and after images exist for all 18 snapshots.

The source-derived cameras used only unchanged central-spine landmarks. Four held-out new strip
stud centers support the corrected mount: main 4 RMS falls from **31.38 px to 1.05 px**. Main 3's
corrected placement gives **0.64 px**, compared with 14.36 px for the **superseded, unapplied**
side-only proposal. The latter is not the raw main 3 baseline. The complete main 3 raw-to-corrected
comparison is the fixed-camera silhouette/edge result above. Three nominal underside contacts
per wing support the new placement; clutch, strength and mesh collision remain unverified.

The private side-only proposal and its renders remain archived. It was never applied to an engine
job and is not counted as a second correction pass. The current result uses **one of two allowed
passes**; no additional source-supported geometry change was forced merely to consume the second.

## Engine implementation

- **Continuation:** `explore` tries one proposal and at most one localized repair per indexed panel.
  Quality findings do not prevent later panels. Missing renderable proposals retain their source
  and unresolved record. Processed and reconstructed counts are distinct. `strict` remains available.
- **Part recognition:** source callout crops, quantities and shape observations retrieve verified
  individual geometry and preserve up to three plausible part IDs with uncertainty.
- **Placement alternatives:** bounded supported-connector search considers up to 64 placements,
  retains eight alternatives and renders up to three, including the raw candidate. Rigid groups,
  unsupported geometry and rejected plans are recorded.
- **Camera separation:** bounded landmark-correspondence alternatives change cameras without moving
  bricks. Failed fits use labelled overview renders. Unscorable segmentation retains a fitted camera.
- **Later-view correction:** immutable forks accept localized mapping, pose, rigid-group, grouping
  and landmark edits or source-guided restarts using later official pages. Full descendant replay,
  correction lineage and a two-pass limit preserve unaided evidence.
- **Diagnostics/evaluation:** exact duplicate placements, nominal contacts, seating gaps, group
  transforms, historical movement and broad-phase overlaps guide corrections. Local `evaluate` and
  `fork-correction` commands and per-instruction preview findings expose the evidence. SceneV2 stays compatible.

The complete v2 inference run uncovered two measurement/selection errors, repaired separately in
v3 after freezing its output:

- The old selector preferred main 2's poor 21.50-px camera over a 0.746-px fit of the **same physical
  scene**, because the better attempt retained more honest uncertainty. The new selection policy
  separates current visible defects from uncertainty, uses numerical camera receipts, preserves
  ambiguity and records ties. A zero-provider-call replay selects the better camera.
- Near-white threshold masks counted almost all blue/grey background as foreground, inflating
  a main 2 overlap score to 0.9686. That legacy score is excluded from ranking. New border-background
  segmentation rejects clipped, ambiguous or multiple-object masks. With original exclusions,
  this example is correctly unscorable; separately source-reviewed callout/numeral exclusions yield
  0.8637. No comparison claims improvement from that changed annotation alone.

For the main 3 geometry comparison, identical source/arrow exclusions, a common crop and fixed XY
projection were used for all candidates. Tight crops were first rejected and retained; a common
20-pixel bottom margin removed clipping for every candidate. These image-policy changes were tested
on retained pixels, independently from candidate-selection replay. A separate earlier retained camera
trial improved RMS from 7.7633 to 0.4021 px with both brick poses and observed pixels unchanged.

The visibility contract now distinguishes assembly presence from source-pixel occlusion, addressing
repeated proposal-schema errors for hidden existing pieces. The v3 prompt and selection changes
have regression/replay evidence; **another full unaided v3 inference run has not been performed**.
The initial engine implementation bundled several mechanisms, so its difference from the historical
production alpha cannot be attributed to one mechanism.

## Remaining issues and next accuracy work

1. **Eight localized nominal feature conflicts remain in the final assembly** (six in the raw result).
   They involve the lower red plates, wing/base contacts and upper support plates. Across snapshots the
   final checker reports 62 corrected versus 44 raw feature-conflict observations, not that many distinct
   physical defects. Compare main 5/6 source views and actual receiver geometry before changing these poses.
2. **General collision and visible-gap correctness remain unknown.** Broad-phase overlap candidates
   increased from 357 to 399 across snapshots (52 to 56 in the final snapshot) after correcting the wing
   mounting. Near-connector-gap observations increased from 27 to 29. These are diagnostic candidates,
   not confirmed collisions or source-visible gaps, and do not overturn the controlled source evidence.
3. **Search can still miss the right branch.** In this run the main 3 plans were rejected because the
   proposed moving group was incomplete, and later model contact hints did not propose the underside
   attachment. Next compare source-consistent complete-group/underside alternatives with the same
   provider and budget, using this frozen run as the control.
4. **Source annotations are partial.** Six exact part identities, ten colours and most absolute poses
   remain unscored. Transparent material appearance and exact aliases/mold variants need more evidence.
5. **Sequence and presentation remain provisional.** The raw model added an inherited-placement
   inspection snapshot; the corrected revision keeps that history without a geometry jump. Some active
   sets emphasize the whole assembly. Normalize those only in a separately measured revision.
6. **Retained warning history is not a count of distinct defects.** The preview labels pre-correction
   findings as needing recheck. Original failed fits, old review notes and broad-phase warnings remain
   accessible rather than being erased or counted as fresh confirmations.

This prioritizes actual wrong pieces and attachment geometry before materials or camera polish. Future
comparisons should change one major mechanism at a time. A complete independent reference remains useful
but is not required for the next exploration run.

Two diagnostic repairs were measured separately on the unchanged frozen scenes. Previously one occupancy
exception erased the contact graph and produced a misleading 31-ID floating warning. Diagnostics now retain
nominal coincidences and identify each conflicting feature and its actual mates. The graph is explicitly
not a graph of validated physical connections; strict occupancy rejection remains in effect.

The isolated tail warning then proved to be omitted metadata: the pinned individual 18980 geometry has a
central underside tube matching the 3040b stud axis, radius, depth and seating plane at the existing poses.
Exactly one inspected receiver was added; the other four internal tube axes remain unsupported. No tail
pose changed. The final replay has **zero no-nominal-path warnings** in either model and 83 raw / 89 corrected
nominal contacts, including conflicted ones. This removes a false warning, not a physical floating defect.
Physical clutch and mesh collision remain untested. The earlier reports with broad contact warnings are
preserved; `*-evaluation-final/` uses the current localized checker and explicit receiver metadata.

## Experiment, usage and preservation

Official PDF SHA-256: `6cb3e669fef3662dfd498cba0e631f1d9ec082c2bf8c0fb0a0febe303680a6b6`.
All assembly evidence is from that booklet. Geometry comes from verified individual LDraw files.

| Artifact | Identity / record |
|---|---|
| Historical assisted alpha baseline | `1cb72d2e2ac84354a587233a2e5859db`; frozen `baseline/` |
| Retained cancelled contract trial | `d5ba2e60f7484bc7a32d48773b82c384`; 11 shared call reservations |
| Complete unaided v2 run | `76c9616b259a4ef89cf63ee86938a7b9`; frozen `unaided-full/` |
| Assisted correction 1 | `c4a4de772606464798f356009fcb03f2`; frozen `corrected-full/` |
| Unaided scene hash | `a040005f0888fdbd4407b4fe573fc05b80493aaea4c0037b24b5bca2c1623e76` |
| Corrected scene hash | `9e684bb94783889e435ac7b386bfec5539cc3246fd6e3bf8f4f4d8e0e6b22bba` |

The existing Codex CLI provider remained `gpt-6-astra` / `high`, with a **100 shared-call ceiling**.
The completed run has **41 actual local provider invocations**, **3,828.97 seconds of measured provider
time** (63.82 minutes), and **52 total shared reservations** including the earlier failed trial. Its
creation-to-finished checkpoint span was 98.80 minutes, including software recovery and pauses, not a
throughput benchmark. Correction, render and deterministic policy replays added **zero engine provider
calls**; the correction is still explicitly agent-assisted. Subscription monetary cost is not inferred.

Fourteen distinct candidate scenes have verified archived/rendered evidence across the 13 panels.
Older abbreviated records make the exact alternative count unknown; the retained distinct-alternative
lower bound is one. The v3 archive records full beam scenes for future exact counts.

The failed nested-contract trial, cropped-render registration failure and prompt-serialization recovery
are preserved with their original inputs. Authenticated saved prompts are replayed without silently
changing their numeric tokens or repeating reserved calls. The frozen 1,067 unaided files and job row
were verified unchanged after the correction. The original 17 job rows, 11 baseline files and 17
interrupted-trial files were also verified unchanged.

## Inspect and reproduce

The corrected preview is available at **http://127.0.0.1:4176**. The unaided comparison preview is
http://127.0.0.1:4175. These are local private servers; no publication occurred.

```sh
.venv/bin/python tools/preview_engine.py c4a4de772606464798f356009fcb03f2 --port 4176
.venv/bin/python tools/engine.py evaluate c4a4de772606464798f356009fcb03f2 --reference var/evidence/accuracy-30669-20261004/source-reviewed-combined.json --baseline var/engine/jobs/76c9616b259a4ef89cf63ee86938a7b9/scene.json --output var/evidence/NEW_EVALUATION
```

Use a new evaluation output directory. Do not restart an already running preview. `ENGINE.md` describes
new runs and correction requests; new policy revisions never silently upgrade original provider receipts.

All private evidence below is under `var/evidence/accuracy-30669-20261004/`:

- `unaided-evaluation-final/`: source comparison and scores against the historical assisted baseline,
  using the final checker. The earlier `unaided-evaluation/` is retained.
- `corrected-evaluation-final/`: all 18 source/before/after cards and the current scoped evaluation.
  `corrected-evaluation-02/` retains the comparison before diagnostic localization. The first
  `corrected-evaluation/` is retained with before images unavailable because its baseline was scene-only.
- `unaided-browser/` and `corrected-browser/`: all snapshots, three final inspection views, desktop and
  phone checks. Both passed without page errors or horizontal overflow.
- `main3-4-source-review/height-review/`: source landmarks, fixed-camera renders, seven-command request,
  nominal contact proof and full descendant replay proof. Earlier side-only proposal is superseded.
- `selection-policy-patch/`: retained main 2/main 4 selection replays and source policy receipts.
- `mask-policy-patch/`: segmentation patch and controlled retained-pixel comparisons.
- `contact-diagnostic-patch/`, `tail-receiver-review/` and `tail-center-connector/`: localized nominal
  graph replay, source/individual-geometry investigation and one explicit receiver addition, without pose changes.
- `baseline-relationship-review/`: historical baseline has nine satisfied qualitative relationships
  and one unscorable aligned-outline relationship; no failed relationship on that limited rubric.
- `unaided-relationship-review/` and `corrected-relationship-review/`: independent same-rubric
  assessment, eight/one/one to nine/zero/one, with source/render and unchanged-scene receipts.
- `unaided-preserved-after-correction.json`: all frozen unaided bytes and durable row unchanged.

## Verification

The final integrated backend suite passed **637 tests** in 17.44 seconds, with no failures or skips
(`backend-final-integrated.xml`). Ruff, generated-schema and whitespace checks passed. Frontend typecheck,
**52 tests** and production build passed; their changed-file hashes are pinned in
`preview-recheck-verification.json`. Five targeted exploration/viewer browser regressions passed, with
the correction-label test rerun after its final change. Both actual 18-snapshot previews passed desktop,
phone, navigation and three-final-view checks with no page errors or horizontal overflow.

Tests cover quality-failure continuation, missing-render gaps, retained uncertainty and alternatives,
fixed attempt/call limits, exact saved-request recovery, geometry/source tampering, dependent pose replay,
old-policy preservation and prefix render reuse. The final recovery audit also reproduced and fixed a
write-before-checkpoint crash window: an outcome requires its trusted checkpoint hash and every selectable
scene must match archived evidence. An unpinned interrupted outcome stops without promotion or another
provider call. This is an integrity boundary, not an assembly-quality gate.

Existing Starlette/httpx deprecation and Vite bundle-size warnings remain. Software and local source
comparison checks do not establish exact reconstruction, human approval or physical build validity.

Human review: `not_run`. Physical build: `not_run`. Publication: `not_performed`.
