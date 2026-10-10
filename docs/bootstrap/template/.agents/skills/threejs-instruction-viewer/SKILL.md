---
name: threejs-instruction-viewer
description: Render reviewed assembly snapshots and nested build steps using Three.js and real part geometry.
---

# threejs-instruction-viewer

Read docs/06_UI_UX_SPEC.md and the generated scene schema. Use the source-aligned snapshot as state.
Lazy-load Three.js; keep transient orbit/animation updates outside React state.
Load individual parts with a restricted local part resolver and preserve material semantics and part origins.
Use the coordinate conversion documented in docs/04_DATA_CONTRACTS.md exactly once.
A missing asset produces a named error, never an anonymous replacement box in a real tutorial.
Animate only current actions; seeking and reversing must restore snapshots exactly without numerical drift.
Dispose geometries/materials/listeners and cancel animation frames. Respect reduced motion and provide keyboard controls.
Keep progress scoped by set, guide, source hash and scene revision. Review mode never silently edits a published scene.
Outputs: responsive viewer, tested state transitions, source alignment, console/network and screenshot evidence.
