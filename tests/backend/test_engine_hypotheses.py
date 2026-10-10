"""Original arrangements exercise bounded search, not target-booklet accuracy."""
from copy import deepcopy
import json
from math import sqrt
from pathlib import Path

from PIL import Image
import pytest

from guide2build.engine import hypotheses, spatial
from guide2build.engine.connectors import METADATA, transform_point
from guide2build.engine.hypotheses import PlacementHint, diagnose_candidate, enumerate_hypotheses, pose_key
from guide2build.engine.source_view import project_source_points
from guide2build.releases.models import SceneV2, digest
from test_engine_spatial import SOURCE, connection, group_scene, pose, scene, step


@pytest.fixture
def catalogue(monkeypatch):
    metadata = json.loads(METADATA.read_text())
    available = {p["geometry_ref"]: p for p in metadata["parts"]}
    def load(_root, references=None):
        references = set(references) if references is not None else set(available)
        if references-set(available):
            raise ValueError("Unsupported connector metadata")
        return deepcopy(metadata), {ref: deepcopy(available[ref]) for ref in references}
    monkeypatch.setattr(hypotheses, "load_connector_catalogue", load)
    monkeypatch.setattr(spatial, "load_connector_catalogue", load)
    return available


def initial():
    return scene({"base": "3022", "slope": "13547"}, [
        step("one", {"base": pose(), "slope": pose(10, 16, 10)}, ["base", "slope"])])


def test_enumerates_competing_positions_orientations_with_fixed_budgets_and_raw_preservation(catalogue):
    raw = initial()
    before = digest(raw)
    hint = PlacementHint(step_id="one", moving_instance_id="slope", target_instance_ids=["base"],
                         moving_connector_ids=["socket:0:-16:0"], source=SOURCE)
    result = enumerate_hypotheses(raw, None, Path("unused"), connections=[connection()],
        roots=[{"step_id": "one", "instance_id": "base"}], hints=[hint], max_candidates=64, beam_width=8)
    assert result["evaluated_count"] == 16
    assert len(result["retained_beam"]) == 8
    assert len(result["candidates"]) == 3
    plans = [entry["plan"][0] for entry in result["attempts"]]
    assert {plan["quarter_turns"] for plan in plans} == {0, 1, 2, 3}
    assert len({plan["target_connector_id"] for plan in plans}) == 4
    assert digest(raw) == before
    assert result["candidates"][-1]["scene"] == raw.model_dump(mode="json")
    assert all(c["scene"]["geometry_check"] == c["scene"]["connector_check"] == "not_run"
               for c in result["candidates"])
    bounded = enumerate_hypotheses(raw, None, Path("unused"), connections=[connection()],
        roots=[{"step_id": "one", "instance_id": "base"}], hints=[hint], max_candidates=3)
    assert bounded["evaluated_count"] == 3 and bounded["truncated"]


def test_group_hypotheses_preserve_all_relative_transforms(catalogue):
    raw, connections, roots = group_scene()
    # The already constructed callout is an immutable prefix. Search attachment
    # alternatives without silently redesigning the detached group's internals.
    previous = raw.model_dump(mode="json")
    previous["steps"] = previous["steps"][:-1]
    result = enumerate_hypotheses(raw, previous, Path("unused"), connections=connections[-1:])
    alternatives = [c for c in result["candidates"] if c["kind"] == "connector_hypothesis"]
    assert alternatives
    for candidate in alternatives:
        poses = candidate["scene"]["steps"][-1]["poses"]
        # The strip is a rigid child 8 LDU up and 10 LDU forward from its plate.
        assert poses["strip"]["position_ldu"] == pytest.approx(transform_point(poses["callout"], [0, 8, 10]))
        assert poses["strip"]["quaternion_xyzw"] == pytest.approx(poses["callout"]["quaternion_xyzw"])
        assert len(candidate["scene"]["instances"]) == 3
        assert candidate["scene"]["steps"][:-1] == previous["steps"]


def test_eight_complete_beam_alternatives_survive_serialization_with_three_render_candidates(catalogue, tmp_path):
    raw = initial()
    hint = PlacementHint(step_id="one", moving_instance_id="slope", target_instance_ids=["base"],
                         moving_connector_ids=["socket:0:-16:0"], source=SOURCE)
    result = enumerate_hypotheses(raw, None, Path("unused"), connections=[connection()],
        roots=[{"step_id": "one", "instance_id": "base"}], hints=[hint],
        max_candidates=64, beam_width=8, return_count=3)
    receipt = tmp_path / "hypotheses.json"
    receipt.write_text(json.dumps(result, allow_nan=False))
    saved = json.loads(receipt.read_text())
    assert saved["evaluated_count"] == 16
    assert len(saved["candidates"]) == 3 and len(saved["retained_beam"]) == 8
    assert len({digest(item["scene"]) for item in saved["retained_beam"]}) == 8
    for item in saved["retained_beam"]:
        reconstructed = SceneV2.model_validate(item["scene"])
        assert item["hypothesis_id"] == "connector-" + digest(reconstructed)[:16]
        assert item["solver_report"]["snapshots"]
        assert isinstance(item["findings"], list)
        assert item["ranking_components"]["image_agreement"] == "not_run"
        assert reconstructed.geometry_check == reconstructed.connector_check == "not_run"
    assert saved["candidates"][:2] == [c for c in saved["retained_beam"]
        if hypotheses._physical_transform_key(c["scene"]) != hypotheses._physical_transform_key(raw)][:2]
    assert saved["candidates"][-1]["scene"] == raw.model_dump(mode="json")
    # Later review annotations on rendered candidates must not rewrite retained search evidence.
    result["candidates"][0]["findings"].append({"code": "later_visual_review"})
    assert result["retained_beam"] == saved["retained_beam"]


def test_unsupported_geometry_retains_raw_with_named_finding(catalogue):
    raw = scene({"unhandled": "99999"}, [step("one", {"unhandled": pose()}, ["unhandled"])])
    result = enumerate_hypotheses(raw, None, Path("unused"))
    assert result["evaluated_count"] == 0
    assert len(result["candidates"]) == 1 and result["candidates"][0]["kind"] == "raw_fallback"
    assert result["candidates"][0]["scene"] == raw.model_dump(mode="json")
    assert result["findings"][0]["code"] == "unsupported_connector_geometry"


def test_coincident_geometry_detects_quaternion_sign_equivalence_and_history_motion(catalogue):
    positive, negative = pose(), {**pose(), "quaternion_xyzw": [0, 0, 0, -1]}
    assert pose_key(positive) == pose_key(negative)
    raw = scene({"a": "3022", "b": "3022"}, [
        step("one", {"a": positive, "b": negative}, ["a", "b"]),
        step("two", {"a": pose(2), "b": negative}, [])])
    report = diagnose_candidate(raw, None, Path("unused"))
    codes = {f["code"] for f in report["findings"]}
    assert {"exact_coincident_geometry", "historical_movement", "floating_supported_instance"} <= codes
    assert report["checks"]["narrow_phase"] == report["checks"]["physical"] == "not_run"


def test_occupancy_gap_and_aabb_are_distinct_diagnostics(catalogue):
    raw = scene({"base": "3022", "a": "13547", "b": "13547"}, [
        step("one", {"base": pose(), "a": pose(10, 16, 10), "b": pose(10, 16, 10)}, ["base", "a", "b"])])
    report = diagnose_candidate(raw, None, Path("unused"))
    assert "occupied_connector" in {f["code"] for f in report["findings"]}
    assert "aabb_overlap_candidate" in {f["code"] for f in report["findings"]}
    gap = initial()
    gap.steps[0].poses["slope"].position_ldu = (10, 18, 10)
    report = diagnose_candidate(gap, None, Path("unused"))
    assert "near_connector_gap" in {f["code"] for f in report["findings"]}
    assert report["checks"]["geometry"] == "broad_phase_only"


def test_local_occupancy_preserves_independent_valid_branch_and_true_floating_piece(catalogue):
    raw = scene({"base": "3022", "a": "13547", "b": "13547", "valid": "13547",
                 "leaf": "3022", "loose": "3022"}, [step("one", {
        "base": pose(), "a": pose(10, 16, 10), "b": pose(10, 16, 10),
        "valid": pose(-10, 16, 10), "leaf": pose(-20, 24, 60), "loose": pose(200)},
        ["base", "a", "b", "valid", "leaf", "loose"])])
    before = digest(raw)
    report = diagnose_candidate(raw, None, Path("unused"))
    occupied = [item for item in report["findings"] if item["code"] == "occupied_connector"]
    assert len(occupied) == 1
    assert occupied[0]["instance_ids"] == ["a", "b", "base"]
    assert occupied[0]["feature"] == ["base", "stud:10:0:10"]
    assert occupied[0]["nominal_mates"] == [["a", "socket:0:-16:0"], ["b", "socket:0:-16:0"]]
    floating = [item for item in report["findings"] if item["code"] == "floating_supported_instance"]
    assert len(floating) == 1 and floating[0]["instance_ids"] == ["loose"]
    snapshot = report["snapshots"][0]
    valid_edges = {frozenset((item["stud"][0], item["socket"][0]))
        for item in snapshot["nominal_contacts"] if item["occupancy"] == "single_mate"}
    assert {frozenset(("base", "valid")), frozenset(("valid", "leaf"))} <= valid_edges
    assert sum(item["occupancy"] == "conflicted" for item in snapshot["nominal_contacts"]) == 2
    assert snapshot["occupancy_conflicts"][0]["feature"] == ["base", "stud:10:0:10"]
    assert snapshot["connectivity_basis"] == "all_nominal_coincidences_not_validated_connections"
    assert report["checks"]["narrow_phase"] == report["checks"]["physical"] == "not_run"
    # The strict solver still rejects exactly the same multiply occupied feature.
    with pytest.raises(spatial.SpatialError, match="Connector occupancy conflict"):
        spatial._contacts(raw.steps[0].poses, {item.instance_id: item for item in raw.instances}, catalogue, .05)
    assert digest(raw) == before


def test_nonconflicting_diagnostic_contacts_match_strict_rules(catalogue):
    raw = initial()
    instances = {item.instance_id: item for item in raw.instances}
    nominal, conflicts = hypotheses._diagnostic_contacts(raw.steps[0].poses, instances, catalogue, .05)
    strict = spatial._contacts(raw.steps[0].poses, instances, catalogue, .05)
    assert not conflicts
    assert [{key: value for key, value in item.items() if key != "occupancy"} for item in nominal] == strict
    # Preserve both distance and opposed-normal requirements rather than inferring contact from nearby bounds.
    raw.steps[0].poses["slope"].position_ldu = (10, 18, 10)
    nominal, conflicts = hypotheses._diagnostic_contacts(raw.steps[0].poses, instances, catalogue, .05)
    assert nominal == strict[:0] and not conflicts


def test_distorted_group_is_reported_without_moving_original(catalogue):
    raw, _, _ = group_scene()
    raw.steps[-1].poses["strip"].position_ldu = (205, 8, 10)
    before = digest(raw)
    report = diagnose_candidate(raw, None, Path("unused"))
    assert "nonrigid_group" in {f["code"] for f in report["findings"]}
    assert digest(raw) == before


def observations(catalogue):
    raw = scene({"near": "13547", "far": "13547"}, [
        step("one", {"near": pose(-10), "far": pose(10)}, ["near", "far"])])
    camera = {"projection": "orthographic", "right": [.8, 0, .6], "up": [.3, sqrt(.75), -.4],
              "target_ldu": [0, 8, 30], "vertical_span_ldu": 180, "image_size": [1200, 900]}
    named, world = [], []
    for identity in ["near", "far"]:
        for feature in catalogue["parts/13547.dat"]["connectors"]:
            if "landmark" not in feature:
                continue
            named.append({"instance_id": "far" if identity == "near" else "near", "landmark_id": feature["landmark"]["landmark_id"]})
            world.append(transform_point(raw.steps[0].poses[identity], feature["landmark"]["position_ldu"]))
    for item, uv in zip(named, project_source_points(camera, world), strict=True):
        item["image_uv"] = uv
    return raw, {"step_id": "one", "landmarks": named, "view_family": "upright_above"}


def test_identity_search_corrects_wrong_correspondence_without_altering_poses_or_image_points(catalogue):
    raw, observation = observations(catalogue)
    before, points = digest(raw), [x["image_uv"] for x in observation["landmarks"]]
    ranked = hypotheses.rank_landmark_identity_alternatives(raw, observation, Path("unused"), (1200, 900),
                                                           instance_groups=[["near", "far"]])
    best = ranked["candidates"][0]
    assert best["identity_changes"] == {"near": "far", "far": "near"}
    assert best["fit"]["rms_pixels"] < .001
    assert ranked["candidates"][1]["fit"]["rms_pixels"] > 4
    assert [tuple(x["image_uv"]) for x in best["observation"]["landmarks"]] == points
    assert digest(raw) == before and not ranked["assembly_poses_changed"]


def test_source_fitting_boundary_consumes_identity_alternatives_and_retains_original(catalogue, tmp_path):
    raw, observation = observations(catalogue)
    path = tmp_path / "page.png"
    Image.new("RGB", (1200, 900), "white").save(path)
    fits, cameras = hypotheses.source_view_alternatives(raw, None, [observation], Path("unused"), path)
    assert fits["one"]["identity_changes"] and fits["one"]["requires_visual_review"]
    assert fits["one"]["rms_pixels"] < .001 and "one" in cameras
    assert fits["one"]["original_observation"]["landmarks"][0]["instance_id"] == "far"
    assert fits["one"]["selected_observation"]["landmarks"][0]["instance_id"] == "near"


def test_bad_rotation_and_unbounded_search_are_rejected(catalogue):
    with pytest.raises(ValueError):
        PlacementHint(step_id="one", moving_instance_id="slope", target_instance_ids=["base"], quarter_turns=[True], source=SOURCE)
    with pytest.raises(ValueError):
        enumerate_hypotheses(initial(), None, Path("unused"), max_candidates=65)


def test_one_guessed_receiver_connector_does_not_collapse_position_search(catalogue):
    raw = initial()
    hint = PlacementHint(step_id="one", moving_instance_id="slope", target_instance_ids=["base"],
        moving_connector_ids=["socket:0:-16:0"], target_connector_ids=["stud:10:0:10"],
        quarter_turns=[0], source=SOURCE)
    result = enumerate_hypotheses(raw, None, Path("unused"), connections=[connection()], hints=[hint],
                                 roots=[{"step_id": "one", "instance_id": "base"}])
    plans = [trial["plan"][0] for trial in result["attempts"]]
    assert len(plans) == 16
    assert len({p["target_connector_id"] for p in plans[:4]}) == 4
    assert {p["quarter_turns"] for p in plans[:4]} == {0, 1, 2, 3}
    assert len({p["target_connector_id"] for p in plans}) == 4
    # Two render slots must show distinct receiving positions, not just a spin
    # of the same source-nominated stud. The third remains the raw proposal.
    first, second, fallback = result["candidates"]
    assert first["search_features"]["positions"] != second["search_features"]["positions"]
    assert fallback["scene"] == raw.model_dump(mode="json")
    assert result["search_receipt"]["anchors"][0]["source_nominated_receiver_ids"] == ["base"]
    assert result["search_receipt"]["anchors"][0]["nominations"][1]["target_connector_ids"] == ["stud:10:0:10"]
    assert len({tuple(f) for c in result["retained_beam"] for f in c["search_features"]["orientations"]}) == 4


def test_raw_equivalent_solve_keeps_receipt_without_consuming_a_render_slot(catalogue):
    raw = initial()
    result = enumerate_hypotheses(raw, None, Path("unused"), connections=[connection()],
                                 roots=[{"step_id": "one", "instance_id": "base"}])
    raw_key = hypotheses._physical_transform_key(raw)
    equivalents = [c for c in result["retained_beam"] if hypotheses._physical_transform_key(c["scene"]) == raw_key]
    assert equivalents and all(c["solver_report"]["status"] == "pass" for c in equivalents)
    assert len(result["candidates"]) == 3
    assert len({hypotheses._physical_transform_key(c["scene"]) for c in result["candidates"]}) == 3
    assert result["candidates"][-1]["kind"] == "raw_fallback"
    assert result["candidates"][-1]["scene"] == raw.model_dump(mode="json")
    assert set(result["search_receipt"]["render_selection"]["skipped_equivalent_hypothesis_ids"]) >= {
        c["hypothesis_id"] for c in equivalents}
    assert len(result["retained_beam"]) == 8 and result["evaluated_count"] == 16


def test_small_budget_reaches_opposite_receiver_extent_before_neighbour_stud(catalogue):
    raw = scene({"receiver": "3020", "moving": "13547"}, [step("one", {
        "receiver": pose(), "moving": pose(-30, 16, -10)}, ["receiver", "moving"])])
    hint = PlacementHint(step_id="one", moving_instance_id="moving", target_instance_ids=["receiver"],
        moving_connector_ids=["socket:0:-16:0"], target_connector_ids=["stud:-30:0:-10"],
        quarter_turns=[0], source=SOURCE)
    result = enumerate_hypotheses(raw, None, Path("unused"), hints=[hint],
        roots=[{"step_id": "one", "instance_id": "receiver"}], max_candidates=2)
    points = [attempt["search_features"]["positions"][0][-3:] for attempt in result["attempts"]]
    assert points == [[-30., 0., -10.], [30., 0., 10.]]
    assert result["truncated"] and result["evaluated_count"] == 2


def test_receiver_identity_diversity_never_adds_unlisted_present_part(catalogue):
    prefix = scene({"base": "3022", "upper": "3022", "unlisted": "13547"}, [step("old", {
        "base": pose(), "upper": pose(0, 8, 20), "unlisted": pose(-10, 16, -10)},
        ["base", "upper", "unlisted"])])
    draft = prefix.model_dump(mode="json")
    draft["instances"].append({**draft["instances"][-1], "instance_id": "moving"})
    draft["steps"].append(step("new", {**draft["steps"][-1]["poses"], "moving": pose(10, 16, 10)}, ["moving"]))
    raw = SceneV2.model_validate(draft)
    hint = PlacementHint(step_id="new", moving_instance_id="moving", target_instance_ids=["base", "upper"],
        moving_connector_ids=["socket:0:-16:0"], target_connector_ids=["stud:10:0:10"], quarter_turns=[0], source=SOURCE)
    result = enumerate_hypotheses(raw, prefix.model_dump(mode="json"), Path("unused"), hints=[hint], max_candidates=8)
    plans = [trial["plan"][0] for trial in result["attempts"]]
    assert {p["target_instance_id"] for p in plans[:2]} == {"base", "upper"}
    assert {p["target_instance_id"] for p in plans} == {"base", "upper"}
    assert len({(p["target_instance_id"], p["target_connector_id"]) for p in plans}) == 8
    assert result["evaluated_count"] == 8 and result["truncated"]
    assert "unlisted" not in result["search_receipt"]["anchors"][0]["source_nominated_receiver_ids"]
    assert result["candidates"][-1]["scene"] == draft


def test_bounded_plan_frontier_and_group_shape_hold_across_multiple_anchors(catalogue):
    raw, choices, roots = group_scene()
    result = enumerate_hypotheses(raw, None, Path("unused"), connections=choices,
        roots=[{"step_id": s, "instance_id": i} for s, i in roots])
    assert result["evaluated_count"] == 64 and result["truncated"]
    assert len(result["retained_beam"]) <= 8 and len(result["candidates"]) <= 3
    assert len({a["plan"][-1]["target_connector_id"] for a in result["attempts"][:16]}) > 1
    for item in result["retained_beam"]:
        prior, attached = item["scene"]["steps"][-2:]
        expected = spatial._rigid_move({i: spatial.Pose.model_validate(p) for i, p in prior["poses"].items()},
                                      {"callout", "strip"}, "callout", spatial.Pose.model_validate(attached["poses"]["callout"]))
        assert all(spatial._same_pose(expected[i], attached["poses"][i]) for i in expected)


def test_incomplete_group_is_not_silently_filled_by_search(catalogue):
    raw, choices, _ = group_scene()
    prefix = raw.model_dump(mode="json")
    prefix["steps"] = prefix["steps"][:-1]
    incomplete = choices[-1].model_copy(update={"moving_group_ids": ["callout"]})
    result = enumerate_hypotheses(raw, prefix, Path("unused"), connections=[incomplete])
    assert result["candidates"] == [result["candidates"][-1]]
    assert result["candidates"][0]["kind"] == "raw_fallback"
    assert all(a["status"] == "rejected" for a in result["attempts"])
    assert all(a["plan"][0]["moving_group_ids"] == ["callout"] for a in result["attempts"])


@pytest.mark.parametrize("source", [{**SOURCE, "source_sha256": "b"*64}, {**SOURCE, "page_index": 1}])
def test_wrong_source_hint_cannot_nominate_receivers(catalogue, source):
    hint = PlacementHint(step_id="one", moving_instance_id="slope", target_instance_ids=["base"], source=source)
    result = enumerate_hypotheses(initial(), None, Path("unused"), hints=[hint],
                                 roots=[{"step_id": "one", "instance_id": "base"}])
    assert not result["search_receipt"]["anchors"]
    assert "unsupported_source_hint" in {f["code"] for f in result["findings"]}
    assert result["candidates"][0]["kind"] == "raw_fallback"


@pytest.mark.parametrize("message", ["Connector geometry hash mismatch", "Unsafe connector geometry path or size",
                                      "Unsupported connector geometry provenance", "Connector geometry dependency limit"])
def test_integrity_and_resource_errors_never_become_quality_fallback(monkeypatch, message):
    def broken(*_):
        raise ValueError(message)
    monkeypatch.setattr(hypotheses, "load_connector_catalogue", broken)
    with pytest.raises(ValueError, match=message):
        enumerate_hypotheses(initial(), None, Path("unused"))


@pytest.mark.parametrize("code", ["resource_limit", "coordinate_limit", "prefix_modified"])
def test_solver_integrity_boundaries_remain_hard(catalogue, monkeypatch, code):
    def rejected(*_):
        raise spatial.SpatialError("hard bounded solve rejection", code=code)
    monkeypatch.setattr(hypotheses, "solve_candidate", rejected)
    with pytest.raises(spatial.SpatialError, match="hard bounded"):
        enumerate_hypotheses(initial(), None, Path("unused"), connections=[connection()])


def test_scoped_diagnostics_keep_all_history_and_group_checks(catalogue, monkeypatch):
    raw, _, _ = group_scene()
    raw.steps[-1].poses["strip"].position_ldu = (123, 8, 10)
    calls = []
    original = hypotheses._diagnostic_contacts
    def counted(poses, *args):
        calls.append(set(poses))
        return original(poses, *args)
    monkeypatch.setattr(hypotheses, "_diagnostic_contacts", counted)
    report = diagnose_candidate(raw, None, Path("unused"), checked_step_ids=[raw.steps[0].step_id])
    assert {f["code"] for f in report["findings"]} >= {"nonrigid_group"}
    assert calls == [{"main"}]
    assert report["coverage"]["history_and_group_scope"] == "all_snapshots"
    assert report["coverage"]["omitted_or_partial_pose_count"] > 0
    assert report["coverage"]["status"] == "partial"
    with pytest.raises(ValueError, match="snapshot scope"):
        diagnose_candidate(raw, None, Path("unused"), checked_step_ids=["unknown"])


def test_large_snapshot_retains_history_and_explicit_unknown_heavy_checks(catalogue, monkeypatch):
    poses = {f"p{i}": pose(i*40) for i in range(520)}
    raw = scene(dict.fromkeys(poses, "3022"), [step("large", poses, list(poses)),
        step("later", {**poses, "p0": pose(1)}, [])])
    def unexpected(*_):
        pytest.fail("Heavy contacts must not run on this over-cap snapshot")
    monkeypatch.setattr(hypotheses, "_diagnostic_contacts", unexpected)
    report = diagnose_candidate(raw, None, Path("unused"), checked_step_ids=["large"])
    assert "historical_movement" in {f["code"] for f in report["findings"]}
    assert report["snapshots"][0]["contact_aabb_status"] == "not_run"
    assert report["snapshots"][0]["duplicate_status"] == "checked_finite_scope"
    assert report["coverage"]["status"] == "partial"
    assert report["coverage"]["omitted_or_partial_pose_count"] == 1040


def test_truncated_diagnostics_preserve_counts_sentinel_and_candidate_coverage(catalogue):
    poses = {f"p{i}": pose(i*.5) for i in range(34)}
    prefix = scene(dict.fromkeys(poses, "3022"), [step("old", poses, list(poses))])
    draft = prefix.model_dump(mode="json")
    draft["instances"].append({**draft["instances"][0], "instance_id": "slope", "part_id": "13547",
                                "geometry_ref": "parts/13547.dat"})
    draft["steps"].append(step("new", {**poses, "slope": pose(10, 16, 10)}, ["slope"]))
    raw = SceneV2.model_validate(draft)
    result = enumerate_hypotheses(raw, prefix.model_dump(mode="json"), Path("unused"),
        connections=[connection("new", target="p0")], max_candidates=1)
    # With one evaluation the solved pose can equal raw; its receipt stays in
    # the beam even when it correctly does not consume another render slot.
    assert result["retained_beam"]
    for candidate in [*result["candidates"], *result["retained_beam"]]:
        assert candidate["findings_truncated"]
        assert candidate["computed_findings_count"] > candidate["retained_findings_count"] == 511
        assert len(candidate["findings"]) == 512
        assert candidate["findings"][-1]["code"] == "diagnostics_truncated"
        assert candidate["diagnostic_coverage"]["status"] == "partial"
        assert sum(candidate["finding_counts"].values()) == candidate["computed_findings_count"]
        assert len(candidate["diagnostic_receipt_sha256"]) == 64
