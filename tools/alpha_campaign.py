"""Generate the selected ten-set local alpha campaign; never publish or approve content."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from _paths import ROOT
from guide2build.catalog import find_guide
from guide2build.engine.alpha import AlphaSourceReview, accept_alpha_correction
from guide2build.engine.alpha_runner import ALPHA_PIPELINE, alpha_runtime_choice, run_alpha_claimed
from guide2build.engine.geometry import verify_individual_assets
from guide2build.engine.runner import Heartbeat, atomic_json
from guide2build.engine.scheduling import run_queue_wave
from guide2build.engine.store import EngineStore, LeaseLost
from guide2build.engine.runtime import DEFAULT_MODEL, DEFAULT_THINKING_LEVEL, DEFAULT_INFERENCE_TIMEOUT_SECONDS
from guide2build.jobs.source_cache import cached_receipt
from guide2build.releases.models import SceneV2, digest

SELECTED = [
    ("30669", "alt-02"), ("60400", "booklet-01"), ("60400", "booklet-02"),
    ("31134", "booklet-01"), ("42163", "main"), ("76920", "main"),
    ("31129", "booklet-01"), ("42171", "main"), ("21343", "main"),
    ("21061", "main"), ("10316", "booklet-01"), ("10316", "booklet-02"), ("10316", "booklet-03"),
]
DEFAULT_MANIFEST = ROOT / "var/evidence/alpha-ten-set/campaign.json"
SAFE_RESOURCE = re.compile(r"^(parts/(?:s/)?|p/(?:8/|48/)?)[a-z0-9_-]+\.dat$")


def seed_geometry(data_dir):
    """Reuse individually verified DAT files only, never any old assembly poses."""
    inputs = [data_dir / "public/ldraw"]
    cases = json.loads((ROOT / "var/evidence/ten-set-construction/benchmark-cases.json").read_text())
    inputs.extend(ROOT / item["assets_path"] for item in cases)
    inputs.append(ROOT / "var/evidence/alpha-ten-set/30669-alt-02/geometry")
    destination = data_dir / "public/alpha-ldraw"
    destination.mkdir(parents=True, exist_ok=True)
    resources, mappings, materials = {}, {}, {}
    for source in dict.fromkeys(inputs):
        if not (source / "provenance.json").is_file():
            continue
        if source.resolve() != source or not source.is_relative_to(ROOT / "var"):
            raise ValueError("Individual part cache must remain within repository data")
        document = json.loads((source / "provenance.json").read_text())
        roots = [path for path, value in document.get("resources", {}).items() if value.get("classification") == "Part"]
        verify_individual_assets(source, roots)
        for name, record in document.get("resources", {}).items():
            if not SAFE_RESOURCE.fullmatch(name):
                raise ValueError("Unsafe individual resource in alpha seed")
            target = source / name
            if target.resolve() != target or not target.is_file() or target.stat().st_size > 1_000_000:
                raise ValueError("Unsafe individual alpha seed file")
            data = target.read_bytes()
            kind = re.search(rb"^0 !LDRAW_ORG (\S+)", data, re.M)
            if (not kind or kind[1].decode() not in {"Part", "Subpart", "Primitive", "8_Primitive", "48_Primitive"}
                    or kind[1].decode() != record.get("classification")
                    or len(data) > 1_000_000
                    or record.get("url") != "https://library.ldraw.org/library/official/" + name
                    or hashlib.sha256(data).hexdigest() != record.get("sha256")):
                raise ValueError("Unverified individual resource in alpha seed")
            if name in resources and resources[name]["sha256"] != record["sha256"]:
                raise ValueError("Conflicting individual part versions in alpha seed")
            if name not in resources:
                out = destination / name
                if out.is_symlink() or out.resolve() != out:
                    raise ValueError("Unsafe alpha geometry destination")
                out.parent.mkdir(parents=True, exist_ok=True)
                if out.exists() and hashlib.sha256(out.read_bytes()).hexdigest() != record["sha256"]:
                    raise ValueError("Existing alpha geometry differs; preserve it for review")
                shutil.copyfile(target, out)
                resources[name] = record
        for alias, name in document.get("file_map", {}).items():
            if alias in mappings and mappings[alias] != name:
                raise ValueError("Conflicting individual dependency aliases")
            mappings[alias] = name
        for name, record in document.get("materials", {}).items():
            if name != "LDConfig.ldr":
                raise ValueError("Unexpected alpha material resource")
            if name in materials and materials[name]["sha256"] != record["sha256"]:
                raise ValueError("Conflicting material versions")
            materials[name] = record
            shutil.copyfile(source / name, destination / name)
    if len(resources) > 8192 or sum(v.get("bytes", 0) for v in resources.values()) > 256_000_000:
        raise ValueError("Alpha seed exceeds bounded individual cache budget")
    document = {"library": "https://library.ldraw.org/library/official/", "scope": "individual parts only; no assembly data",
        "roots": sorted(Path(p).stem for p, r in resources.items() if r["classification"] == "Part"),
        "resources": resources, "file_map": mappings, "materials": materials}
    atomic_json(destination / "provenance.json", document)
    verify_individual_assets(destination, [p for p, r in resources.items() if r["classification"] == "Part"])
    return {"path": str(destination), "designs": len(document["roots"]), "resources": len(resources),
        "sha256": hashlib.sha256((destination / "provenance.json").read_bytes()).hexdigest()}


def register_assisted(store, job, scene_path, geometry, *, lease_wait=0):
    """Attach a frozen local assisted completion without relabelling it automatic."""
    scene = SceneV2.model_validate_json(scene_path.read_text())
    if (scene.set_number, scene.guide_id) != (job["set_number"], job["guide_id"]):
        raise ValueError("Assisted candidate differs from selected job")
    if scene.status != "needs_review" or getattr(scene, "reviews", []) or any(getattr(scene, k) != "not_run"
            for k in ("geometry_check", "connector_check", "physical_build_check")):
        raise ValueError("Alpha candidate cannot grant approval")
    verify_individual_assets(geometry, [p.geometry_ref for p in scene.instances])
    guide = find_guide(scene.set_number, scene.guide_id)
    receipt = cached_receipt(store.data_dir, scene.set_number, scene.guide_id, guide["pdf_url"])
    selected_source = next((s for s in scene.sources if s.guide_id == job["guide_id"]), None)
    if not receipt or not selected_source or receipt["sha256"] != selected_source.source_sha256:
        raise ValueError("Assisted source differs from selected official receipt")
    source_hash = selected_source.source_sha256
    report_path = scene_path.parent / "completion-report.json"
    report = json.loads(report_path.read_text())
    source_pages = guide["expected_page_count"]
    main_steps = len({(s.section_id, s.main_step_number) for s in scene.steps
        if s.main_step_number is not None and s.source.source_sha256 == source_hash})
    coverage = report.get("coverage", {})
    if (report.get("scene_sha256") != digest(scene) or report.get("source_sha256") != source_hash
            or (report.get("set_number"), report.get("guide_id")) != (scene.set_number, scene.guide_id)
            or coverage.get("main_steps") != main_steps
            or coverage.get("expected_main_steps") != main_steps):
        raise ValueError("Assisted completion report must bind the scene, source and full instruction count")
    expected = guide.get("expected_main_steps")
    if expected is not None and main_steps != expected:
        raise ValueError("Assisted candidate does not cover the curated instruction count")
    if expected is None:
        review = report.get("full_source_review", {})
        if (review.get("source_sha256") != source_hash or review.get("page_count") != source_pages
                or review.get("status") != "all_pages_reviewed_by_agent"
                or sorted(review.get("reviewed_page_indexes", [])) != list(range(source_pages))):
            raise ValueError("Assisted completion requires a full selected-source review receipt")
        bindings = {value["page_index"]: value for value in report.get("source_evidence", [])}
        if sorted(bindings) != list(range(source_pages)):
            raise ValueError("Assisted page review must bind every official rendered page")
        pages = store.data_dir / "public/pages" / source_hash
        for index, binding in bindings.items():
            page = pages / f"page-{index:03d}.png"
            if (page.resolve() != page or not page.is_file() or page.stat().st_size > 32_000_000
                    or hashlib.sha256(page.read_bytes()).hexdigest() != binding.get("sha256")):
                raise ValueError("Assisted reviewed-page hash differs from official render")
    previous = job["checkpoint"].get("candidate")
    if previous:
        if digest(previous) == digest(scene):
            _refresh_assisted_notes(store, job, scene, report, report_path)
            return
        lineage = report.get("lineage", {})
        raw = scene.model_dump(mode="json")
        if (job["checkpoint"].get("alpha_source_complete")
                or lineage.get("parent_job_id") != job["id"]
                or lineage.get("parent_scene_sha256") != digest(previous)
                or raw["instances"][:len(previous["instances"])] != previous["instances"]
                or raw["steps"][:len(previous["steps"])] != previous["steps"]):
            raise ValueError("Assisted append must bind and preserve the accepted source-derived prefix")
    if job["state"] == "blocked" and job["owner"] is None:
        # This imports an evidenced assisted completion; consumed model trials
        # remain in its checkpoint and are never made available for inference.
        store.retry(job["id"])
    owner = uuid.uuid4().hex
    deadline = time.monotonic() + lease_wait
    claimed = store.claim(owner, job_id=job["id"])
    while not claimed and time.monotonic() < deadline:
        time.sleep(0.05)
        claimed = store.claim(owner, job_id=job["id"])
    if not claimed:
        raise ValueError("Cannot lease selected assisted alpha job")
    try:
        if claimed["checkpoint"].get("candidate") != previous:
            raise ValueError("Alpha prefix changed before assisted registration claimed it")
        _write_assisted(store, claimed, owner, scene, scene_path, geometry, receipt, report, report_path, source_pages)
    except BaseException as error:
        # A failed reversible import must not occupy the global inference lease.
        # Preserve the original checkpoint and any frozen input evidence.
        checkpoint = claimed["checkpoint"] | {"stage": "alpha_registration_blocked"}
        try:
            store.checkpoint(job["id"], owner, checkpoint, "blocked",
                {"code": "alpha_registration_failed", "message": str(error)[:2000]})
        except (LeaseLost, InterruptedError):
            pass
        raise


def _assisted_review_notes(value, scope=""):
    """Retain source review metadata while exposing grouped notes as plain text."""
    if isinstance(value, str):
        return [{"reason": value, "scope": scope}] if value else []
    if isinstance(value, list):
        return [note for item in value for note in _assisted_review_notes(item, scope)]
    if not isinstance(value, dict):
        return []
    reason = next((value[key] for key in ("reason", "message", "note", "description")
                   if isinstance(value.get(key), str) and value[key]), None)
    if reason is not None:
        return [{**value, "reason": reason, **({"scope": scope} if scope and "scope" not in value else {})}]
    return [note for key, item in value.items() if key != "status"
            for note in _assisted_review_notes(item, f"{scope}.{key}" if scope else key)]


def _report_assisted_notes(report):
    notes = []
    for key in ("review_items", "uncertainties", "review_notes", "uncertainty_notes", "alpha_notes"):
        notes.extend(_assisted_review_notes(report.get(key, [])))
    return _merge_assisted_notes([], notes)


def _merge_assisted_notes(previous, extra):
    result, seen = [], set()
    for note in _assisted_review_notes(previous) + extra:
        key = digest(note)
        if key not in seen:
            result.append(note)
            seen.add(key)
    return result


def _checkpoint_assisted_notes(checkpoint):
    return _merge_assisted_notes(checkpoint.get("alpha_review_notes", []),
        _assisted_review_notes(checkpoint.get("uncertainty_notes", [])))


def _refresh_assisted_notes(store, job, scene, report, report_path):
    """Refresh notes and their evidence on the frozen completion, without inference."""
    checkpoint = job["checkpoint"]
    if (not checkpoint.get("alpha_source_complete")
            or checkpoint.get("artifact_kind") != "pdf_assisted_alpha_completion"):
        return
    notes = _merge_assisted_notes(_checkpoint_assisted_notes(checkpoint), _report_assisted_notes(report))
    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    if (notes == checkpoint.get("uncertainty_notes", [])
            and notes == checkpoint.get("alpha_review_notes", [])
            and checkpoint.get("assisted_note_report_sha256") == report_sha256):
        return
    owner = uuid.uuid4().hex
    claimed = store.claim(owner, job_id=job["id"])
    if not claimed:
        raise ValueError("Cannot lease selected assisted alpha metadata refresh")
    try:
        if claimed["checkpoint"] != checkpoint or digest(claimed["checkpoint"]["candidate"]) != digest(scene):
            raise ValueError("Frozen completion changed before its notes refresh")
        refreshed = checkpoint | {"alpha_review_notes": notes, "uncertainty_notes": notes,
            "assisted_note_report_sha256": report_sha256}
        atomic_json(store.root / "jobs" / job["id"] / "alpha-report.json", report)
        store.checkpoint(job["id"], owner, refreshed, "paused")
    except BaseException:
        store.checkpoint(job["id"], owner, claimed["checkpoint"], "paused", claimed["error"])
        raise


def _write_assisted(store, job, owner, scene, scene_path, geometry, receipt, report, report_path, source_pages):
    directory = store.root / "jobs" / job["id"]
    prior_notes = _checkpoint_assisted_notes(job["checkpoint"])
    directory.mkdir(parents=True, exist_ok=True)
    if job["checkpoint"].get("candidate"):
        parent = directory / "assisted-parent-scene.json"
        previous = job["checkpoint"]["candidate"]
        if parent.exists() and digest(json.loads(parent.read_text())) != digest(previous):
            raise ValueError("Existing assisted parent archive differs; preserve it for review")
        atomic_json(parent, previous)
    shutil.copytree(geometry, directory / "geometry", dirs_exist_ok=True)
    mains = len({(s.section_id, s.main_step_number) for s in scene.steps
        if s.main_step_number is not None and s.source.source_sha256 == receipt["sha256"]})
    checkpoint = job["checkpoint"] | {"stage": "alpha_complete", "alpha_runner_version": ALPHA_PIPELINE,
        "artifact_kind": "pdf_assisted_alpha_completion", "candidate": scene.model_dump(mode="json"),
        "source_sha256": receipt["sha256"], "primary_scene_source_sha256": scene.source_sha256,
        "page_count": source_pages, "completed_pages": source_pages,
        "alpha_completed_pages": source_pages, "alpha_source_complete": True,
        "completed_panels": mains, "total_panels": mains,
        "source_coverage": "assisted_complete_source_review_alpha_unverified",
        "uncertainty_notes": _report_assisted_notes(report),
        "assisted_note_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "assisted_lineage": {"scene_path": str(scene_path), "scene_sha256": digest(scene),
            "completion_report": str(report_path), "source_lineage": report.get("lineage", {}),
            "unassisted_success": False},
        "human_review": "not_run", "physical_build": "not_run"}
    notes = _merge_assisted_notes(prior_notes, checkpoint["uncertainty_notes"])
    checkpoint["alpha_review_notes"] = notes
    checkpoint["uncertainty_notes"] = notes
    atomic_json(directory / "scene.json", scene.model_dump(mode="json"), compact=True)
    atomic_json(directory / "source-receipt.json", receipt)
    atomic_json(directory / "alpha-report.json", report | {"artifact_kind": "pdf_assisted_alpha_completion"})
    store.checkpoint(job["id"], owner, checkpoint, "paused")


class _NoInference:
    def call(self, *args, **kwargs):
        raise RuntimeError("An agent source correction may only replay its accepted batch; inference is disabled")


def correct_empty_batch(store, job, source_review, *, rejected_trial=None):
    """Record actual agent page inspection, then use normal accepted-batch recovery."""
    review = AlphaSourceReview.model_validate(source_review)
    guide = find_guide(job["set_number"], job["guide_id"])
    receipt = cached_receipt(store.data_dir, job["set_number"], job["guide_id"], guide["pdf_url"])
    if (job["config"].get("generation_mode") != "alpha_fast" or not receipt
            or receipt["sha256"] != review.source_sha256
            or job["checkpoint"].get("source_sha256") != receipt["sha256"]):
        raise ValueError("Agent correction requires the selected frozen official alpha source")
    checkpoint = job["checkpoint"]
    state = checkpoint.get("alpha_chunks", {}).get(str(checkpoint.get("alpha_completed_chunks", 0)), {})
    trials = state.get("trials", [])
    if not trials or state.get("accepted"):
        raise ValueError("Agent correction requires a pending rejected source batch")
    if job["state"] == "blocked" and job["owner"] is None:
        store.retry(job["id"])
    owner = uuid.uuid4().hex
    claimed = store.claim(owner, job_id=job["id"])
    if not claimed:
        raise ValueError("Cannot lease the selected agent source correction")
    checkpoint = claimed["checkpoint"]

    def save(stage, state="constructing", error=None):
        checkpoint["stage"] = stage
        checkpoint["uncertainty_notes"] = checkpoint.get("alpha_review_notes", [])
        store.checkpoint(job["id"], owner, checkpoint, state, error)

    try:
        if checkpoint != job["checkpoint"]:
            raise ValueError("Rejected batch changed before the source correction was leased")
        with Heartbeat(store, job["id"], owner) as heartbeat:
            accepted = accept_alpha_correction(job=claimed, checkpoint=checkpoint,
                directory=store.root / "jobs" / job["id"], source_hash=receipt["sha256"],
                pages_dir=store.data_dir / "public/pages" / receipt["sha256"],
                page_count=guide["expected_page_count"], rejected_trial=rejected_trial or trials[-1],
                source_review=review.model_dump(mode="json"), save=save, heartbeat=heartbeat)
        # This promotes the separately evidenced correction through the same
        # receipt/source/counter checks as crash recovery, with no model call.
        run_alpha_claimed(store, store.get(job["id"]), owner, provider=_NoInference(), max_chunks=1)
        latest = store.get(job["id"])
        if latest["state"] != "paused" or latest["owner"] is not None:
            raise ValueError("Recorded source correction did not promote its bounded empty batch")
        return accepted
    except BaseException as error:
        if store.get(job["id"])["owner"] == owner:
            try:
                save("alpha_source_correction_blocked", "blocked",
                    {"code": "alpha_source_correction_failed", "message": str(error)[:2000]})
            except (LeaseLost, InterruptedError):
                pass
        raise


def set_alpha_runtime(store, job, model, thinking_level, reason):
    """Runtime settings are immutable; retain this diagnostic for older callers."""
    raise ValueError("Frozen ADK runtime cannot change; enqueue a new revision with the chosen runtime")


def summary(store, manifest, *, cache=None):
    # This optional cache belongs only to the current command. Final handoff
    # calls omit it and hydrate/hash every candidate again. Live progress avoids
    # rereading all unchanged large scenes whenever another set saves a batch.
    metadata = {row["id"]: row for row in store.queue_snapshot(manifest["job_ids"])} if cache is not None else {}
    result = []
    for identity in manifest["job_ids"]:
        row = metadata.get(identity)
        cache_key = None if row is None else (row["updated"], row["state"], row["cancel"],
            row["alpha_source_complete"], row["alpha_completed_pages"], row["completed_panels"],
            json.dumps(row["error"], sort_keys=True))
        if cache is not None and identity in cache and cache[identity][0] == cache_key:
            result.append(dict(cache[identity][1]))
            continue
        job = store.get(identity)
        cp = job["checkpoint"]
        scene = cp.get("candidate") or {}
        main_count = len({(step["section_id"], step["main_step_number"])
            for step in scene.get("steps", []) if step["main_step_number"] is not None
            and step["source"]["source_sha256"] == cp.get("source_sha256")})
        item = {"job_id": identity, "set_number": job["set_number"], "guide_id": job["guide_id"],
            "state": job["state"], "stage": cp.get("stage", "queued"),
            "completed_pages": cp.get("alpha_completed_pages", cp.get("completed_pages", 0)),
            "page_count": cp.get("page_count"), "main_steps": main_count,
            "snapshots": len(scene.get("steps", [])), "pieces": len(scene.get("instances", [])),
            "all_source_pages_processed": bool(cp.get("alpha_source_complete")), "error": job["error"],
            "artifact_kind": cp.get("artifact_kind", job["config"].get("artifact_kind", "automatic_approximate_alpha")),
            "source_coverage": cp.get("source_coverage", "not_started"),
            "runtime_choice": alpha_runtime_choice(job["config"], cp, historical=True),
            "source_sha256": cp.get("source_sha256"), "scene_sha256": digest(scene) if scene else None}
        result.append(item)
        # A worker may have saved between the lightweight snapshot and hydration.
        # Its updated value must agree before this summary can be reused.
        if cache is not None and job["updated"] == row["updated"]:
            cache[identity] = cache_key, dict(item)
    return {"recorded_at": datetime.now(timezone.utc).isoformat(), "selected_sets": 10, "selected_booklets": 13,
        "provider_pause": store.provider_pause(), "jobs": result, "human_review": "not_run", "physical_build": "not_run",
        "publication": "not_performed"}


def run_campaign_round(store, manifest, *, workers=1, skip_sets=(), on_result=None, run_job=None):
    """One bounded source-batch per selected job, without crossing set dependencies."""
    rows = {job["id"]: job for job in store.queue_snapshot(manifest["job_ids"])}
    selected = []
    for identity in manifest["job_ids"]:
        job = rows[identity]
        if job["set_number"] in skip_sets or job["alpha_source_complete"]:
            continue
        if job["state"] in {"failed", "cancelled", "awaiting_approval"} or job["cancel"]:
            continue
        # These official booklets continue the same physical assembly. A later
        # booklet is not an independent set and cannot run ahead of its prefix.
        if job["set_number"] == "10316" and job["guide_id"] in {"booklet-02", "booklet-03"}:
            predecessor = "booklet-01" if job["guide_id"] == "booklet-02" else "booklet-02"
            if not any(prior["set_number"] == job["set_number"] and prior["guide_id"] == predecessor
                       and prior["alpha_source_complete"] and not prior["owner"] for prior in rows.values()):
                continue
        if job["state"] == "blocked":
            if (job["error"] or {}).get("code") != "alpha_predecessor_required":
                continue
            store.retry(identity)
        selected.append(identity)
    wave = run_queue_wave(store, job_ids=selected, workers=workers, max_panels=1,
                          on_result=on_result, run_job=run_job)
    latest = {job["id"]: job for job in store.queue_snapshot(selected)}
    wave["progressed"] = any(latest[identity]["alpha_completed_pages"] > rows[identity]["alpha_completed_pages"]
                             for identity in selected)
    return wave


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "var")
    parser.add_argument("--campaign-file", type=Path, default=DEFAULT_MANIFEST)
    sub = parser.add_subparsers(dest="command", required=True)
    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--revision", default="alpha-ten-sets-01")
    enqueue.add_argument("--page-batch-size", type=int, choices=range(4, 9), default=6)
    enqueue.add_argument("--model", default=DEFAULT_MODEL)
    enqueue.add_argument("--thinking-level", choices=("low", "medium", "high"), default=DEFAULT_THINKING_LEVEL)
    enqueue.add_argument("--provider-timeout", type=float, default=DEFAULT_INFERENCE_TIMEOUT_SECONDS)
    enqueue.add_argument("--max-model-calls", type=int, default=3)
    run = sub.add_parser("run")
    run.add_argument("--max-rounds", type=int, default=0, help="0 continues selected source jobs until complete or blocked")
    run.add_argument("--skip-set", action="append", default=[], help="Temporarily skip a set being completed by an assisted author")
    run.add_argument("--workers", type=int, choices=(1, 2), default=1,
                     help="Explicit concurrency for independent sets; booklets of one set stay sequential")
    sub.add_parser("status")
    registration = sub.add_parser("register-assisted")
    registration.add_argument("--set", dest="set_number", required=True)
    registration.add_argument("--guide", required=True)
    registration.add_argument("--scene", type=Path, required=True)
    registration.add_argument("--geometry", type=Path, required=True)
    registration.add_argument("--lease-wait", type=float, default=0,
        help="Wait up to 60 seconds for an owned generation batch to release its lease")
    correction = sub.add_parser("correct-empty-batch")
    correction.add_argument("--set", dest="set_number", required=True)
    correction.add_argument("--guide", required=True)
    correction.add_argument("--source-review", type=Path, required=True)
    correction.add_argument("--rejected-trial", type=Path)
    args = parser.parse_args()
    store = EngineStore(args.data_dir)
    if args.command == "enqueue":
        if args.campaign_file.exists():
            raise ValueError("Campaign already exists; resume it rather than reset its counters")
        geometry = seed_geometry(store.data_dir)
        jobs = []
        for set_number, guide_id in SELECTED:
            guide = find_guide(set_number, guide_id)
            receipt = cached_receipt(store.data_dir, set_number, guide_id, guide["pdf_url"])
            job = store.enqueue(set_number, guide_id, {"generation_mode": "alpha_fast", "quality_profile": "alpha",
                "pipeline": ALPHA_PIPELINE, "model": args.model, "thinking_level": args.thinking_level,
                "provider": "google_adk", "provider_timeout": args.provider_timeout, "max_model_calls": args.max_model_calls,
                "revision": args.revision, "parts_revision": geometry["sha256"],
                "source_sha256": receipt["sha256"] if receipt else None,
                "alpha_page_batch_size": args.page_batch_size, "max_chunk_attempts": 5,
                "artifact_kind": "automatic_approximate_alpha"})
            jobs.append(job["id"])
        manifest = {"revision": args.revision, "job_ids": jobs, "geometry": geometry,
            "source_scope": [{"set_number": s, "guide_id": g} for s, g in SELECTED],
            "quality": "approximate_alpha_needs_review", "human_review": "not_run", "physical_build": "not_run"}
        atomic_json(args.campaign_file, manifest)
    else:
        manifest = json.loads(args.campaign_file.read_text())
    if args.command == "register-assisted":
        if not 0 <= args.lease_wait <= 60:
            raise ValueError("Assisted lease wait must be between 0 and 60 seconds")
        job = next(store.get(j) for j in manifest["job_ids"]
            if (store.get(j)["set_number"], store.get(j)["guide_id"]) == (args.set_number, args.guide))
        register_assisted(store, job, args.scene.resolve(), args.geometry.resolve(), lease_wait=args.lease_wait)
    if args.command == "correct-empty-batch":
        job = next(store.get(j) for j in manifest["job_ids"]
            if (store.get(j)["set_number"], store.get(j)["guide_id"]) == (args.set_number, args.guide))
        accepted = correct_empty_batch(store, job, json.loads(args.source_review.read_text()),
            rejected_trial=args.rejected_trial.resolve() if args.rejected_trial else None)
        print(json.dumps({"agent_correction": accepted}, indent=2))
    if args.command == "run":
        if args.max_rounds < 0:
            raise ValueError("Round ceiling cannot be negative")
        round_number = 0
        summary_cache = {}
        while not store.provider_pause():

            def report_result(result):
                latest = store.queue_snapshot([result["job_id"]])[0]
                print(json.dumps({"job_id": latest["id"], "set": latest["set_number"], "guide": latest["guide_id"],
                    "state": latest["state"], "pages": latest["alpha_completed_pages"],
                    "mains": latest["completed_panels"], "error": latest["error"]}), flush=True)
                atomic_json(args.campaign_file.parent / "status.json", summary(store, manifest, cache=summary_cache))

            wave = run_campaign_round(store, manifest, workers=args.workers, skip_sets=args.skip_set,
                                      on_result=report_result)
            round_number += 1
            if not wave["progressed"] or (args.max_rounds and round_number >= args.max_rounds):
                break
            time.sleep(0.1)
    report = summary(store, manifest)
    atomic_json(args.campaign_file.parent / "status.json", report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
