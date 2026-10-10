"""Offline integrity regressions for the separate v2 private mirror only."""

from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3

import pytest

from guide2build.catalog import find_guide
from guide2build.engine import alpha, closure_publication as pub, corrections, exploration
from guide2build.engine.store import execution_config
from guide2build.reconstruction.individual_closure import confined, read, canonical, sha
from guide2build.releases.models import SceneV2, digest
import test_engine_exploration as original_harness
from test_engine_exploration import harness as harness
from test_engine_new_part_rejection import integration as integration, resolver as resolver, tree, seed, dat
from test_engine_corrections import correction_request, seed_job

REAL_GEOMETRY_PINS = alpha._geometry_pins


@pytest.mark.parametrize("kind", ["sibling", "back_inside", "root_dotdot", "relative"])
def test_parent_traversal_is_rejected_before_file_open(tmp_path, monkeypatch, kind):
    root = tmp_path / "private"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside marker")
    (root / "inside").write_bytes(b"inside marker")
    path = root / ".." / outside.name
    if kind == "back_inside":
        path = root / ".." / "private" / "inside"
    if kind == "root_dotdot":
        root = tmp_path / ".." / tmp_path.name / "private"
        path = root / "inside"
    if kind == "relative":
        monkeypatch.chdir(tmp_path)
        root = Path("private")
        path = root / ".." / "outside"
    monkeypatch.setattr(os, "open", lambda *a, **kw: pytest.fail("Traversal reached file open"))
    with pytest.raises(ValueError, match="traversal"):
        read(path, root)


def test_directory_handle_walk_blocks_ancestor_swap_before_leaf_open(tmp_path, monkeypatch):
    root = tmp_path / "private"
    root.mkdir()
    inside = root / "child"
    inside.mkdir()
    (inside / "leaf").write_bytes(b"inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leaf").write_bytes(b"outside")
    real_open = os.open
    mutated = False
    opened_leaf = False

    def intercept(path, flags, *a, **kw):
        nonlocal mutated, opened_leaf
        if path == "child" and not mutated:
            inside.rename(root / "saved")
            inside.symlink_to(outside)
            mutated = True
        if path == "leaf":
            opened_leaf = True
        return real_open(path, flags, *a, **kw)

    monkeypatch.setattr(os, "open", intercept)
    with pytest.raises(OSError):
        read(inside / "leaf", root)
    assert mutated and not opened_leaf


def test_regular_inside_path_remains_readable_and_symlinks_are_not_followed(tmp_path):
    root = tmp_path / "private"
    root.mkdir()
    (root / "item").write_bytes(b"bytes")
    assert read(root / "item", root) == b"bytes"
    (root / "alias").symlink_to(root / "item")
    with pytest.raises(ValueError, match="Symlink"):
        confined(root / "alias", root)


def add_unused(h):
    original = h.provider.call

    def call(*a, **kw):
        result = original(*a, **kw)
        if result.get("delta_json"):
            delta = json.loads(result["delta_json"])
            step = delta["new_steps"][0]
            if step["main_step_number"] == 1:
                part = deepcopy(delta["new_instances"][0])
                part.update(instance_id="permitted-unused", part_id="newb", geometry_ref="parts/newb.dat")
                delta["new_instances"].append(part)
                for key in ["introduced_instance_ids", "visible_instance_ids", "active_instance_ids"]:
                    step[key].append("permitted-unused")
                step["poses"]["permitted-unused"] = {
                    "position_ldu": [40, 0, 0],
                    "quaternion_xyzw": [0, 0, 0, 1],
                }
                result["delta_json"] = json.dumps(delta)
        return result

    h.provider.call = call


def finish(h, monkeypatch):
    monkeypatch.setattr(alpha, "_geometry_pins", REAL_GEOMETRY_PINS)
    add_unused(h)
    assert exploration.run_exploration(**h.args)
    assert h.cp["processed_panels"] == 2 and h.cp["reconstructed_panels"] == 1
    assert "newb" not in {p["part_id"] for p in h.cp["candidate"]["instances"]}
    return h


def mutate(h, kind):
    root = h.directory / "geometry"
    path = root / "provenance.json"
    doc = json.loads(path.read_text())
    relative = "parts/newb.dat"
    if kind in {"body_only", "body_and_record"}:
        p = root / relative
        b = p.read_bytes() + b"0 changed unused published body\n"
        p.write_bytes(b)
        if kind == "body_and_record":
            doc["resources"][relative].update(sha256=sha(b), bytes=len(b))
    elif kind == "record":
        doc["resources"][relative]["description"] = "changed original metadata"
    elif kind == "file_map":
        doc["file_map"].pop("newb.dat")
    elif kind == "root":
        doc["roots"].remove("newb")
    elif kind == "resource_removed":
        doc["resources"].pop(relative)
        doc["file_map"].pop("newb.dat")
        doc["roots"].remove("newb")
        (root / relative).unlink()
    elif kind in {"material_body", "material_and_record"}:
        p = root / "LDConfig.ldr"
        b = p.read_bytes() + b"0 changed material\n"
        p.write_bytes(b)
        if kind == "material_and_record":
            doc["materials"]["LDConfig.ldr"].update(sha256=sha(b), bytes=len(b))
    elif kind == "material_record":
        doc["materials"]["LDConfig.ldr"]["url"] = pub.BASE + "wrong.ldr"
    else:
        raise AssertionError(kind)
    path.write_bytes(canonical(doc))


@pytest.mark.parametrize(
    "kind",
    [
        "body_only",
        "body_and_record",
        "record",
        "file_map",
        "root",
        "resource_removed",
        "material_body",
        "material_and_record",
        "material_record",
    ],
)
def test_no_call_resume_binds_all_original_destination_entries(integration, resolver, monkeypatch, kind):
    h = integration
    # Force material publication too, so its authority is the prepared journal.
    (h.directory / "geometry/provenance.json").unlink()
    (h.directory / "geometry/LDConfig.ldr").unlink()
    finish(h, monkeypatch)
    old = deepcopy(h.cp["geometry_publications"])
    calls = len(h.provider.calls)
    mutate(h, kind)
    h.store.claim("runner-owner", job_id=h.job["id"])
    with pytest.raises((ValueError, FileNotFoundError)):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == calls and h.cp["geometry_publications"] == old


def test_additive_later_publication_and_completed_resume_still_work(integration, resolver, monkeypatch):
    h = finish(integration, monkeypatch)
    calls = len(h.provider.calls)
    item = next(v for k, v in h.cp["geometry_publications"].items() if k.endswith("/newb"))
    journal = json.loads((h.directory / item["journal_path"]).read_text())
    # newb was published in the rejected first instruction; synthetic was a
    # legitimate subsequent publication, and must not invalidate that old entry.
    assert journal["merged_provenance_sha256"] != sha((h.directory / "geometry/provenance.json").read_bytes())
    h.store.claim("runner-owner", job_id=h.job["id"])
    assert exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == calls == 14 and h.cp["model_calls_used"] == 14


def source_fixture(h, monkeypatch):
    body = b"%PDF-1.4\nOriginal synthetic source for correction integration.\n"
    source_hash = sha(body)
    pages = h.pages.parent / source_hash
    h.pages.rename(pages)
    h.pages = pages
    h.args.update(pages_dir=pages, source_hash=source_hash)
    monkeypatch.setattr(original_harness, "SOURCE", source_hash)
    source = h.store.data_dir / "sources/30669/alt-02/source.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(body)
    url = find_guide("30669", "alt-02")["pdf_url"]
    source.with_suffix(".receipt.json").write_bytes(
        canonical(
            {
                "requested_url": url,
                "resolved_url": url,
                "sha256": source_hash,
                "size_bytes": len(body),
                "downloaded_at": "2026-10-05T00:00:00Z",
            }
        )
    )


def fork_request(h, tmp_path, mode="command"):
    scene = SceneV2.model_validate(h.cp["candidate"])
    step = scene.steps[0]
    evidence = step.source.model_dump(mode="json")
    command = {
        "op": "pose",
        "step_id": step.step_id,
        "instance_id": step.visible_instance_ids[0],
        "pose": {"position_ldu": [41, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]},
        "reason": "Synthetic source-bound correction",
        "evidence": evidence,
    }
    data = {
        "schema_version": "1.0",
        "correction_id": "v2-parent-test",
        "expected_scene_sha256": digest(scene),
        "actor": "agent",
        "reason": "Synthetic bound correction",
        "evidence": [evidence],
        "commands": [command] if mode == "command" else [],
        "restart_main_step": 2 if mode == "restart" else None,
    }
    if mode == "restart":
        data["guidance"] = ["Re-identify the current synthetic source; no new reference poses."]
    p = tmp_path / "correction-request.json"
    p.write_bytes(canonical(data))
    return p


@pytest.mark.parametrize("mode", ["command", "restart"])
def test_actual_correction_child_inherits_opt_in_and_budget_without_parent_journals(
    integration, resolver, monkeypatch, tmp_path, mode
):
    h = integration
    source_fixture(h, monkeypatch)
    finish(h, monkeypatch)
    before = h.store.get(h.job["id"])
    files = tree(h.directory)
    request = fork_request(h, tmp_path, mode)
    child = corrections.fork_correction(h.store, h.job["id"], request, "v2-child-" + mode)
    assert h.store.get(h.job["id"]) == before and tree(h.directory) == files
    assert child["config"]["new_part_failure_profile"] == pub.PROFILE
    assert child["checkpoint"]["model_calls_used"] == child["checkpoint"]["inherited_model_calls_used"] == 14
    assert child["checkpoint"]["local_model_calls_used"] == 0
    assert "geometry_publications" not in child["checkpoint"]
    directory = h.store.root / "jobs" / child["id"]
    assert not list(directory.rglob("publication.json"))
    assert not (directory / "geometry/parts/newb.dat").exists()
    assert len(h.provider.calls) == 14
    policy = child["checkpoint"]["exploration_policy"]
    assert policy["new_part_failure_policy"] == pub.binding()
    pub.verify_commitments(directory, child["checkpoint"], child["id"], digest(policy))


@pytest.mark.parametrize("phase", ["before_admission", "before_transaction", "after_copy"])
def test_actual_correction_rechecks_unused_parent_publication_at_transaction_boundaries(
    integration, resolver, monkeypatch, tmp_path, phase
):
    h = integration
    source_fixture(h, monkeypatch)
    finish(h, monkeypatch)
    request = fork_request(h, tmp_path)

    def row_count():
        with sqlite3.connect(h.store.root / "jobs.sqlite3") as db:
            return db.execute("select count(*) from engine_jobs").fetchone()[0]

    before = row_count()
    calls = len(h.provider.calls)
    if phase == "before_admission":
        mutate(h, "body_and_record")
    elif phase == "before_transaction":
        original = h.store.fork_revision

        def fork(*a, **kw):
            mutate(h, "body_and_record")
            return original(*a, **kw)

        monkeypatch.setattr(h.store, "fork_revision", fork)
    else:
        original = corrections._copy_geometry

        def copy(*a, **kw):
            result = original(*a, **kw)
            mutate(h, "body_and_record")
            return result

        monkeypatch.setattr(corrections, "_copy_geometry", copy)
    with pytest.raises(ValueError, match="Committed destination"):
        corrections.fork_correction(h.store, h.job["id"], request, "rejected-child")
    assert row_count() == before and len(h.provider.calls) == calls


def test_legacy_correction_does_not_invoke_publication_admission(tmp_path, scene_data, monkeypatch):
    store, job_id, scene, directory = seed_job(tmp_path, scene_data)
    monkeypatch.setattr(
        pub, "verify_commitments", lambda *a: pytest.fail("Legacy parent reached opt-in verification")
    )
    request = correction_request(tmp_path, scene)
    before = store.get(job_id)
    child = corrections.fork_correction(store, job_id, request, "legacy-child")
    assert store.get(job_id) == before
    assert "new_part_failure_profile" not in child["config"]
    assert "new_part_failure_policy" not in child["checkpoint"]["exploration_policy"]


def test_v1_profile_is_not_silently_migrated():
    with pytest.raises(ValueError, match="Unknown new-part"):
        execution_config(
            {"execution_policy": "explore", "new_part_failure_profile": "new-design-rejection-v1"}
        )
    assert pub.PROFILE == "new-design-rejection-v2"
    assert pub.binding()["publication_version"] == "checkpointed-individual-publication-v2"


@pytest.mark.parametrize("kind", ["material", "unused_prior_resource"])
def test_committed_full_manifest_keeps_carried_forward_entries_immutable(
    integration, resolver, monkeypatch, kind
):
    h = integration
    if kind == "unused_prior_resource":
        seed(h.directory / "geometry", {"parts/prior.dat": dat()})
    finish(h, monkeypatch)
    assert not any(key.endswith("/materials") for key in h.cp["geometry_publications"])
    root = h.directory / "geometry"
    relative, section = (
        ("LDConfig.ldr", "materials") if kind == "material" else ("parts/prior.dat", "resources")
    )
    path = root / relative
    body = path.read_bytes() + b"0 modified carried-forward entry\n"
    path.write_bytes(body)
    doc = json.loads((root / "provenance.json").read_text())
    doc[section][relative].update(sha256=sha(body), bytes=len(body))
    (root / "provenance.json").write_bytes(canonical(doc))
    before = len(h.provider.calls)
    h.store.claim("runner-owner", job_id=h.job["id"])
    with pytest.raises(ValueError, match="Committed destination"):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == before
