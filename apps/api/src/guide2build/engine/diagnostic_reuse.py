"""One-search reuse of an unchanged, connector-verified diagnostic prefix.

This stores execution state, not an approval or a persistent geometry cache.
Unsupported prefix designs and incompatible branches use the full diagnostic.
The enclosing catalogue scope still checks every reused dependency on exit.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path

from ..releases.models import canonical, digest
from .verification_cache import current_verification

VERSION = "immutable-prefix-diagnostics-v1"
MAX_PREFIX_STEPS = 128
MAX_PREFIX_INSTANCES = 512
MAX_STATE_BYTES = 16 * 1024 * 1024
_ACTIVE = ContextVar("hypothesis_diagnostic_prefix", default=None)


class _PrefixReuse:
    def __init__(self):
        self.verification = current_verification()
        self.key = self.state = None
        self.closed = False
        self.hits = self.reused_snapshots = self.captures = 0

    def _live(self):
        if self.closed:
            raise ValueError("Diagnostic prefix scope is closed")
        if self.verification is None or current_verification() is not self.verification:
            return False
        self.verification._live()
        return True

    def binding(self, scene, previous, geometry_root, metadata, catalogue, selected_steps, limits):
        if not self._live() or previous is None or metadata is None:
            return None
        count = len(previous.steps)
        if not 0 < count <= MAX_PREFIX_STEPS or count >= len(scene.steps):
            return None
        prefix = [step.model_dump(mode="json") for step in scene.steps[:count]]
        if prefix != [step.model_dump(mode="json") for step in previous.steps]:
            return None
        identities = {identity for step in scene.steps[:count] for identity in step.poses}
        if len(identities) > MAX_PREFIX_INSTANCES:
            return None
        references = {part.geometry_ref for part in scene.instances if part.instance_id in identities}
        if not references <= set(catalogue):
            # The separate symmetry/perception reader has no catalogue exit
            # fence for unsupported-only meshes. Do not reuse those proofs.
            return None
        root = Path(geometry_root).absolute()
        observed = self.verification.files
        provenance = observed.get(root / "provenance.json")
        if provenance is None:
            return None
        dependencies = {}
        for reference in sorted(references):
            for relative, sha256 in catalogue[reference]["evidence_resources"]:
                record = observed.get(root / relative)
                if record is None or record.sha256 != sha256:
                    return None
                dependencies[relative] = sha256
        return digest({"version": VERSION, "root": str(root), "previous": previous.model_dump(mode="json"),
            "prefix": prefix, "parts": [part.model_dump(mode="json") for part in scene.instances],
            "metadata_sha256": digest(metadata), "provenance_sha256": provenance.sha256,
            "dependencies": dependencies, "selected_steps": sorted(selected_steps), "limits": limits})

    def restore(self, key, count):
        if not self._live() or key is None or key != self.key:
            return None
        self.hits += 1
        self.reused_snapshots += count
        return deepcopy(self.state)

    def capture(self, key, state):
        if not self._live() or key is None or self.key is not None:
            return
        findings, checks, latest, groups, workspace, roots, snapshots, symmetry, *counts = state
        if symmetry:
            # The mesh reader also validates material provenance outside the
            # connector catalogue fence. Keep those proof-bearing prefixes on
            # the full path rather than skipping an unfenced integrity check.
            return
        # Bound the complete retained state before copying it. Full finding
        # counters survive even when per-severity receipt buckets are truncated.
        data = {"findings": [dict(findings.records), dict(findings.counts), dict(findings.severities)],
            "checks": checks, "latest": {key: pose.model_dump(mode="json") for key, pose in latest.items()},
            "groups": {key: sorted(value) for key, value in groups.items()}, "workspace": workspace,
            "roots": roots, "snapshots": snapshots, "symmetry": symmetry, "counts": counts}
        if len(canonical(data)) > MAX_STATE_BYTES:
            return
        self.key, self.state = key, deepcopy(state)
        self.captures += 1

    def close(self):
        self.closed = True
        self.key = self.state = None


def current_diagnostic_reuse():
    return _ACTIVE.get()


@contextmanager
def diagnostic_reuse_scope():
    reuse = _PrefixReuse()
    token = _ACTIVE.set(reuse)
    try:
        yield reuse
    finally:
        reuse.close()
        _ACTIVE.reset(token)
