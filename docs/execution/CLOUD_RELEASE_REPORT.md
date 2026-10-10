# Guide2Build cloud and batch implementation checkpoint

Date: 3 October 2026. This is an implementation/evidence report, not a claim that the 19 tutorials are complete or production-ready.

## Current outcome

The local queue, restricted Codex adapter, public portal, immutable release tooling and dedicated cloud resources are implemented. Real automatic image-based construction reached two of twelve main instructions in the pilot. No tutorial is eligible for publication and none has been approved or published. The other eighteen campaign jobs remain queued behind the pilot gate.

Public website: [https://guide2build-web-i2tso5lznq-ew.a.run.app](https://guide2build-web-i2tso5lznq-ew.a.run.app). IAM-private preview: [https://guide2build-preview-i2tso5lznq-ew.a.run.app](https://guide2build-preview-i2tso5lznq-ew.a.run.app). Both run the same verified image digest, built from local commit `c91669ec1dba0a0b01a938511ea6edb5d67fe2e8`. No tutorial was published.

An actual website recovery exercise deployed a second revision of the same digest, smoke-tested it, routed public traffic to it, and restored the original revision. Final smoke checks passed and the temporary test tag was removed. Evidence: `var/evidence/cloud-release/rollback-exercise.json`. Tutorial-content rollback is separate and remains untested with real approved content.

Final software checks: **159 backend tests, 34 frontend tests, 31 browser tests passed**; three opt-in benchmark tests skipped. Schema, Ruff, TypeScript and production build passed. The live desktop/phone smoke passed: durable request recording/readback, duplicate detection, private API 404s, private preview unauthenticated 403, and no PDF/crop requests or JavaScript errors. Authenticated local preview proxy returned 200.

A cold **browser-cache** portal sample took 1,012 ms; warm sample 34 ms under 40 ms latency / 5 Mbps download throttling. These are single landing-page readiness samples, with Cloud Run already warmed by health checks—not server-cold-start or 3D tutorial load benchmarks.

Evidence: `var/evidence/cloud-release/browser-live/report.json`, `persisted-requests.json`, `private-proxy.json`, `existing-resources-preserved.json`. Krishi's service spec/generation and default Firestore configuration are unchanged; rolling `earliestVersionTime` and its ETag advanced naturally between observations.


## Implemented and checked

- SQLite job leases/checkpoints, restart recovery, bounded retries, provider pause, cancellation, report commands and optional cloud-request synchronization.
- ChatGPT-authenticated Codex CLI in isolated read-only context with tools disabled and paid/cloud credentials omitted; no paid API fallback.
- Append-only construction deltas preserve previous physical IDs and snapshots. Current-state context has a 400 KB bound; full historical snapshots are not repeatedly sent.
- Source/section-aware SceneV2, numbering resets, unnumbered attachments, predecessor continuity for Rivendell. Complete three-book continuity has not been reconstructed in practice.
- Actual Three.js render evidence binds scene, geometry and PNG hashes. Validation rejects self-declared human review, arbitrary checker strings, stale renders and renamed fixtures.
- Compact release indexes retain navigation metadata and once-only introductions. Full visibility/active arrays and poses remain in hash-checked chunks. A 300-to-600-step cumulative synthetic stress test verifies approximately linear index size; it is not a LEGO correctness benchmark.
- Public entrypoint exposes availability, approved manifests and bounded/deduplicated requests. Drafts, source crops, corrections, reconstruction and approval routes are absent.
- Atomic published catalogue metadata lets newly approved sets appear without rebuilding the website. Unknown searches read one bounded cached catalogue, not arbitrary per-set database documents.
- Packaging allowlists exclude PDFs, source crops, prompts and credentials. Staging, remote hashes, exact-version identity-bound approval, compare-and-swap heads and rollback have software tests. Real tutorial staging/publication/rollback remains unexercised because no eligible candidate exists.

## Cloud resources and cost

Project `lumensparkxy`, region `europe-west1`, approved administrator `maswadkar@gmail.com`. Dedicated Firestore databases: `guide2build` for releases and `guide2build-requests` for intake, separated so the public portal cannot write approvals/releases. Dedicated staging/assets/build buckets, Artifact Registry and portal/builder/uploader/publisher service accounts are provisioned. Existing Krishi/default resources are retained.

Cloud Run configuration: request-based billing, minimum zero, maximum one instance per service, one CPU, 512 MiB. Image deployment is bound to Cloud Build's returned digest. The build context is explicitly allowlisted. The first Cloud Build failed on three omitted web build inputs; those inputs were added and an isolated upload-context build passed before retry.

A project-scoped **CHF 8.26/month** budget exists with 50%, 80% and 100% actual-spend emails to project owners. It covers the entire shared project, including Krishi, and is not a hard cap. Named Firestore, storage, downloads and builds can cost money while Cloud Run has no active instance. Evidence: `var/evidence/cloud-release/budget-console.json`, `budget-created.jpg`, `budget-currency.json`.

The uploader's actual credentials could read the requests database and received permission-denied for release/default databases. An extra temporary portal impersonation grant was rejected by automatic approval review as outside scoped privilege authorization; it was not added or bypassed. Read-only IAM inspection and deployed service behavior are used instead.

## Fresh automatic pilot

| Measurement | Observed result |
|---|---|
| Job | `e2d62e6aab434b70b202d93a9799a52c` |
| Source | Official 30669 alt-02, 8 pages, pinned SHA-256 |
| Automatic coverage | 2/12 main steps, 2 microsteps, 5 pieces |
| Current blocker | Step 3: uncertain orientation of white 25269 corner-round tile |
| Model invocations | 16, including indexing and development retries |
| Total active model elapsed time | 781.253 seconds; not completed-set latency |
| CLI-reported tokens | 332,807 input, 17,989 output, 9,856 cached input |
| Rendering | Both partial snapshots rendered using actual geometry |
| GPU | SwiftShader software renderer; reliable GPU timer unsupported |
| Human / physical checks | Not run |
| Complete / approved / published tutorials | 0 / 0 / 0 |

The recorded model time includes development retries and repairs; it cannot be extrapolated to 15-, 50- or 100-page completion. One early wrong-page candidate was quarantined; exact source-panel binding is now enforced. The authored reference and previous ten-set assisted partials remain separate artifacts.

Evidence: `var/evidence/engine-pilot-benchmark.json`, `var/evidence/engine-pilot-render-compact-index/report.json`. CLI report aggregation now reads actual raw model usage and explicitly labels missing measurements.

## Remaining engineering and acceptance gates

1. Resolve the pilot's source-supported poses and finish every expected step/attachment. Do not invent an orientation or promote the existing authored reference as an automatic result.
2. Implement and independently test a geometry/connector checker with explicit supported scope. The registry is currently empty and validation deliberately fails closed. Hash-valid geometry is not a physical-connection check.
3. Support spatial partitioning for assemblies exceeding the 400 KB current-state prompt. Large-set success is not established.
4. Only after the pilot passes, run all remaining booklets, independent source coverage/review, full-assembly cold/warm loads, frame-time/draw-call/triangle/memory and native-M3 GPU measurements where supported.
5. Stage a real eligible immutable bundle, obtain explicit user approval for its exact version, publish it, and exercise actual content rollback. Unit-test success is not this live acceptance gate.

Software release machinery is implemented, but its end-to-end accepted-content gate and the reconstruction campaign are **not complete**.

## Campaign inventory

Every source below is pinned locally; queued does not mean constructed or benchmarked.

| Set | Booklet | PDF pages | Current campaign outcome |
|---|---|---:|---|
| 30669 | alt-02 | 8 | Blocked: 2/12 main steps |
| 30669 | alt-01 | 9 | Queued behind pilot gate; not constructed |
| 30669 | main | 2 | Queued behind pilot gate; not constructed |
| 60400 | booklet-01 | 32 | Queued behind pilot gate; not constructed |
| 60400 | booklet-02 | 36 | Queued behind pilot gate; not constructed |
| 31134 | booklet-01 | 60 | Queued behind pilot gate; not constructed |
| 31134 | booklet-02 | 44 | Queued behind pilot gate; not constructed |
| 31134 | booklet-03 | 36 | Queued behind pilot gate; not constructed |
| 31129 | booklet-01 | 132 | Queued behind pilot gate; not constructed |
| 31129 | booklet-02 | 52 | Queued behind pilot gate; not constructed |
| 31129 | booklet-03 | 60 | Queued behind pilot gate; not constructed |
| 42163 | main | 76 | Queued behind pilot gate; not constructed |
| 76920 | main | 100 | Queued behind pilot gate; not constructed |
| 42171 | main | 360 | Queued behind pilot gate; not constructed |
| 21343 | main | 252 | Queued behind pilot gate; not constructed |
| 21061 | main | 292 | Queued behind pilot gate; not constructed |
| 10316 | booklet-01 | 184 | Queued behind pilot gate; not constructed |
| 10316 | booklet-02 | 164 | Queued behind pilot gate; not constructed |
| 10316 | booklet-03 | 332 | Queued behind pilot gate; not constructed |
