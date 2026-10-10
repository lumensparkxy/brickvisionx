# Fixed-model accuracy experiment — 4 October 2026

Status: the raw comparison and two assisted correction passes are complete and
frozen. The final assisted candidate has 9 pass / 0 fail / 1 unknown visible
relationships, compared with the raw challenger's 7 / 2 / 1. Source-guided
corrections restore the body/roof continuity and opposite wing modules. All 17
snapshots and four final views are inspectable. This is assisted improvement;
autonomous prompt improvement has not been demonstrated.

The prompt challenger removes an
undeclared historical movement but introduces a source-visible lateral body
offset. It is not an overall accuracy improvement and is not promoted to the
default. The unchanged source rubric scores the control 9 pass / 0 fail /
1 unknown and the challenger 7 pass / 2 fail / 1 unknown. The two failing
relationships describe one propagated body-offset defect, not two independent
physical faults.

The user approved a measured improvement sequence while keeping the current model.
Both runs use `gpt-6-astra`, reasoning `high`, exploration execution, a 100-call
ceiling and at most one targeted repair per indexed instruction. The production
viewer continues to use saved SceneV2 and individual-part assets; this work does
not add inference to the production request path or publish a new model.

## Experiment

The control is a fresh complete-booklet attempt using the frozen, unmodified v3
engine. The first intervention appends generic attachment guidance to proposal
and targeted-repair prompts. It asks for complete rigid groups, source-supported
receiving faces, bounded placement alternatives and explicit uncertainty.
It contains no set-specific identities, coordinates or reference answers.

The solver, geometry inputs, image policy, schemas, review prompts, renderer,
model and reasoning setting stay fixed. The opt-in profile is
`--proposal-profile attachment-reasoning`; the default remains `baseline`.
Profile name, version and prompt digest are bound to the run policy. A changed
profile or prompt cannot silently resume an earlier run.

| Run | Job | State |
|---|---|---|
| Frozen v3 control | `bcb5b716c8114d2d843e1fd17e0164a8` | Complete with findings |
| Attachment prompt | `a31294ceb1b34ab4a431db5ca9b54f29` | Complete with findings |
| Assisted source-context restart | `7bbdc42bd1d144cc92c29d2b1f9e43b2` | Complete; parent preserved |
| Assisted localized correction | `9612c61e92004355a68cfd0645dac759` | Complete; final inspectable candidate |

| Source-supported measure | Control | Prompt challenger |
|---|---:|---:|
| Required semantic events represented | 16/16 | 16/16 |
| Physical pieces | 32 | 32 |
| Identifiable part counts matched | 26/26; 6 unknown | 26/26; 6 unknown |
| Supported colour counts matched | 22/22; 10 unknown | 22/22; 10 unknown |
| Visible relationships, pass / fail / unknown | 9 / 0 / 1 | 7 / 2 / 1 |
| Undeclared historical movements | 1 | 0 |

The visible-relationship rubric is coarse and does not certify every part pose,
hidden connection or physical fit. The new lateral body error outweighs the
sequence improvement for deciding whether to promote this prompt.

The control freshly indexed eight official PDF pages into 14 panels. Its index
includes a finished-model thumbnail as an attachment panel, an uncertainty that
already causes sequence findings. The paired run reused this exact automatic
source index without assembly poses, candidates, corrections or evaluation
annotations. The eight index calls are charged to both budgets; the paired run
started at its first assembly proposal without new indexing calls. This design
adjustment was recorded before any
intervention inference. The comparison therefore tests assembly generation with
a shared index, not repeated end-to-end source indexing.

## Evaluation and evidence

The source-only rubric was frozen before inspecting these new results: 12 main
instructions, 16 required semantic events, 32 physical pieces, 26 identifiable
pieces, 22 source-supported colours, and 10 visible relationships containing 32
clauses. Unknown identities, colours and hidden contacts remain unknown. The
existing 32 quantity constraints overlap pieces and are not a per-piece score.

Compare raw runs before corrections. Preserve every source/render frame and
explicitly record missing or ambiguous events, including unmatched frames from
either run. Generated step IDs do not establish correspondence across runs.
Camera-aligned numerical comparisons require shared source evidence; labelled
overview renders support inspection but do not establish pixel accuracy.

Report actual inference calls, inherited indexing calls, token-report completeness,
runtime, coverage, localized defects and remaining alternatives. Equal call
ceilings do not imply equal compute. One pair is descriptive evidence, not a
general conversion rate or statistically established causal effect.

Private evidence and immutable manifests:
`var/evidence/fixed-model-30669-20261004/`. The challenger has an isolated data
directory at `var/experiments/fixed-model-30669-20261004/attachment-data/`.
Historical unaided and corrected jobs remain separate comparison evidence.

The frozen baseline contains all 14 indexed panels, 19 snapshots and 32 pieces.
All 32 overlapping quantity constraints match; the independently source-identifiable
part counts match 26/26 and the supported colour counts match 22/22. Six identities
and ten colours remain unknown. These aggregate counts do not establish per-instance
correspondence, placements or groups. Independent source review found all 16
required semantic events represented: 9 relationships pass and 1 is not evaluable
(31 of 32 clauses pass; the remaining outline clause lacks sufficient aligned
camera evidence). These are coarse visible relationships, not exact pose or
physical-connection scores. A confirmed sequence defect remains: the three-piece
main-3 module translates by 20 LDU at main 7 without updating its earlier snapshots.
The correct absolute seating remains unresolved. The raw run used 63 calls and
4,989.14 seconds of recorded model
execution, with complete token/timing receipts and no failed provider process.
Its 2,072 job files are frozen under `baseline-frozen/` before evaluation.
Wall time from the first claim to completion was 5,331.67 seconds, including source
indexing. Four final inspection views preserve all 2,526 pairwise transforms
exactly. Browser inspection exercised all 19 snapshots, the source panel and
per-instruction findings; no console warning or error was returned. Unnumbered
extra frames receive duplicate main-step navigation labels, a separate preview
issue. Baseline review evidence is retained in `baseline-source-review/`.

The challenger processed all 14 panels; 12 produced new renderable candidates.
Its first proposal already reconstructed printed mains 1 and 2, and their later
indexed panels returned unresolved records instead of adding duplicate snapshots.
The final scene contains all 12 numbered mains, 17 snapshots and 32 pieces. All
32 overlapping quantity constraints, 26 supported identity counts and 22 supported
colour counts match, with the same 6 unknown identities and 10 unknown colours.
All 15 earlier poses are exactly unchanged from main 6 to main 7; the deterministic
whole-run evaluation finds no historical movement. Independent source review has
confirmed a new defect: main 7's yellow body plate sits one stud sideways from
the paired yellow strips, and later roof parts inherit the offset. The part's
actual transverse geometry bounds confirm this is not a local-origin artifact.
The earlier white attachments constrain the displaced channel; the two assisted
correction revisions below investigate that branch. Preventing silent movement is useful, but
cannot establish that the preserved attachment was correct.

The challenger used 52 actual calls, plus 8 inherited indexing calls charged to
its budget (60/100). All 52 calls have complete usage/timing receipts, with
4,728.40 seconds of model execution and no failed process. Its 1,942 job files
were copied and byte-verified before evaluation. Browser inspection exercised all
17 snapshots, rotation/reset and the findings panel without a returned console
warning or error. Four final views preserve all 2,506 pairwise transforms exactly.
Their source-independent camera rotations are inspection aids, not accuracy scores.
Both runs made 14 initial and 14 repair proposals. The three-call reduction is
in visual reviews, including the unresolved duplicate panels; it is not evidence
of improved accuracy or efficiency.

The final independent integrity audit verifies all 20 older job rows and 1,209
older files, both frozen code manifests, both raw job copies and all 149 pinned
source/geometry inputs. Every challenger request used `gpt-6-astra/high`; all
307 supplied image bindings are official source pages or its own instruction
evidence. The audit found no integrity or accounting issue. Exact metrics and
hashes are in `final-integrity-review/README.md`.

Broad-phase final overlap candidates are 48 in the baseline and 41 in the challenger.
This is not seven confirmed collisions repaired. Near-connector gap candidates
across all snapshots are 22 and 17, respectively, and neither final snapshot has
such a finding. Source-view and frame-count differences affect aggregate diagnostic
counts. Narrow-phase collision and physical-build checks were not run. The baseline
has 22 retained archived alternatives; the challenger's archive establishes at
least 39, with its two unresolved panel records preventing an exact evaluator total.
These are retained trial alternatives, not 39 source-approved assemblies.

## Measured next gap

The raw trial's own retained requests also expose a search-coverage gap. Its
repaired proposals fix the transverse positions of both white attachment groups;
their receiver hints keep those positions in every rendered alternative. The
solver changes the main-3 depth, but does not introduce either sideways offset.
This points to alternative receiver selection, in addition to proposal wording,
as a mechanism worth testing separately. Neither more candidates around the same
fixed receiver nor preserving that decision establishes correctness.

A read-only audit of the frozen baseline found that repair feedback bypasses the
24-item prior-finding selection used by initial proposals. Across 14 repairs,
1,584 of 2,105 finding occurrences (75.2%) mention only earlier steps; 1,858 (88.3%)
are bounding-box overlap warnings. The final comparison repeats the same
378-item finding array for two candidates, accounting for 92.8% of its 216,355-byte
prompt. Specific main-3 and main-7 placement messages appear at the ends of long
repair arrays. These measurements come from retained requests and provider events,
not estimates from token counts.

The next separate mechanism should prioritize current-step and affected-group
defects, identify repeated issues consistently, and share historical diagnostics
once while retaining all uncertainty in the evidence archive. Reducing this
measured repetition may improve attention and cost; an accuracy benefit remains
unproven. No feedback filtering or repair-trigger change is applied to either run
in this attachment-prompt comparison. Detailed measurements and exact examples
are retained in `context-audit/`.

## Assisted source-context correction

After freezing the raw comparison, a new source-guided branch restarts at main 3.
Job `7bbdc42bd1d144cc92c29d2b1f9e43b2` retains only mains 1/2 (two snapshots, five
physical IDs) and uses the official main-3/4 attachment views with later mains
7/8 and 11/12. The repair brief identifies the visible discontinuity and uncertain
upstream seating; it supplies no replacement poses. The run completed and was
frozen before evaluation.

Two optional correction controls were added and tested separately: explicit
evidence-bound context pages, and a proposal-attempt cap that can only preserve
or reduce the inherited cap. Without explicit context selection, the previous
restart chose the first two suffix pages, potentially omitting the views that
expose the defect. Defaults and historical request hashes remain unchanged.
The new runner is frozen in `correction-code/`; only `corrections.py` differs from
the frozen challenger code.

This assisted run keeps `gpt-6-astra/high`, the same prompt profile, source index,
geometry, solver and renderer. It uses one proposal and at most one visual review
for each of 11 remaining indexed panels: at most 22 new calls, with 60 calls
already charged to the unchanged 100-call lineage ceiling. It is not another raw
prompt trial: source guidance, selected later views and the lower attempt cap
are explicit assisted inputs. Any improvement must be reported separately.

The restart processed all 14 panels, reconstructed 11, and retained 17 snapshots
and 32 pieces. The three unresolved records are the separately indexed mains 1/2
and the main-5 detail, whose assembly content is represented in other snapshots;
all 16 semantic source events remain represented. It used 21 new calls: 11
proposals and 10 reviews, bringing the shared lineage to 81/100. Recorded model
time was 1,859.70 seconds and claim-to-completion time was 1,951.61 seconds.

The unchanged source rubric scores this revision 8 pass / 1 fail / 1 unknown,
with 28 passing, 3 failing and 1 unknown clauses. The yellow-body and roof offsets
are repaired, but main 3 and main 4 now occupy the same near arm. Verified mesh
vertices establish that their entire rectangular base plates and strips are
superposed despite their different orientations. This is a concrete duplicate
placement, not merely a bounding-box warning. The far arm is bare. A larger count
of passing relationships alone therefore does not establish overall improvement.

## Final localized correction

Job `9612c61e92004355a68cfd0645dac759` is the second and final assisted revision.
The official main-3 callout identifies the rounded tile's other exposed-row end
and orientation; the attachment arrow identifies the far arm. Two explicit
source-bound commands correct that tile, then move the complete three-piece
main-3 module. Main 4 remains on its printed near arm. Three earlier alternatives
that moved main 4 were rendered and rejected against the source.

The completed-parent replay changes 31 poses across 11 snapshots and preserves
197 other pose records, all part identities, colours, counts, groups and snapshot
structure. Earlier evidence remains byte-identical. The reviewed prefix and full
descendant replay agree to numerical tolerance. This pass uses **zero new model
calls**, retains 81/100 charged calls and consumes the second allowed repair pass.
Its sub-second checkpoint completion is not a measurement of authoring or review
effort. It cannot be reported as an unassisted generation success.

All 17 snapshots were exercised in the live preview, waiting for individual
geometry and nonzero draw calls. Camera rotation/reset, the official panel and
the per-instruction findings work without returned console warnings or errors.
Four final inspection views preserve all 2,506 pairwise transforms per view.
The UI correctly marks inherited findings as needing a fresh review; original
step prose can still describe the parent's now-corrected conflict. Use the new
evaluation for current diagnostics rather than interpreting the inherited 518
displayed findings as 518 current physical defects.

The first final-revision evaluation retained metrics but could not start its
browser renderer because loopback binding was denied. Its failed render receipt
is preserved. A separate evaluation in `correction-02-evaluation-rendered/`
successfully rendered 15 microsteps from the refresh boundary and retains 20
comparison cards, including unchanged-prefix and unresolved records. These use
a labelled overview camera when source alignment is unavailable. Successful CLI
exit alone was not accepted as proof of rendered comparisons.

Current deterministic diagnostics are untruncated: 328 bounding-box overlap
candidates and 22 near-connector gap observations across snapshots; the final
snapshot has 48 bounding-box candidates. No exact-pose duplicate, undeclared
historical movement, scoped floating-piece or occupied-connector finding is emitted.
These are detector results, not certified collision, floating-piece or visible-gap counts.
The first assisted revision exhausted the 512-finding cap, so its totals are
lower bounds and its empty final-step diagnostic list cannot be compared as zero.
No new alternatives are generated by this command-only pass; alternatives remain
in the immutable raw and first-correction archives, whose totals are partly unknown.

Private preview: `http://127.0.0.1:4179/`. Frozen revisions, full comparisons,
before/after images, raw failures and review receipts remain under the experiment
evidence directory.

Independent agent source review inspected all 20 final comparison cards and all
four inspection views. The unchanged rubric yields **9 pass / 0 fail / 1 unknown**
relationships and **31 pass / 0 fail / 1 unknown** clauses. The three wing-placement
clauses that failed in the first assisted revision now pass; the central-body and
roof corrections remain intact. The exact source-aligned main-2 outline stays
unknown. All 16 required semantic events are represented; the bookkeeping remains
14 processed / 11 reconstructed indexed panels, rather than relabelling unresolved
records as successful generations.

| Revision | Relationship pass / fail / unknown | Clause pass / fail / unknown | New calls | Calls charged |
|---|---:|---:|---:|---:|
| Unaided control | 9 / 0 / 1 | 31 / 0 / 1 | 63, including indexing | 63 / 100 |
| Unaided prompt challenger | 7 / 2 / 1 | 29 / 2 / 1 | 52 | 60 / 100 |
| Assisted later-view restart | 8 / 1 / 1 | 28 / 3 / 1 | 21 | 81 / 100 |
| Assisted localized replay | 9 / 0 / 1 | 31 / 0 / 1 | 0 | 81 / 100 |

The challenger branch's eight indexing calls were performed by the control and
charged to both comparison budgets. Actual inference across this complete
experiment totals 136 calls, not 144. The two assisted passes share the original
challenger's 100-call ceiling; they do not receive fresh budgets.

The final candidate repairs two failed body/roof clauses relative to its unaided
parent, and three failed wing clauses relative to its first assisted parent. The
control and final correction tie on this coarse source rubric. The control's
undeclared 20-LDU historical movement is absent from the final candidate. These
observations support specific corrections, not a general accuracy percentage,
autonomous-engine superiority or production-alpha superiority.

## Remaining issues and next bounded experiment

1. **Hidden seating and exact geometry.** Source-visible arm placement is repaired;
   exact underside engagement and the lower-body/wing contacts still need focused
   source/geometry checks. Full per-instance placement and grouping scores lack an
   independent reference. Forty-eight final broad-phase overlaps are unresolved
   collision candidates, not proven physical clashes or clearance.
2. **Part and colour ambiguity.** Source-supported counts still match 26 identities
   and 22 colours; 6 identities and 10 colours remain unscored. Retain candidates
   until callout crops and individual-part shape comparisons resolve them.
3. **Index and sequence bookkeeping.** The shared automatic index includes a
   completed-model thumbnail and redundant panels. All required events are
   represented, but three processed records do not produce new reconstructions.
   Improve semantic panel assignment without rewriting this run's history.
4. **Camera and diagnostics.** The main-2 outline is not evaluable with current
   registration. Full narrow-phase collisions and physical building were not run.
   Symmetry-aware duplicate detection should catch identical whole-part geometry
   even when equivalent shapes have different quaternions. Inherited findings and
   original prose remain historical evidence and can describe repaired problems.
5. **Automatic repair focus.** Prioritize localized, deduplicated current-step and
   affected-group feedback in the next isolated mechanism test. The measured
   75.2% prior-only repair findings and 88.3% bounding-box warnings support this
   choice. Then test receiver-position diversity separately; search around one
   model-selected receiver cannot recover an omitted attachment alternative.

Keep the same model, raw/control separation and finite budget for the next test.
The opt-in prompt remains available for reproducibility; the default is unchanged.
No third correction pass or held-out inference was run in this iteration. Human
review and physical building remain `not_run`; publication was not performed.

## Software verification

- All 652 backend tests passed for the raw prompt experiment. After the correction
  controls, all 682 backend tests pass; no failures or skips.
- Schema export, touched-file lint and whitespace checks pass.
- Independent review reproduced byte-identical baseline requests and confirmed
  that only initial/repair proposal wording changes under the opt-in profile.
- Resume drift is rejected before inference, correction forks preserve the
  profile, and strict execution rejects this exploration-only profile.

These checks establish implementation behavior, not reconstruction correctness.
Both raw runs and the two assisted corrections are complete. Their source scores
remain separate; the raw challenger stays an unsuccessful prompt trial. Human
review and physical build remain `not_run`.

The final correction integrity audit verifies both raw jobs, both correction
parents, rows/events and all three frozen code manifests unchanged. Independent
command replay reproduces the final scene exactly. The successful render retry
has 15 new frames, 17 available after images, 20 cards and 70 verified PNGs. The
earlier failed render remains separate. See
`var/evidence/fixed-model-30669-20261004/final-correction-integrity-review/README.md`.

The final source review and every source/render card are retained in
`var/evidence/fixed-model-30669-20261004/correction-02-source-review/`.
Its `report.json` SHA-256 is
`c7c9817c0be2952f42226ea804d59f605941fbe4083be91ae7e290642f3f5677`.
The initial raw pair remains in `paired-comparison/`; correction comparisons are
in `assisted-paired-comparison/`. Before/after evidence is diagnostic and explicitly
distinguishes overview cameras from the source-aligned prefix investigation.
Start with `assisted-paired-comparison/INDEX.md`: it links every raw-to-corrected,
correction-to-correction and control-to-final frame. All 11 targeted snapshots
have before/after images. The final comparison verification checks 254 manifest
files, 231 PNGs and 742 local HTML links, retaining unmatched frames explicitly.
An incomplete control-to-final mapping attempt was rejected and remains excluded;
the complete comparison preserves its different semantic contexts separately.

To reopen the final private preview:

```sh
.venv/bin/python tools/preview_engine.py 9612c61e92004355a68cfd0645dac759 \
  --data-dir var/experiments/fixed-model-30669-20261004/attachment-data --port 4179
```
