# Engine efficiency — 4 October 2026

This implementation keeps the existing provider/model choices and SceneV2 viewer contract.
It does not regenerate, replace or publish saved models. All local web applications remain
stopped. New exploration jobs use an explicit `incremental-v1` efficiency profile; existing
jobs with no profile retain their frozen legacy prompt and repair policy.

## Implemented changes

| Change | Behaviour and boundary |
|---|---|
| Actionable repair selection | A missing renderable proposal, checked current contract defect or typed current source-visible defect can request one targeted repair. Camera residuals, unsupported checks, generic doubts and historical findings alone retain their findings and continue. Unnumbered attachments do not become numbering defects; explicit parent numbers remain checked separately from callout labels. The existing one-proposal/one-repair cap and whole-booklet progression remain. Source comparisons and camera diagnosis still run. Decisions bind source, policy, original trials, budget, affected pieces/groups and unresolved findings; resume verifies them. |
| Smaller exact assembly input | The model receives shared identity/source tables and exact packed poses instead of repeated field names and IDs. Every stable physical ID and current pose remains available when receivers are unknown. Nested child members transfer into an unambiguous receiving group; unknown membership retains full inventory/pose context and explicit uncertainty. Spatial omission requires an exact source-bound receiver scope, supported neighbouring geometry and complete rigid groups; ordinary fresh proposals conservatively send the complete packed state. Same-instruction repair input repeats only new or changed poses. |
| Incremental diagnostic checks | A single hypothesis search can reuse its unchanged, verified prefix across alternatives. Every new snapshot still checks the complete accumulated assembly. Prefix/source/part/group/scope/geometry incompatibilities and unsupported or unfenced mesh-proof-bearing prefixes use full diagnosis. The cache is bounded, invocation-local and closed at exit; standalone diagnostics remain full. Findings, counters and candidate ranking remain equivalent in the measured replay. |
| Lightweight durable checkpoints | Newly saved SQLite checkpoints reference immutable, private, content-hashed candidate files. Public reads hydrate the same checkpoint/SceneV2 value and verify candidate bytes. Legacy inline rows stay readable without migration. Candidate publication precedes the fenced SQL update; previous revisions and evidence remain. Heartbeat, queue and lineage-control reads avoid candidate hydration. Preview caches invalidate on both database and candidate-file changes. |
| Bounded independent-set scheduling | `--workers 2` explicitly permits two different sets; default is one. Transactional claims enforce the global bound and exclude simultaneous booklets/revisions of the same set across CLI processes. Alpha continuation booklets wait for their completed predecessor. Only the selected predecessor is hydrated. Ctrl-C or provider pause stops further dispatch and retains active accepted checkpoints as paused; stale-worker cancellation releases the expired owner. Command-local progress summaries reuse unchanged jobs; final reports verify candidates again. |

Strict assembly verification, source/geometry integrity, resource limits, historical evidence,
human/physical-review labels and publication gates remain in force. No new dependency or service
was introduced. These changes do not add inference to production playback.

## Offline measurements

| Scope | Before | After | What this establishes |
|---|---:|---:|---|
| Aggregate assembly context across 14 retained pilot instructions | 60,005 bytes | 45,195 bytes | 24.68% less assembly input, with exact inventory/pose/source replay. |
| Complete initial proposal prompts for those instructions, including new decoder text | 1,402,221 bytes | 1,394,719 bytes | 7,502 fewer bytes (0.535%). This is not a measured token or model-runtime reduction. Some small contexts grow. |
| Retained main-4 diagnostic contact computations | 504 | 217 | 205 unchanged historical snapshots reused across 41 alternatives; complete results and finding/coverage counts match. |
| Median local main-4 search time, three alternating measurements | 0.9905 seconds | 0.8725 seconds | 11.9% less local search time on this replay. Both paths already include the earlier catalogue cache. |
| Synthetic 64-piece/80-snapshot SQL checkpoint payload | About 436 KB per save | 480–481 bytes per save | 99.89% smaller SQL row payload, excluding candidate artifact bytes and filesystem/SQLite overhead. |
| Synthetic 128-piece/160-snapshot SQL checkpoint payload | About 1.76 MB per save | 482–483 bytes per save | 99.97% smaller SQL row payload; repeated unchanged candidates do not rewrite the immutable artifact. |

The first compact-context format increased pilot assembly input by 28.9%; its failed measurement
is retained alongside the revised format. The earlier 25.3% context / 0.65% full-prompt result
is preserved; the figures above include the final nested-membership fix. Diagnostic replay kept all 64 placement evaluations,
eight retained alternatives and three render candidates; its complete output SHA-256 is
`2abd70164c1dab7e891ffba2613d72c0fb2747367a5ddb63cbbe7e81a51bbb67`.

These are retained-trial and original synthetic measurements with **zero new provider calls**.
They do not establish a new unassisted reconstruction, improved assembly accuracy, full-booklet
throughput, physical fit or a speed estimate for each remaining set. The full comparison must keep
the same source, model, reasoning and call ceiling and measure one major mechanism at a time.

## Usage

Create a new exploration revision; this only enqueues it:

```sh
.venv/bin/python tools/engine.py enqueue --set 30669 --guide alt-02 --execution-policy explore --efficiency-profile incremental-v1 --model gpt-6-astra --reasoning high --max-model-calls 100 --revision efficiency-01
```

`--efficiency-profile legacy` retains the original context/repair policy. Strict jobs retain
legacy prompt behaviour. Changing a frozen job's profile on resume is rejected; use a new revision.

When generation is requested, independent-set queue execution is available with:

```sh
.venv/bin/python tools/engine.py run --max-jobs 0 --workers 2
.venv/bin/python tools/alpha_campaign.py run --workers 2
```

These commands are documented, **not executed by this implementation**. Existing alpha campaign
jobs retain their recorded model/effort/attempt settings. Their batching policy is unchanged; the
new repair/context profile currently applies to exploration, while checkpoint and scheduling
changes support both paths. A target `--job-id` uses one worker; instructions inside a booklet
remain ordered. Provider capacity can limit concurrency gains.

## Evidence and verification

Evidence is private under `var/evidence/engine-efficiency-20261004/`:

- `before-pins.json`: pre-change saved scene/source hashes and logical rows for both live databases.
- `incremental-profile/postfix-01/`: final nested-membership fix, unchanged-source context replay,
  hypothetical repair eligibility, focused tests and exact implementation/source pins. Original
  failed/revised packing evidence remains at `var/evidence/overhead-cleanup-20261004/incremental-profile/`.
- `diagnostics/`: executable retained-trial replay, individual report equivalence, timings,
  unchanged geometry inputs, source reconstruction and focused tests.
- `checkpoints/`: actual synthetic SQL bytes, legacy size survey, immutable candidates and
  corruption/fencing/contention tests.
- `independent-review/`: actual offline two-worker Ctrl-C/quota repros, expired-worker
  cancellation before/after, nested-group and unnumbered-attachment failure/fix reproductions,
  source-guided correction restart and completed correction resume. No actual model/provider calls or app servers.

The final `.venv/bin/python tools/check.py` passed **1,043 backend tests**, **52 frontend tests**,
schema drift, Ruff, TypeScript and build checks (`integration-check-final.log`). Independent final
context/repair review passed 119 focused tests and left no blockers in its inspected scope.
The existing Starlette deprecation and frontend chunk-size warnings remain non-fatal.
The opt-in policy binds internal context/repair versions v2 and `indexed-parent-sequence-v1`;
older policy receipts cannot silently resume with these changes.

`preservation-verification.json` confirms all 40 pinned saved scene/source files and all 24 live
job rows in both databases retain their exact pre-change hashes. `final-listeners.txt` confirms
the known Guide2Build app ports remain closed. Historical failed trials and earlier measurement
manifests are retained. No live queue was enqueued, migrated or run for this implementation.

Final integration results and preservation verification are recorded in `PROGRESS.json`,
`VALIDATION_REPORT.md` and this evidence folder. New browser interaction is not run in this slice,
preserving the user's stopped-local-app request; SceneV2/API compatibility and saved scene bytes
are checked offline. Human assembly review and physical build remain `not_run`.
