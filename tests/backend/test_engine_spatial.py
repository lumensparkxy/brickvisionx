"""Original synthetic assemblies test solver rules, never booklet accuracy."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from guide2build.engine.connectors import METADATA, transform_point
from guide2build.engine.spatial import ConnectionChoice, RootPlacement, SpatialError, solve_candidate
from guide2build.releases.models import SceneV2

SOURCE = {"page_index": 0, "bbox": [0, 0, 1, 1], "source_sha256": "a" * 64}


def pose(x=0, y=0, z=0):
    return {"position_ldu": [x, y, z], "quaternion_xyzw": [0, 0, 0, 1]}


def step(identity, poses, introduced, *, action="add_parts", group=None):
    return {"step_id": identity, "main_step_number": 1, "section_id": "main", "substep_label": None,
            "instruction": "Original synthetic solver fixture", "source": SOURCE,
            "introduced_instance_ids": introduced, "active_instance_ids": introduced or list(poses),
            "visible_instance_ids": list(poses), "poses": poses, "action": action, "assembly_group_id": group}


def scene(parts, steps):
    return SceneV2.model_validate({"schema_version": "2.0", "set_number": "12345", "guide_id": "synthetic",
        "revision": "solver-test", "source_sha256": SOURCE["source_sha256"], "status": "candidate",
        "sources": [{"guide_id": "synthetic", "source_sha256": SOURCE["source_sha256"],
                     "official_url": "https://www.lego.com/synthetic-test-only", "page_count": 1}],
        "sections": [{"section_id": "main", "source_sha256": SOURCE["source_sha256"], "label": "Synthetic"}],
        "instances": [{"instance_id": identity, "part_id": part, "geometry_ref": f"parts/{part}.dat",
                       "color_code": "15", "source": SOURCE, "origin": "vision_proposal", "mapping_status": "candidate"}
                      for identity, part in parts.items()], "steps": steps})


def connection(step_id="one", moving="slope", target="base", moving_site="socket:0:-16:0",
               target_site="stud:10:0:10", turn=0, group=()):
    return ConnectionChoice(step_id=step_id, moving_instance_id=moving, target_instance_id=target,
                            moving_connector_id=moving_site, target_connector_id=target_site,
                            quarter_turns=turn, moving_group_ids=list(group))


@pytest.fixture
def nominal_catalogue(monkeypatch):
    # Geometry/provenance verification is tested independently in test_engine_connectors.
    # These unit tests exercise nominal frames on deliberately synthetic arrangements.
    metadata = json.loads(METADATA.read_text())
    def load(_root, references):
        available = {p["geometry_ref"]: deepcopy(p) for p in metadata["parts"]}
        if set(references)-set(available):
            raise ValueError("Unsupported connector metadata")
        return deepcopy(metadata), {ref: available[ref] for ref in references}
    monkeypatch.setattr("guide2build.engine.spatial.load_connector_catalogue", load)


def run(value, connections, roots, previous=None):
    return solve_candidate(value, previous, connections, [RootPlacement(step_id=s, instance_id=i) for s, i in roots],
                           Path("unused-synthetic-unit-test"))


@pytest.mark.parametrize("turn", [0, 1, 2, 3])
def test_inverted_curve_socket_seats_at_16_not_extremity_24(nominal_catalogue, turn):
    raw = scene({"base": "3022", "slope": "13547"}, [step("one", {"base": pose(), "slope": pose(10, 24, 10)},
                                                           ["base", "slope"])])
    saved = raw.model_dump(mode="json")
    solved, report = run(raw, [connection(turn=turn)], [("one", "base")])
    corrected = solved.steps[0].poses["slope"]
    assert corrected.position_ldu == (10, 16, 10)
    assert transform_point(corrected, [0, -16, 0]) == [10, 0, 10]
    assert raw.model_dump(mode="json") == saved
    assert report["correction_count"] == 1 and report["corrections"][0]["before"]["position_ldu"][1] == 24
    assert report["snapshots"][0]["narrow_phase"] == "not_run"
    assert report["geometry_check"] == "broad_phase_only"
    assert report["physical_check"] == solved.physical_build_check == "not_run"
    assert solved.geometry_check == solved.connector_check == "not_run"


def test_unanchored_piece_cannot_pass_as_floating_pose_or_extra_root(nominal_catalogue):
    raw = scene({"base": "3022", "slope": "13547"}, [step("one", {"base": pose(), "slope": pose(10, 24, 10)},
                                                           ["base", "slope"])])
    with pytest.raises(SpatialError, match="Every new piece"):
        run(raw, [], [("one", "base")])
    with pytest.raises(SpatialError, match="Only one initial root"):
        run(raw, [], [("one", "base"), ("one", "slope")])
    with pytest.raises(SpatialError, match="explicit root"):
        run(raw, [connection()], [])


@pytest.mark.parametrize("kwargs, message", [({"moving_site": "socket:not-real"}, "Unknown connector"),
    ({"moving_site": "stud:0:-8:0"}, "stud/socket"), ({"target": "unknown"}, "distinct visible")])
def test_wrong_ids_and_incompatible_contacts_fail_closed(nominal_catalogue, kwargs, message):
    raw = scene({"base": "3022", "slope": "13547"}, [step("one", {"base": pose(), "slope": pose(10, 24, 10)},
                                                           ["base", "slope"])])
    with pytest.raises(ValueError, match=message):
        run(raw, [connection(**kwargs)], [("one", "base")])


def test_unsupported_part_never_uses_generic_grid(nominal_catalogue):
    raw = scene({"unknown": "99999"}, [step("one", {"unknown": pose()}, ["unknown"])])
    with pytest.raises(ValueError, match="Unsupported connector metadata"):
        run(raw, [], [("one", "unknown")])


def test_one_stud_cannot_be_occupied_by_two_distinct_pieces(nominal_catalogue):
    raw = scene({"base": "3022", "slope": "13547", "second": "13547"},
                [step("one", {"base": pose(), "slope": pose(10, 24, 10), "second": pose(50, 24, 10)},
                      ["base", "slope", "second"])])
    with pytest.raises(SpatialError, match="occupancy conflict"):
        run(raw, [connection(), connection(moving="second")], [("one", "base")])


def test_adjacent_asymmetric_slopes_have_distinct_occupied_features(nominal_catalogue):
    raw = scene({"base": "3022", "slope": "13547", "second": "13547"},
                [step("one", {"base": pose(), "slope": pose(10, 24, 10), "second": pose(-10, 24, 10)},
                      ["base", "slope", "second"])])
    solved, report = run(raw, [connection(), connection(moving="second", target_site="stud:-10:0:10")],
                         [("one", "base")])
    assert solved.steps[0].poses["second"].position_ldu == (-10, 16, 10)
    assert len(report["snapshots"][0]["nominal_contacts"]) == 2


def test_hidden_physical_piece_still_reserves_its_connector(nominal_catalogue):
    raw = scene({"base": "3022", "first": "25269", "second": "25269"}, [
        step("one", {"base": pose(), "first": pose(10, 8, 10)}, ["base", "first"]),
        step("two", {"base": pose(), "second": pose(10, 8, 10)}, ["second"])])
    choices = [connection("one", "first", moving_site="socket:0:-8:0"),
               connection("two", "second", moving_site="socket:0:-8:0")]
    with pytest.raises(SpatialError, match="occupancy conflict"):
        run(raw, choices, [("one", "base")])
    previous = raw.model_dump(mode="json")
    previous["steps"] = previous["steps"][:1]
    previous["instances"] = previous["instances"][:2]
    with pytest.raises(SpatialError, match="occupancy conflict"):
        run(raw, choices[1:], [], previous)


def test_detached_callouts_have_explicit_workspaces_independent_of_visibility(nominal_catalogue):
    raw = scene({"base": "3022", "callout": "3022"}, [
        step("one", {"base": pose()}, ["base"]),
        step("two", {"base": pose(), "callout": pose()}, ["callout"], action="build_subassembly", group="detached")])
    _, report = run(raw, [], [("one", "base"), ("two", "callout")])
    assert report["snapshots"][-1]["workspaces"] == {"base": "main", "callout": "group:detached"}
    assert report["snapshots"][-1]["aabb_overlap_candidates"] == []


def test_extreme_finite_coordinates_fail_before_quantization(nominal_catalogue):
    raw = scene({"base": "3022"}, [step("one", {"base": pose(1e308)}, ["base"])])
    with pytest.raises(SpatialError, match="coordinate.*bound") as error:
        run(raw, [], [("one", "base")])
    assert error.value.report["code"] == "coordinate_limit"


def test_corrected_inheritance_does_not_reintroduce_old_raw_pose(nominal_catalogue):
    raw = scene({"base": "3022", "slope": "13547", "tile": "25269"}, [
        step("one", {"base": pose(), "slope": pose(10, 24, 10)}, ["base", "slope"]),
        step("two", {"base": pose(), "slope": pose(10, 24, 10), "tile": pose(999, 999, 999)}, ["tile"])])
    solved, _ = run(raw, [connection(), connection("two", "tile", "slope", "socket:0:-8:0", "stud:0:-8:20")],
                    [("one", "base")])
    assert solved.steps[1].poses["slope"].position_ldu == (10, 16, 10)
    assert solved.steps[1].poses["tile"].position_ldu == (10, 16, 30)


def test_accepted_prefix_and_input_remain_immutable(nominal_catalogue):
    initial = scene({"base": "3022", "slope": "13547"}, [step("one", {"base": pose(), "slope": pose(10, 24, 10)},
                                                               ["base", "slope"])])
    accepted, _ = run(initial, [connection()], [("one", "base")])
    previous = accepted.model_dump(mode="json")
    draft = deepcopy(previous)
    tile = deepcopy(draft["instances"][0])
    tile.update(instance_id="tile", part_id="25269", geometry_ref="parts/25269.dat")
    draft["instances"].append(tile)
    draft["steps"].append(step("two", {**draft["steps"][0]["poses"], "tile": pose(999, 999, 999)}, ["tile"]))
    solved, _ = run(SceneV2.model_validate(draft),
                    [connection("two", "tile", "slope", "socket:0:-8:0", "stud:0:-8:20")], [], previous)
    assert solved.model_dump(mode="json")["steps"][0] == previous["steps"][0]
    assert previous == accepted.model_dump(mode="json")
    draft["steps"][0]["poses"]["base"]["position_ldu"][0] = 20
    with pytest.raises(SpatialError, match="prefix is immutable"):
        run(SceneV2.model_validate(draft), [], [], previous)


def group_scene():
    parts = {"main": "3022", "callout": "3020", "strip": "3710"}
    steps = [step("one", {"main": pose()}, ["main"]),
             step("build", {"callout": pose(200), "strip": pose(200, 8, 10)}, ["callout", "strip"],
                  action="build_subassembly", group="wing"),
             step("attach", {"main": pose(), "callout": pose(200), "strip": pose(200, 8, 10)}, [],
                  action="attach_subassembly", group="wing")]
    choices = [connection("build", "strip", "callout", "socket:-30:-8:0", "stud:-30:0:10"),
               connection("attach", "callout", "main", "socket:-30:-8:-10", "stud:-10:0:-10",
                          group=["callout", "strip"])]
    return scene(parts, steps), choices, [("one", "main"), ("build", "callout")]


def test_detached_group_attaches_rigidly_without_duplicate_physical_ids(nominal_catalogue):
    raw, choices, roots = group_scene()
    solved, report = run(raw, choices, roots)
    poses = solved.steps[-1].poses
    assert poses["callout"].position_ldu == (20, 8, 0)
    assert poses["strip"].position_ldu == (20, 16, 10)
    assert len(solved.instances) == 3
    assert report["connections"][-1]["moving_group_ids"] == ["callout", "strip"]
    # Resume uses prior snapshots to recover group membership without reference data.
    previous = solved.model_dump(mode="json")
    previous["steps"] = previous["steps"][:2]
    draft = solved.model_dump(mode="json")
    draft["steps"][-1] = raw.model_dump(mode="json")["steps"][-1]
    resumed, _ = run(SceneV2.model_validate(draft), [choices[-1]], [], previous)
    assert resumed.model_dump(mode="json") == solved.model_dump(mode="json")


def test_partial_or_nonrigid_group_move_is_rejected(nominal_catalogue):
    raw, choices, roots = group_scene()
    choices[-1].moving_group_ids = ["callout"]
    with pytest.raises(SpatialError, match="complete declared detached group"):
        run(raw, choices, roots)
    raw, choices, roots = group_scene()
    raw.steps[-1].poses["strip"].position_ldu = (201, 8, 10)
    with pytest.raises(SpatialError, match="not rigid"):
        run(raw, choices, roots)


def test_ordinary_addition_cannot_escape_detached_group_membership_fresh_or_resumed(nominal_catalogue):
    raw = scene({"main": "3022", "callout": "3020", "strip": "3710"}, [
        step("one", {"main": pose()}, ["main"]),
        step("build", {"callout": pose(200)}, ["callout"], action="build_subassembly", group="wing"),
        step("improper", {"callout": pose(200), "strip": pose(200, 8, 10)}, ["strip"]),
        step("attach", {"main": pose(), "callout": pose(200), "strip": pose(200, 8, 10)}, [],
             action="attach_subassembly", group="wing")])
    choices = [connection("improper", "strip", "callout", "socket:-30:-8:0", "stud:-30:0:10"),
               connection("attach", "callout", "main", "socket:-30:-8:-10", "stud:-10:0:-10", group=["callout"])]
    with pytest.raises(SpatialError, match="detached group requires build_subassembly"):
        run(raw, choices, [("one", "main"), ("build", "callout")])
    previous = raw.model_dump(mode="json")
    previous["steps"] = previous["steps"][:3]
    with pytest.raises(SpatialError, match="Historical addition to a detached group"):
        run(raw, choices[-1:], [], previous)


@pytest.mark.parametrize("turn", [1, 2, 3])
def test_quarter_turn_group_attachment_preserves_internal_relative_poses(nominal_catalogue, turn):
    raw, choices, roots = group_scene()
    choices[-1].quarter_turns = turn
    solved, _ = run(raw, choices, roots)
    poses = solved.steps[-1].poses
    expected = transform_point(poses["callout"], [0, 8, 10])
    assert list(poses["strip"].position_ldu) == pytest.approx(expected)
    assert poses["strip"].quaternion_xyzw == pytest.approx(poses["callout"].quaternion_xyzw)


def test_nested_groups_merge_membership_before_the_outer_attachment(nominal_catalogue):
    raw = scene({"main": "3022", "inner": "3022", "strip": "3710", "outer": "3020"}, [
        step("one", {"main": pose()}, ["main"]),
        step("inner-build", {"inner": pose(), "strip": pose(0, 8, 10)}, ["inner", "strip"],
             action="build_subassembly", group="inner-group"),
        step("outer-build", {"outer": pose(200)}, ["outer"], action="build_subassembly", group="outer-group"),
        step("inner-attach", {"outer": pose(200), "inner": pose(), "strip": pose(0, 8, 10)}, [],
             action="attach_subassembly", group="inner-group"),
        step("outer-attach", {"main": pose(), "outer": pose(200), "inner": pose(), "strip": pose(0, 8, 10)}, [],
             action="attach_subassembly", group="outer-group")])
    choices = [connection("inner-build", "strip", "inner", "socket:-10:-8:0", "stud:-10:0:10"),
               connection("inner-attach", "inner", "outer", "socket:-10:-8:-10", "stud:-30:0:-10",
                          group=["inner", "strip"]),
               connection("outer-attach", "outer", "main", "socket:-30:-8:-10", "stud:-10:0:-10",
                          group=["outer", "inner", "strip"])]
    roots = [("one", "main"), ("inner-build", "inner"), ("outer-build", "outer")]
    solved, report = run(raw, choices, roots)
    assert report["snapshots"][-1]["workspaces"] == {identity: "main" for identity in ["main", "inner", "strip", "outer"]}
    assert solved.steps[-1].poses["outer"].position_ldu == (20, 8, 0)
    assert solved.steps[-1].poses["inner"].position_ldu == (0, 16, 0)
    previous = solved.model_dump(mode="json")
    previous["steps"] = previous["steps"][:-1]
    draft = solved.model_dump(mode="json")
    draft["steps"][-1]["poses"] = {"main": pose(), **previous["steps"][-1]["poses"]}
    resumed, _ = run(SceneV2.model_validate(draft), choices[-1:], [], previous)
    assert resumed.model_dump(mode="json") == solved.model_dump(mode="json")


def test_arbitrary_old_piece_motion_and_historical_plans_rejected(nominal_catalogue):
    raw = scene({"base": "3022"}, [step("one", {"base": pose()}, ["base"]),
                                   step("two", {"base": pose(40)}, [])])
    with pytest.raises(SpatialError, match="Historical pieces moved"):
        run(raw, [], [("one", "base")])
    initial = raw.model_dump(mode="json")
    initial["steps"] = initial["steps"][:1]
    with pytest.raises(SpatialError, match="historical step"):
        run(raw, [], [("one", "base")], initial)


def test_connector_choice_rejects_noninteger_or_out_of_range_rotation():
    with pytest.raises(ValueError):
        connection(turn=1.5)
    with pytest.raises(ValueError):
        connection(turn=4)
