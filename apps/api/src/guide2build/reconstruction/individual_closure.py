"""Opt-in bounded acquisition into an unpublished read-through stage.

No finished assembly content is retained. Known Shortcut responses contribute only
bounded origin/hash/license/reference-name rejection evidence. Unknown failures
propagate. This module has no network client: the existing resolver supplies it.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

import httpx

from .asset_errors import RejectedResource, UnsupportedIndividualClosure

BASE = "https://library.ldraw.org/library/official/"
SAFE = re.compile(r"^(parts/(?:s/)?|p/(?:8/|48/)?)[a-z0-9_-]+\.dat$")
ALLOWED = {"Part", "Subpart", "Primitive", "8_Primitive", "48_Primitive"}
MAX_FILES, MAX_BYTES, MAX_DEPTH = 512, 20_000_000, 24
MAX_RESOURCE = 1_000_000
MAX_MANIFEST = 16_000_000
MAX_REJECTION = 65_536


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def confined(path: Path, root: Path):
    # Do not use resolve(): it would follow untrusted symlinks before rejection.
    # Path.absolute() leaves ".." intact, so reject traversal before its lexical
    # is_relative_to check. Even a path that returns inside is not a safe input.
    path, root = Path(path), Path(root)
    if ".." in path.parts or ".." in root.parts:
        raise ValueError("Parent traversal in asset paths is forbidden")
    path, root = path.absolute(), root.absolute()
    if not path.is_relative_to(root) or len(path.parts) > 128:
        raise ValueError("Asset path escapes its configured root or path-depth bound")
    for item in reversed([path, *path.parents]):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("Symlink asset ancestry is forbidden")
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError("Asset ancestry is not a directory")
    return path


def _open_nofollow(path):
    """Walk bounded ancestry using held directory handles, never symlinks.

    The final path still gets the existing identity checks after reading. Held
    parent handles prevent a transient ancestor symlink from escaping the root
    between lexical validation and the leaf open. At most two FDs are live.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open(path.anchor, flags)
    try:
        for name in path.parts[1:-1]:
            child = os.open(name, flags, dir_fd=parent)
            os.close(parent)
            parent = child
        # A FIFO must reach the regular-file fstat check without waiting for a
        # writer. O_NONBLOCK does not alter ordinary regular-file reads.
        return os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)


def read(path, root, limit=MAX_RESOURCE):
    path = confined(path, root)
    descriptor = _open_nofollow(path)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit or before.st_nlink != 1:
            raise ValueError("Asset must be a bounded unlinked regular file")
        # Retain raw-descriptor ownership even if constructing the stream fails.
        # Admission precedes fdopen: wrapping a directory can itself raise.
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
            after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    def identity(info):
        return (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
            info.st_mode,
            info.st_nlink,
        )

    confined(path, root)
    if identity(before) != identity(after) or len(data) > limit or identity(path.stat()) != identity(after):
        raise ValueError("Asset changed while reading")
    return data


class Fence:
    """Exact bytes plus file/ancestor identity, rechecked on success and errors."""

    def __init__(self):
        self.files, self.directories = {}, {}

    def read(self, path, root, limit=MAX_RESOURCE):
        path = confined(path, root)
        for parent in path.parents:
            if parent.exists():
                identity = (parent.stat().st_dev, parent.stat().st_ino, parent.stat().st_mode)
                if parent in self.directories and self.directories[parent] != identity:
                    raise ValueError("Asset ancestry changed during acquisition")
                self.directories[parent] = identity
        data = read(path, root, limit)
        info = path.stat()
        pin = (root, limit, sha(data), info.st_dev, info.st_ino, info.st_mode, info.st_nlink)
        if path in self.files and self.files[path] != pin:
            raise ValueError("Cached input changed during acquisition")
        if len(self.files) >= 16_388 and path not in self.files:
            raise ValueError("Read-through input file budget exceeded")
        self.files[path] = pin
        return data

    def verify(self, *, ignore_files=()):
        for path, identity in self.directories.items():
            confined(path, path)
            info = path.stat()
            if (info.st_dev, info.st_ino, info.st_mode) != identity:
                raise ValueError("Asset ancestry changed during acquisition")
        for path, (root, limit, expected, dev, ino, mode, links) in self.files.items():
            if path in ignore_files:
                continue  # Only an explicitly committed provenance replacement may be excluded.
            data = read(path, root, limit)
            info = path.stat()
            if sha(data) != expected or (info.st_dev, info.st_ino, info.st_mode, info.st_nlink) != (
                dev,
                ino,
                mode,
                links,
            ):
                raise ValueError("Cached input changed during acquisition")

    def pins(self):
        return [
            {"path": str(path), "root": str(v[0]), "limit": v[1], "sha256": v[2], "identity": list(v[3:])}
            for path, v in sorted(self.files.items())
        ]


def envelope(path, data, references, record=None):
    if not SAFE.fullmatch(path) or len(data) > MAX_RESOURCE:
        raise ValueError("Unsafe or oversized individual resource")
    content = data.decode("utf-8-sig")
    names = references(content)  # Lexical safety precedes classification.
    notices = [
        line for line in content.splitlines() if line.startswith(("0 Author:", "0 !LICENSE", "0 !HISTORY"))
    ]
    licenses = [line for line in notices if line.startswith("0 !LICENSE ")]
    if not licenses:
        raise ValueError("Asset lacks a license notice")
    match = re.search(r"^0 !LDRAW_ORG (\S+)", content, re.M)
    classification = match[1] if match else None
    if record is not None:
        if (
            record.get("url") != BASE + path
            or record.get("sha256") != sha(data)
            or type(record.get("bytes")) is not int
            or record["bytes"] != len(data)
            or record.get("classification") != classification
            or record.get("notices") != notices
        ):
            raise ValueError("Cached resource envelope differs from its original receipt")
    if classification not in ALLOWED | {"Shortcut"}:
        raise ValueError("Unapproved or unknown LDraw classification")
    return content, names, classification, notices, licenses


class Cache:
    def __init__(self, root, fence):
        self.root, self.fence = Path(root).absolute(), fence
        confined(self.root, self.root)
        path = self.root / "provenance.json"
        self.raw = fence.read(path, self.root, MAX_MANIFEST) if path.exists() else None
        self.document = (
            json.loads(self.raw)
            if self.raw
            else {"resources": {}, "file_map": {}, "roots": [], "materials": {}}
        )
        doc = self.document
        if (
            not isinstance(doc, dict)
            or not isinstance(doc.get("resources"), dict)
            or not isinstance(doc.get("file_map"), dict)
        ):
            raise ValueError("Invalid cached provenance shape")
        records = doc["resources"]
        if (
            len(records) > 8192
            or sum(r.get("bytes", MAX_RESOURCE + 1) for r in records.values()) > 256_000_000
        ):
            raise ValueError("Assembly geometry cache budget exceeded")
        for path, record in records.items():
            if (
                not SAFE.fullmatch(path)
                or not isinstance(record, dict)
                or type(record.get("bytes")) is not int
                or not 0 <= record["bytes"] <= MAX_RESOURCE
                or record.get("classification") not in ALLOWED
                or record.get("url") != BASE + path
                or not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", ""))
            ):
                raise ValueError("Invalid cached individual resource receipt")
        for name, relative in doc["file_map"].items():
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"(?:s/|48/|8/)?[a-z0-9_-]+\.dat", name)
                or relative not in records
            ):
                raise ValueError("Unsafe or missing cached dependency mapping")
        for record in records.values():
            deps = record.get("dependencies")
            if not isinstance(deps, list) or any(not isinstance(x, str) or x not in records for x in deps):
                raise ValueError("Unsafe or incomplete cached dependency closure")
        if not isinstance(doc.get("materials", {}), dict) or set(doc.get("materials", {})) - {"LDConfig.ldr"}:
            raise ValueError("Invalid cached material receipts")
        if not isinstance(doc.get("roots", []), list) or any(
            not isinstance(x, str) or not re.fullmatch(r"[a-z0-9]+", x) for x in doc.get("roots", [])
        ):
            raise ValueError("Invalid cached root identities")

    def contains(self, path):
        target = confined(self.root / path, self.root)
        exists, recorded = target.exists(), path in self.document["resources"]
        if exists != recorded:
            raise ValueError("Cached asset has no matching original receipt or bytes")
        return recorded

    def obtain(self, path):
        if not self.contains(path):
            raise ValueError("Previously accepted dependency is absent")
        return self.fence.read(self.root / path, self.root), self.document["resources"][path]

    def material(self):
        path = "LDConfig.ldr"
        target, record = self.root / path, self.document.get("materials", {}).get(path)
        if target.exists() != bool(record):
            raise ValueError("Material configuration lacks original receipt or bytes")
        if not record:
            return None
        data = self.fence.read(target, self.root)
        content = data.decode("utf-8-sig")
        if (
            record.get("url") != BASE + path
            or record.get("sha256") != sha(data)
            or record.get("bytes") != len(data)
            or "0 !LDRAW_ORG Configuration" not in content
            or "0 !COLOUR" not in content
        ):
            raise ValueError("Material configuration differs from receipt")
        return data, record


class StageBudget:
    def __init__(self, root):
        self.files, self.bytes = {}, 0
        if root.exists():
            for index, path in enumerate(root.rglob("*")):
                if index >= 32_768:
                    raise ValueError("Unpublished stage directory entry budget exceeded")
                if path.is_symlink():
                    raise ValueError("Unsafe unpublished stage path")
                if path.is_file() and path.suffix in {".dat", ".ldr"}:
                    self.reserve(path, path.stat().st_size)

    def reserve(self, path, size):
        if path in self.files:
            if self.files[path] != size:
                raise ValueError("Unpublished stage file size changed")
            return
        if len(self.files) >= 8192 or self.bytes + size > 256_000_000:
            raise ValueError("Unpublished geometry stage budget exceeded")
        self.files[path] = size
        self.bytes += size


def closure(
    part_id, stage, caches, fetch, references, check=lambda: None, *, cached_only=False, stage_budget=None
):
    """Read existing assets in place; write only newly acquired permitted bytes."""
    if not re.fullmatch(r"[a-z0-9]+", part_id):
        raise ValueError("Invalid curated part ID")
    stage = Path(stage).absolute()
    confined(stage, stage)
    if not cached_only:
        stage.mkdir(parents=True, exist_ok=False)
    records, file_map, origins, rejected, visited, active = {}, {}, {}, [], set(), set()
    total, deadline = 0, time.monotonic() + 300

    def tick():
        check()
        if time.monotonic() > deadline:
            raise ValueError("Part fetch wall-time limit exceeded")

    def walk(path, chain=(), fixed=None):
        nonlocal total
        tick()
        if not SAFE.fullmatch(path) or len(chain) > MAX_DEPTH or path in active:
            raise ValueError("Unsafe path, excessive depth or dependency cycle")
        if path in visited:
            return path
        layer = fixed
        if layer is None:
            layer = next((item for item in caches if item.contains(path)), None)
        if layer:
            data, record = layer.obtain(path)
        else:
            if cached_only:
                raise ValueError("Previously accepted design is absent")
            data, record = fetch(path, deadline, tick), None
        content, names, classification, notices, licenses = envelope(path, data, references, record)
        total += len(data)
        visited.add(path)
        if len(visited) > MAX_FILES or total > MAX_BYTES:
            raise ValueError("Dependency resource limit exceeded")
        if classification == "Shortcut":
            if cached_only or record is not None:
                raise ValueError("Accepted cache contains prohibited Shortcut")
            rejected.append(
                RejectedResource(
                    part_id,
                    path,
                    (*chain, path),
                    classification,
                    BASE + path,
                    sha(data),
                    len(data),
                    tuple(licenses),
                    tuple(names),
                )
            )
            if len(canonical([item.receipt() for item in rejected])) > MAX_REJECTION:
                raise ValueError("Rejection evidence byte budget exceeded")
            return path  # Intentionally do not acquire forbidden descendants.
        if not chain and classification != "Part":
            raise ValueError("A physical root must be a Part")
        active.add(path)
        deps = []
        for name in names:
            tick()
            if layer:
                dep = layer.document["file_map"].get(name)
                if dep is None:
                    raise ValueError("Missing cached dependency mapping")
                deps.append(walk(dep, (*chain, path), fixed=layer))
            else:
                options = ["parts/" + name] if name.startswith("s/") else ["p/" + name, "parts/" + name]
                # Examine both caches before selecting, so an orphan cannot be hidden by a sibling hit.
                present = {option: any([item.contains(option) for item in caches]) for option in options}
                options.sort(key=lambda option: not present[option])
                for option in options:
                    try:
                        deps.append(walk(option, (*chain, path)))
                        break
                    except httpx.HTTPStatusError as error:
                        if error.response.status_code != 404 or option == options[-1]:
                            raise
            if name in file_map and file_map[name] != deps[-1]:
                raise ValueError("Conflicting dependency mapping")
            file_map[name] = deps[-1]
        active.remove(path)
        if record is not None and sorted(set(record.get("dependencies", []))) != sorted(set(deps)):
            raise ValueError("Cached dependency receipt differs from payload")
        records[path] = record or {
            "url": BASE + path,
            "sha256": sha(data),
            "bytes": len(data),
            "classification": classification,
            "description": content.splitlines()[0][2:],
            "notices": notices,
            "dependencies": deps,
        }
        origins[path] = {"kind": "cached", "root": str(layer.root)} if layer else {"kind": "stage"}
        if layer is None:
            target = confined(stage / path, stage)
            if stage_budget is not None:
                stage_budget.reserve(target, len(data))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
        return path

    try:
        walk(f"parts/{part_id}.dat")
        if rejected:
            context = {
                "root_part_id": part_id,
                "input_cache_provenance": [
                    {
                        "root": str(cache.root),
                        "provenance_sha256": sha(cache.raw) if cache.raw is not None else None,
                    }
                    for cache in caches
                ],
                "checked_permitted_resources": {
                    path: {"sha256": record["sha256"], "url": record["url"]}
                    for path, record in sorted(records.items())
                },
                "scope": "Permitted envelopes and reachable permitted siblings were checked; forbidden descendants were not traversed.",
            }
            if (
                len(canonical({"resources": [item.receipt() for item in rejected], "contexts": [context]}))
                > MAX_REJECTION
            ):
                raise ValueError("Rejection evidence byte budget exceeded")
            raise UnsupportedIndividualClosure(rejected, contexts=[context])
        for path in records:
            name = path.removeprefix("parts/").removeprefix("p/")
            if name in file_map and file_map[name] != path:
                raise ValueError("Conflicting individual file mapping")
            file_map[name] = path
        return {"resources": records, "file_map": file_map, "roots": [part_id], "origins": origins}
    finally:
        # Integrity wins over a known classification finding or a transport failure.
        for cache in caches:
            cache.fence.verify()
