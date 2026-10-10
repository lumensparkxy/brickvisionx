# ADR 0002 — one source-aligned, versioned scene
Status: accepted implementation direction.

Keep physical instances, source evidence, poses and steps in one canonical schema. Generate the viewer
snapshots, BOM and review references from it. Use immutable revisions and retain raw proposals separately.
This avoids instruction/BOM divergence and double-counting when a subassembly is attached.
The consequence is explicit migrations and contract tests rather than separate ad hoc browser models.
