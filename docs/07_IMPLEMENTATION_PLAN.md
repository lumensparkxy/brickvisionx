# Implementation plan and milestone gates

Work in vertical slices. Do not build a broad catalogue or Version II while the first official guide remains
unreconstructed. Maintain the current checkpoint in `execution/PROGRESS.json` and evidence in the validation report.

## M0 — preflight and scaffold
Inspect the existing repository, bootstrap missing files when appropriate, read constraints and establish
baseline commands. Confirm installed Python/Node/Codex versions and writable project paths. Obtain normal
network approval for dependency/source retrieval where needed. Resolve dependencies, generate real lockfiles
and record the actual versions. Do not fabricate lockfiles when the package registry is unavailable.

**Exit:** root structure/configuration valid; backend baseline tests run; frontend setup either succeeds or
has a specific environmental blocker. The scaffold being present is not an accepted model.

## M1 — shared contracts and source ingestion
Keep the existing schema as a starting point. Add typed observations, part-candidate records, assembly groups,
camera hints and validation findings. Generate browser types and add runtime response validation. Normalise
API errors. Implement reusable source caching, download locks and safe rendering in a bounded subprocess.
Persist source receipts and exact page/panel identity. Replace the temporary source iframe with local page assets.

**Exit:** the real selected PDF has a computed hash, rendered pages and a verified panel map. Error paths and
source-change detection work. Source retrieval never accepts arbitrary user URLs.

## M2 — curated individual parts and connectors
Identify actual pieces required for the opening instructions. Fetch only individual part geometry and required
primitives from an approved LDraw library source. Preserve notices, versions, hashes and original origins.
Implement safe dependency resolution, explicit material handling and a minimal connector catalogue for these parts.
Do not download a completed model. Add asymmetric orientation and connector-alignment tests.

**Exit:** every mapped part in the opening slice loads correctly and has enough verified metadata to test its
relevant attachments. Ambiguous mappings remain explicit instead of being rendered as generic bricks.

## M3 — first-four-step reconstruction gate
Extract observations from the official pages. Implement bounded candidate placement, source-view comparison,
connector checks and correction records. Reconstruct the four main instructions including their callout
microsteps. Use the live provider when configured; otherwise label agent-generated observations as PDF-assisted.

**Exit:** source-versus-render evidence for every covered instruction; real part IDs and quantities; one physical
instance per piece; no undisclosed unresolved ambiguity. Part-level and pose-level uncertainties are reported.
If an ambiguity blocks acceptance, keep the candidate and review path usable and continue independent software work.

## M4 — interactive tutorial
Use the same scene data for display, per-step parts and the full BOM. Add active-piece emphasis, deterministic
placement replay, seek, keyboard access, reduced motion, responsive source view and revision-aware progress.
Render detached callouts, then attach the same instances. Dispose GPU assets and make missing geometry actionable.

**Exit:** a real browser can follow the four-step slice forward and backward, with correct PDF synchronisation.
Screenshots and interactions are inspected; nothing is accepted merely because TypeScript compiled.

## M5 — durable processing and review
Implement SQLite queue/worker, job events, cancellation, recovery and idempotent conversion requests.
Add revisioned scene storage and typed review commands with conflict detection. Implement review-needed UI,
part/pose correction controls and audit history. Never let an AI acceptance record masquerade as a human action.

**Exit:** restart during processing preserves work, duplicate requests do not duplicate conversions, corrections
create auditable revisions, and the accepted tutorial is isolated from active draft edits.

## M6 — complete the selected booklet
Extend part/connector coverage and reconstruction through the remaining main instructions. Verify main-step
labels against the actual source, rather than assuming array length is the main-step count. Add all callouts,
turnovers and attachment motions present. Verify final BOM and every intermediate assembly against evidence.

Run a fresh automatic conversion separately when a real provider is available; it must not read the accepted
reference coordinates. Report its raw accuracy and correction count. If credentials or model performance block
this gate, keep that status distinct from the completed PDF-assisted reference and software integration.

**Exit:** full-booklet coverage or an exact list of remaining main steps/issues with reasons. Do not stop at four
and describe the whole app as complete. No unverified “all sets supported” promise.

## M7 — validation and handoff
Run deterministic tests, full frontend checks, local real-backend browser tests, asset-path tests and security
cases. Measure loading/render behaviour on a recorded baseline. Inspect all required screenshots. Confirm
README setup commands from a clean checkout with real lockfiles and locally fetched permitted assets.

Update the final validation report, remaining blockers, source/asset notices, execution ledger and user runbook.
Report scaffold, software E2E, PDF-assisted reference, automated conversion, human review and physical build
as independent outcomes. Public deployment is outside this plan.

## Parallel work
The primary agent owns integration and contracts. After the contracts are agreed, backend jobs, viewer UI
and part/reconstruction investigation may proceed in parallel with explicit file ownership. Limit to three
workers. The quality reviewer independently checks evidence. Avoid parallel edits to the same schema file.
A single agent can perform all work sequentially when custom-agent support is unavailable.
