"""Severity-aware uncertain evidence; original synthetic subjects only."""
from itertools import permutations

import pytest

from guide2build.engine import exploration, localized_review as lr
from guide2build.engine.repair_decision import decide_repair
from guide2build.engine.repair_feedback import compact_feedback, prompt_feedback
from test_engine_localized_review import SOURCE, defect, record, review, scene


def candidates(localization="one_of", before="minor", after="major", gain="camera"):
    subjects = ("head", "hand-a") if localization == "one_of" else ()
    head = defect("Small known head issue", severity="minor")
    initial = record("initial", [head, defect("Possible small head or hand issue", subjects,
        localization=localization, severity=before)])
    changed = scene()
    changed["steps"][0]["poses"]["head"]["position_ldu"][1] = 90
    later = record("later", [head, defect("Unresolved issue on head or hand", subjects,
        localization=localization, severity=after)], changed)
    if gain == "camera":
        initial["selection_evidence"]["camera"]["units"][0].update(rms_pixels=3., max_error_pixels=4.)
        later["selection_evidence"]["camera"]["units"][0].update(rms_pixels=.1, max_error_pixels=.2)
    else:
        for item, score in [(initial, .1), (later, .9)]:
            item["selection_evidence"]["images"] = {"current": {"comparison_scope_sha256": "a" * 64,
                "source_mask_sha256": "b" * 64, "occlusion_mask_sha256": "c" * 64, "ranking_score": score}}
    return initial, later


@pytest.mark.parametrize("localization", ["one_of", "unlocalized"])
@pytest.mark.parametrize("gain", ["camera", "image"])
@pytest.mark.parametrize("reverse", [False, True])
def test_worsened_uncertain_severity_cannot_win_a_projection_tiebreak(localization, gain, reverse):
    pair = candidates(localization, gain=gain)
    _, receipt = exploration._select_candidates(list(reversed(pair)) if reverse else list(pair))
    assert receipt["status"] == "unresolved_alternatives"
    assert set(receipt["frontier_ids"]) == {"initial", "later"}
    assert receipt["comparisons"][0]["reason"] == "worsened_unresolved_severity_cannot_establish_superiority"
    for profile in receipt["profiles"].values():
        assert profile["defect_counts"]["placement"] == {"major": 0, "minor": 1}
    assert receipt["profiles"]["initial"]["unresolved_evidence"]["highest_severity"] == "minor"
    assert receipt["profiles"]["later"]["unresolved_evidence"]["highest_severity"] == "major"


@pytest.mark.parametrize("before,after", [("major", "major"), ("major", "minor"), ("minor", "minor")])
def test_unchanged_or_reduced_uncertain_severity_allows_supported_camera_preference(before, after):
    selected, receipt = exploration._select_candidates(list(candidates(before=before, after=after)))
    assert selected["selection_id"] == "later" and receipt["status"] == "preferred_by_evidence"
    assert receipt["comparisons"][0]["reason"] == "numeric_camera_residuals"
    assert selected["selected_quality"]["unresolved_localization"]


def test_narrowing_subjects_does_not_compensate_for_new_major_severity():
    first, _ = candidates(localization="unlocalized")
    _, later = candidates(localization="one_of")
    _, receipt = exploration._select_candidates([first, later])
    assert receipt["status"] == "unresolved_alternatives"
    assert receipt["comparisons"][0]["reason"] == "worsened_unresolved_severity_cannot_establish_superiority"


def test_highest_uncertain_scope_severity_is_order_and_wording_invariant():
    values = [defect(severity="minor"),
        defect("Small uncertain issue", ("head", "hand-a"), localization="one_of", severity="minor"),
        defect("Major uncertain issue", ("head", "hand-a"), localization="one_of"),
        defect("Same concern in other words", ("hand-a", "head"), localization="one_of")]
    expected = lr.uncertainty_summary([review(values)], {"current"})
    assert expected["scope_count"] == 1
    assert expected["severity_scope_counts"]["placement"] == {"major": 1, "minor": 0}
    for order in permutations(values):
        assert lr.uncertainty_summary([review(list(order))], {"current"}) == expected
        groups = lr.group_defects([review(list(order))], {"current"})
        assert len(groups) == 1 and groups[0]["severity"] == "minor"
        assert groups[0]["unresolved_severity"] == "major"


def test_uncertain_severity_reaches_quality_repair_and_compact_feedback():
    _, candidate = candidates()
    selected, _ = exploration._select_candidates([candidate])
    quality = exploration._quality_context(selected["selected_quality"])
    assert quality["unresolved_evidence"]["highest_severity"] == "major"
    decision = decide_repair(selected, None, attempts_used=1, max_attempts=2, calls_remaining=10)
    possible = next(item for item in decision["actionable_defects"] if item.get("localization") == "one_of")
    assert possible["severity"] == "major" and possible["instance_ids"] == []
    assert decision["scope"]["alternative_subjects"][0]["severity"] == "major"
    assert decision["scope"]["unresolved_evidence"]["severity_scope_counts"]["placement"]["major"] == 1
    finding = next(item for item in selected["visual_review"]["visible_defects"] if item["localization"] == "one_of")
    shown = prompt_feedback(compact_feedback([finding | {"category": "source_visible_defect"}], ["current"]))["findings"][0]
    assert shown["finding"]["severity"] == "major" and shown["uncertainty"] == "explicit"
    assert shown["finding"]["subject_scope"]["unresolved_severity"] == "major"
    assert shown["finding"]["subject_scope"]["identified_count"] == 0


def test_uncertainty_comparison_rule_is_bound_before_resume(monkeypatch):
    config = {"execution_policy": "explore", "review_profile": lr.PROFILE,
              "model": "gemini-3.8-flash", "thinking_level": "high", "max_model_calls": 300}
    checkpoint = {}
    value = exploration._policy(config, checkpoint, SOURCE, 8)
    assert value["source_review_profile"]["uncertainty_preference_version"] == lr.UNCERTAINTY_VERSION
    monkeypatch.setattr(lr, "UNCERTAINTY_VERSION", "changed-rule")
    with pytest.raises(ValueError, match="policy"):
        exploration._policy(config, checkpoint, SOURCE, 8)
