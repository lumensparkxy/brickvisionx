"""Bounded instruction repair: model choices, deterministic poses, then source-view review.

Rejected trials never become the input assembly for the next instruction. All repair
attempts are durable, including attempts interrupted before a provider reply.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import Field, model_validator

from ..core.models import StrictModel
from ..releases.models import digest as scene_digest
from .delta import DeltaConstruction, assemble_delta
from .quality import bind_source_view_policy, fit_acceptance, source_view_policy


class SequenceEvidence(StrictModel):
    step_id: str
    kind: Literal["printed_main", "numbered_callout", "attachment"]
    printed_label: str | None
    bbox: tuple[float, float, float, float]
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def bounds(self):
        x, y, right, bottom = self.bbox
        if not 0 <= x < right <= 1 or not 0 <= y < bottom <= 1:
            raise ValueError("Sequence evidence needs a nonempty normalized source crop")
        return self


class InstructionFinding(StrictModel):
    category: Literal["part", "connection", "side", "sequence", "source_view", "coverage", "ambiguity"]
    step_ids: list[str]
    instance_ids: list[str]
    description: str = Field(min_length=1, max_length=4000)
    correction: str = Field(min_length=1, max_length=4000)


class InstructionReview(StrictModel):
    coverage_agrees: bool
    assembly_agrees: bool
    findings: list[InstructionFinding]


def proposal_type():
    # Keep contracts owned by the solver and camera fitter at their boundaries.
    from .spatial import ConnectionChoice, RootPlacement
    from .source_view import SourceViewObservation

    class InstructionProposal(DeltaConstruction):
        connections: list[ConnectionChoice] = Field(default_factory=list, max_length=256)
        roots: list[RootPlacement] = Field(default_factory=list, max_length=20)
        sequence: list[SequenceEvidence] = Field(default_factory=list, max_length=20)
        source_views: list[SourceViewObservation] = Field(default_factory=list, max_length=20)

    return InstructionProposal


def validate_sequence(scene, previous, evidence):
    """Check explicit source sequence claims; pixels still need independent review."""
    steps = scene.steps[len((previous or {}).get("steps", [])):]
    if len(evidence) != len(steps) or [item.step_id for item in evidence] != [s.step_id for s in steps]:
        raise ValueError("Every new snapshot needs ordered source sequence evidence")
    callout_labels = set()
    for step, item in zip(steps, evidence, strict=True):
        if item.kind == "numbered_callout":
            if not item.printed_label or step.action != "build_subassembly" or not step.assembly_group_id:
                raise ValueError("A callout must cite its printed label and a detached assembly group")
            if step.substep_label != item.printed_label:
                raise ValueError("Viewer substep label must equal the source's printed callout label")
            identity = (step.assembly_group_id, item.printed_label)
            if identity in callout_labels:
                raise ValueError("Duplicate printed callout step for the same physical group")
            callout_labels.add(identity)
        elif item.kind == "attachment":
            if step.action != "attach_subassembly" or step.introduced_instance_ids:
                raise ValueError("Attachment must reuse existing physical IDs")
            if not step.assembly_group_id or not any(group == step.assembly_group_id for group, _ in callout_labels):
                raise ValueError("Attachment must follow the same group's explicit callout sequence")
        elif len(steps) != 1 or step.substep_label is not None or step.action != "add_parts":
            raise ValueError("An ordinary printed instruction is one snapshot; do not invent intermediate microsteps")


def source_views_for(scene, previous, observations, geometry, source_image, policy=None):
    """Resolve image landmarks from verified individual geometry, never arbitrary 3D points."""
    from .connectors import world_landmark
    from .source_view import fit_source_view
    policy = policy or source_view_policy()
    steps = scene.steps[len((previous or {}).get("steps", [])):]
    if len(observations) != len(steps) or {o.step_id for o in observations} != {s.step_id for s in steps}:
        raise ValueError("Each new snapshot needs its own source landmark observation")
    parts = {part.instance_id: part for part in scene.instances}
    by_step = {item.step_id: item for item in observations}
    with Image.open(source_image) as image:
        size = image.size
    fits, cameras = {}, {}
    for step in steps:
        observation = by_step[step.step_id]
        seen, world, uv = set(), [], []
        for item in observation.landmarks:
            identity = (item.instance_id, item.landmark_id)
            if identity in seen or item.instance_id not in step.visible_instance_ids:
                raise ValueError("Source landmarks must be distinct and belong to visible pieces")
            seen.add(identity)
            world.append(world_landmark(step.poses[item.instance_id], parts[item.instance_id].geometry_ref,
                                        item.landmark_id, geometry))
            uv.append(item.image_uv)
        fit = fit_source_view(world, uv, size, view_family=observation.view_family,
                              **{key: policy[key] for key in
                                 ("max_rms_pixels", "max_point_pixels", "ambiguity_pixels")})
        fit.update(fit_acceptance(fit))
        fits[step.step_id] = fit
        if fit.get("status") == "fitted" and fit.get("camera"):
            cameras[step.step_id] = fit["camera"]
    return fits, cameras


def build_instruction(*, job, previous, ordinal, panel, page_index, page_count, source_hash,
                      directory, pages_dir, geometry_root, prompt, images, checkpoint, save, infer,
                      heartbeat, validate_candidate, atomic_json):
    """Return a reviewed trial, or persist a precise blocked state after the attempt ceiling."""
    from .geometry import prepare_geometry
    from .spatial import solve_candidate
    from .rendering import render_candidate

    policy = bind_source_view_policy(job["config"], checkpoint)
    limit = job["config"].get("max_panel_attempts", 3)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
        raise ValueError("max_panel_attempts must be an integer between 1 and 5")
    attempts = checkpoint.setdefault("panel_attempts", {})
    state = attempts.setdefault(str(ordinal), {"used": 0, "limit": limit, "trials": [], "feedback": []})
    if state["limit"] != limit:
        raise ValueError("A saved instruction repair budget cannot change on resume")
    model = proposal_type()
    accepted = state.get("accepted")
    if accepted:
        # The reviewed receipt is committed before returning to the outer loop. A
        # crash between review and candidate promotion must not spend another call.
        from .preview import confined_bytes
        if accepted.get("source_view_policy", source_view_policy()) != policy:
            raise ValueError("Reviewed instruction recovery has a different image tolerance")
        if (accepted["previous_scene_sha256"] != (scene_digest(previous) if previous else None)
                or accepted["source_sha256"] != source_hash or accepted["ordinal"] != ordinal
                or accepted["page_index"] != page_index or accepted["panel"] != panel):
            raise ValueError("Reviewed instruction recovery does not match the current source/history")
        if hashlib.sha256((pages_dir / f"page-{page_index:03d}.png").read_bytes()).hexdigest() != accepted["source_image_sha256"]:
            raise ValueError("Reviewed source page changed before instruction recovery")
        trial = Path(accepted["directory"])
        if trial not in [Path(value) for value in state["trials"]] or not trial.is_relative_to(directory / "proposals"):
            raise ValueError("Reviewed instruction recovery escapes this job")
        for name, expected_hash in accepted["files"].items():
            if hashlib.sha256(confined_bytes(trial, name, 32_000_000)).hexdigest() != expected_hash:
                raise ValueError("Reviewed instruction evidence changed before recovery")
        parsed = model.model_validate_json((trial / "proposal.json").read_text())
        raw_scene = validate_candidate((trial / "raw-scene.json").read_text(), job, source_hash,
                                       page_count, previous, panel, page_index)
        validate_sequence(raw_scene, previous, parsed.sequence)
        prepare_geometry(raw_scene, directory / "geometry", geometry_root)
        scene, _ = solve_candidate(raw_scene, previous, parsed.connections, parsed.roots, directory / "geometry")
        if scene_digest(scene) != accepted["scene_sha256"]:
            raise ValueError("Reviewed instruction's deterministic result changed before recovery")
        validate_candidate(scene.model_dump_json(), job, source_hash, page_count, previous, panel, page_index)
        record = json.loads((trial / "visual-review.json").read_text())
        review = InstructionReview.model_validate(record["review"])
        if record["scene_sha256"] != scene_digest(scene) or not review.coverage_agrees or not review.assembly_agrees or review.findings:
            raise ValueError("Reviewed instruction recovery lacks a matching successful visual review")
        return scene, record
    last_proposal = state.get("last_proposal")
    while state["used"] < limit:
        heartbeat.check()
        state["used"] += 1
        attempt = state["used"]
        trial = directory / "proposals" / uuid.uuid4().hex
        state["trials"].append(str(trial))
        checkpoint["current_panel_attempt"] = {"panel": ordinal + 1, "attempt": attempt, "limit": limit}
        save("repairing_instruction" if attempt > 1 else "constructing_instruction")
        feedback = json.dumps({"findings": state["feedback"], "rejected_proposal": last_proposal})
        if len(feedback.encode()) > 400_000:
            raise ValueError("Instruction repair feedback exceeds bounded context")
        repair_prompt = (prompt + "\nChoose compatible named connections from the supplied individual connector "
            "catalogue. The engine computes mating transforms; your poses are retained as raw proposals only. "
            "List a root only for the first piece or the first piece of a printed detached callout. Each other "
            "new/moved piece requires a connection. For a single NEW part, moving_group_ids MUST be []. "
            "Only on attach_subassembly, moving_group_ids lists all physical pieces of a rigid "
            "subassembly being attached, including moving_instance_id; never recreate these IDs. quarter_turns "
            "is the discrete mating-frame rotation, not an unconstrained pose. Unknown connector families block. "
            "Return source sequence evidence for every snapshot: one printed_main for an ordinary instruction, "
            "numbered_callout only for actual printed callout substeps, then attachment of those same pieces. "
            "Do not invent 1a/1b stages from arrows or arbitrary insertion order. Give source_views for each "
            "new snapshot with at least four distinct visibly identifiable stud-cap landmark IDs and their "
            "FULL PAGE normalized image_uv centers. Declare view_family='upright_above' only when the source "
            "shows an upright view from above the canonical assembly; otherwise use 'unconstrained'. "
            "Prefer landmarks with variation in all three world axes; "
            "the engine fits an orthographic source camera and rejects ambiguous or poor fits. Never fabricate "
            "correspondences for hidden landmarks. Use only already seated geometry for camera landmarks; "
            "incoming pieces drawn above the model beside arrows are exploded/in-motion views and do not "
            "share the final seated world pose. Their arrow-indicated destination is reviewed separately. "
            "If insufficient evidence remains, report a specific blocker. "
            "On repair, replace only this rejected instruction; the previous checkpoint is immutable. Fix the "
            "reported connection, side, mapping or order using source evidence. A rejected trial is NOT accepted "
            f"history. Bounded repair {attempt}/{limit}; feedback: {feedback}")
        result = infer(f"construct-{ordinal}", repair_prompt, images, model, heartbeat)
        raw = result.model_dump(mode="json")
        atomic_json(trial / "proposal.json", raw)
        state["last_proposal"] = last_proposal = raw
        findings = []
        scene = None
        failure_category = "ambiguity"
        correction_detail = "Correct this instruction using the supplied source and supported metadata."
        try:
            if result.blockers or not result.delta_json:
                raise ValueError("Unresolved source evidence: " + "; ".join(result.blockers or ["No proposal"]))
            raw_scene = validate_candidate(
                assemble_delta(result.delta_json, job, source_hash, page_count, previous).model_dump_json(),
                job, source_hash, page_count, previous, panel, page_index)
            atomic_json(trial / "raw-scene.json", raw_scene.model_dump(mode="json"))
            failure_category = "sequence"
            validate_sequence(raw_scene, previous, result.sequence)
            failure_category = "connection"
            geometry_report = prepare_geometry(raw_scene, directory / "geometry", geometry_root)
            atomic_json(trial / "geometry-validation.json", geometry_report)
            scene, spatial_report = solve_candidate(raw_scene, previous, result.connections, result.roots,
                                                     directory / "geometry")
            # Recheck append-only and unprivileged metadata after deterministic processing too.
            validate_candidate(scene.model_dump_json(), job, source_hash, page_count, previous, panel, page_index)
            atomic_json(trial / "spatial-validation.json", spatial_report)
            atomic_json(trial / "scene.json", scene.model_dump(mode="json"))
            failure_category = "source_view"
            source_image = pages_dir / f"page-{page_index:03d}.png"
            fits, cameras = source_views_for(scene, previous, result.source_views, directory / "geometry", source_image, policy)
            camera_evidence = {"scene_sha256": scene_digest(scene), "source_sha256": source_hash,
                "source_view_policy": policy,
                "source_page": page_index, "source_image_sha256": hashlib.sha256(source_image.read_bytes()).hexdigest(),
                "observations": [o.model_dump(mode="json") for o in result.source_views], "fits": fits}
            atomic_json(trial / "source-views.json", camera_evidence)
            if len(cameras) != len(result.source_views):
                failed = {key: {name: fit.get(name) for name in ("status", "reason", "rms_pixels",
                    "max_error_pixels", "landmark_residuals_pixels", "ambiguity")}
                    for key, fit in fits.items() if fit.get("status") != "fitted"}
                correction_detail = "Refine the source landmark identities/locations or preserve uncertainty. Diagnostics: " + json.dumps(failed)
                reasons = [f"{key}: {fit['status']}" + (f" (RMS {fit['rms_pixels']:.2f} px)" if fit.get('rms_pixels') is not None else '')
                           for key, fit in failed.items()]
                raise ValueError("Source camera cannot be established; " + "; ".join(reasons))
        except ValueError as error:
            findings = [{"category": failure_category, "step_ids": [],
                         "instance_ids": [], "description": str(error)[:8000],
                         "correction": correction_detail[:16000]}]
        if not findings:
            first_step = len((previous or {}).get("steps", [])) + 1
            if len(scene.steps) - first_step + 1 > 20:
                raise ValueError("Instruction exceeds bounded visual review batch")
            save("rendering_panel", "validating")
            renders = trial / "renders"
            rendered = render_candidate(trial / "scene.json", directory / "geometry", renders,
                                        check=heartbeat.check, first_step=first_step, source_views=cameras)
            new_steps = scene.model_dump(mode="json")["steps"][first_step - 1:]
            visual = infer(f"panel-review-{ordinal}",
                "\nReview this single proposed instruction against the official source BEFORE checkpointing. "
                "Image 1 is the official page; subsequent images are actual 3D snapshots with orthographic "
                "cameras fitted to source landmarks. Check the fitted view itself against distinctive shapes: "
                "a low fit residual does not establish that correspondences or near/far choices were correct. "
                "Review only the requested printed main instruction and its callouts. Check visible counts, "
                "part identities, colours, seating gaps, correct wing/side, printed sequence, detached callouts "
                "and attachment of the same physical IDs. Return structured findings with affected step/instance "
                "IDs and a source-grounded correction or a precise unresolved ambiguity. Do not demand invented "
                "intermediate steps for an ordinary instruction. Empty findings means no visible discrepancy "
                "found. Incoming parts may be depicted displaced by source arrows; compare the final seated "
                "snapshot to the arrow-indicated destination, not that exploded position. A camera fit must "
                "use the already seated source geometry. This is "
                "never hidden connector, collision, strength, human or physical certification. "
                "The image-fit policy only controls landmark reprojection tolerance. In alpha mode, a fit "
                "above the strict RMS limit is recorded separately as unverified image alignment; do not add "
                "a review finding solely for that relaxed RMS. Continue to reject visible assembly/side/count/order "
                "errors and unresolved source ambiguities under either policy. "
                f"Image-fit policy: {json.dumps(policy)}. "
                f"Page {page_index}; panel {json.dumps(panel)}; new snapshots {json.dumps(new_steps)}; "
                f"sequence evidence {json.dumps([v.model_dump(mode='json') for v in result.sequence])}; "
                f"camera fitting {json.dumps(fits)}",
                [pages_dir / f"page-{page_index:03d}.png", *[renders / item["screenshot"] for item in rendered["steps"]]],
                InstructionReview, heartbeat)
            findings = [item.model_dump(mode="json") for item in visual.findings]
            if not visual.coverage_agrees or not visual.assembly_agrees:
                if not findings:
                    findings = [{"category": "ambiguity", "step_ids": [], "instance_ids": [],
                                 "description": "Reviewer did not confirm coverage and visible assembly agreement",
                                 "correction": "Reconcile the requested source instruction and rendered snapshots."}]
            record = {"scene_sha256": scene_digest(scene), "raw_scene_sha256": scene_digest(raw_scene),
                      "source_view_policy": policy,
                      "source_view_checks": {key: {name: fit.get(name) for name in
                          ("status", "rms_pixels", "max_error_pixels", "strict_status", "accepted_with_relaxed_tolerance")}
                          for key, fit in fits.items()},
                      "review": visual.model_dump(mode="json"), "render_directory": str(renders),
                      "proposal_directory": str(trial), "source_page": page_index, "attempt": attempt,
                      "scope": "supported connector alignment and agent visual comparison; no global geometry/physical proof"}
            atomic_json(trial / "visual-review.json", record)
            if not findings:
                state["feedback"] = []
                state.pop("last_proposal", None)
                evidence_files = ["proposal.json", "raw-scene.json", "scene.json", "spatial-validation.json",
                    "geometry-validation.json", "source-views.json", "visual-review.json", "renders/report.json",
                    *["renders/" + item["screenshot"] for item in rendered["steps"]]]
                state["accepted"] = {"directory": str(trial), "source_sha256": source_hash,
                    "source_view_policy": policy,
                    "ordinal": ordinal, "page_index": page_index, "panel": panel,
                    "source_image_sha256": camera_evidence["source_image_sha256"],
                    "previous_scene_sha256": scene_digest(previous) if previous else None,
                    "scene_sha256": scene_digest(scene),
                    "files": {name: hashlib.sha256((trial / name).read_bytes()).hexdigest() for name in evidence_files}}
                save("instruction_reviewed")
                atomic_json(trial / "outcome.json", {"status": "accepted_by_pipeline", "attempt": attempt,
                    "source_view_policy": policy, "source_view_checks": record["source_view_checks"],
                    "raw_scene_sha256": scene_digest(raw_scene), "scene_sha256": scene_digest(scene),
                    "artifact_kind": "automatic_connector_corrected_candidate", "human_review": "not_run"})
                return scene, record
        state["feedback"] = findings
        atomic_json(trial / "outcome.json", {"status": "rejected", "attempt": attempt, "findings": findings})
        save("instruction_repair_pending")
    summary = "; ".join(item["description"] for item in state["feedback"]) or "Repair budget exhausted after interruption"
    save("instruction_repair_blocked", "blocked", {"code": "instruction_repair_exhausted",
        "message": f"Instruction {panel['number']} used {limit}/{limit} attempts. {summary}"[:4000],
        "evidence": state["trials"][-1] if state["trials"] else None})
    return None
