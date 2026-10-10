"""Import independent validation, bound to the exact raw candidate and actual image evidence.

This is a local operator boundary, not an anonymous API. It does not generate connector or
assembly findings and never treats a model's scene JSON critique as rendered validation.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Literal
from pydantic import Field
from PIL import Image
from ..core.models import StrictModel
from ..catalog import find_guide
from ..jobs.source_cache import cached_receipt
from ..reconstruction.checks import verify_assets
from ..releases.models import SceneV2, ReleaseValidation, digest, coverage_keys
from ..releases.evidence import source_registry, verify_source_evidence


class EvidenceFile(StrictModel):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    def verify(self, root: Path, image=False):
        file = root / self.path
        if file.is_symlink() or not file.resolve().is_relative_to(root.resolve()) or file.stat().st_size > 20_000_000:
            raise ValueError("Evidence file escapes bundle or exceeds limit")
        if hashlib.sha256(file.read_bytes()).hexdigest() != self.sha256:
            raise ValueError("Evidence file hash mismatch")
        if image:
            with Image.open(file) as content:
                if content.format != "PNG" or not 32 <= content.width <= 4096 or not 32 <= content.height <= 4096:
                    raise ValueError("Rendered evidence must be a bounded PNG")
                content.verify()
        return file


class ConnectorReport(StrictModel):
    scene_sha256: str
    producer_kind: Literal["deterministic_connector_checker"]
    checker_id: str = Field(min_length=1)
    checker_version: str = Field(min_length=1)
    status: Literal["pass", "fail", "unsupported"]
    supported_instance_ids: list[str]
    evidence: list[EvidenceFile] = Field(min_length=1)


class Comparison(StrictModel):
    step_id: str
    source_page_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    render: EvidenceFile
    decision: Literal["pass", "fail"]


class AssemblyReport(StrictModel):
    scene_sha256: str
    review_kind: Literal["source_render_comparison"]
    actor_type: Literal["agent"]
    reviewer_id: str = Field(min_length=1)
    status: Literal["pass", "fail"]
    render_report: EvidenceFile
    comparisons: list[Comparison] = Field(min_length=1)


class ValidationBundle(StrictModel):
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_index: dict
    connector_report: ConnectorReport
    assembly_report: AssemblyReport


def import_validation(store, job_id, bundle_dir: Path):
    from .runner import atomic_json
    job = store.get(job_id)
    if job["owner"]:
        raise ValueError("Stop the active job before importing independent validation")
    directory = store.root / "jobs" / job_id
    scene = SceneV2.model_validate_json((directory / "scene.json").read_text())
    bundle = ValidationBundle.model_validate_json((bundle_dir / "validation-bundle.json").read_text())
    if scene.set_number != job["set_number"] or scene.guide_id != job["guide_id"]:
        raise ValueError("Candidate identity does not match the queued job")
    raw_hash = digest(scene)
    if bundle.candidate_sha256 != raw_hash or any(report.scene_sha256 != raw_hash for report in
                                                (bundle.connector_report, bundle.assembly_report)):
        raise ValueError("Independent validation does not bind the current raw candidate")
    connector, assembly = bundle.connector_report, bundle.assembly_report
    if connector.status != "pass" or set(connector.supported_instance_ids) != {i.instance_id for i in scene.instances}:
        raise ValueError("Connector validation failed or leaves unsupported physical instances")
    from .checkers import run_registered_checks
    actual_checks = run_registered_checks(scene, directory / "geometry", connector.checker_id, connector.checker_version)
    for evidence in connector.evidence:
        evidence.verify(bundle_dir)
    if assembly.status != "pass" or any(c.decision != "pass" for c in assembly.comparisons):
        raise ValueError("Rendered assembly comparison has unresolved findings")
    comparisons = {comparison.step_id: comparison for comparison in assembly.comparisons}
    if len(comparisons) != len(assembly.comparisons) or set(comparisons) != {s.step_id for s in scene.steps}:
        raise ValueError("Rendered assembly comparison must cover every microstep exactly once")
    trusted = job["checkpoint"]
    if (trusted.get("render_scene_sha256") != raw_hash or
            trusted.get("render_report_sha256") != assembly.render_report.sha256):
        raise ValueError("Assembly report is not bound to this engine job's actual browser render receipt")
    render_file = assembly.render_report.verify(bundle_dir)
    rendered = json.loads(render_file.read_text())
    if rendered.get("status") != "rendered" or rendered.get("scene_sha256") != raw_hash:
        raise ValueError("Browser render report does not bind the candidate")
    rendered_steps = {step["step_id"]: step for step in rendered.get("steps", [])}
    if len(rendered_steps) != len(scene.steps) or set(rendered_steps) != set(comparisons):
        raise ValueError("Browser render report does not cover every microstep")
    for step_id, comparison in comparisons.items():
        if rendered_steps[step_id].get("png_sha256") != comparison.render.sha256:
            raise ValueError("Compared render image differs from actual browser capture")
    for source in scene.sources:
        guide = find_guide(scene.set_number, source.guide_id)
        receipt = cached_receipt(store.data_dir, scene.set_number, source.guide_id, guide["pdf_url"])
        if not receipt or receipt["sha256"] != source.source_sha256:
            raise ValueError("Independent source bytes no longer match candidate provenance")
    preview = None
    for step in scene.steps:
        comparison = comparisons[step.step_id]
        page = store.data_dir / "public/pages" / step.source.source_sha256 / f"page-{step.source.page_index:03d}.png"
        if hashlib.sha256(page.read_bytes()).hexdigest() != comparison.source_page_sha256:
            raise ValueError("Compared source image is not the verified official page")
        preview = comparison.render.verify(bundle_dir, image=True)
    geometry = verify_assets(directory / "geometry", [i.geometry_ref for i in scene.instances])
    if geometry["status"] != "pass":
        raise ValueError("Geometry provenance failed")
    validated = scene.model_copy(update={"geometry_check": actual_checks["geometry_check"],
                                         "connector_check": actual_checks["connector_check"]})
    validation = ReleaseValidation(scene_sha256=digest(validated), coverage_index_sha256=digest(bundle.source_index),
        expected_step_keys=bundle.source_index.get("expected_step_keys", []), covered_step_keys=coverage_keys(validated),
        source_evidence_verified=True, geometry_provenance_verified=True, assembly_review="pass", blockers=[],
        artifact_kind="automatic_reconstruction")
    validation.check(validated)
    verify_source_evidence(validated, validation, source_registry(), bundle.source_index)
    # Preserve raw candidate; check flags are a derived, hash-bound validation artifact.
    atomic_json(directory / "validated-scene.json", validated.model_dump(mode="json"))
    atomic_json(directory / "release-validation.json", validation.model_dump(mode="json"))
    atomic_json(directory / "verified-source-index.json", bundle.source_index)
    atomic_json(directory / "independent-validation.json", bundle.model_dump(mode="json"))
    atomic_json(directory / "validation-import.json", {"raw_scene_sha256": raw_hash,
        "validated_scene_sha256": digest(validated), "validation_bundle_sha256": digest(bundle), "preview": str(preview.resolve()),
        "bundle_directory": str(bundle_dir.resolve()), "actor_type": assembly.actor_type,
        "physical_build_check": "not_run", "publication": "not_performed"})
    return {"status": "validated_for_packaging", "raw_scene_sha256": raw_hash,
            "validated_scene_sha256": digest(validated), "human_release_approval": "not_requested"}
