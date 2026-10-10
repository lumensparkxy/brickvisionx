"""Synthetic feedback tests: prompt focus does not prove reconstruction accuracy."""
from copy import deepcopy
import json

import pytest

from guide2build.engine import repair_feedback as feedback
from guide2build.engine.repair_feedback import compact_feedback, prompt_feedback
from guide2build.releases.models import canonical, digest


SOURCE = {"page_index": 2, "bbox": [0.1, 0.2, 0.4, 0.6], "source_sha256": "a" * 64}


def diagnostic(step="old", identities=("base", "wing"), *, code="aabb_overlap_candidate", **extra):
    return {"code": code, "severity": "review", "step_id": step, "instance_ids": list(identities),
            "message": "Bounds overlap; intended engagement and penetration are not distinguished.", **extra}


def visible(step="now", *, domain="placement", identities=("wing",), **extra):
    return {"category": "source_visible_defect", "origin": "agent_source_comparison", "domain": domain,
            "severity": "major", "step_ids": [step], "instance_ids": list(identities),
            "description": "The indicated arm is on the opposite side of the source panel.", **extra}


def note(step="old", identities=("wing",), **extra):
    return {"category": "connection", "step_ids": [step], "instance_ids": list(identities),
            "reason": "The underside receiver remains occluded.",
            "alternatives": ["Use the upper receiver.", "Use the lower receiver."], **extra}


def test_repeated_history_is_grouped_and_current_action_precedes_aabb_without_mutation():
    records = [diagnostic(f"old-{i}", ordinal=i, page_index=i // 3) for i in range(120)]
    records.extend([deepcopy(records[0]), visible(), visible(domain="identity", identities=("new",))])
    before = deepcopy(records)
    result = compact_feedback(records, ["now"], ["wing"], input_truncated=False)
    assert records == before
    assert result["input"]["sha256"] == digest(records)
    assert result["input"]["canonical_bytes"] == len(canonical(records))
    assert [group["priority_class"] for group in result["findings"]] == [
        "identity_or_quantity", "source_visible_defect", "broad_phase"]
    repeated = result["findings"][-1]
    assert repeated["occurrence_count"] == 121
    assert repeated["evidence"]["distinct_input_records"] == 120
    assert repeated["evidence"]["step_ids_count"] == 120
    assert repeated["preview"]["truncated"]
    assert result["selection"]["exact_duplicate_occurrences"] == 1
    assert result["selection"]["grouped_repeated_occurrences"] == 120
    assert result["selection"]["represented_occurrences"] == 123
    assert result["selection"]["omitted_occurrences"] == 0
    assert result["findings"][1]["finding"]["origin"] == "agent_source_comparison"
    # The result has no mutable aliases to the caller's retained evidence.
    result["findings"][0]["finding"]["description"] = "changed preview"
    result["findings"][0]["instance_ids"].append("injected")
    assert records == before


def test_selection_and_group_ids_stable_under_reordering_but_exact_input_hash_changes():
    records = [diagnostic("a"), diagnostic("b"), visible(), note(), visible(domain="count")]
    first = compact_feedback(records, ["now"], ["wing", "base"])
    second = compact_feedback(list(reversed(records)), ["now", "now"], ["base", "wing"])
    assert first["input"]["sha256"] != second["input"]["sha256"]
    assert first["context"] == second["context"]
    assert first["findings"] == second["findings"]
    assert first["selection"] == second["selection"]
    assert compact_feedback(records, ["now"], ["wing", "base"]) == first
    assert first["receipt_sha256"] == digest({key: value for key, value in first.items() if key != "receipt_sha256"})


def test_old_unresolved_dependency_is_kept_ahead_of_current_broad_phase_noise():
    records = [diagnostic("now", (f"a-{i}", f"b-{i}")) for i in range(40)]
    records += [note(identities=("affected-child",)), visible(identities=("affected-child",))]
    result = compact_feedback(records, ["now"], max_groups=2)
    assert [entry["relevance"] for entry in result["findings"]] == ["current_step", "dependency"]
    dependency = result["findings"][1]
    assert dependency["uncertainty"] == "explicit"
    assert dependency["finding"]["reason"] == records[-2]["reason"]
    assert dependency["finding"]["alternatives"] == records[-2]["alternatives"]
    assert result["context"]["inferred_dependency_ids_count"] == 1
    assert result["selection"]["omitted_groups"] == 40


def test_explicit_affected_ids_and_dependency_steps_work_without_inferred_correspondence():
    records = [note(identities=("child",)), note("earlier-callout", (), reason="Mould uncertain."),
               note("unrelated", ("other",), reason="Separate unresolved identity.")]
    result = compact_feedback(records, ["now"], ["child"], dependency_step_ids=["earlier-callout"], max_groups=2)
    assert {entry["relevance"] for entry in result["findings"]} == {"dependency"}
    assert {entry["finding"]["reason"] for entry in result["findings"]} == {
        "The underside receiver remains occluded.", "Mould uncertain."}
    assert result["selection"]["uncertainty_counts"]["explicit"] == {"groups": 3, "included_groups": 2, "omitted_groups": 1}


def test_aabb_pairs_do_not_expand_dependencies_to_every_historical_piece():
    records = [diagnostic("now", ("unrelated-a", "unrelated-b")), note(identities=("unrelated-a",))]
    result = compact_feedback(records, ["now"])
    assert result["context"]["inferred_dependency_ids_count"] == 0
    assert result["findings"][0]["relevance"] == "historical"


@pytest.mark.parametrize("code", ["exact_coincident_geometry", "floating_supported_instance", "nonrigid_group",
                                  "historical_movement", "wrong_side", "missing_part", "quantity_mismatch"])
def test_specific_current_errors_precede_repeated_aabb(code):
    records = [diagnostic("now"), diagnostic("now", code=code, severity="error")]
    result = compact_feedback(records, ["now"], max_groups=1)
    assert result["findings"][0]["finding"]["code"] == code
    assert result["findings"][0]["finding"]["severity"] == "error"


def test_different_evidence_values_and_alternatives_are_not_deduped():
    records = [note(source=SOURCE), note(source={**SOURCE, "bbox": [0.2, 0.2, 0.4, 0.6]}),
               note(source=SOURCE, alternatives=["Use the lower receiver.", "Use the upper receiver."]),
               note(source=SOURCE, reason="The upper receiver is visibly absent."),
               diagnostic(distance_ldu=1), diagnostic(distance_ldu=2),
               diagnostic(nominal_contact=True), diagnostic(nominal_contact=False)]
    result = compact_feedback(records, ["old"])
    assert result["selection"]["available_groups"] == 8
    assert result["selection"]["grouped_repeated_occurrences"] == 0


def test_source_observation_part_and_colour_uncertainty_preserved():
    finding = {"category": "part_identity_uncertainty", "step_ids": ["now"], "instance_ids": [],
               "description": "Two source-supported designs remain plausible.", "observation_id": "callout-a",
               "source": SOURCE, "candidate_part_ids": ["3020", "3022"],
               "candidate_color_codes": {"3020": ["1", "15"]},
               "uncertainties": ["Underside is hidden.", "Transparent tint is unresolved."],
               "scope": "source_part_observation"}
    result = compact_feedback([finding], ["now"])
    shown = result["findings"][0]
    assert shown["uncertainty"] == "explicit"
    assert not shown["preview"]["truncated"]
    for key in ("source", "candidate_part_ids", "candidate_color_codes", "uncertainties", "observation_id", "scope"):
        assert shown["finding"][key] == finding[key]


def test_source_binding_is_not_shortened_when_long_alternatives_force_a_small_preview():
    record = note("now", source=SOURCE, reason="Reason " * 2000,
                  alternatives=["Alternative " * 300 for _ in range(32)],
                  uncertainties=["Hidden feature " * 300 for _ in range(32)])
    before = deepcopy(record)
    result = compact_feedback([record], ["now"])
    shown = result["findings"][0]
    assert shown["preview"]["truncated"]
    assert shown["finding"]["source"] == SOURCE
    assert shown["evidence"]["source_value_sha256"] == digest(SOURCE)
    assert shown["finding"]["alternatives"] and shown["finding"]["uncertainties"]
    shown["finding"]["source"]["bbox"][0] = 0.9
    assert record == before


def test_oversized_unknown_source_value_is_hash_bound_and_omitted_not_partly_rewritten():
    source = {**SOURCE, "extra_untrusted_metadata": "x" * 5000}
    shown = compact_feedback([note("now", source=source)], ["now"])["findings"][0]
    assert "source" not in shown["finding"]
    assert shown["evidence"]["source_value_sha256"] == digest(source)
    assert shown["preview"]["truncated"]


def test_record_with_current_and_old_occurrences_retains_current_step_in_preview():
    records = [diagnostic(f"old-{i}") for i in range(100)] + [diagnostic("now")]
    shown = compact_feedback(records, ["now"])["findings"][0]
    assert shown["relevance"] == "current_step"
    assert shown["step_ids"][0] == "now"
    assert shown["evidence"]["step_ids_sha256"] == digest(sorted(["now", *(f"old-{i}" for i in range(100))]))


@pytest.mark.parametrize("upstream", [None, False, True])
def test_empty_and_truncated_input_never_means_clean(upstream):
    result = compact_feedback([], ["now"], input_truncated=upstream)
    assert result["input"]["upstream_truncated"] is upstream
    assert result["input"]["completeness"] == {None: "unknown", False: "supplied_list_only", True: "truncated"}[upstream]
    assert result["findings"] == []
    assert "do not establish a clean assembly" in result["scope"]
    assert "pass" not in result and "approved" not in result
    assert result["input"]["sha256"] == digest([])


def test_explicit_resolutions_count_but_do_not_reappear_as_repair_targets():
    records = [note(resolution="resolved"), note(resolution="dismissed"), note(resolution="unresolved")]
    result = compact_feedback(records, ["now"], ["wing"])
    assert len(result["findings"]) == 1
    assert result["findings"][0]["finding"]["resolution"] == "unresolved"
    assert result["selection"]["resolved_groups_not_selected"] == 2
    assert result["selection"]["resolved_occurrences_not_selected"] == 2
    assert result["selection"]["omitted_occurrences"] == 2
    assert result["input"]["count"] == 3


@pytest.mark.parametrize("max_bytes", [4096, 8192, 16384])
def test_whole_receipt_utf8_and_escaping_budget_includes_metadata_and_hash(max_bytes):
    records = [visible(identities=(f"wing-{i}",), description=("🧱\\\"\n" * 1000),
                       alternatives=[f"Alternative {n} " + "色" * 200 for n in range(32)]) for i in range(40)]
    result = compact_feedback(records, ["now"], max_bytes=max_bytes, input_truncated=True)
    assert len(canonical(result)) <= max_bytes
    assert 0 < len(result["findings"]) <= 24
    assert result["selection"]["omitted_groups"] > 0
    assert result["selection"]["preview_truncated_groups"] == len(result["findings"])
    assert all(entry["finding"]["alternatives"] for entry in result["findings"])
    assert result["selection"]["uncertainty_counts"]["explicit"]["groups"] == 40
    assert result["input"]["sha256"] == digest(records)
    assert json.loads(canonical(result)) == result
    assert result["receipt_sha256"] == digest({key: value for key, value in result.items() if key != "receipt_sha256"})


def test_category_summary_is_bounded_without_losing_occurrence_totals():
    records = [{"category": f"category-{i:02}-" + "x" * 400, "description": "Unclassified source finding."} for i in range(60)]
    result = compact_feedback(records, [], max_bytes=4096)
    summary = result["selection"]
    assert len(summary["category_counts"]) == 8
    assert summary["other_category_count"] == 52
    assert sum(row["occurrences"] for row in summary["category_counts"]) + summary["other_category_occurrences"] == 60
    assert all(row["category_sha256"] for row in summary["category_counts"])
    assert len(canonical(result)) <= 4096


def test_context_accepts_actual_8192_instance_bound_without_unbounded_receipt():
    result = compact_feedback([note(identities=("part-8191",))], ["now"], [f"part-{i}" for i in range(8192)])
    assert result["context"]["affected_instance_ids_count"] == 8192
    assert result["findings"][0]["relevance"] == "dependency"
    assert len(canonical(result)) < 4096
    with pytest.raises(ValueError, match="8192"):
        compact_feedback([], [], [f"part-{i}" for i in range(8193)])


@pytest.mark.parametrize("options", [{"max_groups": 0}, {"max_groups": 25}, {"max_groups": True},
    {"max_bytes": 4095}, {"max_bytes": 16385}, {"max_bytes": 16384.0}, {"input_truncated": 1}])
def test_invalid_limits_are_rejected(options):
    with pytest.raises(ValueError):
        compact_feedback([], [], **options)


@pytest.mark.parametrize("records", [[None], [{"severity": {}}], [{"step_ids": ""}],
    [{"instance_ids": "wing"}], [{"step_id": False}], [{"message": float("nan")}],
    [{"confidence": float("inf")}], [{1: "invalid key"}], [{"message": object()}],
    [{"message": "\ud800"}], [{"count": 2 ** 300}], [{"message": "x" * (128 * 1024 + 1)}]])
def test_malformed_json_and_ambiguous_scope_fail_closed(records):
    with pytest.raises(ValueError):
        compact_feedback(records, [])


def test_cycles_depth_and_infinite_iterators_are_rejected_without_sampling():
    cycle = {"category": "bad"}
    cycle["source"] = cycle
    with pytest.raises(ValueError, match="cycle"):
        compact_feedback([cycle], [])
    nested = {}
    for _ in range(15):
        nested = {"nested": nested}
    with pytest.raises(ValueError, match="depth"):
        compact_feedback([nested], [])
    def infinite():
        while True:
            yield {}
    with pytest.raises(ValueError, match="JSON objects"):
        compact_feedback(infinite(), [])


def test_explicit_resource_bounds_fail_instead_of_hashing_a_prefix(monkeypatch):
    with pytest.raises(ValueError, match="20000"):
        compact_feedback([{}] * 20_001, [])
    monkeypatch.setattr(feedback, "MAX_INPUT_BYTES", 1000)
    with pytest.raises(ValueError, match="byte limit"):
        compact_feedback([{"message": "x" * 1000}], [])
    monkeypatch.setattr(feedback, "MAX_INPUT_BYTES", 16 * 1024 * 1024)
    monkeypatch.setattr(feedback, "MAX_INPUT_NODES", 10)
    with pytest.raises(ValueError, match="node/depth"):
        compact_feedback([{"details": [None] * 11}], [])


def test_twenty_thousand_distinct_findings_stay_bounded_and_have_exact_omission_counts():
    records = [diagnostic(f"step-{i}", (f"part-{i}", "root")) for i in range(20_000)]
    result = compact_feedback(records, ["step-19999"])
    assert result["input"]["count"] == 20_000
    assert result["selection"]["available_groups"] == 20_000
    assert result["selection"]["grouped_repeated_occurrences"] == 0
    assert result["selection"]["omitted_occurrences"] + len(result["findings"]) == 20_000
    assert result["findings"][0]["step_ids"] == ["step-19999"]
    assert len(canonical(result)) <= 16384


def test_localized_connection_repair_precedes_generic_camera_notes_without_becoming_a_proven_error():
    guidance = {"category": "connection", "step_ids": ["now"], "instance_ids": ["new-plate", "old-arm"],
        "description": "The new plate conflicts with the inherited arm; the source does not resolve which pose caused it.",
        "correction": "Preserve history and investigate relative registration in a new snapshot.",
        "uncertainties": ["The responsible inherited pose remains unknown."]}
    records = [{"category": "source_view", "step_ids": ["now"], "instance_ids": [],
                "description": f"Camera note {i}", "correction": "Inspect the projection."} for i in range(20)]
    records += [diagnostic("now", code="exact_coincident_geometry", severity="error"),
                visible(), visible(domain="identity", identities=("new-part",)), guidance]
    result = compact_feedback(records, ["now"], max_groups=4)
    assert [row["priority_class"] for row in result["findings"]] == [
        "identity_or_quantity", "structural_or_side", "source_visible_defect", "source_connection_guidance"]
    selected = result["findings"][-1]
    assert selected["uncertainty"] == "explicit"
    assert selected["finding"]["description"] == guidance["description"]
    assert selected["finding"]["correction"] == guidance["correction"]
    assert "severity" not in selected["finding"] and "origin" not in selected["finding"]


@pytest.mark.parametrize("overrides", [{"step_ids": []}, {"instance_ids": []}, {"correction": ""},
    {"correction": None}, {"correction": "Review the indicated official source and provisional reconstruction."}])
def test_anonymous_or_generic_connection_notes_do_not_gain_repair_priority(overrides):
    record = {"category": "connection", "step_ids": ["now"], "instance_ids": ["arm"],
              "description": "Contact remains hidden.", "correction": "Inspect the named receiving arm.", **overrides}
    result = compact_feedback([record], ["now"])
    assert result["findings"][0]["priority_class"] == "review_or_uncertainty"


def test_prompt_view_preserves_selected_evidence_without_opaque_group_metadata_or_input_mutation():
    records = [diagnostic(f"prior-{i}") for i in range(20)] + [note("now", source=SOURCE), visible()]
    receipt = compact_feedback(records, ["now"], ["wing"], input_truncated=True)
    before = deepcopy(receipt)
    prompt = prompt_feedback(receipt)
    assert prompt["receipt_sha256"] == receipt["receipt_sha256"]
    assert prompt["input"]["sha256"] == digest(records)
    assert prompt["input"]["upstream_truncated"] is True
    assert prompt["input"]["completeness"] == "truncated"
    assert "config" not in prompt and "context" not in prompt
    assert "category_counts_sha256" not in prompt["selection"]
    assert len(prompt["findings"]) == len(receipt["findings"])
    for shown, archived in zip(prompt["findings"], receipt["findings"], strict=True):
        for key in ("finding", "relevance", "priority_class", "occurrence_count", "step_ids", "instance_ids", "uncertainty"):
            assert shown[key] == archived[key]
        assert "group_id" not in shown and "evidence" not in shown
        assert shown["preview"]["omitted_step_ids"] == archived["evidence"]["step_ids_count"] - len(archived["step_ids"])
    assert len(canonical(prompt)) < len(canonical(receipt)) <= 16384
    prompt["findings"][0]["finding"]["description"] = "Only this detached prompt changes"
    prompt["selection"]["omitted_groups"] = -1
    assert receipt == before


def test_prompt_view_is_deterministic_and_independently_bounded_for_large_unicode_receipt():
    receipt = compact_feedback([visible(identities=(f"part-{i}",), description="🧱" * 4000) for i in range(40)], ["now"])
    view = prompt_feedback(receipt)
    assert prompt_feedback(json.loads(canonical(receipt))) == view
    assert len(canonical(view)) <= 16384
    assert view["selection"]["omitted_groups"] == receipt["selection"]["omitted_groups"]
    assert view["selection"]["preview_truncated_groups"] == len(view["findings"])


@pytest.mark.parametrize("mutation", ["finding", "receipt_hash", "missing_hash", "version", "counts", "scope_count", "oversized"])
def test_prompt_view_rejects_tampering_or_malformed_receipts(mutation):
    receipt = compact_feedback([visible()], ["now"])
    if mutation == "finding":
        receipt["findings"][0]["finding"]["description"] += " changed"
    elif mutation == "receipt_hash":
        receipt["receipt_sha256"] = "0" * 64
    elif mutation == "missing_hash":
        del receipt["receipt_sha256"]
    else:
        if mutation == "version":
            receipt["version"] = "unknown-version"
        elif mutation == "counts":
            receipt["selection"]["included_groups"] = 2
        elif mutation == "scope_count":
            receipt["findings"][0]["evidence"]["step_ids_count"] = 0
        elif mutation == "oversized":
            receipt["scope"] = "x" * 17000
        receipt["receipt_sha256"] = digest({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    with pytest.raises(ValueError):
        prompt_feedback(receipt)


def test_empty_prompt_view_carries_unknown_completeness_not_clean_status():
    prompt = prompt_feedback(compact_feedback([], []))
    assert prompt["findings"] == [] and prompt["input"]["completeness"] == "unknown"
    assert "do not establish a clean assembly" in prompt["scope"]


def test_prompt_preserves_complete_deep_but_bounded_source_value():
    source = {"page_index": 2}
    for _ in range(9):
        source = {"nested": source}
    receipt = compact_feedback([note("now", source=source)], ["now"])
    prompt = prompt_feedback(receipt)
    assert prompt["findings"][0]["finding"]["source"] == source
