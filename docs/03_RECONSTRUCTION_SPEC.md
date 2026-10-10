# PDF-to-assembly reconstruction specification

## 1. What must be inferred
A visual instruction contains part callouts, a camera projection, visible assembly geometry, arrows, rotations,
subassembly panels and sometimes quantity multipliers. It does not contain a reliable ready-made 3D scene.
Reconstruction must infer **part identity, colour, physical instance identity, local geometry origin, orientation,
translation, assembly membership and instruction order**. Store unknowns rather than fill them with guesses.

The reviewed reference is built from the selected official booklet only. Finished models and unofficial
instructions are prohibited even when publicly accessible. Individual library pieces remain allowed.

## 2. Stage A — source and panel evidence
Download and hash the PDF; render at a reproducible scale. Use native text/object extraction for text and
layout hints, but inspect rasterised panels for geometry. Avoid OCR unless text cannot otherwise be read;
OCR is not a pose estimator. Protect the renderer with page-count, pixel-count, time and memory limits.

Record main-step panels, part callouts, subassembly callouts, arrows and rotation instructions separately.
Panel coordinates are normalised against the rendered, rotation-corrected page with top-left origin.
Store the original page index and crop rectangle. The same page can contain several main instructions.
A callout's internal 1/2 sequence must not be confused with a new pair of main instructions.

For the first source, the opening four main instructions contain initial assembly, wing placement and two
small callout assemblies. Use the observations in the source register as a starting hypothesis, then verify
against locally rendered pixels. The mockup is never assembly evidence.

## 3. Stage B — part identification
For each parts callout, extract quantity, apparent colour and shape cues: stud footprint, slope, curvature,
cut-outs, underside hints and attachment features. Output a shortlist, not an invented exact ID.
Map to actual parts in the curated geometry catalogue. Use the catalogue's part-to-design/element mapping
where verified; a LEGO element number is not automatically an LDraw file ID.

Compare candidate renders to the callout from several plausible orientations. Record what distinguishes
near-duplicate pieces. If a textured/printed variant is unclear, preserve that uncertainty. Do not replace an
unusual plate with a rectangle because it is easier to draw. Missing parts block the affected instruction.

V1 may include a developer-authored part mapping reviewed from official-source evidence. Label it as such.
Maintain ambiguous candidates and the selection reason so a later vision provider can be evaluated against it.

## 4. Stage C — incremental placement
Use the previous accepted candidate state, newly required pieces, local connector metadata and current
instruction image. Generate placements through compatible connection pairs and allowed discrete orientations.
For conventional studded parts, search around relevant stud/plate lattices. Do not snap every geometry
primitive to the same grid: offset parts, half-stud connections and hinges need explicitly supported rules.

One workable bounded solver:

1. Enumerate verified part-ID/colour candidates for each new instance.
2. Enumerate rotations supported by its known connectors; start with orthogonal rotations for this source.
3. Align a candidate's connector frame to a compatible exposed connector on the existing assembly.
4. Reject impossible connector relationships and obvious out-of-range placements.
5. Run broad-phase volume tests, then connection-aware/narrower checks for candidate intersections.
6. Render surviving assemblies with an estimated source camera; compare visibility, silhouette, colour regions,
   edges and recognisable stud patterns. Mask arrows, labels and part callout boxes from assembly scoring.
7. Retain a bounded beam of candidates. Apply later views to disambiguate when possible; record score components.
8. Present unresolved alternatives for correction instead of picking a low-confidence winner silently.

Implementation limits must be configuration values: maximum candidate count, beam width, per-step timeout,
image scale and permitted orientation families. Defaults are engineering choices, not learned confidence guarantees.

Do not treat raw language-model coordinates as validated output. A vision model may propose relative placements
or candidate poses; deterministic code and evidence review decide whether they are acceptable.

## 5. Camera and view handling
Begin with an orthographic approximation when it fits the booklet artwork; estimate view direction, scale
and translation from matching landmarks or candidate renders. Camera changes between steps are allowed.
A model flip shown by an arrow changes presentation, not the canonical orientation of every stored part.
Store the recommended camera separately from world-space part coordinates.

Use both visible features and connectivity to rank candidates. Similar 2D silhouettes can describe different
3D assemblies. Image agreement alone cannot certify hidden geometry or mechanical feasibility.

## 6. Subassemblies and counts
A physical piece has one persistent instance ID throughout the whole build. Building it in a detached
callout, showing it again above the main model, and attaching it are three presentations—not three pieces.

Represent a main instruction as one or more microsteps: create/add parts into a local subassembly,
inspect that subassembly, then rigidly attach the group. Derive final absolute poses from parent-relative
transforms and flatten snapshots for the viewer. Never apply the same parent transform twice.

Quantities such as “2×” mean instantiate two physical groups, each with its own instance IDs. Cloning a
visual group is not enough for BOM correctness. Mirrored assemblies may require different parts or rotated
placements; do not mirror a mesh into a nonexistent part.

## 7. Checks and limitations

| Layer | What to check | What it does not prove |
|---|---|---|
| Structure | IDs, finite/unit poses, source hashes, step references, one creation per physical piece. | Geometry correctness. |
| Part mapping | Real part/colour identity and dependency availability. | Correct placement. |
| Connectors | Compatible attachment frames and expected engagement. | Strength under handling. |
| Geometry | Unintended intersections, floating pieces and collision candidates. | Every real-world fit/tolerance. |
| Visual | Render-to-panel agreement from source-like cameras and multiple views. | Hidden mechanical correctness. |
| Sequence | Accessible placement path and correct callout/attachment order. | Easy handling by every user. |
| Physical | A recorded real assembly trial. | Universal strength or safety certification. |

Axis-aligned boxes overlap during many valid contacts and do not describe concave sockets. They are a
broad-phase filter, not a universal collision proof. Export named check results and unresolved issues,
not a single unsupported “100% buildable” score.

## 8. Uncertainty and review
Assign review items for unknown part IDs, ambiguous colour, pose ambiguity, occluded connections, unavailable
geometry, unresolved collisions or inconsistent quantities. Each item points to source evidence and affected
instance/step IDs, with candidate alternatives and reasons.

A correction creates a new scene revision and retains the original proposal. The reviewer changes a mapping,
colour, transform or grouping through a validated command. Revalidate the affected instruction and descendants.
The worker must not endlessly regenerate after a reviewer makes a locked, source-supported correction.

Confidence scores are ranking signals until calibrated. Do not present a model's self-reported probability
as a measured probability of correctness. The initial release can use categorical confidence and explicit findings.

## 9. Reproducibility and evaluation
Record source hash, page-renderer version, part-library hashes, model/provider identifier, prompt version,
solver configuration, candidate scores, corrections and code revision where available. Preserve raw provider
observations locally with secrets removed. A candidate and its corrected output must be separately loadable.

A “fresh automatic run” starts without reading the accepted reference assembly or its coordinates. It may
use the generic individual-parts catalogue. Compare its raw outputs with source evidence and a separately
reviewed reference; report part-ID, colour, pose, step-assignment and callout-group correctness, plus the number
of manual corrections. A reference authored by the same agent is useful but not independent ground truth.

## 10. Required outputs
`source.receipt.json`, `pages.json`, `panels.json`, typed observations, part-candidate records,
provenance-rich scene manifests, review items, check reports and source-versus-render evidence.
A four-step gate requires the corresponding main instructions and all necessary microsteps, not merely
four arbitrary snapshots. Continue to the complete selected booklet after the gate passes.
