# Data contracts and scene semantics

## Canonical schema
`apps/api/src/guide2build/core/models.py` is the initial schema source. `tools/export_schema.py` generates
`packages/contracts/scene.schema.json`. The frontend currently has matching manual types; milestone M1
must generate or automatically validate TypeScript types and validate actual API payloads at runtime.
A TypeScript `as` cast is not input validation. Schema changes require a version or an explicit migration.

JSON Schema handles shape constraints; Python semantic validation also handles cross-reference rules.
They are not interchangeable. Add shared valid/invalid fixtures to keep frontend/backend expectations aligned.

## Identity
A set number identifies a commercial set; a guide ID identifies one selected booklet/build. An instruction
main-step number is the number printed in that guide. A step ID identifies one viewer microstep. A source
hash identifies the exact downloaded PDF. A revision identifies a reconstruction, including corrections.

Never use display labels or array positions as persistent instance IDs. Every physical piece gets an ID
when introduced, retains it through subassembly attachment, and appears once in the assembly's inventory.

## SceneManifest
The starter defines:

- Identity: schema version, set number, guide ID, revision and source SHA-256.
- Coordinate convention and separate status/check fields.
- `instances`: concrete physical parts with part ID, colour, local geometry reference and source evidence.
- `steps`: ordered immutable snapshots with introduction, activation, visibility and exact poses.
- `reviews`: actor type, revision, evidence paths, decision and time.

Part mappings carry their origin (`vision_proposal`, `pdf_assisted_authoring`, `human_correction`) and mapping
status. A review record is an audit object, not permission for an automated system to impersonate a human.
The current structural contract checks review consistency; the future review API must enforce actor provenance.

## Coordinate system
The canonical scene is right-handed with +Y up, in LDraw units (LDU). Use quaternion order `[x,y,z,w]`,
unit length, and translation `[x,y,z]`. Rotations must not contain unintended scale or reflection.
Part poses refer to each part library's preserved local origin, not an arbitrary mesh-centred origin.

LDraw itself uses -Y up. Its dimensional conventions include a 20-LDU stud pitch, 8-LDU plate height and
24-LDU brick height [S6]. Convert raw part geometry once using a 180-degree rotation around X:

```text
C = diag(1, -1, -1)
p_canonical = C * p_ldraw
R_canonical = C * R_ldraw * inverse(C)
```

`det(C)=+1`, so this is a proper rotation rather than a handedness-changing reflection. If part-local vertices
are converted with C, convert a raw LDraw placement with the conjugated rotation above. Canonical manifest
poses must not be converted a second time. The starter viewer converts raw part geometry beneath a canonical
pose wrapper. Add an asymmetric-part fixture so sign mistakes cannot hide in a symmetric brick.

## Snapshots and actions
Every snapshot contains a pose for exactly each visible instance. `introduced_instance_ids` indicates
new physical pieces; `active_instance_ids` controls emphasis and may include previously introduced pieces
being attached. `visible_instance_ids` is presentation state. Do not infer the BOM from visibility.

Example: the callout introduces IDs `left-base`, `left-strip`, `left-cap`. Its attachment step introduces
nothing and activates those same IDs. Their final poses change together. The complete bill of materials
still counts three pieces, not six. A 2× repeated group gets distinct IDs for both physical copies.

The initial schema flattens poses for deterministic seeking. M1 may add a normalised assembly graph,
action placement transforms, recommended cameras and render hints, while continuing to export compatible
snapshots. Record group membership explicitly and verify rigid movement of attachment groups.
Do not create a second independent scene format inside the viewer.

## Source evidence
A `SourcePanel` contains zero-based PDF page index, normalised `[x0,y0,x1,y1]` crop and the exact source hash.
Its coordinates use the top-left of the rotation-corrected rendered page. For width W and height H:
`left=floor(x0*W)`, `top=floor(y0*H)`, `right=ceil(x1*W)`, `bottom=ceil(y1*H)`, clipped to the valid image.
Validate non-empty crops and retained aspect ratio. A UI page label is `page_index+1`.

Extend evidence metadata with source-renderer version, page-image hash and observation ID. This prevents
using crops from a different raster scale/orientation without detection. Hashes are computed, never supplied
as plausible-looking constant strings for a real source.

## Contracts still to implement
Define typed `GuideSource`, `SourceReceipt`, `PageAsset`, `PanelObservation`, `PartCandidate`, `Connector`,
`AssemblyGroup`, `ConversionJob`, `JobEvent`, `ReviewItem`, `ReviewCommand` and `ValidationReport`.
Observation output must contain quantities, candidates and uncertainty; final placements belong to the scene.
Review commands carry base revision and an idempotency key. Reject stale commands with a conflict response.

Use `not_run`, `pass`, `fail`, plus findings for check results. No global validation flag may imply that
checks which have not been implemented have passed. Physically tested state requires externally supplied
real evidence and remains separate from code-level assertions.

## BOM and progress
Aggregate `(part_id, color_code)` over all concrete scene instances. Per-step “new parts” is the aggregation
over only `introduced_instance_ids`; attachment steps may introduce zero pieces. Distinguish total quantity
from the number of unique part/colour combinations. Scope persisted viewer progress by set, guide, source
hash and revision; migration must not silently reuse progress for a changed instruction sequence.
