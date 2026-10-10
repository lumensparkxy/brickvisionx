"""Original synthetic checkpoints prove storage integrity, never reconstruction quality."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import threading
import time

import pytest

from guide2build.core.models import SceneManifest
from guide2build.engine import checkpoint_artifacts as artifacts
from guide2build.engine import store as store_module
from guide2build.engine.store import EngineStore, LeaseLost
from guide2build.releases.models import adapt_v1, digest


def _job(tmp_path, **config):
    store = EngineStore(tmp_path)
    job = store.enqueue("30669", "alt-02", {"revision": "base", **config})
    store.claim("original", job_id=job["id"])
    return store, job["id"]


def _stored(store, identity):
    with store.connect() as con:
        return con.execute("SELECT checkpoint FROM engine_jobs WHERE id=?", (identity,)).fetchone()[0]


def _artifact(store, raw):
    return store.root / json.loads(raw)["candidate_artifact"]["path"]


def _large_checkpoint():
    return {"stage": "synthetic_checkpoint", "completed_panels": 80, "model_calls_used": 9,
        "candidate": {"artifact_kind": "original_synthetic_storage_fixture", "label": "Café — synthetic",
            "signed_zero": -0.0, "snapshots": [{"ordinal": index,
                "poses": {f"synthetic-{n}": {"position_ldu": [n * 20.0, index / 10, 0],
                    "quaternion_xyzw": [0, 0, 0, 1]} for n in range(64)}} for index in range(80)]},
        "retained_findings": [{"category": "unknown", "reason": "Synthetic source remains unresolved."}]}


def test_small_sql_checkpoint_preserves_exact_public_json_and_old_revisions(tmp_path):
    store, identity = _job(tmp_path)
    checkpoint = _large_checkpoint()
    unchanged = deepcopy(checkpoint)
    store.checkpoint(identity, "original", checkpoint)
    raw = _stored(store, identity)
    path = _artifact(store, raw)
    original = path.read_bytes()
    info = path.stat()
    assert len(raw.encode()) < len(json.dumps(checkpoint).encode()) / 100
    assert json.loads(raw)["candidate_artifact"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert "snapshots" not in raw and "candidate" not in json.loads(raw)["checkpoint"]
    assert checkpoint == unchanged == EngineStore(tmp_path).get(identity)["checkpoint"]
    assert digest(unchanged) == digest(store.get(identity)["checkpoint"])
    assert list(checkpoint["candidate"]) == list(store.get(identity)["checkpoint"]["candidate"])
    assert b'"signed_zero":-0.0' in original
    checkpoint["stage"] = "another_durable_stage"
    store.checkpoint(identity, "original", checkpoint)
    assert path.read_bytes() == original and path.stat().st_mtime_ns == info.st_mtime_ns
    assert path.stat().st_ino == info.st_ino
    checkpoint["candidate"]["snapshots"][-1]["poses"]["synthetic-1"]["position_ldu"][0] += 20
    store.checkpoint(identity, "original", checkpoint, "paused")
    assert _artifact(store, _stored(store, identity)) != path
    assert path.read_bytes() == original
    assert len(list(path.parent.glob("*.json"))) == 2
    assert EngineStore(tmp_path).get(identity)["checkpoint"] == checkpoint


def test_scene_and_checkpoint_authentication_digests_survive_round_trip(tmp_path, scene_data):
    store, identity = _job(tmp_path)
    scene = adapt_v1(SceneManifest.model_validate(scene_data),
                    "https://www.lego.com/en-us/service/building-instructions/99999", 8)
    checkpoint = {"candidate": scene.model_dump(mode="json"), "source_sha256": scene.source_sha256}
    store.checkpoint(identity, "original", checkpoint, "paused")
    restored = store.claim("resumed", job_id=identity)["checkpoint"]
    assert digest(restored) == digest(checkpoint)
    assert digest(restored["candidate"]) == digest(scene)


def test_inline_legacy_rows_are_read_without_migration(tmp_path):
    store, identity = _job(tmp_path)
    legacy = {"candidate": {"original_legacy": True}, "completed_panels": 3}
    raw = json.dumps(legacy, indent=2)
    with store.connect() as con:
        con.execute("UPDATE engine_jobs SET checkpoint=? WHERE id=?", (raw, identity))
    assert EngineStore(tmp_path).get(identity)["checkpoint"] == legacy
    assert _stored(store, identity) == raw
    assert not (store.root / "checkpoint-artifacts").exists()
    store.checkpoint(identity, "original", legacy, "paused")
    assert artifacts.FORMAT_KEY in json.loads(_stored(store, identity))
    assert store.get(identity)["checkpoint"] == legacy


@pytest.mark.parametrize("checkpoint", [{"stage": "before_candidate"}, {"candidate": None}])
def test_checkpoint_without_candidate_stays_inline(tmp_path, checkpoint):
    store, identity = _job(tmp_path)
    store.checkpoint(identity, "original", checkpoint)
    assert json.loads(_stored(store, identity)) == checkpoint
    assert not (store.root / "checkpoint-artifacts").exists()


def test_corrupt_existing_artifact_is_never_repaired_or_overwritten(tmp_path):
    store, identity = _job(tmp_path)
    checkpoint = {"candidate": {"x": 10}}
    store.checkpoint(identity, "original", checkpoint)
    raw = _stored(store, identity)
    path = _artifact(store, raw)
    before = artifacts.checkpoint_artifact_stat(store.root, identity, raw)
    path.write_bytes(path.read_bytes().replace(b"10", b"20"))
    corrupt = path.read_bytes()
    assert artifacts.checkpoint_artifact_stat(store.root, identity, raw) != before
    with pytest.raises(ValueError, match="hash changed"):
        store.get(identity)
    with pytest.raises(ValueError, match="hash changed"):
        store.checkpoint(identity, "original", checkpoint)
    assert path.read_bytes() == corrupt and _stored(store, identity) == raw


@pytest.mark.parametrize("change", ["missing", "symlink", "directory", "size", "traversal", "absolute", "cross_job", "unknown_version", "duplicate_candidate"])
def test_reference_and_file_corruption_fail_closed(tmp_path, change):
    store, identity = _job(tmp_path)
    store.checkpoint(identity, "original", {"candidate": {"original": "synthetic"}})
    raw = json.loads(_stored(store, identity))
    ref = raw["candidate_artifact"]
    path = store.root / ref["path"]
    if change in {"missing", "symlink", "directory"}:
        original = path.read_bytes()
        path.unlink()
        if change == "symlink":
            target = tmp_path / "outside.json"
            target.write_bytes(original)
            path.symlink_to(target)
        if change == "directory":
            path.mkdir()
    elif change == "size":
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "traversal":
        ref["path"] = "../outside.json"
    elif change == "absolute":
        ref["path"] = str(path)
    elif change == "cross_job":
        ref["job_id"] = "different-job"
        ref["path"] = ref["path"].replace(identity, "different-job")
    elif change == "unknown_version":
        raw[artifacts.FORMAT_KEY] = "future-unverified"
    else:
        raw["checkpoint"]["candidate"] = {"replace_verified_candidate": True}
    with pytest.raises(ValueError):
        artifacts.hydrate_checkpoint(store.root, identity, raw)


def test_symlinked_artifact_directory_cannot_write_outside_root(tmp_path):
    store, identity = _job(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.root / "checkpoint-artifacts").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe"):
        store.checkpoint(identity, "original", {"candidate": {"x": 1}})
    assert list(outside.iterdir()) == [] and _stored(store, identity) == "{}"


@pytest.mark.parametrize("candidate", [{"coordinate": float("nan")}, {"coordinate": float("inf")}, "wrong-shape"])
def test_invalid_candidate_never_reaches_sql_or_artifacts(tmp_path, candidate):
    store, identity = _job(tmp_path)
    with pytest.raises(ValueError):
        store.checkpoint(identity, "original", {"candidate": candidate})
    assert _stored(store, identity) == "{}" and not (store.root / "checkpoint-artifacts").exists()


def test_bounded_candidate_and_metadata(tmp_path, monkeypatch):
    store, identity = _job(tmp_path)
    monkeypatch.setattr(artifacts, "MAX_CANDIDATE_BYTES", 50)
    with pytest.raises(ValueError, match="candidate exceeds"):
        store.checkpoint(identity, "original", {"candidate": {"x": "x" * 51}})
    monkeypatch.setattr(artifacts, "MAX_METADATA_BYTES", 40)
    with pytest.raises(ValueError, match="metadata exceeds"):
        store.checkpoint(identity, "original", {"long": "x" * 50, "candidate": {"x": 1}})
    assert _stored(store, identity) == "{}" and not (store.root / "checkpoint-artifacts").exists()


def test_interrupted_publication_keeps_previous_durable_checkpoint(tmp_path, monkeypatch):
    store, identity = _job(tmp_path)
    previous = {"candidate": {"x": 1}, "stage": "before"}
    store.checkpoint(identity, "original", previous)
    raw = _stored(store, identity)
    old = _artifact(store, raw).read_bytes()
    def crash(*args, **kwargs):
        raise KeyboardInterrupt("Synthetic publication interruption")
    monkeypatch.setattr(artifacts.os, "link", crash)
    with pytest.raises(KeyboardInterrupt):
        store.checkpoint(identity, "original", {"candidate": {"x": 2}, "stage": "after"})
    assert _stored(store, identity) == raw and _artifact(store, raw).read_bytes() == old
    assert store.get(identity)["checkpoint"] == previous
    assert not list((store.root / "checkpoint-artifacts").rglob("*.partial"))


def test_artifact_is_published_before_final_lease_fence_without_replacing_prior_state(tmp_path, monkeypatch):
    store, identity = _job(tmp_path)
    previous = {"candidate": {"x": 1}}
    store.checkpoint(identity, "original", previous)
    raw = _stored(store, identity)
    original = store_module.serialize_checkpoint
    def lease_changes(root, job_id, checkpoint):
        encoded = original(root, job_id, checkpoint)
        assert (root / json.loads(encoded)["candidate_artifact"]["path"]).is_file()
        assert _stored(store, identity) == raw
        with store.connect() as con:
            con.execute("UPDATE engine_jobs SET owner='new-owner',lease_until=? WHERE id=?", (time.time() + 120, job_id))
        return encoded
    monkeypatch.setattr(store_module, "serialize_checkpoint", lease_changes)
    with pytest.raises(LeaseLost):
        store.checkpoint(identity, "original", {"candidate": {"x": 2}})
    assert _stored(store, identity) == raw and store.get(identity)["checkpoint"] == previous
    assert len(list((store.root / "checkpoint-artifacts").rglob("*.json"))) == 2


def test_coarse_control_reads_never_hydrate_or_hash_candidate(tmp_path, monkeypatch):
    store, identity = _job(tmp_path, generation_mode="alpha_fast", quality_profile="alpha")
    store.checkpoint(identity, "original", {"candidate": {"x": 1}, "alpha_source_complete": True,
        "alpha_completed_pages": 8, "completed_pages": 8, "completed_panels": 12, "model_calls_used": 5})
    def forbidden(*args):
        raise AssertionError("A coarse control read touched candidate bytes")
    monkeypatch.setattr(artifacts, "_read_candidate", forbidden)
    snapshot = store.queue_snapshot([identity])[0]
    assert snapshot["alpha_source_complete"] and snapshot["alpha_completed_pages"] == 8
    assert snapshot["completed_panels"] == 12 and snapshot["updated"] > 0
    assert store.lineage_model_calls_used(identity) == 5
    assert store.cancel_requested(identity) is False
    store.heartbeat(identity, "original")
    store.cancel(identity)
    assert store.cancel_requested(identity) is True
    with pytest.raises(AssertionError, match="candidate bytes"):
        store.get(identity)


def test_stage_render_reset_and_fork_use_the_same_storage_scheme(tmp_path, monkeypatch, scene_data):
    store, identity = _job(tmp_path)
    scene = adapt_v1(SceneManifest.model_validate(scene_data),
                    "https://www.lego.com/en-us/service/building-instructions/99999", 8)
    scene.revision = "base"
    checkpoint = {"candidate": scene.model_dump(mode="json"), "source_sha256": scene.source_sha256}
    store.checkpoint(identity, "original", checkpoint, "paused")
    directory = store.root / "jobs" / identity
    directory.mkdir(parents=True)
    (directory / "scene.json").write_text(scene.model_dump_json())
    render = tmp_path / "synthetic-render-receipt"
    render.mkdir()
    report = {"scene_sha256": digest(scene), "scope": "synthetic store test, no browser rendering"}
    (render / "report.json").write_text(json.dumps(report))
    original_artifact = _artifact(store, _stored(store, identity))
    original_bytes = original_artifact.read_bytes()
    store.record_render(identity, render, report)
    assert _artifact(store, _stored(store, identity)) == original_artifact
    revised = deepcopy(checkpoint)
    revised["candidate"]["revision"] = "fork-one"
    def materialize(path):
        (path / "scene.json").write_text(json.dumps(revised["candidate"]))
    parent = store.get(identity)
    child = store.fork_revision(identity, correction_id="synthetic-only", expected_scene_sha256=digest(scene),
        request_sha256="a" * 64, config={"revision": "fork-one"}, checkpoint=revised,
        materialize=materialize, expected_checkpoint_sha256=digest(parent["checkpoint"]))
    assert child["checkpoint"] == revised
    assert json.loads(_stored(store, child["id"]))["candidate_artifact"]["job_id"] == child["id"]
    assert store.get(identity) == parent and original_artifact.read_bytes() == original_bytes
    monkeypatch.setattr("guide2build.releases.packaging.verify_manifest", lambda value: None)
    store.staged(identity, {"set_number": "30669", "guide_id": "alt-02", "source_sha256": scene.source_sha256})
    assert store.get(identity)["state"] == "awaiting_approval"
    assert _artifact(store, _stored(store, identity)) == original_artifact
    store.reset_candidate(child["id"])
    assert "candidate" not in store.get(child["id"])["checkpoint"]
    assert artifacts.FORMAT_KEY not in json.loads(_stored(store, child["id"]))
    assert original_artifact.read_bytes() == original_bytes


def test_file_stat_is_only_cache_invalidation_and_never_integrity_proof(tmp_path):
    store, identity = _job(tmp_path)
    store.checkpoint(identity, "original", {"candidate": {"x": 1}})
    raw = _stored(store, identity)
    path = _artifact(store, raw)
    before = path.stat()
    token = artifacts.checkpoint_artifact_stat(store.root, identity, raw)
    path.write_bytes(path.read_bytes().replace(b"1", b"2"))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert artifacts.checkpoint_artifact_stat(store.root, identity, raw) != token
    with pytest.raises(ValueError, match="hash changed"):
        artifacts.hydrate_checkpoint(store.root, identity, raw)


def test_simultaneous_identical_artifact_publication_is_complete_and_immutable(tmp_path):
    store, identity = _job(tmp_path)
    checkpoint = _large_checkpoint()
    ready = threading.Barrier(4)
    def publish(_index):
        ready.wait(timeout=5)
        return artifacts.serialize_checkpoint(store.root, identity, checkpoint)
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(publish, range(4)))
    assert len(set(outputs)) == 1
    assert artifacts.hydrate_checkpoint(store.root, identity, outputs[0]) == checkpoint
    files = list((store.root / "checkpoint-artifacts").rglob("*"))
    assert sum(path.suffix == ".json" for path in files) == 1
    assert not any(path.suffix == ".partial" for path in files)


@pytest.mark.parametrize("data", [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]'])
def test_hash_bound_artifact_still_requires_unambiguous_finite_json_object(tmp_path, data):
    store, identity = _job(tmp_path)
    raw = json.loads(artifacts.serialize_checkpoint(store.root, identity, {"candidate": {"x": 1}}))
    ref = raw["candidate_artifact"]
    sha256 = hashlib.sha256(data).hexdigest()
    path = (store.root / ref["path"]).with_name(sha256 + ".json")
    path.write_bytes(data)
    ref.update(sha256=sha256, size_bytes=len(data), path=str(path.relative_to(store.root)))
    with pytest.raises(ValueError):
        artifacts.hydrate_checkpoint(store.root, identity, raw)
