"""Synthetic authenticated source-index handoffs; no provider or real job writes."""
import copy
import hashlib
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from guide2build.engine.contracts import strict_schema
from guide2build.engine.corrections import CorrectionRequest, fork_correction
from guide2build.engine.exploration import _exploration_event_queue, run_exploration
from guide2build.engine.panel_index import PageIndexV2, normalize_index
from guide2build.releases.models import SceneV2, canonical, digest
from test_engine_corrections import correction_request, seed_job, write_json


def _save(store, identity, checkpoint):
    store.claim("index-test", job_id=identity)
    store.checkpoint(identity, "index-test", checkpoint, "paused")


def _bytes(directory):
    return {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def _page_pixels(page):
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), (page * 20, 30, 60)).save(stream, format="PNG")
    return stream.getvalue()


def _provider_receipt(directory, page, value, *, error=None, key=None):
    """Original synthetic receipts, not claims of actual model invocations."""
    target = directory / "exploration/calls" / (key or f"index-{page:04d}")
    target.mkdir(parents=True, exist_ok=True)
    prompt = f"Synthetic index-only test page {page}; no assembly context."
    inputs = {"prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "schema_sha256": digest(strict_schema(PageIndexV2)), "model": "test", "reasoning": "high",
        "images": [{"name": f"page-{page:03d}.png", "sha256": value["page_sha256"]}]}
    request = canonical({"prompt": prompt, "inputs": inputs})
    (target / "request.json").write_bytes(request)
    if error is None:
        (target / "result.json").write_bytes(canonical(value))
        receipt = {"status": "completed", "inputs": inputs, "result_sha256": digest(value)}
    else:
        receipt = {"status": "failed", "inputs": inputs, "error": error}
    (target / "receipt.json").write_bytes(canonical(receipt))
    return {"inputs": inputs, "status": receipt["status"], "receipt_sha256": digest(receipt),
            "request_sha256": hashlib.sha256(request).hexdigest(), "call_number": page + 1}


def _v2_seed(tmp_path, scene_data, *, failure=False, config=None):
    store, identity, scene, directory = seed_job(tmp_path, scene_data, config=config)
    checkpoint = store.get(identity)["checkpoint"]
    pages = [{"page_index": page, "sha256": hashlib.sha256(_page_pixels(page)).hexdigest(),
              "width": 32, "height": 32} for page in range(scene.sources[0].page_count)]
    indexes = []
    for page, original in enumerate(checkpoint["page_indexes"]):
        panels = [{**panel, "region_id": f"main-{panel['number']}", "event_key": f"main-{panel['number']}",
                   "role": "build_event", "semantic_status": "explicit",
                   "evidence": "Synthetic visible numbered building event."} for panel in original["panels"]]
        if page == 0:
            # Suppress only this explicitly evidenced source-only view; group the
            # independently retained callout with its explicitly associated main.
            panels.insert(0, {**original["panels"][0], "number": None, "label": "Orientation view",
                "region_id": "overview", "role": "overview", "semantic_status": "explicit",
                "evidence": "Synthetic overview without a new building operation."})
            panels.insert(2, {**original["panels"][0], "kind": "substep", "label": "Small callout",
                "region_id": "callout", "event_key": "callout", "role": "build_event",
                "semantic_status": "explicit", "associated_event": {"page_index": 0, "event_key": "main-1"},
                "evidence": "Synthetic callout explicitly associated with main 1."})
        index = PageIndexV2(source_sha256=scene.source_sha256, page_index=page,
            page_sha256=pages[page]["sha256"], panels=panels, uncertainty=[]).model_dump(mode="json")
        indexes.append(index)
    error = {"code": "invalid_response", "message": "Synthetic failed structured response: " + "x" * 3000}
    if failure:
        indexes[-1]["uncertainty"] = [("Page indexing unavailable: " + error["message"])[:2000]]
    calls = {f"index-{page:04d}": _provider_receipt(directory, page, value,
                error=error if failure and page == len(indexes)-1 else None)
             for page, value in enumerate(indexes)}
    regions = normalize_index(indexes, source_sha256=scene.source_sha256, source_pages=pages,
        set_number=scene.set_number, guide_id=scene.guide_id)
    queue = _exploration_event_queue(regions)
    results = [{"ordinal": ordinal, "page_index": item["page_index"], "panel": item["panel"],
        "step_ids": [scene.steps[ordinal].step_id], "findings": [], "reconstructed": True,
        "outcome": "provisional", "attempt_count": 1} for ordinal, item in enumerate(queue)]
    checkpoint.update(page_indexes=indexes, exploration_source_pages=pages, exploration_calls=calls,
        instruction_results=results, processed_panels=len(results), total_panels=len(queue),
        local_model_calls_used=len(calls), model_calls_used=len(calls), exploration_index_sha256=digest(indexes))
    _save(store, identity, checkpoint)
    return store, identity, scene, directory


def _restart(tmp_path, scene, number):
    request = correction_request(tmp_path, scene, restart_main_step=number,
        guidance=["Synthetic source-supported ambiguity needs another inspection."])
    value = json.loads(request.read_text())
    value["commands"] = []
    write_json(request, value)
    return request


def _retried_v2_seed(tmp_path, scene_data, *, attempts=1):
    """Retain synthetic failed attempts before an authenticated successful retry."""
    from guide2build.engine.exploration import provider_retry_key

    store, identity, scene, directory = _v2_seed(tmp_path, scene_data)
    checkpoint = store.get(identity)["checkpoint"]
    value = checkpoint["page_indexes"][0]
    key = "index-0000"
    (directory / f"exploration/calls/{key}/result.json").unlink()
    for _ in range(attempts):
        state = _provider_receipt(directory, 0, value, key=key,
            error={"code": "provider_unavailable", "message": "Synthetic temporary provider failure."})
        state["provider_retry_key"] = provider_retry_key(key, state)
        checkpoint["exploration_calls"][key] = state
        key = state["provider_retry_key"]
    checkpoint["exploration_calls"][key] = _provider_receipt(directory, 0, value, key=key)
    checkpoint["model_calls_used"] += attempts
    checkpoint["local_model_calls_used"] += attempts
    _save(store, identity, checkpoint)
    return store, identity, scene, directory, key


@pytest.mark.parametrize("restart", [False, True])
@pytest.mark.parametrize("attempts", [1, 2])
def test_completed_provider_retry_is_authenticated_for_immutable_index_seed(tmp_path, scene_data, restart, attempts):
    store, identity, scene, directory, key = _retried_v2_seed(tmp_path, scene_data, attempts=attempts)
    parent, before = store.get(identity), _bytes(directory)
    request = _restart(tmp_path, scene, 2) if restart else correction_request(tmp_path, scene)
    child = fork_correction(store, identity, request, "retried-index-seed")
    cp = child["checkpoint"]
    assert cp["page_indexes"] == parent["checkpoint"]["page_indexes"]
    assert cp["model_calls_used"] == cp["inherited_model_calls_used"] == 8 + attempts
    assert cp["local_model_calls_used"] == 0 and cp["exploration_calls"] == {}
    seed = store.root / "jobs" / child["id"] / "source-index-seed.json"
    assert seed.read_bytes() == canonical(parent["checkpoint"]["page_indexes"])
    assert key != "index-0000" and (directory / f"exploration/calls/{key}/result.json").is_file()
    assert store.get(identity) == parent and _bytes(directory) == before


@pytest.mark.parametrize("mutation", ["alias", "inputs", "receipt"])
def test_provider_retry_correction_rejects_changed_link_inputs_or_receipt(tmp_path, scene_data, mutation):
    store, identity, scene, directory, key = _retried_v2_seed(tmp_path, scene_data)
    checkpoint = store.get(identity)["checkpoint"]
    if mutation == "alias":
        checkpoint["exploration_calls"]["index-0000"]["provider_retry_key"] = "index-0001"
    elif mutation == "inputs":
        state = checkpoint["exploration_calls"][key]
        state["inputs"]["model"] = "changed-model"
        target = directory / f"exploration/calls/{key}"
        request = json.loads((target / "request.json").read_bytes())
        receipt = json.loads((target / "receipt.json").read_bytes())
        request["inputs"] = receipt["inputs"] = state["inputs"]
        (target / "request.json").write_bytes(canonical(request))
        (target / "receipt.json").write_bytes(canonical(receipt))
        state["request_sha256"] = digest(request)
        state["receipt_sha256"] = digest(receipt)
    else:
        target = directory / f"exploration/calls/{key}/receipt.json"
        receipt = json.loads(target.read_bytes())
        receipt["result_sha256"] = "f" * 64
        target.write_bytes(canonical(receipt))
    _save(store, identity, checkpoint)
    parent, before = store.get(identity), _bytes(directory)
    with pytest.raises(ValueError):
        fork_correction(store, identity, correction_request(tmp_path, scene), "changed-retry")
    assert len(store.list()) == 1 and store.get(identity) == parent and _bytes(directory) == before


def test_legacy_index_is_canonical_immutable_seed_without_source_pngs(tmp_path, scene_data):
    store, identity, scene, directory = seed_job(tmp_path, scene_data)
    parent, before = store.get(identity), _bytes(directory)
    child = fork_correction(store, identity, correction_request(tmp_path, scene), "legacy-seed")
    seed = store.root / "jobs" / child["id"] / "source-index-seed.json"
    assert seed.read_bytes() == canonical(parent["checkpoint"]["page_indexes"])
    assert child["checkpoint"]["page_indexes"] == parent["checkpoint"]["page_indexes"]
    assert all("schema_version" not in value for value in json.loads(seed.read_bytes()))
    assert child["checkpoint"]["exploration_seed"]["source_index_sha256"] == hashlib.sha256(seed.read_bytes()).hexdigest()
    assert child["checkpoint"]["model_calls_used"] == child["checkpoint"]["inherited_model_calls_used"] == 5
    assert child["checkpoint"]["local_model_calls_used"] == 0
    assert not (tmp_path / "public/pages").exists()
    assert store.get(identity) == parent and _bytes(directory) == before


@pytest.mark.parametrize("restart", [False, True])
def test_v2_preserves_raw_regions_and_normalized_cursor_without_source_pngs(tmp_path, scene_data, restart):
    store, identity, scene, directory = _v2_seed(tmp_path, scene_data)
    parent, before = store.get(identity), _bytes(directory)
    request = _restart(tmp_path, scene, 2) if restart else correction_request(tmp_path, scene)
    child = fork_correction(store, identity, request, "v2-seed")
    checkpoint = child["checkpoint"]
    assert checkpoint["page_indexes"] == parent["checkpoint"]["page_indexes"]
    assert len(checkpoint["page_indexes"][0]["panels"]) == 5
    assert checkpoint["total_panels"] == 3
    assert checkpoint["processed_panels"] == (1 if restart else 3)
    assert [item["panel"]["number"] for item in checkpoint["instruction_results"]] == ([1] if restart else [1, 2, 3])
    assert "exploration_index_sha256" not in checkpoint
    assert checkpoint["exploration_policy"]["source_index_seed_sha256"] == digest(checkpoint["page_indexes"])
    assert checkpoint["exploration_seed"]["source_index_sha256"] == digest(checkpoint["page_indexes"])
    assert checkpoint["model_calls_used"] == checkpoint["inherited_model_calls_used"] == 8
    assert checkpoint["local_model_calls_used"] == 0 and checkpoint["exploration_calls"] == {}
    assert not (tmp_path / "public/pages").exists()
    assert store.get(identity) == parent and _bytes(directory) == before


@pytest.mark.parametrize("mutation", ["bbox", "role", "uncertainty", "pixel", "source", "page"])
def test_corrupt_v2_checkpoint_cannot_be_enrolled_with_unchanged_receipts(tmp_path, scene_data, mutation):
    store, identity, scene, directory = _v2_seed(tmp_path, scene_data)
    checkpoint = store.get(identity)["checkpoint"]
    first = checkpoint["page_indexes"][0]
    if mutation == "bbox":
        first["panels"][1]["bbox"][0] = .1
    elif mutation == "role":
        first["panels"][0]["role"] = "ambiguous"
    elif mutation == "uncertainty":
        first["uncertainty"] = ["Invented observation absent from authenticated result."]
    elif mutation == "pixel":
        first["page_sha256"] = "f" * 64
    elif mutation == "source":
        first["source_sha256"] = "f" * 64
    else:
        first["page_index"] = 1
    checkpoint["exploration_index_sha256"] = digest(checkpoint["page_indexes"])
    _save(store, identity, checkpoint)
    parent, before = store.get(identity), _bytes(directory)
    with pytest.raises(ValueError, match="authenticated|source/page"):
        fork_correction(store, identity, correction_request(tmp_path, scene), "corrupt-v2")
    assert len(store.list()) == 1 and store.get(identity) == parent and _bytes(directory) == before


@pytest.mark.parametrize("name", ["request.json", "receipt.json", "result.json"])
def test_parent_index_receipt_file_tampering_is_hard_before_fork(tmp_path, scene_data, name):
    store, identity, scene, directory = _v2_seed(tmp_path, scene_data)
    target = directory / "exploration/calls/index-0000" / name
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        fork_correction(store, identity, correction_request(tmp_path, scene), "tampered-file")
    assert len(store.list()) == 1


@pytest.mark.parametrize("missing", ["exploration_source_pages", "processed_panels", "instruction_results"])
def test_v2_requires_compatible_parent_bindings_and_cursor(tmp_path, scene_data, missing):
    store, identity, scene, _ = _v2_seed(tmp_path, scene_data)
    checkpoint = store.get(identity)["checkpoint"]
    checkpoint.pop(missing)
    _save(store, identity, checkpoint)
    with pytest.raises(ValueError, match="new source-index revision"):
        fork_correction(store, identity, correction_request(tmp_path, scene), "unbound-v2")


def test_v2_reordered_parent_result_cannot_silently_rebase_prefix(tmp_path, scene_data):
    store, identity, scene, _ = _v2_seed(tmp_path, scene_data)
    checkpoint = store.get(identity)["checkpoint"]
    checkpoint["instruction_results"][0]["panel"] = checkpoint["instruction_results"][1]["panel"]
    _save(store, identity, checkpoint)
    with pytest.raises(ValueError, match="cursor evidence"):
        fork_correction(store, identity, _restart(tmp_path, scene, 2), "shifted-cursor")


def test_v2_parent_cannot_bypass_authentication_by_downgrading_to_legacy(tmp_path, scene_data):
    store, identity, scene, _ = _v2_seed(tmp_path, scene_data)
    checkpoint = store.get(identity)["checkpoint"]
    checkpoint["page_indexes"] = [{"panels": [panel.legacy_panel().model_dump(mode="json")
        for panel in PageIndexV2.model_validate(item).panels if panel.event_key in {"main-1", "main-2", "main-3"}],
        "uncertainty": item["uncertainty"]} for item in checkpoint["page_indexes"]]
    _save(store, identity, checkpoint)
    with pytest.raises(ValueError, match="discarded its authenticated V2"):
        fork_correction(store, identity, correction_request(tmp_path, scene), "downgraded-index")
    assert len(store.list()) == 1


def test_failed_index_fallback_keeps_authenticated_bounded_uncertainty(tmp_path, scene_data):
    store, identity, scene, _ = _v2_seed(tmp_path, scene_data, failure=True)
    child = fork_correction(store, identity, correction_request(tmp_path, scene), "failed-index")
    note = child["checkpoint"]["page_indexes"][-1]["uncertainty"][0]
    assert len(note) == 2000 and note.startswith("Page indexing unavailable: Synthetic failed")
    checkpoint = store.get(identity)["checkpoint"]
    checkpoint["page_indexes"][-1]["uncertainty"][0] = "Discarded real failure"
    _save(store, identity, checkpoint)
    with pytest.raises(ValueError, match="authenticated provider result"):
        fork_correction(store, identity, correction_request(tmp_path, scene, correction_id="different"), "changed-fallback")


def _unavailable_source_page(tmp_path, scene_data, *, code="provider_unavailable"):
    store, identity, scene, directory = _v2_seed(tmp_path, scene_data,
        config={"model": "test", "thinking_level": "high", "revision": "base", "max_model_calls": 300})
    checkpoint = store.get(identity)["checkpoint"]
    page = len(checkpoint["page_indexes"]) - 1  # Original synthetic nonconstruction page.
    index = checkpoint["page_indexes"][page]
    error = {"code": code, "message": "Synthetic process failed before structured output."}
    index["uncertainty"] = ["Page indexing unavailable: " + error["message"]]
    target = directory / f"exploration/calls/index-{page:04d}"
    (target / "result.json").unlink()  # This fixture is an original failed call, not a recovery edit.
    state = _provider_receipt(directory, page, index, error=error)
    checkpoint["exploration_calls"][f"index-{page:04d}"] = state
    checkpoint["exploration_index_sha256"] = digest(checkpoint["page_indexes"])
    process = {"model": "test", "reasoning": "high", "returncode": 1,
               "structured_result_present": False, "completion_or_accuracy_claim": False}
    process_path = target / "provider/process-result.json"
    process_path.parent.mkdir()
    process_path.write_bytes(canonical(process))
    pixels = tmp_path / f"public/pages/{scene.source_sha256}/page-{page:03d}.png"
    pixels.parent.mkdir(parents=True)
    pixels.write_bytes(_page_pixels(page))
    _save(store, identity, checkpoint)
    review = {"actor": "agent", "conclusion": "no_construction", "source_sha256": scene.source_sha256,
        "page_index": page, "page_sha256": index["page_sha256"], "index_sha256": digest(index),
        "failed_request_sha256": state["request_sha256"], "failed_receipt_sha256": state["receipt_sha256"],
        "process_result_sha256": digest(process), "reason": "Synthetic whole-page agent inspection found no construction."}
    return store, identity, scene, directory, review


def _review_request(tmp_path, scene, review, *, correction_id="review-repair"):
    request = _restart(tmp_path, scene, 2)
    value = json.loads(request.read_text())
    value.update(correction_id=correction_id, source_only_index_reviews=[review])
    value["evidence"].append({"source_sha256": review["source_sha256"],
                              "page_index": review["page_index"], "bbox": [0, 0, 1, 1]})
    write_json(request, value)
    return request


def test_explicit_source_only_review_preserves_empty_index_queue_budget_and_parent(tmp_path, scene_data):
    store, identity, scene, directory, review = _unavailable_source_page(tmp_path, scene_data)
    parent, before = store.get(identity), _bytes(directory)
    request = _review_request(tmp_path, scene, review)
    child = fork_correction(store, identity, request, "reviewed-index")
    cp = child["checkpoint"]
    child_dir = store.root / "jobs" / child["id"]
    assert cp["page_indexes"] == parent["checkpoint"]["page_indexes"]
    assert (child_dir / "source-index-seed.json").read_bytes() == canonical(cp["page_indexes"])
    assert cp["total_panels"] == parent["checkpoint"]["total_panels"] == 3
    assert cp["processed_panels"] == 1
    assert cp["instruction_results"][0]["panel"] == parent["checkpoint"]["instruction_results"][0]["panel"]
    note = cp["page_indexes"][review["page_index"]]["uncertainty"][0]
    assert any(item["message"] == note for item in cp["source_index_findings"])
    receipt = {"version": "source-only-index-reviews-v1", "reviews": [review]}
    assert (child_dir / "source-index-reviews.json").read_bytes() == canonical(receipt)
    assert cp["exploration_seed"]["source_index_reviews_sha256"] == digest(receipt)
    assert cp["correction_lineage"][-1]["source_index_reviews_sha256"] == digest(receipt)
    assert cp["correction_lineage"][-1]["unassisted"] is False
    assert cp["model_calls_used"] == cp["inherited_model_calls_used"] == parent["checkpoint"]["model_calls_used"] == 8
    assert cp["local_model_calls_used"] == 0 and cp["exploration_calls"] == {}
    assert child["config"]["max_model_calls"] == parent["config"]["max_model_calls"] == 300
    assert (child["config"]["model"], child["config"]["thinking_level"]) == ("test", "high")
    assert store.lineage_model_calls_used(cp["budget_root_job_id"]) == 8
    assert store.get(identity) == parent and _bytes(directory) == before


def test_unavailable_index_without_explicit_review_still_rejects(tmp_path, scene_data):
    store, identity, scene, directory, _ = _unavailable_source_page(tmp_path, scene_data)
    parent, before = store.get(identity), _bytes(directory)
    with pytest.raises(ValueError, match="fatal index failure"):
        fork_correction(store, identity, _restart(tmp_path, scene, 2), "unreviewed-failure")
    assert len(store.list()) == 1 and store.get(identity) == parent and _bytes(directory) == before


def test_reviewed_source_seed_resumes_same_cursor_without_index_calls(tmp_path, scene_data, monkeypatch):
    store, identity, scene, directory, review = _unavailable_source_page(tmp_path, scene_data)
    parent, before = store.get(identity), _bytes(directory)
    child = fork_correction(store, identity, _review_request(tmp_path, scene, review), "review-resume")
    pages = tmp_path / "public/pages" / scene.source_sha256
    for page in range(scene.sources[0].page_count):
        (pages / f"page-{page:03d}.png").write_bytes(_page_pixels(page))
    monkeypatch.setattr("guide2build.engine.perception.source_relevant_catalogue", lambda *a, **kw: [])
    monkeypatch.setattr("guide2build.engine.alpha.individual_part_index", lambda *a, **kw: [])
    monkeypatch.setattr("guide2build.engine.connectors.connector_context", lambda *a, **kw: {})

    class ReachedInstruction(Exception):
        pass

    def capture(**kwargs):
        assert kwargs["ordinal"] == 1 and kwargs["panel"]["number"] == 2
        assert len(kwargs["previous"]["steps"]) == 1
        assert kwargs["calls"].policy["runtime_choice"] == {"provider": "google_adk", "model": "test", "thinking_level": "high", "provider_timeout": 120}
        assert kwargs["calls"].policy["max_model_calls"] == 300
        raise ReachedInstruction

    monkeypatch.setattr("guide2build.engine.exploration._instruction", capture)
    cp = child["checkpoint"]
    with pytest.raises(ReachedInstruction):
        run_exploration(job=child, checkpoint=cp, directory=store.root / "jobs" / child["id"],
            source_hash=scene.source_sha256, pages_dir=pages, page_count=scene.sources[0].page_count,
            runtime=SimpleNamespace(call=lambda *a, **kw: pytest.fail("No provider call is allowed")),
            save=lambda *a, **kw: None, heartbeat=SimpleNamespace(check=lambda: None))
    assert cp["model_calls_used"] == cp["inherited_model_calls_used"] == 8
    assert cp["local_model_calls_used"] == 0 and cp["exploration_calls"] == {}
    assert cp["page_indexes"] == parent["checkpoint"]["page_indexes"]
    assert store.get(identity) == parent and _bytes(directory) == before


@pytest.mark.parametrize("mutation", ["pixels", "process"])
def test_source_only_review_rechecks_evidence_inside_materialization_fence(tmp_path, scene_data, monkeypatch, mutation):
    store, identity, scene, directory, review = _unavailable_source_page(tmp_path, scene_data)
    parent = store.get(identity)
    request = _review_request(tmp_path, scene, review)
    original = store.fork_revision
    changed_bytes = None

    def mutate_then_fork(*args, **kwargs):
        nonlocal changed_bytes
        path = (tmp_path / f"public/pages/{scene.source_sha256}/page-{review['page_index']:03d}.png" if mutation == "pixels"
                else directory / f"exploration/calls/index-{review['page_index']:04d}/provider/process-result.json")
        path.write_bytes(path.read_bytes() + b" ")
        changed_bytes = _bytes(directory)
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "fork_revision", mutate_then_fork)
    with pytest.raises(ValueError, match="Reviewed source page|Source-only review"):
        fork_correction(store, identity, request, "changed-during-fork")
    assert len(store.list()) == 1 and store.get(identity) == parent
    assert _bytes(directory) == changed_bytes  # The synthetic tamper is retained, never overwritten.


@pytest.mark.parametrize("field", ["index_sha256", "page_sha256", "failed_request_sha256",
                                    "failed_receipt_sha256", "process_result_sha256"])
def test_source_only_review_rejects_forged_hashes(tmp_path, scene_data, field):
    store, identity, scene, directory, review = _unavailable_source_page(tmp_path, scene_data)
    parent, before = store.get(identity), _bytes(directory)
    review[field] = "f" * 64
    with pytest.raises(ValueError, match="Source-only review|Source-only index review"):
        fork_correction(store, identity, _review_request(tmp_path, scene, review), "forged-review")
    assert len(store.list()) == 1 and store.get(identity) == parent and _bytes(directory) == before


@pytest.mark.parametrize("code", ["authentication_required", "subscription_limit", "invalid_schema",
                                   "unsupported_model", "integrity_failure"])
def test_source_only_review_cannot_admit_other_fatal_failures(tmp_path, scene_data, code):
    store, identity, scene, directory, review = _unavailable_source_page(tmp_path, scene_data, code=code)
    parent, before = store.get(identity), _bytes(directory)
    with pytest.raises(ValueError, match="fatal index failure"):
        fork_correction(store, identity, _review_request(tmp_path, scene, review), "fatal-review")
    assert len(store.list()) == 1 and store.get(identity) == parent and _bytes(directory) == before


@pytest.mark.parametrize("mutation", ["nonempty", "uncertainty", "schema", "completed", "no_receipt"])
def test_source_only_review_requires_exact_authenticated_empty_failure(tmp_path, scene_data, mutation):
    store, identity, scene, directory, review = _unavailable_source_page(tmp_path, scene_data)
    checkpoint = store.get(identity)["checkpoint"]
    page = review["page_index"]
    value = checkpoint["page_indexes"][page]
    state = checkpoint["exploration_calls"][f"index-{page:04d}"]
    if mutation == "nonempty":
        value["panels"] = [copy.deepcopy(checkpoint["page_indexes"][0]["panels"][1])]
    elif mutation == "uncertainty":
        value["uncertainty"] = ["Review removed the original failure warning."]
    elif mutation == "schema":
        state["inputs"]["schema_sha256"] = "f" * 64
    elif mutation == "completed":
        state = _provider_receipt(directory, page, value)
        checkpoint["exploration_calls"][f"index-{page:04d}"] = state
        review["failed_request_sha256"], review["failed_receipt_sha256"] = state["request_sha256"], state["receipt_sha256"]
    else:
        state.pop("receipt_sha256")
    review["index_sha256"] = digest(value)  # Re-signing a changed index cannot waive the original receipt.
    checkpoint["exploration_index_sha256"] = digest(checkpoint["page_indexes"])
    _save(store, identity, checkpoint)
    parent, before = store.get(identity), _bytes(directory)
    with pytest.raises(ValueError):
        fork_correction(store, identity, _review_request(tmp_path, scene, review), "not-empty-failure")
    assert len(store.list()) == 1 and store.get(identity) == parent and _bytes(directory) == before


@pytest.mark.parametrize("mutation", ["structured", "successful_exit", "wrong_runtime", "missing_process",
                                      "process_symlink", "result", "response", "pixels", "pixel_symlink"])
def test_source_only_review_requires_no_output_and_exact_source_pixels(tmp_path, scene_data, mutation):
    store, identity, scene, directory, review = _unavailable_source_page(tmp_path, scene_data)
    target = directory / f"exploration/calls/index-{review['page_index']:04d}"
    process_path = target / "provider/process-result.json"
    pixels = tmp_path / f"public/pages/{scene.source_sha256}/page-{review['page_index']:03d}.png"
    if mutation in {"structured", "successful_exit", "wrong_runtime"}:
        process = json.loads(process_path.read_bytes())
        process.update({"structured_result_present": True} if mutation == "structured" else
                       {"returncode": 0} if mutation == "successful_exit" else {"model": "different"})
        process_path.write_bytes(canonical(process))
        review["process_result_sha256"] = digest(process)
    elif mutation == "missing_process":
        process_path.unlink()
    elif mutation in {"process_symlink", "pixel_symlink"}:
        path = process_path if mutation == "process_symlink" else pixels
        other = tmp_path / ("copy-" + path.name)
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(other)
    elif mutation in {"result", "response"}:
        (target / ("result.json" if mutation == "result" else "provider/response.json")).write_text("{}")
    else:
        pixels.write_bytes(_page_pixels(0))
    parent, before = store.get(identity), _bytes(directory)
    with pytest.raises(ValueError):
        fork_correction(store, identity, _review_request(tmp_path, scene, review), "output-or-pixel-drift")
    assert len(store.list()) == 1 and store.get(identity) == parent and _bytes(directory) == before


def test_reviewed_index_seed_remains_authenticated_in_later_correction(tmp_path, scene_data):
    store, identity, scene, directory, review = _unavailable_source_page(tmp_path, scene_data)
    parent, before = store.get(identity), _bytes(directory)
    child = fork_correction(store, identity, _review_request(tmp_path, scene, review), "review-r1")
    child_dir = store.root / "jobs" / child["id"]
    child_before = store.get(child["id"]), _bytes(child_dir)
    corrected = SceneV2.model_validate(child["checkpoint"]["candidate"])
    command = {"op": "mapping", "instance_id": corrected.instances[0].instance_id,
        "part_id": corrected.instances[0].part_id, "color_code": "4", "reason": "Synthetic colour correction.",
        "evidence": corrected.steps[0].source.model_dump(mode="json")}
    grandchild = fork_correction(store, child["id"],
        correction_request(tmp_path, corrected, commands=[command], correction_id="review-r2"), "review-r2")
    grandchild_dir = store.root / "jobs" / grandchild["id"]
    for name in ("source-index-seed.json", "source-index-reviews.json"):
        assert (grandchild_dir / name).read_bytes() == (child_dir / name).read_bytes()
    assert grandchild["checkpoint"]["exploration_seed"]["source_index_reviews_sha256"] == child["checkpoint"]["exploration_seed"]["source_index_reviews_sha256"]
    assert grandchild["checkpoint"]["model_calls_used"] == 8 and grandchild["checkpoint"]["local_model_calls_used"] == 0
    assert grandchild["config"]["max_model_calls"] == 300
    assert store.get(identity) == parent and _bytes(directory) == before
    assert (store.get(child["id"]), _bytes(child_dir)) == child_before


@pytest.mark.parametrize("mutation", ["file", "pin", "missing", "noncanonical", "symlink"])
def test_reviewed_index_seed_tampering_cannot_be_resigned(tmp_path, scene_data, mutation):
    store, identity, scene, _, review = _unavailable_source_page(tmp_path, scene_data)
    child = fork_correction(store, identity, _review_request(tmp_path, scene, review), "review-r1")
    path = store.root / "jobs" / child["id"] / "source-index-reviews.json"
    checkpoint = child["checkpoint"]
    if mutation == "file":
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "pin":
        checkpoint["exploration_seed"].pop("source_index_reviews_sha256")
    elif mutation == "missing":
        path.unlink()
    elif mutation == "noncanonical":
        path.write_text(json.dumps(json.loads(path.read_bytes()), indent=2))
        rebound = hashlib.sha256(path.read_bytes()).hexdigest()
        checkpoint["exploration_seed"]["source_index_reviews_sha256"] = rebound
        checkpoint["correction_lineage"][-1]["source_index_reviews_sha256"] = rebound
    else:
        target = tmp_path / "review-copy.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    _save(store, child["id"], checkpoint)
    corrected = SceneV2.model_validate(checkpoint["candidate"])
    with pytest.raises(ValueError, match="reviews|unsafe|missing"):
        fork_correction(store, child["id"],
            correction_request(tmp_path, corrected, correction_id="review-r2"), "bad-review-r2")
    assert len(store.list()) == 2


@pytest.mark.parametrize("mutation", ["duplicate", "partial_page", "uncited", "wrong_source", "actor", "conclusion"])
def test_source_only_review_requires_explicit_unique_agent_whole_page_acknowledgement(tmp_path, scene_data, mutation):
    _, _, scene, _, review = _unavailable_source_page(tmp_path, scene_data)
    request = json.loads(_review_request(tmp_path, scene, review).read_bytes())
    if mutation == "duplicate":
        request["source_only_index_reviews"].append(review)
    elif mutation == "partial_page":
        request["evidence"][-1]["bbox"] = [0, 0, .5, 1]
    elif mutation == "uncited":
        request["evidence"].pop()
    elif mutation == "wrong_source":
        request["source_only_index_reviews"][0]["source_sha256"] = "f" * 64
    elif mutation == "actor":
        request["source_only_index_reviews"][0]["actor"] = "human"
    else:
        request["source_only_index_reviews"][0]["conclusion"] = "suppress_uncertain_construction"
    with pytest.raises(ValueError):
        CorrectionRequest.model_validate(request)


def test_corrected_parent_authenticates_seed_without_local_index_calls(tmp_path, scene_data):
    store, identity, scene, _ = _v2_seed(tmp_path, scene_data)
    child = fork_correction(store, identity, correction_request(tmp_path, scene), "seed-r1")
    corrected = SceneV2.model_validate(child["checkpoint"]["candidate"])
    child_dir = store.root / "jobs" / child["id"]
    before_job, before = store.get(child["id"]), _bytes(child_dir)
    grandchild = fork_correction(store, child["id"],
        correction_request(tmp_path, corrected, correction_id="repair-2"), "seed-r2")
    assert grandchild["checkpoint"]["page_indexes"] == child["checkpoint"]["page_indexes"]
    assert grandchild["checkpoint"]["model_calls_used"] == 8 and grandchild["checkpoint"]["local_model_calls_used"] == 0
    assert grandchild["checkpoint"]["exploration_calls"] == {}
    assert not (child_dir / "exploration/calls").exists()
    assert store.get(child["id"]) == before_job and _bytes(child_dir) == before


@pytest.mark.parametrize("tamper", ["file", "checkpoint", "noncanonical", "symlink"])
def test_corrected_parent_seed_tampering_cannot_be_resigned(tmp_path, scene_data, tamper):
    store, identity, scene, _ = _v2_seed(tmp_path, scene_data)
    child = fork_correction(store, identity, correction_request(tmp_path, scene), "seed-r1")
    corrected = SceneV2.model_validate(child["checkpoint"]["candidate"])
    path = store.root / "jobs" / child["id"] / "source-index-seed.json"
    checkpoint = child["checkpoint"]
    if tamper == "file":
        path.write_bytes(path.read_bytes() + b" ")
    elif tamper == "checkpoint":
        checkpoint["page_indexes"][0]["uncertainty"] = ["Not present in seed."]
    elif tamper == "noncanonical":
        path.write_text(json.dumps(checkpoint["page_indexes"], indent=2))
        checkpoint["exploration_seed"]["source_index_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        target = tmp_path / "copied-seed.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    _save(store, child["id"], checkpoint)
    with pytest.raises(ValueError, match="seed|unsafe"):
        fork_correction(store, child["id"],
            correction_request(tmp_path, corrected, correction_id="repair-2"), "seed-r2")
    assert len(store.list()) == 2


def test_legacy_scene_fallback_stays_unclassified(tmp_path, scene_data):
    store, identity, scene, _ = seed_job(tmp_path, scene_data)
    checkpoint = store.get(identity)["checkpoint"]
    checkpoint.pop("page_indexes")
    _save(store, identity, checkpoint)
    child = fork_correction(store, identity, correction_request(tmp_path, scene), "scene-source-fallback")
    indexes = child["checkpoint"]["page_indexes"]
    assert len(indexes) == scene.sources[0].page_count
    assert "not independently re-indexed" in indexes[0]["uncertainty"][0]
    assert all("schema_version" not in item for item in indexes)
    assert all("role" not in panel for item in indexes for panel in item["panels"])


@pytest.mark.parametrize("restart", [None, 2])
def test_legacy_callouts_reject_a_retained_prefix(tmp_path, scene_data, restart):
    store, identity, scene, _ = seed_job(tmp_path, scene_data)
    checkpoint = store.get(identity)["checkpoint"]
    callout = copy.deepcopy(checkpoint["page_indexes"][0]["panels"][0])
    callout.update(kind="substep", label="Unclassified small callout")
    checkpoint["page_indexes"][0]["panels"].insert(0, callout)
    _save(store, identity, checkpoint)
    request = _restart(tmp_path, scene, restart) if restart else correction_request(tmp_path, scene)
    with pytest.raises(ValueError, match="restart from the first instruction"):
        fork_correction(store, identity, request, "legacy-callouts")


def test_legacy_callout_zero_prefix_reaches_conservative_host_queue_without_inference(tmp_path, scene_data, monkeypatch):
    store, identity, scene, _ = seed_job(tmp_path, scene_data)
    checkpoint = store.get(identity)["checkpoint"]
    callout = copy.deepcopy(checkpoint["page_indexes"][0]["panels"][0])
    callout.update(kind="substep", label="Unclassified small callout")
    checkpoint["page_indexes"][0]["panels"].insert(0, callout)
    _save(store, identity, checkpoint)
    child = fork_correction(store, identity, _restart(tmp_path, scene, 1), "legacy-first")
    checkpoint = child["checkpoint"]
    assert checkpoint["processed_panels"] == 0 and checkpoint["instruction_results"] == []
    assert checkpoint["total_panels"] == 4 and "candidate" not in checkpoint
    pages = tmp_path / "public/pages" / scene.source_sha256
    pages.mkdir(parents=True)
    for page in range(scene.sources[0].page_count):
        (pages / f"page-{page:03d}.png").write_bytes(_page_pixels(page))
    monkeypatch.setattr("guide2build.engine.perception.source_relevant_catalogue", lambda *a, **kw: [])
    monkeypatch.setattr("guide2build.engine.alpha.individual_part_index", lambda *a, **kw: [])
    monkeypatch.setattr("guide2build.engine.connectors.connector_context", lambda *a, **kw: {})

    class ReachedInstruction(Exception):
        pass

    def capture(**kwargs):
        assert kwargs["panel"]["kind"] == "substep" and kwargs["ordinal"] == 0
        assert kwargs["previous"] is None
        raise ReachedInstruction

    monkeypatch.setattr("guide2build.engine.exploration._instruction", capture)
    with pytest.raises(ReachedInstruction):
        run_exploration(job=child, checkpoint=checkpoint, directory=store.root / "jobs" / child["id"],
            source_hash=scene.source_sha256, pages_dir=pages, page_count=scene.sources[0].page_count,
            runtime=SimpleNamespace(call=lambda *a, **kw: pytest.fail("No inference allowed")),
            save=lambda *a, **kw: None, heartbeat=SimpleNamespace(check=lambda: None))
    assert checkpoint["model_calls_used"] == 5 and checkpoint["local_model_calls_used"] == 0
    assert checkpoint["exploration_calls"] == {}
