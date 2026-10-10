"""Independent original synthetic counterexamples; no live jobs or inference."""
from copy import deepcopy
from itertools import permutations

import pytest

from guide2build.engine import exploration, localized_review as lr
from guide2build.engine.repair_decision import decide_repair
from guide2build.engine.repair_feedback import compact_feedback, prompt_feedback
from guide2build.releases.models import canonical, digest
from test_engine_localized_review import defect, descriptor, record, review, scene


@pytest.mark.parametrize("ambiguous", [
    defect("Another unlocalized concern", (), localization="unlocalized"),
    defect("Could concern head or hand", ("head", "hand-a"), localization="one_of"),
], ids=["anonymous_bridge", "one_of_bridge"])
def test_added_uncertainty_must_not_erase_two_named_subject_incidences(ambiguous):
    identified = [defect(), defect("Misplaced hand", ("hand-a",))]
    before = lr.group_defects([review(identified)], {"current"})
    after = lr.group_defects([review([*identified, ambiguous])], {"current"})
    assert len(before) == 2
    assert len(after) >= len(before), "Adding uncertainty must not reduce already established disjoint subject incidences"


def test_less_localized_review_must_not_be_preferred_as_fewer_assembly_defects():
    initial = record("identified", [defect(), defect("Misplaced hand", ("hand-a",))])
    changed = scene()
    changed["steps"][0]["poses"]["head"]["position_ldu"][1] = 100
    ambiguous = record("unlocalized", [
        defect("Misplaced head", (), localization="unlocalized"),
        defect("Misplaced hand", (), localization="unlocalized"),
    ], changed)
    _, receipt = exploration._select_candidates([initial, ambiguous])
    assert receipt["status"] != "preferred_by_evidence", receipt


def test_receipt_and_source_subject_boundaries_remain_conservative():
    value = descriptor()
    changed = deepcopy(value)
    changed["frames"][0]["png_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="descriptor"):
        lr.normalize_review(review([]), changed)
    for bad in [defect(ids=("absent",)), defect() | {"step_ids": ["not-rendered"]}]:
        with pytest.raises(ValueError):
            review([bad], value)


def test_identified_observation_subject_survives_targeted_repair_scope():
    candidate = record("observed-head", [defect(ids=(), observations=("source-head",))])
    selected, _ = exploration._select_candidates([candidate])
    assert selected["visual_review"]["visible_defects"][0]["subject_candidates"] == ["head"]
    decision = decide_repair(selected, None, attempts_used=1, max_attempts=2, calls_remaining=10)
    assert decision["action"] == "repair"
    assert decision["scope"]["instance_ids"] == ["head"], decision


@pytest.mark.parametrize("count, snapshots", [(128, 1), (144, 1), (128, 5)])
def test_large_scene_coverage_cannot_silently_claim_completeness(count, snapshots):
    value = scene(count)
    first = value["steps"][0]
    value["steps"] = [deepcopy(first) | {"step_id": f"snapshot-{i}"} for i in range(snapshots)]
    result = lr.describe(value, [step["step_id"] for step in value["steps"]], [],
        [{"step_id": step["step_id"], "image_index": i + 1, "png_sha256": "b" * 64,
          "camera_mode": "overview"} for i, step in enumerate(value["steps"])],
        {"image_index": 0, "source_sha256": value["source_sha256"], "page_index": 0, "page_sha256": "c" * 64})
    assert result["coverage"]["included_instances"] <= 128
    assert result["coverage"]["pose_rows_included"] <= 512
    assert result["coverage"]["complete"] is (count <= 128 and count * snapshots <= 512)


def test_bridge_groups_and_severity_are_invariant_under_all_observation_orderings():
    values = [defect(severity="minor"), defect("Hand issue", ("hand-a",)),
        defect("Unknown major issue", (), localization="unlocalized"),
        defect("Head or hand", ("head", "hand-a"), localization="one_of")]
    expected = lr.group_defects([review(values)], {"current"})
    assert len(expected) == 2
    assert {tuple(item["instance_ids"]): item["severity"] for item in expected} == {("head",): "minor", ("hand-a",): "major"}
    for order in permutations(values):
        assert lr.group_defects([review(list(order))], {"current"}) == expected


def test_equivalent_scene_pooling_is_order_invariant_without_erasing_named_subjects():
    records = [record("named", [defect(), defect("Hand issue", ("hand-a",))]),
        record("anonymous", [defect("Unknown issue", (), localization="unlocalized")]),
        record("alternatives", [defect("Could be either", ("head", "hand-a"), localization="one_of")])]
    profiles = None
    for order in permutations(records):
        _, receipt = exploration._select_candidates(list(order))
        assert receipt["status"] == "equivalent_tie"
        for value in receipt["profiles"].values():
            assert value["defect_counts"]["placement"]["major"] == 2
        if profiles is None:
            profiles = {key: digest(value["defects"]) for key, value in receipt["profiles"].items()}
        else:
            assert {key: digest(value["defects"]) for key, value in receipt["profiles"].items()} == profiles


def test_existing_anonymous_residual_cannot_hide_a_previously_identified_head():
    unknown = defect("Hand cannot be localized", (), localization="unlocalized")
    initial = record("initial", [defect(), defect("Identified hand issue", ("hand-a",)), unknown])
    changed = scene()
    changed["steps"][0]["poses"]["head"]["position_ldu"][1] = 90
    less = record("less", [unknown, defect("Head cannot be localized", (), localization="unlocalized")], changed)
    _, receipt = exploration._select_candidates([initial, less])
    assert receipt["status"] == "unresolved_alternatives"
    assert receipt["comparisons"][0]["reason"] == "unresolved_subject_can_explain_apparently_removed_defect"


def test_known_head_resolution_can_win_with_the_same_disjoint_hand_alternatives():
    hands = defect("A hand remains misplaced", ("hand-a", "hand-b"), localization="one_of")
    initial = record("initial", [defect(ids=(), observations=("source-head",)), hands])
    changed = scene()
    changed["steps"][0]["poses"]["head"]["position_ldu"][1] = 90
    after = record("after", [hands], changed)
    for order in ([initial, after], [after, initial]):
        selected, receipt = exploration._select_candidates(order)
        assert selected["selection_id"] == "after"
        assert receipt["status"] == "preferred_by_evidence"
        assert selected["selected_quality"]["unresolved_localization"]


def test_broader_uncertainty_cannot_win_on_camera_only_evidence():
    hands = defect("A hand issue", ("hand-a", "hand-b"), localization="one_of")
    initial = record("initial", [defect(), hands])
    changed = scene()
    changed["steps"][0]["poses"]["head"]["position_ldu"][1] = 90
    broader = record("broader", [defect(), hands, defect("Maybe another issue", (), localization="unlocalized")], changed)
    initial["selection_evidence"]["camera"]["units"][0].update(rms_pixels=3.0, max_error_pixels=4.0)
    broader["selection_evidence"]["camera"]["units"][0].update(rms_pixels=0.1, max_error_pixels=0.2)
    _, receipt = exploration._select_candidates([initial, broader])
    assert receipt["status"] == "unresolved_alternatives"
    assert receipt["comparisons"][0]["reason"] == "less_localized_review_cannot_establish_superiority"


def test_multiple_identified_subjects_remain_anchors_and_shared_text_stays_bounded():
    value = scene(64)
    names = [part["instance_id"] for part in value["instances"]]
    values = [defect(str(index) + "x" * 3900, names) for index in range(64)]
    result = lr.group_defects([review(values, descriptor(value, []))], {"current"})
    assert len(result) == 64 and all(item["incidence"] == "identified_subject" for item in result)
    assert len(canonical(result)) < 2_000_000
    assert sum("observation_sha256" not in item for group in result for item in group["observations"]) == 64


def test_normalization_and_compact_feedback_keep_identified_observation_subject():
    raw = {"hypothesis_id": "candidate", "coverage_agrees": True, "assembly_agrees": False,
        "findings": [], "visible_defects": [defect(ids=(), observations=("source-head",))]}
    before = canonical(raw)
    normalized = lr.normalize_review(raw, descriptor())
    assert canonical(raw) == before
    finding = normalized["visible_defects"][0] | {"category": "source_visible_defect"}
    assert finding["reported_instance_ids"] == [] and finding["instance_ids"] == ["head"]
    shown = prompt_feedback(compact_feedback([finding], ["current"]))["findings"][0]
    assert shown["instance_ids"] == ["head"]
    assert shown["finding"]["subject_scope"]["identified_count"] == 1
    assert shown["finding"]["review_context"]["complete"]


def test_alternatives_reach_repair_as_inspection_subjects_not_all_defective():
    candidate = record("hands", [defect("One wrist", ("hand-a", "hand-b"), localization="one_of")])
    selected, _ = exploration._select_candidates([candidate])
    decision = decide_repair(selected, None, attempts_used=1, max_attempts=2, calls_remaining=10)
    assert decision["scope"]["instance_ids"] == ["hand-a", "hand-b"]
    assert decision["scope"]["identified_instance_ids"] == []
    assert decision["scope"]["alternative_subjects"][0]["possible_instance_ids"] == ["hand-a", "hand-b"]
    assert decision["scope"]["scope_members_are_not_all_defective"]
    assert decision["actionable_defects"][0]["instance_ids"] == []
    finding = selected["visual_review"]["visible_defects"][0] | {"category": "source_visible_defect"}
    shown = prompt_feedback(compact_feedback([finding], ["current"]))["findings"][0]
    assert shown["instance_ids"] == [] and shown["uncertainty"] == "explicit"
    assert shown["finding"]["subject_scope"]["alternative_candidate_count"] == 2
    assert shown["finding"]["subject_scope"]["alternatives_are_not_all_defective"]


def test_partial_zero_defects_retain_coverage_limits_in_quality_repair_and_compaction():
    value = scene(144)
    context = descriptor(value, [])
    candidate = record("partial", [], value)
    candidate.update(review_context_complete=False, review_context_summary=lr.coverage_summary(context))
    selected, _ = exploration._select_candidates([candidate])
    compact = exploration._quality_context(selected["selected_quality"])
    assert not compact["review_context_complete"] and compact["zero_count_is_not_clean_assembly"]
    assert "lower-bound" in compact["defect_count_scope"]
    assert compact["review_context_omissions"][0]["omitted_instances"] == 16
    decision = decide_repair(selected, None, attempts_used=1, max_attempts=2, calls_remaining=10)
    assert decision["action"] == "continue"  # Missing metadata is not a pose defect.
    assert not decision["scope"]["review_context_complete"]
    assert decision["scope"]["review_context_omissions"][0]["omitted_instances"] == 16
    finding = {"category": "review_context_incomplete", "description": "界" * 3000,
        "step_ids": ["current"], "instance_ids": [], "localization_profile": lr.PROFILE,
        "review_context": lr.coverage_summary(context)}
    before = canonical(finding)
    receipt = compact_feedback([finding], ["current"])
    prompt = prompt_feedback(receipt)
    assert len(canonical(receipt)) <= 16384 and len(canonical(prompt)) <= 16384
    assert canonical(finding) == before
    shown = prompt["findings"][0]
    assert shown["uncertainty"] == "explicit" and shown["preview"]["truncated"]
    assert shown["finding"]["review_context"] == {"complete": False, "omitted_instances": 16,
        "omitted_pose_rows": 16, "omitted_observations": 0, "ambiguous_observation_ids_count": 0}
