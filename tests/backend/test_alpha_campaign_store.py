import pytest
import importlib
import json
from pathlib import Path

from guide2build.core.models import SceneManifest
from guide2build.engine.store import EngineStore
from guide2build import catalog as catalog_module
from guide2build.releases.models import adapt_v1, digest


def test_explicit_alpha_job_does_not_invent_pilot_approval(tmp_path):
    store = EngineStore(tmp_path)
    store.gate_campaign()
    strict = store.enqueue("31134", "booklet-01", {"revision": "strict"})
    alpha = store.enqueue("31134", "booklet-01", {"revision": "alpha", "generation_mode": "alpha_fast",
        "quality_profile": "alpha"})
    assert store.claim("strict-owner", job_id=strict["id"]) is None
    leased = store.claim("alpha-owner", job_id=alpha["id"])
    assert leased["id"] == alpha["id"]
    assert store.get(strict["id"])["state"] == "queued"
    assert all(job["state"] != "awaiting_approval" for job in store.list())
    assert store.claim("another-owner", job_id=alpha["id"]) is None


def test_fast_mode_requires_explicit_alpha_and_preserves_provider_pause(tmp_path):
    store = EngineStore(tmp_path)
    with pytest.raises(ValueError, match="explicit alpha"):
        store.enqueue("31134", "booklet-01", {"generation_mode": "alpha_fast"})
    with pytest.raises(ValueError, match="Unknown generation"):
        store.enqueue("31134", "booklet-01", {"generation_mode": "anything"})
    job = store.enqueue("31134", "booklet-01", {"generation_mode": "alpha_fast", "quality_profile": "alpha"})
    store.pause_provider({"code": "subscription_limit"})
    assert store.claim("alpha", job_id=job["id"]) is None


@pytest.fixture
def assisted_import(tmp_path, monkeypatch, scene_data):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    campaign = importlib.import_module("alpha_campaign")
    guide = {"pdf_url": "https://www.lego.com/en-us/service/building-instructions/99999",
        "expected_page_count": 8, "expected_main_steps": 3}
    monkeypatch.setattr(campaign, "find_guide", lambda *args: guide)
    monkeypatch.setattr(catalog_module, "find_guide", lambda *args: guide)
    store = EngineStore(tmp_path)
    job = store.enqueue("99999", "synthetic", {"generation_mode": "alpha_fast", "quality_profile": "alpha"})
    monkeypatch.setattr(campaign, "verify_individual_assets", lambda *args: {"status": "synthetic_test_only"})
    monkeypatch.setattr(campaign, "cached_receipt", lambda *args: {"sha256": scene_data["source_sha256"]})
    scene = adapt_v1(SceneManifest.model_validate(scene_data), guide["pdf_url"], 8)
    scene.status = "needs_review"
    source = tmp_path / "input"
    source.mkdir()
    scene_path = source / "scene.json"
    scene_path.write_text(scene.model_dump_json())
    report = {"scene_sha256": digest(scene), "source_sha256": scene.source_sha256,
        "set_number": scene.set_number, "guide_id": scene.guide_id,
        "coverage": {"main_steps": 3, "expected_main_steps": 3}}
    (source / "completion-report.json").write_text(json.dumps(report))
    geometry = tmp_path / "synthetic-geometry"
    geometry.mkdir()
    return campaign, store, job, scene_path, geometry, guide, report


def test_failed_assisted_import_releases_lease_and_retains_attempts(assisted_import, monkeypatch):
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    owner = "prior-owner"
    store.claim(owner, job_id=job["id"])
    checkpoint = {"stage": "paused", "alpha_chunks": {"0": {"used": 5, "limit": 5, "trials": ["retained"]}}}
    store.checkpoint(job["id"], owner, checkpoint, "paused")
    def fail(*args, **kwargs):
        raise OSError("Original synthetic copy failure")
    monkeypatch.setattr(campaign.shutil, "copytree", fail)
    with pytest.raises(OSError, match="copy failure"):
        campaign.register_assisted(store, store.get(job["id"]), scene_path, geometry)
    failed = store.get(job["id"])
    assert failed["state"] == "blocked" and failed["owner"] is None
    assert failed["checkpoint"]["alpha_chunks"] == checkpoint["alpha_chunks"]
    assert failed["error"]["code"] == "alpha_registration_failed"
    another = store.enqueue("99999", "synthetic", {"revision": "second"})
    assert store.claim("next-owner", job_id=another["id"]) is not None


def test_partial_assisted_scene_cannot_claim_curated_or_unknown_full_coverage(assisted_import):
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    guide["expected_main_steps"] = 4
    with pytest.raises(ValueError, match="curated instruction count"):
        campaign.register_assisted(store, job, scene_path, geometry)
    guide["expected_main_steps"] = None
    with pytest.raises(ValueError, match="full selected-source review receipt"):
        campaign.register_assisted(store, job, scene_path, geometry)
    assert store.get(job["id"])["state"] == "queued"
    assert store.get(job["id"])["owner"] is None


def test_explicit_resume_of_complete_assisted_job_preserves_uncertainty_notes(assisted_import):
    from guide2build.engine.alpha_runner import run_alpha_claimed
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    store.claim("initial", job_id=job["id"])
    notes = [{"kind": "material", "reason": "Original synthetic alpha ambiguity", "alternatives": ["4", "14"]}]
    store.checkpoint(job["id"], "initial", {"alpha_source_complete": True, "alpha_completed_pages": 8,
        "source_coverage": "assisted_complete_source_review_alpha_unverified", "uncertainty_notes": notes}, "paused")
    claimed = store.claim("resume", job_id=job["id"])
    assert run_alpha_claimed(store, claimed, "resume")
    final = store.get(job["id"])
    assert final["owner"] is None and final["state"] == "paused"
    assert final["checkpoint"]["uncertainty_notes"] == notes
    assert final["checkpoint"]["completed_pages"] == 8


def test_cumulative_assisted_import_binds_current_booklet_not_primary(assisted_import, monkeypatch):
    from copy import deepcopy
    from guide2build.releases.models import SceneV2
    campaign, store, original_job, scene_path, geometry, guide, report = assisted_import
    original = json.loads(scene_path.read_text())
    current_hash = "b" * 64
    updated = deepcopy(original)
    updated.update(guide_id="second", revision="synthetic-cumulative-second")
    updated["sources"].append({"guide_id": "second", "source_sha256": current_hash,
        "official_url": guide["pdf_url"], "page_count": 8})
    updated["sections"].append({"section_id": "second", "source_sha256": current_hash,
        "label": "Original synthetic second booklet"})
    extra = deepcopy(updated["steps"][-1])
    extra.update(step_id="second-step-1", section_id="second", main_step_number=1,
        action="inspect", assembly_group_id=None, introduced_instance_ids=[], active_instance_ids=[])
    extra["source"]["source_sha256"] = current_hash
    updated["steps"].append(extra)
    updated["steps"].append({**extra, "step_id": "second-unnumbered", "main_step_number": None})
    updated = SceneV2.model_validate(updated).model_dump(mode="json")
    scene_path.write_text(json.dumps(updated))
    guide["expected_main_steps"] = 1
    monkeypatch.setattr(campaign, "cached_receipt", lambda *args: {"sha256": current_hash})
    report.update(guide_id="second", source_sha256=current_hash, scene_sha256=digest(updated),
        coverage={"main_steps": 1, "expected_main_steps": 1})
    scene_path.with_name("completion-report.json").write_text(json.dumps(report))
    job = store.enqueue("99999", "second", {"generation_mode": "alpha_fast", "quality_profile": "alpha"})
    campaign.register_assisted(store, job, scene_path, geometry)
    latest = store.get(job["id"])
    checkpoint = latest["checkpoint"]
    assert checkpoint["completed_panels"] == 1
    assert checkpoint["source_sha256"] == current_hash
    assert checkpoint["primary_scene_source_sha256"] == original["source_sha256"]
    assert checkpoint["candidate"]["steps"][:len(original["steps"])] == original["steps"]
    assert latest["owner"] is None and latest["state"] == "paused"
    status = campaign.summary(store, {"job_ids": [job["id"]]})["jobs"][0]
    assert status["main_steps"] == 1
    assert status["snapshots"] == len(updated["steps"])


def test_grouped_assisted_uncertainties_import_and_survive_resume(assisted_import):
    from guide2build.engine.alpha_runner import run_alpha_claimed
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    report["uncertainties"] = {"status": "needs_review", "instances": [
        {"instance_id": "synthetic-piece", "note": "Source mould choice remains approximate."}],
        "camera": {"limitations": ["Source camera fit has not been certified."]}}
    scene_path.with_name("completion-report.json").write_text(json.dumps(report))
    campaign.register_assisted(store, job, scene_path, geometry)
    latest = store.get(job["id"])
    notes = latest["checkpoint"]["uncertainty_notes"]
    assert [note["reason"] for note in notes] == [
        "Source mould choice remains approximate.", "Source camera fit has not been certified."]
    assert notes[0]["instance_id"] == "synthetic-piece" and notes[0]["scope"] == "instances"
    assert notes[1]["scope"] == "camera.limitations"
    assert latest["owner"] is None and latest["state"] == "paused"
    claimed = store.claim("resume", job_id=job["id"])
    assert run_alpha_claimed(store, claimed, "resume")
    assert store.get(job["id"])["checkpoint"]["uncertainty_notes"] == notes


@pytest.mark.parametrize("prefix_note_key", ["alpha_review_notes", "uncertainty_notes"])
def test_assisted_append_archives_prefix_and_preserves_counters_and_all_notes(assisted_import, prefix_note_key):
    from copy import deepcopy
    from guide2build.engine.alpha_runner import run_alpha_claimed
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    previous = json.loads(scene_path.read_text())
    updated = deepcopy(previous)
    extra = deepcopy(updated["steps"][-1])
    extra.update(step_id="synthetic-append", main_step_number=4, action="inspect", assembly_group_id=None,
        introduced_instance_ids=[], active_instance_ids=[])
    updated["steps"].append(extra)
    guide["expected_main_steps"] = 4
    from guide2build.releases.models import SceneV2
    updated = SceneV2.model_validate(updated).model_dump(mode="json")
    scene_path.write_text(json.dumps(updated))
    report.update(scene_sha256=digest(updated), coverage={"main_steps": 4, "expected_main_steps": 4},
        lineage={"parent_job_id": job["id"], "parent_scene_sha256": digest(previous)},
        review_items=[{"reason": "Original synthetic completion material note"}])
    scene_path.with_name("completion-report.json").write_text(json.dumps(report))
    counters = {"0": {"used": 5, "limit": 5, "trials": ["frozen-original-trial"]}}
    prefix_notes = [{"reason": "Original synthetic prefix pose note"}]
    store.claim("initial", job_id=job["id"])
    store.checkpoint(job["id"], "initial", {"candidate": previous, "alpha_chunks": counters,
        prefix_note_key: prefix_notes}, "paused")
    campaign.register_assisted(store, store.get(job["id"]), scene_path, geometry)
    imported = store.get(job["id"])
    assert imported["checkpoint"]["alpha_chunks"] == counters
    assert imported["checkpoint"]["candidate"]["steps"][:len(previous["steps"])] == previous["steps"]
    persisted_scene = store.root / "jobs" / job["id"] / "scene.json"
    assert digest(json.loads(persisted_scene.read_text())) == digest(updated)
    archive = store.root / "jobs" / job["id"] / "assisted-parent-scene.json"
    assert digest(json.loads(archive.read_text())) == digest(previous)
    expected_notes = prefix_notes + report["review_items"]
    assert imported["checkpoint"]["uncertainty_notes"] == expected_notes
    claimed = store.claim("explicit-resume", job_id=job["id"])
    run_alpha_claimed(store, claimed, "explicit-resume")
    assert store.get(job["id"])["checkpoint"]["uncertainty_notes"] == expected_notes


@pytest.mark.parametrize("report_key", ["uncertainty_notes", "alpha_notes"])
def test_assisted_report_note_formats_survive_same_scene_refresh_without_budget_reset(assisted_import, report_key):
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    counters = {"0": {"used": 5, "limit": 5, "trials": ["retained-exhausted-trial"]}}
    store.claim("fixture", job_id=job["id"])
    store.checkpoint(job["id"], "fixture", {"alpha_chunks": counters}, "paused")
    campaign.register_assisted(store, store.get(job["id"]), scene_path, geometry)
    original = store.get(job["id"])
    report[report_key] = ["Visible roof seating gap; connector checks have not run."]
    scene_path.with_name("completion-report.json").write_text(json.dumps(report))
    campaign.register_assisted(store, original, scene_path, geometry)
    refreshed = store.get(job["id"])
    assert refreshed["checkpoint"]["candidate"] == original["checkpoint"]["candidate"]
    assert refreshed["checkpoint"]["alpha_chunks"] == counters
    assert refreshed["checkpoint"]["uncertainty_notes"] == [{"reason": report[report_key][0], "scope": ""}]
    assert refreshed["owner"] is None and refreshed["state"] == "paused"
    assert refreshed["config"] == original["config"] and refreshed["fingerprint"] == original["fingerprint"]
    campaign.register_assisted(store, refreshed, scene_path, geometry)
    assert store.get(job["id"]) == refreshed


def test_same_scene_refresh_retains_uncertainty_only_legacy_completion(assisted_import):
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    campaign.register_assisted(store, job, scene_path, geometry)
    imported = store.get(job["id"])
    old_notes = [{"id": "old-camera", "reason": "Original camera agreement remains unverified."},
                 {"id": "old-material", "reason": "Original material ambiguity remains unresolved."}]
    counters = {"0": {"used": 5, "limit": 5, "trials": ["original-exhausted-trial"]}}
    legacy = imported["checkpoint"] | {"uncertainty_notes": old_notes, "alpha_chunks": counters}
    legacy.pop("alpha_review_notes")
    store.claim("legacy-shape", job_id=job["id"])
    store.checkpoint(job["id"], "legacy-shape", legacy, "paused")
    original = store.get(job["id"])
    new_note = {"id": "new-roof", "reason": "Newly recorded roof contact gap."}
    report["review_notes"] = [new_note]
    scene_path.with_name("completion-report.json").write_text(json.dumps(report))
    campaign.register_assisted(store, original, scene_path, geometry)
    refreshed = store.get(job["id"])
    assert refreshed["checkpoint"]["uncertainty_notes"] == old_notes + [new_note]
    assert refreshed["checkpoint"]["alpha_review_notes"] == old_notes + [new_note]
    assert refreshed["checkpoint"]["candidate"] == original["checkpoint"]["candidate"]
    assert refreshed["checkpoint"]["alpha_chunks"] == counters
    assert refreshed["config"] == original["config"] and refreshed["fingerprint"] == original["fingerprint"]
    assert refreshed["owner"] is None and refreshed["state"] == "paused"
    campaign.register_assisted(store, refreshed, scene_path, geometry)
    assert store.get(job["id"]) == refreshed


def test_same_scene_refresh_copies_new_source_receipts_when_notes_are_unchanged(assisted_import):
    import hashlib
    from PIL import Image

    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    counters = {"0": {"used": 5, "limit": 5, "trials": ["retained-exhausted-trial"]}}
    store.claim("fixture", job_id=job["id"])
    store.checkpoint(job["id"], "fixture", {"alpha_chunks": counters}, "paused")
    page_pins = []
    for index in range(8):
        page = scene_path.parent / f"synthetic-page-{index:03d}.png"
        Image.new("RGB", (4, 4), "white").save(page)
        page_pins.append({"page_index": index, "sha256": hashlib.sha256(page.read_bytes()).hexdigest()})
    report["source_evidence"] = page_pins[:7]
    report_path = scene_path.with_name("completion-report.json")
    report_path.write_text(json.dumps(report))
    campaign.register_assisted(store, store.get(job["id"]), scene_path, geometry)
    original = store.get(job["id"])
    campaign.register_assisted(store, original, scene_path, geometry)
    assert store.get(job["id"]) == original
    report["source_evidence"] = page_pins
    report["full_source_review"] = {"scope": "synthetic regression fixture only", "page_count": 8}
    report_path.write_text(json.dumps(report))
    campaign.register_assisted(store, original, scene_path, geometry)
    refreshed = store.get(job["id"])
    registered = json.loads((store.root / "jobs" / job["id"] / "alpha-report.json").read_text())
    assert registered["source_evidence"] == page_pins
    assert registered["full_source_review"] == report["full_source_review"]
    assert refreshed["checkpoint"]["candidate"] == original["checkpoint"]["candidate"]
    assert refreshed["checkpoint"]["alpha_chunks"] == counters
    assert refreshed["checkpoint"]["uncertainty_notes"] == original["checkpoint"]["uncertainty_notes"]
    assert refreshed["checkpoint"]["assisted_note_report_sha256"] == hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert refreshed["config"] == original["config"] and refreshed["fingerprint"] == original["fingerprint"]
    assert refreshed["owner"] is None and refreshed["state"] == "paused"
    campaign.register_assisted(store, refreshed, scene_path, geometry)
    assert store.get(job["id"]) == refreshed


@pytest.fixture
def rejected_cover_batch(assisted_import, monkeypatch):
    import hashlib
    from PIL import Image
    from guide2build.engine import alpha, alpha_runner
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    source_hash = report["source_sha256"]
    monkeypatch.setattr(alpha, "find_guide", lambda *args: guide)
    monkeypatch.setattr(alpha_runner, "find_guide", lambda *args: guide)
    monkeypatch.setattr(alpha_runner, "cached_receipt", lambda *args: {"sha256": source_hash})
    monkeypatch.setattr(alpha, "individual_catalogue_context", lambda *args, **kwargs: [])
    monkeypatch.setattr(alpha, "individual_part_index", lambda *args, **kwargs: [])
    pages = store.data_dir / "public/pages" / source_hash
    pages.mkdir(parents=True)
    for index in range(8):
        Image.new("RGB", (32, 24), "white").save(pages / f"page-{index:03d}.png")
    (pages / "pages.json").write_text(json.dumps([{"index": i} for i in range(8)]))
    original = {"page_observations": [{"page_index": i, "panels": [],
        "description": "Original synthetic blank noninstruction page.", "uncertainties": []} for i in range(4)],
        "new_sections": [], "new_instances": [], "new_steps": [], "quantity_evidence": [], "uncertainties": [],
        "blockers": ["Original synthetic leading cover batch is not a complete model."]}
    trials = []
    for index in range(5):
        trial = store.root / "jobs" / job["id"] / "alpha-proposals" / f"synthetic-{index}"
        trial.mkdir(parents=True)
        (trial / "patch.json").write_text(json.dumps(original))
        (trial / "rejected.json").write_text(json.dumps({"code": "invalid_alpha_patch",
            "message": "Source/identity blocker: Synthetic cover contains no instructions."}))
        trials.append(str(trial))
    checkpoint = {"source_sha256": source_hash,
        "alpha_page_manifest_sha256": hashlib.sha256((pages / "pages.json").read_bytes()).hexdigest(),
        "alpha_policy": alpha._execution_policy({"alpha_page_batch_size": 4, "max_chunk_attempts": 5}, source_hash, 8),
        "alpha_chunks": {"0": {"used": 5, "limit": 5, "trials": trials, "feedback": []}}}
    # The fixture's default batch size is six; this separate explicit job freezes four.
    job = store.enqueue("99999", "synthetic", {"generation_mode": "alpha_fast", "quality_profile": "alpha",
        "alpha_page_batch_size": 4, "max_chunk_attempts": 5, "revision": "cover-correction"})
    original_root = Path(trials[0]).parent
    new_root = store.root / "jobs" / job["id"] / "alpha-proposals"
    new_root.parent.mkdir(parents=True)
    original_root.rename(new_root)
    trials[:] = [str(new_root / Path(value).name) for value in trials]
    store.claim("fixture", job_id=job["id"])
    store.checkpoint(job["id"], "fixture", checkpoint, "blocked", {"code": "alpha_attempt_limit"})
    review = {"actor_type": "agent", "actor_id": "synthetic-source-inspector", "source_sha256": source_hash,
        "reason": "Original synthetic blank pages are valid empty preparation, not assembly evidence.",
        "pages": [{"page_index": i, "sha256": hashlib.sha256((pages / f"page-{i:03d}.png").read_bytes()).hexdigest(),
            "classification": "non_instruction", "description": "Original synthetic blank page."} for i in range(4)]}
    return campaign, store, store.get(job["id"]), review, checkpoint


def test_cover_correction_promotes_without_inference_or_resetting_trials(rejected_cover_batch):
    campaign, store, job, review, original = rejected_cover_batch
    original_bytes = Path(original["alpha_chunks"]["0"]["trials"][-1], "patch.json").read_bytes()
    accepted = campaign.correct_empty_batch(store, job, review)
    latest = store.get(job["id"])
    checkpoint = latest["checkpoint"]
    assert latest["state"] == "paused" and latest["owner"] is None
    assert checkpoint["alpha_completed_pages"] == 4 and not checkpoint.get("alpha_source_complete")
    assert checkpoint.get("candidate") is None and len(checkpoint["alpha_chunks"]) == 1
    assert checkpoint["alpha_chunks"]["0"]["used"] == 5
    assert checkpoint["alpha_chunks"]["0"]["trials"] == original["alpha_chunks"]["0"]["trials"]
    assert Path(original["alpha_chunks"]["0"]["trials"][-1], "patch.json").read_bytes() == original_bytes
    assert accepted["artifact_kind"] == "pdf_assisted_alpha_correction"
    assert checkpoint["artifact_kind"] == "automatic_alpha_with_agent_corrections"


def test_failed_cover_correction_releases_global_lease(rejected_cover_batch, monkeypatch):
    campaign, store, job, review, original = rejected_cover_batch
    def fail(**kwargs):
        raise ValueError("Original synthetic source inspection mismatch")
    monkeypatch.setattr(campaign, "accept_alpha_correction", fail)
    with pytest.raises(ValueError, match="inspection mismatch"):
        campaign.correct_empty_batch(store, job, review)
    latest = store.get(job["id"])
    assert latest["owner"] is None and latest["state"] == "blocked"
    assert latest["checkpoint"]["alpha_chunks"] == original["alpha_chunks"]
    assert latest["error"]["code"] == "alpha_source_correction_failed"


def test_alpha_runtime_is_frozen_without_mutating_proposals_or_budget(assisted_import):
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    previous = json.loads(scene_path.read_text())
    counters = {"0": {"used": 2, "limit": 5, "trials": ["original-synthetic-one", "original-synthetic-two"]}}
    store.claim("fixture", job_id=job["id"])
    store.checkpoint(job["id"], "fixture", {"candidate": previous, "alpha_chunks": counters}, "paused")
    before = store.get(job["id"])
    with pytest.raises(ValueError, match="Frozen ADK runtime"):
        campaign.set_alpha_runtime(store, before, "gemini-3.8-flash", "low", "Synthetic choice")
    assert store.get(job["id"]) == before


@pytest.mark.parametrize("condition", ["active", "strict", "complete", "exhausted"])
def test_alpha_runtime_change_cannot_reset_or_capture_unsafe_job(assisted_import, condition):
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    if condition == "strict":
        job = store.enqueue("99999", "synthetic", {"revision": "strict-runtime-test"})
    else:
        store.claim("fixture", job_id=job["id"])
        checkpoint = {"alpha_source_complete": condition == "complete",
            "alpha_chunks": {"0": {"used": 5 if condition == "exhausted" else 1, "limit": 5, "trials": ["retained"]}}}
        store.checkpoint(job["id"], "fixture", checkpoint, "constructing" if condition == "active" else "paused")
        job = store.get(job["id"])
    with pytest.raises(ValueError, match="Frozen ADK runtime"):
        campaign.set_alpha_runtime(store, job, "gemini-3.8-flash", "low", "Original synthetic invalid runtime change")
    assert store.get(job["id"]) == job


def test_alpha_runtime_change_keeps_unfinished_predecessor_block(assisted_import):
    campaign, store, job, scene_path, geometry, guide, report = assisted_import
    store.claim("fixture", job_id=job["id"])
    error = {"code": "alpha_predecessor_required", "message": "Original synthetic prior booklet is unfinished"}
    store.checkpoint(job["id"], "fixture", {"stage": "alpha_waiting_for_booklet"}, "blocked", error)
    before = store.get(job["id"])
    with pytest.raises(ValueError, match="Frozen ADK runtime"):
        campaign.set_alpha_runtime(store, before, "gemini-3.8-flash", "low", "Synthetic future-runtime choice")
    assert store.get(job["id"]) == before
    latest = store.get(job["id"])
    assert latest["state"] == "blocked" and latest["owner"] is None and latest["error"] == error
    assert latest["checkpoint"]["stage"] == "alpha_waiting_for_booklet"
