# Delivered scaffold status — 1 October 2026

Historical packaging record. Implementation has progressed since this snapshot; current measured status
and limitations are in [execution/VALIDATION_REPORT.md](execution/VALIDATION_REPORT.md).

## What this package is
An implementation-ready specification and code foundation for Guide2Build 3D Version I. It is not the
completed PDF-to-3D application. The launch prompt assigns the remaining implementation to Codex and
requires evidence before any stronger completion claim.

## Implemented in the starter

| Area | Delivered behavior |
|---|---|
| Source registry | Set 30669 and the selected official alternate guide are explicitly registered. |
| Backend | Health, set details, stored-scene retrieval and parts-count endpoints; honest unsupported/not-ready errors. |
| Source utility | Allowlisted, bounded PDF fetch, actual-hash receipt and page rendering code. Successful external download not verified here. |
| Scene contract | Pydantic model, exported JSON Schema, source/pose/step/identity/review invariants. |
| Parts counting | Counts unique physical instances, including reuse across subassembly snapshots. |
| Frontend | Set-number form, status/error states and source/3D/parts workspace starter. |
| Three.js | Individual LDraw part loading, canonical pose wrappers, orbit controls and step visibility foundation. No real geometry bundled. |
| Runtime inference | Explicitly disabled provider; unavailable inference cannot return fabricated success. |
| Codex | Root and scoped instructions, four custom agents, six repository skills and conservative configuration. |
| Tests/tooling | Python tests, schema checks, frontend test definitions, source fetch/scene validation/dev/check tools and CI definition. |
| Docs-only delivery | Verified-checksum bootstrap with dry run, idempotency and conflict/path safety. |

## Not implemented or not yet established
Persistent conversion jobs/worker; panel segmentation; resolved target part catalogue/connectors; placement
solver; collision/connector geometry checks; real vision-provider adapter; correction API/editor; placement
animations/highlighting; detached-subassembly interaction; complete source-panel synchronization; all
12 source-derived steps; physical verification. The backlog and implementation plan cover these areas.

The existing UI starter can report that the source is known but the reconstruction is unavailable. That is
the expected initial state. It must not show a fake aircraft or a synthetic fixture as set 30669.
The small synthetic scene exists only for deterministic contract/API tests under a separate identity.

## Checks actually performed during packaging
- `python tools/check.py --python-only`: **37 tests passed** and the generated JSON Schema is current.
- `NODE_PATH=$(npm root -g) node tools/check_ts_syntax.cjs`: **11 TypeScript files, zero syntax errors**.
  This uses the available global TypeScript parser. It is not dependency resolution, type checking or a build.
- Local Python/JSON/TOML/skill-metadata and bootstrap integrity checks: see `execution/VALIDATION_REPORT.md`.
- Docs-only restoration, repeat run and conflict protection: see the validation report and bootstrap tests.

## Not claimed as tested
No frontend dependency install, full TypeScript typecheck, Vite build, browser/Playwright run, rendered
screenshot fidelity review, Codex configuration execution, live download, real source-to-model reconstruction,
live inference or physical build was completed in this environment. Network-dependent package setup and source
retrieval were blocked by container name resolution. Ruff was not installed. No lockfiles were invented.

The reference concept in `docs/assets/v1-concept.png` is a design reference, not a screenshot of this scaffold
running. Specification copy/states override its illustrative counts and any inaccurate claims.

## Model coverage and acceptance

| Dimension | Packaging status |
|---|---|
| Code/spec scaffold | Delivered; checked in the limited scopes above. |
| Local software end-to-end | Not yet verified. |
| PDF-assisted target reconstruction | 0 of 12 main steps reconstructed. |
| Runtime automatic reconstruction | Not implemented/evaluated. |
| Agent review of target geometry | Not performed. |
| Human review | Not performed. |
| Physical build | Not performed. |

The real source PDF hash remains null until the actual bytes are retrieved. Source page/step counts are
booklet metadata checked through web inspection, not proof of a locally cached source or valid reconstruction.
