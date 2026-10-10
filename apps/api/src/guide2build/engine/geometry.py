"""Reuse the bounded individual-part resolver without mutating the portal's shared cache."""
from __future__ import annotations
import importlib.util
import json
import math
import shutil
import sys
import threading
from pathlib import Path
from ..catalog import ROOT
from ..reconstruction.checks import verify_assets

_RESOLVER_IMPORT_LOCK = threading.Lock()


def verify_individual_assets(root: Path, geometry_refs: list[str]) -> dict:
    """Validate bounded individual designs, then count their actual closure union."""
    roots = sorted(set(geometry_refs))
    if len(roots) > 2048:
        raise ValueError("Assembly individual-design budget exceeded")
    manifest_path = root / "provenance.json"
    if manifest_path.is_symlink():
        raise ValueError("Symlink provenance is forbidden")
    manifest = json.loads(manifest_path.read_text())
    records = manifest["resources"]
    for relative in roots:
        if records.get(relative, {}).get("classification") != "Part":
            raise ValueError("Assembly root must be an individually resolved Part")
        # Retain the existing hash, path, dependency and 512-resource boundary
        # for each design; unrelated designs do not share that request budget.
        verify_assets(root, [relative])
    if not roots:
        verify_assets(root, [])
    reachable, pending = set(), list(roots)
    total_bytes = 0
    while pending:
        relative = pending.pop()
        if relative in reachable:
            continue
        reachable.add(relative)
        total_bytes += (root / relative).stat().st_size
        if len(reachable) > 8192 or total_bytes > 256_000_000:
            raise ValueError("Assembly geometry cache budget exceeded")
        pending.extend(records[relative].get("dependencies", []))
    return {"status": "pass", "individual_designs": len(roots),
        "reachable_geometry_files": len(reachable), "geometry_bytes": total_bytes, "material_files": 1,
        "scope": "verified individual dependency closures and their union; not correctness of assembly"}


def prepare_geometry(scene, directory: Path, shared: Path, *, accepted_scene=None,
                     new_part_failure_profile="legacy", trial=None, publications=None):
    if new_part_failure_profile != "legacy":
        from .closure_publication import PROFILE, prepare
        if new_part_failure_profile != PROFILE:
            raise ValueError("Unknown new-part failure profile")
        with _RESOLVER_IMPORT_LOCK:
            spec = importlib.util.spec_from_file_location("guide2build_staged_fetch_parts", ROOT / "tools/fetch_parts.py")
            resolver = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(ROOT / "tools"))
            try:
                spec.loader.exec_module(resolver)
            finally:
                sys.path.pop(0)
        return prepare(scene, accepted_scene, directory, shared, trial, publications, resolver)
    roots = sorted({instance.part_id for instance in scene.instances})
    if any(instance.geometry_ref != f"parts/{instance.part_id}.dat" for instance in scene.instances):
        raise ValueError("Physical instance geometry must be its individually resolved Part")
    directory.mkdir(parents=True, exist_ok=True)
    # Existing assets can seed the private cache only with their verified provenance.
    if not (directory / "provenance.json").exists() and (shared / "provenance.json").is_file():
        document = json.loads((shared / "provenance.json").read_text())
        for relative in [*document.get("resources", {}), *document.get("materials", {})]:
            source = shared / relative
            if source.is_symlink() or not source.resolve().is_relative_to(shared.resolve()):
                raise ValueError("Geometry cache escapes the curated root")
            destination = directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        shutil.copyfile(shared / "provenance.json", directory / "provenance.json")
    retained = merge_verified_cache_receipts(directory, shared)
    # This module remains the existing single authoritative allowlist/classification boundary.
    # Two independent-set workers may prepare private geometry concurrently.
    # Serialize only the existing temporary import-path mutation, not downloads,
    # checks or inference. Each worker still receives its own resolver object.
    with _RESOLVER_IMPORT_LOCK:
        spec = importlib.util.spec_from_file_location("guide2build_local_fetch_parts", ROOT / "tools/fetch_parts.py")
        resolver = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            spec.loader.exec_module(resolver)
        finally:
            sys.path.pop(0)
    # The resolver's 512-file/20-MB/depth limits apply to each individual
    # design closure. A complete set can contain many such designs without
    # turning the accumulated assembly into one unbounded download request.
    if len(roots) > 2048:
        raise ValueError("Assembly individual-design budget exceeded")
    for part_id in roots:
        root = f"parts/{part_id}.dat"
        if root in retained.get("resources", {}):
            verify_assets(directory, [root])
            continue
        resolver.fetch_parts([part_id], directory)
        fetched = json.loads((directory / "provenance.json").read_text())
        for path, record in fetched["resources"].items():
            old = retained.get("resources", {}).get(path)
            if old is not None and old.get("sha256") != record.get("sha256"):
                raise ValueError("Individual geometry changed during assembly accumulation")
        retained["resources"] = retained.get("resources", {}) | fetched["resources"]
        retained["file_map"] = retained.get("file_map", {}) | fetched.get("file_map", {})
        retained["roots"] = sorted(set(retained.get("roots", [])) | {part_id})
        if (len(retained["resources"]) > 8192 or
                sum(item.get("bytes", 0) for item in retained["resources"].values()) > 256_000_000):
            raise ValueError("Assembly geometry cache budget exceeded")
        fetched.update(resources=retained["resources"], file_map=retained["file_map"], roots=retained["roots"])
        (directory / "provenance.json").write_text(json.dumps(fetched, indent=2) + "\n")
    resolver.fetch_materials(directory)
    current = json.loads((directory / "provenance.json").read_text())
    current["resources"] = retained.get("resources", {}) | current["resources"]
    current["file_map"] = retained.get("file_map", {}) | current.get("file_map", {})
    (directory / "provenance.json").write_text(json.dumps(current, indent=2) + "\n")
    return verify_individual_assets(directory, [instance.geometry_ref for instance in scene.instances])


def individual_catalogue_context(shared: Path, max_bytes=100_000):
    """Verified geometry only. Never reads set mappings, scene/reference files or assembly coordinates."""
    import hashlib
    manifest = shared / "provenance.json"
    if not manifest.is_file():
        return []
    document = json.loads(manifest.read_text())
    result, size = [], 0
    def verified_geometry(relative, record):
        target = shared / relative
        if target.is_symlink() or not target.resolve().is_relative_to(shared.resolve()):
            raise ValueError("Individual part path escapes root")
        if target.stat().st_size > 1_000_000:
            raise ValueError("Individual part exceeds bound")
        data = target.read_bytes()
        if record.get("url") != "https://library.ldraw.org/library/official/" + relative:
            raise ValueError("Individual part origin not official LDraw")
        if hashlib.sha256(data).hexdigest() != record.get("sha256"):
            raise ValueError("Individual part cache hash mismatch")
        return data

    for relative, record in sorted(document.get("resources", {}).items()):
        if record.get("classification") != "Part":
            continue
        data = verified_geometry(relative, record)
        # Keep source notices but never use comments as executable instructions.
        geometry = data.decode("utf-8-sig")[:6000]
        size += len(geometry.encode())
        if size > max_bytes:
            break
        result.append({"geometry_ref": relative, "description": record.get("description"),
                       "raw_ldraw_part_geometry": geometry, "truncated": len(data) > 6000})
    # A Part can be only a tiny reference wrapper around its asymmetric shape. Preserve
    # those transforms and supply verified Subpart definitions, never assembly models.
    # Roots retain priority; supplementary bytes share the same existing context budget.
    for part in result:
        record = document["resources"][part["geometry_ref"]]
        pending = [(path, 0) for path in record.get("dependencies", [])]
        seen, definitions = set(), []
        part["subparts_truncated"] = False
        while pending:
            path, depth = pending.pop(0)
            if path in seen:
                continue
            seen.add(path)
            dependency = document["resources"].get(path)
            if dependency is None:
                raise ValueError("Missing individual geometry dependency receipt")
            if dependency.get("classification") != "Subpart":
                continue
            if depth > 2 or len(definitions) >= 8:
                part["subparts_truncated"] = True
                continue
            data = verified_geometry(path, dependency)
            text = data.decode("utf-8-sig")[:6000]
            if size + len(text.encode()) > max_bytes:
                part["subparts_truncated"] = True
                continue
            size += len(text.encode())
            definitions.append({"geometry_ref": path, "sha256": dependency["sha256"],
                                "raw_ldraw_subpart_geometry": text, "truncated": len(data) > 6000})
            pending.extend((child, depth + 1) for child in dependency.get("dependencies", []))
        part["subpart_definitions"] = definitions
    # Expose mesh-reference origins in the viewer's coordinates. These are geometric
    # landmarks, not inferred sockets, assembly positions or certified connectors.
    for part in result:
        frames, truncated = stud_mesh_frames(part["geometry_ref"], document, verified_geometry)
        encoded = len(json.dumps(frames).encode())
        part["stud_mesh_frames_truncated"] = truncated or size + encoded > max_bytes
        part["stud_mesh_frames"] = frames if size + encoded <= max_bytes else []
        if part["stud_mesh_frames"]:
            size += encoded
    return result


def stud_mesh_frames(root, document, read, limit=128):
    """Flatten verified stud/group/subpart transforms; no set-specific knowledge."""
    frames, visits = [], 0
    truncated = False
    identity = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]

    def product(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

    def walk(path, matrix, offset, ancestry):
        nonlocal visits, truncated
        if path in ancestry:
            raise ValueError("Cyclic stud geometry context")
        if len(ancestry) > 8 or visits >= 512 or len(frames) >= limit:
            truncated = True
            return
        visits += 1
        record = document["resources"][path]
        data = read(path, record)
        for line in data.decode("utf-8-sig").splitlines():
            fields = line.split(maxsplit=14)
            if not fields or fields[0] != "1":
                continue
            if len(fields) != 15:
                raise ValueError("Malformed geometry reference")
            name = fields[14].lower().replace("\\", "/")
            child = document.get("file_map", {}).get(name)
            if child is None:
                # Older minimal contexts can omit maps; never invent a transform.
                truncated = True
                continue
            child_record = document["resources"].get(child)
            if child_record is None or child not in record.get("dependencies", []):
                raise ValueError("Stud geometry dependency lacks provenance")
            leaf = Path(child).name
            is_stud = leaf.startswith("stud") and child_record.get("classification") in {
                "Primitive", "48_Primitive", "8_Primitive"}
            if not (is_stud or leaf.startswith("stug-") or child_record.get("classification") == "Subpart"):
                continue
            values = [float(value) for value in fields[2:14]]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("Non-finite geometry transform")
            translation, local = values[:3], [values[3:6], values[6:9], values[9:12]]
            composed = product(matrix, local)
            origin = [offset[i] + sum(matrix[i][k] * translation[k] for k in range(3)) for i in range(3)]
            if is_stud:
                read(child, child_record)  # Hash-check the named primitive as well.
                if len(frames) >= limit:
                    truncated = True
                    continue
                signs = [1, -1, -1]
                frames.append({"primitive": child, "sha256": child_record["sha256"],
                    "position_ldu": [signs[i] * origin[i] for i in range(3)],
                    "basis": [[signs[i] * composed[i][j] * signs[j] for j in range(3)] for i in range(3)],
                    "scope": "mesh reference only; not a certified connector"})
            else:
                walk(child, composed, origin, [*ancestry, path])
    walk(root, identity, [0., 0., 0.], [])
    return frames, truncated


def merge_verified_cache_receipts(directory: Path, shared: Path):
    """Keep receipts for unused seeded files; selected-closure fetches must not orphan them."""
    import hashlib
    target = directory / "provenance.json"
    document = json.loads(target.read_text()) if target.exists() else {"resources": {}, "file_map": {}}
    source = shared / "provenance.json"
    shared_document = json.loads(source.read_text()) if source.exists() else {}
    for relative, record in shared_document.get("resources", {}).items():
        if relative in document["resources"]:
            continue
        file = directory / relative
        if not file.is_file():
            continue
        if file.is_symlink() or not file.resolve().is_relative_to(directory.resolve()) or file.stat().st_size > 1_000_000:
            raise ValueError("Unsafe seeded geometry")
        if record.get("url") != "https://library.ldraw.org/library/official/" + relative:
            raise ValueError("Unverified seeded geometry origin")
        if hashlib.sha256(file.read_bytes()).hexdigest() != record.get("sha256"):
            raise ValueError("Seeded geometry hash differs from original receipt")
        document["resources"][relative] = record
    document.setdefault("file_map", {}).update({name: path for name, path in shared_document.get("file_map", {}).items()
                                               if path in document["resources"]})
    target.write_text(json.dumps(document, indent=2) + "\n")
    return document
