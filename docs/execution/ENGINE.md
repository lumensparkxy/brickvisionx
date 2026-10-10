# BrickVisionX local Google ADK engine

Current runtime (10 October 2026): Google ADK LlmAgent + Runner, Gemini Developer API, no application Codex execution. Configure backend GOOGLE_API_KEY in ignored .env. New jobs freeze provider/model/thinking/deadline/request ceiling. Default gemini-3.8-flash, medium, 120 seconds, three requests total including failures, retries, cancellation and inherited correction lineage. No hidden SDK retries or provider fallback.

Starter integration check: `uv run python tools/adk_smoke.py`. It indexes one verified official page and retains evidence without reconstructing or publishing an assembly. Starting the web application or ordinary checks makes no inference calls.

Full engine experiments use `enqueue --thinking-level medium --provider-timeout 120 --max-model-calls 3`; model is configurable with `--model`. Use a new revision to change runtime or budget; alpha runtime mutation is no longer available. Historical jobs retain their recorded runtime evidence and cannot be resumed through a different provider.

Explicit `--provider-timeout none` disables the app and SDK invocation deadline
for a new revision while preserving cancellation and frozen runtime settings.
Google server deadlines and quotas still apply. A fresh exploration revision can
use `--share-budget-with ORIGINAL_JOB_ID` to preserve the aggregate ceiling across
the same verified source, model and thinking level; this starts with fresh model
evidence. The selected root must be inactive and have budget left. For the
isolated Shuttle command, see [SHUTTLE_TERMINAL.md](SHUTTLE_TERMINAL.md).

See README.md and docs/migration/VALIDATION.md for current setup and evidence. The following source-era record is historical; its Codex commands, model identifiers, permissions and previous results are not the new ADK runbook.

---

# Local batch engine

Routine development checks: `.venv/bin/python tools/check.py --quick` runs selected regressions and
frontend type checks/tests. The no-flag command retains full CI/release validation. See
[test-suite optimization](TEST_SUITE_OPTIMIZATION.md). Tests are separate from generation and playback.

Latest maintenance: [engine efficiency changes and measured limits](ENGINE_EFFICIENCY.md),
following the [generation and local overhead cleanup](OVERHEAD_CLEANUP.md).
New exploration jobs default to `incremental-v1` for exact compact context and actionable
repair selection; frozen legacy jobs retain their policy. Searches reuse unchanged verified
diagnostic prefixes, new checkpoints reference immutable candidates, and `--workers 2`
explicitly schedules independent sets. Candidate limits, source checks and model settings
remain unchanged. All local web instances were stopped at the user’s request on
4 October 2026; saved scenes remain available for a later preview restart.

The private Python engine runs source indexing and fresh Codex CLI proposals. It never loads authored
reference scenes. Only official page images, its own earlier proposal checkpoints and verified individual
part geometry are supplied as assembly/geometry inputs. It is separate from the public portal API.

## Complete-booklet improvement runs

Use `explore` to retain imperfect renderable proposals and continue through quality findings. `strict`
remains the default. Both policies require intact official source evidence, valid SceneV2 structure,
actual individual geometry and bounded resources. Exploration never grants publication or validation.

```sh
.venv/bin/python tools/engine.py enqueue --set 30669 --guide alt-02 --execution-policy explore --model gpt-6-astra --reasoning high --max-model-calls 100 --revision YOUR_NEW_REVISION
.venv/bin/python tools/engine.py run --job-id JOB_ID
.venv/bin/python tools/engine.py evaluate JOB_ID --reference var/evidence/accuracy-30669-20261004/source-reviewed-combined.json --baseline var/evidence/accuracy-30669-20261004/baseline/scene.json --output var/evidence/NEW_EVALUATION
```

The targeted `run` processes only that job, including a paused correction fork. Exploration permits one
initial proposal and at most one targeted repair per indexed instruction panel, including its callouts. Camera,
connection, overlap, coverage and visual-review findings remain diagnostics. A source camera that cannot
be fitted falls back to a labelled overview; its silhouette cannot establish source agreement. An
instruction without a renderable proposal remains unresolved while subsequent instructions are processed.
The preview and evaluation report distinguish instructions processed, instructions reconstructed and
individual snapshots. A complete processing pass is not a correctness claim.

The model and reasoning setting are frozen in each job. The model-call ceiling includes indexing,
proposal and comparison calls and is inherited by correction forks. Reserved interrupted calls consume
budget; recovery does not silently repeat them. Authentication or provider availability failures and
resource exhaustion remain operational stops. They do not erase the retained candidate or findings.

Fresh exploration jobs can explicitly select `--review-profile localized-source-v4` and
`--new-part-failure-profile new-design-rejection-v2`. The review profile supplies bounded physical
instance/source context and requires distinct named observations when comparing localized defects.
Unlocalized or incomplete comparisons remain incomparable. The new-part profile retains an explicitly
classified unsupported shortcut as a rejected new design, permits the single targeted re-identification
repair, then continues unresolved when necessary. Source, hash, path, licence, material, accepted-part
and resource integrity failures remain operational stops. These opt-in profiles do not change existing
job policies or reset shared budgets; direct correction commands cannot silently change profiles.

Fresh exploration jobs can also select `--source-reference-profile exact-source-v1`.
Structured proposal source hashes and page indexes are constrained to the verified current
PDF/page in the output schema and bound to the existing request/receipt digest. Returned and
cached payloads are validated without rewriting them. Opaque `delta_json` source fields still
use the unchanged independent integrity checks. Legacy is the default; absent controls keep
legacy request bytes and policy bindings. A correction may introduce this profile only with
an explicit `restart_main_step`, creating an assisted child with the inherited call ceiling.
Provider schema failures retain their existing `invalid_output` handling. This prevents a
specific structured transcription error; it does not establish assembly accuracy.

Resume verifies a complete checkpoint-bound source page cache before repeating PDF preflight. It
requires the same PDF, page bytes, dimensions, renderer parameters and resource limits; missing or
untrusted proof follows ordinary validation. Historical recovery checks cancellation between receipts
and instruction results. A single stalled operating-system read remains outside those cancellation
boundaries. These availability changes preserve evidence and do not demonstrate an accuracy gain.

Evaluation annotations are separate inputs for scoring. A previous assisted candidate is a comparison
baseline, not independent ground truth. Unannotated identity, colour, placement and grouping values remain
unknown. Keep source-reviewed annotations out of the unaided generator's inputs.

The current exploration contract is `source-exploration-v4`. Candidate selection compares
current-instruction concrete defects first, then compatible camera evidence. An honest uncertainty
note is not a penalty; equivalent physical scenes retain their combined uncertainty. Missing reviews,
ties and incomparable alternatives stay explicit. Old near-white silhouette scores cannot rank
candidates: blue booklet and grey viewer backgrounds inflated those values. The new masks estimate
border background, retain segmentation uncertainty and reject ambiguous/clipped/multiple-object
comparisons. Image scores require a common source, crop, exclusions, mask policy and registered
camera basis. An unscorable mask retains a fitted camera; only unavailable camera registration
requires an overview.

Snapshot visibility means presence in the assembly workspace, including pieces hidden behind other
pieces. Source-pixel visibility is separate. Detached callouts may use their own workspace; active
pieces identify new/moving/emphasized pieces rather than every visible instance.

Policies and provider receipts are revision-bound. An older v2 run is preserved and cannot silently
resume under a changed v3 contract. A new correction fork records the old/new policy hashes and
inherits the shared budget. The first completed pilot used v2. A subsequent fresh v3
baseline and a shared-index prompt challenger both completed; their results and limits
are recorded in [`FIXED_MODEL_ACCURACY.md`](FIXED_MODEL_ACCURACY.md).

```sh
.venv/bin/python tools/engine.py fork-correction JOB_ID --request var/evidence/CORRECTION.json --revision accuracy-30669-repair-1
```

Correction requests bind the exact parent scene hash and official source evidence. They either apply
explicit mapping, pose, rigid-group, attachment-grouping or landmark corrections, or restart at a main instruction with localized
findings and later official views. At most two correction passes are allowed. Derived revisions preserve
the parent's scene, prompts, render evidence and findings; descendant snapshots are regenerated. Corrected
results retain their assisted lineage and do not replace the unaided result. Human review and physical
build status remain separate.

Source-guided requests (`restart_main_step` plus `guidance`, with no commands) also accept:

- `context_page_indexes`: up to two unique zero-based page indexes, each cited in
  the request's official `evidence`. Their order takes priority over the default
  sorted later-page context. The target remains the first image; duplicate target
  or previous-page images are omitted. This selects the later views that expose
  the defect without supplying a finished assembly.
- `max_panel_attempts`: either 1 or 2, never greater than the parent's normalized
  exploration cap. Use 1 to spend at most one proposal and one visual-review call
  per remaining panel. It does not reset or increase the shared model-call budget.

Both controls are optional and recorded in correction lineage. Omitting them keeps
existing behavior and request hashes. They are rejected for direct correction commands.

An `op: "grouping"` command takes `step_id`, `group_id`, `reason` and `evidence` (the attachment's
official `SourcePanel`). It changes only an `attach_subassembly` snapshot's group label to an existing
earlier declared detached group. All group members must be visible and its receiving workspace must be
unambiguous; unknown, incomplete or already attached groups are rejected. Grouping corrections do not
change poses. When several labels are wrong, list their `grouping` commands in instruction order before
any `group` pose commands, so rigid replay uses the corrected membership. Each correction invalidates
dependent checks; evaluating the new revision refreshes affected renders without changing parent evidence.
Unchanged prefix images may be reused only after scene, image and lineage verification. Every changed
snapshot is rendered again. For before images, `--baseline` should point to a scene beside its original
render receipts (for example the pinned parent job's `scene.json`); a scene-only export remains valid
for numeric comparison but has no before pixels. Evaluation writes a new directory and prints a compact
summary with paths to the full JSON report and source/before/after HTML.

The completed first iteration and exact local preview commands are in
[`ACCURACY_ITERATION.md`](ACCURACY_ITERATION.md).

## Fixed-model prompt comparison

`enqueue --proposal-profile attachment-reasoning` opts an **explore** job into the
generic `attachment-reasoning-v1` proposal guidance. It clarifies complete physical
group membership and source-supported receiving faces, targets and connector alternatives.
It contains no set-specific part IDs, poses or accepted answers. The index/review prompts,
schema, solver, rendering, ranking and resource limits are unchanged. The default
`baseline` preserves existing request bytes and job deduplication.

```sh
.venv/bin/python tools/engine.py enqueue --set 30669 --guide alt-02 --execution-policy explore --model gpt-6-astra --reasoning high --max-model-calls 100 --proposal-profile attachment-reasoning --revision YOUR_NEW_PROMPT_EXPERIMENT
```

The profile name, version and exact prompt hash are recorded in the exploration policy.
Changing them during resume fails before inference; use a new experiment instead.
Correction forks inherit the selected profile and keep their assisted status. A prompt
profile cannot be enabled for strict jobs. This option creates no production LLM usage
and does not publish a candidate.

The current comparison freezes the baseline implementation and initial source/individual-part
cache. A paired run may reuse the baseline's authenticated automatic **source index only**,
with its original indexing calls charged to both budgets and its reuse disclosed. No
assembly, corrected pose or scoring annotation belongs in that input. Report such a
comparison as shared-index assembly generation; a new end-to-end indexing trial is a
separate measurement. Keep actual new calls, reused index calls and total charged calls
distinct. See `var/evidence/fixed-model-30669-20261004/experiment.json` for run bindings.

`enqueue --proposal-profile event-scoped` selects `event-scope-v1` for a fresh explore
revision. It limits the proposal to the requested panel and explicitly listed callouts,
permits an ambiguous region to remain unresolved without constructing its neighbours,
and explains the existing sequence/action/group contract. All replacement and appended
wording is hashed in the policy. The queue, source checks, solver, renderer and call limits
remain unchanged; baseline and attachment-reasoning requests retain their original bytes.
This is prompt guidance, and its accuracy effect must be measured from actual output.

## Run

Use the existing project virtual environment (or `uv run --extra dev`). Codex must be installed and
`codex login status` must report ChatGPT authentication. No paid provider API fallback exists.

```sh
.venv/bin/python tools/engine.py enqueue --all --revision campaign-1
.venv/bin/python tools/engine.py run --max-jobs 1
.venv/bin/python tools/engine.py status
.venv/bin/python tools/engine.py report
.venv/bin/python tools/engine.py watch
.venv/bin/python tools/engine.py watch --sync-cloud --project lumensparkxy
.venv/bin/python tools/engine.py cancel JOB_ID
.venv/bin/python tools/engine.py retry JOB_ID
.venv/bin/python tools/engine.py retry JOB_ID --reset-candidate
.venv/bin/python tools/engine.py resume --provider
.venv/bin/python tools/engine.py resume JOB_ID
```

`enqueue --all` installs a campaign gate: only 30669/alt-02 runs until a validated pilot has been packaged.
Other jobs remain queued, not falsely tested. Explicit `--set NUMBER --guide ID` supports individual jobs.
`--revision` creates a distinct experiment; repeated identical requests deduplicate. Source receipts,
model, pipeline version, part-cache revision and experiment identity are included in CLI fingerprints.

Watch runs only while the computer/process is active. SQLite (`var/engine/jobs.sqlite3`) provides durable
checkpoints, one globally leased job, fencing and crash recovery after a 120-second lease. A heartbeat
renews every five seconds. The optional cloud sync runs independently every 300 seconds even during a
long job. It uses uploader impersonation and the dedicated `guide2build-requests` database, filters eligible
requests and leases them transactionally. Unknown sets become `source_discovery_required`, never a guessed URL.
Authentication is optional for local-only commands. Cloud errors do not erase or stop local work.

Each model call defaults to a fifteen-minute deadline (900 seconds), a 20 MB result limit and 32 MB
event-log bounds. Alpha jobs retain explicit `provider_timeout` overrides; the actual deadline is recorded
in each call's `request-runtime.json`. Invalid proposals get up to three attempts per unit; explicit retry
retains earlier attempts. Authentication, quota and unavailable
provider failures pause inference globally until `resume --provider`; no credits are purchased automatically.
Subscription reset times are not guessed. Model subprocesses use a temporary non-repository cwd, read-only
sandbox, forced ChatGPT auth, disabled model tools/plugins/hooks/browser/memory and an environment allowlist
that excludes API keys, cloud credentials and parent-agent state. The CLI itself retains access to its normal
ChatGPT authentication mechanism. Do not use `danger-full-access` to work around an inference failure.

## Evidence and completion gates

### Guided one-instruction operation

After enqueueing a fresh experiment, run:

```sh
.venv/bin/python tools/engine.py step JOB_ID
```

The first call indexes the official booklet, then attempts at most one new main instruction,
including its substeps. Success saves the candidate and releases the lease in `paused` state;
ambiguity or provider failure records a blocker. Inspect the source and candidate before running
the same command for the next instruction. This is a candidate checkpoint, not validation or approval.
Ordinary `run`/`watch` do not select paused jobs. The targeted command never falls back to another job
and respects the global lease, provider pause and campaign gate. A blocked job still requires explicit
retry/resume after its cause is addressed. Calling `step` after construction is complete pauses with
`construction_complete_needs_validation`; it does not silently enter whole-booklet review.

Fresh guided 30669/alt-02 job `4623deafb567466e8b1f97bb512881c0` was verified queued with an empty
checkpoint on 2026-10-03. No inference was started while adding this control. Synthetic tests verify
indexing, one-instruction boundaries, checkpoint preservation and job selection; they do not establish
official reconstruction accuracy.

Each job directory retains source receipts, page indexes, prompts, raw JSONL events, structured responses,
invocation durations/CLI-reported usage, proposals, rejected candidates and geometry provenance. Token counts
are reported only when the CLI actually returns them. Subscription monetary cost is not inferred from tokens.
Automatic source indexing remains `automatic_unverified`; matching a known 12-step count is not proof of every
substep or a complete reconstruction. A page is not a step.

Proposals are append-only deltas: new sections, new physical instances and new snapshots with only new/moved
pose updates. The engine reconstructs unchanged poses and preserves historical snapshots deterministically.
Model context contains current physical IDs/poses, not full snapshot history. Source indexing sends only the
previous page and section names; rendered review sends only page-local changes. Current-state context is capped
at 400 KB and total prompts at 1 MB. Assemblies beyond that need spatial partitioning; the largest sets have
not been validated and are not silently sent as unbounded full-history prompts.

Fresh snapshots are bound to the requested source page and printed main step, use stable physical IDs and
cannot rewrite earlier checkpointed snapshots. Rivendell books 2/3 require a validated staged predecessor and
carry forward its sources, sections and physical IDs; they do not start as unrelated models. Other alternate
builds/car booklets remain independent. Missing or blocked predecessors block continuation explicitly.

Individual geometry downloads use the existing allowlisted resolver into a per-job cache; shared portal assets
are not overwritten. Dependency hashes and actual geometry existence do not prove placement or connections.
Current resolver bounds can still block large/unsupported part closures; such failures remain visible.

```sh
.venv/bin/python tools/engine.py render JOB_ID --output var/evidence/NEW_RENDER_DIRECTORY
.venv/bin/python tools/engine.py validate JOB_ID --bundle var/evidence/INDEPENDENT_VALIDATION
.venv/bin/python tools/engine.py package JOB_ID --output var/releases/NEW_RELEASE_DIRECTORY
```

`render` calls the actual loopback Three.js renderer and verifies its scene and PNG hashes. Complete candidates
also render before independent model review receives original pages **and** actual model images. GPU values
from SwiftShader are software-renderer measurements, not native-M3 GPU benchmarks. Renderer failures cannot
qualify as review passes.

`validate` imports `validation-bundle.json`, whose strict schema is defined by `engine.validation.ValidationBundle`:

- `candidate_sha256`: canonical hash of the exact untouched SceneV2 proposal.
- `source_index`: independently verified source hashes and expected section/step keys, in the release packager's
  format; it must agree with the trusted source registry and candidate coverage.
- `connector_report`: matching scene hash, named/versioned deterministic checker, pass/fail/unsupported,
  supported physical IDs and hash-verified evidence files. Every physical instance must be supported.
- `assembly_report`: matching scene hash, named agent reviewer, source/render comparison report (no unverified camera-matching claim),
  actual render report file and one passing source-page/render-image comparison for every microstep.

Relative evidence files are root-confined, byte-bounded and hash checked. Compared source-page hashes must
match the locally retained official rasters. Source PDF receipts and the entire geometry closure are verified
again. Browser reports must match an engine-recorded render receipt. Human actor labels are rejected here;
authenticated tutorial publication approval remains a separate operation.

**Current deterministic-checker gate:** the closed registry has no general assembly checker. The legacy
authored first-four-step helper cannot certify complete automatic scenes and is deliberately not registered.
Validation rejects unsupported checker IDs and reruns registered code; caller-provided pass flags and arbitrary
evidence files can never grant geometry/connector success. Implementing and independently testing a general
checker remains required before the pilot or any other full tutorial can pass this gate.

Successful import writes a separate `validated-scene.json` (only deterministic check flags differ), release
validation and an immutable-by-hash validation receipt. The raw candidate remains unchanged. Packaging checks
that the candidate, bundle and evidence have not changed, then delegates to the fail-closed release packager.
Only successful packaging marks `awaiting_approval` and unlocks the campaign. It does not upload, approve or
publish anything. The engine has no publisher authority.

This interface supports a real validation handoff; it does not manufacture a general connector checker.
Unsupported connectors, missing independent coverage or missing matched render review remain blockers until
appropriate independent evidence is produced. JSON-only model critique cannot certify a release.

## Recorded implementation experiment (2026-10-03)

19 catalogue jobs were enqueued. Only the 30669/alt-02 pilot ran; the other 18 are gated/queued.
Real subscription-authenticated structured image calls succeeded after an outer sandbox restriction and strict
schema issue were diagnosed. The pilot indexed all eight pages and identified main instructions 1–12.
An initial construction call refused uncertain curved-part identity. Supplying verified individual-part geometry
allowed a three-piece step-1 proposal; step 2 then reported uncertain heights/rotations. Independent inspection
caught an in-range but wrong source-page reference in step 1. That candidate was quarantined, not silently fixed,
and the exact-panel guard was added before a bounded retry. See current `engine.py report` and the job directory
for the retry's final state. This experiment does not establish a complete tutorial or assembly correctness.

The old partial screenshot in `var/evidence/engine-pilot-render` binds the quarantined candidate hash and must
not be used as validation of a later revision. No human review, physical build or tutorial publication occurred.

Final bounded pilot retry: 2 of 12 main steps / 2 microsteps / 5 physical parts retained, both bound to the
correct official page. Step 3 stopped on the model's unresolved 25269 corner-round tile rotation. The delta
adapter's real structured call also returned that explicit blocker; it did not invent an attachment.
`var/evidence/engine-pilot-benchmark.json` records 16 model calls and 781.253 seconds of active model-call time
across indexing, failed proposals and development retries (332,807 input / 17,989 output tokens reported by
CLI, with reasoning tokens reported separately). This is a development experiment, not end-to-end completed-set
latency or a basis for extrapolating 100-page completion time. Monetary subscription usage is not reported.

The valid partial candidate has canonical hash `bafb5402e76e8a18e67a8986c71a1655d866fa6756a0345ba515d28032b2a2a7`.
Actual screenshots for both steps and rendering counters are retained under
`var/evidence/engine-candidate-render-bafb5402e76e8a18e67a8986c71a1655d866fa6756a0345ba515d28032b2a2a7/`.
They were visually inspected against the official page, but no connector or completed-assembly pass was granted.
The browser reported SwiftShader and no GPU timer support; native GPU benchmark status remains `not_run`.

### Context repair during requested resume

`codex-source-context-v3` retains the append-only contract and adds verified Subpart definitions to the individual-part context, within the existing byte budget. This repairs wrapper-only parts such as25269, whose shape is defined in `parts/s/25269s01.dat`. Definitions retain their hashes, depth/count limits and explicit truncation flags. No assembly coordinates or authored reference are loaded.

At a page boundary, construction receives the target official page first and the preceding instruction page second. The preceding page supplies orientation context only; new instance/step source references must still match the exact target page. These additions are evidence input improvements, not geometry/connector certification.

## Private local playground preview

To inspect a persisted engine job in the real portal, build the frontend and start the read-only preview:

```sh
npm run build
.venv/bin/python tools/preview_engine.py JOB_ID --port 4175
```

Open `http://127.0.0.1:4175`, enter the job's set number, and choose **Open candidate**.
The landing status reports the experiment, engine state, coverage and current blocker, including when
no candidate exists. The viewer loads the actual checkpointed SceneV2, verified individual geometry and
checksum-verified official source pages. Candidate identity is checked against the private checkpoint;
this does not import an authored reference, certify the assembly, create a release or publish a tutorial.
The server accepts reads only, binds loopback, and exposes selected in-memory asset snapshots rather than
the private job directory. Return to set lookup and reopen to load a newer checkpoint. The full-height
viewer retains candidate labels; job/experiment identity is in its reconstruction-details popover.

`codex-source-context-v4` adds bounded, hash-verified stud mesh-reference transforms derived from individual
part/subpart/stud-group files in canonical viewer coordinates. These landmarks are not certified connectors
or assembly poses. `v5` further instructs proposals to derive socket seating planes instead of aligning a
curved part's lowest outer edge to another part. These changes were motivated by a real rejected first-step
candidate with an 8-LDU seating gap; its raw proposal and screenshots remain in the playground evidence.
The known indexed panel count is now checkpointed before construction, including first-panel failures.

`codex-source-context-v6` adds a per-instruction visual gate. Each structurally valid proposal is saved
under `proposals/`, rendered with real geometry for its new snapshots, and independently compared by the
runtime model with the official page before it becomes the next checkpoint. A failed or ambiguous visual
comparison retains the raw proposal, rendered images and review but does not advance the candidate.
Active-piece semantics and image-relative attachment order are explicit in the construction prompt.
This adds actual image review, not a general connector checker: scene geometry/connector/physical flags
remain `not_run`, and review metadata remains agent evidence. The complete-booklet validation and packaging
gates still apply. `step` also performs this visual gate before pausing after one instruction.

## Alpha image tolerance (opt-in)

New jobs can use a less precise source-image fit for alpha experiments:

```sh
.venv/bin/python tools/engine.py enqueue --set 30669 --guide alt-02 --revision alpha-30669-01 --quality-profile alpha --max-panel-attempts 3
.venv/bin/python tools/engine.py step JOB_ID
```

Use the job ID returned by enqueue. `step` processes at most one new main instruction; it does not start
a web server. These example commands have not been run against the live queue in this tolerance change.

| Profile | Maximum landmark RMS | Maximum individual landmark error |
|---|---|---|
| `strict` (default) | 4 px | 12 px |
| `alpha` | 8 px | 12 px |

Pixels refer to the retained rendered source page, not the portal viewport. Source resolution, camera
ambiguity tolerance (0.75 px), named landmark requirements, part/connector/sequence checks and actual-render
visual review are unchanged. The profiles are engineering tolerances, not measured accuracy percentages.
Unsupported contacts, missing parts, wrong-side attachments and visible discrepancies still block.

The job fingerprint includes the profile. The checkpoint and per-instruction recovery receipt bind its
version and limits; changing an existing job's tolerance is rejected. Enqueue a new experiment rather than
resetting an exhausted strict job. Reports retain the strict fit result and exact errors for alpha-accepted
landmarks. Local previews label alpha candidates **Alpha sample · unverified**, including measurements in
the reconstruction details. An open older snapshot excludes measurements from future instructions.
No release, human acceptance or physical-build status is granted by alpha mode.

Offline replay of the saved instruction-2 proposal `69451c531c524ef5a5be037aad9f8a40` passes the alpha
landmark fit at 7.763342 px RMS / 9.859493 px maximum, but its actual fitted render is nearly edge-on and
does not match the booklet's above view. That proposal remains rejected; numerical fit acceptance alone
does not make it a suitable tester sample. No new inference or complete alpha booklet was generated here.
Evidence: `var/evidence/alpha-tolerance-30669-01/`. Local services remain stopped.

## Connection-based instruction repair (`codex-spatial-repair-v7`)

The local engine now separates model choices, deterministic placement, camera fitting, and image review.
A model-facing instruction proposal includes the existing append-only delta plus explicit connector pairs,
free assembly roots, printed sequence evidence, and named visible source landmarks. For ordinary additions,
`moving_group_ids` is empty. Only an attachment moves an entire previously constructed detached group.

`config/individual-connectors.json` describes 18 individual designs through 19 geometry records (including
the 3023/3023b alias), with 141 nominal frames. The original six records are preserved. The added records
cover the pilot's remaining plates, tiles, wedges and slopes, including 11477, 15573, 18980, 22385, 3040b,
3068b, 32028, 3623, 6636, 78443 and 78444. Unsupported cavities, rails, clips and other connector families
remain excluded. Each nominal connector and visible stud-cap landmark is tied to the actual individual-part dependency
closure and its hashes. Metadata contains no set assembly coordinates. It is agent-derived engineering
metadata, not physical measurements or human approval. Other part/connector families remain unsupported.

The solver computes mating-frame transforms and quarter-turn orientations, checks occupancy across visible
and hidden physical pieces, and retains rigid group membership across attachment and resume. Detached
callouts have separate coordinate workspaces until connected. Extra free roots, disconnected new pieces,
unsupported contacts, duplicate poses, nonrigid movement and extreme coordinates are rejected. Broad-phase
volume overlaps are retained as review candidates; narrow-phase intersection and insertion-path checks are
not implemented. Global scene geometry/connector/physical flags remain `not_run`.

Source observations identify visible stud-cap centers by catalogue landmark ID and full-page image UV.
The bounded orthographic fitter records every landmark residual, ambiguous alternatives and the declared
camera family. `upright_above` is an explicit source interpretation, never inferred just to lower an error.
The default gate is RMS <=4 original-page pixels and maximum landmark error <=12 pixels. Incoming pieces
shown displaced beside arrows must not serve as seated-world camera landmarks. The actual Three.js renderer
uses the fitted camera independently of assembly poses, preserves page aspect, and binds the requested camera,
actual camera matrices and screenshots to hashes. Landmark agreement does not certify hidden geometry.

New jobs may explicitly select `--quality-profile alpha` for RMS <=8 pixels, retaining the 12-pixel
individual-landmark bound, ambiguity gate and actual visual review. The profile is bound to the saved
configuration and receipts and cannot be changed on resume. Strict results are retained alongside alpha
results. A numerically passing edge-on render can still fail the source comparison. Preview UI labels
these samples unverified; relaxed image tolerance never grants assembly, human or physical approval.

The next proposal now receives compact prior-camera context from this job's last accepted snapshot:
named source pixels, resolved world landmarks and camera right/up axes. The reader verifies the current
scene receipt, source-view file hash, actual official page PNG hash/dimensions, visible IDs and individual
geometry. The active source is the last snapshot's booklet, which may differ from a continuation's primary
source. Missing legacy/rebased receipts supply no context; a matching but invalid receipt fails closed.
Old image coordinates cannot be copied into the new source figure, and previously visible studs may become
hidden. This context supports correspondence identity without prescribing new poses. Its live generation
effect has not yet been measured: the pilot stopped on colour uncertainty before the upgraded worker ran.

Each instruction has a persisted trial budget (default 3; configurable 1–5 on enqueue). Structured review
findings identify connection, side, sequence, mapping, coverage or source-view failures. A repair replaces only
the rejected instruction. Previously checkpointed snapshots never pass through model output again.
Ordinary printed instructions are single snapshots; numbered detached callouts and subsequent attachments
need explicit source sequence evidence. Printed callout labels must equal the labels shown by the viewer.

```sh
.venv/bin/python tools/engine.py enqueue --set 30669 --guide alt-02 --revision MY-NEW-REVISION --max-panel-attempts 3
.venv/bin/python tools/engine.py step JOB_ID
.venv/bin/python tools/preview_engine.py JOB_ID --port 4175
```

A normal retry retains the instruction budget. Exhaustion leaves a specific blocker and all trial evidence.
A reviewed trial is durably receipted before candidate promotion; recovery verifies source/history, proposal,
scene, render and review hashes without spending another model call. Candidates from older pipeline versions
require a new revision. Source indexing and schema-response retries have their own existing bounded counters.
Provider schema rejection is an engine `invalid_schema` failure, not an authentication/quota outage or reason
to pause unrelated jobs. Homogeneous tuple schemas are translated to supported bounded array schemas.

Per-trial evidence is under `var/engine/jobs/JOB_ID/proposals/TRIAL_ID/`: `proposal.json`, `raw-scene.json`,
`scene.json`, `spatial-validation.json`, `source-views.json`, actual `renders/`, `visual-review.json` when reached,
and `outcome.json`. Rejected trials are never served as accepted candidates. Accepted output is labelled
`automatic_connector_corrected_candidate`; it is not an unassisted success or an approved tutorial.
Whole-job validation reports retain the configured artifact kind and reused-evidence lineage, so an assisted
alpha continuation is not relabelled as an unassisted automatic conversion.

Fast alpha campaign commands: `.venv/bin/python tools/alpha_campaign.py status`; `.venv/bin/python tools/alpha_campaign.py run` (selected campaign IDs only, --skip-set may freeze source-assisted prefixes); `.venv/bin/python tools/preview_alpha.py --campaign-file var/evidence/alpha-ten-set/campaign.json` (read-only loopback preview, no publication/review authority).

`correct-empty-batch --set N --guide ID --source-review PATH` is a separately labelled agent correction for a rejected batch of genuinely noninstruction pages, never a way to reset inference attempts. The typed review must bind actual source/page hashes, actor and non_instruction classifications. The backend removes only false blockers, preserves all parts/poses/source observations and original trial/counter history, then normal receipt replay advances one batch with inference disabled. It cannot clear geometry/schema/security failures or grant assembly/human approval. `register-assisted` validates full source coverage, real individual assets and any accepted-prefix lineage, then leases the selected job for a frozen assisted import. Failed imports/corrections release their own lease and retain attempts.
# Accuracy mechanism update — 4 October 2026

Fresh exploration uses `source-exploration-v4`; fresh fast alpha uses
`source-direct-alpha-v2`. These versions freeze semantic source routing, localized
feedback, hypothesis/geometry diagnostics and the model/reasoning choice. Saved
scenes remain viewable; a frozen job cannot silently resume under a different
policy. New correction revisions carry authenticated canonical source-index seeds,
preserve legacy uncertainty and verify actual source pixels on resume. V2 parent
cursors must match the normalized event queue; incompatible legacy callout prefixes
require a restart from the first instruction.

The model remains `gpt-6-astra` / `high`. No inference is added to production
playback. Measured offline results, software validation and remaining accuracy
limits are recorded in `ENGINE_ACCURACY_IMPROVEMENTS.md`.

An exploration correction can carry at most two explicit `source_only_index_reviews`.
Each agent review must cite a whole official page and authenticate its unchanged empty
V2 index, cached PNG, failed request/receipt and exact nonzero process result with no
structured output. This admits only a retained `provider_unavailable` failure; integrity,
authentication, quota, nonempty-index and forged evidence failures still reject. The
canonical acknowledgement is stored separately in `source-index-reviews.json` and
authenticated through later correction seeds. It never replaces the raw source index,
removes its uncertainty, resets call counts or grants human/physical approval. Requests
without this optional field retain their previous canonical hash.


# Local engine activity logs — 5 October 2026

`run`, `watch` and `step` now emit timestamped INFO activity on stderr while keeping JSON results on stdout. A read-only observer polls existing durable events/checkpoints once per second: source indexing, model-call reservations/receipts, trial/render outcomes, repair decisions, provisional selections, saved coverage and blockers. Summaries distinguish processed instructions from reconstructed instructions and report source events including callouts when those counters are available. Findings are diagnostics, not accuracy or approval claims. Unknown counters stay `?`.

```sh
# Observe a job already running in another terminal, without starting a worker.
.venv/bin/python tools/engine.py --data-dir var/experiments/next-nine-20261005/data logs JOB_ID --follow

# One current progress snapshot.
.venv/bin/python tools/engine.py --data-dir var/experiments/next-nine-20261005/data logs JOB_ID

# Quieter future worker; global options precede the command.
.venv/bin/python tools/engine.py --log-level WARNING run --job-id JOB_ID

# Optionally retain readable activity in addition to the existing durable events.
.venv/bin/python tools/engine.py run --job-id JOB_ID 2>> var/engine-activity.log
```

A follower starts with the current saved progress and shows newly committed events; it does not replay old event history. It reports a long unchanged checkpoint at most every 30 seconds, labels an expired lease explicitly, and exits once the job is paused, blocked, cancelled or otherwise stopped with its lease released. Ctrl-C stops only the follower. It never claims, cancels, resumes, migrates or rewrites the observed job, and never opens candidate/source/render files. Prompt text, model response bodies and arbitrary error messages are excluded. Logging failures warn once and retry without stopping reconstruction. Logs describe saved phases; very short intermediate phases can be represented by their event messages before a later progress summary.

The current Terminal worker keeps its already loaded CLI. Automatic logs apply to new worker processes; use `logs --follow` to observe the existing job without a restart. No inference policy, model, budget, prompt, scene or viewer contract changed.
