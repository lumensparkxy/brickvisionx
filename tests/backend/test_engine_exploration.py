"""Offline original synthetic evidence tests; none establish LEGO reconstruction accuracy."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from guide2build.engine import exploration
from guide2build.engine.provider import ProviderFailure
from guide2build.releases.models import SceneV2, digest


SOURCE = "a" * 64


def synthetic_proposal(prompt, ordinal, *, mode="valid"):
    marker = prompt.index('{"set_number"')
    context = json.JSONDecoder().raw_decode(prompt[marker:])[0]
    current = context["current_own_assembly"]
    number = ordinal + 1
    identity = f"synthetic-part-{number}"
    source = {"page_index": context.get("page_index", ordinal), "bbox": [0, 0, 1, 1], "source_sha256": SOURCE}
    proposal = {"delta_json": None, "blockers": [], "observations": [], "connections": [],
                "roots": [], "sequence": [], "source_views": [], "part_observations": [], "placement_hints": []}
    if mode == "none":
        proposal["blockers"] = ["The synthetic source does not identify this piece."]
        return proposal
    delta = {"new_sections": [] if current else [{"section_id": "synthetic-main", "label": "Synthetic source", "source_sha256": SOURCE}],
             "new_instances": [{"instance_id": identity, "part_id": "synthetic", "color_code": "4",
                 "geometry_ref": "parts/synthetic.dat", "source": source,
                 "origin": "vision_proposal", "mapping_status": "candidate"}],
             "new_steps": [{"step_id": f"synthetic-step-{number}", "section_id": "synthetic-main", "main_step_number": number,
                 "substep_label": None, "instruction": "Place the synthetic source piece.", "source": source,
                 "introduced_instance_ids": [identity], "active_instance_ids": [identity],
                 "visible_instance_ids": [p["instance_id"] for p in current["physical_instances"]] + [identity] if current else [identity],
                 "poses": {identity: {"position_ldu": [number * 20, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]}},
                 "action": "add_parts", "assembly_group_id": None}]}
    if mode == "bad_delta":
        delta["new_steps"][0]["poses"] = {}
    if mode == "wrong_page":
        source["page_index"] = 7
    proposal["delta_json"] = json.dumps(delta)
    proposal["sequence"] = [{"step_id": f"synthetic-step-{number}", "kind": "printed_main",
        "printed_label": str(number), "bbox": [0, 0, 1, 1], "explanation": "Original synthetic evidence."}]
    return proposal


class SyntheticProvider:
    model = "synthetic-provider"
    thinking_level = "high"

    def __init__(self):
        self.calls = []
        self.modes = {}
        self.review_mode = "fail"
        self.failure = None

    def call(self, prompt, images, schema, evidence, check):
        check()
        key = evidence.parent.name
        self.calls.append({"key": key, "prompt": prompt, "images": images})
        if self.failure:
            raise self.failure
        if key.startswith("index-"):
            page = int(key.split("-")[1])
            if "source_sha256" not in schema.get("properties", {}):
                return {"panels": [{"section": "synthetic-main", "number": page+1, "label": str(page+1),
                                    "bbox": [0, 0, 1, 1], "kind": "main"}] if page < 2 else [], "uncertainty": []}
            source = json.JSONDecoder().raw_decode(prompt[prompt.index('{"source_sha256"'):])[0]
            return {"schema_version": "2.0", "source_sha256": source["source_sha256"],
                    "page_index": page, "page_sha256": source["page_sha256"],
                    "panels": [{"section": "synthetic-main", "number": page+1, "label": str(page+1),
                                "bbox": [0, 0, 1, 1], "kind": "main", "region_id": f"main-{page+1}",
                                "role": "build_event", "event_key": f"main-{page+1}", "associated_event": None,
                                "semantic_status": "explicit", "evidence": "Original synthetic numbered building operation.",
                                "uncertainty": []}] if page < 2 else [],
                    "uncertainty": ["Synthetic source index uncertainty"] if page == 1 else []}
        if key.endswith("proposal"):
            ordinal = int(key.split("-")[1])
            return synthetic_proposal(prompt, ordinal, mode=self.modes.get(ordinal, "valid"))
        if self.review_mode == "malformed":
            return {"unexpected": True}
        if self.review_mode == "wrong_id":
            identity = "not-rendered"
        else:
            identity = "synthetic-raw"
        return {"selected_hypothesis_id": identity, "reason": "Original synthetic visual comparison.",
                "reviews": [{"hypothesis_id": identity, "coverage_agrees": self.review_mode == "pass",
                             "assembly_agrees": self.review_mode == "pass", "findings": []}]}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    from guide2build.engine import alpha, connectors, geometry, hypotheses, perception, rendering
    directory = tmp_path / "engine" / "jobs" / "synthetic-job"
    directory.mkdir(parents=True)
    pages = tmp_path / "public" / "pages" / SOURCE
    pages.mkdir(parents=True)
    for index in range(8):
        Image.new("RGB", (32, 24), "white").save(pages / f"page-{index:03d}.png")
    cp, events, renders = {}, [], []
    provider = SyntheticProvider()
    job = {"id": "synthetic-job", "set_number": "30669", "guide_id": "alt-02",
           "config": {"model": "synthetic-provider", "execution_policy": "explore", "max_model_calls": 100}}
    def save(stage, state="constructing", error=None):
        cp["stage"] = stage
        events.append({"stage": stage, "state": state, "error": error})
    def asset_pins(scene, root):
        return {"scope": "synthetic only", "parts": sorted({p.part_id for p in scene.instances})}
    def enumerate_candidates(scene, previous, root, **kwargs):
        assert kwargs["max_candidates"] == 64 and kwargs["beam_width"] == 8 and kwargs["return_count"] == 3
        return {"candidates": [{"hypothesis_id": "synthetic-raw", "scene": scene.model_dump(mode="json"),
                 "findings": [exploration.finding("unsupported_connector", "Synthetic unsupported connection")], "solver_report": {}}],
                "evaluated_count": 1, "findings": [], "limits": kwargs | {"connections": [], "roots": [], "hints": []}}
    def parts(observations, source, geometry, output, **kwargs):
        output.mkdir(parents=True, exist_ok=True)
        paths = []
        for name in ("source.png", "part-sheet.png"):
            path = output / name
            Image.new("RGB", (16, 16), "white").save(path)
            paths.append(str(path))
        return {"image_paths": paths, "findings": []}
    def render(scene_path, geometry, output, *, source_views, first_step, **kwargs):
        scene = SceneV2.model_validate_json(scene_path.read_text())
        output.mkdir(parents=True)
        frames = []
        for index, step in enumerate(scene.steps[first_step - 1:]):
            path = output / f"frame-{index}.png"
            Image.new("RGB", (16, 16), "red").save(path)
            frames.append({"step_id": step.step_id, "screenshot": path.name,
                           "png_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "camera_mode": "overview", "source_camera": None})
        result = {"status": "rendered", "scene_sha256": digest(scene), "steps": frames}
        (output / "report.json").write_text(json.dumps(result))
        renders.append({"source_views": source_views, "scene": scene, "report": result})
        return result
    monkeypatch.setattr(alpha, "individual_part_index", lambda *args: [])
    monkeypatch.setattr(alpha, "_geometry_pins", asset_pins)
    monkeypatch.setattr(connectors, "connector_context", lambda *args: {})
    monkeypatch.setattr(geometry, "prepare_geometry", lambda *args: {"scope": "synthetic assets only"})
    monkeypatch.setattr(hypotheses, "enumerate_hypotheses", enumerate_candidates)
    monkeypatch.setattr(hypotheses, "source_view_alternatives", lambda *args: ({"synthetic": {"status": "poor_fit"}}, {}))
    monkeypatch.setattr(perception, "source_relevant_catalogue", lambda *args, **kwargs: {"parts": []})
    monkeypatch.setattr(perception, "prepare_part_evidence", parts)
    monkeypatch.setattr(rendering, "render_candidate", render)
    args = dict(job=job, checkpoint=cp, directory=directory, source_hash=SOURCE, pages_dir=pages,
                page_count=8, runtime=provider, save=save, heartbeat=SimpleNamespace(check=lambda: None))
    return SimpleNamespace(args=args, job=job, cp=cp, provider=provider, events=events, renders=renders,
                           directory=directory, pages=pages, save=save)


def test_poor_fit_unsupported_connection_and_failed_review_continue(harness):
    h = harness
    assert exploration.run_exploration(**h.args)
    assert h.cp["stage"] == "exploration_complete_with_findings"
    assert h.cp["processed_panels"] == h.cp["reconstructed_panels"] == 2
    assert h.events[-1]["state"] == "paused"
    assert len(h.renders) == 4 and all(item["source_views"] is None for item in h.renders)
    assert {r["attempt_count"] for r in h.cp["instruction_results"]} == {2}
    kinds = {f["category"] for f in h.cp["provisional_findings"]}
    assert {"unsupported_connector", "source_view", "visual_review"} <= kinds
    assert h.cp["source_index_findings"][0]["category"] == "source_index_uncertainty"
    scene = SceneV2.model_validate(h.cp["candidate"])
    assert scene.geometry_check == scene.connector_check == scene.physical_build_check == "not_run"
    assert scene.status == "needs_review"
    assert h.cp["model_calls_used"] == 16  # Eight source pages, four proposals, four comparisons.
    repair = next(call for call in h.provider.calls if call["key"] == "instruction-0000-attempt-2-proposal")
    assert "previous_instruction_best_candidate" in repair["prompt"]
    assert any(image.name == "part-sheet.png" for image in repair["images"])
    review = next(call for call in h.provider.calls if call["key"].endswith("review"))
    assert any(image.name == "source.png" for image in review["images"])
    following = next(call for call in h.provider.calls if call["key"] == "instruction-0001-attempt-1-proposal")
    assert "Synthetic unsupported connection" in following["prompt"]


def test_proposal_receives_complete_delta_payload_contract(harness):
    from guide2build.engine.attachment_prompt import PROMPT_SUFFIX
    from guide2build.engine.delta import SceneDelta
    h = harness
    exploration.run_exploration(**h.args, max_panels=1)
    proposals = [call for call in h.provider.calls if call["key"].endswith("proposal")]
    assert len(proposals) == 2
    for call in proposals:
        prompt = call["prompt"]
        context = json.JSONDecoder().raw_decode(prompt[prompt.index('{"set_number"'):])[0]
        assert context["scene_delta_schema"] == SceneDelta.model_json_schema()
        assert set(context["scene_delta_schema"]["required"]) == {"new_sections", "new_instances", "new_steps"}
        assert context["scene_delta_schema"]["$defs"]["StepV2"]["properties"]["poses"]
        assert exploration.SNAPSHOT_VISIBILITY_CONTRACT in prompt
    policy = h.cp["exploration_policy"]
    assert policy["scene_delta_schema_sha256"] == digest(SceneDelta.model_json_schema())
    assert "proposal_profile" not in policy
    assert all(PROMPT_SUFFIX not in call["prompt"] for call in h.provider.calls)
    assert policy["version"] == "source-exploration-v4"
    assert policy["candidate_selection_version"] == "source-quality-selection-v1"
    assert policy["snapshot_visibility_contract_sha256"] == hashlib.sha256(exploration.SNAPSHOT_VISIBILITY_CONTRACT.encode()).hexdigest()
    previous_policy = deepcopy(policy)
    calls = len(h.provider.calls)
    policy["version"] = "source-exploration-v2"
    with pytest.raises(ValueError, match="policy"):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == calls
    h.cp["exploration_policy"] = previous_policy


def test_attachment_profile_changes_only_proposals_and_is_fenced_on_resume(harness, monkeypatch):
    from guide2build.engine import attachment_prompt
    h = harness
    h.job["config"]["proposal_profile"] = attachment_prompt.VARIANT
    exploration.run_exploration(**h.args, max_panels=1)
    suffix = attachment_prompt.PROMPT_SUFFIX
    proposals = [call for call in h.provider.calls if call["key"].endswith("proposal")]
    assert len(proposals) == 2
    assert all(call["prompt"].count(suffix) == 1 for call in proposals)
    assert all(suffix not in call["prompt"] for call in h.provider.calls if not call["key"].endswith("proposal"))
    assert h.cp["model_calls_used"] == 12
    receipt = h.cp["exploration_policy"]["proposal_profile"]
    assert receipt == {"name": attachment_prompt.VARIANT, "version": attachment_prompt.VERSION,
                       "prompt_sha256": hashlib.sha256(suffix.encode()).hexdigest()}
    saved = deepcopy(h.cp)
    calls = len(h.provider.calls)
    h.job["config"].pop("proposal_profile")
    with pytest.raises(ValueError, match="changed on resume"):
        exploration.run_exploration(**h.args)
    assert h.cp == saved and len(h.provider.calls) == calls
    h.job["config"]["proposal_profile"] = attachment_prompt.VARIANT
    monkeypatch.setattr(attachment_prompt, "PROMPT_SUFFIX", suffix + "\nChanged experiment.")
    with pytest.raises(ValueError, match="changed on resume"):
        exploration.run_exploration(**h.args)
    assert h.cp == saved and len(h.provider.calls) == calls


@pytest.mark.parametrize("first_mode", ["none", "bad_delta"])
def test_no_renderable_proposal_records_gap_and_continues(harness, first_mode):
    h = harness
    h.provider.modes[0] = first_mode
    exploration.run_exploration(**h.args)
    assert h.cp["processed_panels"] == 2 and h.cp["reconstructed_panels"] == 1
    assert not h.cp["instruction_results"][0]["reconstructed"]
    assert h.cp["instruction_results"][0]["step_ids"] == []
    assert h.cp["instruction_results"][1]["step_ids"] == ["synthetic-step-2"]


@pytest.mark.parametrize("review_mode", ["malformed", "wrong_id"])
def test_invalid_visual_response_keeps_candidate(harness, review_mode):
    h = harness
    h.provider.review_mode = review_mode
    exploration.run_exploration(**h.args)
    assert h.cp["reconstructed_panels"] == 2
    assert any(f["category"] == "visual_review_not_run" for f in h.cp["provisional_findings"])


def test_resume_is_idempotent_and_rejects_candidate_and_render_tampering(harness):
    h = harness
    exploration.run_exploration(**h.args)
    calls = len(h.provider.calls)
    before = deepcopy(h.cp["candidate"])
    exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == calls and h.cp["candidate"] == before
    h.cp["candidate"]["steps"][-1]["poses"]["synthetic-part-2"]["position_ldu"][0] += 1
    with pytest.raises(ValueError, match="candidate differs"):
        exploration.run_exploration(**h.args)
    h.cp["candidate"] = before
    frame = next(h.directory.glob("exploration/instructions/*/attempt-*/candidate-*/renders/frame-0.png"))
    frame.write_bytes(b"tampered synthetic pixels")
    with pytest.raises(ValueError, match="evidence changed"):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == calls


def test_crash_after_result_receipt_promotes_without_inference(harness):
    h = harness
    class Crash(BaseException):
        pass
    def save(stage, *args):
        h.save(stage, *args)
        if stage == "exploration_instruction_recorded":
            raise Crash()
    h.args["save"] = save
    with pytest.raises(Crash):
        exploration.run_exploration(**h.args)
    before = [item["key"] for item in h.provider.calls]
    h.args["save"] = h.save
    exploration.run_exploration(**h.args)
    assert [item["key"] for item in h.provider.calls][:len(before)] == before
    assert sum(item["key"] == "instruction-0000-attempt-1-proposal" for item in h.provider.calls) == 1
    assert h.cp["processed_panels"] == 2


@pytest.mark.parametrize("during", ["proposal", "review", "repair_proposal"])
def test_completed_provider_receipt_recovers_without_duplicate_call(harness, during):
    h = harness
    key = "instruction-0000-attempt-2-proposal" if during == "repair_proposal" else f"instruction-0000-attempt-1-{during}"
    class Crash(BaseException):
        pass
    def save(stage, *args):
        h.save(stage, *args)
        if stage == "exploration_call_completed" and h.provider.calls[-1]["key"] == key:
            raise Crash()
    h.args["save"] = save
    with pytest.raises(Crash):
        exploration.run_exploration(**h.args)
    h.args["save"] = h.save
    exploration.run_exploration(**h.args)
    assert sum(call["key"] == key for call in h.provider.calls) == 1
    assert h.cp["processed_panels"] == 2


def test_provider_result_tamper_and_shared_lineage_budget_are_hard(harness):
    h = harness
    h.args["store"] = SimpleNamespace(lineage_model_calls_used=lambda root: 99)
    exploration.run_exploration(**h.args)
    assert h.cp["model_calls_used"] == 100 and h.cp["local_model_calls_used"] == 1
    assert h.cp["stage"] == "exploration_budget_exhausted"
    result = next(h.directory.glob("exploration/calls/*/result.json"))
    result.write_text('{"panels": [], "uncertainty": []}')
    with pytest.raises(ValueError, match="provider result changed"):
        exploration.run_exploration(**h.args)


def test_budget_is_frozen_includes_indexing_and_honors_one_attempt(harness):
    h = harness
    h.job["config"].update(max_model_calls=10, max_panel_attempts=1)
    exploration.run_exploration(**h.args)
    assert h.cp["stage"] == "exploration_budget_exhausted"
    assert h.cp["model_calls_used"] == 10 and h.cp["processed_panels"] == 1
    assert h.cp["instruction_results"][0]["attempt_count"] == 1
    calls = len(h.provider.calls)
    exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == calls
    h.job["config"]["max_model_calls"] = 11
    with pytest.raises(ValueError, match="budget changed"):
        exploration.run_exploration(**h.args)


def test_wrong_source_page_is_hard_and_quota_is_propagated(harness):
    h = harness
    h.provider.modes[0] = "wrong_page"
    with pytest.raises(ValueError, match="exact requested official page"):
        exploration.run_exploration(**h.args)
    assert not h.cp.get("candidate")
    h.provider.failure = ProviderFailure("subscription_limit", "Original synthetic quota failure")
    h.job["config"]["revision"] = "another"
    h.args["checkpoint"] = {}
    with pytest.raises(ProviderFailure, match="quota"):
        exploration.run_exploration(**h.args)


@pytest.mark.parametrize("restart", [True, False])
def test_correction_seed_supports_empty_restart_or_complete_assisted_revision(harness, restart):
    h = harness
    exploration.run_exploration(**h.args)
    before = len(h.provider.calls)
    candidate = None if restart else deepcopy(h.cp["candidate"])
    results = [] if restart else deepcopy(h.cp["instruction_results"])
    if candidate:
        candidate["revision"] = "synthetic-correction"
        candidate["instances"][0]["origin"] = "pdf_assisted_authoring"
        for item in results:
            item["inherited_from_job"] = h.job["id"]
    derived = {"candidate": candidate, "page_indexes": deepcopy(h.cp["page_indexes"]),
               "instruction_results": results, "processed_panels": len(results),
               "model_calls_used": h.cp["model_calls_used"], "inherited_model_calls_used": h.cp["model_calls_used"],
               "local_model_calls_used": 0, "exploration_seed": {
                   "candidate_sha256": digest(candidate) if candidate else None,
                   "source_sha256": SOURCE, "parent_job_id": h.job["id"], "processed_panels": len(results)}}
    directory = h.directory.parent / "synthetic-correction"
    directory.mkdir()
    exploration._write(directory / "source-index-seed.json", derived["page_indexes"])
    derived["exploration_seed"]["source_index_sha256"] = digest(derived["page_indexes"])
    def save(stage, state="constructing", error=None):
        derived["stage"] = stage
    args = dict(h.args, job=dict(h.job, id="synthetic-correction"), checkpoint=derived,
                directory=directory, save=save)
    exploration.run_exploration(**args)
    assert derived["artifact_kind"] == "corrected_exploration_candidate"
    assert derived["processed_panels"] == derived["reconstructed_panels"] == 2
    if restart:
        new_calls = h.provider.calls[before:]
        assert len(new_calls) == 8 and all(not item["key"].startswith("index-") for item in new_calls)
        first = new_calls[0]["prompt"]
        assert '"current_own_assembly":null' in first
        assert "synthetic-step-2" not in first
    else:
        assert len(h.provider.calls) == before and derived["candidate"] == candidate


def test_unchanged_assisted_prefix_does_not_allow_new_model_authoring_claims(harness):
    from guide2build.engine.runner import validate_candidate
    from guide2build.engine.delta import assemble_delta
    h = harness
    exploration.run_exploration(**h.args, max_panels=1)
    previous = deepcopy(h.cp["candidate"])
    previous["instances"][0]["origin"] = "pdf_assisted_authoring"
    context = {"set_number": "30669", "current_own_assembly": exploration.current_context(previous)}
    proposal = synthetic_proposal(json.dumps(context), 1)
    scene = assemble_delta(proposal["delta_json"], h.job, SOURCE, 8, previous)
    assert validate_candidate(scene.model_dump_json(), h.job, SOURCE, 8, previous)
    scene.instances[-1].origin = "human_correction"
    with pytest.raises(ValueError, match="impersonate"):
        validate_candidate(scene.model_dump_json(), h.job, SOURCE, 8, previous)


@pytest.mark.parametrize("partial_report", [False, True])
def test_actual_renderer_sidecar_interruption_uses_fresh_bounded_output(tmp_path, monkeypatch, partial_report):
    """Run the actual Python renderer boundary, replacing only its browser process."""
    from guide2build.engine import rendering
    from guide2build.engine.delta import assemble_delta
    from guide2build.engine.source_view import SourceCamera
    job = {"id": "render-recovery", "set_number": "30669", "guide_id": "alt-02"}
    proposal = synthetic_proposal(json.dumps({"set_number": "30669", "current_own_assembly": None}), 0)
    scene = assemble_delta(proposal["delta_json"], job, SOURCE, 8, None)
    candidate = tmp_path / "candidate"
    exploration._write(candidate / "scene.json", scene)
    view = SourceCamera(projection="orthographic", right=(1, 0, 0), up=(0, 1, 0),
        target_ldu=(0, 0, 0), vertical_span_ldu=100, image_size=(64, 64)).model_dump(mode="json")
    cameras = {scene.steps[0].step_id: view}
    invoked = []

    class BrowserProcess:
        returncode = 0

        def __init__(self, args, **kwargs):
            output = Path(args[args.index("--output") + 1])
            invoked.append(output)
            # render_candidate has already written its immutable xb camera sidecar.
            camera_bytes = Path(args[args.index("--source-views") + 1]).read_bytes()
            if len(invoked) == 1:
                if partial_report:
                    output.mkdir()
                    (output / "report.json").write_bytes(b'{"status":')
                raise RuntimeError("Synthetic interruption after real camera sidecar creation")
            output.mkdir()
            (output / "source-views.json").write_bytes(camera_bytes)
            screenshot = output / "frame.png"
            Image.new("RGB", (64, 64), "red").save(screenshot)
            frame = {"input": view, "viewport": {"width": 64, "height": 64},
                "source_rect": {"x": 0, "y": 0, "width": 64, "height": 64},
                "projection_matrix": [.02, 0, 0, 0, 0, .02, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                "matrix_world_inverse": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}
            report = {"status": "rendered", "scene_sha256": digest(scene),
                "source_views_sha256": hashlib.sha256(camera_bytes).hexdigest(),
                "steps": [{"step_id": scene.steps[0].step_id, "screenshot": screenshot.name,
                    "png_sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
                    "camera_mode": "source_orthographic", "source_camera": frame}]}
            exploration._write(output / "report.json", report)

        def poll(self):
            return 0

    monkeypatch.setattr(rendering.shutil, "which", lambda name: "/synthetic/node")
    monkeypatch.setattr(rendering.subprocess, "Popen", BrowserProcess)
    with pytest.raises(RuntimeError, match="after real camera sidecar"):
        exploration._render_diagnostic(scene, tmp_path, candidate, 1, cameras, lambda: None)
    retained = (candidate / "renders.source-views.json").read_bytes()
    report, output = exploration._render_diagnostic(scene, tmp_path, candidate, 1, cameras, lambda: None)
    assert output.name == "renders-retry-1" and report["status"] == "rendered"
    assert (candidate / "renders.source-views.json").read_bytes() == retained
    if partial_report:
        assert (candidate / "renders/report.json").read_bytes() == b'{"status":'
    assert json.loads((candidate / "render-attempts.json").read_text())["retained_incomplete_directories"] == ["renders"]
    assert exploration._render_diagnostic(scene, tmp_path, candidate, 1, cameras, lambda: None)[1] == output
    assert len(invoked) == 2  # The third invocation reuses hash-checked pixels.
    (output / "frame.png").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="evidence changed"):
        exploration._render_diagnostic(scene, tmp_path, candidate, 1, cameras, lambda: None)
    assert len(invoked) == 2  # Integrity errors cannot trigger a replacement render.
    for name in ("renders-retry-1", "renders-retry-2"):
        target = candidate / name
        target.mkdir(exist_ok=True)
        (target / "report.json").write_bytes(b'{"status":')
    with pytest.raises(ValueError, match="exhausted three"):
        exploration._render_diagnostic(scene, tmp_path, candidate, 1, cameras, lambda: None)


def test_explicit_landmark_override_is_fixed_and_retained_in_new_instruction(harness, monkeypatch):
    from guide2build.engine import hypotheses
    h = harness
    # Deliberately insufficient source evidence remains a finding, never a fitted camera.
    for index in range(8):
        Image.new("RGB", (64, 64), "white").save(h.pages / f"page-{index:03d}.png")
    observation = {"step_id": "synthetic-step-1", "landmarks": [], "view_family": "upright_above"}
    h.cp["landmark_overrides"] = {"synthetic-step-1": observation}
    monkeypatch.setattr(hypotheses, "source_view_alternatives", lambda *args: ({"synthetic-step-1": {
        "status": "poor_fit", "selected_observation": {"step_id": "wrong-automatic-identity"},
        "landmark_alternatives": [{"identity_changes": {"a": "b"}}]}}, {}))
    exploration.run_exploration(**h.args, max_panels=1)
    result = h.cp["instruction_results"][0]
    record = json.loads((h.directory / result["source_views_path"]).read_text())
    fit = record["fits"]["synthetic-step-1"]
    assert fit["status"] == "insufficient" and fit["correspondence_policy"] == "explicit_correction"
    assert fit["selected_observation"] == fit["correction_observation"] == observation
    assert fit["identity_changes"] == {} and fit["landmark_alternatives"] == [{"identity_changes": {"a": "b"}}]
    assert record["observations"] == [observation] and not record["cameras"]
    assert h.cp["reconstructed_panels"] == 1
    assert h.cp["exploration_policy"]["landmark_overrides_sha256"] == digest(h.cp["landmark_overrides"])
    h.cp["landmark_overrides"]["synthetic-step-1"]["view_family"] = "unconstrained"
    with pytest.raises(ValueError, match="policy"):
        exploration.run_exploration(**h.args)


@pytest.mark.parametrize("issue", ["unknown_step", "invisible_piece", "bad_landmark", "source_page"])
def test_landmark_override_invalid_binding_is_hard(harness, monkeypatch, issue):
    from guide2build.engine import connectors
    from guide2build.engine.delta import assemble_delta
    h = harness
    proposal = synthetic_proposal(json.dumps({"set_number": "30669", "current_own_assembly": None}), 0)
    scene = assemble_delta(proposal["delta_json"], h.job, SOURCE, 8, None)
    observation = {"step_id": "synthetic-step-1", "landmarks": [{
        "instance_id": "synthetic-part-1", "landmark_id": "unknown", "image_uv": [.5, .5]}]}
    if issue == "unknown_step":
        observation["step_id"] = "missing-step"
    if issue == "invisible_piece":
        observation["landmarks"][0]["instance_id"] = "missing-piece"
    if issue == "bad_landmark":
        def bad_landmark(*args):
            raise ValueError("Unknown verified geometry landmark")
        monkeypatch.setattr(connectors, "world_landmark", bad_landmark)
    with pytest.raises(ValueError):
        exploration._landmark_corrections(scene, None, {observation["step_id"]: observation},
            h.directory, SOURCE, 1 if issue == "source_page" else 0)


def _letterboxed_camera_frame():
    """Synthetic matrices for a 128x96 source inside a 200x96 canvas."""
    from guide2build.engine.source_view import SourceCamera
    view = SourceCamera(projection="orthographic", right=(1, 0, 0), up=(0, 1, 0),
        target_ldu=(0, 0, 0), vertical_span_ldu=100, image_size=(128, 96)).model_dump(mode="json")
    return {"input": view,
        "viewport": {"width": 200, "height": 96},
        "source_rect": {"x": 36, "y": 0, "width": 128, "height": 96},
        "projection_matrix": [.0096, 0, 0, 0, 0, .02, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        "matrix_world_inverse": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}


@pytest.mark.parametrize("clipped", [True, False])
def test_source_camera_registration_matches_actual_clipped_or_canvas_png(tmp_path, clipped):
    from guide2build.engine.perception import compare_source_render_images
    source = tmp_path / "source.png"
    foreground = Image.new("RGB", (128, 96), "white")
    foreground.paste(Image.new("RGB", (48, 40), "red"), (40, 28))
    foreground.save(source)
    screenshot = tmp_path / "render.png"
    picture = Image.new("RGB", (128, 96) if clipped else (200, 96), "white")
    picture.paste(foreground, (0 if clipped else 36, 0))
    picture.save(screenshot)
    frame = {"source_camera": _letterboxed_camera_frame(), "png_sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest()}
    registration = exploration._render_registration(screenshot, frame)
    assert registration["status"] == "registered"
    assert registration["render_source_rect"]["x"] == (0 if clipped else 36)
    comparison = compare_source_render_images(source, screenshot, [0, 0, 1, 1], tmp_path / "comparison",
        render_source_rect=registration["render_source_rect"], camera_registration=registration)
    assert comparison["status"] == "ranked" and comparison["silhouette_iou"] == 1
    screenshot.write_bytes(b"tampered")
    with pytest.raises((ValueError, OSError)):
        exploration._render_registration(screenshot, frame)


def test_unknown_pixel_registration_falls_back_and_continues_booklet(harness, monkeypatch):
    from guide2build.engine import hypotheses, rendering, perception
    h = harness
    frame = _letterboxed_camera_frame()
    modes = []

    def fits(scene, previous, *args):
        new = scene.steps[len((previous or {}).get("steps", [])):]
        return ({step.step_id: {"status": "fitted"} for step in new},
                {step.step_id: frame["input"] for step in new})

    def render(scene_path, geometry, output, *, source_views, first_step, **kwargs):
        scene = SceneV2.model_validate_json(scene_path.read_text())
        output.mkdir()
        modes.append("source" if source_views else "overview")
        camera_bytes = json.dumps(source_views, sort_keys=True, separators=(",", ":")).encode() if source_views else None
        if camera_bytes:
            (output / "source-views.json").write_bytes(camera_bytes)
        frames = []
        for index, step in enumerate(scene.steps[first_step - 1:]):
            image = output / f"frame-{index}.png"
            # Hash-valid pixels whose dimensions match neither registered layout.
            Image.new("RGB", (100, 70) if source_views else (64, 64), "red").save(image)
            frames.append({"step_id": step.step_id, "screenshot": image.name,
                "png_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "camera_mode": "source_orthographic" if source_views else "overview",
                "source_camera": frame if source_views else None})
        report = {"status": "rendered", "scene_sha256": digest(scene), "steps": frames,
                  "source_views_sha256": hashlib.sha256(camera_bytes).hexdigest() if camera_bytes else None}
        exploration._write(output / "report.json", report)
        return report

    monkeypatch.setattr(hypotheses, "source_view_alternatives", fits)
    monkeypatch.setattr(rendering, "render_candidate", render)
    def cannot_compare(*args, **kwargs):
        pytest.fail("Unregistered pixels must not be assigned source comparison metrics")
    monkeypatch.setattr(perception, "compare_source_render_images", cannot_compare)
    exploration.run_exploration(**h.args)
    assert h.cp["processed_panels"] == h.cp["reconstructed_panels"] == 2
    assert modes == ["source", "overview"] * 4
    assert all(result["render_directory"].endswith("overview-renders") for result in h.cp["instruction_results"])
    assert all(any(item["category"] == "source_image_comparison" for item in result["findings"])
               for result in h.cp["instruction_results"])
    reports = sorted(h.directory.glob("exploration/instructions/*/attempt-*/candidate-0/image-comparisons.json"))
    assert len(reports) == 4
    for path in reports:
        comparison = next(iter(json.loads(path.read_text()).values()))
        assert comparison["status"] == "unavailable" and comparison["ranking_score"] is None
        assert comparison["registration"]["status"] == "unresolved"
        assert (path.parent / "renders/report.json").is_file()
        assert (path.parent / "comparison-fallback.json").is_file()
    calls = len(h.provider.calls)
    exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == calls and len(modes) == 8


def test_hypothesis_diagnostic_upgrade_preserves_retained_inputs(tmp_path):
    original = {"input_scene_sha256": SOURCE, "limits": {"max_candidates": 64, "beam_width": 8, "return_count": 3},
        "candidates": [{"hypothesis_id": "same", "scene": {"poses": "synthetic"}, "ranking_score": 1}],
        "retained_beam": [{"hypothesis_id": "same", "ranking_score": 1}]}
    exploration._write(tmp_path / "hypotheses.json", original)
    original_bytes = (tmp_path / "hypotheses.json").read_bytes()
    upgraded = deepcopy(original)
    upgraded["retained_beam"] = deepcopy(upgraded["candidates"])
    assert exploration._retain_hypotheses(tmp_path, upgraded) == upgraded
    assert (tmp_path / "hypotheses.json").read_bytes() == original_bytes
    assert json.loads((tmp_path / "hypotheses-diagnostic-refresh.json").read_text())["candidate_payloads_unchanged"]
    upgraded["candidates"][0]["scene"] = {"poses": "different"}
    with pytest.raises(ValueError, match="candidate payloads"):
        exploration._retain_hypotheses(tmp_path, upgraded)


def test_old_identity_warning_survives_later_broad_phase_diagnostics():
    identity = {**exploration.finding("part_identity_uncertainty", "Retained source part could be A or B.",
        step_ids=["old-step"], instance_ids=["old-part"]), "ordinal": 0, "candidate_part_ids": ["a", "b"]}
    later = [{**exploration.finding("aabb_overlap_candidate", f"Broad-phase pair {i}.",
        instance_ids=[f"new-{i}"]), "ordinal": i + 1} for i in range(40)]
    context = exploration._prior_finding_context([identity, dict(identity), *later], [],
        {"steps": [{"visible_instance_ids": ["old-part", "new-39"]}]}, 2)
    assert context["findings"][0]["candidate_part_ids"] == ["a", "b"]
    assert context["findings"][0]["occurrence_count"] == 2
    assert context["selection"]["included"] == 24 and context["selection"]["omitted_from_context"] == 17
    assert context["findings"][1]["instance_ids"] == ["new-39"]


def test_first_correction_dependent_prompt_rebuilds_inherited_findings(harness):
    h = harness
    exploration.run_exploration(**h.args, max_panels=1)
    candidate = deepcopy(h.cp["candidate"])
    results = deepcopy(h.cp["instruction_results"])
    results[0]["inherited_from_job"] = h.job["id"]
    results[0]["findings"].append(exploration.finding("part_identity_uncertainty", "Inherited source identity needs correction.",
        step_ids=["synthetic-step-1"], instance_ids=["synthetic-part-1"]))
    derived = {"candidate": candidate, "page_indexes": deepcopy(h.cp["page_indexes"]),
        "instruction_results": results, "processed_panels": 1,
        "model_calls_used": h.cp["model_calls_used"], "inherited_model_calls_used": h.cp["model_calls_used"],
        "local_model_calls_used": 0, "exploration_seed": {"candidate_sha256": digest(candidate),
            "source_sha256": SOURCE, "parent_job_id": h.job["id"], "processed_panels": 1}}
    assert "provisional_findings" not in derived  # Covers legacy fork checkpoints too.
    directory = h.directory.parent / "inherited-findings"
    directory.mkdir()
    exploration._write(directory / "source-index-seed.json", derived["page_indexes"])
    derived["exploration_seed"]["source_index_sha256"] = digest(derived["page_indexes"])
    before = len(h.provider.calls)
    def save(stage, *args):
        derived["stage"] = stage
    exploration.run_exploration(**dict(h.args, job=dict(h.job, id="inherited-findings"), checkpoint=derived,
        directory=directory, save=save))
    first = h.provider.calls[before]["prompt"]
    context = json.JSONDecoder().raw_decode(first[first.index('{"set_number"'):])[0]
    warning = next(item for item in context["prior_unresolved_findings"] if item["category"] == "part_identity_uncertainty")
    assert warning["inherited_from_job"] == h.job["id"] and warning["step_ids"] == ["synthetic-step-1"]
    assert any(item["category"] == "source_index_uncertainty" for item in context["prior_unresolved_findings"])
    assert derived["processed_panels"] == 2


def test_part_alternatives_and_hypothesis_findings_survive_review_omission(harness, monkeypatch):
    from guide2build.engine import hypotheses
    h = harness
    original_call = h.provider.call
    original_hypotheses = hypotheses.enumerate_hypotheses
    def call(prompt, images, schema, evidence, check):
        response = original_call(prompt, images, schema, evidence, check)
        if evidence.parent.name.endswith("proposal"):
            page = int(evidence.parent.name.split("-")[1])
            response["part_observations"] = [{"observation_id": f"uncertain-part-{page}",
                "source": {"page_index": page, "source_sha256": SOURCE, "bbox": [0, 0, .2, .2]},
                "quantity": 1, "shape_cues": ["plate"], "colour_description": "red",
                "candidates": [{"part_id": "synthetic", "reason": "Visible shape"},
                               {"part_id": "alternative", "reason": "Underside is hidden"}],
                "uncertainties": ["Underside identity is unresolved"]}]
        return response
    def enumerate_candidates(*args, **kwargs):
        result = original_hypotheses(*args, **kwargs)
        result["findings"] = [{"code": "unsupported_connection_hint", "severity": "unsupported",
            "step_id": "synthetic-step-1", "instance_ids": ["synthetic-part-1"],
            "message": "The hinted source connection has no supported metadata."}]
        return result
    h.provider.call = call
    monkeypatch.setattr(hypotheses, "enumerate_hypotheses", enumerate_candidates)
    exploration.run_exploration(**h.args)
    first = h.cp["instruction_results"][0]["findings"]
    observation = next(item for item in first if item.get("category") == "part_identity_uncertainty")
    assert observation["candidate_part_ids"] == ["synthetic", "alternative"]
    assert observation["uncertainties"] == ["Underside identity is unresolved"]
    assert any(item.get("code") == "unsupported_connection_hint" and item["scope"] == "hypothesis_search" for item in first)
    following = next(item for item in h.provider.calls if item["key"] == "instruction-0001-attempt-1-proposal")
    prompt = following["prompt"]
    context = json.JSONDecoder().raw_decode(prompt[prompt.index('{"set_number"'):])[0]
    assert any(item.get("candidate_part_ids") == ["synthetic", "alternative"] for item in context["prior_unresolved_findings"])
    assert any(item.get("code") == "unsupported_connection_hint" for item in context["prior_unresolved_findings"])


def test_single_identity_competing_colours_remain_an_explicit_uncertainty():
    value = synthetic_proposal(json.dumps({"set_number": "30669", "current_own_assembly": None}), 0)
    value["part_observations"] = [{"observation_id": "colour-uncertain", "source": {
        "page_index": 0, "source_sha256": SOURCE, "bbox": [0, 0, .2, .2]}, "quantity": 1,
        "shape_cues": ["plate"], "colour_description": "red or orange",
        "candidates": [{"part_id": "synthetic", "reason": "Known shape", "color_codes": ["4", "25"]}],
        "uncertainties": []}]
    findings = exploration._part_uncertainties(exploration.exploration_proposal_type().model_validate(value))
    assert len(findings) == 1 and findings[0]["candidate_color_codes"] == {"synthetic": ["4", "25"]}
    context = exploration._prior_finding_context(findings, [], None, 0)
    assert context["findings"][0]["candidate_color_codes"] == {"synthetic": ["4", "25"]}


def test_legacy_cached_prompt_replays_only_authenticated_json_order_equivalence(harness):
    from guide2build.engine.contracts import PageIndex
    h = harness
    h.cp.update(model_calls_used=0, local_model_calls_used=0)
    calls = exploration.ExplorationCalls(h.provider, h.directory, h.cp, h.save, h.args["heartbeat"], {"max_model_calls": 100})
    original = 'Keep these instructions exactly.\n{"category": "identity", "ids": [1, 2]}\nDo not alter this suffix.'
    equivalent = 'Keep these instructions exactly.\n{ "ids": [1,2], "category":"identity" }\nDo not alter this suffix.'
    images = [h.pages / "page-000.png"]
    first = calls.call("index-0000", original, images, PageIndex)
    target = h.directory / "exploration/calls/index-0000"
    original_receipt = (target / "receipt.json").read_bytes()
    # Reproduce legacy evidence that predates the engine-owned complete request.
    (target / "request.json").unlink()
    h.cp["exploration_calls"]["index-0000"].pop("request_sha256")
    (target / "provider").mkdir()
    (target / "provider/prompt.txt").write_text(original)
    assert calls.call("index-0000", equivalent, images, PageIndex) == first
    assert len(h.provider.calls) == h.cp["model_calls_used"] == 1
    assert (target / "receipt.json").read_bytes() == original_receipt
    assert (target / "provider/prompt.txt").read_text() == original
    assert json.loads((target / "request.json").read_text())["prompt"] == original
    for changed in (equivalent.replace('"identity"', '"pose"'), equivalent.replace("[1,2]", "[2,1]"),
                    equivalent.replace("Do not alter", "Alter"), equivalent.replace('"category":"identity"', '"category":"identity","category":"pose"')):
        with pytest.raises(ValueError):
            calls.call("index-0000", changed, images, PageIndex)
    Image.new("RGB", (32, 24), "black").save(images[0])
    with pytest.raises(ValueError, match="image/schema/runtime"):
        calls.call("index-0000", equivalent, images, PageIndex)
    assert len(h.provider.calls) == 1


def test_frozen_request_tampering_is_hard_before_cached_call_replay(harness):
    h = harness
    exploration.run_exploration(**h.args, max_panels=1)
    calls = len(h.provider.calls)
    request = next(h.directory.glob("exploration/calls/*/request.json"))
    request.write_bytes(request.read_bytes() + b" ")
    with pytest.raises(ValueError, match="frozen provider request changed"):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == calls


def test_prompt_replay_preserves_exact_numeric_tokens_and_types():
    semantics = exploration.ExplorationCalls._prompt_semantics
    assert semantics('{"x":0.1,"y":[1,2]}') == semantics('{ "y": [1, 2], "x": 0.1 }')
    for different in ('{"x":0.10000000000000001}', '{"x":"0.1"}', '{"x":["number","0.1"]}'):
        assert semantics('{"x":0.1}') != semantics(different)
    assert semantics('{"x":1}') != semantics('{"x":1.0}')
    assert semantics('{"x":1}') != semantics('{"x":true}')


# Retained main-2 residuals below come from the first-pass job's immutable
# ordinal-0001 attempt-1/2 source-views.json. They test selection policy only;
# synthetic scenes here do not establish source reconstruction accuracy.
RETAINED_MAIN2_FITS = ((21.49809981493281, 34.24993554328824),
                      (0.7462230552321297, 1.3341991973968634))


def _selection_record(identity, *, rms=1., maximum=2., review=True, physical="same", findings=(), images=None):
    source = {"source_sha256": SOURCE, "page_index": 1, "bbox": [0, 0, 1, 1]}
    scene = {"instances": [{"instance_id": "part", "part_id": physical, "color_code": "4", "geometry_ref": "parts/synthetic.dat"}],
        "steps": [{"step_id": "current", "section_id": "synthetic", "main_step_number": 2,
                   "substep_label": None, "action": "add_parts", "assembly_group_id": None,
                   "introduced_instance_ids": ["part"], "visible_instance_ids": ["part"],
                   "active_instance_ids": ["part"], "poses": {"part": {"position_ldu": [0, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]}},
                   "source": source}]}
    views = {"fits": {"current": {"status": "fitted" if rms is not None and rms <= 4 else "poor_fit",
                                  "rms_pixels": rms, "max_error_pixels": maximum}},
             "cameras": {"current": {"fixture": "already-validated-camera"}} if rms is not None and rms <= 4 else {}}
    return {"selection_id": identity, "candidate": scene, "hypothesis_id": identity, "rendered": True,
            "findings": list(findings),
            "visual_review": {"hypothesis_id": identity, "coverage_agrees": review, "assembly_agrees": review,
                              "visible_defects": [], "findings": []} if review is not None else None,
            "selection_evidence": {"physical_scene_sha256": exploration._physical_signature(scene), "step_ids": ["current"],
                "camera": exploration._camera_quality(scene, 0, views), "images": exploration._eligible_image_metrics(images or {})}}


def _eligible_image(score=.8, scope=SOURCE):
    return {"status": "ranked", "rank_eligible": True, "ranking_score": score,
            "mask_policy": {"kind": "border_connected_background", "version": "border-connected-background-v1"},
            "segmentation_checks": {"comparability": {"status": "passed"}},
            "comparison_scope_sha256": scope, "source_mask_sha256": "b" * 64,
            "render_mask_sha256": "c" * 64, "occlusion_mask_sha256": "d" * 64,
            "registration": {"status": "registered", "render_sha256": "e" * 64},
            "original_render_sha256": "e" * 64}


def test_selection_replays_main2_camera_improvement_without_uncertainty_penalty():
    first = _selection_record("attempt-1", rms=RETAINED_MAIN2_FITS[0][0], maximum=RETAINED_MAIN2_FITS[0][1],
        findings=[exploration.finding("source_view", "Poor source camera fit", step_ids=["current"])])
    # This legacy 0.9686 IoU scored almost-all-foreground backgrounds. Exclude it.
    legacy = _eligible_image(.9232836311627046)
    legacy.update(silhouette_iou=.9686446422126566, source_foreground_pixels=112431, valid_pixels=114188)
    legacy["mask_policy"] = {"kind": "diagnostic_near_white_threshold"}
    second = _selection_record("attempt-2", rms=RETAINED_MAIN2_FITS[1][0], maximum=RETAINED_MAIN2_FITS[1][1],
        findings=[exploration.finding("ambiguity", f"Retained hidden contact uncertainty {i}", step_ids=["current"]) for i in range(20)]
        + [exploration.finding("source_view", "Stale prose incorrectly claims no fitted view.", step_ids=["current"])],
        images={"current": legacy})
    original = deepcopy([first, second])
    selected, receipt = exploration._select_candidates([first, second])
    assert selected["selection_id"] == "attempt-2"
    assert receipt["status"] == "preferred_by_evidence"
    assert receipt["comparisons"][0]["reason"] == "numeric_camera_fit_status"
    assert receipt["profiles"]["attempt-2"]["images"] == {}
    assert len(selected["findings"]) == 22  # Both equivalent candidates retain their uncertainty.
    assert [first, second] == original
    assert receipt["profiles"]["attempt-2"]["review_status"] == "agrees"


def test_current_grouping_defect_precedes_good_callout_camera_and_ignores_inherited_defect():
    defect = {"code": "nonrigid_group", "severity": "error", "step_id": "current", "instance_ids": ["part"],
              "message": "Attachment lacks complete prior group membership/poses."}
    # Main4's detached fits were 0.035246/0.101402 px, but attachment had no fit
    # and the group-membership failure was in the current instruction.
    broken = _selection_record("broken", rms=.1014018476737874, maximum=.1193195416388786,
                               physical="broken", findings=[defect])
    reviewed = _selection_record("reviewed", rms=3., maximum=5., physical="other",
                                 findings=[dict(defect, step_id="previous")])
    selected, receipt = exploration._select_candidates([broken, reviewed])
    assert selected["selection_id"] == "reviewed"
    assert receipt["comparisons"][0]["reason"] == "current_assembly_and_review_evidence"
    assert receipt["profiles"]["reviewed"]["defects"] == []
    assert receipt["profiles"]["broken"]["defect_counts"]["grouping"]["major"] == 1


def test_grouping_failure_and_missing_review_are_explicit_tradeoff_not_clean_candidate():
    failure = {"code": "nonrigid_group", "severity": "error", "step_id": "current", "instance_ids": ["part"]}
    known = _selection_record("known", physical="reviewed", review=False, findings=[failure])
    unreviewed = _selection_record("unreviewed", physical="not-reviewed", review=None, rms=.01, maximum=.02)
    _, receipt = exploration._select_candidates([known, unreviewed])
    assert receipt["status"] == "unresolved_alternatives"
    assert receipt["frontier_ids"] == ["known", "unreviewed"]
    assert receipt["profiles"]["unreviewed"]["review_status"] == "not_run"
    clean = _selection_record("clean", physical="reviewed-clean")
    selected, _ = exploration._select_candidates([unreviewed, clean])
    assert selected["selection_id"] == "clean"


def test_visible_defects_and_review_failure_are_separate_from_honest_findings():
    candidate = _selection_record("wrong-colour", physical="one")
    candidate["visual_review"]["visible_defects"] = [{"domain": "colour", "severity": "major",
        "step_ids": ["current"], "instance_ids": ["part"], "description": "Visible source and model colours differ."}]
    other = _selection_record("reviewed", physical="two", rms=3., maximum=6.,
        findings=[exploration.finding("ambiguity", str(index)) for index in range(60)])
    selected, receipt = exploration._select_candidates([candidate, other])
    assert selected["selection_id"] == "reviewed"
    assert receipt["profiles"]["wrong-colour"]["defect_counts"]["colour"]["major"] == 1
    assert receipt["profiles"]["reviewed"]["review_status"] == "agrees"


def test_equivalent_scene_cannot_turn_missing_own_review_into_completed_review():
    unseen = _selection_record("not-reviewed", review=None, rms=.01, maximum=.02)
    seen = _selection_record("reviewed", rms=3., maximum=6.)
    selected, receipt = exploration._select_candidates([unseen, seen])
    assert selected["selection_id"] == "reviewed"
    assert receipt["profiles"]["not-reviewed"]["review_status"] == "not_run"
    assert not receipt["profiles"]["not-reviewed"]["own_review_completed"]


def test_camera_registration_evidence_precedes_residual_precision():
    unregistered = _selection_record("unregistered", rms=.01, maximum=.02)
    registered = _selection_record("registered", rms=3., maximum=6.)
    registered["selection_evidence"]["camera"]["units"][0]["render_registration"] = "registered"
    selected, receipt = exploration._select_candidates([unregistered, registered])
    assert selected["selection_id"] == "registered"
    assert receipt["comparisons"][0]["reason"] == "numeric_camera_fit_status"


def test_compatible_masks_only_break_camera_ties_and_legacy_metrics_never_rank():
    first = _selection_record("a", images={"current": _eligible_image(.8)})
    second = _selection_record("b", images={"current": _eligible_image(.95, scope="f" * 64)})
    _, receipt = exploration._select_candidates([first, second])
    assert receipt["status"] == "equivalent_tie"
    assert receipt["tied_alternatives"] == ["b"]
    second["selection_evidence"]["images"]["current"]["comparison_scope_sha256"] = SOURCE
    selected, receipt = exploration._select_candidates([first, second])
    assert selected["selection_id"] == "b"
    assert receipt["comparisons"][0]["reason"] == "compatible_segmented_image_evidence"
    legacy = _eligible_image(1)
    legacy["mask_policy"]["kind"] = "diagnostic_near_white_threshold"
    assert exploration._eligible_image_metrics({"current": legacy}) == {}


def test_camera_quality_preserves_missing_attachment_and_numeric_status():
    record = _selection_record("candidate")
    scene = deepcopy(record["candidate"])
    scene["steps"].append(dict(scene["steps"][0], step_id="attachment", action="attach_subassembly"))
    views = {"fits": {"current": {"status": "fitted", "rms_pixels": .035, "max_error_pixels": .036},
                      "attachment": {"status": "fitted", "rms_pixels": 21.498, "max_error_pixels": 34.25}},
             "cameras": {"current": {}, "attachment": {}}}
    quality = exploration._camera_quality(scene, 0, views)
    assert quality["required_snapshots"] == 2 and quality["fitted_snapshots"] == 1
    assert quality["units"][1]["status"] == "poor_fit"  # Numeric data wins over the label.
    del views["fits"]["attachment"]
    assert exploration._camera_quality(scene, 0, views)["units"][1]["status"] == "unavailable"


def test_selection_keeps_all_first_attempt_frontier_alternatives_for_repair_comparison():
    first = _selection_record("attempt-1:a", physical="a")
    alternate = _selection_record("attempt-1:b", physical="b")
    first["visual_review"]["visible_defects"] = [{"domain": "identity", "severity": "minor",
        "step_ids": ["current"], "instance_ids": ["part"], "description": "First typed issue."}]
    alternate["visual_review"]["visible_defects"] = [{"domain": "grouping", "severity": "minor",
        "step_ids": ["current"], "instance_ids": ["part"], "description": "Second typed issue."}]
    selected, receipt = exploration._select_candidates([first, alternate])
    assert receipt["status"] == "unresolved_alternatives"
    repaired = _selection_record("attempt-2:c", physical="c", rms=3., maximum=6.)
    choice, receipt = exploration._select_candidates([selected, repaired])
    assert choice["selection_id"] == "attempt-2:c"
    assert set(receipt["profiles"]) == {"attempt-1:a", "attempt-1:b", "attempt-2:c"}


def test_visibility_examples_allow_occluded_body_and_detached_workspace(harness):
    from guide2build.engine.delta import assemble_delta
    h = harness
    exploration.run_exploration(**h.args, max_panels=1)
    previous = h.cp["candidate"]
    prompt = next(item["prompt"] for item in h.provider.calls if item["key"].endswith("proposal"))
    proposal = synthetic_proposal(prompt, 0)
    delta = json.loads(proposal["delta_json"])
    delta["new_sections"] = []
    piece = delta["new_instances"][0]
    piece["instance_id"] = "new-detached"
    step = delta["new_steps"][0]
    step.update(step_id="detached-callout", main_step_number=2, substep_label="1", action="build_subassembly",
                assembly_group_id="detached", introduced_instance_ids=["new-detached"],
                active_instance_ids=["new-detached"], visible_instance_ids=["new-detached"],
                poses={"new-detached": {"position_ldu": [80, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]}})
    detached = assemble_delta(json.dumps(delta), h.job, SOURCE, 8, previous)
    assert detached.steps[-1].visible_instance_ids == ["new-detached"]
    # A following assembly snapshot includes occluded base, while highlighting
    # only the new piece. Delta inherits the base pose; no source visibility claim.
    step.update(step_id="assembly", substep_label=None, action="add_parts", assembly_group_id=None,
                visible_instance_ids=["synthetic-part-1", "new-detached"])
    assembly = assemble_delta(json.dumps(delta), h.job, SOURCE, 8, previous)
    assert assembly.steps[-1].active_instance_ids == ["new-detached"]
    assert set(assembly.steps[-1].poses) == {"synthetic-part-1", "new-detached"}
    step["visible_instance_ids"] = ["new-detached"]
    step["active_instance_ids"] = ["synthetic-part-1", "new-detached"]
    with pytest.raises(ValueError, match="New and active instances must be visible"):
        assemble_delta(json.dumps(delta), h.job, SOURCE, 8, previous)


def test_review_uncertainty_does_not_change_visible_agreement_and_selection_receipts_replay(harness, monkeypatch):
    h = harness
    original = h.provider.call
    def call(prompt, images, schema, evidence, check):
        response = original(prompt, images, schema, evidence, check)
        if evidence.parent.name.endswith("review"):
            judgement = response["reviews"][0]
            judgement.update(assembly_agrees=True, coverage_agrees=True, visible_defects=[],
                findings=[exploration.finding("ambiguity", "Hidden contact is not visible.", step_ids=["synthetic-step-1"])])
        return response
    monkeypatch.setattr(h.provider, "call", call)
    exploration.run_exploration(**h.args, max_panels=1)
    paths = list(h.directory.glob("exploration/instructions/0000/attempt-*/outcome.json"))
    before = {path: path.read_bytes() for path in paths}
    for path in paths:
        assert json.loads(path.read_text())["result"]["visual_agrees"]
    receipt = h.cp["instruction_results"][0]["selection"]
    assert receipt["status"] == "equivalent_tie" and len(receipt["frontier_ids"]) == 2
    calls = len(h.provider.calls)
    exploration.run_exploration(**h.args, max_panels=1)
    assert all(path.read_bytes() == value for path, value in before.items())
    assert all("instruction-0000" not in item["key"] for item in h.provider.calls[calls:])


def test_segmentation_unscorable_retains_source_camera_without_overview(harness, monkeypatch):
    from guide2build.engine import hypotheses, perception, rendering
    h = harness
    frame = _letterboxed_camera_frame()
    modes = []
    def fits(scene, previous, *args):
        steps = scene.steps[len((previous or {}).get("steps", [])):]
        return ({step.step_id: {"status": "fitted", "rms_pixels": 1., "max_error_pixels": 2.} for step in steps},
                {step.step_id: frame["input"] for step in steps})
    def render(scene_path, geometry, output, *, source_views, first_step, **kwargs):
        assert source_views  # Segmentation must not trigger an overview rerender.
        modes.append("source")
        scene = SceneV2.model_validate_json(scene_path.read_text())
        output.mkdir()
        camera_bytes = json.dumps(source_views, sort_keys=True, separators=(",", ":")).encode()
        (output / "source-views.json").write_bytes(camera_bytes)
        frames = []
        for number, step in enumerate(scene.steps[first_step-1:]):
            path = output / f"frame-{number}.png"
            Image.new("RGB", (128, 96), "grey").save(path)
            frames.append({"step_id": step.step_id, "screenshot": path.name,
                "png_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "camera_mode": "source_orthographic", "source_camera": frame})
        result = {"status": "rendered", "scene_sha256": digest(scene), "steps": frames,
                  "source_views_sha256": hashlib.sha256(camera_bytes).hexdigest()}
        exploration._write(output / "report.json", result)
        return result
    def unscorable(*args, **kwargs):
        assert kwargs["camera_registration"]["status"] == "registered"
        return {"status": "unscorable", "rank_eligible": False, "ranking_score": None,
                "reason": "Ambiguous foreground/background segmentation."}
    monkeypatch.setattr(hypotheses, "source_view_alternatives", fits)
    monkeypatch.setattr(rendering, "render_candidate", render)
    monkeypatch.setattr(perception, "compare_source_render_images", unscorable)
    exploration.run_exploration(**h.args)
    assert modes == ["source"] * 4
    assert not list(h.directory.rglob("comparison-fallback.json"))
    assert all(result["render_directory"].endswith("renders") for result in h.cp["instruction_results"])
    assert any("retained without an image score" in item["description"] for item in h.cp["provisional_findings"])


def test_selection_tie_and_typed_defect_reach_bounded_dependent_context():
    first = _selection_record("a", physical="one")
    second = _selection_record("b", physical="two")
    selected, receipt = exploration._select_candidates([first, second])
    assert receipt["status"] == "unresolved_alternatives"
    ambiguity = next(item for item in selected["findings"] if item["category"] == "selection_ambiguity")
    assert ambiguity["alternative_selection_ids"] == ["a", "b"]
    typed = {"category": "source_visible_defect", "domain": "identity", "origin": "agent_source_comparison",
             "description": "Wrong visible identity", "step_ids": ["current"], "instance_ids": ["part"]}
    later = [{"category": "aabb_overlap_candidate", "description": f"Later overlap {i}", "ordinal": i} for i in range(40)]
    context = exploration._prior_finding_context([typed, ambiguity, *later], [], None, 0, max_items=2)
    retained = next(item for item in context["findings"] if item.get("domain") == "identity")
    assert retained["origin"] == "agent_source_comparison"
    assert any(item.get("alternative_selection_ids") == ["a", "b"] for item in context["findings"])
    quality = exploration._quality_context(selected["selected_quality"])
    assert "review_observations" not in quality and len(json.dumps(quality)) < 4000


def test_unrenderable_attempts_retain_both_failure_findings():
    records = [{"candidate": None, "rendered": False, "findings": [exploration.finding("no_candidate", "Missing identity")]},
               {"candidate": None, "rendered": False, "findings": [exploration.finding("invalid_proposal", "Repair invalid visibility")]}]
    selected, receipt = exploration._select_candidates(records)
    assert receipt["status"] == "no_renderable_candidate"
    assert {item["category"] for item in selected["findings"]} == {"no_candidate", "invalid_proposal"}


@pytest.mark.parametrize("change", ["none", "outcome", "selected_scene", "nested_scene", "selection"])
def test_interrupted_trial_recovery_pins_outcome_and_binds_every_candidate(harness, change):
    h = harness
    h.job["config"]["max_panel_attempts"] = 1
    class Crash(BaseException):
        pass
    def save(stage, *args):
        h.save(stage, *args)
        if stage == "exploration_trial_recorded":
            raise Crash()
    h.args["save"] = save
    with pytest.raises(Crash):
        exploration.run_exploration(**h.args, max_panels=1)
    state = h.cp["exploration_instructions"]["0"]
    path = next(h.directory.glob("exploration/instructions/0000/attempt-*/outcome.json"))
    assert state["trial_sha256"]["attempt-1"] == hashlib.sha256(path.read_bytes()).hexdigest()
    outcome = json.loads(path.read_text())
    before_calls = len(h.provider.calls)
    if change != "none":
        if change == "selection":
            outcome["result"]["selection"]["status"] = "forged"
        else:
            record = outcome["result"]["selection_candidates"][0] if change == "nested_scene" else outcome["result"]
            record["candidate"]["steps"][-1]["poses"]["synthetic-part-1"]["position_ldu"][0] = 777
        path.write_text(json.dumps(outcome))
        if change != "outcome":
            # Independently exercise scene/selection binding even if an outer
            # receipt pointer is rehashed incorrectly by a caller.
            state["trial_sha256"]["attempt-1"] = hashlib.sha256(path.read_bytes()).hexdigest()
    h.args["save"] = h.save
    if change == "none":
        exploration.run_exploration(**h.args, max_panels=1)
        assert h.cp["processed_panels"] == 1
    else:
        expected = "outcome changed" if change == "outcome" else "selection differs" if change == "selection" else "retained scene"
        with pytest.raises(ValueError, match=expected):
            exploration.run_exploration(**h.args, max_panels=1)
        assert not h.cp.get("candidate")
    assert len(h.provider.calls) == before_calls


def test_crash_after_outcome_write_before_checkpoint_pin_stops_without_promotion(harness, monkeypatch):
    h = harness
    h.job["config"]["max_panel_attempts"] = 1
    original_write = exploration._write
    class Crash(BaseException):
        pass
    def write(path, value):
        original_write(path, value)
        if path.name == "outcome.json":
            raise Crash()
    monkeypatch.setattr(exploration, "_write", write)
    with pytest.raises(Crash):
        exploration.run_exploration(**h.args, max_panels=1)
    state = h.cp["exploration_instructions"]["0"]
    assert not state.get("trial_sha256")
    path = next(h.directory.glob("exploration/instructions/0000/attempt-*/outcome.json"))
    retained = path.read_bytes()
    before_calls = len(h.provider.calls)
    monkeypatch.setattr(exploration, "_write", original_write)
    with pytest.raises(ValueError, match="Unpinned exploration trial"):
        exploration.run_exploration(**h.args, max_panels=1)
    assert len(h.provider.calls) == before_calls
    assert not h.cp.get("candidate") and path.read_bytes() == retained


@pytest.mark.parametrize("filename", ["repair-feedback.json", "review-feedback.json", "source-regions.json"])
def test_new_accuracy_receipts_are_pinned_on_resume_before_more_calls(harness, filename):
    h = harness
    exploration.run_exploration(**h.args, max_panels=1)
    path = next(h.directory.rglob(filename))
    original = path.read_bytes()
    receipt = json.loads(original)
    receipt["forged"] = "The old evidence must not be enrolled as a new result."
    path.write_text(json.dumps(receipt))
    calls = len(h.provider.calls)
    scene = deepcopy(h.cp["candidate"])
    with pytest.raises(ValueError, match="changed|differs"):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == calls and h.cp["candidate"] == scene


def test_semantic_overview_retained_and_later_source_event_still_runs(harness, monkeypatch):
    h = harness
    original = h.provider.call
    def call(prompt, images, schema, evidence, check):
        reply = original(prompt, images, schema, evidence, check)
        key = evidence.parent.name
        if key == "index-0001":
            reply["panels"][0].update(region_id="overview", role="overview", kind="attachment", number=None,
                event_key=None, evidence="Synthetic full assembly overview, no building operation.")
        if key == "index-0002":
            reply["panels"] = [{"section": "synthetic-main", "number": 2, "label": "2",
                "bbox": [0, 0, 1, 1], "kind": "main", "region_id": "later", "role": "build_event",
                "event_key": "main-2", "associated_event": None, "semantic_status": "explicit",
                "evidence": "Synthetic numbered building operation after the overview.", "uncertainty": []}]
        return reply
    monkeypatch.setattr(h.provider, "call", call)
    exploration.run_exploration(**h.args)
    assert h.cp["processed_panels"] == h.cp["reconstructed_source_events"] == 2
    regions = json.loads((h.directory / "source-regions.json").read_text())
    assert len(regions["retained_regions"]) == 3
    assert len(regions["reconstruction_panels"]) == 2
    assert h.cp["candidate"]["steps"][-1]["source"]["page_index"] == 2
    later = next(item for item in h.provider.calls if item["key"] == "instruction-0001-attempt-1-proposal")
    context = json.JSONDecoder().raw_decode(later["prompt"][later["prompt"].index('{"set_number"'):])[0]
    assert context["page_index"] == 2


def test_orphan_callout_is_processed_and_missing_snapshot_is_exposed(harness, monkeypatch):
    h = harness
    original = h.provider.call
    def call(prompt, images, schema, evidence, check):
        reply = original(prompt, images, schema, evidence, check)
        if evidence.parent.name == "index-0001":
            reply["panels"][0].update(kind="substep", number=1, label="1", event_key="orphan-callout",
                evidence="Synthetic numbered callout whose parent is not identified.")
        return reply
    monkeypatch.setattr(h.provider, "call", call)
    exploration.run_exploration(**h.args)
    assert h.cp["processed_panels"] == h.cp["processed_source_events"] == 2
    assert h.cp["reconstructed_source_events"] == 1
    assert any(item["category"] == "source_panel_uncovered" for item in h.cp["source_index_findings"])
    following = next(item for item in h.provider.calls if item["key"] == "instruction-0001-attempt-1-proposal")
    context = json.JSONDecoder().raw_decode(following["prompt"][following["prompt"].index('{"set_number"'):])[0]
    assert context["panel"]["kind"] == "substep"


def test_index_response_wrong_page_binding_is_hard_before_proposing(harness, monkeypatch):
    h = harness
    original = h.provider.call
    def call(prompt, images, schema, evidence, check):
        reply = original(prompt, images, schema, evidence, check)
        if evidence.parent.name == "index-0000":
            reply["page_sha256"] = "b" * 64
        return reply
    monkeypatch.setattr(h.provider, "call", call)
    with pytest.raises(ValueError, match="exact verified page"):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == 1 and not h.cp.get("candidate")


def test_coverage_cannot_reuse_snapshot_or_count_callout_for_wrong_parent():
    panel = {"section": "main", "number": 1, "label": "1", "kind": "main", "bbox": [0, 0, 1, 1]}
    step = {"step_id": "one", "section_id": "main", "main_step_number": 1, "substep_label": None,
            "source": {"source_sha256": SOURCE, "page_index": 0, "bbox": [0, 0, 1, 1]}}
    missing = exploration._source_coverage_findings([{"panels": [panel, deepcopy(panel)]}], {"steps": [step]}, SOURCE)
    assert len(missing) == 1
    callout = {**panel, "kind": "substep", "parent_main_step_number": 2}
    assert exploration._source_coverage_findings([{"panels": [callout]}], {"steps": [{**step, "substep_label": "1"}]}, SOURCE)
    assert exploration._source_coverage_findings([{"panels": [panel]}], {"steps": [{**step, "substep_label": "1"}]}, SOURCE)
    assert exploration._source_coverage_findings([{"panels": [panel]}], {"steps": [{**step, "source": {**step["source"], "source_sha256": "b" * 64}}]}, SOURCE)
    assert not exploration._source_coverage_findings([{"panels": [callout]}], {"steps": [{**step, "main_step_number": 2, "substep_label": "1"}]}, SOURCE)
    attachment = {**panel, "kind": "attachment", "number": None, "parent_main_step_number": 3}
    attached = {**step, "action": "attach_subassembly", "main_step_number": 3}
    assert not exploration._source_coverage_findings([{"panels": [attachment]}], {"steps": [attached]}, SOURCE)
    assert not exploration._source_coverage_findings([{"panels": [attachment]}], {"steps": [{**attached, "substep_label": "Attach completed module"}]}, SOURCE)
    assert exploration._source_coverage_findings([{"panels": [attachment]}], {"steps": [{**attached, "main_step_number": 2}]}, SOURCE)
    assert exploration._source_coverage_findings([{"panels": [attachment]}], {"steps": [{**attached, "action": "add_parts"}]}, SOURCE)


@pytest.mark.parametrize("change", ["none", "index", "failed_index"])
def test_partial_index_resume_binds_checkpoint_to_completed_call(harness, monkeypatch, change):
    h = harness
    class Crash(BaseException):
        pass
    if change == "failed_index":
        original = h.provider.call
        def call(prompt, images, schema, evidence, check):
            reply = original(prompt, images, schema, evidence, check)
            return {"invalid": "synthetic schema failure"} if evidence.parent.name == "index-0000" else reply
        monkeypatch.setattr(h.provider, "call", call)
    def save(stage, *args):
        h.save(stage, *args)
        if stage == "exploration_indexing":
            raise Crash()
    h.args["save"] = save
    with pytest.raises(Crash):
        exploration.run_exploration(**h.args)
    assert len(h.cp["page_indexes"]) == len(h.provider.calls) == 1
    if change == "index":
        h.cp["page_indexes"][0]["panels"] = []
    if change == "failed_index":
        h.cp["page_indexes"][0]["uncertainty"] = []
    h.args["save"] = h.save
    if change == "none":
        exploration.run_exploration(**h.args)
        assert h.cp["processed_panels"] == 2
        assert sum(item["key"] == "index-0000" for item in h.provider.calls) == 1
    else:
        with pytest.raises(ValueError, match="projection differs"):
            exploration.run_exploration(**h.args)
        assert len(h.provider.calls) == 1 and not h.cp.get("candidate")


@pytest.mark.parametrize("rebind_scene_hash", [False, True])
def test_promoted_scene_is_bound_to_authenticated_selected_trial(harness, rebind_scene_hash):
    h = harness
    exploration.run_exploration(**h.args, max_panels=1)
    result = deepcopy(h.cp["instruction_results"][0])
    path = h.directory / result["receipt_path"]
    receipt = json.loads(path.read_text())
    receipt["candidate"]["steps"][0]["poses"]["synthetic-part-1"]["position_ldu"][0] += 10
    if rebind_scene_hash:
        receipt["result"]["provisional_scene_sha256"] = digest(receipt["candidate"])
        result["provisional_scene_sha256"] = receipt["result"]["provisional_scene_sha256"]
    path.write_text(json.dumps(receipt))
    result["receipt_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    calls = len(h.provider.calls)
    with pytest.raises(ValueError, match="promoted"):
        exploration._recover_result(h.directory, result, None, SOURCE, exploration._page_bindings(h.pages, 8))
    assert len(h.provider.calls) == calls


def test_long_soft_index_failure_continues_and_replays_with_original_receipt(harness, monkeypatch):
    h = harness
    original = h.provider.call
    def call(prompt, images, schema, evidence, check):
        if evidence.parent.name == "index-0000":
            h.provider.calls.append({"key": "index-0000", "prompt": prompt, "images": images})
            raise ProviderFailure("invalid_output", "x" * 3000)
        return original(prompt, images, schema, evidence, check)
    monkeypatch.setattr(h.provider, "call", call)
    exploration.run_exploration(**h.args)
    assert len(h.cp["page_indexes"]) == 8 and h.cp["processed_panels"] == 1
    assert len(h.cp["page_indexes"][0]["uncertainty"][0]) == 2000
    receipt = h.directory / "exploration/calls/index-0000/receipt.json"
    assert len(json.loads(receipt.read_text())["error"]["message"]) == 3000
    calls = len(h.provider.calls)
    exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == calls
