# Product specification

**Project:** Guide2Build 3D  
**Release:** Version I, bounded local prototype  
**Document version:** 1.0 · 2026-10-01  
**Status:** Build contract; current implementation status is maintained separately.

## 1. Purpose
Make an existing illustrated construction guide easier to follow by reconstructing the assembly in 3D,
retaining its original instruction order, and allowing the builder to inspect each connection interactively.
The product does not invent a new design. It does not merely display pictures of the booklet on a canvas.
The user supplies a set number; the application resolves the selected official guide behind the scenes.

The primary user is a person building a real set. The secondary user is a reviewer who resolves ambiguities
in the reconstruction. For the prototype, a developer may perform both roles; their actions remain separately recorded.

## 2. Scope and exclusions
The first supported catalogue entry is 30669 / alt-02, documented in the source register. Begin with four
main instructions as a geometry and UX checkpoint, then implement the remaining instructions in the same booklet.
Support substeps and detached subassemblies from the start. Four steps are not the final release scope.

Use individual real-part geometry and locally authored connector metadata. No complete community model,
community-derived assembly sequence, extracted model from another instruction app, or alternate unofficial
build is permitted. A part library is allowed; importing someone else's finished assembly is not.

Version I excludes natural-language design generation, arbitrary PDF upload, scanning a brick collection,
shopping, checkout, user accounts, social sharing, PDF export, mobile-native applications, RAG and public hosting.
Do not add these features because an older visual concept contains a button or label for them.

## 3. User journey

### FR-01: Find the set
Accept a 4–7 digit set number. Resolve it against a curated source catalogue. Clearly distinguish malformed
input from an unsupported set. Only the initial supported source needs to work in V1; unknown numbers do
not trigger guessed URLs or fabricated models. Show the official set name and guide choices actually supported.

### FR-02: Choose a guide
A set can have multiple booklets or alternate builds. Persist set number and guide identity together.
The prototype may expose only the chosen alternate booklet, explicitly labelled as its supported guide.
The interface must not imply that it supports all booklets or all sets on the LEGO website.

### FR-03: Prepare the source
Obtain the official PDF server-side, hash it, render its pages, identify panels and retain all evidence.
A cached reconstruction may be reused only when guide identity, source hash, part-library provenance and
pipeline/version information are compatible. On a cache hit, report that the result was loaded, not regenerated.

### FR-04: Reconstruct the assembly
Identify candidate parts and colours, derive their poses, represent subassemblies, and run explicit checks.
Store structured observations and candidate placements before corrections. Maintain a clear route to review
for unknown parts, hidden connections and competing interpretations. A provider failure is not an empty successful build.

### FR-05: Follow the guide in 3D
Show the original instruction panel, interactive assembly at that instruction, and newly introduced pieces.
Provide rotate, zoom, pan, reset, previous, next, replay and instruction navigation. Highlight active pieces
without relying on colour alone. Expose callout substeps before attachment. Keep the original main-step number
visible while moving through substeps. The source panel and 3D state must remain synchronised.

### FR-06: Review uncertainty
Provide a developer/reviewer view for changing a candidate part mapping, colour, pose or step association.
Every edit records prior value, new value, reason, source evidence, actor type and base revision.
Re-run affected checks and create a new revision. Do not overwrite the original automated proposal.
Do not conflate an agent's inspection with human approval or a real physical build.

### FR-07: Parts list
Count unique physical part instances in the selected assembly. Derive the complete and per-step lists from
the same scene revision as the viewer. Repeated appearance across screenshots and subassembly attachment
must not increase the count. Do not use the box's advertised piece count as the alternate-build bill of materials.

### FR-08: Resume and retry
Save viewing progress locally, scoped by set, guide, source hash and scene revision. Persist conversion jobs
server-side once implemented. Reloading or retrying must not multiply jobs, charge repeatedly without notice,
or corrupt an accepted revision. Permit retry from a recorded checkpoint after interrupted processing.

## 4. Required states
`unsupported`, `source_available`, `queued`, `fetching`, `rendering`, `extracting`, `mapping_parts`,
`solving_poses`, `validating`, `needs_review`, `ready`, `failed`, `cancelled`.
These are workflow states, not the same as scene review status. A `ready` scene still carries its actual
review and physical-test metadata. Progress percentages must be based on completed measurable work;
use named stages where the total is not known.

## 5. Quality targets
These are proposed acceptance targets to measure, not current performance claims.
For the small target assembly, a cached tutorial should become usable within 3 seconds on a documented local
baseline after its assets are available. Aim for smooth orbiting at 30 FPS or better on that baseline, with no
persistent GPU-memory growth over repeated open/close cycles. Report device/browser and measurements.
Uncached conversion is asynchronous with visible stage feedback; no fixed conversion-time promise is made.

Support current Chromium and Safari on desktop for the target release, plus a narrow touch-screen layout.
Check keyboard navigation, focus visibility, reduced motion, contrast, touch target sizes and WebGL failure.
A missed browser check is explicitly untested, not assumed to pass because another browser did.

## 6. Completion dimensions
Report these independently:

| Dimension | Passing evidence |
|---|---|
| Scaffold readiness | Files materialize correctly; baseline tests/config/contracts are valid. |
| Local software E2E | Real frontend, backend, processing/review states and asset serving work together. |
| PDF-assisted reference | Every covered instruction is reconstructed from recorded official-source evidence; corrections are labelled. |
| Automated conversion | A real configured runtime provider runs on a clean source-derived job; raw candidate and corrected results are measured separately. |
| Human verification | An actual human has reviewed a specified revision and recorded that action. |
| Physical verification | The specified model has actually been assembled and the result recorded. |

A polished reference tutorial can be delivered before fully automatic conversion succeeds. That does not
make the automatic converter complete. Conversely, a pipeline that returns JSON is not sufficient without
correct real-part geometry and usable instructions.

## 7. Release gate
The software deliverable should cover the complete selected booklet, pass the defined local checks and
show source-aligned 3D steps with unresolved issues clearly exposed. A reviewer-ready candidate may be
handed over when evidence remains ambiguous, but its coverage and unresolved defects must be stated.
Do not release silently substituted pieces, wrong source editions or unverifiable claimed review records.
