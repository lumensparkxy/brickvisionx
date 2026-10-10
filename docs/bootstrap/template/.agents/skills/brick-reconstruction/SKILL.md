---
name: brick-reconstruction
description: Infer real brick identities and build-step poses from official instruction images, with explicit uncertainty.
---

# brick-reconstruction

Read docs/03_RECONSTRUCTION_SPEC.md, docs/04_DATA_CONTRACTS.md and docs/15_PART_CATALOGUE.md.
Never fetch completed models or assembly coordinates. Individual documented part geometry is allowed.
Start with source callouts; shortlist actual part IDs, compare part geometry, and retain alternatives.
Propose orientation/translation on a connector-aware lattice; do not treat raw vision coordinates as truth.
Keep physical instance IDs stable while subassemblies are built and attached. Never count them twice.
Keep candidate, agent-reviewed, human-reviewed and physically-tested states separate.
Check image agreement from matched cameras, independent connector evidence and unintended intersections.
Uncertainty is a review item, not a permission to silently substitute another piece.
Outputs: observations, candidate manifest, validation findings, original-versus-render comparisons, correction audit.
