"""Exact compact proposal input; spatial omission requires explicit source scope."""
from __future__ import annotations

from copy import deepcopy
import itertools
import math

from ..core.models import SourcePanel
from ..releases.models import SceneV2, canonical, digest
from .connectors import transform_point
from .delta import MAX_CONTEXT_BYTES

VERSION = "source-local-assembly-context-v2"
PROMPT = """Decode physical_instances using inventory_fields plus inventory_defaults; pose is
[x,y,z,qx,qy,qz,qw] in LDU, null means withheld, not absent. Source rows use source_fields;
source_index indexes sources. Group members and snapshot inventory_indices index
physical_instances. Inventory is complete; poses are prior estimates, never verification.
Uncertain group membership forces full context; group rows then list known members only.
Full fallback retains all poses. Preserve IDs, origins and history; output SceneDelta.
"""


def rigid_groups(steps):
    """Replay declared workspaces, merging child members into one known receiver.

    This mirrors the solver's membership transfer without guessing a receiver
    from unverified contacts. Multiple visible receiving workspaces need geometry
    evidence unavailable here, so membership stays explicitly incomplete.
    """
    groups, detached, workspaces, ambiguous = {}, set(), {}, False
    for step in steps:
        group = step.get("assembly_group_id")
        introduced = set(step["introduced_instance_ids"])
        for identity in introduced:
            workspaces[identity] = "main"
        if step["action"] == "build_subassembly" and group:
            if group in groups and group not in detached:
                ambiguous = True  # Reusing an already attached group is not a new workspace.
            groups.setdefault(group, set()).update(introduced)
            detached.add(group)
            for identity in introduced:
                workspaces[identity] = "group:" + group
        elif step["action"] == "attach_subassembly" and group:
            members = groups.get(group, set())
            outside = set(step["visible_instance_ids"]) - members
            receiving = {workspaces.get(identity) for identity in outside}
            if (not members or not members <= set(step["visible_instance_ids"])
                    or group not in detached or len(receiving) != 1 or None in receiving
                    or "group:" + group in receiving or introduced):
                ambiguous = True
                # Future attachments must not mistake unresolved members for
                # either their old display workspace or a guessed receiver.
                for identity in members:
                    workspaces[identity] = None
                continue
            workspace = receiving.pop()
            for identity in members:
                workspaces[identity] = workspace
            if workspace.startswith("group:"):
                groups[workspace.removeprefix("group:")].update(members)
            detached.discard(group)
    return groups, detached, ambiguous


def complete_groups(identities, groups):
    selected = set(identities)
    while True:
        expanded = selected | set().union(*(members for members in groups.values() if members & selected))
        if expanded == selected:
            return selected
        selected = expanded


def _local_poses(parts, poses, groups, ambiguous, localization, source, connector_parts):
    if localization is None:
        return set(poses), "receiver_scope_not_established"
    if (type(localization) is not dict or set(localization) != {"source", "receiver_instance_ids"}
            or SourcePanel.model_validate(localization["source"]).model_dump(mode="json") != source):
        raise ValueError("Assembly localization must bind the exact requested source panel")
    ids = localization["receiver_instance_ids"]
    if (type(ids) is not list or not 1 <= len(ids) <= 64 or any(type(i) is not str for i in ids)
            or len(set(ids)) != len(ids) or not set(ids) <= set(poses)):
        raise ValueError("Assembly localization requires known distinct receiving instances")
    if ambiguous:
        return set(poses), "nested_group_membership_not_established"
    catalogue = {part["geometry_ref"]: part for part in connector_parts}
    if any(part["geometry_ref"] not in catalogue for part in parts.values()):
        return set(poses), "neighbour_geometry_not_supported"
    bounds = {}
    for identity, pose in poses.items():
        corners = catalogue[parts[identity]["geometry_ref"]].get("bounds_ldu")
        if (not isinstance(corners, (list, tuple)) or len(corners) != 2
                or any(len(point) != 3 or any(not math.isfinite(v) for v in point) for point in corners)
                or any(a > b for a, b in zip(*corners, strict=True))):
            raise ValueError("Invalid verified individual bounds for assembly context")
        world = [transform_point(pose, point) for point in itertools.product(*zip(*corners, strict=True))]
        bounds[identity] = ([min(p[i] for p in world) for i in range(3)],
                            [max(p[i] for p in world) for i in range(3)])
    seeds = complete_groups(ids, groups)
    selected = set(seeds)
    # One-hop broad-phase neighbours are context only, not contact/fit evidence.
    for identity, (low, high) in bounds.items():
        if any(all(low[i] <= bounds[seed][1][i] + 20 and high[i] >= bounds[seed][0][i] - 20
                   for i in range(3)) for seed in seeds):
            selected.add(identity)
    return complete_groups(selected, groups), None


def build_assembly_context(previous, *, source_hash, page_index, panel, findings=(),
                           localization=None, connector_parts=()):
    source = SourcePanel(source_sha256=source_hash, page_index=page_index,
                         bbox=panel["bbox"]).model_dump(mode="json")
    receipt = {"version": VERSION, "previous_scene_sha256": digest(previous) if previous else None,
               "source": source, "panel_sha256": digest(panel), "findings_sha256": digest(list(findings)),
               "localization": deepcopy(localization), "neighbour_margin_ldu": 20,
               "connector_parts_sha256": digest(list(connector_parts)) if localization else None,
               "scope": "Exact own-assembly input only; no source agreement or connection claim."}
    if previous is None:
        return {"context": None, "receipt": {**receipt, "context_sha256": digest(None),
            "context_bytes": 4, "inventory_count": 0, "pose_count": 0,
            "omitted_pose_ids": [], "fallback_reason": "no_prior_assembly"}}
    data = SceneV2.model_validate(previous).model_dump(mode="json")
    parts = {part["instance_id"]: part for part in data["instances"]}
    poses = {}
    for step in data["steps"]:
        poses.update(step["poses"])
    groups, detached, ambiguous = rigid_groups(data["steps"])
    selected, fallback = _local_poses(parts, poses, groups, ambiguous, localization, source, connector_parts)
    sources = {canonical(part["source"]): part["source"] for part in parts.values()}
    last = data["steps"][-1]
    sources[canonical(last["source"])] = last["source"]
    bindings = [sources[key] for key in sorted(sources)]
    source_index = {canonical(value): index for index, value in enumerate(bindings)}
    registry_index = {value["source_sha256"]: index for index, value in enumerate(data["sources"])}
    identities = sorted(parts)
    inventory_index = {identity: index for index, identity in enumerate(identities)}
    fields = ["instance_id", "part_id", "color_code", "geometry_ref"]
    defaults = {}
    for key in ("origin", "mapping_status"):
        values = {part[key] for part in parts.values()}
        if len(values) == 1:
            defaults[key] = values.pop()
        else:
            fields.append(key)
    last_snapshot = {key: value for key, value in last.items()
                     if key not in {"poses", "source", "introduced_instance_ids", "active_instance_ids", "visible_instance_ids"}}
    last_snapshot["source_binding"] = source_index[canonical(last["source"])]
    for role in ("introduced", "active", "visible"):
        last_snapshot[role + "_inventory_indices"] = [inventory_index[i] for i in last[role + "_instance_ids"]]
    context = {"encoding": VERSION, "sources": data["sources"], "sections": data["sections"],
        "inventory_fields": [*fields, "source_binding", "pose"], "inventory_defaults": defaults,
        "physical_instances": [[*(parts[i][key] for key in fields), source_index[canonical(parts[i]["source"])],
                                [*poses[i]["position_ldu"], *poses[i]["quaternion_xyzw"]] if i in selected else None]
                               for i in identities],
        "source_fields": ["source_index", "page_index", "bbox"],
        "source_bindings": [[registry_index[value["source_sha256"]], value["page_index"], value["bbox"]] for value in bindings],
        "rigid_group_fields": ["assembly_group_id", "known_member_inventory_indices", "detached"],
        "rigid_groups": [[group, sorted(inventory_index[i] for i in members), group in detached]
                         for group, members in sorted(groups.items())],
        "group_membership_complete": not ambiguous,
        "last_snapshot": last_snapshot,
        "pose_scope": {"mode": "full" if selected == set(poses) else "source_local",
                       "fallback_reason": fallback}}
    size = len(canonical(context))
    if size > MAX_CONTEXT_BYTES:
        raise ValueError("Compact assembly context exceeds the 400 KB proposal bound")
    return {"context": context, "receipt": {**receipt, "context_sha256": digest(context),
        "context_bytes": size, "inventory_count": len(parts), "pose_count": len(selected),
        "omitted_pose_ids": sorted(set(poses) - selected), "fallback_reason": fallback,
        "group_membership_complete": not ambiguous}}


def instruction_updates(candidate, previous):
    """Same-instruction repair input omits only exactly inherited pose values."""
    latest = {}
    for step in (previous or {}).get("steps", []):
        latest.update(step["poses"])
    result = []
    for step in candidate["steps"][len((previous or {}).get("steps", [])):]:
        updates = {identity: pose for identity, pose in step["poses"].items() if latest.get(identity) != pose}
        result.append({**deepcopy(step), "poses": deepcopy(updates)})
        latest.update(step["poses"])
    return result
