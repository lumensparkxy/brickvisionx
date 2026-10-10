"""Source-bound, immutable correction branches with full rigid-transform replay.

Corrections are assisted evidence, never a new unassisted accuracy result. Nothing
here performs inference, downloads assets, certifies geometry, or changes a parent.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..catalog import find_guide
from ..core.models import Pose, SourcePanel, StrictModel
from ..jobs.source_cache import cached_receipt
from ..releases.models import SceneV2, canonical, digest
from .geometry import verify_individual_assets
from .source_view import SourceViewObservation
from .spatial import _product, _quaternion, _rigid_move, _transpose
from .connectors import rotation_matrix, transform_vector
from .store import PIPELINE


class _Command(StrictModel):
    reason: str = Field(min_length=1, max_length=2000)
    evidence: SourcePanel


class MappingCorrection(_Command):
    op: Literal["mapping"]
    instance_id: str = Field(min_length=1, max_length=160)
    part_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    color_code: str = Field(pattern=r"^[0-9]{1,5}$")


class PoseCorrection(_Command):
    op: Literal["pose"]
    step_id: str = Field(min_length=1, max_length=160)
    instance_id: str = Field(min_length=1, max_length=160)
    pose: Pose


class GroupCorrection(_Command):
    op: Literal["group"]
    step_id: str = Field(min_length=1, max_length=160)
    group_id: str = Field(min_length=1, max_length=160)
    anchor_instance_id: str = Field(min_length=1, max_length=160)
    pose: Pose


class GroupingCorrection(_Command):
    op: Literal["grouping"]
    step_id: str = Field(min_length=1, max_length=160)
    group_id: str = Field(min_length=1, max_length=160)


class LandmarkCorrection(_Command):
    op: Literal["landmark"]
    observation: SourceViewObservation


Command = Annotated[MappingCorrection | PoseCorrection | GroupCorrection | GroupingCorrection | LandmarkCorrection,
                    Field(discriminator="op")]


class SourceOnlyIndexReview(StrictModel):
    """Agent acknowledgement of one exact empty, failed source-page observation.

    This is not a replacement provider result or permission to suppress a region.
    The original empty index and its indexing uncertainty remain unchanged.
    """

    actor: Literal["agent"]
    conclusion: Literal["no_construction"]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_index: int = Field(strict=True, ge=0)
    page_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    index_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    failed_request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    failed_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    process_result_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: str = Field(min_length=1, max_length=2000)


class CorrectionRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    correction_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$")
    expected_scene_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor: Literal["agent"] = "agent"
    reason: str = Field(min_length=1, max_length=4000)
    evidence: list[SourcePanel] = Field(min_length=1, max_length=64)
    commands: list[Command] = Field(default_factory=list, max_length=64)
    restart_main_step: int | None = Field(default=None, ge=1, le=10000)
    guidance: list[str] = Field(default_factory=list, max_length=64)
    context_page_indexes: list[Annotated[int, Field(strict=True, ge=0)]] | None = Field(default=None, max_length=2)
    max_panel_attempts: int | None = Field(default=None, strict=True, ge=1, le=2)
    review_profile: Literal["localized-source-v4"] | None = None
    source_reference_profile: Literal["exact-source-v1"] | None = None
    source_only_index_reviews: list[SourceOnlyIndexReview] | None = Field(default=None, min_length=1, max_length=2)

    @model_validator(mode="after")
    def bounded_mode(self):
        if bool(self.commands) == (self.restart_main_step is not None):
            raise ValueError("Use commands or restart_main_step, exclusively")
        if any(not text.strip() or len(text) > 4000 for text in self.guidance):
            raise ValueError("Correction guidance must contain bounded nonempty findings")
        if self.restart_main_step is not None and not self.guidance:
            raise ValueError("A model repair fork requires source-backed finding guidance")
        if self.restart_main_step is None and (self.context_page_indexes is not None or self.max_panel_attempts is not None):
            raise ValueError("Context pages and attempt controls require restart_main_step")
        if self.review_profile is not None and self.restart_main_step is None:
            raise ValueError("A source review profile control requires restart_main_step")
        if self.source_reference_profile is not None and self.restart_main_step is None:
            raise ValueError("A source reference profile control requires restart_main_step")
        if self.context_page_indexes is not None:
            if len(set(self.context_page_indexes)) != len(self.context_page_indexes):
                raise ValueError("Correction context page indexes must be unique")
            if not set(self.context_page_indexes) <= {panel.page_index for panel in self.evidence}:
                raise ValueError("Every correction context page must be cited in request evidence")
        if self.source_only_index_reviews:
            pages = [(item.source_sha256, item.page_index) for item in self.source_only_index_reviews]
            if len(set(pages)) != len(pages):
                raise ValueError("Source-only index review pages must be unique")
            whole_pages = {(panel.source_sha256, panel.page_index) for panel in self.evidence
                           if list(panel.bbox) == [0, 0, 1, 1]}
            if not set(pages) <= whole_pages or any(not item.reason.strip() for item in self.source_only_index_reviews):
                raise ValueError("Source-only index reviews require whole-page evidence and a nonempty reason")
        return self


def _read_json(path: Path, limit=1_000_000):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Missing, unsafe or oversized correction input")
    return json.loads(path.read_text())


def _json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def verify_scene_source(store, job, scene):
    """Validate original PDF bytes and curated identities; no network fallback."""
    if (scene.set_number, scene.guide_id) != (job["set_number"], job["guide_id"]):
        raise ValueError("Correction scene identity differs from its job")
    sources = {}
    for source in scene.sources:
        guide = find_guide(scene.set_number, source.guide_id)
        source_dir = store.data_dir / "sources" / scene.set_number / source.guide_id
        for name in ("source.pdf", "source.receipt.json"):
            path = source_dir / name
            if path.is_symlink() or not path.resolve().is_relative_to(store.data_dir.resolve()):
                raise ValueError("Official source evidence escapes the local cache")
        _read_json(source_dir / "source.receipt.json")
        receipt = cached_receipt(store.data_dir, scene.set_number, source.guide_id, guide["pdf_url"])
        if receipt is None or receipt["sha256"] != source.source_sha256:
            raise ValueError("Official source bytes or receipt differ from the correction base")
        if guide.get("expected_page_count") is not None and source.page_count != guide["expected_page_count"]:
            raise ValueError("Scene page count differs from its curated official booklet")
        if source.official_url not in {guide["pdf_url"], guide.get("official_page_url"), guide.get("official_url")}:
            # SceneV2 commonly uses the official service information link.
            expected = f"https://www.lego.com/en-us/service/building-instructions/{scene.set_number}"
            if source.official_url != expected:
                raise ValueError("Scene official source link differs from its curated guide")
        sources[source.source_sha256] = source.page_count
    return sources


def _source_evidence(panel, sources):
    if panel.source_sha256 not in sources or panel.page_index >= sources[panel.source_sha256]:
        raise ValueError("Correction evidence does not name a verified source page")


def _bounded_scene(scene):
    if len(scene.steps) > 10000 or len(scene.instances) > 20000:
        raise ValueError("Correction scene exceeds bounded replay size")
    for step in scene.steps:
        if any(abs(x) > 1_000_000 for pose in step.poses.values() for x in pose.position_ldu):
            raise ValueError("Correction coordinates exceed the supported bound")


def _replay_pose(old_previous, old_next, corrected_previous):
    """Apply the recorded world-space rigid motion, including rotation of offsets."""
    rotation = _product(rotation_matrix(old_next.quaternion_xyzw),
                        _transpose(rotation_matrix(old_previous.quaternion_xyzw)))
    offset = transform_vector(rotation, [corrected_previous.position_ldu[i] - old_previous.position_ldu[i]
                                         for i in range(3)])
    return Pose(position_ldu=[old_next.position_ldu[i] + offset[i] for i in range(3)],
                quaternion_xyzw=_quaternion(_product(rotation,
                                                     rotation_matrix(corrected_previous.quaternion_xyzw))))


def _group_memberships(scene, requested, geometry):
    """Recover nested logical membership without silently splitting an attached child.

    A unique visible target workspace is sufficient for membership, not connector
    certification. Ambiguous target workspaces require a supported contact witness;
    when that is unavailable the requested group edit is explicitly unsupported.
    """
    from .spatial import _contacts
    from .connectors import load_connector_catalogue
    groups, workspaces, timeline = {}, {}, []
    instances = {part.instance_id: part for part in scene.instances}
    for step in scene.steps:
        for identity in step.introduced_instance_ids:
            workspaces[identity] = "main"
        group = step.assembly_group_id
        if step.action == "build_subassembly" and group:
            groups.setdefault(group, set()).update(step.introduced_instance_ids)
            for identity in step.introduced_instance_ids:
                workspaces[identity] = "group:" + group
        if step.action == "attach_subassembly" and group:
            members = groups.get(group, set())
            if not members or not members <= set(step.poses):
                raise ValueError("Cannot correct a group whose attachment omits declared members")
            outside = set(step.poses)-members
            possible = {workspaces[identity] for identity in outside}
            if len(possible) != 1:
                try:
                    metadata, catalogue = load_connector_catalogue(geometry, {instances[i].geometry_ref for i in step.poses})
                    contacts = _contacts(step.poses, instances, catalogue, metadata["tolerance_ldu"])
                    targets = set()
                    for contact in contacts:
                        a, b = contact["stud"][0], contact["socket"][0]
                        if (a in members) != (b in members):
                            targets.add(workspaces[b if a in members else a])
                    possible = targets
                except (ValueError, OSError) as error:
                    raise ValueError("Nested group attachment target is unsupported; supply reviewed grouping evidence before applying a rigid edit") from error
            if len(possible) != 1:
                raise ValueError("Nested group attachment target is ambiguous; rigid correction was not applied")
            target = possible.pop()
            if target == "group:" + group:
                raise ValueError("Cyclic group attachment cannot be corrected as a rigid body")
            if target.startswith("group:"):
                groups[target.removeprefix("group:")].update(members)
            for identity in members:
                workspaces[identity] = target
        timeline.append(set(groups.get(requested, set())))
    return timeline


def _correct_grouping(scene, ordinal, command, geometry):
    """Repair only an attachment label against the already-declared prefix.

    Future labels may need their own later commands in the same request. They do
    not participate in this metadata-only check, and no poses are inferred.
    """
    selected, earlier = scene.steps[ordinal], scene.steps[:ordinal]
    if selected.action != "attach_subassembly" or selected.introduced_instance_ids:
        raise ValueError("Grouping correction requires an attachment snapshot with no new physical pieces")
    if (command.evidence.source_sha256, command.evidence.page_index) != (
            selected.source.source_sha256, selected.source.page_index):
        raise ValueError("Grouping correction must use its attachment instruction's source page")
    declarations = [step for step in earlier if step.action == "build_subassembly"
                    and step.assembly_group_id == command.group_id]
    if not declarations:
        raise ValueError("Grouping correction names an unknown earlier declared detached group")
    if any((step.section_id, step.source.source_sha256) != (selected.section_id, selected.source.source_sha256)
           for step in declarations):
        raise ValueError("Grouping correction has ambiguous declarations across source sections")
    if any(step.action == "attach_subassembly" and step.assembly_group_id == command.group_id for step in earlier):
        raise ValueError("Grouping correction requires a still-detached group; it was already attached")
    prefix = scene.model_copy(update={"steps": earlier})
    membership = _group_memberships(prefix, command.group_id, geometry)
    members = membership[-1] if membership else set()
    if not members or not members <= set(selected.poses):
        raise ValueError("Grouping correction requires complete visible membership of the declared detached group")
    before = selected.assembly_group_id
    selected.assembly_group_id = command.group_id
    # Existing nesting rules resolve one receiving workspace, or a supported
    # contact witness if several are visible. Unsupported ambiguity stays open.
    try:
        _group_memberships(scene.model_copy(update={"steps": scene.steps[:ordinal+1]}), command.group_id, geometry)
    except ValueError as error:
        selected.assembly_group_id = before
        raise ValueError("Grouping correction attachment target is ambiguous or unsupported: " + str(error)) from error
    return {"op": command.op, "step_id": selected.step_id,
        "before": {"assembly_group_id": before}, "after": {"assembly_group_id": command.group_id},
        "member_instance_ids": sorted(members), "assembly_poses_changed": False,
        "dependent_steps_invalidated": len(scene.steps)-ordinal-1}


def _apply_commands(scene, commands, sources, geometry):
    result = scene.model_copy(deep=True)
    steps = {step.step_id: i for i, step in enumerate(result.steps)}
    instances = {part.instance_id: part for part in result.instances}
    changes, landmarks, touched = [], {}, set()
    first = len(result.steps)
    for command in commands:
        _source_evidence(command.evidence, sources)
        if isinstance(command, MappingCorrection):
            if command.instance_id not in instances:
                raise ValueError("Mapping correction names an unknown physical instance")
            part = instances[command.instance_id]
            before = part.model_dump(mode="json")
            part.part_id, part.geometry_ref, part.color_code = (command.part_id,
                f"parts/{command.part_id}.dat", command.color_code)
            part.origin, part.mapping_status = "pdf_assisted_authoring", "candidate"
            first = min(first, next(i for i, step in enumerate(result.steps)
                                    if part.instance_id in step.introduced_instance_ids))
            touched.add(part.instance_id)
            changes.append({"op": command.op, "instance_id": part.instance_id,
                            "before": before, "after": part.model_dump(mode="json")})
            continue
        step_id = command.observation.step_id if isinstance(command, LandmarkCorrection) else command.step_id
        if step_id not in steps:
            raise ValueError("Correction names an unknown instruction")
        ordinal = steps[step_id]
        first = min(first, ordinal)
        selected = result.steps[ordinal]
        if isinstance(command, GroupingCorrection):
            changes.append(_correct_grouping(result, ordinal, command, geometry))
            continue
        if isinstance(command, LandmarkCorrection):
            from .connectors import world_landmark
            if command.evidence.source_sha256 != selected.source.source_sha256:
                raise ValueError("Landmark correction source differs from the instruction")
            if command.evidence.page_index != selected.source.page_index:
                raise ValueError("Landmark correction must use its instruction's page coordinates")
            for landmark in command.observation.landmarks:
                if landmark.instance_id not in selected.poses:
                    raise ValueError("Landmark correction names an invisible piece")
                world_landmark(selected.poses[landmark.instance_id], instances[landmark.instance_id].geometry_ref,
                               landmark.landmark_id, geometry)
            landmarks[step_id] = command.observation.model_dump(mode="json")
            changes.append({"op": command.op, "step_id": step_id, "after": landmarks[step_id],
                            "assembly_poses_changed": False})
            continue
        anchor = command.instance_id if isinstance(command, PoseCorrection) else command.anchor_instance_id
        if anchor not in selected.poses:
            raise ValueError("Pose correction anchor is not visible at the selected instruction")
        old_steps = [step.model_copy(deep=True) for step in result.steps]
        if isinstance(command, GroupCorrection):
            membership = _group_memberships(result, command.group_id, geometry)
            members = membership[ordinal]
            if anchor not in members or not members:
                raise ValueError("Group correction does not identify a declared rigid subassembly")
            if not members <= set(selected.poses):
                raise ValueError("Group correction requires all currently introduced group members")
            previous_anchor = selected.poses[anchor]
            corrected_anchor = command.pose
            for i in range(ordinal, len(result.steps)):
                old_step, new_step = old_steps[i], result.steps[i]
                if anchor in old_step.poses:
                    if i != ordinal:
                        corrected_anchor = _replay_pose(previous_anchor, old_step.poses[anchor], corrected_anchor)
                    previous_anchor = old_step.poses[anchor]
                visible = membership[i] & set(old_step.poses)
                # Hidden anchors retain their most recent gauge; visible new group members
                # inherit that same frame instead of remaining at the old assembly origin.
                poses = dict(old_step.poses) | {anchor: previous_anchor}
                new_step.poses.update(_rigid_move(poses, visible, anchor, corrected_anchor))
            touched.update(set().union(*membership[ordinal:]))
        else:
            previous, corrected = selected.poses[anchor], command.pose
            for i in range(ordinal, len(result.steps)):
                old_step, new_step = old_steps[i], result.steps[i]
                if anchor not in old_step.poses:
                    continue
                if i != ordinal:
                    corrected = _replay_pose(previous, old_step.poses[anchor], corrected)
                previous = old_step.poses[anchor]
                new_step.poses[anchor] = corrected
            touched.add(anchor)
        changes.append({"op": command.op, "step_id": step_id, "anchor_instance_id": anchor,
                        "before": old_steps[ordinal].poses[anchor].model_dump(mode="json"),
                        "after": command.pose.model_dump(mode="json"),
                        "replayed_descendant_steps": len(result.steps) - ordinal - 1})
    for identity in touched:
        instances[identity].origin = "pdf_assisted_authoring"
        instances[identity].mapping_status = "candidate"
    return SceneV2.model_validate(result.model_dump(mode="json")), first, changes, landmarks


def _copy_geometry(source, destination, scene):
    verify_individual_assets(source, [part.geometry_ref for part in scene.instances])
    manifest = _read_json(source / "provenance.json", 32_000_000)
    reachable, pending = set(), [part.geometry_ref for part in scene.instances]
    while pending:
        relative = pending.pop()
        if relative in reachable:
            continue
        reachable.add(relative)
        pending.extend(manifest["resources"][relative].get("dependencies", []))
    destination.mkdir()
    for relative in sorted(reachable | {"LDConfig.ldr"}):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    manifest["resources"] = {key: value for key, value in manifest["resources"].items() if key in reachable}
    manifest["file_map"] = {key: value for key, value in manifest.get("file_map", {}).items() if value in reachable}
    _json(destination / "provenance.json", manifest)
    return verify_individual_assets(destination, [part.geometry_ref for part in scene.instances])


def _verify_materials(scene, geometry):
    material = geometry / "LDConfig.ldr"
    if material.is_symlink() or material.stat().st_size > 1_000_000:
        raise ValueError("Unsafe material configuration")
    colors = set(re.findall(r"^0 !COLOUR\s+\S+\s+CODE\s+(\d+)\b", material.read_text(), re.M))
    if any(part.color_code not in colors or part.color_code in {"16", "24"} for part in scene.instances):
        raise ValueError("Corrected material is not a concrete verified LDraw colour")
    if any(part.geometry_ref != f"parts/{part.part_id}.dat" for part in scene.instances):
        raise ValueError("Corrected part identity differs from its individual geometry")


def _prefix(scene, restart):
    # A failed instruction can be present in the source index but absent from the
    # candidate. Keep all earlier snapshots and retry that unresolved instruction.
    first = next((i for i, step in enumerate(scene.steps)
                  if step.main_step_number is not None and step.main_step_number >= restart), len(scene.steps))
    if first == 0:
        return None, first
    value = scene.model_dump(mode="json")
    value["steps"] = value["steps"][:first]
    ids = {identity for step in value["steps"] for identity in step["introduced_instance_ids"]}
    value["instances"] = [part for part in value["instances"] if part["instance_id"] in ids]
    return SceneV2.model_validate(value), first


def _reviewed_index(review, indexes, checkpoint):
    """Bind an acknowledgement to the unchanged empty observation and page receipt."""
    from .panel_index import PageIndexV2

    page = review.page_index
    pages = checkpoint.get("exploration_source_pages", [])
    if (not isinstance(pages, list) or page >= len(indexes) or page >= len(pages)
            or not isinstance(pages[page], dict)):
        raise ValueError("Source-only index review is outside the verified page bindings")
    observed = PageIndexV2.model_validate(indexes[page])
    if (observed.panels or review.index_sha256 != digest(indexes[page])
            or review.source_sha256 != observed.source_sha256 or review.page_index != observed.page_index
            or review.page_sha256 != observed.page_sha256
            or pages[page].get("page_index") != page or pages[page].get("sha256") != review.page_sha256):
        raise ValueError("Source-only index review differs from its exact empty index or page binding")


def _inherited_source_only_reviews(checkpoint, indexes, directory):
    """Authenticate the assisted acknowledgement separately from raw index bytes."""
    from .exploration import _read

    expected = checkpoint.get("exploration_seed", {}).get("source_index_reviews_sha256")
    lineage = checkpoint.get("correction_lineage", [])
    recorded = lineage[-1].get("source_index_reviews_sha256") if lineage else None
    path = Path(directory) / "source-index-reviews.json"
    if expected is None:
        if recorded is not None or path.exists() or path.is_symlink():
            raise ValueError("Inherited source-only index reviews lack their authenticated seed")
        return None
    raw = _read(directory, path.name, 32_000)
    receipt = json.loads(raw)
    if (hashlib.sha256(raw).hexdigest() != expected or recorded != expected
            or raw != canonical(receipt) or not isinstance(receipt, dict)
            or set(receipt) != {"version", "reviews"} or receipt["version"] != "source-only-index-reviews-v1"
            or not isinstance(receipt["reviews"], list) or not 1 <= len(receipt["reviews"]) <= 2):
        raise ValueError("Inherited source-only index reviews differ from their authenticated canonical seed")
    reviews = [SourceOnlyIndexReview.model_validate(value) for value in receipt["reviews"]]
    if len({(item.source_sha256, item.page_index) for item in reviews}) != len(reviews):
        raise ValueError("Inherited source-only index review pages must be unique")
    for review in reviews:
        _reviewed_index(review, indexes, checkpoint)
    return receipt


def _verify_reviewed_page_pixels(store, checkpoint, receipt):
    """Only explicitly reviewed pages require pixels during the deterministic fork."""
    import io
    from PIL import Image
    from .exploration import _read

    if receipt is None:
        return
    for value in receipt["reviews"]:
        review = SourceOnlyIndexReview.model_validate(value)
        raw = _read(store.data_dir, f"public/pages/{review.source_sha256}/page-{review.page_index:03d}.png")
        if hashlib.sha256(raw).hexdigest() != review.page_sha256:
            raise ValueError("Reviewed source page pixels changed before correction")
        page = checkpoint["exploration_source_pages"][review.page_index]
        with Image.open(io.BytesIO(raw)) as image:
            if (image.format != "PNG" or image.width * image.height > 25_000_000
                    or (image.width, image.height) != (page.get("width"), page.get("height"))):
                raise ValueError("Reviewed source page differs from its verified dimensions")
            image.verify()


def _authenticate_index_seed(checkpoint, indexes, directory):
    """Verify an inherited seed without loading source images or provider code."""
    from .exploration import _read
    from .panel_index import MAX_INDEX_BYTES

    expected = checkpoint.get("exploration_seed", {}).get("source_index_sha256")
    if not expected or directory is None:
        raise ValueError("Inherited source index lacks its authenticated seed; create a new source-index revision")
    raw = _read(directory, "source-index-seed.json", MAX_INDEX_BYTES)
    if hashlib.sha256(raw).hexdigest() != expected or raw != canonical(indexes):
        raise ValueError("Inherited source index differs from its authenticated canonical seed")
    _inherited_source_only_reviews(checkpoint, indexes, directory)


def _authenticate_v2_indexes(checkpoint, indexes, scene, directory, source_only_reviews=()):
    """Authenticate raw index responses before enrolling them in a new seed."""
    from .contracts import strict_schema
    from .exploration import FATAL_PROVIDER_CODES, _read, _verify_call_receipts
    from .panel_index import PageIndexV2

    if directory is None:
        raise ValueError("V2 source indexes require authenticated parent index receipts")
    _verify_call_receipts(directory, checkpoint)
    reviews = {review.page_index: review for review in source_only_reviews}
    acknowledged = set()
    for page, value in enumerate(indexes):
        state = checkpoint.get("exploration_calls", {}).get(f"index-{page:04d}")
        prefix = f"exploration/calls/index-{page:04d}"
        if "schema_version" not in value:
            v2_call = state and state.get("inputs", {}).get("schema_sha256") == digest(strict_schema(PageIndexV2))
            if state and state.get("receipt_sha256"):
                receipt = json.loads(_read(directory, f"{prefix}/receipt.json"))
                if receipt["status"] == "completed":
                    result = json.loads(_read(directory, f"{prefix}/result.json", 20_000_000))
                    v2_call = v2_call or result.get("schema_version") == "2.0"
            if v2_call:
                raise ValueError("Parent source index discarded its authenticated V2 provider fields")
            continue
        observed = PageIndexV2.model_validate(value)
        if not state or state.get("inputs", {}).get("images") != [
                {"name": f"page-{page:03d}.png", "sha256": observed.page_sha256}]:
            raise ValueError("V2 source index lacks its authenticated page call binding")
        if state.get("receipt_sha256"):
            receipt = json.loads(_read(directory, f"{prefix}/receipt.json"))
            if receipt["status"] == "completed":
                expected = PageIndexV2.model_validate_json(_read(directory, f"{prefix}/result.json", 20_000_000))
            elif receipt["status"] == "failed":
                error = receipt["error"]
                if error["code"] in FATAL_PROVIDER_CODES | {"integrity_failure"}:
                    review = reviews.get(page)
                    if error["code"] != "provider_unavailable" or review is None:
                        raise ValueError("A fatal index failure cannot seed a correction without an eligible source-only review")
                    _reviewed_index(review, indexes, checkpoint)
                    if (state.get("status") != "failed" or not state.get("request_sha256")
                            or review.failed_request_sha256 != state["request_sha256"]
                            or review.failed_receipt_sha256 != state["receipt_sha256"]
                            or state["inputs"].get("schema_sha256") != digest(strict_schema(PageIndexV2))):
                        raise ValueError("Source-only review differs from its authenticated failed call")
                    process_raw = _read(directory, f"{prefix}/provider/process-result.json", 32_000)
                    process = json.loads(process_raw)
                    if (hashlib.sha256(process_raw).hexdigest() != review.process_result_sha256
                            or process.get("structured_result_present") is not False
                            or type(process.get("returncode")) is not int or process["returncode"] == 0
                            or process.get("model") != state["inputs"].get("model")
                            or any(process.get(key) != state["inputs"].get(key)
                                for key in ("reasoning", "thinking_level", "provider") if key in state["inputs"])):
                        raise ValueError("Source-only review requires the exact failed process without structured output")
                    for name in ("result.json", "provider/response.json"):
                        path = Path(directory) / prefix / name
                        if path.exists() or path.is_symlink():
                            raise ValueError("Source-only review cannot replace retained structured output")
                    acknowledged.add(page)
                expected = PageIndexV2(source_sha256=scene.source_sha256, page_index=page,
                    page_sha256=observed.page_sha256, panels=[],
                    uncertainty=[("Page indexing unavailable: " + error["message"])[:2000]])
            else:
                raise ValueError("Parent index receipt has no completed or failed outcome")
        else:
            # Recovery never repeats a reserved call. Only its exact conservative
            # interrupted-call fallback can exist without a committed receipt.
            if (Path(directory) / prefix / "receipt.json").exists():
                raise ValueError("Unpinned parent index receipt cannot seed a correction")
            expected = PageIndexV2(source_sha256=scene.source_sha256, page_index=page,
                page_sha256=observed.page_sha256, panels=[], uncertainty=[
                    "Page indexing unavailable: A previously reserved provider call was interrupted; it is not repeated."])
        if digest(expected) != digest(observed):
            raise ValueError("Parent source index differs from its authenticated provider result")
    if acknowledged != set(reviews):
        raise ValueError("Source-only reviews must identify eligible recovered provider-unavailable index calls")


def _inherited_indexes(checkpoint, scene, directory=None, source_only_reviews=()):
    from .contracts import PageIndex
    from .panel_index import MAX_INDEX_BYTES, MAX_REGIONS, MAX_REGIONS_PER_PAGE, PageIndexV2

    if checkpoint.get("page_indexes"):
        indexes = copy.deepcopy(checkpoint["page_indexes"])
        if not isinstance(indexes, list) or len(indexes) != scene.sources[0].page_count:
            raise ValueError("Inherited source index must cover the complete verified page count")
        if len(canonical(indexes)) > MAX_INDEX_BYTES:
            raise ValueError("Inherited source index exceeds its evidence byte limit")
        for page, value in enumerate(indexes):
            if not isinstance(value, dict) or not isinstance(value.get("panels"), list):
                raise ValueError("Inherited source index requires page objects and panel lists")
            if len(value["panels"]) > MAX_REGIONS_PER_PAGE:
                raise ValueError("Inherited source index exceeds its per-page region limit")
            if "schema_version" in value:
                observed = PageIndexV2.model_validate(value)
                if observed.source_sha256 != scene.source_sha256 or observed.page_index != page:
                    raise ValueError("Inherited V2 index differs from the verified source/page order")
            else:
                PageIndex.model_validate(value)
        if sum(len(value["panels"]) for value in indexes) > MAX_REGIONS:
            raise ValueError("Inherited source index exceeds its total region limit")
        if checkpoint.get("exploration_seed") is not None:
            if source_only_reviews:
                raise ValueError("An inherited authenticated index seed cannot accept a new failed-call review")
            _authenticate_index_seed(checkpoint, indexes, directory)
        elif (any("schema_version" in value for value in indexes)
                or any(re.fullmatch(r"index-[0-9]{4}", key) for key in checkpoint.get("exploration_calls", {}))):
            _authenticate_v2_indexes(checkpoint, indexes, scene, directory, source_only_reviews)
        elif source_only_reviews:
            raise ValueError("Source-only reviews require an authenticated V2 failed index call")
        # Keep the actual raw records. The resume host alone may bind legacy
        # records to rendered pixels; validation here does not upgrade semantics.
        return indexes
    if source_only_reviews:
        raise ValueError("Source-only reviews cannot invent a missing source index")
    # Older direct-alpha jobs have no strict page-index receipts. Preserve the
    # source panels they actually reconstructed and mark this inherited index as
    # uncertain, rather than pretending a new source-index model call occurred.
    indexes = [{"panels": [], "uncertainty": []} for _ in range(scene.sources[0].page_count)]
    groups = {}
    for step in scene.steps:
        key = (step.source.page_index, step.main_step_number, step.section_id)
        groups.setdefault(key, []).append(step)
    for (page, number, section), steps in groups.items():
        boxes = [step.source.bbox for step in steps]
        indexes[page]["panels"].append({"section": section, "number": number,
            "label": f"Inherited instruction {number}", "kind": "main",
            "bbox": [min(b[0] for b in boxes), min(b[1] for b in boxes),
                     max(b[2] for b in boxes), max(b[3] for b in boxes)]})
        indexes[page]["uncertainty"] = ["Source index inherited from the parent's reconstructed panels; not independently re-indexed."]
    return [PageIndex.model_validate(value).model_dump(mode="json") for value in indexes]


def _inherited_panels(checkpoint, indexes, scene):
    """Preserve the authenticated V2 event cursor, never infer it from scene poses."""
    if not any("schema_version" in value for value in indexes):
        return [(page, panel) for page, index in enumerate(indexes) for panel in index["panels"]]
    from .exploration import _exploration_event_queue
    from .panel_index import normalize_index

    pages = checkpoint.get("exploration_source_pages")
    if (not isinstance(pages, list) or len(pages) != scene.sources[0].page_count
            or any(not isinstance(item, dict) or item.get("page_index") != page for page, item in enumerate(pages))):
        raise ValueError("V2 source index lacks parent page bindings; create a new source-index revision")
    regions = normalize_index(indexes, source_sha256=scene.source_sha256, source_pages=pages,
        set_number=scene.set_number, guide_id=scene.guide_id)
    panels = [(item["page_index"], item["panel"]) for item in _exploration_event_queue(regions)]
    results = checkpoint.get("instruction_results", [])
    processed = checkpoint.get("processed_panels")
    if (type(processed) is not int or not 0 <= processed <= len(panels) or not isinstance(results, list)
            or len(results) != processed or checkpoint.get("total_panels", len(panels)) != len(panels)
            or any(not isinstance(item, dict) or item.get("ordinal") != ordinal
                or (item.get("page_index"), item.get("panel")) != panels[ordinal]
                for ordinal, item in enumerate(results))):
        raise ValueError("V2 source index lacks compatible parent cursor evidence; create a new source-index revision")
    return panels


def _inherited_results(checkpoint, scene, panels, count, job_id):
    previous = {item["ordinal"]: item for item in checkpoint.get("instruction_results", [])}
    results = []
    for ordinal, (page, panel) in enumerate(panels[:count]):
        result = copy.deepcopy(previous.get(ordinal))
        if result is None:
            matches = [step.step_id for step in scene.steps if step.main_step_number == panel["number"]
                       and step.source.page_index == page]
            result = {"ordinal": ordinal, "page_index": page, "panel": panel, "step_ids": matches,
                "findings": [{"category": "inherited_candidate", "description":
                    "Inherited reconstruction; previous quality checks do not validate this correction."}],
                "reconstructed": bool(matches), "outcome": "inherited_provisional" if matches else "unresolved",
                "attempt_count": 0, "assembly_approval": "not_run"}
        result["inherited_from_job"] = job_id
        result["checks_invalidated"] = True
        results.append(result)
    return results


def fork_correction(store, job_id, request_path, revision):
    """Create a paused assisted revision, or a prefix for bounded source-driven repair."""
    if not isinstance(revision, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}", revision):
        raise ValueError("Correction revision must be a safe nonempty identifier")
    request = CorrectionRequest.model_validate(_read_json(Path(request_path)))
    job = store.get(job_id)
    if job["owner"] and (job["lease_until"] or 0) > time.time():
        raise ValueError("Cannot correct an actively leased job")
    candidate = job["checkpoint"].get("candidate")
    if not candidate:
        raise ValueError("Correction base has no reconstructed candidate")
    scene = SceneV2.model_validate(candidate)
    if digest(scene) != request.expected_scene_sha256:
        raise ValueError("Stale expected scene hash")
    _bounded_scene(scene)
    sources = verify_scene_source(store, job, scene)
    for panel in request.evidence:
        _source_evidence(panel, sources)
    cited_pages = {panel.page_index for panel in request.evidence if panel.source_sha256 == scene.source_sha256}
    if not set(request.context_page_indexes or []) <= cited_pages:
        raise ValueError("Correction context pages must cite the restart's verified source")
    parent_attempt_cap = min(2, job["config"].get("max_panel_attempts", 2))
    if request.max_panel_attempts is not None and request.max_panel_attempts > parent_attempt_cap:
        raise ValueError("Correction max_panel_attempts cannot increase the parent's normalized exploration cap")
    controls = {key: getattr(request, key) for key in ("context_page_indexes", "max_panel_attempts", "review_profile",
                                                    "source_reference_profile")
                if getattr(request, key) is not None}
    # Preserve the existing request bytes/hash shape when no new control is used.
    request_data = request.model_dump(mode="json", exclude={"context_page_indexes", "max_panel_attempts", "review_profile",
                                                           "source_reference_profile", "source_only_index_reviews"}) | controls
    if request.source_only_index_reviews:
        request_data["source_only_index_reviews"] = [item.model_dump(mode="json") for item in request.source_only_index_reviews]
    directory = store.root / "jobs" / job_id
    geometry = directory / "geometry"
    from .closure_publication import verify_correction_parent
    verify_correction_parent(job, directory, scene)
    verify_individual_assets(geometry, [part.geometry_ref for part in scene.instances])
    history = copy.deepcopy(job["checkpoint"].get("correction_lineage", []))
    limit = job["config"].get("max_repair_passes", 2)
    if type(limit) is not int or not 0 <= limit <= 2 or len(history) >= limit:
        raise ValueError("At most two correction repair passes are permitted in a lineage")
    if request.correction_id in {entry.get("correction_id") for entry in history}:
        raise ValueError("Duplicate correction_id in the correction lineage")
    # Keep only source and progress metadata. Old raw proposal caches and accepted
    # validation receipts stay in the parent and cannot leak future poses into repair.
    retained = {"source_sha256", "page_count", "page_indexes", "total_panels", "completed_panels",
                "processed_panels", "reconstructed_panels", "instruction_results", "source_coverage",
                "exploration_policy", "model_calls_used", "inherited_model_calls_used", "landmark_overrides",
                "budget_root_job_id", "budget_origin_model_calls_used", "unaided_origin_job_id", "source_view_policy"}
    retained.update({"exploration_source_pages", "source_index_findings"})
    checkpoint = {key: copy.deepcopy(value) for key, value in job["checkpoint"].items() if key in retained}
    checkpoint["page_indexes"] = _inherited_indexes(job["checkpoint"], scene, directory,
                                                   request.source_only_index_reviews or ())
    source_index_sha256 = digest(checkpoint["page_indexes"])
    index_reviews = _inherited_source_only_reviews(job["checkpoint"], checkpoint["page_indexes"], directory)
    if request.source_only_index_reviews:
        index_reviews = {"version": "source-only-index-reviews-v1", "reviews": request_data["source_only_index_reviews"]}
    _verify_reviewed_page_pixels(store, checkpoint, index_reviews)
    panels = _inherited_panels(job["checkpoint"], checkpoint["page_indexes"], scene)
    checkpoint["total_panels"] = len(panels)
    legacy_callouts = (all("schema_version" not in value for value in checkpoint["page_indexes"])
                      and any(panel["kind"] == "substep" for _, panel in panels))
    calls_used = max(checkpoint.get("model_calls_used", 0), checkpoint.get("inherited_model_calls_used", 0))
    if type(calls_used) is not int or calls_used < 0:
        raise ValueError("Inherited model-call budget is invalid")
    # Older strict/alpha checkpoints predate reservation counts; measured local invocations
    # provide a lower bound, not an invented zero-cost fresh budget.
    from .evaluation import summarize_job_calls
    local_measured = summarize_job_calls(directory)["model_invocations"]
    calls_used = max(calls_used, checkpoint.get("inherited_model_calls_used", 0) + local_measured)
    budget_root = checkpoint.get("budget_root_job_id", job_id)
    root_floor = checkpoint.get("budget_origin_model_calls_used", max(local_measured,
        job["checkpoint"].get("local_model_calls_used", calls_used)) if budget_root == job_id else 0)
    calls_used = max(calls_used, store.lineage_model_calls_used(budget_root))
    checkpoint.pop("model_requests", None)  # Inherited requests remain charged, never local reservations.
    checkpoint.update(model_calls_used=calls_used, inherited_model_calls_used=calls_used,
                      local_model_calls_used=0, budget_root_job_id=budget_root,
                      budget_origin_model_calls_used=root_floor,
                      exploration_calls={}, artifact_kind="agent_corrected_exploration", runner_version=PIPELINE,
                      source_sha256=scene.source_sha256, stage="correction_ready",
                      invalidated_checks=["source_camera", "visual_review", "geometry", "connectors", "physical_build"])
    landmarks, changes = {}, []
    if request.restart_main_step is not None:
        matches = [i for i, (_, panel) in enumerate(panels)
                   if panel["number"] == request.restart_main_step and panel["kind"] != "substep"]
        if not matches:
            raise ValueError("Restart instruction is absent from the retained source index")
        if len(matches) != 1:
            raise ValueError("Restart main number is ambiguous across source panels; no repair fork was created")
        restart_ordinal = matches[0]
        updated, first = _prefix(scene, request.restart_main_step)
        if legacy_callouts:
            # A restart at the first main event discards the entire old prefix,
            # including any preceding unclassified callouts. Every raw region
            # remains in the new conservative queue. Never rebase retained work.
            first_main = next((i for i, (_, panel) in enumerate(panels) if panel["kind"] != "substep"), None)
            if updated is None and restart_ordinal == first_main:
                restart_ordinal = 0
            elif restart_ordinal:
                raise ValueError("Legacy callout index cannot retain a processed prefix; restart from the first instruction or create a new source-index revision")
        prefix_steps = {step.step_id for step in updated.steps} if updated else set()
        results = _inherited_results(checkpoint, scene, panels, restart_ordinal, job_id)
        checkpoint["landmark_overrides"] = {key: value for key, value in checkpoint.get("landmark_overrides", {}).items()
                                             if key in prefix_steps}
        prefix_panels = restart_ordinal
        later_pages = list(request.context_page_indexes or [])
        later_pages.extend(page for page in sorted({step.source.page_index for step in scene.steps[first:]})
                           if page not in later_pages)
        checkpoint.update(instruction_results=results, processed_panels=prefix_panels,
                          reconstructed_panels=sum(item["reconstructed"] for item in results),
                          completed_panels=sum(item["reconstructed"] for item in results), source_coverage="partial",
                          correction_guidance={"restart_main_step": request.restart_main_step,
                            "findings": request.guidance, "evidence": [item.model_dump(mode="json") for item in request.evidence],
                            "later_source_pages": [{"page_index": page, "source_sha256": scene.source_sha256}
                                for page in later_pages]})
    else:
        processed = checkpoint.get("processed_panels", checkpoint.get("completed_panels", len(panels)))
        if legacy_callouts and processed:
            raise ValueError("Legacy callout index cannot retain a processed prefix; restart from the first instruction or create a new source-index revision")
        updated, first, changes, landmarks = _apply_commands(scene, request.commands, sources, geometry)
        checkpoint["landmark_overrides"] = checkpoint.get("landmark_overrides", {}) | landmarks
        checkpoint["instruction_results"] = _inherited_results(checkpoint, scene, panels, processed, job_id)
        checkpoint["processed_panels"] = processed
        checkpoint["reconstructed_panels"] = sum(item["reconstructed"] for item in checkpoint["instruction_results"])
    # Rebuild warnings from the retained prefix, never from discarded suffix
    # trials or a parent's possibly stale aggregate. Keep source-index concerns
    # separate so dependent prompts can prioritize them without losing provenance.
    checkpoint["provisional_findings"] = []
    for result in checkpoint["instruction_results"]:
        for item in result.get("findings", []):
            item = copy.deepcopy(item) if isinstance(item, dict) else {"code": "instruction_review", "message": str(item)}
            item.update(ordinal=result["ordinal"], inherited_from_job=result["inherited_from_job"])
            item.setdefault("step_ids", result.get("step_ids", []))
            item.setdefault("page_index", result["page_index"])
            item.setdefault("source_sha256", scene.source_sha256)
            checkpoint["provisional_findings"].append(item)
    index_findings = checkpoint.get("source_index_findings", []) + [
        {"code": "source_index_uncertainty", "severity": "review", "message": note,
         "page_index": page, "source_sha256": scene.source_sha256}
        for page, index in enumerate(checkpoint["page_indexes"]) for note in index.get("uncertainty", [])]
    checkpoint["source_index_findings"] = list({digest(item): item for item in index_findings}.values())
    checkpoint["uncertainty_notes"] = checkpoint["source_index_findings"] + checkpoint["provisional_findings"]
    if updated is not None:
        updated.revision = revision
        updated.status = "needs_review"
        updated.geometry_check = updated.connector_check = updated.physical_build_check = "not_run"
        updated = SceneV2.model_validate(updated.model_dump(mode="json"))
        _bounded_scene(updated)
        verify_individual_assets(geometry, [part.geometry_ref for part in updated.instances])
        _verify_materials(updated, geometry)
        checkpoint["candidate"] = updated.model_dump(mode="json")
    else:
        checkpoint.pop("candidate", None)
    checkpoint["exploration_seed"] = {"candidate_sha256": digest(updated) if updated else None,
        "processed_panels": checkpoint.get("processed_panels", checkpoint.get("completed_panels", 0)),
        "parent_job_id": job_id, "source_sha256": scene.source_sha256,
        "source_index_sha256": source_index_sha256}
    record = {"correction_id": request.correction_id, "parent_job_id": job_id,
              "parent_scene_sha256": digest(scene), "result_scene_sha256": digest(updated) if updated else None,
              "request_sha256": digest(request_data), "revision": revision, "actor": "agent", "reason": request.reason,
              "repair_pass": len(history) + 1, "first_affected_step_index": first,
              "mode": "source_guided_restart" if request.restart_main_step is not None else "deterministic_replay",
              "source_index_seed_sha256": source_index_sha256,
              "changes": changes, "evidence": [item.model_dump(mode="json") for item in request.evidence],
              "invalidated_checks": checkpoint["invalidated_checks"], "unassisted": False}
    if index_reviews is not None:
        review_hash = digest(index_reviews)
        checkpoint["exploration_seed"]["source_index_reviews_sha256"] = review_hash
        record["source_index_reviews_sha256"] = review_hash
    checkpoint["correction_lineage"] = history + [record]
    parent_kind = job["checkpoint"].get("artifact_kind", job["config"].get("artifact_kind", ""))
    parent_assisted = bool(job["checkpoint"].get("assisted_lineage") or job["checkpoint"].get("alpha_assisted_corrections")
                           or history or "assisted" in parent_kind or "corrected" in parent_kind
                           or any(part.origin != "vision_proposal" for part in scene.instances))
    checkpoint["unaided_origin_job_id"] = checkpoint.get("unaided_origin_job_id", None if parent_assisted else job_id)
    config = dict(job["config"], execution_policy="explore", generation_mode="strict", revision=revision,
                  max_model_calls=job["config"].get("max_model_calls", 3), max_repair_passes=limit,
                  artifact_kind="agent_corrected_exploration", budget_root_job_id=budget_root,
                  max_panel_attempts=request.max_panel_attempts if request.max_panel_attempts is not None else parent_attempt_cap)
    if request.review_profile is not None:
        config["review_profile"] = request.review_profile
    if request.source_reference_profile is not None:
        config["source_reference_profile"] = request.source_reference_profile
    from .quality import source_view_policy
    checkpoint.setdefault("source_view_policy", source_view_policy(config.get("quality_profile", "strict")))
    # A correction is a new experiment revision. Initialize its current policy
    # from the authoritative runner contract, retaining explicit transition
    # evidence instead of mutating or replaying the parent's provider receipts.
    from .exploration import _policy
    parent_policy = checkpoint.pop("exploration_policy", None)
    record["parent_exploration_policy_sha256"] = digest(parent_policy) if parent_policy is not None else None
    policy = _policy(config, checkpoint, scene.source_sha256, scene.sources[0].page_count)
    record["derived_exploration_policy_sha256"] = digest(policy)
    record["exploration_policy_transition"] = {
        "scope": "new_correction_revision_only", "parent_version": (parent_policy or {}).get("version"),
        "derived_version": policy["version"], "changed_fields": sorted(
            key for key in set(parent_policy or {}) | set(policy)
            if key not in (parent_policy or {}) or key not in policy or parent_policy[key] != policy[key]),
        "parent_provider_receipts_reused": False,
        "model_call_budget_preserved": True}
    if index_reviews is not None:
        record["exploration_policy_transition"]["source_index_reviews_sha256"] = digest(index_reviews)
    if controls:
        record["requested_controls"] = controls
        record["exploration_policy_transition"].update(requested_controls=controls,
            parent_normalized_max_panel_attempts=parent_attempt_cap,
            derived_max_panel_attempts=config["max_panel_attempts"])

    def materialize(destination):
        # Recheck source and geometry after acquiring the transactional fork fence.
        verify_correction_parent(job, directory, scene)
        verify_scene_source(store, job, scene)
        if digest(_inherited_indexes(job["checkpoint"], scene, directory,
                                      request.source_only_index_reviews or ())) != source_index_sha256:
            raise ValueError("Parent source index changed before correction materialization")
        _verify_reviewed_page_pixels(store, checkpoint, index_reviews)
        with (destination / "source-index-seed.json").open("xb") as stream:
            stream.write(canonical(checkpoint["page_indexes"]))
        if index_reviews is not None:
            with (destination / "source-index-reviews.json").open("xb") as stream:
                stream.write(canonical(index_reviews))
        assets = _copy_geometry(geometry, destination / "geometry", updated or scene)
        verify_correction_parent(job, directory, scene)
        _json(destination / "parent-scene.json", scene.model_dump(mode="json"))
        _json(destination / "correction-request.json", request_data)
        _json(destination / "correction.json", record | {"geometry_receipt": assets,
              "geometry_provenance_sha256": hashlib.sha256((destination / "geometry/provenance.json").read_bytes()).hexdigest()})
        if updated:
            _json(destination / "scene.json", updated.model_dump(mode="json"))
        for name in ("source-receipt.json", "coverage-index.json"):
            source = directory / name
            if source.is_file():
                _read_json(source, 32_000_000)
                shutil.copyfile(source, destination / name)
        inherited_evidence = {"parent_job_id": job_id,
            "parent_scene_sha256": digest(scene), "unaided_origin_job_id": checkpoint["unaided_origin_job_id"],
            "inherited_model_calls_used": calls_used, "raw_calls_copied": False,
            "source_index_seed_sha256": source_index_sha256}
        if index_reviews is not None:
            inherited_evidence["source_index_reviews_sha256"] = digest(index_reviews)
        _json(destination / "inherited-evidence.json", inherited_evidence)

    return store.fork_revision(job_id, correction_id=request.correction_id,
        expected_scene_sha256=request.expected_scene_sha256, request_sha256=digest(request_data),
        config=config, checkpoint=checkpoint, materialize=materialize,
        expected_checkpoint_sha256=digest(job["checkpoint"]))


def refresh_correction_evidence(store, job_id, output):
    """Refit explicit landmark edits and render changed descendants, without inference.

    Called by evaluation, not by the fast transactional fork. The output is a new
    private evidence directory. Unsupported/poor camera fits retain their diagnosis
    and use an overview; this never grants visual, connector or physical approval.
    """
    from PIL import Image
    from .connectors import world_landmark
    from .quality import source_view_policy
    from .source_view import fit_source_view
    from .rendering import render_candidate

    job = store.get(job_id)
    checkpoint = job["checkpoint"]
    if job["owner"] and (job["lease_until"] or 0) > time.time():
        raise ValueError("Cannot refresh correction evidence for an actively changing job")
    scene = SceneV2.model_validate(checkpoint["candidate"])
    verify_scene_source(store, job, scene)
    directory = store.root / "jobs" / job_id
    geometry = directory / "geometry"
    verify_individual_assets(geometry, [part.geometry_ref for part in scene.instances])
    output = Path(output).absolute()
    if (output.is_symlink() or not output.resolve().is_relative_to(store.data_dir.resolve())
            or output.resolve().is_relative_to((store.data_dir / "public").resolve()) or output.exists()):
        raise ValueError("Correction render output must be a new private evidence directory")
    output.mkdir(parents=True)
    _json(output / "scene.json", scene.model_dump(mode="json"))
    policy = checkpoint.get("source_view_policy", source_view_policy(job["config"].get("quality_profile", "strict")))
    steps = {step.step_id: step for step in scene.steps}
    parts = {part.instance_id: part for part in scene.instances}
    cameras, fits = {}, {}
    first = min((entry["first_affected_step_index"] for entry in checkpoint.get("correction_lineage", [])), default=0)
    first = min(first, len(scene.steps)-1)
    for step_id, raw in checkpoint.get("landmark_overrides", {}).items():
        observation = SourceViewObservation.model_validate(raw)
        if step_id != observation.step_id or step_id not in steps:
            raise ValueError("Landmark override no longer belongs to this corrected scene")
        step = steps[step_id]
        page = store.data_dir / "public/pages" / step.source.source_sha256 / f"page-{step.source.page_index:03d}.png"
        if page.is_symlink() or not page.resolve().is_relative_to(store.data_dir.resolve()) or page.stat().st_size > 32_000_000:
            raise ValueError("Unsafe correction source image")
        records = _read_json(page.parent / "pages.json", 32_000_000)
        record = next((item for item in records if item.get("page_index") == step.source.page_index), None)
        if not record or record["sha256"] != hashlib.sha256(page.read_bytes()).hexdigest():
            raise ValueError("Correction source pixels differ from their page receipt")
        with Image.open(page) as image:
            size = image.size
            if size[0] * size[1] > 32_000_000:
                raise ValueError("Correction source image exceeds pixel bound")
        world, uv = [], []
        for landmark in observation.landmarks:
            if landmark.instance_id not in step.poses:
                raise ValueError("Correction landmark names an invisible physical instance")
            world.append(world_landmark(step.poses[landmark.instance_id], parts[landmark.instance_id].geometry_ref,
                                        landmark.landmark_id, geometry))
            uv.append(landmark.image_uv)
        fit = fit_source_view(world, uv, size, view_family=observation.view_family,
            **{key: policy[key] for key in ("max_rms_pixels", "max_point_pixels", "ambiguity_pixels")})
        fits[step_id] = fit
        if fit.get("status") == "fitted" and fit.get("camera"):
            cameras[step_id] = fit["camera"]
    _json(output / "camera-fits.json", {"scene_sha256": digest(scene), "fits": fits,
        "overrides": checkpoint.get("landmark_overrides", {}), "assembly_poses_changed": False})
    try:
        rendered = render_candidate(output / "scene.json", geometry, output / "renders", first_step=first+1,
                                    source_views=cameras or None)
        outcome = {"status": "rendered", "scene_sha256": digest(scene), "first_step": first+1,
                   "report_path": str(output / "renders/report.json"), "fits": fits,
                   "rendered_microsteps": len(rendered["steps"]), "source_aligned_steps": sorted(cameras),
                   "camera_fallback_label": "Overview camera — source alignment unavailable",
                   "visual_review": "not_run", "geometry_check": "not_run", "physical_build": "not_run"}
    except (ValueError, OSError) as error:
        outcome = {"status": "render_failed", "scene_sha256": digest(scene), "fits": fits,
                   "reason": str(error), "rendered_microsteps": 0, "visual_review": "not_run"}
    _json(output / "refresh-report.json", outcome)
    return outcome
