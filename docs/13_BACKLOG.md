# Agent-ready bootstrap backlog

Use existing authenticated GitHub issues as the master backlog when a project repository is available.
These local IDs are initial task contracts, not claimed GitHub issue numbers. Map them to actual issues;
do not create issues, a remote repository or PRs without authorization.

| ID | Task and required outcome | Depends on | Acceptance |
|---|---|---|---|
| G2B-001 | Verify toolchain, install dependencies, generate real locks and run baseline checks. | — | M0; no fabricated lockfile/test pass. |
| G2B-002 | Add typed observations/jobs/reviews, generated TS and runtime API validation. | 001 | Valid/invalid cross-language fixtures. |
| G2B-003 | Fetch actual booklet, cache by hash, render pages and map original instruction panels. | 001 | SRC-01–07 evidence; no community source. |
| G2B-004 | Identify and curate individual opening-step parts with safe dependency loading. | 003 | Correct part identity/origin/material and notices. |
| G2B-005 | Implement relevant connector metadata and coordinate conversion fixtures. | 002,004 | GEO-02–08 with an asymmetric part. |
| G2B-006 | Extract typed visual observations and retain alternative mappings. | 003,004 | Source-evidenced candidates and ambiguity records. |
| G2B-007 | Implement constrained placement/visual comparison and four-step candidate. | 005,006 | STEP-01–05, labelled authoring mode. |
| G2B-008 | Build source-synchronised 3D viewer, highlighting, replay and revision-aware resume. | 002,007 | Real browser four-step walkthrough. |
| G2B-009 | Add persistent SQLite jobs, worker, retries, cancellation and stage feedback. | 002,003 | Restart and idempotency tests. |
| G2B-010 | Build review UI/API with typed corrections and immutable revisions. | 007,009 | Conflict detection, audit trail, actor integrity. |
| G2B-011 | Complete all remaining main instructions, part mappings and callouts. | 007,008,010 | Full-booklet coverage and source comparison. |
| G2B-012 | Integrate an actual runtime vision provider when authorized/configured. | 002,006,009 | Fresh provider run; no reference-coordinate leakage. |
| G2B-013 | Evaluate raw automatic output separately from corrected reference. | 011,012 | Numerators, denominators, raw artifacts and correction count. |
| G2B-014 | Run real-backend E2E, visual/accessibility, security and performance checks. | 008–011 | Evidence matrix, no silent skipped test. |
| G2B-015 | Clean-checkout reproducibility, notices, runbook and final status handoff. | 014 | All completion dimensions reported separately. |

## Task execution contract
For each task record goal, scope/owned paths, current status, dependent contracts, exact validation command,
source/evidence paths, unresolved issues and next action. A completed coding task can still leave model
verification blocked; reflect both in the ledger. Do not close dependent accuracy work on software-only evidence.

G2B-012/013 are explicit automatic-conversion gates. Missing runtime credentials must not prevent the local
reference/tutorial work, but those gates cannot be marked done by replaying an authored scene.

## Default status
All feature tasks are pending implementation/verification. The delivered starter has baseline infrastructure
and tests; consult `14_SCAFFOLD_STATUS.md` rather than marking the backlog completed on sight.
