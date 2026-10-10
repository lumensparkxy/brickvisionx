"""Exact input compaction and conservative scope on original synthetic assemblies."""
from copy import deepcopy

import pytest

from guide2build.engine import assembly_context as contexts
from guide2build.engine.delta import current_context
from guide2build.releases.models import canonical, digest
from test_engine_spatial import SOURCE, group_scene, pose, scene, step

PANEL = {"bbox": [0, 0, 1, 1], "number": 1, "kind": "main", "label": "Synthetic"}


def build(previous, **kwargs):
    return contexts.build_assembly_context(previous, source_hash=SOURCE["source_sha256"],
        page_index=0, panel=PANEL, **kwargs)


def unpack(packed):
    """Independent reader exercises the documented table indirection contract."""
    inventory, poses = [], {}
    for row in packed["physical_instances"]:
        instance = {**packed["inventory_defaults"], **dict(zip(packed["inventory_fields"], row, strict=True))}
        source = dict(zip(packed["source_fields"], packed["source_bindings"][instance.pop("source_binding")], strict=True))
        source["source_sha256"] = packed["sources"][source.pop("source_index")]["source_sha256"]
        instance["source"] = source
        value = instance.pop("pose")
        if value is not None:
            poses[instance["instance_id"]] = {"position_ldu": value[:3], "quaternion_xyzw": value[3:]}
        inventory.append(instance)
    snapshot = deepcopy(packed["last_snapshot"])
    for role in ("introduced", "active", "visible"):
        snapshot[role + "_instance_ids"] = [inventory[i]["instance_id"] for i in snapshot.pop(role + "_inventory_indices")]
    source = dict(zip(packed["source_fields"], packed["source_bindings"][snapshot.pop("source_binding")], strict=True))
    snapshot["source"] = {"source_sha256": packed["sources"][source.pop("source_index")]["source_sha256"], **source}
    groups = {row[0]: {inventory[i]["instance_id"] for i in row[1]} for row in packed["rigid_groups"]}
    return inventory, poses, snapshot, groups


def nested_scene(*, ambiguous=False):
    """The existing spatial nested fixture, with an optional second receiver workspace."""
    value = scene({"main": "3022", "inner": "3022", "strip": "3710", "outer": "3020"}, [
        step("one", {"main": pose()}, ["main"]),
        step("inner-build", {"inner": pose(), "strip": pose(0, 8, 10)}, ["inner", "strip"],
             action="build_subassembly", group="inner-group"),
        step("outer-build", {"outer": pose(200)}, ["outer"], action="build_subassembly", group="outer-group"),
        step("inner-attach", {**({"main": pose()} if ambiguous else {}),
                             "outer": pose(200), "inner": pose(), "strip": pose(0, 8, 10)}, [],
             action="attach_subassembly", group="inner-group"),
        step("outer-attach", {"main": pose(), "outer": pose(200), "inner": pose(), "strip": pose(0, 8, 10)}, [],
             action="attach_subassembly", group="outer-group")])
    return value.model_dump(mode="json")


def test_nested_members_transfer_to_receiving_group_before_outer_attachment():
    data = nested_scene()
    before = digest(data)
    groups, detached, ambiguous = contexts.rigid_groups(data["steps"][:-1])
    assert groups == {"inner-group": {"inner", "strip"}, "outer-group": {"outer", "inner", "strip"}}
    assert detached == {"outer-group"} and ambiguous is False
    context = build(data)["context"]
    assert unpack(context)[3] == groups
    assert context["group_membership_complete"] is True
    assert contexts.complete_groups({"outer"}, groups) == {"outer", "inner", "strip"}
    assert contexts.rigid_groups(data["steps"])[1:] == (set(), False)
    assert digest(data) == before


@pytest.mark.parametrize("unavailable", ["multiple_workspaces", "hidden_child_member", "missing_receiver"])
def test_uncertain_nested_membership_is_visible_and_forces_full_pose_context(unavailable):
    data = nested_scene(ambiguous=unavailable == "multiple_workspaces")
    if unavailable == "hidden_child_member":
        attached = data["steps"][3]
        for key in ("visible_instance_ids", "active_instance_ids"):
            attached[key].remove("strip")
        del attached["poses"]["strip"]
    elif unavailable == "missing_receiver":
        attached = data["steps"][3]
        for key in ("visible_instance_ids", "active_instance_ids"):
            attached[key].remove("outer")
        del attached["poses"]["outer"]
    result = build(data, localization={"source": SOURCE, "receiver_instance_ids": ["outer"]})
    assert result["context"]["group_membership_complete"] is False
    assert result["receipt"]["group_membership_complete"] is False
    assert "complete_member_inventory_indices" not in result["context"]["rigid_group_fields"]
    assert result["receipt"]["fallback_reason"] == "nested_group_membership_not_established"
    assert result["receipt"]["pose_count"] == len(data["instances"])
    assert result["receipt"]["omitted_pose_ids"] == []


def test_full_fallback_packs_exact_inventory_poses_sources_and_origins():
    value = scene({f"part-{i:03d}": "3022" for i in range(80)}, [step("one",
        {f"part-{i:03d}": pose(i*20, i%3*8, -i*20) for i in range(80)},
        [f"part-{i:03d}" for i in range(80)])]).model_dump(mode="json")
    before = digest(value)
    result = build(value)
    packed = result["context"]
    inventory, poses, snapshot, _ = unpack(packed)
    assert poses == value["steps"][-1]["poses"]
    assert len(inventory) == len(value["instances"]) == 80
    assert inventory == value["instances"]
    assert snapshot == {key: val for key, val in value["steps"][-1].items() if key != "poses"}
    assert result["receipt"]["fallback_reason"] == "receiver_scope_not_established"
    assert result["receipt"]["omitted_pose_ids"] == []
    assert len(canonical(packed)) + len(contexts.PROMPT.encode()) < .60 * len(canonical(current_context(value)))
    assert result["receipt"]["context_sha256"] == digest(packed) and digest(value) == before
    assert build(value) == result


def test_explicit_scope_keeps_complete_group_and_actual_bound_neighbours():
    value, _, _ = group_scene()
    data = value.model_dump(mode="json")
    connector_parts = [{"geometry_ref": f"parts/{part}.dat", "bounds_ldu": [[-10, -8, -10], [10, 0, 10]]}
                       for part in ("3022", "3020", "3710")]
    source = {"source": SOURCE, "receiver_instance_ids": ["callout"]}
    result = build(data, localization=source, connector_parts=connector_parts)
    assert set(unpack(result["context"])[1]) == {"callout", "strip"}
    assert result["receipt"]["omitted_pose_ids"] == ["main"]
    assert len(result["context"]["physical_instances"]) == 3
    # Nearby geometry is included without asserting it is connected.
    data["steps"][-1]["poses"]["main"] = pose(220)
    result = build(data, localization=source, connector_parts=connector_parts)
    assert result["receipt"]["pose_count"] == 3


def test_small_mixed_inventory_keeps_each_source_and_origin_without_repeated_identity():
    ids = [f"synthetic-stable-instance-{i}" for i in range(8)]
    data = scene(dict.fromkeys(ids, "3022"), [step("first", {i: pose(n * 20) for n, i in enumerate(ids)}, ids)]).model_dump(mode="json")
    # Several independently observed crops and two origins must survive packing.
    for number, instance in enumerate(data["instances"]):
        instance["source"]["bbox"] = [number / 16, 0, (number + 1) / 16, .25]
    data["instances"][0]["origin"] = "pdf_assisted_authoring"
    context = build(data)["context"]
    inventory, poses, snapshot, _ = unpack(context)
    assert inventory == data["instances"] and poses == data["steps"][0]["poses"]
    assert snapshot["visible_instance_ids"] == ids
    assert "origin" not in context["inventory_defaults"]
    assert all(canonical(context).count(identity.encode()) == 1 for identity in ids)
    assert len(canonical(context)) + len(contexts.PROMPT.encode()) < len(canonical(current_context(data)))


def test_localization_never_guesses_missing_geometry_or_source_scope():
    raw, _, _ = group_scene()
    data = raw.model_dump(mode="json")
    localization = {"source": SOURCE, "receiver_instance_ids": ["callout"]}
    result = build(data, localization=localization)
    assert result["receipt"]["fallback_reason"] == "neighbour_geometry_not_supported"
    assert result["receipt"]["pose_count"] == 3
    invalid = deepcopy(localization)
    invalid["source"]["source_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="exact requested source"):
        build(data, localization=invalid)
    with pytest.raises(ValueError, match="known distinct"):
        build(data, localization={"source": SOURCE, "receiver_instance_ids": ["invented"]})


def test_compact_same_instruction_updates_replay_exact_poses_and_rigid_group():
    raw, _, _ = group_scene()
    data = raw.model_dump(mode="json")
    previous = deepcopy(data)
    previous["steps"] = data["steps"][:1]
    previous["instances"] = data["instances"][:1]
    updates = contexts.instruction_updates(data, previous)
    latest = deepcopy(previous["steps"][0]["poses"])
    for original, compact in zip(data["steps"][1:], updates, strict=True):
        latest.update(compact["poses"])
        assert {i: latest[i] for i in compact["visible_instance_ids"]} == original["poses"]
        assert compact["assembly_group_id"] == original["assembly_group_id"]
    assert updates[-1]["poses"] == {}
    updates[0]["poses"]["callout"]["position_ldu"][0] = 999
    assert data["steps"][1]["poses"]["callout"]["position_ldu"][0] == 200


def test_context_resource_bound_and_empty_start_are_explicit(monkeypatch):
    assert build(None)["receipt"]["fallback_reason"] == "no_prior_assembly"
    raw, _, _ = group_scene()
    monkeypatch.setattr(contexts, "MAX_CONTEXT_BYTES", 10)
    with pytest.raises(ValueError, match="400 KB"):
        build(raw.model_dump(mode="json"))
