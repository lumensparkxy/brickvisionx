"""Original synthetic receipts and individual geometry, never target-set evidence."""
from copy import deepcopy
import hashlib
import json
from math import sqrt
from types import SimpleNamespace

import pytest
from PIL import Image

from guide2build.core.models import SceneManifest
from guide2build.engine import connectors
from guide2build.engine.alignment_context import accepted_alignment_context
from guide2build.releases.models import adapt_v1, digest


@pytest.fixture
def accepted_context(tmp_path, monkeypatch, scene_data):
    directory = tmp_path / "var" / "engine" / "jobs" / "job"
    trial = directory / "proposals" / "synthetic-accepted-trial"
    trial.mkdir(parents=True)
    geometry = directory / "geometry"
    part_file = geometry / "parts/synthetic.dat"
    part_file.parent.mkdir(parents=True)
    part_file.write_bytes(b"0 Original synthetic individual part\n3 16 0 0 0 20 0 0 0 0 20\n")
    geometry_hash = hashlib.sha256(part_file.read_bytes()).hexdigest()
    pins = [["parts/synthetic.dat", geometry_hash]]
    (geometry / "provenance.json").write_text(json.dumps({"resources": {
        "parts/synthetic.dat": {"sha256": geometry_hash, "classification": "Part",
                                "url": "https://library.ldraw.org/library/official/parts/synthetic.dat",
                                "dependencies": []}}, "file_map": {}}))
    local_points = [[0, 4, 0], [20, 4, 0], [0, 4, 20], [20, 4, 20]]
    metadata = {"schema_version": "1.0", "parts": [{
        "part_id": "synthetic-part", "geometry_ref": "parts/synthetic.dat", "geometry_sha256": geometry_hash,
        "closure_sha256": hashlib.sha256(json.dumps(pins, separators=(",", ":")).encode()).hexdigest(),
        "closure_file_count": 1, "evidence_resources": pins,
        "connectors": [{"connector_id": f"synthetic-stud-{i}", "kind": "stud",
                        "position_ldu": [point[0], 0, point[2]],
                        "landmark": {"landmark_id": f"synthetic-cap-{i}", "position_ldu": point}}
                       for i, point in enumerate(local_points)]}]}
    metadata_file = tmp_path / "synthetic-metadata.json"
    metadata_file.write_text(json.dumps(metadata))
    monkeypatch.setattr(connectors, "METADATA", metadata_file)
    candidate = adapt_v1(SceneManifest.model_validate(scene_data),
        "https://www.lego.com/en-us/service/building-instructions/99999", 1).model_dump(mode="json")
    candidate["steps"][-1]["poses"]["b"] = {
        "position_ldu": [10, 30, 50], "quaternion_xyzw": [0, sqrt(.5), 0, sqrt(.5)]}
    source_hash = candidate["source_sha256"]
    page_file = directory.parents[2] / "public" / "pages" / source_hash / "page-000.png"
    page_file.parent.mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(page_file)
    image_hash = hashlib.sha256(page_file.read_bytes()).hexdigest()
    record = {"scene_sha256": digest(candidate), "source_sha256": source_hash, "source_page": 0,
              "source_image_sha256": image_hash, "observations": [{"step_id": "s3", "view_family": "unconstrained",
                "landmarks": [{"instance_id": "b", "landmark_id": f"synthetic-cap-{i}",
                               "image_uv": [.2+(i % 2)*.1, .3+(i // 2)*.1]} for i in range(4)]}],
              "fits": {"s3": {"status": "fitted", "camera": {"projection": "orthographic",
                "right": [1, 0, 0], "up": [0, 1, 0], "target_ldu": [0, 0, 0],
                "vertical_span_ldu": 200, "image_size": [800, 600]}}}}
    accepted = {"directory": str(trial), "scene_sha256": digest(candidate), "source_sha256": source_hash,
                "source_image_sha256": image_hash, "page_index": 0, "files": {}}
    checkpoint = {"source_sha256": source_hash, "panel_attempts": {
        "1": {"accepted": {"scene_sha256": digest({"earlier_synthetic_revision": True}),
                           "directory": "/must-not-read-another-job"}},
        "2": {"trials": [str(trial)], "accepted": accepted}}}
    def write_record():
        path = trial / "source-views.json"
        path.write_text(json.dumps(record))
        accepted["files"]["source-views.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_record()
    return SimpleNamespace(directory=directory, trial=trial, geometry=geometry, page_file=page_file, candidate=candidate,
                           checkpoint=checkpoint, accepted=accepted, record=record, write_record=write_record)


def read(h):
    return accepted_alignment_context(h.directory, h.checkpoint, h.candidate)


def test_uses_named_geometry_and_last_snapshot_pose_without_mutating_history(accepted_context):
    h = accepted_context
    before = deepcopy((h.candidate, h.checkpoint))
    context = read(h)
    assert context["step_id"] == "s3"
    assert context["source_page"] == 0
    assert context["scene_sha256"] == digest(h.candidate)
    assert context["source_sha256"] == h.candidate["source_sha256"]
    assert context["source_image_sha256"] == h.accepted["source_image_sha256"]
    assert context["image_size"] == [800, 600]
    assert context["image_coordinates"] == "full_page_top_left_normalized"
    assert context["camera"] == {"right": [1, 0, 0], "up": [0, 1, 0]}
    assert context["view_family"] == "unconstrained"
    # Actual world_landmark applies the accepted +90-degree Y rotation and offset.
    for item, expected in zip(context["landmarks"], [[10, 34, 50], [10, 34, 30], [30, 34, 50], [30, 34, 30]], strict=True):
        assert item["instance_id"] == "b"
        assert item["world_ldu"] == pytest.approx(expected)
    assert context["landmarks"][0]["image_uv"] == [.2, .3]
    assert (h.candidate, h.checkpoint) == before


def test_no_candidate_or_no_matching_legacy_receipt_skips_without_reading_files(accepted_context):
    h = accepted_context
    assert accepted_alignment_context(h.directory / "absent", {}, None) is None
    assert accepted_alignment_context(h.directory / "absent", {}, h.candidate) is None
    assert accepted_alignment_context(h.directory / "absent", {"panel_attempts": {}}, h.candidate) is None
    # Inherited/rebased scenes deliberately do not reuse another revision's receipt.
    rebased = deepcopy(h.candidate)
    rebased["revision"] = "rebased-own-scene-without-receipt"
    assert accepted_alignment_context(h.directory, h.checkpoint, rebased) is None


@pytest.mark.parametrize("target,key,value", [
    ("accepted", "source_sha256", "a"*64),
    ("accepted", "page_index", 1),
    ("accepted", "page_index", False),
    ("checkpoint", "source_sha256", "a"*64),
    ("record", "scene_sha256", "a"*64),
    ("record", "source_sha256", "a"*64),
    ("record", "source_page", 1),
    ("record", "source_image_sha256", "a"*64),
])
def test_matching_receipt_rejects_scene_source_and_page_mismatch(accepted_context, target, key, value):
    h = accepted_context
    getattr(h, target)[key] = value
    h.write_record()
    with pytest.raises(ValueError, match="differs"):
        read(h)


@pytest.mark.parametrize("path", ["relative/proposals/trial", "/another-job/proposals/trial"])
def test_receipt_cannot_import_another_job_or_relative_path(accepted_context, path):
    h = accepted_context
    h.accepted["directory"] = path
    h.checkpoint["panel_attempts"]["2"]["trials"] = [path]
    with pytest.raises(ValueError, match="escapes"):
        read(h)


def test_trial_must_be_registered_and_rejects_symlink_components(accepted_context):
    h = accepted_context
    h.checkpoint["panel_attempts"]["2"]["trials"] = []
    with pytest.raises(ValueError, match="not registered"):
        read(h)
    linked = h.directory / "proposals" / "linked"
    linked.symlink_to(h.trial, target_is_directory=True)
    h.accepted["directory"] = str(linked)
    h.checkpoint["panel_attempts"]["2"]["trials"] = [str(linked)]
    with pytest.raises(ValueError, match="escapes"):
        read(h)


def test_changed_hash_missing_evidence_and_oversize_file_fail_closed(accepted_context):
    h = accepted_context
    path = h.trial / "source-views.json"
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError, match="hash changed"):
        read(h)
    path.unlink()
    with pytest.raises(ValueError, match="asset"):
        read(h)
    path.write_bytes(b" "*1_000_001)
    h.accepted["files"]["source-views.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="asset"):
        read(h)


def test_unknown_instance_or_nonexistent_landmark_fails_closed(accepted_context):
    h = accepted_context
    landmark = h.record["observations"][0]["landmarks"][0]
    landmark["instance_id"] = "not-in-this-scene"
    h.write_record()
    with pytest.raises(ValueError, match="visible snapshot"):
        read(h)
    landmark["instance_id"] = "b"
    landmark["landmark_id"] = "not-in-individual-metadata"
    h.write_record()
    with pytest.raises(ValueError, match="Unknown visible landmark"):
        read(h)


def test_hidden_landmark_is_not_recovered_from_an_older_visible_pose(accepted_context):
    h = accepted_context
    last = h.candidate["steps"][-1]
    last.update(visible_instance_ids=["b"], active_instance_ids=["b"])
    del last["poses"]["a"]
    h.accepted["scene_sha256"] = h.record["scene_sha256"] = digest(h.candidate)
    h.record["observations"][0]["landmarks"][0]["instance_id"] = "a"
    h.write_record()
    with pytest.raises(ValueError, match="visible snapshot"):
        read(h)


@pytest.mark.parametrize("change", ["missing_observation", "duplicate_observation", "many_landmarks", "duplicate_landmark", "poor_fit", "invalid_camera", "missing_file_hash"])
def test_incomplete_or_unbounded_matching_view_is_not_silently_skipped(accepted_context, change):
    h = accepted_context
    observations = h.record["observations"]
    if change == "missing_observation":
        observations[0]["step_id"] = "older-step"
    elif change == "duplicate_observation":
        observations.append(deepcopy(observations[0]))
    elif change == "many_landmarks":
        observations[0]["landmarks"] *= 17
    elif change == "duplicate_landmark":
        observations[0]["landmarks"][1] = deepcopy(observations[0]["landmarks"][0])
    elif change == "poor_fit":
        h.record["fits"]["s3"]["status"] = "poor_fit"
    elif change == "invalid_camera":
        h.record["fits"]["s3"]["camera"]["right"] = [2, 0, 0]
    h.write_record()
    if change == "missing_file_hash":
        h.accepted["files"].clear()
    with pytest.raises(ValueError):
        read(h)


def test_changed_individual_geometry_is_not_used_as_accepted_landmark_context(accepted_context):
    h = accepted_context
    (h.geometry / "parts/synthetic.dat").write_bytes(b"changed geometry")
    with pytest.raises(ValueError, match="geometry hash mismatch"):
        read(h)


def test_duplicate_matching_receipts_fail_closed(accepted_context):
    h = accepted_context
    h.checkpoint["panel_attempts"]["3"] = deepcopy(h.checkpoint["panel_attempts"]["2"])
    with pytest.raises(ValueError, match="Multiple accepted"):
        read(h)


def test_last_snapshot_active_booklet_can_differ_from_original_primary_source(accepted_context):
    h = accepted_context
    primary = h.candidate["source_sha256"]
    continuation = hashlib.sha256(b"second original synthetic booklet").hexdigest()
    h.candidate["sources"].append({"guide_id": "second-synthetic", "source_sha256": continuation,
        "official_url": "https://www.lego.com/en-us/service/building-instructions/99999", "page_count": 2})
    h.candidate["sections"].append({"section_id": "second-synthetic", "source_sha256": continuation,
                                      "label": "Original synthetic continuation"})
    h.candidate["steps"][-1]["section_id"] = "second-synthetic"
    h.candidate["steps"][-1]["source"].update(source_sha256=continuation, page_index=1)
    h.accepted.update(source_sha256=continuation, page_index=1, scene_sha256=digest(h.candidate))
    h.checkpoint["source_sha256"] = continuation
    h.record.update(source_sha256=continuation, source_page=1, scene_sha256=digest(h.candidate))
    page_file = h.directory.parents[2] / "public" / "pages" / continuation / "page-001.png"
    page_file.parent.mkdir(parents=True)
    Image.new("RGB", (800, 600), "blue").save(page_file)
    image_hash = hashlib.sha256(page_file.read_bytes()).hexdigest()
    h.accepted["source_image_sha256"] = h.record["source_image_sha256"] = image_hash
    h.write_record()
    context = read(h)
    assert context["source_sha256"] == continuation
    assert context["source_image_sha256"] == image_hash
    assert context["source_page"] == 1
    assert h.candidate["source_sha256"] == primary  # Primary registry identity remains unchanged.


def test_changed_actual_source_page_is_not_hidden_by_matching_receipt_fields(accepted_context):
    h = accepted_context
    Image.new("RGB", (800, 600), "red").save(h.page_file)
    with pytest.raises(ValueError, match="source page image hash changed"):
        read(h)


@pytest.mark.parametrize("change", ["dimensions", "invalid_png", "missing", "symlink"])
def test_actual_source_page_must_be_safe_valid_png_with_camera_dimensions(accepted_context, change):
    h = accepted_context
    if change == "dimensions":
        Image.new("RGB", (640, 480), "white").save(h.page_file)
    elif change == "invalid_png":
        h.page_file.write_bytes(b"not a source PNG")
    elif change == "symlink":
        copy = h.page_file.with_name("original-page-copy.png")
        copy.write_bytes(h.page_file.read_bytes())
        h.page_file.unlink()
        h.page_file.symlink_to(copy)
    else:
        h.page_file.unlink()
    if change in ("dimensions", "invalid_png"):
        image_hash = hashlib.sha256(h.page_file.read_bytes()).hexdigest()
        h.accepted["source_image_sha256"] = h.record["source_image_sha256"] = image_hash
        h.write_record()
    with pytest.raises(ValueError):
        read(h)
