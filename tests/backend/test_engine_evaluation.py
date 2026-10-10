"""Scoring, invocation accounting and private comparison artifacts on synthetic data."""
import copy
import hashlib
import json

import pytest
from PIL import Image

from guide2build.catalog import find_guide
from guide2build.core.models import SceneManifest
from guide2build.engine.evaluation import EvaluationReference, evaluate_job, score_scene, summarize_job_calls
from guide2build.releases.models import adapt_v1, digest
from test_engine_corrections import correction_request, seed_job, write_json


@pytest.fixture
def scoring_scene(scene_data):
    """The seed job's exact synthetic SceneV2, without unrelated durable assets."""
    source_hash = hashlib.sha256(b"%PDF-1.4\nOriginal synthetic test source; not LEGO evidence.\n").hexdigest()
    value = copy.deepcopy(scene_data)
    value.update(set_number="30669", guide_id="alt-02", revision="base", source_sha256=source_hash)
    for item in value["instances"] + value["steps"]:
        item["source"]["source_sha256"] = source_hash
    for part in value["instances"]:
        part.update(part_id="synthetic", origin="vision_proposal")
    guide = find_guide("30669", "alt-02")
    return adapt_v1(SceneManifest.model_validate(value), guide["pdf_url"], guide["expected_page_count"])


def reference(scene, **values):
    return EvaluationReference.model_validate({"schema_version": "1.0",
        "artifact_kind": "source_reviewed_annotations", "set_number": scene.set_number,
        "guide_id": scene.guide_id, "source_sha256": scene.source_sha256,
        "actor": "agent", "reason": "Original synthetic source annotations", **values})


def test_source_scores_have_independent_denominators_and_unknowns(scoring_scene):
    scene = scoring_scene
    source = scene.steps[0].source.model_dump(mode="json")
    ref = reference(scene, instances=[{"instance_id": "a", "evidence": source, "part_id": "synthetic",
        "color_code": "4", "introduced_main_step": 1, "grouping_known": True, "group_id": None,
        "poses": [{"step_id": "s1", "pose": scene.steps[0].poses["a"].model_dump(mode="json")}]},
        {"instance_id": "missing", "evidence": source, "part_id": "synthetic"}],
        quantities=[{"main_step_number": 1, "count": 1, "evidence": source},
                    {"main_step_number": 2, "count": 2, "evidence": source}],
        expected_main_steps=[1, 2, 3, 4], expected_microsteps=4)
    metrics = score_scene(scene, ref)
    assert (metrics["part_identity"]["numerator"], metrics["part_identity"]["denominator"],
            metrics["part_identity"]["unknown"]) == (1, 2, 1)
    assert metrics["color"]["numerator"] == 0 and metrics["color"]["denominator"] == 1
    assert metrics["grouping"]["numerator"] == metrics["grouping"]["denominator"] == 1
    assert metrics["pose"]["numerator"] == 1 and metrics["pose"]["unknown"] == 4
    assert (metrics["quantity"]["numerator"], metrics["quantity"]["denominator"], metrics["quantity"]["unknown"]) == (1, 2, 2)
    absent = score_scene(scene)
    assert all(value["denominator"] == 0 and value["status"] == "unscorable" for value in absent.values())


def test_instruction_identity_fails_wrong_design_even_when_total_quantity_matches(scoring_scene):
    scene = scoring_scene
    evidence = scene.steps[0].source.model_dump(mode="json")
    ref = reference(scene, quantities=[
        {"main_step_number": 1, "count": 1, "evidence": evidence},
        {"main_step_number": 1, "part_id": "other-synthetic-design", "count": 1, "evidence": evidence}])
    scores = score_scene(scene, ref)
    assert scores["quantity"]["numerator"] == 1  # The total is right; its design-specific row fails.
    assert scores["part_identity"]["denominator"] == 0  # No engine instance-ID ground truth was supplied.
    identity = scores["part_identity_by_instruction"]
    assert (identity["numerator"], identity["denominator"], identity["unknown"]) == (0, 1, 1)
    assert identity["mismatches"][0]["actual"] == 0
    assert scores["color_by_instruction"]["denominator"] == 0


def test_instruction_color_fails_wrong_color_without_failing_correct_identity(scoring_scene):
    scene = scoring_scene
    evidence = scene.steps[0].source.model_dump(mode="json")
    ref = reference(scene, quantities=[
        {"main_step_number": 1, "part_id": "synthetic", "color_code": "4", "count": 1, "evidence": evidence}])
    scores = score_scene(scene, ref)
    assert scores["part_identity_by_instruction"]["numerator"] == 1
    assert scores["part_identity_by_instruction"]["denominator"] == 1
    color = scores["color_by_instruction"]
    assert (color["numerator"], color["denominator"], color["unknown"]) == (0, 1, 1)
    assert color["mismatches"][0]["color_code"] == "4" and color["mismatches"][0]["actual"] == 0
    assert scores["color"]["status"] == "unscorable"


def test_instruction_scores_ignore_totals_and_do_not_reuse_pieces_across_color_rows(scoring_scene):
    scene = scoring_scene
    # Two unique same-design white pieces are introduced within one main instruction.
    scene.steps[1].main_step_number = 1
    evidence = scene.steps[0].source.model_dump(mode="json")
    ref = reference(scene, quantities=[
        {"main_step_number": 1, "count": 2, "evidence": evidence},
        {"main_step_number": 1, "part_id": "synthetic", "color_code": "15", "count": 1, "evidence": evidence},
        {"main_step_number": 1, "part_id": "synthetic", "color_code": "4", "count": 1, "evidence": evidence}])
    scores = score_scene(scene, ref)
    identity, color = scores["part_identity_by_instruction"], scores["color_by_instruction"]
    assert (identity["numerator"], identity["denominator"], identity["unknown"]) == (2, 2, 0)
    assert identity["annotation_groups"] == 1
    assert (color["numerator"], color["denominator"], color["unknown"]) == (1, 2, 0)
    assert color["excess_matching_pieces"] == 1
    assert {item["color_code"]: item["actual"] for item in color["mismatches"]} == {"4": 0, "15": 2}


def test_instruction_unknown_colors_are_not_inferred_from_identity_annotations(scoring_scene):
    scene = scoring_scene
    evidence = scene.steps[0].source.model_dump(mode="json")
    ref = reference(scene, quantities=[
        {"main_step_number": 1, "part_id": "synthetic", "count": 1, "evidence": evidence},
        {"main_step_number": 2, "part_id": "synthetic", "color_code": "15", "count": 1, "evidence": evidence}])
    scores = score_scene(scene, ref)
    assert scores["part_identity_by_instruction"]["denominator"] == 2
    assert scores["color_by_instruction"]["numerator"] == scores["color_by_instruction"]["denominator"] == 1
    assert scores["color_by_instruction"]["unknown"] == 1


def test_overlapping_wildcard_and_specific_color_annotations_are_rejected(scoring_scene):
    scene = scoring_scene
    evidence = scene.steps[0].source.model_dump(mode="json")
    with pytest.raises(ValueError, match="Overlapping part quantity annotations"):
        reference(scene, quantities=[
            {"main_step_number": 1, "part_id": "synthetic", "count": 2, "evidence": evidence},
            {"main_step_number": 1, "part_id": "synthetic", "color_code": "15", "count": 1, "evidence": evidence}])


def test_counts_actual_calls_once_and_includes_failed_process_receipts(tmp_path):
    strict = tmp_path / "calls/construct/1"
    write_json(strict / "invocation.json", {"elapsed_seconds": 2, "returncode": 0,
        "reported_usage": {"input_tokens": 80, "output_tokens": 10}})
    write_json(strict / "process-result.json", {"elapsed_seconds": 3, "returncode": 0,
        "structured_result_present": True})
    (strict / "events.jsonl").write_text(json.dumps({"type": "turn.completed",
        "usage": {"input_tokens": 80, "output_tokens": 10}}) + "\n")
    alpha = tmp_path / "alpha-proposals/abc/provider"
    write_json(alpha / "process-result.json", {"elapsed_seconds": 7, "returncode": -15,
        "structured_result_present": False})
    explore = tmp_path / "exploration/calls/step-2/1"
    write_json(explore / "invocation.json", {"elapsed_seconds": 5, "returncode": 0,
        "reported_usage": {"input_tokens": 20, "output_tokens": 5}})
    result = summarize_job_calls(tmp_path)
    assert result["model_invocations"] == 3
    assert result["model_elapsed_seconds"] == 14
    assert result["reported_usage"] == {"input_tokens": 100, "output_tokens": 15}
    assert result["process_failures"] == result["processes_without_structured_result"] == 1
    assert result["usage_reporting"]["calls_without_usage"] == 1


def test_alternative_archive_counts_distinct_full_beam_and_actual_rendered_pixels(tmp_path, scene_data):
    from guide2build.engine.evaluation import _alternatives
    _, _, scene, directory = seed_job(tmp_path, scene_data)
    trial = directory / "exploration/instructions/0000/attempt-1"
    beam = []
    for index in range(8):
        candidate = scene.model_dump(mode="json")
        candidate["steps"][-1]["poses"]["b"]["position_ldu"][0] += index
        beam.append({"hypothesis_id": f"connector-{index}", "scene": candidate})
    fallback = dict(beam[0], hypothesis_id="raw-same-scene")
    write_json(trial / "hypotheses.json", {"candidates": [beam[0], beam[1], fallback], "retained_beam": beam})
    render = trial / "candidate-0/renders"
    render.mkdir(parents=True)
    picture = render / "step.png"
    Image.new("RGB", (16, 16), "blue").save(picture)
    write_json(render / "report.json", {"status": "rendered", "scene_sha256": digest(beam[0]["scene"]), "steps": [
        {"step_id": "s3", "screenshot": picture.name, "png_sha256": hashlib.sha256(picture.read_bytes()).hexdigest()}]})
    result = _alternatives(directory, [{"ordinal": 0, "render_directory": str(render.relative_to(directory)),
        "provisional_scene_sha256": digest(beam[0]["scene"])}])
    assert result["retained_candidate_alternatives"] == 7
    row = result["instructions"][0]
    assert row["archived_distinct_candidates"] == 8
    assert row["render_selected_distinct_candidates"] == 2
    assert row["rendered_distinct_candidates"] == 1
    assert row["unrendered_distinct_candidates"] == 7
    assert row["count_status"] == "complete"
    picture.write_bytes(b"tampered pixels")
    with pytest.raises(ValueError, match="Render image hash"):
        _alternatives(directory, [{"ordinal": 0, "render_directory": str(render.relative_to(directory)),
            "provisional_scene_sha256": digest(beam[0]["scene"])}])


def test_abbreviated_legacy_beam_does_not_claim_exact_distinct_alternative_count(tmp_path, scene_data):
    from guide2build.engine.evaluation import _alternatives
    _, _, scene, directory = seed_job(tmp_path, scene_data)
    trial = directory / "exploration/instructions/0000/attempt-1"
    write_json(trial / "hypotheses.json", {"candidates": [{"scene": scene.model_dump(mode="json")}],
        "retained_beam": [{"hypothesis_id": "abbreviated-one", "scene_sha256": digest(scene)}]})
    result = _alternatives(directory, [{"ordinal": 0,
        "render_directory": str((trial / "candidate-0/renders").relative_to(directory)),
        "provisional_scene_sha256": digest(scene)}])
    assert result["retained_candidate_alternatives"] is None
    assert result["retained_alternatives_lower_bound"] == 0
    assert result["instructions"][0]["abbreviated_records_with_unknown_distinctness"] == 1
    assert result["instructions"][0]["count_status"] == "lower_bound"


def test_diagnostic_counts_exclude_repeated_instruction_review_records(tmp_path, scene_data, monkeypatch):
    from guide2build.engine import evaluation
    store, identity, _, _ = seed_job(tmp_path, scene_data)
    store.claim("repeated-review", job_id=identity)
    checkpoint = store.get(identity)["checkpoint"]
    checkpoint["instruction_results"] = [{"ordinal": ordinal, "step_ids": [f"s{ordinal+1}"],
        "reconstructed": True, "findings": [{"code": "aabb_overlap_candidate", "message": "Repeated inherited overlap"}]}
        for ordinal in range(3)]
    store.checkpoint(identity, "repeated-review", checkpoint, "paused")
    monkeypatch.setattr(evaluation, "diagnose", lambda *_: {"checks": {"narrow_phase": "not_run"},
        "findings_truncated": True, "findings": [
            {"code": "aabb_overlap_candidate", "step_id": "s3", "message": "Diagnostic overlap"},
            {"code": "unsupported_connector_geometry", "step_id": None, "message": "Scoped coverage unknown"}]})
    report = evaluate_job(store, identity)
    assert report["aggregate_finding_count"] == 5
    assert report["finding_counts"]["aabb_overlap_candidate"] == 4
    assert report["diagnostic_finding_counts"] == {"aabb_overlap_candidate": 1, "unsupported_connector_geometry": 1}
    assert report["diagnostic_finding_counts_basis"] == "per-snapshot scoped diagnostic observations"
    assert report["diagnostic_findings_truncated"] is True
    assert report["final_assembly_diagnostic_finding_counts"] == {"aabb_overlap_candidate": 1}
    assert report["diagnostic_global_finding_counts"] == {"unsupported_connector_geometry": 1}


def test_evaluate_separates_progress_from_accuracy_and_escapes_html(tmp_path, scene_data):
    def unsafe_label(value):
        value["steps"][0]["step_id"] = '<script>alert(1)</script>'
        return value
    store, identity, scene, directory = seed_job(tmp_path, scene_data, transform=unsafe_label)
    store.claim("seed-progress", job_id=identity)
    checkpoint = store.get(identity)["checkpoint"]
    checkpoint.update(processed_panels=4, total_panels=4, instruction_results=[{"ordinal": 4,
        "step_ids": [], "reconstructed": False, "findings": ["No renderable proposal"]}])
    store.checkpoint(identity, "seed-progress", checkpoint, "paused")
    pages = tmp_path / "public/pages" / scene.source_sha256
    pages.mkdir(parents=True)
    picture = pages / "page-000.png"
    Image.new("RGB", (64, 64), "white").save(picture)
    write_json(pages / "pages.json", [{"page_index": 0, "file": picture.name,
        "sha256": hashlib.sha256(picture.read_bytes()).hexdigest()}])
    renders = directory / "renders"
    renders.mkdir()
    image = renders / "step.png"
    Image.new("RGB", (64, 64), "blue").save(image)
    write_json(renders / "report.json", {"status": "rendered", "scene_sha256": digest(scene), "steps": [
        {"step_id": scene.steps[0].step_id, "screenshot": image.name,
         "png_sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "camera_mode": "overview_unaligned"}]})
    before = store.get(identity)
    report = evaluate_job(store, identity, output=tmp_path / "evidence/report")
    assert store.get(identity) == before
    assert report["coverage"]["processed_instructions"] == 4
    assert report["coverage"]["reconstructed_instructions"] == 3
    assert report["coverage"]["unreconstructed_processed_instructions"] == 1
    assert report["source_scores"]["part_identity"]["denominator"] == 0
    document = (tmp_path / "evidence/report/comparison.html").read_text()
    assert '<script>alert(1)</script>' not in document
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in document
    assert "Not rendered for this revision" in document and "Overview camera — source alignment unavailable" in document
    assert (tmp_path / "evidence/report/source-00001.png").is_file()
    assert (tmp_path / "evidence/report/after-00001.png").is_file()
    assert report["human_review"] == "not_established" and report["physical_build"] == "not_run"


@pytest.mark.parametrize("durable_reconstructed_count", [False, True])
@pytest.mark.parametrize("has_gap", [False, True])
def test_exploration_counts_attachment_panels_and_keeps_unresolved_source_cards(
        tmp_path, scene_data, durable_reconstructed_count, has_gap):
    from guide2build.releases.models import SceneV2
    store, identity, scene, directory = seed_job(tmp_path, scene_data,
        config={"model": "test", "revision": "base", "execution_policy": "explore"})
    raw = scene.model_dump(mode="json")
    raw["steps"][2]["main_step_number"] = None  # An unnumbered attach still reconstructs one panel.
    scene = SceneV2.model_validate(raw)
    write_json(directory / "scene.json", raw)
    panels = [{"section": "main", "number": number, "label": str(number),
        "bbox": [0, 0, 1, 1], "kind": "main"} for number in (1, 2)]
    if has_gap:
        panels.append({"section": "main", "number": 3, "label": "Unreadable source step",
            "bbox": [.25, .5, .75, .75], "kind": "main"})
    panels.append({"section": "main", "number": None, "label": "Attach assembly",
        "bbox": [0, 0, 1, 1], "kind": "attachment"})
    results = [{"ordinal": ordinal, "page_index": 0, "panel": panel,
        "step_ids": [] if panel["number"] == 3 else [f's{panel["number"] or 3}'],
        "reconstructed": panel["number"] != 3,
        "findings": ["Gap-specific <ambiguous> source finding"] if panel["number"] == 3 else []}
        for ordinal, panel in enumerate(panels)]
    store.claim("exploration-panel-coverage", job_id=identity)
    checkpoint = store.get(identity)["checkpoint"]
    checkpoint.update(candidate=raw, processed_panels=len(panels), completed_panels=3,
        instruction_results=results, total_panels=len(panels))
    checkpoint["page_indexes"][0]["panels"] = panels
    if durable_reconstructed_count:
        checkpoint["reconstructed_panels"] = 3
    store.checkpoint(identity, "exploration-panel-coverage", checkpoint, "paused")
    page = tmp_path / "public/pages" / scene.source_sha256 / "page-000.png"
    page.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), "white").save(page)
    write_json(page.parent / "pages.json", [{"page_index": 0, "file": page.name,
        "sha256": hashlib.sha256(page.read_bytes()).hexdigest()}])
    source_reference = tmp_path / "source-annotations.json"
    write_json(source_reference, reference(scene,
        expected_main_steps=[1, 2, 3] if has_gap else [1, 2]).model_dump(mode="json"))
    before_job, before_scene = store.get(identity), (directory / "scene.json").read_bytes()
    report = evaluate_job(store, identity, reference_path=source_reference)
    assert store.get(identity) == before_job and (directory / "scene.json").read_bytes() == before_scene
    coverage = report["coverage"]
    assert coverage["processed_instructions"] == len(panels)
    assert coverage["reconstructed_instructions"] == 3
    assert coverage["reconstructed_main_steps"] == 2
    assert coverage["reconstructed_microsteps"] == 3
    assert coverage["expected_instructions"] == len(panels)
    assert coverage["expected_main_steps"] == 2 + has_gap
    assert coverage["unreconstructed_processed_instructions"] == int(has_gap)
    assert coverage["main_step_coverage"]["missing_numbers"] == ([3] if has_gap else [])
    assert coverage["reconstructed_count_basis"] == (
        "durable_instruction_checkpoint" if durable_reconstructed_count else "durable_instruction_results")
    cards = report["instruction_comparisons"]
    assert [card["step_id"] for card in cards] == (["s1", "s2", "unresolved-3", "s3"] if has_gap else ["s1", "s2", "s3"])
    assert len(cards) == len(panels)
    if has_gap:
        assert cards[2]["instruction_ordinal"] == 2 and cards[2]["reconstructed"] is False
        assert cards[2]["before"] is None and cards[2]["after"] is None
        from pathlib import Path
        output = Path(report["artifacts"]["comparison_html"]).parent
        with Image.open(output / cards[2]["source"]["file"]) as crop:
            assert crop.size == (32, 16)
        document = (output / "comparison.html").read_text()
        assert "Unresolved instruction — no reconstructed snapshot" in document
        assert "Gap-specific &lt;ambiguous&gt; source finding" in document


def test_baseline_comparison_does_not_create_ground_truth_and_reports_defects(tmp_path, scene_data):
    store, identity, scene, _ = seed_job(tmp_path, scene_data)
    baseline = copy.deepcopy(scene.model_dump(mode="json"))
    baseline["revision"] = "prior"
    baseline["steps"][-1]["poses"]["b"] = copy.deepcopy(baseline["steps"][-1]["poses"]["a"])
    path = tmp_path / "baseline/scene.json"
    write_json(path, baseline)
    report = evaluate_job(store, identity, baseline_path=path, output=tmp_path / "evidence/baseline-comparison")
    assert report["baseline_comparison"]["before_finding_counts"]["exact_coincident_geometry"] >= 1
    assert report["source_scores"]["pose"]["denominator"] == 0
    assert report["baseline_comparison"]["changed_steps"][0]["instance_ids"] == ["b"]


def test_reference_source_and_private_output_safety(tmp_path, scene_data):
    store, identity, scene, _ = seed_job(tmp_path, scene_data)
    value = reference(scene).model_dump(mode="json")
    value["source_sha256"] = "0" * 64
    path = tmp_path / "reference.json"
    write_json(path, value)
    with pytest.raises(ValueError, match="different guide or source"):
        evaluate_job(store, identity, reference_path=path)
    with pytest.raises(ValueError, match="private"):
        evaluate_job(store, identity, output=tmp_path / "public/unsafe-report")


def test_tampered_source_or_render_never_enters_comparison(tmp_path, scene_data):
    store, identity, scene, directory = seed_job(tmp_path, scene_data)
    renders = directory / "renders"
    renders.mkdir()
    (renders / "fake.png").write_bytes(b"tampered")
    write_json(renders / "report.json", {"status": "rendered", "scene_sha256": digest(scene), "steps": [
        {"step_id": "s1", "screenshot": "fake.png", "png_sha256": "0" * 64}]})
    with pytest.raises(ValueError, match="Render image hash"):
        evaluate_job(store, identity)


def test_all_unresolved_run_is_still_evaluable_without_fabricating_scene(tmp_path, scene_data):
    store, identity, _, directory = seed_job(tmp_path, scene_data)
    store.claim("no-scene", job_id=identity)
    checkpoint = store.get(identity)["checkpoint"]
    checkpoint.pop("candidate")
    checkpoint["processed_panels"] = 3
    checkpoint["instruction_results"] = [{"ordinal": ordinal, "page_index": 0, "panel": panel,
        "step_ids": [], "reconstructed": False, "findings": ["Synthetic ambiguous instruction"]}
        for ordinal, panel in enumerate(checkpoint["page_indexes"][0]["panels"])]
    store.checkpoint(identity, "no-scene", checkpoint, "paused")
    (directory / "scene.json").unlink()
    report = evaluate_job(store, identity)
    assert report["scene_sha256"] is None
    assert report["coverage"]["processed_instructions"] == 3
    assert report["coverage"]["reconstructed_instructions"] == 0
    assert len(report["instruction_comparisons"]) == 3
    assert all(item["after"] is None for item in report["instruction_comparisons"])


@pytest.mark.parametrize("ambiguous", [False, True])
def test_before_images_match_only_unique_source_instruction_when_ids_differ(tmp_path, scene_data, ambiguous):
    store, identity, scene, _ = seed_job(tmp_path, scene_data)
    before = copy.deepcopy(scene.model_dump(mode="json"))
    for step in before["steps"]:
        step["step_id"] = "before-" + step["step_id"]
    if ambiguous:
        duplicate = copy.deepcopy(before["steps"][1])
        duplicate.update(step_id="ambiguous-callout", introduced_instance_ids=[])
        before["steps"].insert(2, duplicate)
    baseline = tmp_path / "baseline/scene.json"
    write_json(baseline, before)
    image = baseline.parent / "renders/before.png"
    image.parent.mkdir()
    Image.new("RGB", (64, 64), "yellow").save(image)
    write_json(image.parent / "report.json", {"status": "rendered", "scene_sha256": digest(before), "steps": [
        {"step_id": "before-s2", "screenshot": image.name,
         "png_sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "camera_mode": "perspective"}]})
    report = evaluate_job(store, identity, baseline_path=baseline)
    compared = report["instruction_comparisons"][1]["before"]
    if ambiguous:
        assert compared is None
    else:
        assert compared["match_basis"] == "unique_source_page_main_substep_action"


@pytest.mark.parametrize("fit_status", ["fitted", "poor_fit"])
def test_landmark_correction_evaluation_refits_and_renders_without_changing_poses(tmp_path, scene_data, monkeypatch, fit_status):
    from guide2build.engine import connectors, rendering, source_view
    from guide2build.engine.corrections import fork_correction
    from guide2build.releases.models import SceneV2
    store, identity, scene, directory = seed_job(tmp_path, scene_data)
    monkeypatch.setattr(connectors, "world_landmark", lambda *args: [1, 2, 3])
    observation = {"step_id": "s2", "landmarks": [{"instance_id": "b", "landmark_id": "synthetic-corner",
                    "image_uv": [.4, .6]}], "view_family": "unconstrained"}
    request = correction_request(tmp_path, scene, [{"op": "landmark", "reason": "Synthetic camera-only edit",
        "evidence": scene.steps[1].source.model_dump(mode="json"), "observation": observation}])
    child = fork_correction(store, identity, request, "landmark-r1")
    page = tmp_path / "public/pages" / scene.source_sha256 / "page-000.png"
    page.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), "white").save(page)
    write_json(page.parent / "pages.json", [{"page_index": 0, "file": page.name,
        "sha256": hashlib.sha256(page.read_bytes()).hexdigest()}])
    camera = {"projection": "orthographic", "right": [1, 0, 0], "up": [0, 1, 0], "target_ldu": [0, 0, 0],
              "vertical_span_ldu": 50, "image_size": [64, 64]}
    seen = []
    def fit(world, uv, size, **kwargs):
        assert world == [[1, 2, 3]] and uv == [(0.4, 0.6)] and size == (64, 64)
        return {"status": fit_status, "camera": camera if fit_status == "fitted" else None}
    def render(path, geometry, output, **kwargs):
        current = SceneV2.model_validate_json(path.read_text())
        seen.append(kwargs)
        output.mkdir()
        records = []
        for step in current.steps[kwargs["first_step"]-1:]:
            picture = output / (step.step_id + ".png")
            Image.new("RGB", (64, 64), "blue").save(picture)
            aligned = (kwargs["source_views"] or {}).get(step.step_id)
            records.append({"step_id": step.step_id, "screenshot": picture.name,
                "png_sha256": hashlib.sha256(picture.read_bytes()).hexdigest(),
                "camera_mode": "source_orthographic" if aligned else "perspective"})
        report = {"status": "rendered", "scene_sha256": digest(current), "steps": records}
        write_json(output / "report.json", report)
        return report
    monkeypatch.setattr(source_view, "fit_source_view", fit)
    monkeypatch.setattr(rendering, "render_candidate", render)
    report = evaluate_job(store, child["id"], baseline_path=directory / "scene.json")
    assert seen[0]["first_step"] == 2
    assert bool(seen[0]["source_views"]) == (fit_status == "fitted")
    assert report["correction_evidence_refresh"]["rendered_microsteps"] == 2
    assert report["instruction_comparisons"][1]["after"] is not None
    assert [step["poses"] for step in child["checkpoint"]["candidate"]["steps"]] == [step.model_dump(mode="json")["poses"] for step in scene.steps]
    assert store.get(identity)["checkpoint"]["candidate"] == scene.model_dump(mode="json")


@pytest.mark.parametrize("tamper", [None, "parent_pixels", "parent_scene", "copied_parent", "lineage_binding", "changed_prefix"])
def test_corrected_evaluation_reuses_only_verified_unchanged_parent_prefix(tmp_path, scene_data, monkeypatch, tamper):
    from guide2build.engine import rendering
    from guide2build.engine.corrections import fork_correction
    from guide2build.releases.models import SceneV2
    store, identity, scene, directory = seed_job(tmp_path, scene_data)
    parent_renders = directory / "retained-renders"
    parent_renders.mkdir()
    records = []
    for step in scene.steps:
        picture = parent_renders / f"{step.step_id}.png"
        Image.new("RGB", (32, 32), "red").save(picture)
        records.append({"step_id": step.step_id, "screenshot": picture.name,
            "png_sha256": hashlib.sha256(picture.read_bytes()).hexdigest(), "camera_mode": "perspective"})
    write_json(parent_renders / "report.json", {"status": "rendered", "scene_sha256": digest(scene), "steps": records})
    pose = scene.steps[1].poses["b"].model_dump(mode="json")
    pose["position_ldu"][0] += 10
    request = correction_request(tmp_path, scene, [{"op": "pose", "step_id": "s2", "instance_id": "b",
        "pose": pose, "reason": "Synthetic corrected suffix", "evidence": scene.steps[1].source.model_dump(mode="json")}])
    child = fork_correction(store, identity, request, "render-reuse-r1")
    child_directory = store.root / "jobs" / child["id"]
    if tamper == "parent_pixels":
        (parent_renders / "s1.png").write_bytes(b"changed parent pixels")
    elif tamper in {"parent_scene", "copied_parent"}:
        path = directory / "scene.json" if tamper == "parent_scene" else child_directory / "parent-scene.json"
        changed = json.loads(path.read_text())
        changed["revision"] = "tampered"
        write_json(path, changed)
    elif tamper == "lineage_binding":
        receipt = json.loads((child_directory / "correction.json").read_text())
        receipt["parent_scene_sha256"] = "0" * 64
        write_json(child_directory / "correction.json", receipt)
    elif tamper == "changed_prefix":
        store.claim("changed-prefix", job_id=child["id"])
        checkpoint = store.get(child["id"])["checkpoint"]
        checkpoint["candidate"]["steps"][0]["poses"]["a"]["position_ldu"][0] += 1
        write_json(child_directory / "scene.json", checkpoint["candidate"])
        store.checkpoint(child["id"], "changed-prefix", checkpoint, "paused")
    page = tmp_path / "public/pages" / scene.source_sha256 / "page-000.png"
    page.parent.mkdir(parents=True)
    Image.new("RGB", (32, 32), "white").save(page)
    write_json(page.parent / "pages.json", [{"page_index": 0, "file": page.name,
        "sha256": hashlib.sha256(page.read_bytes()).hexdigest()}])
    def render(path, geometry, output, **kwargs):
        assert kwargs["first_step"] == 2
        current = SceneV2.model_validate_json(path.read_text())
        output.mkdir()
        fresh_records = []
        for step in current.steps[1:]:
            picture = output / f"{step.step_id}.png"
            Image.new("RGB", (32, 32), "blue").save(picture)
            fresh_records.append({"step_id": step.step_id, "screenshot": picture.name,
                "png_sha256": hashlib.sha256(picture.read_bytes()).hexdigest(), "camera_mode": "perspective"})
        report = {"status": "rendered", "scene_sha256": digest(current), "steps": fresh_records}
        write_json(output / "report.json", report)
        return report
    monkeypatch.setattr(rendering, "render_candidate", render)
    if tamper not in {None, "changed_prefix"}:
        with pytest.raises(ValueError, match="Render image hash|Parent scene differs|parent render lineage"):
            evaluate_job(store, child["id"])
        return
    parent_before, child_before = store.get(identity), store.get(child["id"])
    report = evaluate_job(store, child["id"])
    assert store.get(identity) == parent_before and store.get(child["id"]) == child_before
    cards = {row["step_id"]: row for row in report["instruction_comparisons"]}
    assert all(row["source"] is not None for row in cards.values())
    if tamper == "changed_prefix":
        assert cards["s1"]["after"] is None and report["reused_parent_prefix_render_step_ids"] == []
    else:
        reused = cards["s1"]["after"]
        assert report["reused_parent_prefix_render_step_ids"] == ["s1"]
        assert reused["sha256"] == records[0]["png_sha256"]
        assert reused["match_basis"] == "unchanged_parent_prefix" and reused["reused_parent_render"] is True
        assert reused["reuse_lineage"][-1]["parent_job_id"] == identity
        assert reused["reuse_lineage"][-1]["parent_scene_sha256"] == digest(scene)
        assert reused["render_receipt_sha256"] == hashlib.sha256((parent_renders / "report.json").read_bytes()).hexdigest()
    for step_id in ("s2", "s3"):
        fresh = cards[step_id]["after"]
        assert fresh["sha256"] != records[0]["png_sha256"]
        assert fresh.get("reused_parent_render") is not True
        assert fresh["render_scene_sha256"] == report["scene_sha256"]


@pytest.mark.parametrize("whole_canvas", [False, True])
def test_source_aligned_derivative_keeps_original_hash_and_crops_same_panel(tmp_path, whole_canvas):
    from guide2build.engine.evaluation import _comparison_render
    path = tmp_path / "original.png"
    Image.new("RGB", (120, 100) if whole_canvas else (100, 80), "green").save(path)
    original = path.read_bytes()
    output = tmp_path / "evidence"
    output.mkdir()
    result = _comparison_render({"path": path, "sha256": hashlib.sha256(original).hexdigest(),
        "camera_mode": "source_orthographic", "source_camera": {"source_rect": {"x": 10, "y": 10, "width": 100, "height": 80},
            "viewport": {"width": 120, "height": 100}}}, output, "after-1.png", [.25, .25, .75, .75])
    assert (output / result["original_file"]).read_bytes() == original
    assert result["original_sha256"] == hashlib.sha256(original).hexdigest()
    assert result["sha256"] == hashlib.sha256((output / result["file"]).read_bytes()).hexdigest()
    assert Image.open(output / result["file"]).size == (50, 40)
    assert result["crop_pixels"] == ([35, 30, 85, 70] if whole_canvas else [25, 20, 75, 60])


def test_later_assisted_origin_does_not_hide_unchanged_earlier_callout_render(tmp_path, scene_data):
    from guide2build.engine.corrections import fork_correction
    from guide2build.engine.evaluation import _parent_prefix_images
    from guide2build.releases.models import SceneV2
    store, identity, scene, directory = seed_job(tmp_path, scene_data)
    renders = directory / "renders"
    renders.mkdir()
    picture = renders / "s2.png"
    Image.new("RGB", (32, 32), "green").save(picture)
    write_json(renders / "report.json", {"status": "rendered", "scene_sha256": digest(scene), "steps": [
        {"step_id": "s2", "screenshot": picture.name, "png_sha256": hashlib.sha256(picture.read_bytes()).hexdigest()}]})
    desired = scene.steps[2].poses["b"].model_dump(mode="json")
    desired["position_ldu"][0] += 10
    request = correction_request(tmp_path, scene, [{"op": "group", "step_id": "s3", "group_id": "g1",
        "anchor_instance_id": "b", "pose": desired, "reason": "Synthetic later group correction",
        "evidence": scene.steps[2].source.model_dump(mode="json")}])
    child = fork_correction(store, identity, request, "later-group-repair")
    current = SceneV2.model_validate(child["checkpoint"]["candidate"])
    assert current.instances[1].origin == "pdf_assisted_authoring" and scene.instances[1].origin == "vision_proposal"
    images = _parent_prefix_images(store, child, current, store.root / "jobs" / child["id"])
    assert set(images) == {"s2"}
    assert images["s2"]["reuse_lineage"][-1]["ignored_nonvisual_instance_fields"] == ["origin", "mapping_status"]
    second_request = correction_request(tmp_path, current, [{"op": "pose", "step_id": "s3", "instance_id": "b",
        "pose": scene.steps[2].poses["b"].model_dump(mode="json"), "reason": "Synthetic second correction",
        "evidence": scene.steps[2].source.model_dump(mode="json")}], correction_id="repair-second")
    second = fork_correction(store, child["id"], second_request, "second-later-repair")
    second_scene = SceneV2.model_validate(second["checkpoint"]["candidate"])
    twice_inherited = _parent_prefix_images(store, second, second_scene, store.root / "jobs" / second["id"])
    assert set(twice_inherited) == {"s2"}
    assert [item["parent_job_id"] for item in twice_inherited["s2"]["reuse_lineage"]] == [identity, child["id"]]
    # A visible material change can never use the earlier image, even with the same poses.
    current.instances[1].color_code = "4"
    assert _parent_prefix_images(store, child, current, store.root / "jobs" / child["id"]) == {}
