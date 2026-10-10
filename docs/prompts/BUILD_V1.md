# One-prompt implementation contract

You are implementing Guide2Build 3D Version I in this repository. Execute the project end to end within
available permissions; do not stop after a plan, a scaffold, a mockup or a static model viewer.

## Bootstrap and inspect
If this repository contains only `docs/`, run `python3 docs/bootstrap/materialize.py` to create missing
root files. The script does not overwrite existing files. Inspect conflicts and preserve unrelated work.
Read `AGENTS.md`, `project.toml`, `docs/00_START_HERE.md`, the product/architecture/reconstruction/data/UI
specifications, the implementation plan, acceptance tests and current scaffold status.
Read the relevant local `.agents/skills/*/SKILL.md` files. Verify the installed Codex/toolchain rather than
assuming configuration support. Newly materialized custom agents may need a new session for discovery;
continue sequentially with explicit role reads when necessary.

## Deliver this exact product
A user enters set number 30669, selects the supported official alternate booklet 02, and follows that
booklet's assembly in an interactive Three.js tutorial with the original source panel beside it.
Find/fetch the official PDF behind the scenes; no PDF-upload interface.
Derive the assembly and step sequence from the PDF. Do not fetch or import any completed community model,
completed set geometry, unofficial assembly sequence or extracted model from another app.
Individual LDraw pieces/primitives/materials are allowed, with verified identity and retained notices.
No natural-language new-design generation, RAG, accounts, shopping, public hosting or Version II features.

## Execute the build
Use the existing starter rather than replacing it without cause. Maintain `docs/execution/PLAN.md`,
`PROGRESS.json`, `BLOCKERS.md` and `VALIDATION_REPORT.md` as you work.

1. Preflight the actual repository and environment. Install project-local dependencies where permitted,
   generate genuine Python/JavaScript lockfiles, and run the baseline. Do not fabricate a lockfile or a pass.
2. Implement shared typed contracts, runtime input validation, source caching and bounded PDF rendering.
   Download the actual official booklet, compute its hash, inspect pages and map original main steps/callouts.
3. Curate required individual parts and relevant connector metadata; preserve origins and coordinate semantics.
   Never hide unavailable geometry with generic pieces. Derive exact mappings from evidence, not guesses.
4. Implement incremental visual observations, candidate placement, geometric/connector checks and review items.
   Reconstruct the first four main instructions and all their substeps. Compare real renders with source panels.
5. Build the usable viewer: source synchronisation, correct per-step pieces, orbit/zoom/pan/reset, highlighting,
   deterministic replay/seeking, detached subassembly assembly/attachment, keyboard/reduced-motion and resume.
6. Implement persistent SQLite jobs and a worker, idempotent conversion requests, recovery/cancel/retry, status
   feedback, revisioned correction commands and reviewer UI. Never impersonate human acceptance.
7. Continue through the full selected booklet after the four-step gate. Verify every main instruction,
   intermediate assembly, final model and physical-instance BOM against official-source evidence.
8. Run full local checks and real-backend browser tests; inspect desktop and phone screenshots, console/network
   errors, model/source alignment and performance. Fix discovered defects and update evidence and runbooks.

## Inference and honesty
The default runtime provider is disabled. When real credentials and permission exist, implement a current,
real vision-provider adapter with structured outputs, bounded retries and a documented budget. Evaluate a
fresh automatic run without access to the accepted reference coordinates. Retain its raw output and corrections.
Do not create credentials, incur unapproved charges, or pretend the coding subscription automatically supplies
backend inference. Use an available credential mechanism without printing secrets.

When a runtime provider is unavailable, keep building the local software and a **PDF-assisted, evidence-backed
reference** using your available image inspection tools. Label every such observation/placement accordingly.
The app must expose assisted/review modes honestly. Do not mark automated conversion complete by replaying
that reference. Unknown geometry or occluded connections remain explicit review findings; investigate rather
than inventing a placement. Agent review is not human or physical verification.

## Working method
Work through the milestone dependency graph. Use at most three parallel workers with explicit file ownership
when useful; the main agent owns integration and acceptance. A sequential workflow is fully acceptable.
Do not ask the user routine architecture/filename questions already answered in the docs. Ask only for a
non-resolvable credential/access/rights issue, conflicting existing project content, an unresolved assembly
ambiguity requiring real input, or a destructive/externally visible action. Do not weaken tests or source
constraints to remove a blocker. Continue independent work and leave a precise next action for blocked gates.

Do not push, publish, create GitHub issues/PRs or deploy without separate authorization. Read and map existing
GitHub issues when available; otherwise use the local backlog. Do not invent external issue numbers.

## Completion contract
Before the final handoff, run the acceptance matrix and report exact command results, changed files,
source hash, main-step/microstep coverage, part coverage, correction count, screenshots/evidence and limitations.
Report these separately: scaffold readiness; local software E2E; PDF-assisted reference; automatic conversion;
human review; physical build. Only claim a dimension passed when the corresponding evidence exists.

Provide exact local startup instructions and the specific set/guide to enter. Keep the execution ledger
resumable. Continue to a complete supported-booklet product or a concrete documented blocker; do not deliver
another plan as though it were the implemented application.
