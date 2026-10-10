# Individual part catalogue and geometry policy

## Permitted and prohibited inputs
Permitted: real individual LDraw parts, primitives, verified material definitions, part identifiers, relevant
connector metadata, and source notices. Prohibited: completed set models, finished community assemblies,
community-derived placements, unofficial alternate-build instructions, and extracted models from instruction apps.

An archive may include both parts and models. Exclude the model directory and any finished assembly entries.
The application's allowed parts import must inspect expected part/primitive classifications and dependencies;
file extension alone is insufficient. A `.dat` file may reference a subpart, which is allowed, but must not be
used to smuggle an assembled aircraft into the project.

## Part record
For every selected physical design, store catalogue ID, optional verified LEGO design/element mappings,
geometry path, original local origin, source URL, file/release hash, notices, dependency list and supported
colours/material metadata. Record bounds for search/performance without moving the part's origin.
Variants and printed textures require their own identity or explicit variant relationship.

The catalogue is not a bill of materials; the scene's physical instances determine required quantities.
Do not invent part IDs from the appearance of a label or infer element numbers by manipulating a set number.

## Procurement workflow
Identify a shortlist from source callouts. Consult the primary LDraw catalogue/library for the individual part.
Inspect the candidate geometry from enough angles to distinguish it from lookalikes. Fetch only the selected
part and required primitives/subparts, preserving file notices. Log every obtained resource.

When a bundled full part-library release is the practical source, approve the release URL, download with
size/resource limits, safely extract only `parts/`, `p/` and required material/license metadata, and exclude
all models. Do not guess a release URL or checksum; verify from the primary library site first.

The scaffold intentionally ships no part data because it has not completed this identity/geometry review.
An empty asset store is an explicit pending task, not a reason to render pretend parts.

## Dependency resolver
Resolve each reference under a fixed curated root. Reject absolute paths, URLs, `..`, symlink escape and
unexpected file classes. Track visited dependencies and depth/count/byte limits. Handle case consistently
across macOS/Linux and normalise known part-reference conventions without losing source IDs.
Preserve conditional lines, winding/BFC semantics, colour inheritance and special material definitions.

Prepare a web-loadable dependency map or packed **individual part** resource when useful. Do not load
hundreds of repeated instances from the network independently. Cache geometry by verified asset identity;
keep per-instance transforms and highlight materials separate.

## Connector metadata
Raw visible meshes are not a complete connectivity database. Define the supported connection features for
the target parts: connector type, local frame, polarity, engagement depth, allowed relative orientations,
contact allowances and source of the metadata. Implement only connector families actually needed first.

For unsupported hinges, clips, axles or offset geometries, return an unsupported/needs-review result rather
than applying an orthogonal stud rule. Distinguish a visual alignment from a verified compatible attachment.
A connection graph does not establish a strength rating or physical build test.

## Tests
Use asymmetric real pieces to test axes/origins, a supported stud/socket pair for connection transforms,
an obviously floating candidate, an unrelated penetration, a repeated subassembly and a missing dependency.
Document connector tolerances and why intended contact is permitted. Do not use only symmetric boxes.
