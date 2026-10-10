"""Opt-in individual closure publication, authenticated by the existing job lease.

The checkpoint owns journal hashes; filesystem leftovers never create authority.
A private cache lock serializes writes across an expired/reclaimed worker lease.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import time

from ..reconstruction.asset_errors import UnsupportedIndividualClosure
from ..reconstruction.individual_closure import (
    BASE,
    MAX_MANIFEST,
    MAX_REJECTION,
    MAX_RESOURCE,
    SAFE,
    Cache,
    Fence,
    StageBudget,
    canonical,
    closure,
    confined,
    read,
    sha,
)

PROFILE = "new-design-rejection-v2"
VERSION = "checkpointed-individual-publication-v2"
REJECTION_VERSION = "individual-closure-rejection-v1"
FEEDBACK = (
    "The entire current proposal is unavailable because a newly identified design uses prohibited "
    "Shortcut geometry. Re-identify only the listed current-source instances from the official "
    "callout; do not substitute a generic brick, guessed replacement or finished model. "
    "Previously accepted instances and source evidence remain fixed."
)


def profile(config):
    value = config.get("new_part_failure_profile", "legacy")
    if not isinstance(value, str) or value not in {"legacy", PROFILE}:
        raise ValueError("Unknown new-part failure profile")
    if value != "legacy" and (
        config.get("execution_policy", "strict") != "explore"
        or config.get("generation_mode", "strict") != "strict"
    ):
        raise ValueError("New-part rejection requires the exploration engine")
    return value


def binding():
    return {
        "profile": PROFILE,
        "publication_version": VERSION,
        "rejection_receipt_version": REJECTION_VERSION,
        "cache_staging_version": "unpublished-closure-staging-v2",
        "recoverable_classifications": ["Shortcut"],
        "scope": "new_designs_in_the_current_validated_instruction",
        "existing_attempt_and_call_caps": True,
        "limits": {
            "resource_bytes": MAX_RESOURCE,
            "closure_files": 512,
            "closure_bytes": 20_000_000,
            "closure_depth": 24,
            "closure_seconds": 300,
            "designs": 2048,
            "union_files": 8192,
            "union_bytes": 256_000_000,
            "stage_files": 8192,
            "stage_bytes": 256_000_000,
            "rejection_bytes": MAX_REJECTION,
        },
        "feedback_sha256": hashlib.sha256(FEEDBACK.encode()).hexdigest(),
    }


def write_new(path, data):
    confined(path, path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    sync_dir(path.parent)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Publications:
    """A runtime capability built only by orchestration, never by provider output."""

    def __init__(self, *, job_id, directory, trial, checkpoint, save, check, lease_check, scope):
        self.job_id, self.directory = job_id, Path(directory).absolute()
        self.trial = confined(Path(trial).absolute(), self.directory)
        self.checkpoint, self.save, self.check, self.lease_check = checkpoint, save, check, lease_check
        self.scope = {"job_id": job_id, "trial": str(self.trial.relative_to(self.directory)), **scope}
        self.lock_guard = lambda: None
        self.phase_hook = lambda phase: None  # Offline crash injection; not a config/provider input.

    def fence(self):
        self.check()
        self.lock_guard()
        self.lease_check()  # Synchronous SQLite ownership/expiry/cancellation check.

    def key(self, root):
        if not re.fullmatch(r"[a-z0-9]+|materials", root):
            raise ValueError("Invalid publication root")
        return self.scope["trial"] + "/part-closures/" + root

    def retained(self, root):
        return self.checkpoint.get("geometry_publications", {}).get(self.key(root))

    def authenticate(self, root, journal_path):
        retained = self.retained(root)
        if not retained:
            raise ValueError("Missing checkpoint-pinned publication commitment")
        if retained.get("journal_path") != str(journal_path.relative_to(self.directory)) or retained.get(
            "scope_sha256"
        ) != sha(canonical(self.scope | {"root": root})):
            raise ValueError("Publication commitment scope changed")
        data = read(journal_path, self.directory, MAX_MANIFEST)
        if sha(data) != retained.get("journal_sha256"):
            raise ValueError("Publication journal differs from trusted checkpoint")
        journal = json.loads(data)
        if journal.get("scope") != self.scope | {"root": root} or journal.get("version") != VERSION:
            raise ValueError("Publication journal source or policy binding changed")
        return journal

    def pin(self, root, journal_path, journal):
        self.fence()
        if self.retained(root) is not None:
            raise ValueError("Publication commitment already exists")
        if len(self.checkpoint.get("geometry_publications", {})) >= 8193:
            raise ValueError("Publication commitment count exceeds bounded cache")
        self.checkpoint.setdefault("geometry_publications", {})[self.key(root)] = {
            "journal_path": str(journal_path.relative_to(self.directory)),
            "journal_sha256": sha(canonical(journal)),
            "scope_sha256": sha(canonical(self.scope | {"root": root})),
            "status": "prepared",
        }
        self.save("geometry_publication_prepared")
        self.phase_hook("after_checkpoint_pin")

    def complete(self, root, receipt_path, receipt):
        self.fence()
        item = self.retained(root)
        expected = {"path": str(receipt_path.relative_to(self.directory)), "sha256": sha(canonical(receipt))}
        if item.get("status") == "committed":
            if item.get("receipt") != expected:
                raise ValueError("Publication completion commitment changed")
            return
        item.update(status="committed", receipt=expected)
        self.save("geometry_publication_committed")
        self.phase_hook("after_completion_pin")


@contextmanager
def cache_lock(directory, publications):
    import fcntl  # POSIX locking is required only for the opt-in publication path.

    lock = confined(directory.parent / "geometry-publication.lock", publications.directory)
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.is_symlink():
        raise ValueError("Unsafe geometry publication lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    started = time.monotonic()
    try:
        while True:
            publications.fence()
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - started > 30:
                    raise ValueError("Geometry publication lock wait exceeded")
                time.sleep(0.05)
        info, current = os.fstat(fd), lock.stat()
        if (info.st_dev, info.st_ino, info.st_nlink) != (current.st_dev, current.st_ino, 1):
            raise ValueError("Geometry publication lock identity changed")
        previous_guard = publications.lock_guard

        def lock_guard():
            confined(lock, publications.directory)
            current = lock.stat()
            if (info.st_dev, info.st_ino, 1) != (current.st_dev, current.st_ino, current.st_nlink):
                raise ValueError("Geometry publication lock identity changed")

        publications.lock_guard = lock_guard
        try:
            yield
        finally:
            publications.lock_guard = previous_guard
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def merged_document(base, addition):
    merged = deepcopy(base)
    merged.setdefault("library", BASE)
    merged.setdefault("scope", "individual parts and their primitives/subparts only")
    for section in ("resources", "materials", "file_map"):
        dest = merged.setdefault(section, {})
        for key, value in addition.get(section, {}).items():
            if key in dest and dest[key] != value:
                raise ValueError("Individual geometry or provenance changed during accumulation")
            dest[key] = value
    merged["roots"] = sorted(set(base.get("roots", [])) | set(addition.get("roots", [])))
    records = merged["resources"]
    if len(records) > 8192 or sum(item["bytes"] for item in records.values()) > 256_000_000:
        raise ValueError("Assembly geometry cache budget exceeded")
    if len(canonical(merged)) > MAX_MANIFEST:
        raise ValueError("Geometry provenance byte budget exceeded")
    return merged


def publish(root, stage, addition, cache, shared, publications, resolver):
    """Prepare once, persist authority, then promote exactly the approved bytes."""
    journal_path = stage / "publication.json"
    if journal_path.exists() or publications.retained(root):
        journal = publications.authenticate(root, journal_path)
    else:
        entries = []
        for section in ("resources", "materials"):
            for relative, record in addition.get(section, {}).items():
                if relative in cache.document.get(section, {}):
                    continue
                if confined(cache.root / relative, cache.root).exists():
                    raise ValueError("Unreceipted destination file cannot be adopted")
                origin = addition["origins"][relative]
                origin_root = stage if origin["kind"] == "stage" else Path(origin["root"])
                if origin_root not in {stage, cache.root, shared.root}:
                    raise ValueError("Publication source is outside verified cache layers")
                data = read(origin_root / relative, origin_root)
                if sha(data) != record["sha256"] or len(data) != record["bytes"]:
                    raise ValueError("Publication source differs from verified closure")
                entries.append(
                    {
                        "relative": relative,
                        "source": "stage" if origin_root == stage else "shared",
                        "sha256": sha(data),
                        "bytes": len(data),
                    }
                )
        merged = merged_document(cache.document, addition)
        manifest_bytes = canonical(merged)
        write_new(stage / "merged-provenance.json", manifest_bytes)
        cache.fence.verify()
        journal = {
            "version": VERSION,
            "scope": publications.scope | {"root": root},
            "directory": str(cache.root),
            "shared": str(shared.root),
            "base_provenance_sha256": sha(cache.raw) if cache.raw is not None else None,
            "shared_provenance_sha256": sha(shared.raw) if shared.raw is not None else None,
            "merged_provenance_sha256": sha(manifest_bytes),
            "entries": entries,
            "addition": {k: addition.get(k, {}) for k in ("resources", "materials", "file_map")},
            "roots": addition.get("roots", []),
        }
        if len(canonical(journal)) > MAX_MANIFEST:
            raise ValueError("Publication journal exceeds byte bound")
        write_new(journal_path, canonical(journal))
        publications.phase_hook("before_checkpoint_pin")
        publications.pin(root, journal_path, journal)
    # Always read back the checkpoint-bound journal before any cache mutation.
    journal = publications.authenticate(root, journal_path)
    if journal["directory"] != str(cache.root) or journal["shared"] != str(shared.root):
        raise ValueError("Publication target changed")
    merged_bytes = read(stage / "merged-provenance.json", stage, MAX_MANIFEST)
    if sha(merged_bytes) != journal["merged_provenance_sha256"]:
        raise ValueError("Prepared geometry manifest changed")
    merged = json.loads(merged_bytes)
    material_only = root == "materials"
    receipt = {
        "version": VERSION,
        "journal_sha256": sha(canonical(journal)),
        "merged_provenance_sha256": sha(merged_bytes),
        "root": root,
        "scope_sha256": sha(canonical(journal["scope"])),
    }
    receipt_path = stage / "committed.json"
    if publications.retained(root).get("status") == "committed":
        # Later committed roots may extend the manifest; existing entries cannot change.
        if read(receipt_path, stage, MAX_MANIFEST) != canonical(receipt):
            raise ValueError("Committed publication receipt changed")
        current = Cache(cache.root, Fence())
        _verify_committed_destination(current, merged)
        if material_only:
            current.material()
        else:
            closure(root, stage, [current], None, resolver.references, publications.check, cached_only=True)
        current.fence.verify()
        publications.complete(root, receipt_path, receipt)
        return
    # A prepared journal can authorize partial destination files, never an unknown manifest.
    destination_manifest = cache.root / "provenance.json"
    current = read(destination_manifest, cache.root, MAX_MANIFEST) if destination_manifest.exists() else None
    if (sha(current) if current is not None else None) not in {
        journal["base_provenance_sha256"],
        journal["merged_provenance_sha256"],
    }:
        raise ValueError("Publication base provenance changed")
    shared_manifest = shared.root / "provenance.json"
    shared_raw = read(shared_manifest, shared.root, MAX_MANIFEST) if shared_manifest.exists() else None
    if (sha(shared_raw) if shared_raw is not None else None) != journal["shared_provenance_sha256"]:
        raise ValueError("Publication read-through provenance changed")
    # Reverify every old private resource and material before recovery/promotion.
    base_doc = cache.document if current is None or sha(current) != sha(merged_bytes) else merged
    for relative, record in base_doc.get("resources", {}).items():
        target = cache.root / relative
        if target.exists() and sha(read(target, cache.root)) != record["sha256"]:
            raise ValueError("Protected prior geometry changed")
        if relative not in {e["relative"] for e in journal["entries"]} and not target.exists():
            raise ValueError("Protected prior geometry disappeared")
    for relative, record in base_doc.get("materials", {}).items():
        if relative not in {e["relative"] for e in journal["entries"]}:
            data = read(cache.root / relative, cache.root)
            if sha(data) != record["sha256"] or len(data) != record["bytes"]:
                raise ValueError("Protected prior material changed")
    for entry in journal["entries"]:
        publications.fence()
        relative = entry["relative"]
        if not (SAFE.fullmatch(relative) or relative == "LDConfig.ldr"):
            raise ValueError("Unsafe publication entry")
        origin = stage if entry["source"] == "stage" else shared.root
        data = read(origin / relative, origin)
        if len(data) != entry["bytes"] or sha(data) != entry["sha256"]:
            raise ValueError("Prepared publication bytes changed")
        target = confined(cache.root / relative, cache.root)
        if target.exists():
            if read(target, cache.root) != data:
                raise ValueError("Partial publication differs from authenticated bytes")
        else:
            # No temporary destination orphan: bounded immutable data are already fsynced in stage.
            # A crash during exclusive creation is detected as a partial-file mismatch, not adopted.
            write_new(target, data)
        publications.phase_hook("after_file:" + relative)
    publications.fence()
    temporary = confined(cache.root / "provenance.prepared", cache.root)
    if temporary.exists():
        if read(temporary, cache.root, MAX_MANIFEST) != merged_bytes:
            raise ValueError("Pending provenance differs from authenticated commitment")
    else:
        write_new(temporary, merged_bytes)
    temporary.replace(destination_manifest)
    sync_dir(cache.root)
    publications.phase_hook("after_provenance_replace")
    final = Cache(cache.root, Fence())
    if material_only:
        if final.material() is None:
            raise ValueError("Published material is absent")
    else:
        closure(root, stage, [final], None, resolver.references, publications.check, cached_only=True)
    # Recheck all read-through inputs after the authorized manifest replacement.
    cache.fence.verify(ignore_files={cache.root / "provenance.json"})
    if (
        sha(read(shared_manifest, shared.root, MAX_MANIFEST)) if shared_manifest.exists() else None
    ) != journal["shared_provenance_sha256"]:
        raise ValueError("Publication read-through provenance changed")
    for entry in journal["entries"]:
        origin = stage if entry["source"] == "stage" else shared.root
        data = read(origin / entry["relative"], origin)
        if sha(data) != entry["sha256"] or len(data) != entry["bytes"]:
            raise ValueError("Prepared publication bytes changed before completion")
    if receipt_path.exists():
        if read(receipt_path, stage, MAX_MANIFEST) != canonical(receipt):
            raise ValueError("Uncommitted completion receipt changed")
    else:
        write_new(receipt_path, canonical(receipt))
    publications.phase_hook("before_completion_pin")
    publications.complete(root, receipt_path, receipt)


@contextmanager
def protect_cache(cache):
    """Preserve accepted and unused old assets across all root transactions."""
    original = deepcopy(cache.document)
    try:
        yield
    finally:
        cache.fence.verify(ignore_files={cache.root / "provenance.json"})
        manifest = cache.root / "provenance.json"
        current = json.loads(read(manifest, cache.root, MAX_MANIFEST)) if manifest.exists() else {}
        for section in ("resources", "materials", "file_map"):
            if any(
                current.get(section, {}).get(key) != value for key, value in original.get(section, {}).items()
            ):
                raise ValueError("Protected prior provenance changed during acquisition")


def prepare(scene, previous, directory, shared_root, trial, publications, resolver):
    if publications is None:
        raise ValueError("Opt-in geometry needs a checkpoint/lease publication capability")
    directory, shared_root, trial = (
        Path(directory).absolute(),
        Path(shared_root).absolute(),
        Path(trial).absolute(),
    )
    if publications.trial != trial or publications.directory / "geometry" != directory:
        raise ValueError("Publication capability is not bound to this private geometry root")
    roots = sorted({item.part_id for item in scene.instances})
    old = sorted({item["part_id"] for item in (previous or {}).get("instances", [])})
    if len(roots) > 2048 or any(item.geometry_ref != f"parts/{item.part_id}.dat" for item in scene.instances):
        raise ValueError("Invalid or excessive individual physical designs")
    with cache_lock(directory, publications):
        # Pending authorized publications must finish before a normal cache reader sees partial files.
        for root in ["materials", *roots]:
            stage = trial / "part-closures" / root
            if publications.retained(root):
                journal = publications.authenticate(root, stage / "publication.json")
                private = Cache(directory, Fence())
                shared = Cache(shared_root, private.fence)
                publish(
                    root,
                    stage,
                    journal["addition"] | {"roots": journal["roots"]},
                    private,
                    shared,
                    publications,
                    resolver,
                )
        fence = Fence()
        private, shared = Cache(directory, fence), Cache(shared_root, fence)
        try:
            # All accepted roots must already exist privately; never reacquire or reinterpret them.
            for root in old:
                closure(
                    root, trial, [private], None, resolver.references, publications.check, cached_only=True
                )
            if old and private.material() is None:
                raise ValueError("Previously accepted material is absent")
            # Validate retained unused private assets too, so a rejected new part cannot mask corruption.
            for relative, record in private.document["resources"].items():
                data, _ = private.obtain(relative)
                from ..reconstruction.individual_closure import envelope

                envelope(relative, data, resolver.references, record)
            private.material()
        finally:
            fence.verify()
        with protect_cache(private):
            # Publish material through the same authenticated mechanism before new root closures.
            if private.material() is None:
                stage = trial / "part-closures" / "materials"
                if stage.exists():
                    raise ValueError("Unpublished material stage lacks authenticated commitment")
                stage.mkdir(parents=True)
                material = shared.material()
                if material is None:
                    write_new(
                        stage / "provenance.json",
                        canonical({"resources": {}, "file_map": {}, "materials": {}}),
                    )
                    resolver.fetch_materials(stage)
                    material_doc = json.loads(read(stage / "provenance.json", stage, MAX_MANIFEST))
                    record = material_doc["materials"]["LDConfig.ldr"]
                    origin = {"kind": "stage"}
                else:
                    _, record = material
                    origin = {"kind": "cached", "root": str(shared.root)}
                publish(
                    "materials",
                    stage,
                    {"materials": {"LDConfig.ldr": record}, "origins": {"LDConfig.ldr": origin}},
                    private,
                    shared,
                    publications,
                    resolver,
                )
            rejected, rejection_contexts = [], []
            stage_budget = StageBudget(trial / "part-closures")
            for root in roots:
                publications.fence()
                fence = Fence()
                private, shared = Cache(directory, fence), Cache(shared_root, fence)
                if (
                    root in private.document.get("roots", [])
                    or f"parts/{root}.dat" in private.document["resources"]
                ):
                    closure(
                        root,
                        trial,
                        [private],
                        None,
                        resolver.references,
                        publications.check,
                        cached_only=True,
                    )
                    continue
                stage = trial / "part-closures" / root
                if stage.exists():
                    raise ValueError("Unpublished closure stage lacks authenticated commitment")
                try:
                    addition = resolver.stage_individual(
                        root, stage, [private, shared], publications.check, stage_budget=stage_budget
                    )
                    publish(root, stage, addition, private, shared, publications, resolver)
                except UnsupportedIndividualClosure as error:
                    if root in old or any(
                        item.root_part_id != root or item.classification != "Shortcut"
                        for item in error.evidence
                    ):
                        raise ValueError(
                            "Unsupported design is not confined to new current instances"
                        ) from error
                    rejected.extend(error.evidence)
                    rejection_contexts.extend(error.contexts)
                    if (
                        len(
                            canonical(
                                {
                                    "resources": [item.receipt() for item in rejected],
                                    "contexts": rejection_contexts,
                                }
                            )
                        )
                        > MAX_REJECTION
                    ):
                        raise ValueError("Rejection evidence byte budget exceeded")
                # Continue permitted sibling roots; any later hard error takes precedence.
            final = Cache(directory, Fence())
            for root in old:
                closure(root, trial, [final], None, resolver.references, publications.check, cached_only=True)
            final.material()
            final.fence.verify()
            if rejected:
                raise UnsupportedIndividualClosure(rejected, contexts=rejection_contexts)
    from .geometry import verify_individual_assets

    return verify_individual_assets(directory, [item.geometry_ref for item in scene.instances])


def _verify_committed_destination(cache, committed_manifest):
    """Bind every originally committed entry, including unused sibling closures.

    Later publications may add entries/roots. They may not rewrite any original
    body, material receipt, dependency mapping or resource metadata. The current
    manifest is not authority to reinterpret an authenticated old journal.
    """
    # The journal authenticates the whole prepared manifest, including prior
    # materials/assets carried into that publication, not just newly copied files.
    addition = committed_manifest
    for section in ("resources", "materials", "file_map"):
        for relative, original in addition[section].items():
            if cache.document.get(section, {}).get(relative) != original:
                raise ValueError("Committed destination record differs from trusted publication")
            if section != "file_map":
                try:
                    data = cache.fence.read(cache.root / relative, cache.root)
                except FileNotFoundError as error:
                    raise ValueError("Committed destination bytes are missing") from error
                if len(data) != original["bytes"] or sha(data) != original["sha256"]:
                    raise ValueError("Committed destination bytes differ from trusted publication")
    if not set(committed_manifest["roots"]) <= set(cache.document.get("roots", [])):
        raise ValueError("Committed destination root declaration disappeared")


def verify_commitments(directory, checkpoint, job_id, policy_sha256):
    """Read-only resume fence, including outcomes that need no new geometry work."""
    directory = Path(directory).absolute()
    entries = checkpoint.get("geometry_publications", {})
    if not isinstance(entries, dict) or len(entries) > 8193:
        raise ValueError("Invalid geometry publication commitment map")
    destination = None
    try:
        expected = set()
        for key, item in entries.items():
            relative = item.get("journal_path")
            if not isinstance(relative, str) or not relative.endswith("/publication.json"):
                raise ValueError("Invalid publication journal binding")
            path = confined(directory / relative, directory)
            if Path(key) != Path(relative).parent:
                raise ValueError("Publication key differs from its journal path")
            expected.add(path)
            data = read(path, directory, MAX_MANIFEST)
            if sha(data) != item.get("journal_sha256"):
                raise ValueError("Publication journal differs from trusted checkpoint")
            journal = json.loads(data)
            if journal.get("directory") != str(directory / "geometry"):
                raise ValueError("Publication destination is not this job's private geometry")
            scope = journal.get("scope", {})
            if (
                scope.get("job_id") != job_id
                or scope.get("policy_sha256") != policy_sha256
                or sha(canonical(scope)) != item.get("scope_sha256")
                or journal.get("version") != VERSION
            ):
                raise ValueError("Publication scope or frozen policy changed")
            trial = confined(directory / scope["trial"], directory)
            if path.parent.parent != trial / "part-closures" or path.parent.name != scope["root"]:
                raise ValueError("Publication trial or root binding changed")
            if sha(read(trial / "raw-scene.json", directory, 32_000_000)) != scope["raw_scene_sha256"]:
                raise ValueError("Publication proposal changed")
            state = checkpoint.get("exploration_instructions", {}).get(str(int(trial.parent.name)))
            if state is not None and state.get("context_sha256") != scope.get("context_sha256"):
                raise ValueError("Publication instruction context changed")
            merged_bytes = read(path.parent / "merged-provenance.json", directory, MAX_MANIFEST)
            if sha(merged_bytes) != journal["merged_provenance_sha256"]:
                raise ValueError("Prepared geometry manifest changed")
            for entry in journal["entries"]:
                if entry["source"] == "stage":
                    body = read(path.parent / entry["relative"], directory)
                    if sha(body) != entry["sha256"] or len(body) != entry["bytes"]:
                        raise ValueError("Prepared publication bytes changed")
            if item.get("status") == "committed":
                receipt = item.get("receipt", {})
                if receipt.get("path") != str((path.parent / "committed.json").relative_to(directory)):
                    raise ValueError("Publication completion path changed")
                if sha(read(directory / receipt["path"], directory, MAX_MANIFEST)) != receipt.get("sha256"):
                    raise ValueError("Publication completion receipt changed")
                if destination is None:
                    destination = Cache(directory / "geometry", Fence())
                _verify_committed_destination(destination, json.loads(merged_bytes))
            elif item.get("status") != "prepared":
                raise ValueError("Invalid publication commitment state")
        actual = set(
            (directory / "exploration" / "instructions").glob("*/attempt-*/part-closures/*/publication.json")
        )
        if actual != expected:
            raise ValueError(
                "Missing checkpoint-pinned publication commitment; orphan enrollment is forbidden"
            )
    finally:
        if destination is not None:
            destination.fence.verify()


def verify_correction_parent(job, directory, scene):
    """Opt-in admission only; child revisions never inherit journal authority."""
    if profile(job["config"]) == "legacy":
        return
    from .exploration import _policy
    from ..releases.models import digest

    checkpoint = job["checkpoint"]
    if not isinstance(checkpoint.get("exploration_policy"), dict):
        raise ValueError("Opt-in correction parent lacks its frozen publication policy")
    policy = _policy(job["config"], deepcopy(checkpoint), scene.source_sha256, scene.sources[0].page_count)
    verify_commitments(directory, checkpoint, job["id"], digest(policy))
