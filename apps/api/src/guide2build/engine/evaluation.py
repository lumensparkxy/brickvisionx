"""Measure complete-booklet experiments without treating baseline agreement as accuracy."""
from __future__ import annotations

import hashlib
import html
import json
import math
import shutil
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from pydantic import Field, model_validator

from ..core.models import Pose, SourcePanel, StrictModel
from ..releases.models import SceneV2, Source, digest
from .connectors import rotation_matrix
from .reporting import _counts, _event_usage
from .spatial import _same_pose


class ExpectedPose(StrictModel):
    step_id: str = Field(min_length=1, max_length=160)
    pose: Pose


class InstanceExpectation(StrictModel):
    instance_id: str = Field(min_length=1, max_length=160)
    evidence: SourcePanel
    part_id: str | None = Field(default=None, max_length=80)
    color_code: str | None = Field(default=None, pattern=r"^[0-9]{1,5}$")
    introduced_main_step: int | None = Field(default=None, ge=1)
    group_id: str | None = Field(default=None, max_length=160)
    grouping_known: bool = False
    poses: list[ExpectedPose] = Field(default_factory=list, max_length=10000)


class QuantityExpectation(StrictModel):
    main_step_number: int = Field(ge=1, le=10000)
    count: int = Field(ge=0, le=20000)
    evidence: SourcePanel
    part_id: str | None = Field(default=None, max_length=80)
    color_code: str | None = Field(default=None, pattern=r"^[0-9]{1,5}$")


class EvaluationReference(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    artifact_kind: Literal["source_reviewed_annotations"]
    set_number: str = Field(pattern=r"^[0-9]{4,7}$")
    guide_id: str = Field(pattern=r"^[a-z0-9-]+$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor: Literal["agent", "human"]
    reason: str = Field(min_length=1, max_length=4000)
    instances: list[InstanceExpectation] = Field(default_factory=list, max_length=20000)
    quantities: list[QuantityExpectation] = Field(default_factory=list, max_length=10000)
    expected_main_steps: list[int] = Field(default_factory=list, max_length=10000)
    expected_microsteps: int | None = Field(default=None, ge=1, le=10000)

    @model_validator(mode="after")
    def unique(self):
        if len({part.instance_id for part in self.instances}) != len(self.instances):
            raise ValueError("Duplicate reference instance identity")
        quantities = [(q.evidence.source_sha256, q.main_step_number, q.part_id, q.color_code) for q in self.quantities]
        if len(set(quantities)) != len(quantities):
            raise ValueError("Duplicate quantity scoring annotation")
        part_colors = {}
        for quantity in self.quantities:
            if quantity.part_id is not None:
                key = (quantity.evidence.source_sha256, quantity.main_step_number, quantity.part_id)
                part_colors.setdefault(key, set()).add(quantity.color_code)
        if any(None in colors and len(colors) > 1 for colors in part_colors.values()):
            raise ValueError("Overlapping part quantity annotations: wildcard colour and specific colours cannot score the same instruction/part")
        if len(set(self.expected_main_steps)) != len(self.expected_main_steps) or any(
                type(n) is not int or n < 1 for n in self.expected_main_steps):
            raise ValueError("Invalid reference main-step inventory")
        for part in self.instances:
            if len({pose.step_id for pose in part.poses}) != len(part.poses):
                raise ValueError("Duplicate pose scoring annotation")
        return self


def _read(path, limit=32_000_000, root=None):
    path = Path(path)
    if (path.is_symlink() or not path.is_file() or path.stat().st_size > limit
            or (root is not None and not path.resolve().is_relative_to(Path(root).resolve()))):
        raise ValueError("Unavailable, unsafe or oversized evaluation evidence")
    return json.loads(path.read_text())


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def summarize_job_calls(directory):
    """Count actual invocations once across strict, alpha and exploration layouts.

    A timed-out process may have process-result.json but no invocation.json. The
    shared directory identifies one call; raw token events take precedence over
    copied usage receipts. Inherited parent calls remain outside this local count.
    """
    directory = Path(directory)
    call_directories = set()
    for name in ("invocation.json", "process-result.json"):
        for path in directory.rglob(name):
            if len(call_directories) >= 20000:
                raise ValueError("Invocation evidence exceeds evaluation bound")
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError("Invocation evidence escapes its job")
            call_directories.add(path.parent)
    usage, elapsed, failed, missing_results = {}, 0.0, 0, 0
    usage_calls = timing_calls = event_calls = receipt_calls = 0
    for parent in sorted(call_directories):
        records = []
        for name in ("invocation.json", "process-result.json"):
            path = parent / name
            try:
                value = _read(path, 1_000_000, directory) if path.exists() else {}
                records.append(value if isinstance(value, dict) else {})
            except (ValueError, OSError):
                records.append({})
        receipt, process = records
        duration = receipt.get("elapsed_seconds")
        if not _number(duration):
            duration = process.get("elapsed_seconds")
        if _number(duration):
            elapsed += duration
            timing_calls += 1
        code = process.get("returncode", receipt.get("returncode"))
        if type(code) is int and code != 0:
            failed += 1
        if process.get("structured_result_present") is False:
            missing_results += 1
        events = parent / "events.jsonl"
        if events.exists() and (events.is_symlink() or events.stat().st_size > 32_000_000):
            raise ValueError("Unsafe or oversized provider event evidence")
        measured = _event_usage(events)
        if measured:
            event_calls += 1
        else:
            measured = _counts(receipt.get("reported_usage"))
            if measured:
                receipt_calls += 1
        if measured:
            usage_calls += 1
            for key, value in measured.items():
                usage[key] = usage.get(key, 0) + value
    total = len(call_directories)
    return {"model_invocations": total, "model_elapsed_seconds": elapsed, "reported_usage": usage,
            "process_failures": failed, "processes_without_structured_result": missing_results,
            "usage_reporting": {"status": "complete" if total and usage_calls == total else
                                "partial" if usage_calls else "unavailable", "calls_with_usage": usage_calls,
                                "calls_without_usage": total - usage_calls, "raw_event_calls": event_calls,
                                "receipt_fallback_calls": receipt_calls},
            "timing_reporting": {"calls_with_elapsed_time": timing_calls,
                                 "calls_without_elapsed_time": total - timing_calls}}


def _metric(numerator=0, denominator=0, unknown=0, mismatches=None):
    return {"numerator": numerator, "denominator": denominator, "unknown": unknown,
            "status": "scored" if denominator else "unscorable",
            "mismatches": mismatches or []}


def _instruction_part_scores(parts, introductions, quantities):
    """Match independent source count annotations without requiring engine instance IDs.

    Totals never enter these denominators. Explicit colour rows describe disjoint
    subsets of a part count, so identity matching aggregates them before capping
    actual pieces. Wildcard/colour overlap is rejected by EvaluationReference.
    """
    expected_parts, expected_colors = Counter(), Counter()
    for row in quantities:
        if row.part_id is None:
            continue
        key = (row.evidence.source_sha256, row.main_step_number, row.part_id)
        expected_parts[key] += row.count
        if row.color_code is not None:
            expected_colors[(*key, row.color_code)] += row.count
    actual_parts, actual_colors = Counter(), Counter()
    for identity, step in introductions.items():
        part = parts[identity]
        key = (step.source.source_sha256, step.main_step_number, part.part_id)
        actual_parts[key] += 1
        actual_colors[(*key, part.color_code)] += 1
    metrics = {}
    for name, expected, actual in (("part_identity_by_instruction", expected_parts, actual_parts),
                                   ("color_by_instruction", expected_colors, actual_colors)):
        numerator, denominator, wrong = 0, sum(expected.values()), []
        for key, count in sorted(expected.items()):
            observed = actual[key]
            numerator += min(count, observed)
            if observed != count:
                wrong.append({"source_sha256": key[0], "main_step_number": key[1], "part_id": key[2],
                    "color_code": key[3] if len(key) == 4 else None, "expected": count, "actual": observed,
                    "missing": max(0, count-observed), "excess": max(0, observed-count)})
        metric = _metric(numerator, denominator, max(0, len(introductions)-denominator), wrong)
        metric.update(unit="pieces", annotation_groups=len(expected),
            unknown_basis="Unique candidate introductions beyond the number of source-annotated expected pieces.",
            matching_rule="Matching source/main/part counts are capped at each expected count; colour additionally requires the explicit source colour.",
            excess_matching_pieces=sum(item["excess"] for item in wrong),
            scope=("Aggregate part identity and colour counts by instruction; colour requires the matching part identity. "
                   "These counts do not establish per-instance correspondence, poses or grouping. "
                   "The capped ratio does not penalize excess pieces; count mismatches report them separately."))
        metrics[name] = metric
    return metrics


def score_scene(scene, reference=None):
    """Only explicitly annotated attributes enter a source-grounded denominator."""
    parts = {part.instance_id: part for part in scene.instances}
    steps = {step.step_id: step for step in scene.steps}
    introductions = {identity: step for step in scene.steps for identity in step.introduced_instance_ids}
    annotations = {part.instance_id: part for part in reference.instances} if reference else {}
    identities = set(parts) | set(annotations)
    metrics = {}
    for name, attribute in (("part_identity", "part_id"), ("color", "color_code"),
                             ("step_association", "introduced_main_step"), ("grouping", "group_id")):
        eligible = [annotation for annotation in annotations.values()
                    if (annotation.grouping_known if name == "grouping"
                        else getattr(annotation, attribute) is not None)]
        wrong = []
        for annotation in eligible:
            part = parts.get(annotation.instance_id)
            step = introductions.get(annotation.instance_id)
            if name == "step_association":
                actual = step.main_step_number if step else None
            elif name == "grouping":
                actual = step.assembly_group_id if step else None
            else:
                actual = getattr(part, attribute) if part else None
            if part is None or actual != getattr(annotation, attribute):
                wrong.append({"instance_id": annotation.instance_id, "expected": getattr(annotation, attribute),
                              "actual": actual})
        metrics[name] = _metric(len(eligible) - len(wrong), len(eligible), len(identities) - len(eligible), wrong)
    poses = [(annotation.instance_id, pose) for annotation in annotations.values() for pose in annotation.poses]
    wrong = []
    for identity, expected in poses:
        step = steps.get(expected.step_id)
        actual = step.poses.get(identity) if step else None
        # Position and orientation tolerances are separate; a 0.05 LDU distance
        # tolerance must not silently allow 0.05 error in a rotation matrix.
        correct = actual is not None and math.dist(actual.position_ldu, expected.pose.position_ldu) <= .05
        if correct:
            correct = max(abs(a-b) for ar, br in zip(rotation_matrix(actual.quaternion_xyzw),
                rotation_matrix(expected.pose.quaternion_xyzw), strict=True) for a, b in zip(ar, br, strict=True)) <= 1e-5
        if not correct:
            wrong.append({"instance_id": identity, "step_id": expected.step_id})
    scored_poses = {(identity, pose.step_id) for identity, pose in poses}
    actual_poses = {(identity, step.step_id) for step in scene.steps for identity in step.poses}
    metrics["pose"] = _metric(len(poses)-len(wrong), len(poses), len(actual_poses-scored_poses), wrong)
    quantities = reference.quantities if reference else []
    wrong = []
    for expected in quantities:
        actual = sum(step.main_step_number == expected.main_step_number
                     and step.source.source_sha256 == expected.evidence.source_sha256
                     and (expected.part_id is None or parts[identity].part_id == expected.part_id)
                     and (expected.color_code is None or parts[identity].color_code == expected.color_code)
                     for identity, step in introductions.items())
        if actual != expected.count:
            wrong.append({"main_step_number": expected.main_step_number, "part_id": expected.part_id,
                          "color_code": expected.color_code, "expected": expected.count, "actual": actual})
    all_mains = {step.main_step_number for step in scene.steps if step.main_step_number is not None}
    if reference:
        all_mains.update(reference.expected_main_steps)
    known_mains = {item.main_step_number for item in quantities}
    metrics["quantity"] = _metric(len(quantities)-len(wrong), len(quantities), len(all_mains-known_mains), wrong)
    metrics.update(_instruction_part_scores(parts, introductions, quantities))
    return metrics


def _basic_diagnostics(scene):
    """Conservative fallback while unsupported connector geometry remains unscored."""
    instances = {part.instance_id: part for part in scene.instances}
    findings, previous = [], {}
    for step in scene.steps:
        seen = {}
        for identity, pose in step.poses.items():
            # Quaternion signs are equivalent; rotation matrices avoid false differences.
            key = (instances[identity].geometry_ref, tuple(round(v, 8) for v in pose.position_ldu),
                   tuple(round(v, 8) for row in rotation_matrix(pose.quaternion_xyzw) for v in row))
            if key in seen:
                findings.append({"code": "exact_coincident_geometry", "severity": "error", "step_id": step.step_id,
                    "instance_ids": [seen[key], identity], "message": "Distinct physical instances share a whole-part pose."})
            seen[key] = identity
            if identity in previous and not _same_pose(previous[identity], pose) and step.action != "attach_subassembly":
                findings.append({"code": "historical_movement", "severity": "review", "step_id": step.step_id,
                    "instance_ids": [identity], "message": "Existing piece moved without a declared subassembly attachment."})
        previous.update(step.poses)
    return {"status": "findings" if findings else "clear_within_scope", "findings": findings,
            "checks": {"exact_coincident_geometry": "run", "historical_movement": "run",
                       "supported_connectors": "not_run", "narrow_phase": "not_run", "physical": "not_run"}}


def diagnose(scene, geometry):
    try:
        from .hypotheses import diagnose_candidate
    except ImportError:
        return _basic_diagnostics(scene)
    return diagnose_candidate(scene, None, geometry)


def _diagnostic_counts(diagnostics, final_step_id=None):
    findings = diagnostics.get("findings", [])
    return {"diagnostic_finding_counts": dict(Counter(item.get("code", "unresolved") for item in findings)),
        "diagnostic_finding_counts_basis": "per-snapshot scoped diagnostic observations",
        "diagnostic_findings_truncated": diagnostics.get("findings_truncated", False),
        "final_assembly_diagnostic_step_id": final_step_id,
        "final_assembly_diagnostic_finding_counts": dict(Counter(item.get("code", "unresolved")
            for item in findings if final_step_id is not None and item.get("step_id") == final_step_id)),
        "diagnostic_global_finding_counts": dict(Counter(item.get("code", "unresolved")
            for item in findings if item.get("step_id") is None)),
        "diagnostic_counts_limitations": "Counts exclude inherited review records. Truncated diagnostic counts are lower bounds. "
            "Final-assembly counts include only observations attached to its snapshot; unscoped findings are separate. "
            "AABB overlaps are candidates, not certified collisions."}


def _comparison(scene, baseline):
    if (scene.set_number, scene.guide_id, scene.source_sha256) != (
            baseline.set_number, baseline.guide_id, baseline.source_sha256):
        raise ValueError("Baseline belongs to a different guide or source revision")
    old, current = ({part.instance_id: part for part in item.instances} for item in (baseline, scene))
    old_steps = {step.step_id: step for step in baseline.steps}
    changed = []
    for step in scene.steps:
        before = old_steps.get(step.step_id)
        if before is None:
            changed.append({"step_id": step.step_id, "kind": "new_snapshot"})
            continue
        ids = [identity for identity, pose in step.poses.items()
               if identity not in before.poses or not _same_pose(before.poses[identity], pose)]
        if ids:
            changed.append({"step_id": step.step_id, "kind": "changed_pose", "instance_ids": ids})
    return {"baseline_scene_sha256": digest(baseline), "baseline_revision": baseline.revision,
            "comparison_scope": "revision differences only; baseline agreement is not source accuracy",
            "added_instance_ids": sorted(set(current)-set(old)), "removed_instance_ids": sorted(set(old)-set(current)),
            "changed_mapping_ids": sorted(identity for identity in set(old) & set(current)
                if (old[identity].part_id, old[identity].color_code) != (current[identity].part_id, current[identity].color_code)),
            "changed_steps": changed}


def _alternatives(directory, results):
    counts, unknown = [], 0
    for result in results:
        relative = result.get("render_directory")
        if not relative:
            unknown += 1
            continue
        render = directory / relative
        if not render.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Alternative evidence escapes the evaluated job")
        manifest = render.parent.parent / "hypotheses.json"
        if not manifest.is_file():
            unknown += 1
            continue
        value = _read(manifest, 128_000_000, directory)
        candidates = value.get("candidates") if isinstance(value, dict) else None
        beam = value.get("retained_beam", []) if isinstance(value, dict) else []
        if (not isinstance(candidates, list) or len(candidates) > 8
                or not isinstance(beam, list) or len(beam) > 8):
            raise ValueError("Invalid bounded candidate-alternative receipt")
        scenes, selected_for_render, abbreviated = {}, set(), 0
        for selected, records in ((True, candidates), (False, beam)):
            for item in records:
                if not isinstance(item, dict):
                    raise ValueError("Invalid candidate-alternative record")
                if item.get("scene") is None:
                    # Older beam summaries have IDs/scores but no inspectable scene.
                    # Their distinctness cannot be verified from abbreviated hashes.
                    abbreviated += 1
                    continue
                scene = SceneV2.model_validate(item["scene"])
                scene_hash = digest(scene)
                scenes[scene_hash] = scene
                if selected:
                    selected_for_render.add(scene_hash)
        rendered = set()
        for index, path in enumerate(sorted(manifest.parent.rglob("report.json"))):
            if index >= 2000:
                raise ValueError("Alternative render evidence exceeds evaluation bound")
            receipt = _read(path, root=directory)
            if not isinstance(receipt, dict) or receipt.get("status") != "rendered":
                continue
            scene_hash = receipt.get("scene_sha256")
            if scene_hash in scenes and _render_images(path.parent, scenes[scene_hash]):
                rendered.add(scene_hash)
        selected_hash = result.get("provisional_scene_sha256")
        selected_known = selected_hash in scenes
        lower_bound = max(0, len(scenes) - (1 if selected_known or selected_hash is None else 0))
        count = lower_bound if selected_known and not abbreviated else None
        counts.append({"instruction_ordinal": result.get("ordinal"), "retained_alternatives": count,
            "retained_alternatives_lower_bound": lower_bound, "archived_distinct_candidates": len(scenes),
            "render_selected_distinct_candidates": len(selected_for_render),
            "rendered_distinct_candidates": len(rendered), "unrendered_distinct_candidates": len(set(scenes)-rendered),
            "abbreviated_records_with_unknown_distinctness": abbreviated,
            "selected_scene_present_in_archive": selected_known,
            "count_status": "complete" if count is not None else "lower_bound"})
    complete = counts and not unknown and all(item["retained_alternatives"] is not None for item in counts)
    return {"retained_candidate_alternatives": sum(item["retained_alternatives"] for item in counts) if complete else None,
            "retained_alternatives_lower_bound": sum(item["retained_alternatives_lower_bound"] for item in counts),
            "archived_distinct_candidates": sum(item["archived_distinct_candidates"] for item in counts),
            "rendered_distinct_candidates": sum(item["rendered_distinct_candidates"] for item in counts),
            "instructions_with_records": len(counts), "instructions_without_records": unknown,
            "instructions": counts, "scope": "Distinct validated full-scene digests within each instruction archive; "
                "rendered counts require actual hash-verified pixels. Abbreviated legacy beam records remain unknown. "
                "Source correctness remains unresolved."}


def _render_images(directory, scene):
    images = {}
    if not directory or not Path(directory).is_dir():
        return images
    directory = Path(directory)
    steps = {step.step_id: step for step in scene.steps}
    for index, path in enumerate(sorted(directory.rglob("report.json"))):
        if index >= 2000:
            raise ValueError("Render evidence exceeds evaluation bound")
        report = _read(path, root=directory)
        if not isinstance(report, dict) or report.get("status") != "rendered":
            continue
        if report.get("scene_sha256") != digest(scene):
            # An instruction render is valid only if its exact candidate prefix
            # still occurs in this revision. A corrected pose invalidates it.
            source = path.parent.parent / "scene.json"
            if not source.is_file():
                continue
            prior = SceneV2.model_validate(_read(source, 128_000_000, directory))
            if digest(prior) != report.get("scene_sha256"):
                continue
            if (scene.steps[:len(prior.steps)] != prior.steps
                    or scene.instances[:len(prior.instances)] != prior.instances):
                continue
        for item in report.get("steps", []):
            if not isinstance(item, dict) or item.get("step_id") not in steps:
                continue
            picture = path.parent / item.get("screenshot", "")
            if (picture.is_symlink() or not picture.is_file() or picture.stat().st_size > 32_000_000
                    or not picture.resolve().is_relative_to(path.parent.resolve())):
                raise ValueError("Render image is not a bounded local evidence file")
            if hashlib.sha256(picture.read_bytes()).hexdigest() != item.get("png_sha256"):
                raise ValueError("Render image hash differs from its receipt")
            images[item["step_id"]] = {"path": picture, "sha256": item["png_sha256"],
                                       "camera_mode": item.get("camera_mode", "overview_unaligned"),
                                       "source_camera": item.get("source_camera"),
                                       "render_receipt_path": str(path),
                                       "render_receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                       "render_scene_sha256": report.get("scene_sha256")}
    return images


def _parent_prefix_images(store, job, scene, directory, visited=()):
    """Reuse only unchanged pre-correction snapshots with an authenticated lineage.

    A correction's copied parent, durable fork row, current frozen parent and
    render receipts must agree. Recursing through at most two correction passes
    permits an unchanged prefix to retain the original pixels across both forks.
    """
    lineage = job["checkpoint"].get("correction_lineage", [])
    if not lineage:
        return {}
    if job["id"] in visited or len(visited) >= 2:
        raise ValueError("Correction render lineage exceeds its bound or contains a cycle")
    record = lineage[-1]
    receipt = _read(directory / "correction.json", root=store.root)
    with store.connect() as connection:
        durable = connection.execute("SELECT parent_job_id,parent_scene_sha256,request_sha256,correction_id "
            "FROM engine_corrections WHERE child_job_id=?", (job["id"],)).fetchone()
    if durable is None or any(record.get(key) != durable[key] or receipt.get(key) != durable[key]
                              for key in ("parent_job_id", "parent_scene_sha256", "request_sha256", "correction_id")):
        raise ValueError("Correction parent render lineage differs from its durable fork receipt")
    copied_parent = SceneV2.model_validate(_read(directory / "parent-scene.json", 128_000_000, store.root))
    parent = store.get(record["parent_job_id"])
    parent_directory = store.root / "jobs" / parent["id"]
    parent_scene = SceneV2.model_validate(_read(parent_directory / "scene.json", 128_000_000, store.root))
    if (digest(copied_parent) != record["parent_scene_sha256"] or digest(parent_scene) != record["parent_scene_sha256"]
            or digest(parent.get("checkpoint", {}).get("candidate")) != record["parent_scene_sha256"]):
        raise ValueError("Parent scene differs from correction render lineage")
    from .corrections import verify_scene_source
    verify_scene_source(store, parent, parent_scene)
    if (scene.set_number, scene.guide_id, scene.source_sha256, scene.sources, scene.sections) != (
            parent_scene.set_number, parent_scene.guide_id, parent_scene.source_sha256, parent_scene.sources, parent_scene.sections):
        raise ValueError("Correction parent render source identity differs from its child")
    first = record.get("first_affected_step_index")
    if type(first) is not int or not 0 <= first <= len(parent_scene.steps) or receipt.get("first_affected_step_index") != first:
        raise ValueError("Correction render prefix boundary is invalid")
    parent_parts = {part.instance_id: part for part in parent_scene.instances}
    current_parts = {part.instance_id: part for part in scene.instances}
    def rendered_part(part):
        # A later correction changes authorship labels globally. They are not
        # visible mesh state; preserve all identity, material, geometry and source
        # fields, and record the two excluded provenance fields in the reuse proof.
        return part.model_dump(mode="json", exclude={"origin", "mapping_status"}) if part else None
    reusable, introduced = [], set()
    for old, current in zip(parent_scene.steps[:first], scene.steps[:first]):
        introduced.update(old.introduced_instance_ids)
        relevant = introduced | set(old.visible_instance_ids)
        if old != current or any(rendered_part(parent_parts.get(identity)) != rendered_part(current_parts.get(identity))
                                 for identity in relevant):
            break
        reusable.append(current.step_id)
    if not reusable:
        return {}
    inherited = _parent_prefix_images(store, parent, parent_scene, parent_directory, (*visited, job["id"]))
    inherited.update(_render_images(parent_directory, parent_scene))
    return {identity: image | {"reused_parent_render": True,
        "reuse_lineage": [*image.get("reuse_lineage", []), {"parent_job_id": parent["id"], "child_job_id": job["id"],
            "parent_scene_sha256": record["parent_scene_sha256"], "child_scene_sha256": digest(scene),
            "correction_id": record["correction_id"], "request_sha256": record["request_sha256"],
            "unchanged_prefix_steps": len(reusable),
            "ignored_nonvisual_instance_fields": ["origin", "mapping_status"]}]}
        for identity, image in inherited.items() if identity in reusable}


def _comparison_render(image, output, name, bbox):
    """Preserve original pixels and derive a source-region crop for fitted cameras."""
    from PIL import Image
    original_name = name.replace(".png", "-original.png") if image["camera_mode"] == "source_orthographic" else name
    shutil.copyfile(image["path"], output / original_name)
    if hashlib.sha256((output / original_name).read_bytes()).hexdigest() != image["sha256"]:
        raise ValueError("Copied comparison pixels differ from their verified render evidence")
    result = {"file": original_name, "sha256": image["sha256"], "camera_mode": image["camera_mode"],
              "original_file": original_name, "original_sha256": image["sha256"]}
    for key in ("render_receipt_path", "render_receipt_sha256", "render_scene_sha256", "reused_parent_render", "reuse_lineage"):
        if key in image:
            result[key] = image[key]
    if image["camera_mode"] != "source_orthographic":
        return result
    frame = image.get("source_camera")
    if not isinstance(frame, dict) or not isinstance(frame.get("source_rect"), dict):
        result["crop_status"] = "unavailable_unverified_source_frame"
        return result
    rect, viewport = frame["source_rect"], frame.get("viewport", {})
    values = [rect.get(key) for key in ("x", "y", "width", "height")]
    if any(not _number(value) for value in values) or min(rect["width"], rect["height"]) <= 0:
        raise ValueError("Invalid rendered source frame for comparison crop")
    with Image.open(image["path"]) as picture:
        if picture.width * picture.height > 32_000_000:
            raise ValueError("Comparison render exceeds pixel bound")
        # The current renderer clips to the full source page; old receipts may
        # contain the complete canvas with a source rectangle inside it.
        if abs(picture.width-rect["width"]) <= 2 and abs(picture.height-rect["height"]) <= 2:
            x, y, width, height = 0., 0., picture.width, picture.height
            frame_basis = "screenshot_already_clipped_to_source_page"
        elif (all(_number(viewport.get(key)) for key in ("width", "height"))
              and abs(picture.width-viewport["width"]) <= 2 and abs(picture.height-viewport["height"]) <= 2):
            x, y, width, height = values
            frame_basis = "source_rectangle_inside_canvas"
        else:
            raise ValueError("Rendered pixels do not match their recorded source frame")
        left, top, right, bottom = bbox
        crop = (max(0, math.floor(x+left*width)), max(0, math.floor(y+top*height)),
                min(picture.width, math.ceil(x+right*width)), min(picture.height, math.ceil(y+bottom*height)))
        if crop[2] <= crop[0] or crop[3] <= crop[1]:
            raise ValueError("Source-aligned comparison crop is empty")
        picture.crop(crop).save(output / name)
    result.update(file=name, sha256=hashlib.sha256((output / name).read_bytes()).hexdigest(),
                  crop_status="derived_source_panel", source_bbox=list(bbox), crop_pixels=list(crop),
                  frame_basis=frame_basis)
    return result


def _source_crop(store, source, destination):
    from PIL import Image
    directory = store.data_dir / "public/pages" / source.source_sha256
    manifest = directory / "pages.json"
    if not manifest.is_file():
        return None
    records = _read(manifest, root=store.data_dir)
    if not isinstance(records, list):
        raise ValueError("Source page manifest must be a list")
    record = next((item for item in records if isinstance(item, dict)
                   and item.get("page_index") == source.page_index), None)
    if record is None:
        return None
    picture = directory / record.get("file", "")
    if (picture.is_symlink() or not picture.is_file() or picture.stat().st_size > 32_000_000
            or not picture.resolve().is_relative_to(directory.resolve())):
        raise ValueError("Source image escapes its cache")
    if hashlib.sha256(picture.read_bytes()).hexdigest() != record.get("sha256"):
        raise ValueError("Source page differs from its page receipt")
    with Image.open(picture) as image:
        if image.width * image.height > 32_000_000:
            raise ValueError("Source page exceeds evaluation pixel bound")
        x0, y0, x1, y1 = source.bbox
        image.crop((int(x0*image.width), int(y0*image.height), math.ceil(x1*image.width),
                    math.ceil(y1*image.height))).save(destination)
    return {"file": destination.name, "source_page_sha256": record["sha256"],
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}


def _comparison_steps(scene, results, sources):
    """Include unresolved source panels without inventing scene snapshots for them."""
    from .corrections import _source_evidence
    steps = {step.step_id: step for step in scene.steps}
    indexed, mapped, unresolved = [], set(), []
    for result in results:
        ordinal = result.get("ordinal")
        for identity in result.get("step_ids", []):
            if identity in steps and identity not in mapped:
                indexed.append((steps[identity], ordinal, True))
                mapped.add(identity)
        if result.get("reconstructed") is False:
            panel = result.get("panel", {})
            source = None
            if "bbox" in panel and "page_index" in result:
                source = SourcePanel(source_sha256=scene.source_sha256,
                    page_index=result["page_index"], bbox=panel["bbox"])
                _source_evidence(source, sources)
            label = ordinal + 1 if type(ordinal) is int else len(unresolved) + 1
            gap = (SimpleNamespace(step_id=f"unresolved-{label}", main_step_number=panel.get("number"),
                source=source, substep_label=panel.get("label"), action=None), ordinal, False)
            indexed.append(gap)
            unresolved.append(gap)
    # Exploration has a complete result-to-snapshot map. Older strict records
    # may only retain failures; preserve their original scene order in that case.
    if mapped == set(steps):
        return indexed
    return [(step, None, True) for step in scene.steps] + unresolved


def _instruction_coverage(scene, checkpoint, reference, execution_policy):
    mains = {step.main_step_number for step in scene.steps if step.main_step_number is not None}
    results = checkpoint.get("instruction_results", [])
    processed = checkpoint.get("processed_panels", checkpoint.get("completed_panels"))
    processed_basis = "durable_instruction_checkpoint"
    if execution_policy == "explore":
        if checkpoint.get("processed_panels") is None:
            processed, processed_basis = len(results), "durable_instruction_results"
        reconstructed = checkpoint.get("reconstructed_panels")
        reconstructed_basis = "durable_instruction_checkpoint"
        if reconstructed is None:
            reconstructed = sum(result.get("reconstructed") is True for result in results)
            reconstructed_basis = "durable_instruction_results"
        if not scene.steps:
            reconstructed = 0
        expected = checkpoint.get("total_panels")
        unit = "indexed_instruction_panels_including_attachments"
    else:
        if processed is None:
            processed, processed_basis = len(mains), "reconstructed_main_steps_lower_bound"
        reconstructed, reconstructed_basis = len(mains), "distinct_reconstructed_main_steps"
        expected = (len(reference.expected_main_steps) if reference and reference.expected_main_steps
                    else checkpoint.get("total_panels"))
        unit = "legacy_main_instruction_count"
    expected_mains = set(reference.expected_main_steps) if reference and reference.expected_main_steps else {
        panel["number"] for page in checkpoint.get("page_indexes", []) for panel in page.get("panels", [])
        if panel.get("kind") == "main" and type(panel.get("number")) is int}
    main_basis = "source_reviewed_annotations" if reference and reference.expected_main_steps else "source_panel_index"
    return {"processed_instructions": processed, "processed_count_basis": processed_basis,
        "reconstructed_instructions": reconstructed, "reconstructed_count_basis": reconstructed_basis,
        "instruction_count_unit": unit, "reconstructed_main_steps": len(mains),
        "reconstructed_microsteps": len(scene.steps),
        "unreconstructed_processed_instructions": max(0, processed-reconstructed),
        "expected_instructions": expected, "expected_main_steps": len(expected_mains) if expected_mains else None,
        "main_step_coverage": {"reconstructed": len(mains & expected_mains) if expected_mains else len(mains),
            "expected": len(expected_mains) if expected_mains else None,
            "missing_numbers": sorted(expected_mains-mains) if expected_mains else None,
            "unexpected_numbers": sorted(mains-expected_mains) if expected_mains else None,
            "basis": main_basis if expected_mains else "unavailable",
            "scope": "A retained snapshot carries the main number; completeness and source accuracy remain unverified."},
        "expected_microsteps": reference.expected_microsteps if reference else None,
        "processed_pages": checkpoint.get("completed_pages", checkpoint.get("alpha_completed_pages")),
        "physical_instances": len(scene.instances)}


def _write_comparison(store, report, scene, directory, output, baseline=None, baseline_dir=None, refreshed=None,
                      results=(), sources=None, inherited_images=None):
    after_images = dict(inherited_images or {})
    if isinstance(scene, SceneV2):
        after_images.update(_render_images(directory, scene))
    if refreshed:
        after_images.update(_render_images(refreshed, scene))
    before_images = _render_images(baseline_dir, baseline) if baseline else {}
    def source_key(step):
        if step.source is None:
            return None
        return (step.source.source_sha256, step.source.page_index, step.main_step_number,
                getattr(step, "substep_label", None), getattr(step, "action", None))
    comparison_steps = _comparison_steps(scene, results, sources)
    before_keys, current_keys = {}, Counter(source_key(step) for step, _, _ in comparison_steps)
    if baseline:
        for step in baseline.steps:
            before_keys.setdefault(source_key(step), []).append(step.step_id)
    cards, evidence = [], []
    for index, (step, ordinal, reconstructed) in enumerate(comparison_steps):
        slug = f"{index+1:05d}"
        source = _source_crop(store, step.source, output / f"source-{slug}.png") if step.source else None
        row = {"step_id": step.step_id, "instruction_ordinal": ordinal, "reconstructed": reconstructed,
               "source": source, "before": None, "after": None}
        source_label = f'Official source, page {step.source.page_index+1}' if step.source else 'Official source'
        columns = [f'<figure><figcaption>{source_label}</figcaption>' +
                   (f'<img alt="Official instruction crop" src="{source["file"]}">' if source else
                    '<p>Source crop unavailable.</p>') + '</figure>']
        for label, images in (("before", before_images), ("after", after_images)):
            image = images.get(step.step_id) if reconstructed else None
            match_basis = ("unchanged_parent_prefix" if image.get("reused_parent_render") else "same_step_id") if image else None
            if label == "before" and image is None and reconstructed:
                matches = before_keys.get(source_key(step), [])
                if len(matches) == 1 and current_keys[source_key(step)] == 1:
                    image = images.get(matches[0])
                    match_basis = "unique_source_page_main_substep_action" if image else None
            if image:
                name = f"{label}-{slug}.png"
                row[label] = _comparison_render(image, output, name, step.source.bbox) | {"match_basis": match_basis}
                camera_label = ("Source-aligned camera; assembly accuracy remains unverified" if image["camera_mode"] == "source_orthographic"
                                else "Overview camera — source alignment unavailable")
                body = f'<img alt="{label.title()} reconstruction" src="{row[label]["file"]}"><p>{camera_label}</p>'
                if image.get("reused_parent_render"):
                    body += '<p>Unchanged parent snapshot; original render hashes verified.</p>'
            else:
                body = ('<p>Not rendered for this revision.</p>' if reconstructed else
                        '<p>Unresolved instruction — no reconstructed snapshot.</p>')
            columns.append(f'<figure><figcaption>{label.title()}</figcaption>{body}</figure>')
        findings = [item for item in report["findings"] if item.get("step_id") == step.step_id
                    or step.step_id in item.get("step_ids", [])
                    or ordinal is not None and item.get("instruction_ordinal") == ordinal]
        notes = ''.join(f'<li>{html.escape(str(item.get("message", item.get("description", item.get("reason", item.get("code", "Review finding"))))))}</li>'
                        for item in findings)
        cards.append(f'<section><h2>{html.escape(step.step_id)} · main {step.main_step_number}</h2>'
                     f'<div class="views">{"".join(columns)}</div><ul>{notes}</ul></section>')
        evidence.append(row)
    content = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
    content += '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'">'
    content += '<title>Reconstruction comparison</title><style>body{font:16px system-ui;max-width:1500px;margin:24px auto;padding:0 20px;background:#f7f7fa;color:#171820}.views{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}figure{margin:0;background:white;padding:12px}img{max-width:100%}section{margin:32px 0}figcaption{font-weight:600}p{line-height:1.5}@media(max-width:800px){.views{grid-template-columns:1fr}}</style>'
    content += '<h1>Reconstruction comparison</h1><p>Private official-source evidence. Candidate quality findings remain open. '
    content += 'Baseline differences do not establish source accuracy. Agent corrections are assisted; human and physical review are not inferred.</p>'
    content += f'<p>{report["coverage"]["processed_instructions"]} processed; {report["coverage"]["reconstructed_instructions"]} reconstructed. '
    content += f'{len(report["findings"])} findings.</p>' + ''.join(cards) + '</html>'
    (output / "comparison.html").write_text(content)
    return evidence


def _output_directory(store, report, output):
    output = Path(output) if output is not None else store.data_dir / "evidence" / f"evaluation-{report['job_id']}-{digest(report)[:12]}"
    output = output.absolute()
    if (output.is_symlink() or not output.resolve().is_relative_to(store.data_dir.resolve())
            or output.resolve().is_relative_to((store.data_dir / "public").resolve())):
        raise ValueError("Evaluation output must remain in private local evidence storage")
    if output.exists():
        raise ValueError("Evaluation evidence directory already exists; choose a new immutable output")
    output.mkdir(parents=True)
    return output


def _evaluate_without_candidate(store, job, reference_path, baseline_path, output):
    """An all-unresolved experiment still has measurable processed source coverage."""
    from ..catalog import find_guide
    from .corrections import verify_scene_source, _source_evidence
    checkpoint = job["checkpoint"]
    guide = find_guide(job["set_number"], job["guide_id"])
    source_hash = checkpoint.get("source_sha256")
    source = Source(guide_id=job["guide_id"], source_sha256=source_hash,
                    official_url=guide["pdf_url"], page_count=checkpoint.get("page_count", guide.get("expected_page_count")))
    empty = SimpleNamespace(set_number=job["set_number"], guide_id=job["guide_id"], source_sha256=source_hash,
                            sources=[source], instances=[], steps=[])
    sources = verify_scene_source(store, job, empty)
    reference = EvaluationReference.model_validate(_read(reference_path)) if reference_path else None
    if reference:
        if (reference.set_number, reference.guide_id, reference.source_sha256) != (
                job["set_number"], job["guide_id"], source_hash):
            raise ValueError("Scoring annotations belong to a different guide or source")
        for item in [*reference.instances, *reference.quantities]:
            _source_evidence(item.evidence, sources)
    if baseline_path:
        baseline = SceneV2.model_validate(_read(baseline_path, 128_000_000))
        if (baseline.set_number, baseline.guide_id, baseline.source_sha256) != (empty.set_number, empty.guide_id, source_hash):
            raise ValueError("Baseline belongs to a different guide or source revision")
    directory = store.root / "jobs" / job["id"]
    results = checkpoint.get("instruction_results", [])
    findings = []
    for result in results:
        for finding in result.get("findings", []):
            finding = finding if isinstance(finding, dict) else {"description": str(finding)}
            findings.append(dict(finding, instruction_ordinal=result.get("ordinal")))
    report = {"schema_version": "1.0", "artifact_kind": "reconstruction_evaluation", "job_id": job["id"],
        "set_number": empty.set_number, "guide_id": empty.guide_id, "source_sha256": source_hash,
        "scene_sha256": None, "revision": job["config"].get("revision"), "candidate_status": "unavailable",
        "execution_policy": job["config"].get("execution_policy", "strict"),
        "coverage": _instruction_coverage(empty, checkpoint, reference, job["config"].get("execution_policy", "strict")),
        "source_scores": score_scene(empty, reference), "reference_sha256": digest(reference) if reference else None,
        "findings": findings, "diagnostic_checks": {"geometry": "not_run", "connectors": "not_run"},
        "finding_counts": dict(Counter(item.get("code", item.get("category", "unresolved")) for item in findings)),
        "aggregate_finding_count": len(findings), "finding_counts_basis": "combined review records; repeated observations are not distinct defects",
        **_diagnostic_counts({"findings": []}),
        "measurements": summarize_job_calls(directory), "correction_lineage": checkpoint.get("correction_lineage", []),
        "correction_count": 0, "human_review": "not_established", "physical_build": "not_run",
        "limitations": ["Instructions were processed but no renderable candidate was retained.",
                        "Source annotations alone are not a reconstructed scene."]}
    output = _output_directory(store, report, output)
    report["instruction_comparisons"] = _write_comparison(store, report, empty, directory, output,
        results=results, sources=sources)
    report["artifacts"] = {"report": str(output / "report.json"), "comparison_html": str(output / "comparison.html")}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def evaluate_job(store, job_id, reference_path=None, baseline_path=None, output=None):
    """Write a private report; corrected revisions also refresh affected local renders.

    Parent/evaluated jobs and previous evidence are unchanged. No model inference
    occurs. Fresh and baseline candidates use only their existing render evidence.
    """
    job = store.get(job_id)
    checkpoint = job["checkpoint"]
    candidate = checkpoint.get("candidate")
    if not candidate:
        return _evaluate_without_candidate(store, job, reference_path, baseline_path, output)
    scene = SceneV2.model_validate(candidate)
    directory = store.root / "jobs" / job_id
    if digest(SceneV2.model_validate(_read(directory / "scene.json", 128_000_000, store.root))) != digest(scene):
        raise ValueError("Stored scene differs from its checkpoint")
    from .corrections import verify_scene_source, _source_evidence
    sources = verify_scene_source(store, job, scene)
    reference = EvaluationReference.model_validate(_read(reference_path)) if reference_path else None
    if reference:
        if (reference.set_number, reference.guide_id, reference.source_sha256) != (
                scene.set_number, scene.guide_id, scene.source_sha256):
            raise ValueError("Scoring annotations belong to a different guide or source")
        for item in [*reference.instances, *reference.quantities]:
            _source_evidence(item.evidence, sources)
    baseline = SceneV2.model_validate(_read(baseline_path, 128_000_000)) if baseline_path else None
    diagnostics = diagnose(scene, directory / "geometry")
    findings = list(diagnostics.get("findings", []))
    for result in checkpoint.get("instruction_results", []):
        for finding in result.get("findings", []):
            if isinstance(finding, str):
                finding = {"code": "instruction_review", "severity": "review", "message": finding}
            if isinstance(finding, dict):
                findings.append(dict(finding, step_ids=result.get("step_ids", []), instruction_ordinal=result.get("ordinal")))
    for note in checkpoint.get("uncertainty_notes", checkpoint.get("alpha_review_notes", [])):
        findings.append(note if isinstance(note, dict) else {"code": "unresolved", "message": str(note)})
    findings = list({digest(item): item for item in findings}.values())
    priority = {"missing_piece": 0, "wrong_part": 0, "nonrigid_group": 1, "historical_movement": 1,
                "exact_coincident_geometry": 2, "floating_supported_instance": 2, "near_connector_gap": 2,
                "aabb_overlap_candidate": 3, "unsupported_connector_geometry": 4}
    findings.sort(key=lambda finding: (priority.get(finding.get("code"), 5), str(finding.get("step_id", ""))))
    results = checkpoint.get("instruction_results", [])
    calls = summarize_job_calls(directory)
    calls["inherited_model_calls_used"] = checkpoint.get("inherited_model_calls_used", 0)
    calls["budget_reservations_used"] = checkpoint.get("model_calls_used")
    calls["max_model_calls"] = job["config"].get("max_model_calls")
    score = score_scene(scene, reference)
    alternatives = _alternatives(directory, results)
    artifact_kind = checkpoint.get("artifact_kind", job["config"].get("artifact_kind", "unclassified_candidate"))
    report = {"schema_version": "1.0", "artifact_kind": "reconstruction_evaluation", "job_id": job_id,
        "set_number": scene.set_number, "guide_id": scene.guide_id, "revision": scene.revision,
        "source_sha256": scene.source_sha256, "scene_sha256": digest(scene),
        "execution_policy": job["config"].get("execution_policy", "strict"),
        "generation_mode": job["config"].get("generation_mode", "strict"),
        "candidate_artifact_kind": artifact_kind,
        "assisted": bool(checkpoint.get("correction_lineage") or checkpoint.get("alpha_assisted_corrections")
                         or checkpoint.get("assisted_lineage") or "assisted" in artifact_kind or "corrected" in artifact_kind
                         or any(part.origin != "vision_proposal" for part in scene.instances)),
        "coverage": _instruction_coverage(scene, checkpoint, reference, job["config"].get("execution_policy", "strict")),
        "source_scores": score, "reference_sha256": digest(reference) if reference else None,
        "reference_actor": reference.actor if reference else None,
        "diagnostic_checks": diagnostics.get("checks", {}), "findings": findings,
        "finding_counts": dict(Counter(item.get("code", item.get("category", "unresolved")) for item in findings)),
        "aggregate_finding_count": len(findings), "finding_counts_basis": "combined review records; repeated observations are not distinct defects",
        **_diagnostic_counts(diagnostics, scene.steps[-1].step_id),
        "measurements": calls, "correction_lineage": checkpoint.get("correction_lineage", []),
        "correction_count": sum(len(item.get("changes", [])) for item in checkpoint.get("correction_lineage", [])),
        "repair_passes": len(checkpoint.get("correction_lineage", [])),
        "remaining_alternatives": alternatives["retained_candidate_alternatives"], "alternative_evidence": alternatives,
        "baseline_comparison": _comparison(scene, baseline) if baseline else None,
        "human_review": "not_established", "physical_build": "not_run",
        "limitations": ["Unannotated source attributes are unknown, not correct.",
            "Bounding-box overlaps are collision candidates, not confirmed mesh collisions.",
            "Pose agreement cannot establish hidden connectors, strength or physical assembly.",
            "Provider token and timing totals use actual local receipts; unavailable usage stays unreported."]}
    if baseline:
        before_diagnostics = diagnose(baseline, directory / "geometry")
        report["baseline_comparison"]["before_finding_counts"] = dict(Counter(
            item["code"] for item in before_diagnostics.get("findings", [])))
        report["baseline_comparison"]["before_diagnostic_counts"] = _diagnostic_counts(before_diagnostics, baseline.steps[-1].step_id)
        report["baseline_comparison"]["before_source_scores"] = score_scene(baseline, reference)
    inherited_images = _parent_prefix_images(store, job, scene, directory)
    report["reused_parent_prefix_render_step_ids"] = [step.step_id for step in scene.steps if step.step_id in inherited_images]
    output = _output_directory(store, report, output)
    refreshed = None
    if checkpoint.get("correction_lineage"):
        from .corrections import refresh_correction_evidence
        refreshed = output / "correction-refresh"
        report["correction_evidence_refresh"] = refresh_correction_evidence(store, job_id, refreshed)
    report["instruction_comparisons"] = _write_comparison(store, report, scene, directory, output,
        baseline, Path(baseline_path).parent if baseline_path else None, refreshed, results, sources, inherited_images)
    report["artifacts"] = {"report": str(output / "report.json"), "comparison_html": str(output / "comparison.html")}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report
