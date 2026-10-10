"""Original synthetic assemblies verify correction mechanics, never target accuracy."""
import copy
import hashlib
import json
import math

import pytest

from guide2build.catalog import find_guide
from guide2build.core.models import SceneManifest
from guide2build.engine.corrections import fork_correction
from guide2build.engine.store import EngineStore
from guide2build.releases.models import SceneV2, adapt_v1, digest


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def seed_job(tmp_path, scene_data, *, config=None, transform=None):
    store = EngineStore(tmp_path)
    job = store.enqueue("30669", "alt-02", {"max_model_calls": 100} | (config or {"model": "test", "revision": "base"}))
    pdf = b"%PDF-1.4\nOriginal synthetic test source; not LEGO evidence.\n"
    source_hash = hashlib.sha256(pdf).hexdigest()
    guide = find_guide("30669", "alt-02")
    pdf_path = tmp_path / "sources/30669/alt-02/source.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(pdf)
    write_json(pdf_path.with_suffix(".receipt.json"), {"requested_url": guide["pdf_url"],
        "resolved_url": guide["pdf_url"], "sha256": source_hash, "size_bytes": len(pdf),
        "downloaded_at": "2026-10-04T12:00:00Z"})
    value = copy.deepcopy(scene_data)
    value.update(set_number="30669", guide_id="alt-02", revision="base", source_sha256=source_hash)
    for item in value["instances"] + value["steps"]:
        item["source"]["source_sha256"] = source_hash
    for part in value["instances"]:
        part["part_id"] = "synthetic"
        part["origin"] = "vision_proposal"
    scene = adapt_v1(SceneManifest.model_validate(value), guide["pdf_url"], guide["expected_page_count"])
    if transform:
        scene = SceneV2.model_validate(transform(scene.model_dump(mode="json")))
    directory = store.root / "jobs" / job["id"]
    write_json(directory / "scene.json", scene.model_dump(mode="json"))
    resources = {}
    for name in ("synthetic", "synthetic2"):
        data = f"0 Original synthetic test part {name}\n3 16 0 0 0 20 0 0 0 8 0\n".encode()
        path = directory / f"geometry/parts/{name}.dat"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        resources[f"parts/{name}.dat"] = {"classification": "Part", "sha256": hashlib.sha256(data).hexdigest(),
            "url": f"https://library.ldraw.org/library/official/parts/{name}.dat", "dependencies": []}
    material = b"0 !COLOUR White CODE 15 VALUE #FFFFFF EDGE #000000\n0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #000000\n"
    (directory / "geometry/LDConfig.ldr").write_bytes(material)
    write_json(directory / "geometry/provenance.json", {"resources": resources, "file_map": {},
        "materials": {"LDConfig.ldr": {"sha256": hashlib.sha256(material).hexdigest(),
            "url": "https://library.ldraw.org/library/official/LDConfig.ldr"}}})
    indexes = [{"panels": [{"section": scene.sections[0].section_id, "number": n, "label": str(n),
        "bbox": [0, 0, 1, 1], "kind": "main"} for n in sorted({step.main_step_number for step in scene.steps})],
        "uncertainty": []}] + [{"panels": [], "uncertainty": []} for _ in range(guide["expected_page_count"] - 1)]
    store.claim("seed", job_id=job["id"])
    store.checkpoint(job["id"], "seed", {"candidate": scene.model_dump(mode="json"), "page_indexes": indexes,
        "completed_panels": len(indexes[0]["panels"]), "source_sha256": source_hash, "model_calls_used": 5,
        "total_panels": len(indexes[0]["panels"]), "page_count": guide["expected_page_count"]}, "paused")
    return store, job["id"], scene, directory


def correction_request(tmp_path, scene, commands=None, **extra):
    evidence = scene.steps[0].source.model_dump(mode="json")
    commands = commands or [{"op": "mapping", "instance_id": "a", "part_id": "synthetic2", "color_code": "4",
                             "reason": "Synthetic mapping correction", "evidence": evidence}]
    data = {"schema_version": "1.0", "correction_id": "repair-1", "expected_scene_sha256": digest(scene),
            "actor": "agent", "reason": "Synthetic source-bound test correction", "evidence": [evidence],
            "commands": commands} | extra
    path = tmp_path / (data["correction_id"] + ".json")
    write_json(path, data)
    return path


def test_mapping_fork_is_immutable_assisted_and_has_frozen_budget(tmp_path, scene_data):
    store, identity, scene, directory = seed_job(tmp_path, scene_data)
    before_job, before_file = store.get(identity), (directory / "scene.json").read_bytes()
    request = correction_request(tmp_path, scene)
    child = fork_correction(store, identity, request, "repair-r1")
    assert store.get(identity) == before_job
    assert (directory / "scene.json").read_bytes() == before_file
    assert child["state"] == "paused"
    assert child["config"]["execution_policy"] == "explore"
    assert child["config"]["max_model_calls"] == 100
    assert child["checkpoint"]["model_calls_used"] == child["checkpoint"]["inherited_model_calls_used"] == 5
    revised = child["checkpoint"]["candidate"]
    assert revised["instances"][0]["part_id"] == "synthetic2"
    assert revised["instances"][0]["origin"] == "pdf_assisted_authoring"
    assert revised["status"] == "needs_review" and revised["connector_check"] == "not_run"
    assert child["checkpoint"]["correction_lineage"][0]["unassisted"] is False
    copied = store.root / "jobs" / child["id"]
    assert digest(SceneV2.model_validate_json((copied / "parent-scene.json").read_text())) == digest(scene)
    assert (copied / "geometry/parts/synthetic2.dat").is_file()
    assert "visual_review" in child["checkpoint"]["invalidated_checks"]


def test_stale_duplicate_active_and_invalid_source_rejected(tmp_path, scene_data):
    store, identity, scene, directory = seed_job(tmp_path, scene_data)
    wrong = correction_request(tmp_path, scene, expected_scene_sha256="0" * 64)
    with pytest.raises(ValueError, match="Stale"):
        fork_correction(store, identity, wrong, "wrong")
    request = correction_request(tmp_path, scene)
    store.claim("active", job_id=identity)
    with pytest.raises(ValueError, match="actively leased"):
        fork_correction(store, identity, request, "active")
    store.checkpoint(identity, "active", store.get(identity)["checkpoint"], "paused")
    child = fork_correction(store, identity, request, "good")
    with pytest.raises(ValueError, match="Duplicate"):
        fork_correction(store, identity, request, "duplicate")
    data = json.loads(request.read_text())
    data["correction_id"] = "invalid-source"
    data["commands"][0]["evidence"]["source_sha256"] = "b" * 64
    write_json(request, data)
    with pytest.raises(ValueError, match="verified source"):
        fork_correction(store, identity, request, "bad-source")
    assert len(store.list()) == 2 and store.get(child["id"])["owner"] is None


def test_pose_replay_preserves_rotation_and_translation_not_only_xyz_offsets(tmp_path, scene_data):
    z90 = [0, 0, math.sqrt(.5), math.sqrt(.5)]
    x90 = [math.sqrt(.5), 0, 0, math.sqrt(.5)]
    def transform(value):
        value["steps"][2]["poses"]["b"] = {"position_ldu": [100, 0, 0], "quaternion_xyzw": z90}
        return value
    store, identity, scene, _ = seed_job(tmp_path, scene_data, transform=transform)
    request = correction_request(tmp_path, scene, [{"op": "pose", "step_id": "s2", "instance_id": "b",
        "pose": {"position_ldu": [10, 8, 0], "quaternion_xyzw": x90},
        "evidence": scene.steps[1].source.model_dump(mode="json"), "reason": "Synthetic seating correction"}])
    child = fork_correction(store, identity, request, "pose-r1")
    result = child["checkpoint"]["candidate"]
    assert result["steps"][0] == scene.steps[0].model_dump(mode="json")
    assert result["steps"][2]["poses"]["b"]["position_ldu"] == pytest.approx([100, 10, 0])
    assert result["steps"][2]["poses"]["b"]["quaternion_xyzw"] == pytest.approx([.5, .5, .5, .5])


def test_group_replay_carries_future_members_through_six_dof_attachment(tmp_path, scene_data):
    z90 = [0, 0, math.sqrt(.5), math.sqrt(.5)]
    def transform(value):
        part = copy.deepcopy(value["instances"][1])
        part["instance_id"] = "c"
        value["instances"].append(part)
        extra = copy.deepcopy(value["steps"][1])
        extra.update(step_id="s2b", main_step_number=3, introduced_instance_ids=["c"], active_instance_ids=["c"])
        extra["visible_instance_ids"].append("c")
        extra["poses"]["c"] = {"position_ldu": [20, 8, 0], "quaternion_xyzw": [0, 0, 0, 1]}
        value["steps"].insert(2, extra)
        last = value["steps"][3]
        last.update(main_step_number=4, active_instance_ids=["b", "c"])
        last["visible_instance_ids"].append("c")
        last["poses"]["b"] = {"position_ldu": [100, 0, 0], "quaternion_xyzw": z90}
        last["poses"]["c"] = {"position_ldu": [100, 20, 0], "quaternion_xyzw": z90}
        return value
    store, identity, scene, _ = seed_job(tmp_path, scene_data, transform=transform)
    request = correction_request(tmp_path, scene, [{"op": "group", "group_id": "g1", "step_id": "s2",
        "anchor_instance_id": "b", "pose": {"position_ldu": [10, 8, 0],
        "quaternion_xyzw": [math.sqrt(.5), 0, 0, math.sqrt(.5)]},
        "evidence": scene.steps[1].source.model_dump(mode="json"), "reason": "Synthetic rigid correction"}])
    child = fork_correction(store, identity, request, "group-r1")
    poses = child["checkpoint"]["candidate"]["steps"]
    assert poses[2]["poses"]["c"]["position_ldu"] == pytest.approx([30, 8, 0])
    assert poses[3]["poses"]["c"]["position_ldu"] == pytest.approx([100, 30, 0])
    assert poses[3]["poses"]["b"]["quaternion_xyzw"] == pytest.approx([.5, .5, .5, .5])


def mislabelled_attachment(value):
    """Original synthetic reproduction of two callouts and a wrong attach group."""
    part = copy.deepcopy(value["instances"][1])
    part["instance_id"] = "c"
    value["instances"].append(part)
    first = value["steps"][1]
    first.update(step_id="model-1-step-3-callout-1", main_step_number=3,
        assembly_group_id="model-1-step-3-group", visible_instance_ids=["b"],
        poses={"b": copy.deepcopy(first["poses"]["b"])})
    second = copy.deepcopy(first)
    second.update(step_id="model-1-step-3-callout-2", introduced_instance_ids=["c"],
        active_instance_ids=["c"], visible_instance_ids=["b", "c"])
    second["poses"]["c"] = copy.deepcopy(second["poses"]["b"])
    second["poses"]["c"]["position_ldu"][0] += 20
    attach = value["steps"][2]
    attach.update(step_id="model-1-step-3", assembly_group_id="model-1-main",
        visible_instance_ids=["a", "b", "c"], active_instance_ids=["b", "c"])
    attach["poses"]["c"] = copy.deepcopy(attach["poses"]["b"])
    attach["poses"]["c"]["position_ldu"][0] += 20
    descendant = copy.deepcopy(attach)
    descendant.update(step_id="later-view", main_step_number=4, action="add_parts",
        assembly_group_id=None, active_instance_ids=[])
    value["steps"] = [value["steps"][0], first, second, attach, descendant]
    return value


@pytest.mark.parametrize("following_move", [False, True])
def test_grouping_metadata_repair_is_immutable_and_enables_following_group_move(tmp_path, scene_data, following_move):
    store, identity, scene, directory = seed_job(tmp_path, scene_data, transform=mislabelled_attachment)
    before_job, before_bytes = store.get(identity), (directory / "scene.json").read_bytes()
    selected = scene.steps[3]
    commands = [{"op": "grouping", "step_id": selected.step_id, "group_id": "model-1-step-3-group",
        "reason": "Synthetic source callouts identify the existing detached group", "evidence": selected.source.model_dump(mode="json")}]
    if following_move:
        target = selected.poses["b"].model_dump(mode="json")
        target["position_ldu"][0] += 10
        commands.append({"op": "group", "step_id": selected.step_id, "group_id": "model-1-step-3-group",
            "anchor_instance_id": "b", "pose": target, "reason": "Synthetic rigid seating correction",
            "evidence": selected.source.model_dump(mode="json")})
    request = correction_request(tmp_path, scene, commands)
    child = fork_correction(store, identity, request, "grouping-repair")
    revised = SceneV2.model_validate(child["checkpoint"]["candidate"])
    assert store.get(identity) == before_job and (directory / "scene.json").read_bytes() == before_bytes
    assert revised.steps[3].assembly_group_id == "model-1-step-3-group"
    assert revised.steps[:3] == scene.steps[:3]
    for old, new in zip(scene.steps, revised.steps, strict=True):
        for instance_id, pose in old.poses.items():
            expected = list(pose.position_ldu)
            if following_move and old.step_id in {selected.step_id, "later-view"} and instance_id in {"b", "c"}:
                expected[0] += 10
            assert new.poses[instance_id].position_ldu == pytest.approx(expected)
            assert new.poses[instance_id].quaternion_xyzw == pose.quaternion_xyzw
    lineage = child["checkpoint"]["correction_lineage"][-1]
    assert lineage["first_affected_step_index"] == 3
    change = lineage["changes"][0]
    assert change["before"] == {"assembly_group_id": "model-1-main"}
    assert change["after"] == {"assembly_group_id": "model-1-step-3-group"}
    assert change["member_instance_ids"] == ["b", "c"] and change["assembly_poses_changed"] is False
    assert change["dependent_steps_invalidated"] == 1
    assert "source_camera" in child["checkpoint"]["invalidated_checks"]
    assert "visual_review" in child["checkpoint"]["invalidated_checks"]


def test_grouping_corrections_ignore_future_bad_labels_until_their_command(tmp_path, scene_data):
    def two_bad_labels(value):
        value = mislabelled_attachment(value)
        part = copy.deepcopy(value["instances"][-1])
        part["instance_id"] = "d"
        value["instances"].append(part)
        build = copy.deepcopy(value["steps"][1])
        build.update(step_id="model-1-step-4-callout", main_step_number=4,
            introduced_instance_ids=["d"], active_instance_ids=["d"], visible_instance_ids=["d"],
            assembly_group_id="model-1-step-4-group", poses={"d": copy.deepcopy(build["poses"]["b"])})
        attach = copy.deepcopy(value["steps"][3])
        attach.update(step_id="model-1-step-4", main_step_number=4, active_instance_ids=["d"],
            visible_instance_ids=["a", "b", "c", "d"])
        attach["poses"]["d"] = copy.deepcopy(build["poses"]["d"])
        attach["poses"]["d"]["position_ldu"][2] = 20
        value["steps"] = value["steps"][:4] + [build, attach]
        return value
    store, identity, scene, _ = seed_job(tmp_path, scene_data, transform=two_bad_labels)
    commands = [{"op": "grouping", "step_id": f"model-1-step-{number}", "group_id": f"model-1-step-{number}-group",
        "reason": "Synthetic callout-to-attachment source correction", "evidence": scene.steps[3].source.model_dump(mode="json")}
        for number in (3, 4)]
    target = scene.steps[3].poses["b"].model_dump(mode="json")
    target["position_ldu"][0] += 10
    commands.append({"op": "group", "step_id": "model-1-step-3", "group_id": "model-1-step-3-group",
        "anchor_instance_id": "b", "pose": target, "reason": "Synthetic pose correction after both metadata fixes",
        "evidence": scene.steps[3].source.model_dump(mode="json")})
    child = fork_correction(store, identity, correction_request(tmp_path, scene, commands), "two-grouping-fixes")
    revised = SceneV2.model_validate(child["checkpoint"]["candidate"])
    assert revised.steps[3].assembly_group_id == "model-1-step-3-group"
    assert revised.steps[-1].assembly_group_id == "model-1-step-4-group"
    assert revised.steps[-1].poses["b"].position_ldu[0] == scene.steps[-1].poses["b"].position_ldu[0] + 10
    assert revised.steps[-1].poses["c"].position_ldu[0] == scene.steps[-1].poses["c"].position_ldu[0] + 10
    assert revised.steps[-1].poses["d"] == scene.steps[-1].poses["d"]


@pytest.mark.parametrize("problem", ["unknown", "incomplete", "ambiguous", "attached", "not_attachment", "foreign_page"])
def test_grouping_rejects_unknown_incomplete_ambiguous_or_unbound_groups(tmp_path, scene_data, problem):
    def malformed(value):
        value = mislabelled_attachment(value)
        attach = value["steps"][3]
        if problem == "incomplete":
            attach["visible_instance_ids"].remove("c")
            attach["active_instance_ids"].remove("c")
            del attach["poses"]["c"]
        elif problem == "ambiguous":
            # A second detached receiver and the main workspace are both visible.
            part = copy.deepcopy(value["instances"][-1])
            part["instance_id"] = "d"
            value["instances"].append(part)
            build = copy.deepcopy(value["steps"][1])
            build.update(step_id="other-detached-group", assembly_group_id="other-group",
                introduced_instance_ids=["d"], active_instance_ids=["d"], visible_instance_ids=["d"],
                poses={"d": copy.deepcopy(build["poses"]["b"])})
            value["steps"].insert(3, build)
            attach["visible_instance_ids"].append("d")
            attach["poses"]["d"] = copy.deepcopy(build["poses"]["d"])
        elif problem == "attached":
            prior_attach = copy.deepcopy(attach)
            prior_attach.update(step_id="already-attached", assembly_group_id="model-1-step-3-group")
            value["steps"].insert(3, prior_attach)
        return value
    store, identity, scene, directory = seed_job(tmp_path, scene_data, transform=malformed)
    selected = next(step for step in scene.steps if step.step_id == "model-1-step-3")
    evidence = selected.source.model_dump(mode="json")
    if problem == "foreign_page":
        evidence["page_index"] += 1
    command = {"op": "grouping", "step_id": "model-1-step-3-callout-1" if problem == "not_attachment" else selected.step_id,
        "group_id": "unknown-group" if problem == "unknown" else "model-1-step-3-group",
        "reason": "Synthetic negative grouping correction", "evidence": evidence}
    before_job, before_bytes = store.get(identity), (directory / "scene.json").read_bytes()
    with pytest.raises(ValueError, match="Grouping correction"):
        fork_correction(store, identity, correction_request(tmp_path, scene, [command]), "invalid-grouping")
    assert store.get(identity) == before_job and (directory / "scene.json").read_bytes() == before_bytes
    assert len(store.list()) == 1


def test_restart_prefix_never_leaks_future_poses_and_limits_two_passes(tmp_path, scene_data):
    store, identity, scene, _ = seed_job(tmp_path, scene_data)
    request = correction_request(tmp_path, scene, commands=[], restart_main_step=2,
                                 guidance=["Compare the later official view to resolve this attachment."])
    # Explicit commands=[] overrides helper default through the serialized request.
    value = json.loads(request.read_text())
    value["commands"] = []
    write_json(request, value)
    child = fork_correction(store, identity, request, "restart-r1")
    checkpoint = child["checkpoint"]
    assert checkpoint["processed_panels"] == 1
    assert len(checkpoint["candidate"]["steps"]) == len(checkpoint["candidate"]["instances"]) == 1
    assert "poses" not in json.dumps(checkpoint["correction_guidance"])
    assert checkpoint["exploration_seed"]["candidate_sha256"] == digest(checkpoint["candidate"])
    next_scene = SceneV2.model_validate(checkpoint["candidate"])
    next_request = correction_request(tmp_path, next_scene, commands=[{"op": "mapping", "instance_id": "a",
        "part_id": "synthetic", "color_code": "4", "reason": "Synthetic colour edit",
        "evidence": next_scene.steps[0].source.model_dump(mode="json")}], correction_id="repair-2")
    second = fork_correction(store, child["id"], next_request, "second-r2")
    third_request = correction_request(tmp_path, SceneV2.model_validate(second["checkpoint"]["candidate"]),
                                      correction_id="repair-3")
    with pytest.raises(ValueError, match="two correction"):
        fork_correction(store, second["id"], third_request, "third-r3")


def test_asset_tampering_and_nonfinite_budgets_rejected(tmp_path, scene_data):
    store, identity, scene, directory = seed_job(tmp_path, scene_data)
    (directory / "geometry/parts/synthetic.dat").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        fork_correction(store, identity, correction_request(tmp_path, scene), "tampered")
    for value in (float("inf"), float("nan"), 0, -1, True, 1.5):
        with pytest.raises(ValueError, match="finite integer"):
            store.enqueue("30669", "alt-02", {"execution_policy": "explore", "max_model_calls": value})
    with pytest.raises(ValueError, match="policy"):
        store.enqueue("30669", "alt-02", {"execution_policy": "skip-everything"})


def test_restart_at_main_one_has_no_candidate_or_future_poses(tmp_path, scene_data):
    store, identity, scene, _ = seed_job(tmp_path, scene_data)
    path = correction_request(tmp_path, scene, restart_main_step=1, guidance=["Revisit the official first panel."])
    value = json.loads(path.read_text())
    value["commands"] = []
    write_json(path, value)
    child = fork_correction(store, identity, path, "restart-first")
    checkpoint = child["checkpoint"]
    assert "candidate" not in checkpoint
    assert checkpoint["exploration_seed"]["candidate_sha256"] is None
    assert checkpoint["processed_panels"] == 0 and checkpoint["instruction_results"] == []
    assert not (store.root / "jobs" / child["id"] / "scene.json").exists()
    assert "poses" not in json.dumps(checkpoint)


def test_full_corrected_seed_resumes_without_regeneration_or_budget_reset(tmp_path, scene_data):
    from types import SimpleNamespace
    from PIL import Image
    from guide2build.engine.exploration import run_exploration
    store, identity, scene, directory = seed_job(tmp_path, scene_data)
    parent_bytes = (directory / "scene.json").read_bytes()
    child = fork_correction(store, identity, correction_request(tmp_path, scene), "complete-seed")
    pages = tmp_path / "public/pages" / scene.source_sha256
    pages.mkdir(parents=True)
    for page in range(8):
        Image.new("RGB", (64, 64), "white").save(pages / f"page-{page:03d}.png")
    claimed = store.claim("resume-test", job_id=child["id"])
    checkpoint = claimed["checkpoint"]
    initial_candidate = copy.deepcopy(checkpoint["candidate"])
    def forbidden(*args, **kwargs):
        pytest.fail("A complete corrected seed must not regenerate or issue model calls")
    def save(stage, state="constructing", error=None):
        checkpoint["stage"] = stage
        store.checkpoint(child["id"], "resume-test", checkpoint, state, error)
    run_exploration(job=claimed, checkpoint=checkpoint, directory=store.root / "jobs" / child["id"],
        source_hash=scene.source_sha256, pages_dir=pages, page_count=8,
        runtime=SimpleNamespace(call=forbidden), save=save, heartbeat=SimpleNamespace(check=lambda: None), store=store)
    assert checkpoint["candidate"] == initial_candidate
    assert checkpoint["model_calls_used"] == 5 and checkpoint["local_model_calls_used"] == 0
    assert checkpoint["processed_panels"] == 3
    assert (directory / "scene.json").read_bytes() == parent_bytes


def test_lineage_budget_counts_sibling_local_calls_once(tmp_path, scene_data):
    store, identity, scene, _ = seed_job(tmp_path, scene_data)
    first = fork_correction(store, identity, correction_request(tmp_path, scene), "sibling-1")
    store.claim("first", job_id=first["id"])
    cp = first["checkpoint"]
    cp.update(model_calls_used=8, local_model_calls_used=3,
              exploration_calls={"one": {}, "two": {}, "three": {}})
    store.checkpoint(first["id"], "first", cp, "paused")
    second_request = correction_request(tmp_path, scene, correction_id="sibling-two")
    second = fork_correction(store, identity, second_request, "sibling-2")
    assert second["checkpoint"]["inherited_model_calls_used"] == 8
    assert store.lineage_model_calls_used(identity) == 8
    store.claim("second", job_id=second["id"])
    cp2 = second["checkpoint"]
    cp2.update(model_calls_used=10, local_model_calls_used=2, exploration_calls={"four": {}, "five": {}})
    store.checkpoint(second["id"], "second", cp2, "paused")
    assert store.lineage_model_calls_used(identity) == 10


def test_restart_retains_prior_unresolved_instruction_results(tmp_path, scene_data):
    store, identity, scene, _ = seed_job(tmp_path, scene_data)
    store.claim("missing", job_id=identity)
    cp = store.get(identity)["checkpoint"]
    panels = cp["page_indexes"][0]["panels"]
    cp["instruction_results"] = [{"ordinal": n, "panel": panels[n], "page_index": 0,
        "step_ids": [scene.steps[n].step_id] if n != 1 else [], "reconstructed": n != 1,
        "findings": [{"code": "wrong_part", "message": f"Source uncertainty {n}"}]} for n in range(3)]
    cp["page_indexes"][0]["uncertainty"] = ["Uncertain callout boundary"]
    cp["provisional_findings"] = [{"code": "stale_suffix", "message": "Discarded future pose evidence"}]
    cp["processed_panels"] = 3
    store.checkpoint(identity, "missing", cp, "paused")
    request = correction_request(tmp_path, scene, restart_main_step=3, guidance=["Use later official evidence."])
    data = json.loads(request.read_text())
    data["commands"] = []
    write_json(request, data)
    child = fork_correction(store, identity, request, "restart-third")
    rows = child["checkpoint"]["instruction_results"]
    assert len(rows) == child["checkpoint"]["processed_panels"] == 2
    assert rows[1]["reconstructed"] is False and rows[1]["step_ids"] == []
    assert rows[1]["inherited_from_job"] == identity
    assert child["checkpoint"]["reconstructed_panels"] == 1
    warnings = child["checkpoint"]["provisional_findings"]
    assert [item["message"] for item in warnings] == ["Source uncertainty 0", "Source uncertainty 1"]
    assert [item["ordinal"] for item in warnings] == [0, 1]
    assert all(item["inherited_from_job"] == identity and item["source_sha256"] == scene.source_sha256 for item in warnings)
    assert child["checkpoint"]["source_index_findings"][0]["message"] == "Uncertain callout boundary"
    assert "Discarded future pose evidence" not in json.dumps(child["checkpoint"])


def test_nested_group_edit_moves_attached_child_and_its_descendants(tmp_path):
    from guide2build.engine.corrections import GroupCorrection, _apply_commands
    from test_engine_spatial import scene as synthetic_scene, pose, step, SOURCE
    assembly = synthetic_scene({"main": "3022", "inner": "3022", "strip": "3710", "outer": "3020"}, [
        step("one", {"main": pose()}, ["main"]),
        step("inner-build", {"inner": pose(), "strip": pose(0, 8, 10)}, ["inner", "strip"],
             action="build_subassembly", group="inner-group"),
        step("outer-build", {"outer": pose(200)}, ["outer"], action="build_subassembly", group="outer-group"),
        step("inner-attach", {"outer": pose(200), "inner": pose(180, 8), "strip": pose(180, 16, 10)}, [],
             action="attach_subassembly", group="inner-group"),
        step("outer-attach", {"main": pose(), "outer": pose(20, 8), "inner": pose(0, 16), "strip": pose(0, 24, 10)}, [],
             action="attach_subassembly", group="outer-group")])
    command = GroupCorrection(op="group", reason="Original synthetic nested group adjustment", evidence=SOURCE,
        step_id="inner-attach", group_id="outer-group", anchor_instance_id="outer", pose=pose(210))
    updated, _, _, _ = _apply_commands(assembly, [command], {SOURCE["source_sha256"]: 1}, tmp_path)
    assert updated.steps[3].poses["inner"].position_ldu == (190, 8, 0)
    assert updated.steps[3].poses["strip"].position_ldu == (190, 16, 10)
    assert updated.steps[4].poses["inner"].position_ldu == (10, 16, 0)
    assert updated.steps[4].poses["strip"].position_ldu == (10, 24, 10)
    # A move made before the child attaches is inherited by that later attachment too.
    earlier = command.model_copy(update={"step_id": "outer-build"})
    updated, _, _, _ = _apply_commands(assembly, [earlier], {SOURCE["source_sha256"]: 1}, tmp_path)
    assert updated.steps[3].poses["inner"].position_ldu == (190, 8, 0)


def test_unresolved_nested_target_rejects_edit_without_splitting_group(tmp_path):
    from guide2build.engine.corrections import GroupCorrection, _apply_commands
    from test_engine_spatial import scene as synthetic_scene, pose, step, SOURCE
    assembly = synthetic_scene({"main": "3022", "inner": "3022", "outer": "3020"}, [
        step("one", {"main": pose()}, ["main"]),
        step("inner-build", {"inner": pose()}, ["inner"], action="build_subassembly", group="inner-group"),
        step("outer-build", {"outer": pose(200)}, ["outer"], action="build_subassembly", group="outer-group"),
        step("inner-attach", {"main": pose(), "outer": pose(200), "inner": pose(180, 8)}, [],
             action="attach_subassembly", group="inner-group")])
    before = digest(assembly)
    command = GroupCorrection(op="group", reason="Synthetic ambiguous target", evidence=SOURCE,
        step_id="inner-attach", group_id="outer-group", anchor_instance_id="outer", pose=pose(210))
    with pytest.raises(ValueError, match="Nested group attachment target is unsupported"):
        _apply_commands(assembly, [command], {SOURCE["source_sha256"]: 1}, tmp_path)
    assert digest(assembly) == before


def test_legacy_alpha_correction_initializes_compatible_source_policy(tmp_path, scene_data):
    from guide2build.engine.quality import bind_source_view_policy
    store, identity, scene, _ = seed_job(tmp_path, scene_data, config={"revision": "base", "model": "test",
        "generation_mode": "alpha_fast", "quality_profile": "alpha", "max_panel_attempts": 3})
    child = fork_correction(store, identity, correction_request(tmp_path, scene), "legacy-alpha-repair")
    assert child["config"]["max_panel_attempts"] == 2
    assert bind_source_view_policy(child["config"], child["checkpoint"])["profile"] == "alpha"


def test_new_adk_defaults_do_not_relabel_or_reuse_historical_provider_job(tmp_path):
    from guide2build.engine.store import PIPELINE
    store = EngineStore(tmp_path)
    configuration = {"model": "test", "revision": "legacy"}
    job = store.enqueue("30669", "alt-02", configuration)
    old_identity = {"set": "30669", "guide": "alt-02", "url": find_guide("30669", "alt-02")["pdf_url"],
                    "pipeline": PIPELINE, "config": configuration}
    old_hash = hashlib.sha256(json.dumps(old_identity, sort_keys=True).encode()).hexdigest()
    with store.connect() as con:
        con.execute("UPDATE engine_jobs SET config=?,fingerprint=? WHERE id=?",
                    (json.dumps(configuration), old_hash, job["id"]))
    historical = store.get(job["id"])
    new = store.enqueue("30669", "alt-02", configuration)
    assert new["id"] != job["id"] and new["config"]["provider"] == "google_adk"
    assert store.get(job["id"]) == historical
    assert store.enqueue("30669", "alt-02", configuration | {"execution_policy": "strict"})["id"] == new["id"]


def test_new_correction_initializes_current_policy_without_upgrading_parent_receipts(tmp_path, scene_data):
    from guide2build.engine.delta import SceneDelta
    from guide2build.engine.exploration import EXPLORATION_VERSION, _policy
    store, identity, scene, directory = seed_job(tmp_path, scene_data,
        config={"model": "test", "revision": "base", "execution_policy": "explore", "max_model_calls": 100})
    store.claim("old-policy", job_id=identity)
    checkpoint = store.get(identity)["checkpoint"]
    legacy = {"version": "source-exploration-v2", "source_sha256": scene.source_sha256,
        "page_count": scene.sources[0].page_count, "max_model_calls": 100, "proposal_attempts": 2,
        "max_candidates": 64, "beam_width": 8, "render_candidates": 3,
        "scene_delta_schema_sha256": digest(SceneDelta.model_json_schema()), "landmark_overrides_sha256": digest({})}
    checkpoint["exploration_policy"] = legacy
    checkpoint["exploration_calls"] = {"original-call": {"status": "completed", "marker": "original provider receipt"}}
    receipt_path = directory / "exploration/calls/original-call/receipt.json"
    write_json(receipt_path, {"immutable_original_receipt": True, "policy_sha256": digest(legacy)})
    store.checkpoint(identity, "old-policy", checkpoint, "paused")
    original_job, original_receipt = store.get(identity), receipt_path.read_bytes()
    child = fork_correction(store, identity, correction_request(tmp_path, scene), "policy-corrected")
    assert store.get(identity) == original_job and receipt_path.read_bytes() == original_receipt
    current = child["checkpoint"]["exploration_policy"]
    assert current["version"] == EXPLORATION_VERSION and current["version"] != legacy["version"]
    assert current["candidate_selection_version"] == "source-quality-selection-v1"
    assert len(current["candidate_review_schema_sha256"]) == 64
    assert len(current["snapshot_visibility_contract_sha256"]) == 64
    lineage = child["checkpoint"]["correction_lineage"][-1]
    assert lineage["parent_exploration_policy_sha256"] == digest(legacy)
    assert lineage["derived_exploration_policy_sha256"] == digest(current)
    assert lineage["exploration_policy_transition"]["scope"] == "new_correction_revision_only"
    assert {"version", "candidate_selection_version", "candidate_review_schema_sha256", "snapshot_visibility_contract_sha256"} <= set(
        lineage["exploration_policy_transition"]["changed_fields"])
    assert child["checkpoint"]["exploration_calls"] == {}
    assert child["checkpoint"]["model_calls_used"] == original_job["checkpoint"]["model_calls_used"]
    assert child["checkpoint"]["local_model_calls_used"] == 0 and child["config"]["max_model_calls"] == 100
    rebound = copy.deepcopy(child["checkpoint"])
    assert _policy(child["config"], rebound, scene.source_sha256, scene.sources[0].page_count) == current
    with pytest.raises(ValueError, match="policy or model-call budget changed"):
        _policy(original_job["config"], copy.deepcopy(original_job["checkpoint"]), scene.source_sha256, scene.sources[0].page_count)
