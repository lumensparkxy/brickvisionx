"""Private immutable candidate storage; public checkpoints retain their JSON shape.

Only newly saved checkpoints use this representation. Inline legacy rows remain
readable, and hydration always verifies the candidate bytes. Files are published
without replacement before a caller commits its fenced SQLite update. An aborted
update can leave an unreferenced artifact, never a reference to a partial file.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid


FORMAT_KEY = "_guide2build_checkpoint_storage"
FORMAT_VERSION = "candidate-artifact-v1"
MAX_CANDIDATE_BYTES = 128_000_000
MAX_METADATA_BYTES = 32_000_000
MAX_CHECKPOINT_BYTES = MAX_CANDIDATE_BYTES + MAX_METADATA_BYTES
_JOB = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")


def _json_bytes(value):
    # Preserve mapping order and JSON numeric representation, including -0.0.
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("Duplicate checkpoint JSON key")
        value[key] = item
    return value


def _constant(_value):
    raise ValueError("Nonfinite checkpoint JSON value")


def _load(raw, limit=MAX_CHECKPOINT_BYTES):
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, (str, bytes)) or len(raw) > limit:
        raise ValueError("Checkpoint JSON exceeds its storage limit")
    if isinstance(raw, str) and len(raw.encode("utf-8")) > limit:
        raise ValueError("Checkpoint JSON exceeds its storage limit")
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(value, dict):
        raise ValueError("Checkpoint JSON must be an object")
    return value


def _job_id(value):
    if not isinstance(value, str) or not _JOB.fullmatch(value):
        raise ValueError("Invalid checkpoint artifact job identity")
    return value


def _relative(job_id, sha256):
    return f"checkpoint-artifacts/{job_id}/candidate/{sha256}.json"


def _unpack(raw, job_id=None):
    value = _load(raw)
    if FORMAT_KEY not in value:
        return value, None
    if (set(value) != {FORMAT_KEY, "checkpoint", "candidate_artifact"}
            or value[FORMAT_KEY] != FORMAT_VERSION or not isinstance(value["checkpoint"], dict)
            or "candidate" in value["checkpoint"] or FORMAT_KEY in value["checkpoint"]):
        raise ValueError("Invalid checkpoint storage envelope")
    ref = value["candidate_artifact"]
    if (not isinstance(ref, dict) or set(ref) != {"kind", "job_id", "sha256", "size_bytes", "path"}
            or ref["kind"] != "candidate-json" or not isinstance(ref["sha256"], str)
            or not _SHA.fullmatch(ref["sha256"]) or type(ref["size_bytes"]) is not int
            or not 1 <= ref["size_bytes"] <= MAX_CANDIDATE_BYTES):
        raise ValueError("Invalid checkpoint candidate artifact reference")
    _job_id(ref["job_id"])
    if (job_id is not None and ref["job_id"] != _job_id(job_id)
            or ref["path"] != _relative(ref["job_id"], ref["sha256"])):
        raise ValueError("Checkpoint candidate artifact escapes its job identity")
    return value["checkpoint"], ref


@contextmanager
def _candidate_directory(engine_root, job_id, *, create=False):
    """Open each private directory relative to its verified parent, never a symlink."""
    root = Path(engine_root).absolute()
    if root.resolve() != root:
        raise ValueError("Unsafe checkpoint artifact root")
    _job_id(job_id)
    descriptor = None
    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for component in ("checkpoint-artifacts", job_id, "candidate"):
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    except OSError as error:
        raise ValueError("Unavailable or unsafe checkpoint artifact directory") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_candidate(directory, ref):
    name = ref["sha256"] + ".json"
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise ValueError("Unavailable or unsafe checkpoint candidate artifact") from error
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != ref["size_bytes"]:
            raise ValueError("Checkpoint candidate artifact size or file type changed")
        data = stream.read(ref["size_bytes"] + 1)
    if len(data) != ref["size_bytes"] or hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise ValueError("Checkpoint candidate artifact hash changed")
    return data


def _publish_candidate(engine_root, job_id, data):
    sha256 = hashlib.sha256(data).hexdigest()
    ref = {"kind": "candidate-json", "job_id": job_id, "sha256": sha256,
           "size_bytes": len(data), "path": _relative(job_id, sha256)}
    with _candidate_directory(engine_root, job_id, create=True) as directory:
        try:
            existing = _read_candidate(directory, ref)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != data:
                raise ValueError("Checkpoint candidate artifact content collision")
            return ref
        temporary = ".candidate-" + uuid.uuid4().hex + ".partial"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # An atomic hard link publishes complete bytes without replacing
                # an older artifact, including under simultaneous identical writes.
                os.link(temporary, sha256 + ".json", src_dir_fd=directory, dst_dir_fd=directory,
                        follow_symlinks=False)
            except FileExistsError:
                if _read_candidate(directory, ref) != data:
                    raise ValueError("Checkpoint candidate artifact content collision")
            os.fsync(directory)
        finally:
            os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
    return ref


def serialize_checkpoint(engine_root, job_id, checkpoint):
    """Publish candidate bytes first; return the small JSON for a later fenced SQL write."""
    _job_id(job_id)
    if not isinstance(checkpoint, dict) or FORMAT_KEY in checkpoint:
        raise ValueError("Expected a public checkpoint object, not a storage envelope")
    candidate = checkpoint.get("candidate")
    if candidate is None:
        encoded = _json_bytes(checkpoint)
        if len(encoded) > MAX_METADATA_BYTES:
            raise ValueError("Checkpoint metadata exceeds its storage limit")
        return encoded.decode("utf-8")
    if not isinstance(candidate, dict):
        raise ValueError("Checkpoint candidate must be a JSON object")
    metadata = {key: value for key, value in checkpoint.items() if key != "candidate"}
    if len(_json_bytes(metadata)) > MAX_METADATA_BYTES:
        raise ValueError("Checkpoint metadata exceeds its storage limit")
    data = _json_bytes(candidate)
    if len(data) > MAX_CANDIDATE_BYTES:
        raise ValueError("Checkpoint candidate exceeds its storage limit")
    ref = _publish_candidate(engine_root, job_id, data)
    return _json_bytes({FORMAT_KEY: FORMAT_VERSION, "checkpoint": metadata,
                        "candidate_artifact": ref}).decode("utf-8")


def hydrate_checkpoint(engine_root, job_id, raw_checkpoint):
    """Restore the unchanged public interface, verifying every referenced candidate read."""
    metadata, ref = _unpack(raw_checkpoint, job_id)
    value = dict(metadata)
    if ref is not None:
        with _candidate_directory(engine_root, job_id) as directory:
            try:
                data = _read_candidate(directory, ref)
            except FileNotFoundError as error:
                raise ValueError("Checkpoint candidate artifact is missing") from error
        value["candidate"] = _load(data, MAX_CANDIDATE_BYTES)
    return value


def checkpoint_metadata(raw_checkpoint):
    """Small control fields only; deliberately neither reads nor verifies candidate bytes."""
    metadata, _ = _unpack(raw_checkpoint)
    return {key: value for key, value in metadata.items() if key != "candidate"}


def checkpoint_artifact_stat(engine_root, job_id, raw_checkpoint):
    """Cache invalidation token, not integrity proof; hydration still hashes the bytes."""
    _, ref = _unpack(raw_checkpoint, job_id)
    if ref is None:
        return None
    with _candidate_directory(engine_root, job_id) as directory:
        try:
            info = os.stat(ref["sha256"] + ".json", dir_fd=directory, follow_symlinks=False)
        except OSError as error:
            raise ValueError("Checkpoint candidate artifact is missing") from error
        if not stat.S_ISREG(info.st_mode) or info.st_size != ref["size_bytes"]:
            raise ValueError("Checkpoint candidate artifact size or file type changed")
    return (ref["sha256"], info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
