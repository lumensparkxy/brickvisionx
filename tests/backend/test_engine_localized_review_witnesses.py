"""Capacity-one review witnesses; synthetic scopes, no assembly truth claims."""
from copy import deepcopy
from itertools import combinations, permutations

import pytest

from guide2build.engine import exploration, localized_review as lr
from guide2build.releases.models import canonical
from test_engine_localized_review import SOURCE, defect, descriptor, record, review, scene

REASON = "distinct_unresolved_witnesses_required_for_superiority"


def disjoint_pair(gain="camera", anonymous=True):
    anchors = [defect("Known minor head issue", severity="minor"),
               defect("Known minor body issue", ("body",), severity="minor")]
    old = defect("One possible major concern", () if anonymous else ("head", "body", "hand-a", "hand-b"),
                 localization="unlocalized" if anonymous else "one_of")
    first = record("initial", [*anchors, old])
    changed = scene()
    changed["steps"][0]["poses"]["head"]["position_ldu"][1] = 90
    later = record("split", [*anchors,
        defect("One of head/hand-a", ("head", "hand-a"), localization="one_of"),
        defect("One of body/hand-b", ("body", "hand-b"), localization="one_of")], changed)
    if gain == "camera":
        first["selection_evidence"]["camera"]["units"][0].update(rms_pixels=3., max_error_pixels=4.)
        later["selection_evidence"]["camera"]["units"][0].update(rms_pixels=.1, max_error_pixels=.2)
    else:
        for candidate, score in [(first, .1), (later, .9)]:
            candidate["selection_evidence"]["images"] = {"current": {
                "comparison_scope_sha256": "a"*64, "source_mask_sha256": "b"*64,
                "occlusion_mask_sha256": "c"*64, "ranking_score": score}}
    return first, later


@pytest.mark.parametrize("anonymous", [True, False])
@pytest.mark.parametrize("gain", ["camera", "image"])
@pytest.mark.parametrize("reverse", [False, True])
def test_one_uncertain_scope_cannot_cover_two_new_disjoint_scopes(anonymous, gain, reverse):
    pair = list(disjoint_pair(gain, anonymous))
    before = canonical(pair)
    _, result = exploration._select_candidates(pair[::-1] if reverse else pair)
    assert canonical(pair) == before
    assert result["status"] == "unresolved_alternatives"
    assert result["comparisons"][0]["reason"] == REASON
    assert set(result["frontier_ids"]) == {"initial", "split"}
    assert result["profiles"]["initial"]["unresolved_evidence"]["scope_count"] == 1
    assert result["profiles"]["split"]["unresolved_evidence"]["scope_count"] == 2
    for profile in result["profiles"].values():
        assert profile["defect_counts"]["placement"] == {"major": 0, "minor": 2}


def test_rewording_and_equivalent_old_scenes_do_not_create_additional_witness_capacity():
    first, later = disjoint_pair()
    old_copy = deepcopy(first)
    old_copy["selection_id"] = "initial-copy"
    old_copy["visual_review"]["hypothesis_id"] = "initial-copy"
    old_copy["visual_review"]["visible_defects"][-1]["description"] = "Different wording of the same unknown subject"
    for order in permutations([first, old_copy, later]):
        _, result = exploration._select_candidates(list(order))
        assert result["status"] == "unresolved_alternatives"
        assert all(result["profiles"][key]["unresolved_evidence"]["scope_count"] == 1
                   for key in ["initial", "initial-copy"])
        assert any(row["reason"] == REASON for row in result["comparisons"])


def profile(values):
    return {"review_observations": [review(values)], "current_step_ids": ["current"]}


def test_matching_reassigns_a_flexible_old_witness_instead_of_greedily_rejecting():
    old = [defect("One unknown subject", (), localization="unlocalized"),
           defect("Possible head/hand-a", ("head", "hand-a"), localization="one_of")]
    new = [defect("Narrow head/hand-a", ("head", "hand-a"), localization="one_of"),
           defect("Narrow body/hand-b", ("body", "hand-b"), localization="one_of")]
    for before in permutations(old):
        for after in permutations(new):
            assert lr.preference_guard(profile(list(after)), profile(list(before))) is None
    # Exercise the explicit augmenting path independent of canonical scope order.
    uncertain = lr._uncertain_scopes(lr._observations([review(new)], {"current"}))
    witnesses = lr._uncertain_scopes(lr._observations([review(old)], {"current"}))
    broad_first = sorted(witnesses, key=lambda item: bool(item["subject_candidates"]))
    head_first = sorted(uncertain, key=lambda item: "head" not in item["subject_candidates"])
    assert lr._uncertainty_guard(head_first, broad_first) is None


def test_witness_domain_and_severity_are_not_exchangeable_capacity():
    new = [defect("Head pair", ("head", "hand-a"), localization="one_of"),
           defect("Body pair", ("body", "hand-b"), localization="one_of")]
    wrong_domain = defect("Unknown colour", (), localization="unlocalized") | {"domain": "colour"}
    old = [defect("Unknown placement", (), localization="unlocalized"), wrong_domain]
    assert lr.preference_guard(profile(new), profile(old)) == REASON
    old[1] = defect("Minor body pair", ("body", "hand-b"), localization="one_of", severity="minor")
    # Both new majors need the same old major; the minor is not a second major witness.
    assert lr.preference_guard(profile(new), profile(old)) == REASON
    old[1]["severity"] = "major"
    assert lr.preference_guard(profile(new), profile(old)) is None


def test_same_uncertain_subject_scope_keeps_one_witness_despite_words_order_and_lower_severity():
    old = [defect("Old hand pair", ("hand-a", "hand-b"), localization="one_of")]
    repeated = [defect("First wording", ("hand-b", "hand-a"), localization="one_of"),
                defect("Other wording", ("hand-a", "hand-b"), localization="one_of", severity="minor")]
    for order in permutations(repeated):
        current = profile(list(order))
        assert lr.preference_guard(current, profile(old)) is None
        assert lr.uncertainty_summary(current["review_observations"], {"current"})["scope_count"] == 1


def test_witness_steps_cannot_cover_unseen_current_snapshot():
    # Direct bounded normalized profiles exercise the step subset condition.
    old = profile([defect("Unknown", (), localization="unlocalized")])
    new = deepcopy(old)
    new["current_step_ids"] = ["later"]
    new["review_observations"][0]["visible_defects"][0]["step_ids"] = ["later"]
    old["current_step_ids"] = ["current", "later"]
    assert lr.preference_guard(new, old) == "less_localized_review_cannot_establish_superiority"


@pytest.mark.parametrize("reverse", [False, True])
def test_resolved_named_head_with_unchanged_disjoint_hands_still_wins(reverse):
    hand = defect("Possible one hand", ("hand-a", "hand-b"), localization="one_of")
    first = record("initial", [defect(), hand])
    changed = scene()
    changed["steps"][0]["poses"]["head"]["position_ldu"][1] = 20
    later = record("repaired", [hand], changed)
    pair = [first, later]
    selected, result = exploration._select_candidates(pair[::-1] if reverse else pair)
    assert result["status"] == "preferred_by_evidence" and selected["selection_id"] == "repaired"
    assert result["profiles"]["repaired"]["unresolved_evidence"]["scope_count"] == 1
    assert not selected["visual_review"]["assembly_agrees"]


def test_full_retained_review_bound_is_supported_and_excess_rejected_without_mutation():
    value = scene(32)
    context = descriptor(value, [])
    names = [x["instance_id"] for x in value["instances"]]
    pairs = list(combinations(names, 2))[:384]
    values = [defect(f"Distinct subject scope {n}", ids, localization="one_of") for n, ids in enumerate(pairs)]
    reviews = [review(values[i:i+64], context) for i in range(0, 384, 64)]
    packed = {"review_observations": reviews, "current_step_ids": ["current"]}
    before = canonical(packed)
    assert lr.preference_guard(packed, deepcopy(packed)) is None
    assert lr.uncertainty_summary(reviews, {"current"})["scope_count"] == 384
    assert canonical(packed) == before
    oversized = deepcopy(packed)
    oversized["review_observations"].append(deepcopy(reviews[0]))
    with pytest.raises(ValueError, match="bound"):
        lr.preference_guard(oversized, packed)


def test_new_capacity_rule_and_profile_are_durably_bound_before_resume(monkeypatch):
    config = {"execution_policy": "explore", "review_profile": lr.PROFILE,
              "model": "gemini-3.8-flash", "thinking_level": "high", "max_model_calls": 300}
    checkpoint = {}
    first = exploration._policy(config, checkpoint, SOURCE, 8)
    assert lr.PROFILE == "localized-source-v4"
    assert first["source_review_profile"]["uncertainty_preference_version"] == "capacity-one-unresolved-scope-v1"
    monkeypatch.setattr(lr, "UNCERTAINTY_VERSION", "capacity-rule-drift")
    with pytest.raises(ValueError, match="policy"):
        exploration._policy(config, checkpoint, SOURCE, 8)
    for superseded in ["localized-source-v1", "localized-source-v2", "localized-source-v3"]:
        with pytest.raises(ValueError, match="profile"):
            lr.normalize_profile(superseded)
