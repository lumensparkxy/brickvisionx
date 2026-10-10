"""Original synthetic review subjects; no LEGO geometry/accuracy assertions."""
from copy import deepcopy
import hashlib
import json

import pytest

from guide2build.engine import corrections, exploration, localized_review as lr
from guide2build.engine.store import execution_config
from guide2build.releases.models import SceneV2, canonical, digest
from guide2build.engine.exploration import strict_schema
from test_engine_exploration import harness as _harness, _selection_record
from test_engine_correction_controls import _seed, _request, _parent_state

harness = _harness

SOURCE = "a" * 64


def scene(count=4):
    names = ["head", "body", "hand-a", "hand-b"] + [f"extra-{i:04d}" for i in range(max(0, count-4))]
    names = names[:count]
    parts = [{"instance_id": name, "part_id": "synthetic", "color_code": "4",
        "geometry_ref": "parts/synthetic.dat", "origin": "vision_proposal", "mapping_status": "candidate",
        "source": {"source_sha256": SOURCE, "page_index": 0, "bbox": [(i % 8)/10, 0, (i % 8+1)/10, .1]}}
        for i, name in enumerate(names)]
    value = {"schema_version": "2.0", "set_number": "30669", "guide_id": "alt-02", "revision": "synthetic",
        "source_sha256": SOURCE, "sources": [{"source_sha256": SOURCE, "guide_id": "alt-02", "page_count": 8,
            "official_url": "https://www.lego.com/cdn/product-assets/product.bi.core.pdf/synthetic.pdf"}],
        "coordinate_system": "right_handed_y_up_ldu", "status": "needs_review", "geometry_check": "not_run",
        "connector_check": "not_run", "physical_build_check": "not_run", "instances": parts,
        "sections": [{"section_id": "main", "label": "Original synthetic source", "source_sha256": SOURCE}],
        "steps": [{"step_id": "current", "section_id": "main", "main_step_number": 1, "substep_label": None,
            "action": "add_parts", "assembly_group_id": None, "instruction": "Synthetic state only.",
            "source": {"source_sha256": SOURCE, "page_index": 0, "bbox": [0, 0, 1, 1]},
            "introduced_instance_ids": names, "active_instance_ids": names, "visible_instance_ids": names,
            "poses": {name: {"position_ldu": [i*20, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]} for i, name in enumerate(names)}}]}
    return SceneV2.model_validate(value).model_dump(mode="json")


def descriptor(value=None, observations=None):
    value = value or scene()
    observations = observations if observations is not None else [
        {"observation_id": "source-" + part["instance_id"], "source": part["source"]} for part in value["instances"][:4]]
    return lr.describe(value, ["current"], observations,
        [{"step_id": "current", "image_index": 1, "png_sha256": "b" * 64, "camera_mode": "overview"}],
        {"image_index": 0, "source_sha256": SOURCE, "page_index": 0, "page_sha256": "c" * 64})


def defect(text="Misplaced head", ids=("head",), observations=(), localization="identified", severity="major"):
    return {"domain": "placement", "severity": severity, "step_ids": ["current"], "instance_ids": list(ids),
            "observation_ids": list(observations), "localization": localization, "description": text}


def review(values, context=None):
    return lr.normalize_review({"hypothesis_id": "candidate", "coverage_agrees": True, "assembly_agrees": not values,
        "findings": [], "visible_defects": values}, context or descriptor())


def record(identifier, values, value=None):
    value = value or scene()
    result = _selection_record(identifier, physical=exploration._physical_signature(value))
    result.update(candidate=value, review_profile=lr.PROFILE, review_context_complete=True,
                  visual_review=review(values, descriptor(value)))
    result["selection_evidence"]["physical_scene_sha256"] = exploration._physical_signature(value)
    result["visual_review"]["hypothesis_id"] = identifier
    return result


def test_descriptor_has_actual_ids_poses_sources_and_bound_pixels_without_mutation():
    value = scene()
    before = canonical(value)
    result = descriptor(value)
    assert canonical(value) == before
    assert result["scene_sha256"] == digest(value)
    assert [part["instance_id"] for part in result["instances"]] == ["body", "hand-a", "hand-b", "head"]
    assert result["snapshots"][0]["poses"] == value["steps"][0]["poses"]
    assert result["observations"][3]["possible_instance_ids"] == ["head"]
    assert result["frames"][0]["png_sha256"] == "b" * 64
    assert result["source_image"]["page_sha256"] == "c" * 64
    assert result["coverage"]["complete"] and not result["assembly_verified"]
    lr.verify_descriptor(result)


def test_large_descriptor_is_bounded_in_utf8_and_discloses_exact_omissions(monkeypatch):
    value = scene(300)
    value["steps"][0]["introduced_instance_ids"] = ["extra-0295"]
    value["steps"][0]["active_instance_ids"] = ["extra-0295"]
    # A renderer's scene has already passed SceneV2. Only review metadata is bounded here.
    monkeypatch.setitem(lr.LIMITS, "bytes", 5000)
    result = descriptor(value, [])
    assert len(canonical(result)) <= 5000
    assert result["coverage"]["included_instances"] + result["coverage"]["omitted_instances"] == 300
    assert not result["coverage"]["complete"]
    assert result["instances"][0]["instance_id"] == "extra-0295"
    assert result["coverage"]["pose_rows_included"] <= lr.LIMITS["pose_rows"]


@pytest.mark.parametrize("change", ["hash", "scene", "limit"])
def test_descriptor_tampering_rejected(change):
    value = descriptor()
    if change == "hash":
        value["receipt_sha256"] = "0" * 64
    elif change == "scene":
        value["snapshots"][0]["poses"]["head"]["position_ldu"][1] += 1
    else:
        value["limits"]["bytes"] += 1
    with pytest.raises(ValueError, match="descriptor"):
        lr.verify_descriptor(value)


def test_equal_source_box_mapping_does_not_depend_on_correct_design_identity():
    value = scene()
    value["instances"][0]["part_id"] = "syntheticwrong"
    assert descriptor(value)["observations"][3]["possible_instance_ids"] == ["head"]


def test_conflicting_observation_names_are_omitted_as_uncertain_not_given_a_false_map():
    value = scene()
    context = descriptor(value, [{"observation_id": "ambiguous", "source": part["source"]} for part in value["instances"][:2]])
    assert context["observations"] == []
    assert context["coverage"]["ambiguous_observation_ids"] == ["ambiguous"]
    assert context["coverage"]["omitted_observations"] == 2 and not context["coverage"]["complete"]
    with pytest.raises(ValueError, match="omitted|unknown"):
        review([defect(ids=(), observations=("ambiguous",))], context)


def test_anonymous_distinct_observations_survive_permutation_without_prose_votes():
    values = [defect("Head at torso", (), localization="unlocalized"),
              defect("Hand above wrist", (), localization="unlocalized")]
    first = lr.group_defects([review(values)], {"current"})
    assert first == lr.group_defects([review(list(reversed(values)))], {"current"})
    assert len(first) == 1 and first[0]["observation_count"] == 2
    assert {item["description"] for item in first[0]["observations"]} == {"Head at torso", "Hand above wrist"}
    assert first[0]["incidence"] == "unlocalized_lower_bound"
    repeated = lr.group_defects([review(values + [values[0], defect("Rephrased head concern", (), localization="unlocalized")])], {"current"})
    assert len(repeated) == 1 and repeated[0]["observation_count"] == 3


def test_disjoint_head_and_ambiguous_hands_rank_separately_and_repair_can_win():
    hand = defect("Wrist stem exposed", ("hand-a", "hand-b"), localization="one_of")
    initial = record("initial", [defect(), hand])
    after = scene()
    after["steps"][0]["poses"]["head"]["position_ldu"][1] = 20
    repaired = record("repair", [hand], after)
    selected, receipt = exploration._select_candidates([initial, repaired])
    assert selected["selection_id"] == "repair"
    assert receipt["version"] == lr.SELECTION_VERSION
    assert receipt["profiles"]["initial"]["defect_counts"]["placement"]["major"] == 2
    assert receipt["profiles"]["repair"]["defect_counts"]["placement"]["major"] == 1
    assert receipt["profiles"]["repair"]["defects"][0]["localization_uncertainty"]
    assert not selected["visual_review"]["assembly_agrees"]  # A relative preference is not approval.


def test_overlapping_ambiguous_subject_and_rewording_do_not_double_count():
    values = [defect("Possibly one hand", ("hand-a", "hand-b"), localization="one_of"),
              defect("Identified hand issue", ("hand-a",)),
              defect("Same hand described differently", ("hand-a",))]
    result = lr.group_defects([review(values)], {"current"})
    assert len(result) == 1 and result[0]["observation_count"] == 3
    assert result[0]["localization_uncertainty"]


def test_exact_repeats_and_equivalent_scene_review_pooling_do_not_inflate():
    first = record("first", [defect()])
    repeat = record("repeat", [defect(), defect("Different wording for the same head")])
    _, result = exploration._select_candidates([first, repeat])
    assert result["status"] == "equivalent_tie"
    for profile in result["profiles"].values():
        assert profile["defect_counts"]["placement"]["major"] == 1
        assert profile["defects"][0]["observation_count"] == 2


def test_explicit_source_observation_resolves_a_known_physical_subject():
    result = review([defect(ids=(), observations=("source-head",))])
    assert result["visible_defects"][0]["subject_candidates"] == ["head"]


@pytest.mark.parametrize("value", [
    defect(ids=("missing",)), defect(ids=(), observations=("unknown-observation",)),
    defect(ids=(), localization="identified"), defect(localization="unlocalized"),
    defect(localization="one_of"), defect(ids=("head", "head")),
    defect() | {"step_ids": ["different-step"]},
])
def test_invalid_or_invented_review_subjects_reject(value):
    with pytest.raises(ValueError):
        review([value])


def test_omitted_subject_cannot_be_used_for_false_precise_localization(monkeypatch):
    monkeypatch.setitem(lr.LIMITS, "instances", 1)
    context = descriptor()
    assert context["coverage"]["omitted_instances"] == 3
    with pytest.raises(ValueError, match="omitted|complete"):
        review([defect()], context)


def test_unknown_subject_overlapping_named_claim_remains_one_conservative_group():
    result = lr.group_defects([review([defect(), defect("Cannot localize", (), localization="unlocalized")])], {"current"})
    assert len(result) == 1 and result[0]["localization_uncertainty"]
    assert result[0]["observation_count"] == 2


def test_duplicate_subject_mapping_cannot_claim_exact_localization():
    value = scene()
    value["instances"][2]["source"] = deepcopy(value["instances"][0]["source"])
    with pytest.raises(ValueError, match="multiply mapped"):
        review([defect(ids=(), observations=("source-head",))], descriptor(value))


def test_grouping_resource_bound_rejects_extra_reviews():
    with pytest.raises(ValueError, match="bound"):
        lr.group_defects([review([])] * 7, {"current"})


def test_profile_is_opt_in_and_unknown_or_strict_profiles_are_rejected():
    base = {"execution_policy": "explore", "model": "gemini-3.8-flash", "thinking_level": "high"}
    assert execution_config(base) == execution_config(base | {"review_profile": "legacy"})
    assert "review_profile" not in execution_config(base)
    assert execution_config(base | {"review_profile": lr.PROFILE})["review_profile"] == lr.PROFILE
    for value in [None, "other", True]:
        with pytest.raises(ValueError):
            execution_config(base | {"review_profile": value})
    with pytest.raises(ValueError, match="exploration"):
        execution_config({"execution_policy": "strict", "review_profile": lr.PROFILE})


def test_policy_binds_opt_in_text_limits_schema_and_rejects_resume_drift(monkeypatch):
    base = {"execution_policy": "explore", "review_profile": lr.PROFILE,
            "model": "gemini-3.8-flash", "thinking_level": "high", "max_model_calls": 300}
    checkpoint = {}
    policy = exploration._policy(base, checkpoint, SOURCE, 8)
    assert policy["candidate_review_schema_sha256"] == digest(strict_schema(lr.CandidateComparison))
    assert policy["candidate_selection_version"] == lr.SELECTION_VERSION
    assert policy["max_model_calls"] == 300 and policy["runtime_choice"] == {"provider": "google_adk", "model": "gemini-3.8-flash", "thinking_level": "high", "provider_timeout": 120}
    with pytest.raises(ValueError, match="policy"):
        exploration._policy(base | {"review_profile": "legacy"}, deepcopy(checkpoint), SOURCE, 8)
    monkeypatch.setattr(lr, "PROMPT", lr.PROMPT + "changed")
    with pytest.raises(ValueError, match="policy"):
        exploration._policy(base, deepcopy(checkpoint), SOURCE, 8)


def test_legacy_policy_and_schema_do_not_enroll_new_profile():
    for proposal in ("baseline", "attachment-reasoning", "event-scoped"):
        config = {"execution_policy": "explore", "proposal_profile": proposal, "model": "gemini-3.8-flash", "thinking_level": "high"}
        policy = exploration._policy(config, {}, SOURCE, 8)
        assert policy == exploration._policy(config | {"review_profile": "legacy"}, {}, SOURCE, 8)
        assert "source_review_profile" not in policy
        assert policy["candidate_selection_version"] == "source-quality-selection-v1"
        assert policy["candidate_review_schema_sha256"] == "bafb3791f700e6f19ad84eb0563f9df803c496a6b4dc55c995028c0423d2552f"


def test_actual_opt_in_review_prompt_contains_rendered_ids_and_resume_reuses_receipts(harness):
    h = harness
    h.job["config"]["review_profile"] = lr.PROFILE
    exploration.run_exploration(**h.args, max_panels=1)
    calls_before = len(h.provider.calls)
    call = next(item for item in h.provider.calls if item["key"].endswith("review"))
    payload = json.loads(call["prompt"][call["prompt"].index("{"):])
    context = payload["candidates"][0]["rendered_context"]
    assert lr.PROMPT in call["prompt"]
    assert context["instances"][0]["instance_id"] == "synthetic-part-1"
    assert context["snapshots"][0]["poses"]["synthetic-part-1"]["position_ldu"] == [20, 0, 0]
    assert context["frames"][0]["png_sha256"] == hashlib.sha256(call["images"][-1].read_bytes()).hexdigest()
    assert context["coverage"]["complete"]
    assert h.cp["model_calls_used"] == 12  # Same eight indexes + two proposals + two reviews.
    result = exploration._recover_result(h.directory, h.cp["instruction_results"][0], None, SOURCE,
        h.cp["exploration_source_pages"], h.cp["exploration_policy"])
    assert result == h.cp["candidate"] and len(h.provider.calls) == calls_before


def test_same_selector_cannot_mix_legacy_and_localized_records():
    legacy = _selection_record("legacy", physical="legacy")
    localized = record("localized", [defect()])
    with pytest.raises(ValueError, match="mix"):
        exploration._select_candidates([legacy, localized])


def test_partial_context_cannot_win_by_omitting_localized_defects():
    complete = record("complete", [defect()])
    other = scene()
    other["steps"][0]["poses"]["head"]["position_ldu"][1] = 10
    partial = record("partial", [], other)
    partial["review_context_complete"] = False
    _, receipt = exploration._select_candidates([complete, partial])
    assert receipt["status"] == "unresolved_alternatives"
    assert receipt["comparisons"][0]["reason"] == "incomplete_rendered_review_context"
    assert set(receipt["frontier_ids"]) == {"complete", "partial"}


def test_new_restart_can_explicitly_opt_in_without_parent_or_budget_changes(tmp_path, scene_data):
    store, identity, original, directory = _seed(tmp_path, scene_data)
    before = _parent_state(store, identity, directory)
    child = corrections.fork_correction(store, identity, _request(tmp_path, original, review_profile=lr.PROFILE), "localized")
    assert _parent_state(store, identity, directory) == before
    assert child["config"]["review_profile"] == lr.PROFILE
    assert child["config"]["model"] == before[0]["config"]["model"]
    assert child["config"]["max_model_calls"] == before[0]["config"]["max_model_calls"] == 7
    assert child["checkpoint"]["model_calls_used"] == child["checkpoint"]["inherited_model_calls_used"] == 5
    assert child["checkpoint"]["local_model_calls_used"] == 0
    line = child["checkpoint"]["correction_lineage"][-1]
    assert line["requested_controls"]["review_profile"] == lr.PROFILE
    assert line["exploration_policy_transition"]["scope"] == "new_correction_revision_only"
    assert "source_review_profile" in line["exploration_policy_transition"]["changed_fields"]
    assert line["exploration_policy_transition"]["model_call_budget_preserved"]
    assert not line["exploration_policy_transition"]["parent_provider_receipts_reused"]
    recorded = json.loads((store.root / "jobs" / child["id"] / "correction-request.json").read_text())
    assert recorded["review_profile"] == lr.PROFILE and digest(recorded) == line["request_sha256"]


def test_command_only_correction_cannot_silently_switch_review_profile(tmp_path, scene_data):
    store, _, original, _ = _seed(tmp_path, scene_data)
    value = json.loads(_request(tmp_path, original, review_profile=lr.PROFILE).read_text())
    value.pop("restart_main_step")
    value["commands"] = [{"op": "mapping", "instance_id": "a", "part_id": "synthetic2", "color_code": "4",
        "reason": "Original synthetic correction", "evidence": value["evidence"][0]}]
    with pytest.raises(ValueError, match="requires restart"):
        corrections.CorrectionRequest.model_validate(value)
    assert len(store.list()) == 1


def test_following_correction_inherits_profile_when_control_is_absent(tmp_path, scene_data):
    store, identity, original, _ = _seed(tmp_path, scene_data)
    child = corrections.fork_correction(store, identity, _request(tmp_path, original, review_profile=lr.PROFILE), "localized")
    child_scene = SceneV2.model_validate(child["checkpoint"]["candidate"])
    path = _request(tmp_path, child_scene)
    value = json.loads(path.read_text())
    value.update(correction_id="repair-second", restart_main_step=1)
    path.write_text(json.dumps(value))
    child_directory = store.root / "jobs" / child["id"]
    before = _parent_state(store, child["id"], child_directory)
    later = corrections.fork_correction(store, child["id"], path, "still-localized")
    assert _parent_state(store, child["id"], child_directory) == before
    assert later["config"]["review_profile"] == lr.PROFILE
    assert later["checkpoint"]["exploration_policy"]["source_review_profile"] == lr.binding()
    assert later["checkpoint"]["model_calls_used"] == 5 and later["checkpoint"]["local_model_calls_used"] == 0
