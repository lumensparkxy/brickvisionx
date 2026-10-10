# Reusable accuracy improvements — 4 October 2026

The remaining mechanisms identified by the fixed-model experiment are implemented
for fresh generation jobs. The model remains `gpt-6-astra` with `high` reasoning.
Production still serves saved SceneV2 data through Three.js; these changes add no
production inference. No new full-booklet generation or publication occurred in
this slice. Autonomous accuracy and generation-runtime improvement remain unmeasured.

## What changed

| Mechanism | Current behavior | Relevant implementation |
| --- | --- | --- |
| Focused repair and review feedback | Prioritize current defects and affected rigid-group dependencies; group repeated diagnostics and share identical comparison findings once. Retain complete originals, input hashes, selection receipts, uncertainty and omission counts. Each compact receipt is bounded to 24 groups and 16 KiB; the model receives a smaller projection. | `repair_feedback.py`, `exploration.py` |
| Competing receiving positions | Explore compatible receiver sites and quarter-turn orientations across source-nominated receiving pieces. Hints remain priors. Keep 64 evaluations, eight beam alternatives and up to three distinct rendered scenes, including the unchanged raw fallback. The proposal prompt asks for competing source-supported receiver identities when mirrored/symmetric receivers are ambiguous. | `hypotheses.py`, `exploration.py` |
| Rotated duplicate detection | Verify whole individual-part triangle geometry under bounded proper-axis rotations. Detect coincident symmetric placements without treating nominal bounds, reflected shapes or asymmetric tiles as identical geometry. | `whole_part_symmetry.py`, `hypotheses.py` |
| Semantic source regions | Retain every indexed crop and distinguish build events, overviews, associated details, repeated depictions and ambiguous regions. Only explicit, evidenced classifications and valid associations can remove a crop from the reconstruction queue. Uncertain and orphan callouts remain executable. Source/page/image hashes bind every index. Coverage requires distinct snapshots and respects callout/attachment parents. | `panel_index.py`, `exploration.py`, `alpha.py` |
| Batch alpha reuse | Send localized retained quality findings and the latest rejection into later batches. Record bounded diagnostics for newly added snapshots, source-region findings and semantic associations without adding calls or assembly gates. | `alpha.py` |

The new execution contracts are `source-exploration-v4` and
`source-direct-alpha-v2`. The rejected attachment-prompt challenger remains opt-in.
Existing strict behavior is available. Assembly-quality failures remain diagnostic
during exploration; verified source integrity, valid scene structure and resource
limits remain required. SceneV2 and its viewer contract are unchanged.

Resume checks now bind partial indexes to authenticated provider replies and
promoted candidates to authenticated selected trials. Alpha checks the immutable
accepted receipt, reconstructs observations/findings from accepted evidence and
retains semantic indexes for assisted empty-batch corrections. Model/reasoning and
policy changes are rejected before further calls.

Fresh correction forks authenticate inherited indexes, preserve their raw records
in canonical `source-index-seed.json`, and pin its digest. V2 cursors must agree with
the normalized source-event queue. Legacy regions stay unclassified; incompatible
legacy callout prefixes require a restart from the first instruction. The fork does
not require rendered PNGs, while reconstruction resume verifies their actual hashes.
Historical evidence and inference budgets are preserved.

## Measured offline results

Evidence root: `var/evidence/engine-accuracy-improvements-20261004/`.
The feedback replay consumes frozen unaided baseline findings. The placement replay
consumes frozen raw proposals. The failed assisted scene is used only to test duplicate
diagnosis; corrected poses do not enter generation or placement-search inputs.

| Check | Before | After | Scope |
| --- | ---: | ---: | --- |
| Findings payload across 14 repair contexts | 586,963 bytes | 137,079 bytes | Model-facing payload: 76.65% smaller |
| Findings payload across 27 comparisons | 2,288,898 bytes | 331,458 bytes | Model-facing payload: 85.52% smaller |
| Final duplicated comparison diagnostics | 200,906 bytes | 12,213 bytes | Model-facing payload: 93.92% smaller |
| Receiving sites examined, each of two raw trials | 1 | 4 | Source-nominated receivers only |
| Main-3 candidate evaluations | 16 | 64 | Eight beam entries, three distinct render scenes |
| Main-4 candidate evaluations | 8 | 64 | Eight beam entries, three distinct render scenes |

The compact repair projections retain all 5 current agent-visible defects and all
15 current deterministic contract findings in this baseline. They retain 102 of 117
other current guidance occurrences; 15 are omitted from the prompt and explicitly
counted. Ten explicit-uncertainty groups are likewise omitted and counted. All full
records remain archived. A few initially small contexts grow because receipt/scope
metadata is added. Smaller feedback is not proof of faster or more accurate inference.

The geometry check detects the coincident `3020` bases and `3710` strips under Y180
in the retained failed revision; asymmetric `25269` geometry is excluded. Independent
checks verified all 16 beam prefixes, provenance and rigid-group transforms, with
maximum relative-transform error below 3.56e-15.

All six rendered alternatives were inspected as detached modules and assembled
attachments: 12 actual Three.js images, with no JavaScript errors in their reports.
The images use overview cameras and do not establish source alignment. Some expanded
alternatives have visibly wrong strip/tile arrangements compared with the official
parallel-row callout. Broader search requires source-based selection; it does not
automatically produce a better assembly. The frozen trials nominate `35044` receivers,
so search alone cannot discover an omitted opposite receiving piece or the `18980`
receiver. The revised prompt addresses this nomination gap; its effect is unmeasured.

## Validation and preservation

- `.venv/bin/python tools/check.py --python-only`: **889 tests passed**, generated
  schemas current. One existing Starlette deprecation warning was reported.
- `.venv/bin/python -m ruff check apps/api tools tests/backend`: passed.
- `npm run check`: typecheck, **52 frontend tests** and production build passed.
- `npm run test:e2e -- --project=software tests/e2e/exploration-preview.spec.ts`:
  **one browser regression passed**, including unresolved-instruction navigation and
  phone-width inspection.
- Actual read-only browser interaction opened the saved 30669 candidate, navigated
  its branch and inspected the focused findings with the pre-correction review label.
  The temporary preview tab and server were closed; existing preview services were
  not changed.
- All **5,277** files in the initial preservation inventory are hash-identical,
  including historical frozen experiment inputs and the four live scene files.
  The saved final scene file SHA-256 remains
  `fa13022eb0f109d6b7a8f644e25eb12e448d8ae0b07fb339d907facf90b3cb0d`.

The first broad check exposed a stale synthetic campaign fixture that stamped the
new version onto the old policy shape. It now uses the engine's frozen policy
constructor. Initial sandbox-denied rendering evidence was retained; successful
rendering used a separate output directory. Neither was classified as an accuracy result.

Evidence entry points:

- `feedback-replay/v2/report.json`: payload sizes, retained/omitted findings and
  authenticated source inputs. The four replayed integration helpers and feedback
  module still match the implemented code; subsequent source/resume fixes are separately
  pinned in `implemented-code-manifest.json`.
- `search-replay/dedup-final/manifest.json`: raw proposals, geometry, 64/8/3 bounds,
  alternatives and search coverage.
- `render-inspection.json`: source bindings, scene/image hashes and inspection limits.
- `preview-browser.json`, `preview-findings-context.png`: actual saved-candidate UI proof.
- `preservation-after.json`: unchanged historical inventory.
- `backend-check-final.log`, `ruff-check-final.log`, `frontend-check.log`,
  `exploration-e2e.log`: final software checks.

## Remaining accuracy work

Fresh autonomous improvement is **not measured**. Keep the provider and inference
budget fixed for future comparisons and evaluate one major mechanism at a time.
Retained alternatives still need source comparison and localized correction. Receiver
identity coverage remains a limit when the source is ambiguous. Semantic region
recognition has software coverage but no fresh pilot indexing-quality measurement.
Connection metadata and collision analysis remain partial; AABB warnings are not
physical collision proof. Human review and physical-build verification are `not_run`.
The saved assisted model and all earlier experiment results remain separately reported
in `FIXED_MODEL_ACCURACY.md`.
