"""Bounded stud/socket mating solver, separate from image and physical checks.

The model names a supported connector pair and a discrete relative orientation.
Its floating point translations never decide the final contact pose. Free poses
are permitted only as initial/detached assembly gauges, with explicit roots.
"""
from __future__ import annotations

import itertools
import math
from collections import defaultdict
from pathlib import Path

from pydantic import Field

from ..core.models import Pose, StrictModel
from ..releases.models import SceneV2, digest
from .connectors import (MAX_COORDINATE_LDU, connector, load_connector_catalogue, rotation_matrix,
                         transform_point, transform_vector)


class ConnectionChoice(StrictModel):
    step_id: str = Field(min_length=1)
    moving_instance_id: str = Field(min_length=1, description="New physical piece, or anchor member of the prior detached group being attached")
    moving_connector_id: str = Field(min_length=1, description="Exact supported connector_id from this part's catalogue; no mesh/internal primitive IDs")
    target_instance_id: str = Field(min_length=1, description="Distinct visible, already anchored physical piece receiving the connection")
    target_connector_id: str = Field(min_length=1, description="Exact supported catalogue connector_id with opposite stud/socket polarity")
    quarter_turns: int = Field(ge=0, le=3, strict=True,
                              description="0, 1, 2, or 3 right-handed quarter turns about the TARGET connector outward normal")
    moving_group_ids: list[str] = Field(default_factory=list,
        description="[] for a single newly introduced part; full prior physical group IDs only for attach_subassembly")


class RootPlacement(StrictModel):
    step_id: str = Field(min_length=1)
    instance_id: str = Field(min_length=1,
        description="Exactly one new free root for the initial assembly or a new detached build_subassembly group; not a floating ordinary addition")


class SpatialError(ValueError):
    def __init__(self, message, *, step_id=None, code="unsupported_placement"):
        super().__init__(message)
        self.report = {"status": "fail", "code": code, "step_id": step_id,
                       "findings": [message], "physical_check": "not_run"}


def _product(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _transpose(matrix):
    return [list(row) for row in zip(*matrix)]


def _quaternion(matrix):
    # Robust conversion, including the 180-degree rotations used by connector frames.
    trace = sum(matrix[i][i] for i in range(3))
    if trace > 0:
        s = math.sqrt(trace + 1) * 2
        q = [(matrix[2][1]-matrix[1][2])/s, (matrix[0][2]-matrix[2][0])/s,
             (matrix[1][0]-matrix[0][1])/s, s/4]
    else:
        i = max(range(3), key=lambda index: matrix[index][index])
        j, k = (i+1) % 3, (i+2) % 3
        s = math.sqrt(max(0, 1+matrix[i][i]-matrix[j][j]-matrix[k][k])) * 2
        q = [0., 0., 0., (matrix[k][j]-matrix[j][k])/s]
        q[i], q[j], q[k] = s/4, (matrix[j][i]+matrix[i][j])/s, (matrix[k][i]+matrix[i][k])/s
    norm = math.sqrt(sum(v*v for v in q))
    sign = -1 if q[3] < 0 else 1
    return tuple(0. if abs(v) < 1e-12 else sign*v/norm for v in q)


def _frame(feature):
    x, y = feature["tangent"], feature["normal"]
    z = [x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0]]
    return _transpose([x, y, z])


def _same_pose(a, b, tolerance=1e-6):
    a, b = Pose.model_validate(a), Pose.model_validate(b)
    return (math.dist(a.position_ldu, b.position_ldu) <= tolerance
            and max(abs(x-y) for ar, br in zip(rotation_matrix(a.quaternion_xyzw),
                                               rotation_matrix(b.quaternion_xyzw))
                    for x, y in zip(ar, br)) <= tolerance)


def _mate_pose(target_pose, moving_connector, target_connector, quarter_turns):
    if moving_connector["kind"] == target_connector["kind"]:
        raise SpatialError("Only an explicit stud/socket pair can mate", code="incompatible_connectors")
    if (quarter_turns not in moving_connector["allowed_quarter_turns"]
            or quarter_turns not in target_connector["allowed_quarter_turns"]):
        raise SpatialError("Unsupported relative connector orientation")
    if moving_connector["engagement_ldu"] != target_connector["engagement_ldu"]:
        raise SpatialError("Unsupported connector engagement")
    angle = quarter_turns * math.pi / 2
    c, s = round(math.cos(angle)), round(math.sin(angle))
    turn = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    opposite = [[1, 0, 0], [0, -1, 0], [0, 0, -1]]
    target_rotation = rotation_matrix(target_pose.quaternion_xyzw)
    rotation = _product(_product(_product(_product(target_rotation, _frame(target_connector)), turn),
                                opposite), _transpose(_frame(moving_connector)))
    world_target = transform_point(target_pose, target_connector["position_ldu"])
    local_offset = transform_vector(rotation, moving_connector["position_ldu"])
    return Pose(position_ldu=[world_target[i]-local_offset[i] for i in range(3)],
                quaternion_xyzw=_quaternion(rotation))


def _rigid_move(poses, ids, anchor, desired):
    old = poses[anchor]
    rotation = _product(rotation_matrix(desired.quaternion_xyzw),
                        _transpose(rotation_matrix(old.quaternion_xyzw)))
    result = {}
    for identity in ids:
        pose = poses[identity]
        relative = [pose.position_ldu[i]-old.position_ldu[i] for i in range(3)]
        rotated = transform_vector(rotation, relative)
        result[identity] = Pose(position_ldu=[desired.position_ldu[i]+rotated[i] for i in range(3)],
                               quaternion_xyzw=_quaternion(_product(rotation, rotation_matrix(pose.quaternion_xyzw))))
    return result


def _contacts(poses, instances, catalogue, tolerance):
    """All nominal coincidences reserve both ends, including secondary contacts."""
    studs = defaultdict(list)
    sockets = []
    for identity, pose in poses.items():
        part = catalogue[instances[identity].geometry_ref]
        rotation = rotation_matrix(pose.quaternion_xyzw)
        for feature in part["connectors"]:
            point = transform_point(pose, feature["position_ldu"])
            normal = transform_vector(rotation, feature["normal"])
            value = (identity, feature["connector_id"], point, normal)
            if feature["kind"] == "stud":
                studs[tuple(math.floor(v/tolerance) for v in point)].append(value)
            else:
                sockets.append(value)
    contacts, occupied = [], defaultdict(set)
    for identity, feature_id, point, normal in sockets:
        cell = [math.floor(v/tolerance) for v in point]
        for offsets in itertools.product((-1, 0, 1), repeat=3):
            for other, other_id, other_point, other_normal in studs.get(tuple(cell[i]+offsets[i] for i in range(3)), []):
                if (identity == other or math.dist(point, other_point) > tolerance
                        or sum(normal[i]*other_normal[i] for i in range(3)) > -1 + 1e-6):
                    continue
                socket_key, stud_key = (identity, feature_id), (other, other_id)
                occupied[socket_key].add(stud_key)
                occupied[stud_key].add(socket_key)
                contacts.append({"socket": list(socket_key), "stud": list(stud_key),
                                 "distance_ldu": math.dist(point, other_point)})
    if any(len(mates) > 1 for mates in occupied.values()):
        raise SpatialError("Connector occupancy conflict: one mating feature is shared by multiple pieces",
                           code="occupied_connector")
    return contacts


def _broad_phase(poses, instances, catalogue, tolerance):
    bounds = {}
    for identity, pose in poses.items():
        lo, hi = catalogue[instances[identity].geometry_ref]["bounds_ldu"]
        corners = [transform_point(pose, point) for point in itertools.product(*zip(lo, hi))]
        bounds[identity] = ([min(p[i] for p in corners) for i in range(3)],
                            [max(p[i] for p in corners) for i in range(3)])
    candidates = []
    for a, b in itertools.combinations(poses, 2):
        if instances[a].geometry_ref == instances[b].geometry_ref and _same_pose(poses[a], poses[b]):
            raise SpatialError("Two physical instances occupy the same individual-part pose",
                               code="duplicate_geometry_pose")
        alo, ahi = bounds[a]
        blo, bhi = bounds[b]
        if all(min(ahi[i], bhi[i])-max(alo[i], blo[i]) > tolerance for i in range(3)):
            candidates.append([a, b])
    return candidates


def _bounded_poses(poses, step_id):
    if any(abs(value) > MAX_COORDINATE_LDU for pose in poses.values() for value in pose.position_ldu):
        raise SpatialError("Pose coordinates exceed the supported 1000000 LDU bound", step_id=step_id,
                           code="coordinate_limit")


def _workspace_checks(poses, workspaces, instances, catalogue, tolerance):
    """Visibility never frees a contact; unattached callouts have separate gauges."""
    partitions = defaultdict(dict)
    for identity, pose in poses.items():
        partitions[workspaces[identity]][identity] = pose
    contacts, overlaps = [], []
    for workspace, physical in partitions.items():
        contacts.extend({**contact, "workspace": workspace}
                        for contact in _contacts(physical, instances, catalogue, tolerance))
        overlaps.extend(_broad_phase(physical, instances, catalogue, tolerance))
    return contacts, overlaps


def solve_candidate(scene: SceneV2, previous: dict | None, connections: list[ConnectionChoice],
                    roots: list[RootPlacement], geometry_root: Path) -> tuple[SceneV2, dict]:
    """Return an independent corrected candidate and a scoped, reproducible audit.

    A connection error is fail-closed. Broad-phase overlap candidates are retained
    for image/narrow-phase review and are never promoted to a collision pass.
    """
    scene = SceneV2.model_validate(scene)
    raw = scene.model_dump(mode="json")
    result = scene.model_copy(deep=True)
    for step in scene.steps:
        _bounded_poses(step.poses, step.step_id)
    previous_scene = SceneV2.model_validate(previous) if previous is not None else None
    prefix = len(previous_scene.steps) if previous_scene else 0
    if previous_scene:
        old = previous_scene.model_dump(mode="json")
        if (raw["steps"][:prefix] != old["steps"] or raw["instances"][:len(old["instances"])] != old["instances"]
                or any(raw[key] != old[key] for key in ("set_number", "guide_id", "source_sha256", "coordinate_system"))):
            raise SpatialError("Accepted candidate prefix is immutable", code="prefix_modified")
    metadata, catalogue = load_connector_catalogue(geometry_root, {part.geometry_ref for part in scene.instances})
    limits, tolerance = metadata["limits"], metadata["tolerance_ldu"]
    if (len(scene.instances) > limits["max_instances"] or len(scene.steps) > limits["max_steps"]
            or len(connections) > limits["max_connections"] or len(roots) > limits["max_instances"]):
        raise SpatialError("Spatial solve exceeds configured bounds", code="resource_limit")
    instances = {part.instance_id: part for part in scene.instances}
    if any(part.geometry_ref != f"parts/{part.part_id}.dat" for part in scene.instances):
        raise SpatialError("Part identity differs from its connector geometry")
    connections = [ConnectionChoice.model_validate(choice) for choice in connections]
    roots = [RootPlacement.model_validate(root) for root in roots]
    new_steps = {step.step_id for step in scene.steps[prefix:]}
    if any(choice.step_id not in new_steps for choice in [*connections, *roots]):
        raise SpatialError("Connection/root plan refers to an unknown or historical step")
    if len({(root.step_id, root.instance_id) for root in roots}) != len(roots):
        raise SpatialError("Duplicate root placement")
    latest, raw_latest, groups, attached, workspaces = {}, {}, {}, set(), {}
    for step in scene.steps[:prefix]:
        if step.action not in {"build_subassembly", "attach_subassembly"} and step.introduced_instance_ids:
            new_ids = set(step.introduced_instance_ids)
            detached_spaces = {workspaces[identity] for identity in step.poses
                               if identity in workspaces and workspaces[identity].startswith("group:")}
            for workspace in detached_spaces:
                members = {identity for identity in step.poses if workspaces.get(identity) == workspace}
                contacts = _contacts({identity: step.poses[identity] for identity in members | new_ids},
                                     instances, catalogue, tolerance)
                if any((contact["stud"][0] in new_ids) != (contact["socket"][0] in new_ids)
                       for contact in contacts):
                    raise SpatialError("Historical addition to a detached group requires build_subassembly membership",
                                       step_id=step.step_id, code="invalid_rigid_group")
        latest.update(step.poses)
        raw_latest.update(step.poses)
        for identity in step.introduced_instance_ids:
            workspaces[identity] = "main"
        if step.action == "build_subassembly" and step.assembly_group_id:
            groups.setdefault(step.assembly_group_id, set()).update(step.introduced_instance_ids)
            for identity in step.introduced_instance_ids:
                workspaces[identity] = "group:" + step.assembly_group_id
        if step.action == "attach_subassembly" and step.assembly_group_id:
            group_id = step.assembly_group_id
            members = groups.get(group_id, set())
            if not members or not members <= set(step.poses):
                raise SpatialError("Historical attachment lacks its complete group", step_id=step.step_id)
            # The accepted snapshot retains exact mating poses. Recover the target
            # workspace through its visible contacts, not through arbitrary display
            # gauge overlap with a different hidden detached group.
            possibilities = set()
            other_spaces = {workspaces[identity] for identity in step.poses if identity not in members}
            for workspace in other_spaces:
                outside = {identity for identity in step.poses
                           if identity not in members and workspaces[identity] == workspace}
                contacts = _contacts({identity: step.poses[identity] for identity in members | outside},
                                     instances, catalogue, tolerance)
                if any((contact["stud"][0] in members) != (contact["socket"][0] in members)
                       for contact in contacts):
                    possibilities.add(workspace)
            if len(possibilities) != 1:
                raise SpatialError("Historical attachment workspace is missing or ambiguous", step_id=step.step_id)
            workspace = possibilities.pop()
            for identity in members:
                workspaces[identity] = workspace
            if workspace.startswith("group:"):
                groups[workspace.removeprefix("group:")].update(members)
            attached.add(group_id)
    corrections, receipts, root_receipts, snapshots = [], [], [], []
    for step in result.steps[prefix:]:
        raw_poses = dict(step.poses)
        visible, new = set(step.visible_instance_ids), set(step.introduced_instance_ids)
        old_ids = visible - new
        if not old_ids <= set(latest):
            raise SpatialError("Missing prior pose for an existing instance", step_id=step.step_id)
        poses = {identity: latest[identity] for identity in old_ids}
        # Move an existing target group before placing any new pieces onto it;
        # provider list order must not leave those pieces at the old display gauge.
        pending = sorted((choice for choice in connections if choice.step_id == step.step_id),
                         key=lambda choice: not bool(choice.moving_group_ids))
        step_roots = [root for root in roots if root.step_id == step.step_id]
        group_id = step.assembly_group_id
        if step.action == "build_subassembly":
            if not group_id or group_id in attached:
                raise SpatialError("Detached construction requires a distinct un-attached assembly group", step_id=step.step_id)
            prior_members = groups.get(group_id, set())
            allowed_root = not prior_members
            groups.setdefault(group_id, set()).update(new)
        else:
            allowed_root = not latest
        if step_roots and (len(step_roots) != 1 or not allowed_root):
            raise SpatialError("Only one initial root or new detached build_subassembly root is allowed", step_id=step.step_id)
        if allowed_root and new and len(step_roots) != 1:
            raise SpatialError("Initial or detached assembly needs one explicit root", step_id=step.step_id)
        for root in step_roots:
            if root.instance_id not in new:
                raise SpatialError("A free root must be a newly introduced physical instance", step_id=step.step_id)
            poses[root.instance_id] = raw_poses[root.instance_id]
            workspaces[root.instance_id] = "group:" + group_id if step.action == "build_subassembly" else "main"
            root_receipts.append({**root.model_dump(), "scope": "free assembly gauge, not inferred attachment"})
        moved_old = {identity for identity in old_ids if not _same_pose(raw_poses[identity], raw_latest[identity])}
        moved_by_group, completed = set(), set()
        while pending:
            progressed = False
            for choice in list(pending):
                moving, target = choice.moving_instance_id, choice.target_instance_id
                if moving == target or moving not in visible or target not in visible:
                    raise SpatialError("Connector pair needs two distinct visible instances", step_id=step.step_id)
                if target not in poses:
                    continue
                members = set(choice.moving_group_ids)
                if len(members) != len(choice.moving_group_ids):
                    raise SpatialError("Duplicate rigid group member", step_id=step.step_id)
                if members:
                    if (step.action != "attach_subassembly" or not group_id or group_id in attached
                            or members != groups.get(group_id) or moving not in members or target in members
                            or not members <= old_ids or moved_by_group):
                        raise SpatialError("Attachment must move the complete declared detached group exactly once",
                                           step_id=step.step_id, code="invalid_rigid_group")
                    if not members <= set(poses):
                        raise SpatialError("Detached group pose is unavailable", step_id=step.step_id)
                    expected_raw = _rigid_move(raw_latest, members, moving, raw_poses[moving])
                    if any(not _same_pose(raw_poses[identity], expected_raw[identity], tolerance) for identity in members):
                        raise SpatialError("Proposed group motion is not rigid; partial or distorted movement rejected",
                                           step_id=step.step_id, code="nonrigid_group")
                elif moving not in new:
                    raise SpatialError("Moving an existing piece requires its complete detached subassembly",
                                       step_id=step.step_id, code="arbitrary_history_motion")
                elif step.action != "build_subassembly" and workspaces[target].startswith("group:"):
                    raise SpatialError("Adding to a detached group requires build_subassembly and its assembly_group_id",
                                       step_id=step.step_id)
                if moving in completed or moving in {root.instance_id for root in step_roots}:
                    raise SpatialError("Each moving piece has one placement anchor", step_id=step.step_id)
                if step.action == "build_subassembly" and (moving not in groups[group_id] or target not in groups[group_id]):
                    raise SpatialError("Detached build connection crosses into another assembly", step_id=step.step_id)
                moving_feature = connector(catalogue[instances[moving].geometry_ref], choice.moving_connector_id)
                target_feature = connector(catalogue[instances[target].geometry_ref], choice.target_connector_id)
                desired = _mate_pose(poses[target], moving_feature, target_feature, choice.quarter_turns)
                if members:
                    poses.update(_rigid_move(poses, members, moving, desired))
                    moved_by_group.update(members)
                    attached.add(group_id)
                    workspace = workspaces[target]
                    for identity in members:
                        workspaces[identity] = workspace
                    if workspace.startswith("group:"):
                        groups[workspace.removeprefix("group:")].update(members)
                else:
                    poses[moving] = desired
                    workspaces[moving] = workspaces[target]
                _bounded_poses(poses, step.step_id)
                completed.add(moving)
                receipts.append({**choice.model_dump(), "moving_world": transform_point(poses[moving], moving_feature["position_ldu"]),
                                 "target_world": transform_point(poses[target], target_feature["position_ldu"]),
                                 "scope": "nominal mating frames with opposing normals and prescribed engagement"})
                pending.remove(choice)
                progressed = True
            if not progressed:
                raise SpatialError("Connection plan is cyclic or has no anchored target", step_id=step.step_id)
        if moved_old - moved_by_group:
            raise SpatialError("Historical pieces moved without a complete rigid attachment", step_id=step.step_id,
                               code="arbitrary_history_motion")
        if set(poses) != visible:
            raise SpatialError("Every new piece needs a supported connection or permitted root: "
                               + ", ".join(sorted(visible-set(poses))), step_id=step.step_id, code="floating_instance")
        if step.action == "attach_subassembly" and not moved_by_group:
            raise SpatialError("An attachment instruction needs an explicit complete-group connection", step_id=step.step_id)
        nominal, overlap_candidates = _workspace_checks(latest | poses, workspaces, instances, catalogue, tolerance)
        for identity, pose in poses.items():
            if not _same_pose(raw_poses[identity], pose):
                corrections.append({"step_id": step.step_id, "instance_id": identity,
                                    "before": raw_poses[identity].model_dump(mode="json"),
                                    "after": pose.model_dump(mode="json"),
                                    "reason": "connector solve or inheritance from a solved prior snapshot"})
        step.poses = poses
        latest.update(poses)
        raw_latest.update(raw_poses)
        snapshots.append({"step_id": step.step_id, "nominal_contacts": nominal,
                          "aabb_overlap_candidates": overlap_candidates,
                          "physical_instance_count": len(latest), "visible_instance_count": len(poses),
                          "workspaces": dict(workspaces),
                          "geometry_status": "needs_review" if overlap_candidates else "broad_phase_clear",
                          "narrow_phase": "not_run"})
    result = SceneV2.model_validate(result.model_dump(mode="json"))
    return result, {"status": "pass", "scope": "bounded nominal stud/socket placement and rigid-group invariants only",
                    "input_scene_sha256": digest(scene), "output_scene_sha256": digest(result),
                    "metadata_status": metadata["metadata_status"], "tolerance_ldu": tolerance,
                    "metadata_sha256": digest(metadata),
                    "geometry_pins": {ref: part["closure_sha256"] for ref, part in catalogue.items()},
                    "connector_check": "supported_mating_frames_pass", "geometry_check": "broad_phase_only",
                    "physical_check": "not_run", "corrections": corrections, "correction_count": len(corrections),
                    "roots": root_receipts, "connections": receipts, "snapshots": snapshots,
                    "limitations": ["Metadata is agent-derived from pinned individual geometry, awaiting independent review.",
                                    "AABB overlaps include intended contacts; narrow-phase intersections are not tested.",
                                    "Image agreement, hidden contacts, placement path and physical strength remain separate checks."]}
