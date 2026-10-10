"""Separate provenance, connector-frame and sequence checks for the authored candidate.
A connector coincidence is neither a mesh collision test nor physical-build evidence.
"""

from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path
from guide2build.core.models import SceneManifest

SAFE = re.compile(r"^(parts/(?:s/)?|p/(?:8/|48/)?)[a-z0-9_-]+\.dat$")


def verify_assets(root: Path, geometry_refs: list[str]) -> dict:
    manifest_path = root / "provenance.json"
    if manifest_path.is_symlink():
        raise ValueError("Symlink provenance is forbidden")
    manifest = json.loads(manifest_path.read_text())
    records = manifest["resources"]
    visited = set()
    active = set()

    def walk(path):
        if not SAFE.fullmatch(path) or path in active:
            raise ValueError("Unsafe or cyclic dependency")
        if path in visited:
            return
        if len(visited) + len(active) > 512:
            raise ValueError("Dependency resource limit")
        target = root / path
        if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
            raise ValueError("Geometry path escapes root")
        if path not in records:
            raise ValueError("Missing asset provenance")
        record = records[path]
        if record.get("url") != "https://library.ldraw.org/library/official/" + path:
            raise ValueError("Unexpected asset origin")
        if target.stat().st_size > 1_000_000:
            raise ValueError("Geometry resource exceeds byte limit")
        data = target.read_bytes()
        if len(data) > 1_000_000 or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("Geometry hash mismatch")
        active.add(path)
        actual = []
        for line in data.decode("utf-8-sig").splitlines():
            fields = line.split(maxsplit=14)
            if fields and fields[0] == "1":
                if len(fields) != 15:
                    raise ValueError("Malformed geometry reference")
                name = fields[14].lower().replace("\\", "/")
                dep = manifest.get("file_map", {}).get(name)
                if dep is None:
                    raise ValueError("Missing dependency mapping")
                actual.append(dep)
        if sorted(set(actual)) != sorted(set(record.get("dependencies", []))):
            raise ValueError("Dependency receipt mismatch")
        for dep in actual:
            walk(dep)
        active.remove(path)
        visited.add(path)

    for path in geometry_refs:
        walk(path)
    material = root / "LDConfig.ldr"
    record = manifest.get("materials", {}).get("LDConfig.ldr")
    if not record or record.get("url") != "https://library.ldraw.org/library/official/LDConfig.ldr":
        raise ValueError("Missing material provenance")
    if material.stat().st_size > 1_000_000:
        raise ValueError("Material exceeds byte limit")
    if (
        material.is_symlink()
        or len(material.read_bytes()) > 1_000_000
        or hashlib.sha256(material.read_bytes()).hexdigest() != record["sha256"]
    ):
        raise ValueError("Material hash mismatch")
    return {
        "status": "pass",
        "reachable_geometry_files": len(visited),
        "material_files": 1,
        "scope": "actual dependency closure, hashes and confined paths; not correctness of assembly",
    }


def world(pose, local):
    # The bounded authored candidates use only Y rotations. Reject unsupported families.
    q = pose.quaternion_xyzw
    if abs(q[0]) + abs(q[2]) > 1e-6:
        raise ValueError("Unsupported connector orientation family")
    a = 2 * math.atan2(q[1], q[3])
    c, s = math.cos(a), math.sin(a)
    return [
        pose.position_ldu[0] + c * local[0] + s * local[2],
        pose.position_ldu[1] + local[1],
        pose.position_ldu[2] - s * local[0] + c * local[2],
    ]


def aligned(a, b, tolerance=0.05):
    return math.dist(a, b) <= tolerance


def four_step_connector_report(scene: SceneManifest) -> dict:
    step = next(s for s in scene.steps if s.main_step_number == 4 and s.action == "attach_subassembly")
    p = step.poses
    # Local frames preserve original origins after the single LDraw->canonical C transform.
    pairs = [
        ("base", (-10, 0, 10), "keel-left", (0, -16, 0)),
        ("base", (10, 0, 10), "keel-right", (0, -16, 0)),
        ("base", (-10, 0, -10), "wing-left", (-30, -8, -30)),
        ("base", (10, 0, -10), "wing-right", (-30, -8, -30)),
    ]
    # Conventional plate sockets/round tile cavity, 20-LDU pitch and 8-LDU layer.
    for side, sgn in [("left", 1), ("right", -1)]:
        for x in [-30, -10, 10, 30]:
            pairs.append((side + "-wing-base", (x, 0, 10), side + "-wing-strip", (x, -8, 0)))
        pairs.append((side + "-wing-base", (sgn * 30, 0, -10), side + "-wing-tip", (0, -8, 0)))
    contacts = []
    for a, la, b, lb in pairs:
        wa, wb = world(p[a], la), world(p[b], lb)
        contacts.append(
            {
                "instances": [a, b],
                "position_a": wa,
                "position_b": wb,
                "status": "pass" if aligned(wa, wb) else "fail",
            }
        )
    return {
        "status": "pass" if all(c["status"] == "pass" for c in contacts) else "fail",
        "scope": "first-four declared stud/socket mating frames only",
        "tolerance_ldu": 0.05,
        "metadata_origin": "developer-authored from retained individual geometry and source lattice",
        "contacts": contacts,
        "limitations": [
            "Callout-base-to-curved-wing underside sockets require independent metadata review.",
            "No narrow-phase intersection or placement-path test; no strength or physical verification.",
        ],
    }
