---
name: reconstruction-validation
description: Test structure, geometry, provenance and browser behavior without overstating reconstruction correctness.
---

# reconstruction-validation

Read docs/08_ACCEPTANCE_TESTS.md. Run unit/API/contract tests and actual browser interactions.
Keep deterministic local tests separate from network and paid provider checks.
Use original synthetic fixtures only in tests, never as evidence for the target LEGO set.
Compare first four main steps against PDF panels and then the full booklet. Count unique physical instances.
Test invalid poses, missing geometry, ambiguous mappings, interrupted jobs, duplicate operations and stale revisions.
Geometry overlap is not necessarily collision at a valid stud/socket connection; broad-phase boxes are candidates only.
An agent cannot manufacture human approval. A physical test requires a real recorded physical build.
Outputs: exact commands, exit codes, reference coverage, unresolved errors and evidence paths.
