"""Synthetic restart controls: cited source views, lower attempt caps, no inference."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from guide2build.catalog import find_guide
from guide2build.core.models import SceneManifest
from guide2build.engine import corrections
from guide2build.engine.corrections import CorrectionRequest, fork_correction
from guide2build.engine.exploration import _policy, run_exploration
from guide2build.releases.models import adapt_v1, digest
from test_engine_corrections import correction_request, seed_job, write_json


def _seed(tmp_path, scene_data, cap=2):
    def pages(value):
        for step, page in zip(value["steps"], [0, 2, 4], strict=True):
            step["source"]["page_index"] = page
        return value

    store, identity, scene, directory = seed_job(tmp_path, scene_data,
        config={"model": "test", "revision": "base", "execution_policy": "explore",
                "max_model_calls": 7, "max_panel_attempts": cap}, transform=pages)
    store.claim("synthetic-pages", job_id=identity)
    parent = store.get(identity)
    checkpoint = parent["checkpoint"]
    indexes = [{"panels": [], "uncertainty": []} for _ in range(scene.sources[0].page_count)]
    for step in scene.steps:
        indexes[step.source.page_index]["panels"].append({"section": step.section_id,
            "number": step.main_step_number, "label": str(step.main_step_number),
            "bbox": step.source.bbox, "kind": "main"})
    checkpoint["page_indexes"] = indexes
    # This fixture's existing five charged calls belong to the parent. They are
    # synthetic history, not invocations made by this test or by the correction.
    checkpoint["local_model_calls_used"] = checkpoint["model_calls_used"]
    _policy(parent["config"], checkpoint, scene.source_sha256, scene.sources[0].page_count)
    store.checkpoint(identity, "synthetic-pages", checkpoint, "paused")
    return store, identity, scene, directory


def _request(tmp_path, scene, *, evidence_pages=(0,), **controls):
    evidence = [scene.steps[0].source.model_dump(mode="json") | {"page_index": page} for page in evidence_pages]
    path = correction_request(tmp_path, scene, restart_main_step=2,
        guidance=["Compare the specifically cited later source views before estimating the attachment."],
        evidence=evidence, **controls)
    value = json.loads(path.read_text())
    value["commands"] = []  # Shared helper intentionally defaults empty commands to a mapping.
    write_json(path, value)
    return path


def _parent_state(store, identity, directory):
    return store.get(identity), {str(p.relative_to(directory)): p.read_bytes()
                                for p in directory.rglob("*") if p.is_file()}


def _validation_request(scene_data, *, evidence_pages=(0,), restart=True, **controls):
    """Keep the original request values without constructing a job to reject them."""
    source_hash = hashlib.sha256(b"%PDF-1.4\nOriginal synthetic test source; not LEGO evidence.\n").hexdigest()
    value = copy.deepcopy(scene_data)
    value.update(set_number="30669", guide_id="alt-02", revision="base", source_sha256=source_hash)
    for item in value["instances"] + value["steps"]:
        item["source"]["source_sha256"] = source_hash
    for part in value["instances"]:
        part.update(part_id="synthetic", origin="vision_proposal")
    guide = find_guide("30669", "alt-02")
    scene = adapt_v1(SceneManifest.model_validate(value), guide["pdf_url"], guide["expected_page_count"])
    for step, page in zip(scene.steps, [0, 2, 4], strict=True):
        step.source.page_index = page
    evidence = scene.steps[0].source.model_dump(mode="json")
    request = {"schema_version": "1.0", "correction_id": "repair-1", "expected_scene_sha256": digest(scene),
        "actor": "agent", "reason": "Synthetic source-bound test correction",
        "evidence": [evidence | {"page_index": page} for page in evidence_pages], "commands": []}
    if restart:
        request.update(restart_main_step=2,
            guidance=["Compare the specifically cited later source views before estimating the attachment."])
    else:
        request["commands"] = [{"op": "mapping", "instance_id": "a", "part_id": "synthetic2", "color_code": "4",
            "reason": "Synthetic mapping correction", "evidence": evidence}]
    return request | controls


def _reject_before_job_or_source(tmp_path, monkeypatch, request, *, message=None):
    with pytest.raises(ValueError, match=message):
        CorrectionRequest.model_validate(request)

    class UnreadableStore:
        def get(self, *_args):
            pytest.fail("Malformed request accessed a job before being rejected")

    def source_access(*_args, **_kwargs):
        pytest.fail("Malformed request accessed source evidence before being rejected")

    monkeypatch.setattr(corrections, "verify_scene_source", source_access)
    path = tmp_path / "invalid-request.json"
    write_json(path, request)
    with pytest.raises(ValueError, match=message):
        fork_correction(UnreadableStore(), "unreadable-job", path, "invalid-request")
    assert sorted(item.name for item in tmp_path.iterdir()) == [path.name]


def test_requested_source_pages_precede_deduplicated_suffix_and_are_recorded(tmp_path, scene_data):
    store, identity, scene, directory = _seed(tmp_path, scene_data)
    before = _parent_state(store, identity, directory)
    request = _request(tmp_path, scene, evidence_pages=(0, 4, 6), context_page_indexes=[6, 4])
    child = fork_correction(store, identity, request, "explicit-context")
    guidance = child["checkpoint"]["correction_guidance"]
    assert guidance["later_source_pages"] == [
        {"page_index": page, "source_sha256": scene.source_sha256} for page in [6, 4, 2]]
    assert "poses" not in json.dumps(guidance)
    lineage = child["checkpoint"]["correction_lineage"][-1]
    assert lineage["requested_controls"] == {"context_page_indexes": [6, 4]}
    transition = lineage["exploration_policy_transition"]
    assert transition["requested_controls"] == lineage["requested_controls"]
    assert transition["parent_normalized_max_panel_attempts"] == transition["derived_max_panel_attempts"] == 2
    assert _parent_state(store, identity, directory) == before


@pytest.mark.parametrize(("selected", "expected"), [([4, 6], [2, 0, 4, 6]),
                                                     ([6, 4], [2, 0, 6, 4]),
                                                     ([2, 6], [2, 0, 6]),
                                                     ([0, 4], [2, 0, 4])])
def test_chosen_pages_reach_actual_exploration_prompt_without_inference(tmp_path, scene_data, monkeypatch, selected, expected):
    store, identity, scene, directory = _seed(tmp_path, scene_data)
    before = _parent_state(store, identity, directory)
    request = _request(tmp_path, scene, evidence_pages=sorted({0, *selected}),
                       context_page_indexes=selected, max_panel_attempts=1)
    child = fork_correction(store, identity, request, "prompt-context")
    pages = tmp_path / "public/pages" / scene.source_sha256
    pages.mkdir(parents=True)
    for page in range(scene.sources[0].page_count):
        Image.new("RGB", (32, 32), (page * 20, 30, 60)).save(pages / f"page-{page:03d}.png")
    monkeypatch.setattr("guide2build.engine.perception.source_relevant_catalogue", lambda *a, **kw: [])
    monkeypatch.setattr("guide2build.engine.alpha.individual_part_index", lambda *a, **kw: [])
    monkeypatch.setattr("guide2build.engine.connectors.connector_context", lambda *a, **kw: {})

    class ReachedInstruction(Exception):
        pass

    captured = {}

    def capture(**kwargs):
        prompt = kwargs["prompt"]
        captured["context"], _ = json.JSONDecoder().raw_decode(prompt[prompt.index('{"set_number"'):])
        captured["images"] = kwargs["images"]
        captured["policy"] = kwargs["calls"].policy
        raise ReachedInstruction

    def forbidden(*args, **kwargs):
        pytest.fail("Source-guided restart context construction must not invoke a provider")

    monkeypatch.setattr("guide2build.engine.exploration._instruction", capture)
    claimed = store.claim("prompt-test", job_id=child["id"])
    checkpoint = claimed["checkpoint"]

    def save(stage, state="constructing", error=None):
        checkpoint["stage"] = stage
        store.checkpoint(child["id"], "prompt-test", checkpoint, state, error)

    with pytest.raises(ReachedInstruction):
        run_exploration(job=claimed, checkpoint=checkpoint, directory=store.root / "jobs" / child["id"],
            source_hash=scene.source_sha256, pages_dir=pages, page_count=scene.sources[0].page_count,
            runtime=SimpleNamespace(call=forbidden), save=save,
            heartbeat=SimpleNamespace(check=lambda: None), store=store)
    assert captured["context"]["input_image_page_order"] == expected
    assert [path.name for path in captured["images"]] == [f"page-{page:03d}.png" for page in expected]
    assert len(expected) == len(set(expected)) and len(expected) <= 4
    assert captured["context"]["page_index"] == expected[0] == 2
    assert captured["policy"]["proposal_attempts"] == 1
    assert checkpoint["model_calls_used"] == checkpoint["inherited_model_calls_used"] == 5
    assert checkpoint["local_model_calls_used"] == 0 and checkpoint["exploration_calls"] == {}
    assert _parent_state(store, identity, directory) == before


@pytest.mark.parametrize(("context", "evidence", "message"), [
    ([4, 4], (0, 4), "unique"), ([4, 6, 7], (0, 4, 6, 7), "at most 2"),
    ([-1], (0,), "greater than or equal"), ([True], (0,), "valid integer"),
    (["4"], (0, 4), "valid integer"), ([4.0], (0, 4), "valid integer"),
    ([6], (0,), "cited in request evidence"),
])
def test_invalid_context_request_rejects_before_job_or_source_access(tmp_path, scene_data, monkeypatch, context, evidence, message):
    request = _validation_request(scene_data, evidence_pages=evidence, context_page_indexes=context)
    _reject_before_job_or_source(tmp_path, monkeypatch, request, message=message)


@pytest.mark.parametrize(("context", "evidence", "message"), [([8], (0, 8), "verified source page")])
def test_invalid_or_unbound_context_pages_reject_without_parent_changes(tmp_path, scene_data, context, evidence, message):
    store, identity, scene, directory = _seed(tmp_path, scene_data)
    before = _parent_state(store, identity, directory)
    request = _request(tmp_path, scene, evidence_pages=evidence, context_page_indexes=context)
    with pytest.raises(ValueError, match=message):
        fork_correction(store, identity, request, "invalid-context")
    assert _parent_state(store, identity, directory) == before and len(store.list()) == 1


def test_context_page_must_name_verified_source_bytes(tmp_path, scene_data):
    store, identity, scene, directory = _seed(tmp_path, scene_data)
    before = _parent_state(store, identity, directory)
    request = _request(tmp_path, scene, evidence_pages=(0, 4), context_page_indexes=[4])
    value = json.loads(request.read_text())
    value["evidence"][1]["source_sha256"] = "f" * 64
    write_json(request, value)
    with pytest.raises(ValueError, match="verified source page"):
        fork_correction(store, identity, request, "unverified-context")
    assert _parent_state(store, identity, directory) == before and len(store.list()) == 1


@pytest.mark.parametrize("control", [{"context_page_indexes": [0]}, {"context_page_indexes": []}, {"max_panel_attempts": 1}])
def test_controls_are_exclusive_to_source_guided_restarts(tmp_path, scene_data, monkeypatch, control):
    request = _validation_request(scene_data, restart=False, **control)
    _reject_before_job_or_source(tmp_path, monkeypatch, request, message="require restart_main_step")


@pytest.mark.parametrize(("parent_cap", "requested_cap"), [(2, 1), (2, 2), (1, 1)])
def test_attempt_cap_only_reduces_or_preserves_parent_and_keeps_budget(tmp_path, scene_data, parent_cap, requested_cap):
    store, identity, scene, directory = _seed(tmp_path, scene_data, cap=parent_cap)
    before = _parent_state(store, identity, directory)
    child = fork_correction(store, identity, _request(tmp_path, scene, max_panel_attempts=requested_cap), "attempt-control")
    cp = child["checkpoint"]
    assert child["config"]["max_panel_attempts"] == cp["exploration_policy"]["proposal_attempts"] == requested_cap
    assert child["config"]["max_model_calls"] == 7
    assert cp["model_calls_used"] == cp["inherited_model_calls_used"] == 5
    assert cp["local_model_calls_used"] == 0 and cp["exploration_calls"] == {}
    transition = cp["correction_lineage"][-1]["exploration_policy_transition"]
    assert transition["requested_controls"] == {"max_panel_attempts": requested_cap}
    assert transition["parent_normalized_max_panel_attempts"] == parent_cap
    assert transition["derived_max_panel_attempts"] == requested_cap
    assert ("proposal_attempts" in transition["changed_fields"]) == (parent_cap != requested_cap)
    assert store.lineage_model_calls_used(identity) == 5
    assert _parent_state(store, identity, directory) == before


def test_attempt_cap_cannot_widen_one_to_two(tmp_path, scene_data):
    store, identity, scene, directory = _seed(tmp_path, scene_data, cap=1)
    before = _parent_state(store, identity, directory)
    with pytest.raises(ValueError, match="cannot increase"):
        fork_correction(store, identity, _request(tmp_path, scene, max_panel_attempts=2), "wider-cap")
    assert _parent_state(store, identity, directory) == before and len(store.list()) == 1


@pytest.mark.parametrize("cap", [-1, 0, 3, 1.5, True, "1"])
def test_attempt_cap_rejects_out_of_range_and_noninteger_values(tmp_path, scene_data, monkeypatch, cap):
    request = _validation_request(scene_data, max_panel_attempts=cap)
    _reject_before_job_or_source(tmp_path, monkeypatch, request)


def test_legacy_parent_attempt_cap_is_normalized_before_comparison(tmp_path, scene_data):
    store, identity, scene, directory = seed_job(tmp_path, scene_data,
        config={"model": "test", "revision": "base", "max_panel_attempts": 3})
    before = _parent_state(store, identity, directory)
    child = fork_correction(store, identity, _request(tmp_path, scene, max_panel_attempts=2), "legacy-cap")
    assert child["config"]["max_panel_attempts"] == 2
    assert child["checkpoint"]["correction_lineage"][-1]["exploration_policy_transition"]["parent_normalized_max_panel_attempts"] == 2
    assert _parent_state(store, identity, directory) == before


@pytest.mark.parametrize("null_controls", [False, True])
def test_default_restart_preserves_fallback_attempts_and_legacy_request_hash(tmp_path, scene_data, null_controls):
    store, identity, scene, directory = _seed(tmp_path, scene_data)
    before = _parent_state(store, identity, directory)
    request = _request(tmp_path, scene, **({"context_page_indexes": None, "max_panel_attempts": None} if null_controls else {}))
    legacy_data = CorrectionRequest.model_validate(json.loads(request.read_text())).model_dump(mode="json",
        exclude={"context_page_indexes", "max_panel_attempts", "source_only_index_reviews", "review_profile",
                 "source_reference_profile"})
    child = fork_correction(store, identity, request, "default-control")
    cp = child["checkpoint"]
    assert cp["correction_guidance"]["later_source_pages"] == [
        {"page_index": page, "source_sha256": scene.source_sha256} for page in [2, 4]]
    assert child["config"]["max_panel_attempts"] == cp["exploration_policy"]["proposal_attempts"] == 2
    lineage = cp["correction_lineage"][-1]
    assert "requested_controls" not in lineage and "requested_controls" not in lineage["exploration_policy_transition"]
    assert lineage["request_sha256"] == digest(legacy_data)
    recorded = json.loads((store.root / "jobs" / child["id"] / "correction-request.json").read_text())
    assert recorded == legacy_data
    assert "source_reference_profile" not in recorded
    assert _parent_state(store, identity, directory) == before
    assert cp["model_calls_used"] == cp["inherited_model_calls_used"] == 5 and cp["local_model_calls_used"] == 0
    assert _policy(child["config"], copy.deepcopy(cp), scene.source_sha256, scene.sources[0].page_count) == cp["exploration_policy"]
