"""Bounded alternatives and diagnostic checks; never a global assembly certificate.

Only source-supported connector/identity alternatives are expanded. The original
proposal remains available, including when supported metadata cannot solve it.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import heapq
import itertools
import math
from pathlib import Path
from typing import Annotated

from pydantic import Field, model_validator

from ..core.models import Pose, SourcePanel, StrictModel
from ..releases.models import SceneV2, digest
from .connectors import connector, load_connector_catalogue, rotation_matrix, transform_point, transform_vector
from .diagnostic_reuse import current_diagnostic_reuse, diagnostic_reuse_scope
from .source_view import SourceViewObservation, fit_source_view
from .spatial import ConnectionChoice, RootPlacement, SpatialError, _mate_pose, _rigid_move, _same_pose, solve_candidate
from .whole_part_symmetry import IDENTITY, relative_axis_rotation, verified_origin_symmetries
from .verification_cache import catalogue_verification_scope

VERSION = "bounded-source-hypotheses-v2"
MAX_DIAGNOSTIC_POSES = 512
MAX_SYMMETRY_PAIRS = 512
MAX_SYMMETRY_DESIGNS = 16


def _unsupported_metadata(error):
    # Unsupported design coverage is a quality limitation. Hash, path,
    # classification, resource and metadata-version errors are integrity errors.
    return str(error) == "Unsupported connector metadata" or str(error).startswith("Unsupported connector metadata: ")


class PlacementHint(StrictModel):
    step_id: str = Field(min_length=1, max_length=160)
    moving_instance_id: str = Field(min_length=1, max_length=160)
    target_instance_ids: list[str] = Field(min_length=1, max_length=8)
    moving_connector_ids: list[str] = Field(default_factory=list, max_length=8)
    target_connector_ids: list[str] = Field(default_factory=list, max_length=16)
    quarter_turns: list[Annotated[int, Field(strict=True)]] = Field(default_factory=lambda: [0, 1, 2, 3], min_length=1, max_length=4)
    moving_group_ids: list[str] = Field(default_factory=list, max_length=256)
    source: SourcePanel

    @model_validator(mode="after")
    def distinct(self):
        for values in (self.target_instance_ids, self.moving_connector_ids, self.target_connector_ids,
                       self.quarter_turns, self.moving_group_ids):
            if len(set(values)) != len(values):
                raise ValueError("Duplicate placement alternatives")
        if any(type(turn) is not int or not 0 <= turn <= 3 for turn in self.quarter_turns):
            raise ValueError("Only explicit orthogonal connector orientations are supported")
        if self.moving_instance_id in self.target_instance_ids:
            raise ValueError("A placement target must be a different physical instance")
        return self


def pose_key(pose):
    """Canonical transform key: q and -q describe one rotation, not alternatives."""
    pose = Pose.model_validate(pose)
    return tuple(round(v, 6) for v in pose.position_ldu) + tuple(
        round(value, 6) for row in rotation_matrix(pose.quaternion_xyzw) for value in row)


def _finding(code, step_id, identities, message, severity="review", **details):
    return {"code": code, "severity": severity, "step_id": step_id,
            "instance_ids": sorted(identities), "message": message, **details}


class _DiagnosticFindings:
    """Count all computed findings, but bound memory and preserve serious ones."""

    def __init__(self):
        self.records = defaultdict(list)
        self.counts = defaultdict(int)
        self.severities = defaultdict(int)

    def append(self, finding):
        self.counts[finding["code"]] += 1
        self.severities[finding["severity"]] += 1
        bucket = self.records[finding["severity"]]
        if len(bucket) < 512:
            bucket.append(finding)

    def __len__(self):
        return sum(self.counts.values())

    def retained(self, limit):
        return [finding for severity in ("error", "unsupported", "review")
                for finding in self.records[severity]][:limit]


def _diagnostic_contacts(poses, instances, catalogue, tolerance):
    """Keep nominal coincidences and localize occupancy without approving mates.

    Strict spatial._contacts deliberately rejects the whole solve on occupancy.
    Diagnostics must not turn that local conflict into an empty graph and infer
    that every other piece is floating. The same distance/opposing-normal rules
    are used here; multiply-mated endpoints and their edges remain explicit.
    """
    studs, sockets = defaultdict(list), []
    for identity in sorted(poses):
        pose = poses[identity]
        rotation = rotation_matrix(pose.quaternion_xyzw)
        for feature in catalogue[instances[identity].geometry_ref]["connectors"]:
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
            for other, other_id, other_point, other_normal in studs.get(
                    tuple(cell[i]+offsets[i] for i in range(3)), []):
                distance = math.dist(point, other_point)
                if (identity == other or distance > tolerance
                        or sum(normal[i]*other_normal[i] for i in range(3)) > -1+1e-6):
                    continue
                socket_key, stud_key = (identity, feature_id), (other, other_id)
                occupied[socket_key].add(stud_key)
                occupied[stud_key].add(socket_key)
                contacts.append({"socket": list(socket_key), "stud": list(stud_key), "distance_ldu": distance})
    conflicts = [{"feature": list(feature), "nominal_mates": [list(mate) for mate in sorted(mates)],
        "instance_ids": sorted({feature[0]} | {mate[0] for mate in mates})}
        for feature, mates in sorted(occupied.items()) if len(mates) > 1]
    conflicted = {tuple(item["feature"]) for item in conflicts}
    for contact in contacts:
        contact["occupancy"] = "conflicted" if (
            tuple(contact["socket"]) in conflicted or tuple(contact["stud"]) in conflicted) else "single_mate"
    contacts.sort(key=lambda item: (item["socket"], item["stud"]))
    return contacts, conflicts


def diagnose_candidate(scene, previous, geometry_root: Path, *, checked_step_ids=None):
    """Diagnose exact duplicates/history and the supported nominal connector scope.

    Floating and gap reports are made only inside fully supported workspaces.
    Bounding overlaps are candidates, including valid stud engagement, not collisions.
    """
    scene = SceneV2.model_validate(scene)
    all_step_ids = {step.step_id for step in scene.steps}
    if checked_step_ids is None:
        selected_steps = all_step_ids
    else:
        requested = list(checked_step_ids)
        if (len(requested) > 64 or len(set(requested)) != len(requested)
                or not set(requested) <= all_step_ids):
            raise ValueError("Invalid diagnostic snapshot scope (maximum 64 known distinct snapshots)")
        selected_steps = set(requested)
    findings, checks = _DiagnosticFindings(), {"exact_coincident_geometry": "checked", "historical_movement": "checked",
                           "rigid_groups": "checked", "supported_connectors": "not_run",
                           "symmetric_coincident_geometry": "checked_finite_scope",
                           "geometry": "broad_phase_only", "narrow_phase": "not_run", "physical": "not_run"}
    parts = {p.instance_id: p for p in scene.instances}
    old = None
    if previous:
        old = SceneV2.model_validate(previous)
        if scene.model_dump(mode="json")["steps"][:len(old.steps)] != old.model_dump(mode="json")["steps"]:
            findings.append(_finding("historical_movement", None, [], "Accepted snapshot history changed.", "error"))
    catalogue, metadata = {}, None
    try:
        metadata, available = load_connector_catalogue(Path(geometry_root))
        catalogue = {ref: part for ref, part in available.items() if ref in {p.geometry_ref for p in scene.instances}}
        checks["supported_connectors"] = "checked_scoped"
    except ValueError as error:
        if not _unsupported_metadata(error):
            raise
        findings.append(_finding("unsupported_connector_geometry", None, [], str(error)[:1000], "unsupported"))
    unsupported = {p.instance_id for p in scene.instances if p.geometry_ref not in catalogue}
    if unsupported:
        findings.append(_finding("unsupported_connector_geometry", None, unsupported,
                                 "No verified nominal connector metadata for these physical designs.", "unsupported"))
    tolerance = metadata["tolerance_ldu"] if metadata else .05
    latest, groups, workspace, roots = {}, defaultdict(set), {}, {}
    snapshots, symmetry_cache, symmetry_pairs, symmetry_considered = [], {}, 0, 0
    symmetry_omitted = 0
    reuse = current_diagnostic_reuse()
    prefix_count = len(old.steps) if old else 0
    key = reuse.binding(scene, old, geometry_root, metadata, catalogue, selected_steps,
        [MAX_DIAGNOSTIC_POSES, MAX_SYMMETRY_PAIRS, MAX_SYMMETRY_DESIGNS]) if reuse else None
    retained = reuse.restore(key, prefix_count) if reuse else None
    start = prefix_count if retained is not None else 0
    if retained is not None:
        (findings, checks, latest, groups, workspace, roots, snapshots, symmetry_cache,
         symmetry_pairs, symmetry_considered, symmetry_omitted) = retained
    for ordinal, step in enumerate(scene.steps[start:], start):
        if reuse and key and ordinal == prefix_count and retained is None:
            reuse.capture(key, (findings, checks, latest, groups, workspace, roots, snapshots, symmetry_cache,
                               symmetry_pairs, symmetry_considered, symmetry_omitted))
        new = set(step.introduced_instance_ids)
        for identity in step.introduced_instance_ids:
            space = "group:" + step.assembly_group_id if step.action == "build_subassembly" and step.assembly_group_id else "main"
            workspace[identity] = space
            roots.setdefault(space, identity)
        if step.action == "build_subassembly" and step.assembly_group_id:
            groups[step.assembly_group_id].update(new)
        moved = {identity for identity, pose in step.poses.items()
                 if identity in latest and not _same_pose(pose, latest[identity])}
        permitted = set()
        if step.action == "attach_subassembly" and step.assembly_group_id:
            members = groups[step.assembly_group_id]
            if members and members <= set(step.poses) and members <= set(latest):
                anchor = sorted(members)[0]
                expected = _rigid_move(latest, members, anchor, step.poses[anchor])
                if any(not _same_pose(expected[i], step.poses[i], tolerance) for i in members):
                    findings.append(_finding("nonrigid_group", step.step_id, members,
                                             "Attachment distorts internal part transforms.", "error"))
                permitted = members
                # Infer the target workspace from actual supported contact, never a display offset.
                targets = set()
                combined = latest | step.poses
                other_spaces = {workspace[i] for i in step.poses if i not in members and i in workspace}
                if len(other_spaces) == 1:
                    # Source-visible receiving workspace is unambiguous; no need
                    # to inspect every historical contact merely to name it.
                    targets = other_spaces
                elif step.step_id in selected_steps and len(combined) <= MAX_DIAGNOSTIC_POSES:
                    supported = {i: pose for i, pose in combined.items() if i not in unsupported}
                    contacts, _ = _diagnostic_contacts(supported, parts, catalogue, tolerance)
                    for contact in contacts:
                        if contact["occupancy"] != "single_mate":
                            continue
                        a, b = contact["stud"][0], contact["socket"][0]
                        if (a in members) != (b in members):
                            targets.add(workspace[b if a in members else a])
                target_space = next(iter(targets)) if len(targets) == 1 else "unknown:"+step.assembly_group_id
                if len(targets) != 1:
                    findings.append(_finding("workspace_assignment_unknown", step.step_id, members,
                        "Receiving workspace is ambiguous within this diagnostic scope; cross-workspace coincidence is not inferred.",
                        "unsupported"))
                for identity in members:
                    workspace[identity] = target_space
                if target_space.startswith("group:"):
                    groups[target_space[6:]].update(members)
            else:
                findings.append(_finding("nonrigid_group", step.step_id, members,
                                         "Attachment lacks complete prior group membership/poses.", "error"))
        if moved - permitted:
            findings.append(_finding("historical_movement", step.step_id, moved-permitted,
                                     "Existing pieces moved without a complete rigid attachment.", "error"))
        latest.update(step.poses)
        if step.step_id not in selected_steps:
            snapshots.append({"step_id": step.step_id, "status": "omitted_by_scope", "pose_count": len(latest),
                              "contact_aabb_status": "not_run", "duplicate_status": "not_run"})
            continue
        heavy = len(latest) <= MAX_DIAGNOSTIC_POSES
        if not heavy:
            findings.append(_finding("diagnostic_limit", step.step_id, [],
                "Contact/AABB checks omitted above the snapshot pose bound; bounded duplicate checks remain available.",
                "unsupported", pose_count=len(latest), max_poses=MAX_DIAGNOSTIC_POSES))
        partitions = defaultdict(dict)
        for identity, pose in latest.items():
            partitions[workspace.get(identity, "main")][identity] = pose
        step_contacts, step_overlaps, step_conflicts = [], [], []
        for space, poses in partitions.items():
            duplicates = defaultdict(list)
            for identity, pose in poses.items():
                duplicates[(parts[identity].geometry_ref, pose_key(pose))].append(identity)
            for identities in duplicates.values():
                if len(identities) > 1:
                    findings.append(_finding("exact_coincident_geometry", step.step_id, identities,
                                             "Distinct physical instances share the exact same geometry transform.", "error", workspace=space))
            origins = defaultdict(list)
            for identity, pose in poses.items():
                origins[(parts[identity].geometry_ref, tuple(pose.position_ldu))].append(identity)
            for (reference, _), identities in origins.items():
                pair_count = len(identities)*(len(identities)-1)//2
                pairs_considered_here = 0
                for a, b in itertools.combinations(sorted(identities), 2):
                    if symmetry_considered >= MAX_SYMMETRY_PAIRS:
                        symmetry_omitted += pair_count-pairs_considered_here
                        break
                    pairs_considered_here += 1
                    symmetry_considered += 1
                    relative = relative_axis_rotation(poses[a], poses[b])
                    if relative is None or relative == IDENTITY:
                        continue
                    if reference not in symmetry_cache and len(symmetry_cache) >= MAX_SYMMETRY_DESIGNS:
                        symmetry_omitted += 1
                        continue
                    symmetry_pairs += 1
                    if reference not in symmetry_cache:
                        symmetry_cache[reference] = verified_origin_symmetries(geometry_root, reference)
                    proof = symmetry_cache[reference]
                    if relative in proof["rotations"]:
                        findings.append(_finding("symmetric_coincident_geometry", step.step_id, [a, b],
                            "Distinct physical instances have coincident whole-part triangles under a verified origin-preserving rotation.",
                            "error", workspace=space, geometry_ref=reference, symmetry_rotation=relative,
                            symmetry_receipt_sha256=digest(proof), pose_tolerance=proof["pose_tolerance"]))
            if not heavy:
                continue
            supported = {i: pose for i, pose in poses.items() if i not in unsupported}
            contacts, conflicts = _diagnostic_contacts(supported, parts, catalogue, tolerance)
            for conflict in conflicts:
                findings.append(_finding("occupied_connector", step.step_id, conflict["instance_ids"],
                    "One nominal mating feature coincides with multiple mates; these contacts are not validated.",
                    "error", feature=conflict["feature"], nominal_mates=conflict["nominal_mates"], workspace=space))
            step_conflicts.extend({**conflict, "workspace": space} for conflict in conflicts)
            step_contacts.extend(contacts)
            edges = defaultdict(set)
            for contact in contacts:
                a, b = contact["stud"][0], contact["socket"][0]
                edges[a].add(b)
                edges[b].add(a)
            if len(supported) == len(poses) and poses:
                reached, pending = set(), [roots.get(space, next(iter(poses)))]
                while pending:
                    identity = pending.pop()
                    if identity in reached:
                        continue
                    reached.add(identity)
                    pending.extend(edges[identity]-reached)
                if set(poses)-reached:
                    findings.append(_finding("floating_supported_instance", step.step_id, set(poses)-reached,
                        "No path of supported nominal coincidences to this assembly's root. Conflicted contacts elsewhere do not erase this graph.",
                        "review", connectivity_basis="all_nominal_coincidences_not_validated_connections"))
            bounds, features = {}, {}
            for identity, pose in supported.items():
                part = catalogue[parts[identity].geometry_ref]
                lo, hi = part["bounds_ldu"]
                corners = [transform_point(pose, p) for p in itertools.product(*zip(lo, hi))]
                bounds[identity] = ([min(p[i] for p in corners) for i in range(3)],
                                    [max(p[i] for p in corners) for i in range(3)])
                rotation = rotation_matrix(pose.quaternion_xyzw)
                features[identity] = [(c, transform_point(pose, c["position_ldu"]), transform_vector(rotation, c["normal"]))
                                      for c in part["connectors"]]
            for a, b in itertools.combinations(supported, 2):
                alo, ahi = bounds[a]
                blo, bhi = bounds[b]
                if all(min(ahi[i], bhi[i])-max(alo[i], blo[i]) > tolerance for i in range(3)):
                    step_overlaps.append([a, b])
                    findings.append(_finding("aabb_overlap_candidate", step.step_id, [a, b],
                        "Bounds overlap; intended engagement and unintended penetration are not distinguished.",
                        nominal_contact=b in edges[a]))
                if b in edges[a] or not ({a, b} & new):
                    continue
                near = []
                for ca, pa, na in features[a]:
                    for cb, pb, nb in features[b]:
                        distance = math.dist(pa, pb)
                        if (ca["kind"] != cb["kind"] and tolerance < distance <= 8
                                and sum(x*y for x, y in zip(na, nb)) < -1+1e-6):
                            near.append(distance)
                if near:
                    findings.append(_finding("near_connector_gap", step.step_id, [a, b],
                        "Opposing supported features are near but not seated; candidate gap, not a proven intended connection.",
                        distance_ldu=min(near)))
        snapshots.append({"step_id": step.step_id, "status": "checked" if heavy else "partial_pose_limit",
                          "pose_count": len(latest), "contact_aabb_status": "checked_scoped" if heavy else "not_run",
                          "duplicate_status": "checked_finite_scope", "nominal_contacts": step_contacts,
                          "occupancy_conflicts": step_conflicts,
                          "connectivity_basis": "all_nominal_coincidences_not_validated_connections",
                          "aabb_overlap_candidates": step_overlaps})
    symmetry_partial = symmetry_omitted or any(p["status"] != "checked_finite_rotations" for p in symmetry_cache.values())
    if symmetry_partial:
        findings.append(_finding("symmetry_diagnostic_limit", None, [],
            "Some whole-part symmetry comparisons were outside bounded verified coverage.", "unsupported",
            omitted_pairs=symmetry_omitted))
    omitted = [item for item in snapshots if item["status"] != "checked"]
    if omitted:
        checks["exact_coincident_geometry"] = checks["symmetric_coincident_geometry"] = "checked_scoped"
    computed_findings = len(findings)
    finding_counts, finding_severities = dict(findings.counts), dict(findings.severities)
    if finding_counts.get("workspace_assignment_unknown"):
        checks["rigid_groups"] = "checked_with_workspace_uncertainty"
    truncated = computed_findings > 512
    findings = findings.retained(511 if truncated else 512)
    if truncated:
        findings = [*findings[:511], _finding("diagnostics_truncated", None, [],
            "Diagnostic findings exceed the retained receipt bound; the missing findings remain unknown to this compact view.",
            "unsupported", computed_findings=computed_findings, retained_findings=511,
            omitted_findings=computed_findings-511)]
    return {"version": VERSION, "diagnostic_version": "scoped-contact-and-whole-part-symmetry-v3",
            "status": "findings" if findings else "partial_unknown" if omitted else "clear_within_scope",
            "scene_sha256": digest(scene), "metadata_sha256": digest(metadata) if metadata else None,
            "findings": findings, "findings_truncated": truncated,
            "computed_findings_count": computed_findings, "retained_findings_count": min(computed_findings, 511 if truncated else 512),
            "finding_counts": finding_counts, "finding_severity_counts": finding_severities,
            "checks": checks,
            "snapshots": snapshots,
            "coverage": {"status": "partial" if omitted or symmetry_partial or truncated else "checked_within_declared_scope",
                         "requested_step_ids": [s.step_id for s in scene.steps if s.step_id in selected_steps],
                         "checked_step_ids": [s["step_id"] for s in snapshots if s["status"] == "checked"],
                         "omitted_or_partial_snapshots": [{k: s[k] for k in ("step_id", "status", "pose_count")} for s in omitted],
                         "omitted_or_partial_pose_count": sum(s["pose_count"] for s in omitted),
                         "history_and_group_scope": "all_snapshots", "max_contact_aabb_poses": MAX_DIAGNOSTIC_POSES},
            "symmetry": {"pairs_checked": symmetry_pairs, "pairs_considered": symmetry_considered, "pairs_omitted": symmetry_omitted,
                         "max_pairs": MAX_SYMMETRY_PAIRS, "max_designs": MAX_SYMMETRY_DESIGNS,
                         "geometry_receipts": list(symmetry_cache.values())},
            "scope": "Scoped diagnostics; no narrow-phase, strength, or physical-build certification."}


def _distance(a, b):
    a, b = Pose.model_validate(a), Pose.model_validate(b)
    ar, br = rotation_matrix(a.quaternion_xyzw), rotation_matrix(b.quaternion_xyzw)
    cosine = (sum(ar[i][j]*br[i][j] for i in range(3) for j in range(3))-1)/2
    return math.dist(a.position_ldu, b.position_ldu) + 20*math.acos(max(-1, min(1, cosine)))


def _diverse(items, limit):
    """Keep the best supported prior plus distinct receivers/positions/rotations.

    Confirmed diagnostic errors precede diversity. Neither uncertainty wording
    nor number of review-only findings makes an alternative less diverse.
    """
    remaining, retained = list(items), []
    seen = {name: set() for name in ("targets", "positions", "orientations")}
    while remaining and len(retained) < limit:
        def key(item):
            features = item["search_features"]
            novelty = tuple(-len({tuple(value) for value in features[name]}-seen[name]) for name in seen)
            # Distinct IDs alone can still consume a small beam on neighbouring
            # studs. Spread retained positions across each nominated receiver.
            spread = 0.
            for position in features["positions"]:
                comparable = [old for old in seen["positions"] if old[:3] == tuple(position[:3])]
                if comparable:
                    spread += min(math.dist(position[-3:], old[-3:]) for old in comparable)
            return (item.get("diagnostic_error_count", 0), *novelty,
                    -spread, item["ranking_score"], item["hypothesis_id"])
        best = min(remaining, key=key)
        retained.append(best)
        remaining.remove(best)
        for name in seen:
            seen[name].update(tuple(value) for value in best["search_features"][name])
    return retained


def _choice_features(choice, step, catalogue, parts):
    target = connector(catalogue[parts[choice.target_instance_id].geometry_ref], choice.target_connector_id)
    moving = connector(catalogue[parts[choice.moving_instance_id].geometry_ref], choice.moving_connector_id)
    desired = _mate_pose(step.poses[choice.target_instance_id], moving, target, choice.quarter_turns)
    anchor = [choice.step_id, choice.moving_instance_id]
    return desired, {"targets": [[*anchor, choice.target_instance_id]],
        "positions": [[*anchor, choice.target_instance_id,
                       *[round(v, 8) for v in transform_point(step.poses[choice.target_instance_id], target["position_ldu"])]]],
        "orientations": [[*anchor, *pose_key(desired)[3:]]]}


def _interleave(iterables):
    """Round-robin generators without constructing their Cartesian products."""
    pending = [iter(values) for values in iterables]
    while pending:
        following = []
        for values in pending:
            try:
                yield next(values)
                following.append(values)
            except StopIteration:
                pass
        pending = following


def _diagnostic_summary(report):
    return {"diagnostic_coverage": deepcopy(report["coverage"]), "diagnostic_receipt_sha256": digest(report),
            "findings_truncated": report["findings_truncated"],
            "computed_findings_count": report["computed_findings_count"],
            "retained_findings_count": report["retained_findings_count"],
            "finding_counts": report["finding_counts"], "finding_severity_counts": report["finding_severity_counts"]}


def _physical_transform_key(scene):
    """Snapshot transforms, not solver annotations or quaternion sign spelling."""
    data = scene.model_dump(mode="json") if isinstance(scene, SceneV2) else scene
    return (tuple((part["instance_id"], part["geometry_ref"], part["color_code"]) for part in data["instances"]),
            tuple((step["step_id"], tuple((identity, pose_key(pose)) for identity, pose in sorted(step["poses"].items())))
                  for step in data["steps"]))


def enumerate_hypotheses(raw_scene, previous, geometry_root: Path, *, connections=(), roots=(), hints=(),
                         max_candidates=64, beam_width=8, return_count=3):
    """Bounded diverse receiving positions, restricted to source-nominated IDs.

    Connector IDs and turns in model hints are priors, not reviewed locks. Only
    compatible catalogue sites/orientations on the nominated physical receivers
    are expanded. Complete group membership remains the solver's hard boundary.
    Pose distance never substitutes for a source-image comparison.
    """
    with catalogue_verification_scope(), diagnostic_reuse_scope():
        return _enumerate_hypotheses(raw_scene, previous, geometry_root, connections=connections,
            roots=roots, hints=hints, max_candidates=max_candidates, beam_width=beam_width,
            return_count=return_count)


def _enumerate_hypotheses(raw_scene, previous, geometry_root, *, connections, roots, hints,
                          max_candidates, beam_width, return_count):
    if (any(type(v) is not int for v in (max_candidates, beam_width, return_count))
            or not 1 <= max_candidates <= 64 or not 1 <= beam_width <= 8 or not 1 <= return_count <= 3):
        raise ValueError("Hypothesis budgets exceed supported bounds")
    scene = SceneV2.model_validate(raw_scene)
    raw = scene.model_dump(mode="json")
    diagnostic = diagnose_candidate(scene, previous, geometry_root)
    fallback = {"hypothesis_id": "raw-"+digest(scene)[:16], "kind": "raw_fallback", "scene": raw,
                **_diagnostic_summary(diagnostic),
                "solver_report": {"status": "not_run", "scope": "Unmodified provider proposal"},
                "findings": diagnostic["findings"], "ranking_score": 1_000_000.,
                "ranking_components": {"image_agreement": "not_run", "raw_preserved": True}}
    result = {"version": VERSION, "input_scene_sha256": digest(scene), "candidates": [fallback], "retained_beam": [],
              "evaluated_count": 0, "truncated": False, "findings": [], "attempts": [],
              "limits": {"max_candidates": max_candidates, "beam_width": beam_width, "return_count": return_count},
              "score_direction": "lower_is_better", "limitations": ["Pose prior is not image agreement.",
                  "Supported nominal frames and broad-phase diagnostics only; unresolved alternatives require review."]}
    choices = [ConnectionChoice.model_validate(c) for c in connections]
    roots = [RootPlacement.model_validate(r) for r in roots]
    hints = [PlacementHint.model_validate(h) for h in hints]
    if len(hints) > 64 or len(choices) > 512 or len(roots) > 512:
        raise ValueError("Source hypothesis hints exceed bound")
    search = {"policy": "source-receiver-position-diversity-v2", "anchors": [],
              "nomination_sha256": digest({"connections": [c.model_dump(mode="json") for c in choices],
                                            "hints": [h.model_dump(mode="json") for h in hints]}),
              "receiver_scope": "only_current_source_nominated_physical_instance_ids",
              "connector_scope": "compatible_catalogue_sites_and_allowed_turns_on_nominated_receivers",
              "moving_scope": "nominated_moving_connector_ids_and_unchanged_complete_rigid_group",
              "option_generation_limit": 16_384, "per_anchor_option_limit": 2048,
              "connector_pair_check_limit": 65_536, "connector_pair_checks": 0,
              "options_generated": 0, "generation_truncated": False,
              "plan_order": "balanced_diverse_option_depth_then_pose_prior",
              "retention": "diagnostic_error_count_then_receiver_position_orientation_diversity_then_pose_prior"}
    result["search_receipt"] = search
    try:
        _, catalogue = load_connector_catalogue(Path(geometry_root), {p.geometry_ref for p in scene.instances})
    except ValueError as error:
        if not _unsupported_metadata(error):
            raise
        result["findings"] = [_finding("unsupported_connector_geometry", None, [], str(error)[:1000], "unsupported")]
        return result
    parts = {p.instance_id: p for p in scene.instances}
    prefix = len((previous or {}).get("steps", []))
    steps = {step.step_id: step for step in scene.steps[prefix:]}
    keys = [(c.step_id, c.moving_instance_id) for c in choices]
    if len(set(keys)) != len(keys):
        result["findings"] = [_finding("duplicate_placement_anchor", None, [], "Multiple anchors for one moving piece.", "error")]
        return result
    nominations = defaultdict(list)
    for choice in choices:
        step = steps.get(choice.step_id)
        if step is None:
            result["findings"].append(_finding("unsupported_source_hint", choice.step_id, [choice.moving_instance_id],
                "Connection is outside the current source snapshots.", "unsupported"))
            continue
        nominations[(choice.step_id, choice.moving_instance_id)].append({
            "target_instance_ids": [choice.target_instance_id], "moving_connector_ids": [choice.moving_connector_id],
            "target_connector_ids": [choice.target_connector_id], "quarter_turns": [choice.quarter_turns],
            "moving_group_ids": choice.moving_group_ids, "source": step.source.model_dump(mode="json"),
            "origin": "source_bound_connection"})
    for hint in hints:
        step = steps.get(hint.step_id)
        if (step is None or hint.moving_instance_id not in step.poses
                or hint.source.source_sha256 != step.source.source_sha256
                or hint.source.page_index != step.source.page_index):
            result["findings"].append(_finding("unsupported_source_hint", hint.step_id, [hint.moving_instance_id],
                "Placement hint differs from current snapshot/source evidence.", "unsupported"))
            continue
        nominations[(hint.step_id, hint.moving_instance_id)].append({
            **hint.model_dump(mode="json"), "origin": "source_bound_placement_hint"})
    options, costs, features_by_choice = {}, {}, {}
    for key, specs in nominations.items():
        step_id, moving_id = key
        step = steps[step_id]
        if moving_id not in step.poses:
            result["findings"].append(_finding("unsupported_connection_hint", step_id, [moving_id],
                "Moving anchor is absent from the source snapshot.", "unsupported"))
            continue
        group_sets = {tuple(sorted(spec["moving_group_ids"])) for spec in specs}
        if len(group_sets) != 1:
            result["findings"].append(_finding("conflicting_group_hints", step_id, [moving_id],
                "Model nominations disagree about rigid group membership; no merged group is invented.", "error"))
            continue
        group = list(next(iter(group_sets)))
        moving_part = catalogue[parts[moving_id].geometry_ref]
        target_specs = defaultdict(list)
        for spec in specs:
            try:
                moving_features = ([connector(moving_part, name) for name in spec["moving_connector_ids"]]
                                   if spec["moving_connector_ids"] else moving_part["connectors"])
            except ValueError as error:
                result["findings"].append(_finding("unsupported_connection_hint", step_id, [moving_id], str(error), "unsupported"))
                continue
            for target_id in spec["target_instance_ids"]:
                if target_id == moving_id or target_id in group or target_id not in step.poses:
                    result["findings"].append(_finding("unsupported_connection_hint", step_id, [moving_id, target_id],
                        "Receiver must be a distinct present instance outside the moving group.", "unsupported"))
                    continue
                target_part = catalogue[parts[target_id].geometry_ref]
                try:
                    # Validate the nominated sites even though their location is
                    # not a lock. Invalid model names cannot become provenance.
                    for name in spec["target_connector_ids"]:
                        connector(target_part, name)
                except ValueError as error:
                    result["findings"].append(_finding("unsupported_connection_hint", step_id, [target_id], str(error), "unsupported"))
                    continue
                target_specs[target_id].append((moving_features, target_part["connectors"]))

        def target_options(target_id, pairs):
            seen_choices = set()
            # Interleave distinct source nominations before imposing a bound.
            iterators = [itertools.product(moving, targets, range(4)) for moving, targets in pairs]
            for moving_feature, target_feature, turn in _interleave(iterators):
                if search["connector_pair_checks"] >= search["connector_pair_check_limit"]:
                    search["generation_truncated"] = result["truncated"] = True
                    return
                search["connector_pair_checks"] += 1
                if (moving_feature["kind"] == target_feature["kind"]
                        or turn not in moving_feature["allowed_quarter_turns"]
                        or turn not in target_feature["allowed_quarter_turns"]
                        or moving_feature["engagement_ldu"] != target_feature["engagement_ldu"]):
                    continue
                choice = ConnectionChoice(step_id=step_id, moving_instance_id=moving_id,
                    moving_connector_id=moving_feature["connector_id"], target_instance_id=target_id,
                    target_connector_id=target_feature["connector_id"], quarter_turns=turn, moving_group_ids=group)
                identity = digest(choice)
                if identity not in seen_choices:
                    seen_choices.add(identity)
                    yield choice

        unique, generated = {}, 0
        iterator = _interleave(target_options(target_id, pairs) for target_id, pairs in sorted(target_specs.items()))
        for choice in iterator:
            if generated >= search["per_anchor_option_limit"] or search["options_generated"] >= search["option_generation_limit"]:
                search["generation_truncated"] = result["truncated"] = True
                break
            generated += 1
            search["options_generated"] += 1
            desired, features = _choice_features(choice, step, catalogue, parts)
            cost = _distance(desired, step.poses[moving_id])
            identity = digest(choice)
            item = {"hypothesis_id": identity, "choice": choice, "ranking_score": cost,
                    "search_features": features, "pose": pose_key(desired)}
            prior = unique.get(item["pose"])
            if prior is None or (cost, identity) < (prior["ranking_score"], prior["hypothesis_id"]):
                unique[item["pose"]] = item
        diverse = _diverse(list(unique.values()), max_candidates)
        if len(unique) > len(diverse):
            result["truncated"] = True
        search["anchors"].append({"step_id": step_id, "moving_instance_id": moving_id,
            "source": step.source.model_dump(mode="json"), "nominations": specs,
            "source_nominated_receiver_ids": sorted(target_specs), "moving_group_ids": group,
            "generated_options": generated, "distinct_anchor_poses": len(unique), "retained_options": len(diverse),
            "retained_targets": sorted({item["choice"].target_instance_id for item in diverse}),
            "retained_receiver_positions": sorted({tuple(value) for item in diverse for value in item["search_features"]["positions"]}),
            "retained_orientations": sorted({tuple(value) for item in diverse for value in item["search_features"]["orientations"]})})
        if not diverse:
            result["findings"].append(_finding("unsupported_connection_hint", step_id, [moving_id],
                "No compatible supported pair exists within this source-nominated receiver scope and budget.", "unsupported"))
            continue
        options[key] = [item["choice"] for item in diverse]
        for item in diverse:
            costs[item["hypothesis_id"]] = item["ranking_score"]
            features_by_choice[item["hypothesis_id"]] = item["search_features"]
    keys = list(options)
    initial = tuple(0 for _ in keys)
    def prior(indices):
        return sum(costs[digest(options[key][index])] for key, index in zip(keys, indices))
    def priority(indices):
        # A distance-only queue can spend all 64 evaluations at one receiver.
        # Diverse option depth treats alternative receiving positions fairly.
        return (max(indices, default=0), sum(indices), prior(indices), indices)
    queue, seen, retained, scene_keys = [priority(initial)], {initial}, [], set()
    while queue and result["evaluated_count"] < max_candidates:
        _, _, cost, indices = heapq.heappop(queue)
        plan = [options[key][index] for key, index in zip(keys, indices)]
        result["evaluated_count"] += 1
        features = {name: [value for choice in plan for value in features_by_choice[digest(choice)][name]]
                    for name in ("targets", "positions", "orientations")}
        attempt = {"plan": [choice.model_dump(mode="json") for choice in plan], "pose_prior": cost,
                   "search_features": features, "search_features_basis": "source_proposal_receiver_frames",
                   "diverse_option_indices": list(indices)}
        try:
            solved, report = solve_candidate(scene, previous, plan, roots, geometry_root)
            transform_key = _physical_transform_key(solved)
            attempt.update(status="nominally_supported", scene_sha256=digest(solved))
            if transform_key not in scene_keys:
                scene_keys.add(transform_key)
                solved_steps = {step.step_id: step for step in solved.steps}
                solved_features = [_choice_features(choice, solved_steps[choice.step_id], catalogue, parts)[1] for choice in plan]
                features = {name: [value for values in solved_features for value in values[name]]
                            for name in ("targets", "positions", "orientations")}
                diagnostics = diagnose_candidate(solved, previous, geometry_root)
                errors = diagnostics["finding_severity_counts"].get("error", 0)
                # Review wording is not a measured error count. Keep it in full,
                # but it cannot suppress otherwise distinct receiving positions.
                score = errors*1000 + cost/1000
                retained.append({"hypothesis_id": "connector-"+digest(solved)[:16], "kind": "connector_hypothesis",
                    **_diagnostic_summary(diagnostics),
                    "scene": solved.model_dump(mode="json"), "solver_report": report, "findings": diagnostics["findings"],
                    "ranking_score": score, "diagnostic_error_count": errors, "search_features": features,
                    "search_features_basis": "solved_receiver_frames",
                    "search_plan": attempt["plan"],
                    "ranking_components": {"diagnostic_penalty": errors*1000,
                    "pose_prior_distance": cost, "image_agreement": "not_run", "diversity_policy": search["policy"]}})
                retained = _diverse(retained, beam_width)
        except SpatialError as error:
            if error.report["code"] in {"resource_limit", "coordinate_limit", "prefix_modified"}:
                raise
            attempt.update(status="rejected", finding=str(error)[:1000], diagnostic=error.report)
        result["attempts"].append(attempt)
        for i, key in enumerate(keys):
            if indices[i]+1 >= len(options[key]):
                continue
            neighbor = indices[:i] + (indices[i]+1,) + indices[i+1:]
            if neighbor not in seen:
                seen.add(neighbor)
                heapq.heappush(queue, priority(neighbor))
        if len(queue) > max_candidates*beam_width:
            queue = heapq.nsmallest(max_candidates*beam_width, queue)
            heapq.heapify(queue)
            result["truncated"] = True
    result["truncated"] = result["truncated"] or bool(queue)
    # Raw is always rendered, so an equivalent solved transform must not consume
    # another scarce image slot. Its full solver evidence remains in the beam.
    render_keys, best, skipped = {_physical_transform_key(raw)}, [], []
    for candidate in retained:
        key = _physical_transform_key(candidate["scene"])
        if key in render_keys:
            skipped.append(candidate["hypothesis_id"])
            continue
        if len(best) < return_count-1:
            best.append(candidate)
            render_keys.add(key)
    result["candidates"] = [*best, fallback] if best else [fallback]
    result["retained_beam"] = deepcopy(retained)
    search["render_selection"] = {"policy": "raw-equivalent-transform-dedup-v1", "raw_fallback_preserved": True,
        "skipped_equivalent_hypothesis_ids": skipped, "distinct_transform_scenes": len(result["candidates"]),
        "solver_receipts_retained_in_beam": True}
    search["evaluated_targets"] = sorted({tuple(value) for attempt in result["attempts"] for value in attempt["search_features"]["targets"]})
    search["evaluated_receiver_positions"] = sorted({tuple(value) for attempt in result["attempts"] for value in attempt["search_features"]["positions"]})
    search["evaluated_orientations"] = sorted({tuple(value) for attempt in result["attempts"] for value in attempt["search_features"]["orientations"]})
    search["render_hypothesis_ids"] = [item["hypothesis_id"] for item in result["candidates"]]
    search["coverage_status"] = "bounded_partial" if result["truncated"] else "enumerated_within_nominated_scope"
    return result


def rank_landmark_identity_alternatives(scene, observation, geometry_root: Path, image_size, *, instance_groups=(),
                                       max_candidates=8, view_family=None, max_rms_pixels=4., max_point_pixels=12.):
    """Try bounded identity swaps without changing one assembly pose or image point.

    Groups must be source-supported alternatives of the same individual design.
    Lower residual ranks a correspondence, not the correctness of the assembly.
    """
    if not 1 <= max_candidates <= 16 or len(instance_groups) > 8:
        raise ValueError("Landmark alternative budget exceeded")
    scene = SceneV2.model_validate(scene)
    observation = SourceViewObservation.model_validate(observation)
    step = next((step for step in scene.steps if step.step_id == observation.step_id), None)
    if step is None:
        raise ValueError("Unknown landmark snapshot")
    parts = {p.instance_id: p for p in scene.instances}
    ids = {landmark.instance_id for landmark in observation.landmarks}
    mappings = [{}]
    for group in instance_groups:
        if (not 2 <= len(group) <= 4 or len(set(group)) != len(group) or not set(group) <= set(step.poses)
                or len({parts[i].geometry_ref for i in group}) != 1):
            raise ValueError("Landmark identity alternatives need distinct visible instances of the same design")
        ids.update(group)
        for a, b in itertools.combinations(group, 2):
            if len(mappings) >= max_candidates:
                break
            mappings.append({a: b, b: a})
    _, catalogue = load_connector_catalogue(geometry_root, {parts[i].geometry_ref for i in ids})
    locals_ = {ref: {c["landmark"]["landmark_id"]: c["landmark"]["position_ldu"]
                    for c in part["connectors"] if c.get("landmark")} for ref, part in catalogue.items()}
    candidates = []
    for mapping in mappings:
        candidate = deepcopy(observation.model_dump(mode="json"))
        for landmark in candidate["landmarks"]:
            landmark["instance_id"] = mapping.get(landmark["instance_id"], landmark["instance_id"])
        candidate = SourceViewObservation.model_validate(candidate)
        world = []
        for landmark in candidate.landmarks:
            if landmark.instance_id not in step.poses:
                raise ValueError("Landmark instance is not visible")
            local = locals_[parts[landmark.instance_id].geometry_ref].get(landmark.landmark_id)
            if local is None:
                raise ValueError("Unknown geometry-bound source landmark")
            world.append(transform_point(step.poses[landmark.instance_id], local))
        fit = fit_source_view(world, [landmark.image_uv for landmark in candidate.landmarks], image_size,
                              view_family=view_family or candidate.view_family,
                              max_rms_pixels=max_rms_pixels, max_point_pixels=max_point_pixels)
        candidates.append({"observation": candidate.model_dump(mode="json"), "identity_changes": mapping,
                           "fit": fit, "ranking_score": fit["rms_pixels"], "requires_visual_review": True})
    candidates.sort(key=lambda c: (c["ranking_score"] is None, c["ranking_score"] or 0, len(c["identity_changes"])))
    return {"version": "landmark-identity-alternatives-v1", "scene_sha256": digest(scene),
            "assembly_poses_changed": False, "source_image_points_changed": False, "candidates": candidates,
            "evaluated_count": len(candidates), "score_direction": "lower_is_better",
            "limitations": ["Identity swaps are source-supported hypotheses, not verified correspondences.",
                            "Residual does not test silhouette, occlusion or hidden geometry."]}


def source_view_alternatives(scene, previous, observations, geometry, source_image, policy=None):
    """Backward-compatible fitting boundary with retained, bounded identity alternatives."""
    from PIL import Image
    from .quality import fit_acceptance, source_view_policy
    scene = SceneV2.model_validate(scene)
    observations = [SourceViewObservation.model_validate(o) for o in observations]
    steps = scene.steps[len((previous or {}).get("steps", [])):]
    if len(observations) != len(steps) or {o.step_id for o in observations} != {s.step_id for s in steps}:
        raise ValueError("Each new snapshot needs its own source landmark observation")
    policy = policy or source_view_policy()
    with Image.open(source_image) as image:
        size = image.size
    parts = {part.instance_id: part for part in scene.instances}
    by_step = {o.step_id: o for o in observations}
    fits, cameras = {}, {}
    for step in steps:
        observation = by_step[step.step_id]
        by_design = defaultdict(set)
        for landmark in observation.landmarks:
            if landmark.instance_id not in step.poses:
                raise ValueError("A source landmark must belong to a visible instance")
            by_design[parts[landmark.instance_id].geometry_ref].add(landmark.instance_id)
        groups = [sorted(identities) for identities in by_design.values() if 2 <= len(identities) <= 4][:8]
        ranked = rank_landmark_identity_alternatives(scene, observation, geometry, size, instance_groups=groups,
            max_candidates=8, max_rms_pixels=policy["max_rms_pixels"], max_point_pixels=policy["max_point_pixels"])
        original = next(c for c in ranked["candidates"] if not c["identity_changes"])
        best = ranked["candidates"][0]
        # Do not swap a plausible original for a numerically indistinguishable identity.
        if (original["fit"]["status"] == "fitted" and original["ranking_score"] is not None
                and best["ranking_score"] is not None
                and original["ranking_score"]-best["ranking_score"] <= policy["ambiguity_pixels"]):
            best = original
        fit = {**best["fit"], **fit_acceptance(best["fit"]),
               "original_observation": observation.model_dump(mode="json"),
               "selected_observation": best["observation"], "identity_changes": best["identity_changes"],
               "landmark_alternatives": ranked["candidates"], "assembly_poses_changed": False,
               "requires_visual_review": True}
        fits[step.step_id] = fit
        if fit["status"] == "fitted" and fit["camera"]:
            cameras[step.step_id] = fit["camera"]
    return fits, cameras
