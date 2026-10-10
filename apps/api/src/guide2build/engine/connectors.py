"""Hash-bound nominal connectors for explicitly inspected individual parts.

This is deliberately not a mesh-to-connectivity classifier. In particular, internal
stud primitives do not automatically become connection sites; an explicit site
such as 18980's centre tube requires individual geometry evidence. A matching frame does not prove
collision freedom, clutch strength, or a physical build.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from ..catalog import ROOT
from ..core.models import Pose
from .verification_cache import current_verification

METADATA = ROOT / "config/individual-connectors.json"
SAFE = re.compile(r"^(parts/(?:s/)?|p/(?:8/|48/)?)[a-z0-9_-]+\.dat$")
CLASSES = {"Part", "Subpart", "Primitive", "48_Primitive", "8_Primitive"}
MAX_COORDINATE_LDU = 1_000_000


def rotation_matrix(quaternion):
    x, y, z, w = quaternion
    return [[1 - 2*(y*y + z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
            [2*(x*y + z*w), 1 - 2*(x*x + z*z), 2*(y*z - x*w)],
            [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x + y*y)]]


def transform_vector(matrix, value):
    return [sum(matrix[i][j] * value[j] for j in range(3)) for i in range(3)]


def transform_point(pose: Pose | dict, point):
    pose = Pose.model_validate(pose)
    if any(not math.isfinite(v) or abs(v) > MAX_COORDINATE_LDU for v in [*pose.position_ldu, *point]):
        raise ValueError("Connector coordinates exceed the supported 1000000 LDU bound")
    rotated = transform_vector(rotation_matrix(pose.quaternion_xyzw), point)
    world = [pose.position_ldu[i] + rotated[i] for i in range(3)]
    if any(not math.isfinite(v) or abs(v) > MAX_COORDINATE_LDU for v in world):
        raise ValueError("World connector coordinates exceed the supported 1000000 LDU bound")
    return world


def _read_json(path, bound, verification=None):
    if path.is_symlink() or path.stat().st_size > bound:
        raise ValueError("Unsafe or oversized connector metadata/provenance")
    return json.loads(verification.read(path, bound).decode() if verification else path.read_text())


def load_connector_catalogue(geometry_root: Path, geometry_refs=None, *, metadata_path: Path | None = None):
    """Verify pinned bytes and actual dependency closure before returning local frames.

    ``metadata_path`` is for original synthetic test catalogues, never model input.
    A library update needs a deliberate metadata review; updating a cache receipt is
    insufficient to reuse connector assumptions from different mesh bytes.
    """
    verification = current_verification()
    if verification is None:
        return _load_connector_catalogue(geometry_root, geometry_refs, metadata_path=metadata_path)
    references = None if geometry_refs is None else tuple(sorted(set(geometry_refs)))
    metadata_path = metadata_path or METADATA
    key = (Path(geometry_root).absolute(), references, Path(metadata_path).absolute())
    return verification.catalogue(key, lambda: _load_connector_catalogue(
        geometry_root, references, metadata_path=metadata_path, verification=verification))


def _load_connector_catalogue(geometry_root, geometry_refs=None, *, metadata_path=None, verification=None):
    metadata = _read_json(metadata_path or METADATA, 2_000_000, verification)
    if metadata.get("schema_version") != "1.0":
        raise ValueError("Unsupported connector metadata version")
    root = Path(geometry_root)
    if root.is_symlink():
        raise ValueError("Symlink connector geometry root")
    manifest = _read_json(root / "provenance.json", 10_000_000, verification)
    records, mapping = manifest["resources"], manifest.get("file_map", {})
    available = {part["geometry_ref"]: part for part in metadata["parts"]}
    requested = set(geometry_refs) if geometry_refs is not None else set(available) & set(records)
    unsupported = requested - set(available)
    if unsupported:
        raise ValueError("Unsupported connector metadata: " + ", ".join(sorted(unsupported)))
    checked = {}

    def walk(path, closure, ancestry=()):
        if not SAFE.fullmatch(path) or path in ancestry or len(ancestry) > 32:
            raise ValueError("Unsafe or cyclic connector geometry dependency")
        if path in closure:
            return
        if len(closure) >= 512:
            raise ValueError("Connector geometry dependency limit")
        if path not in checked:
            record = records.get(path)
            if (not record or record.get("classification") not in CLASSES
                    or record.get("url") != "https://library.ldraw.org/library/official/" + path):
                raise ValueError("Unsupported connector geometry provenance")
            target = root / path
            if (target.is_symlink() or not target.resolve().is_relative_to(root.resolve())
                    or target.stat().st_size > 1_000_000):
                raise ValueError("Unsafe connector geometry path or size")
            data = verification.read(target, 1_000_000) if verification else target.read_bytes()
            if hashlib.sha256(data).hexdigest() != record.get("sha256"):
                raise ValueError("Connector geometry hash mismatch")
            dependencies = set()
            for line in data.decode("utf-8-sig").splitlines():
                fields = line.split(maxsplit=14)
                if fields and fields[0] == "1":
                    if len(fields) != 15:
                        raise ValueError("Malformed connector geometry dependency")
                    if not all(math.isfinite(float(value)) for value in fields[2:14]):
                        raise ValueError("Non-finite connector geometry transform")
                    child = mapping.get(fields[14].lower().replace("\\", "/"))
                    if child is None:
                        raise ValueError("Missing connector geometry dependency mapping")
                    dependencies.add(child)
            if dependencies != set(record.get("dependencies", [])):
                raise ValueError("Connector geometry dependency receipt mismatch")
            checked[path] = (record["sha256"], dependencies)
        sha256, dependencies = checked[path]
        closure[path] = sha256
        for child in dependencies:
            walk(child, closure, (*ancestry, path))

    result = {}
    for reference in sorted(requested):
        part = available[reference]
        closure = {}
        walk(reference, closure)
        if records[reference].get("classification") != "Part":
            raise ValueError("Connector root must be an individual Part")
        pins = [[path, sha] for path, sha in sorted(closure.items())]
        closure_hash = hashlib.sha256(json.dumps(pins, separators=(",", ":")).encode()).hexdigest()
        if (part["geometry_sha256"] != closure[reference] or part["closure_sha256"] != closure_hash
                or part["evidence_resources"] != pins or part["closure_file_count"] != len(closure)):
            raise ValueError("Connector metadata hash pin differs; review the changed individual geometry")
        ids = [feature["connector_id"] for feature in part["connectors"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate connector ID in metadata")
        result[reference] = part
    return metadata, result


def connector_context(geometry_root: Path):
    metadata, parts = load_connector_catalogue(geometry_root)
    from ..releases.models import digest
    return {"schema_version": metadata["schema_version"], "scope": metadata["scope"],
            "metadata_sha256": digest(metadata),
            "metadata_status": metadata["metadata_status"], "tolerance_ldu": metadata["tolerance_ldu"],
            "orientation_rule": "quarter_turns rotates about the target connector outward normal; opposing normals mate",
            "unsupported": metadata["unsupported"], "limits": metadata["limits"],
            "parts": [{key: value for key, value in part.items() if key != "evidence_resources"}
                      for part in parts.values()]}


def connector(part, connector_id):
    for feature in part["connectors"]:
        if feature["connector_id"] == connector_id:
            return feature
    raise ValueError(f"Unknown connector ID {connector_id!r} for {part['geometry_ref']}")


def world_connector(pose: Pose | dict, geometry_ref: str, connector_id: str, geometry_root: Path):
    _, parts = load_connector_catalogue(geometry_root, [geometry_ref])
    return transform_point(pose, connector(parts[geometry_ref], connector_id)["position_ldu"])


def world_landmark(pose: Pose | dict, geometry_ref: str, landmark_id: str, geometry_root: Path):
    """Visible cap/rim landmarks only; source visibility is a separate observation."""
    _, parts = load_connector_catalogue(geometry_root, [geometry_ref])
    for feature in parts[geometry_ref]["connectors"]:
        landmark = feature.get("landmark")
        if landmark and landmark["landmark_id"] == landmark_id:
            return transform_point(pose, landmark["position_ldu"])
    raise ValueError(f"Unknown visible landmark ID {landmark_id!r} for {geometry_ref}")
