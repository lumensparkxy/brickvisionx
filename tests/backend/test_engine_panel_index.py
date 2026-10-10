"""Synthetic source-layout tests; these are not reconstruction evidence for a LEGO set."""
from copy import deepcopy
import json

import pytest

from guide2build.engine.contracts import PageIndex, Panel, strict_schema
from guide2build.engine.panel_index import (
    INDEX_PROMPT,
    INDEX_VERSION,
    MAX_REGIONS_PER_PAGE,
    REGION_PROMPT,
    PageIndexV2,
    PanelV2,
    event_registry,
    normalize_index,
    normalize_partial,
)
from guide2build.releases.models import canonical, digest


# Synthetic receipts only. No downloads or actual-guide assertions are made by these tests.
SOURCE = "a" * 64
PIXELS = ["b" * 64, "c" * 64, "d" * 64]


def panel(identity, *, number=1, role="build_event", kind="main", event=None, association=None,
          section="main", status="explicit", uncertainty=None, label="Synthetic source region"):
    return {"section": section, "number": number, "label": label, "bbox": [0, 0, 1, 1], "kind": kind,
        "region_id": identity, "role": role, "event_key": event if event is not None else (
            identity if role == "build_event" else None),
        "associated_event": association, "semantic_status": status,
        "evidence": "Synthetic visible operation or source association.", "uncertainty": uncertainty or []}


def page(number, *regions):
    return {"schema_version": "2.0", "source_sha256": SOURCE, "page_index": number,
            "page_sha256": PIXELS[number], "panels": list(regions), "uncertainty": []}


def receipts(*indexes):
    return [{"page_index": p, "sha256": PIXELS[p], "width": 100, "height": 100} for p in indexes]


def normalize(indexes, *, source_pages=None, partial=False, **kwargs):
    fn = normalize_partial if partial else normalize_index
    return fn(indexes, source_sha256=SOURCE, source_pages=source_pages or receipts(*range(len(indexes))),
              set_number="99999", guide_id="synthetic", **kwargs)


def codes(result):
    return {f["code"] for f in result["findings"]}


def test_explicit_overview_and_associated_detail_are_retained_without_new_build_events():
    raw = [page(0,
        panel("thumbnail", number=1, role="overview", label="1: instruction-like thumbnail"),
        panel("first", number=1, label="finished model overview words do not control routing"),
        panel("first-detail", number=None, role="detail", association={"page_index": 0, "event_key": "first"}),
        panel("second", number=2)),
        page(1, panel("again", number=1, role="repeated_depiction",
                      association={"page_index": 0, "event_key": "first"}))]
    original = deepcopy(raw)
    result = normalize(raw, expected_main_steps=2)
    assert raw == original
    assert [p["panel"]["number"] for p in result["reconstruction_panels"]] == [1, 2]
    assert result["summary"]["declared_regions"] == 5
    assert result["summary"]["source_only_regions"] == 3
    assert len(result["retained_regions"]) == 5
    assert result["raw_page_indexes"] == raw
    assert [len(p["panels"]) for p in result["page_indexes"]] == [4, 1]
    assert "source_main_number_repeated" not in codes(result)
    for retained in result["retained_regions"]:
        assert retained["source"]["source_sha256"] == SOURCE
        assert retained["source"]["page_sha256"] == PIXELS[retained["page_index"]]
        assert retained["raw_index_sha256"] == digest(raw)
    assert result["retained_regions"][2]["associated_region_key"] == result["retained_regions"][1]["region_key"]
    assert result["retained_regions"][4]["associated_region_key"] == result["retained_regions"][1]["region_key"]


def test_genuine_callouts_are_construction_events_even_when_main_region_follows_them():
    raw = [page(0,
        panel("callout-one", number=1, kind="substep", label="2x: build a second physical copy",
              association={"page_index": 0, "event_key": "main-five"}),
        panel("callout-two", number=2, kind="substep", association={"page_index": 0, "event_key": "main-five"}),
        panel("main-five", number=5, kind="attachment"),
        panel("repeat-callout", number=2, kind="substep", role="repeated_depiction",
              association={"page_index": 0, "event_key": "callout-two"}))]
    result = normalize(raw)
    assert [p["panel"]["kind"] for p in result["reconstruction_panels"]] == ["substep", "substep", "attachment"]
    assert result["reconstruction_panels"][0]["associated_region_key"] == result["retained_regions"][2]["region_key"]
    assert result["retained_regions"][3]["disposition"] == "source_only_associated"
    assert result["summary"]["distinct_numbered_mains_by_section"] == {"main": 1}
    assert not result["findings"]


@pytest.mark.parametrize("change", [
    {"role": "ambiguous"}, {"semantic_status": "uncertain"},
    {"uncertainty": ["Could instead be a new assembly operation."]},
    {"evidence": ""}, {"region_id": None}, {"semantic_status": "legacy_unclassified"},
])
def test_ambiguous_or_unsubstantiated_overview_stays_reconstructable(change):
    region = panel("overview", role="overview") | change
    result = normalize([page(0, region)])
    assert len(result["reconstruction_panels"]) == 1
    assert result["retained_regions"][0]["routing_reasons"]
    assert result["findings"]


def test_legacy_adaptation_preserves_all_regions_and_never_guesses_semantic_exemptions():
    legacy = {"panels": [
        {"section": "main", "number": 1, "label": "overview preview thumbnail", "bbox": [0, 0, 1, 1], "kind": "main"},
        {"section": "main", "number": 1, "label": "repeat detail", "bbox": [0, 0, 1, 1], "kind": "substep"}],
        "uncertainty": []}
    result = normalize([PageIndex.model_validate(legacy)])
    assert result["page_indexes"] == [legacy]
    assert len(result["reconstruction_panels"]) == 2
    assert result["summary"]["legacy_unclassified_regions"] == 2
    assert all(r["semantic_status"] == "legacy_unclassified" for r in result["retained_regions"])
    adapted = PanelV2.model_validate(legacy["panels"][0])
    assert adapted.semantic_status == "legacy_unclassified"
    assert adapted.legacy_panel() == Panel.model_validate(legacy["panels"][0])


def test_partial_index_uses_absolute_pages_and_does_not_suppress_an_unseen_future_event():
    early = page(1, panel("detail", role="detail", association={"page_index": 2, "event_key": "build"}))
    result = normalize([early], source_pages=receipts(1, 2), partial=True)
    assert result["indexed_page_indexes"] == [1]
    assert result["summary"]["unindexed_verified_pages"] == [2]
    assert result["reconstruction_panels"][0]["page_index"] == 1
    assert "source_event_association_unresolved" in codes(result)
    later = page(2, panel("build"))
    complete = normalize([early, later], source_pages=receipts(1, 2))
    assert complete["retained_regions"][0]["disposition"] == "source_only_associated"
    assert len(complete["reconstruction_panels"]) == 1
    assert complete["raw_index_sha256"] != result["raw_index_sha256"]


def test_source_only_regions_cannot_anchor_each_other_or_hide_reference_cycles():
    a = panel("a", role="detail", event="a", association={"page_index": 0, "event_key": "b"})
    b = panel("b", role="repeated_depiction", event="b", association={"page_index": 0, "event_key": "a"})
    result = normalize([page(0, a, b)])
    assert len(result["reconstruction_panels"]) == 2
    assert "source_event_association_unproven" in codes(result)


def test_detail_cannot_be_suppressed_by_a_later_invalid_build_event_parent():
    detail = panel("detail", role="detail", association={"page_index": 0, "event_key": "bad-main"})
    invalid = panel("bad-main", association={"page_index": 0, "event_key": "other"})
    other = panel("other", number=2)
    result = normalize([page(0, detail, invalid, other)])
    assert len(result["reconstruction_panels"]) == 3
    assert result["retained_regions"][0]["disposition"] == "reconstruct"
    assert "source_build_event_parent_invalid" in codes(result)


def test_ambiguous_duplicate_event_identity_retains_both_events_and_their_detail():
    result = normalize([page(0, panel("a", event="same"), panel("b", event="same"),
        panel("detail", role="detail", association={"page_index": 0, "event_key": "same"}))])
    assert len(result["reconstruction_panels"]) == 3
    assert "source_event_key_ambiguous" in codes(result)
    assert "source_event_association_unresolved" in codes(result)


def test_missing_or_cross_section_association_stays_in_construction_with_findings():
    result = normalize([page(0, panel("base", section="model"),
        panel("detail", role="detail"), panel("other", section="figure", role="repeated_depiction",
              association={"page_index": 0, "event_key": "base"}))])
    assert len(result["reconstruction_panels"]) == 3
    assert {"source_event_association_missing", "source_event_section_mismatch"} <= codes(result)


@pytest.mark.parametrize("mutation,match", [
    ({"source_sha256": "e" * 64}, "verified guide"),
    ({"page_sha256": "e" * 64}, "pixel hash"),
    ({"page_index": 2}, "verified guide"),
    ({"schema_version": "3.0"}, "schema_version"),
])
def test_rejects_stale_or_foreign_source_binding(mutation, match):
    with pytest.raises(ValueError, match=match):
        normalize([page(0, panel("one")) | mutation])


def test_reference_cannot_escape_the_verified_page_scope_or_name_another_guide():
    with pytest.raises(ValueError, match="outside this verified guide"):
        normalize([page(0, panel("detail", role="detail", association={"page_index": 2, "event_key": "other"}))])
    with pytest.raises(ValueError, match="guide_id"):
        PageIndexV2.model_validate(page(0, panel("detail", role="detail",
            association={"page_index": 0, "event_key": "other", "guide_id": "foreign"})))


@pytest.mark.parametrize("bbox", [
    [0, 0, float("nan"), 1], [0, 0, float("inf"), 1], [0, 0, 1, 2],
    [0.5, 0, 0.5, 1], [1, 0, 0, 1], [False, 0, 1, 1], ["0", 0, 1, 1],
    [0, 0, 10**400, 1],
])
def test_v2_bounds_are_finite_normalized_numbers_not_coerced_strings_or_booleans(bbox):
    with pytest.raises(ValueError):
        PageIndexV2.model_validate(page(0, panel("one") | {"bbox": bbox}))


@pytest.mark.parametrize("number", [True, "1", 0, -1, 100_001])
def test_v2_main_numbers_are_strict_bounded_positive_integers(number):
    with pytest.raises(ValueError):
        PageIndexV2.model_validate(page(0, panel("one", number=number)))


def test_page_and_region_identity_are_unique_ordered_and_bounded():
    with pytest.raises(ValueError, match="Duplicate page-local"):
        normalize([page(0, panel("same"), panel("same"))])
    with pytest.raises(ValueError, match="unique increasing"):
        normalize([page(0), page(0)], source_pages=receipts(0, 1))
    with pytest.raises(ValueError, match="unique increasing"):
        normalize([page(1), page(0)], source_pages=receipts(0, 1))
    with pytest.raises(ValueError, match="unique increasing"):
        normalize([page(0)], source_pages=receipts(0, 0))
    with pytest.raises(ValueError, match="bounded region"):
        normalize([page(0, *[panel(f"r-{i}") for i in range(MAX_REGIONS_PER_PAGE + 1)])])


def test_complete_scope_rejects_missing_pages_while_partial_reports_them():
    with pytest.raises(ValueError, match="missing verified"):
        normalize([page(0)], source_pages=receipts(0, 1))
    result = normalize([page(0)], source_pages=receipts(0, 1), partial=True)
    assert result["summary"]["complete_supplied_page_coverage"] is False
    assert result["summary"]["index_coverage_is_source_verified"] is False


def test_cross_page_main_order_duplicates_and_gaps_are_retained_as_quality_findings():
    source = [page(0, panel("first", number=1), panel("fourth", number=4)),
              page(1, panel("second", number=2), panel("second-again", number=2))]
    result = normalize(source, expected_main_steps=4)
    assert [r["panel"]["number"] for r in result["reconstruction_panels"]] == [1, 4, 2, 2]
    assert {"source_main_number_gap", "source_main_number_reversed", "source_main_number_repeated",
            "source_main_coverage_mismatch"} <= codes(result)
    mismatch = next(f for f in result["findings"] if f["code"] == "source_main_coverage_mismatch")
    assert mismatch["missing_numbers"] == [3]


def test_independent_sections_may_restart_printed_numbering():
    result = normalize([page(0, panel("figure-one", section="figure")),
                        page(1, panel("model-one", section="model"))])
    assert "source_main_number_repeated" not in codes(result)
    assert "source_main_number_reversed" not in codes(result)


def test_receipt_defaults_and_legacy_absolute_batch_mapping_are_explicitly_unclassified():
    legacy = {"panels": [PanelV2.model_validate(panel("legacy")).legacy_panel().model_dump(mode="json")], "uncertainty": []}
    complete = normalize([legacy], source_pages=[{"sha256": PIXELS[0]}])
    assert complete["indexed_page_indexes"] == [0]
    partial = normalize([legacy], source_pages=receipts(2), partial=True)
    assert partial["indexed_page_indexes"] == [2]
    assert partial["retained_regions"][0]["semantic_status"] == "legacy_unclassified"
    with pytest.raises(ValueError, match="one corresponding"):
        normalize([legacy], source_pages=receipts(0, 1), partial=True)


def test_page_uncertainty_and_empty_pages_are_retained_without_fabricating_instructions():
    source = page(0)
    source["uncertainty"] = ["This synthetic region could not be read."]
    result = normalize([source])
    assert result["raw_page_indexes"] == [source]
    assert not result["reconstruction_panels"]
    assert {"source_regions_empty", "source_index_uncertainty"} <= codes(result)


def test_normalization_is_deterministic_hash_bound_and_all_legacy_views_validate():
    source = [page(0, panel("one"), panel("overview", role="overview", number=None))]
    result = normalize(source)
    assert result == normalize(source)
    assert result["version"] == INDEX_VERSION
    claimed = result.pop("normalization_sha256")
    assert claimed == digest(result)
    for legacy in result["page_indexes"]:
        PageIndex.model_validate(legacy)
    source[0]["panels"][1]["evidence"] += " Additional visible source detail."
    assert normalize(source)["normalization_sha256"] != claimed
    assert "3D poses" in INDEX_PROMPT
    assert REGION_PROMPT in INDEX_PROMPT
    assert "PageIndexV2" not in REGION_PROMPT
    assert "Return " not in REGION_PROMPT


def test_model_schema_requires_additive_fields_and_has_bounded_homogeneous_arrays():
    schema = strict_schema(PageIndexV2)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    definition = schema["$defs"]["PanelV2"]
    assert set(definition["required"]) == set(definition["properties"])
    assert {"role", "associated_event", "semantic_status", "evidence"} <= set(definition["required"])
    assert definition["properties"]["bbox"]["items"]["type"] == "number"
    assert definition["properties"]["bbox"]["minItems"] == definition["properties"]["bbox"]["maxItems"] == 4
    assert schema["properties"]["panels"]["maxItems"] == MAX_REGIONS_PER_PAGE
    assert "prefixItems" not in json.dumps(schema)


def test_event_registry_exposes_only_explicit_source_keys_with_parent_and_pixel_binding():
    result = normalize([page(0,
        panel("callout", kind="substep", association={"page_index": 0, "event_key": "main"}),
        panel("main"), panel("overview", role="overview"),
        panel("legacy", status="legacy_unclassified"), panel("unsure", status="uncertain"),
        panel("duplicate-one", event="duplicate"), panel("duplicate-two", event="duplicate")),
        page(1, panel("repeat", role="repeated_depiction", association={"page_index": 0, "event_key": "main"}),
             panel("second", number=2))], expected_main_steps=3)
    before = deepcopy(result)
    registry = event_registry(result)
    assert result == before
    assert [(row["page_index"], row["event_key"]) for row in registry["events"]] == [
        (0, "callout"), (0, "main"), (1, "second")]
    assert registry["events"][0]["associated_event"] == {"page_index": 0, "event_key": "main"}
    assert registry["events"][0]["kind"] == "substep"
    assert registry["source"]["source_sha256"] == SOURCE
    assert registry["normalization_sha256"] == result["normalization_sha256"]
    assert registry["source_pages_sha256"] == digest(result["source_pages"])
    assert registry["coverage"]["ineligible_region_counts"] == {
        "nonbuilding_region": 2, "legacy_unclassified": 1, "uncertain_or_unresolved": 3}
    assert registry["coverage"]["complete_known_event_key_coverage"]
    assert registry["coverage"]["source_coverage_verified"] is False
    claimed = registry.pop("registry_sha256")
    assert claimed == digest(registry)
    registry["events"][0]["bbox"][0] = 0.2
    assert result == before


def test_event_registry_selects_latest_events_but_returns_original_source_order():
    result = normalize([page(0, panel("first"), panel("second", number=2)),
                        page(1, panel("third", number=3), panel("fourth", number=4))])
    registry = event_registry(result, max_events=2)
    assert [row["event_key"] for row in registry["events"]] == ["third", "fourth"]
    assert registry == event_registry(result, max_events=2)
    coverage = registry["coverage"]
    assert (coverage["eligible_events"], coverage["included_events"], coverage["omitted_eligible_events"]) == (4, 2, 2)
    assert not coverage["complete_known_event_key_coverage"]
    assert coverage["omitted_event_keys_sha256"] == digest([
        {"page_index": 0, "event_key": "first"}, {"page_index": 0, "event_key": "second"}])


def test_event_registry_enforces_utf8_byte_bound_and_retains_full_evidence_digest():
    source = [panel(f"event-{index}", number=index+1) for index in range(30)]
    for row in source:
        row["evidence"] = "Visible source evidence 磚塊 " * 60
    result = normalize([page(0, *source)])
    registry = event_registry(result, max_bytes=4_000)
    assert len(canonical(registry)) <= 4_000
    assert 0 < len(registry["events"]) < 30
    keys = [row["event_key"] for row in registry["events"]]
    assert keys == [row["event_key"] for row in source][-len(keys):]
    assert registry["coverage"]["omitted_eligible_events"] == 30-len(keys)
    for row in registry["events"]:
        assert row["evidence_truncated"] and len(row["evidence"].encode("utf-8")) <= 320
        assert row["evidence_sha256"] == digest(source[0]["evidence"])


def test_event_registry_preserves_partial_and_legacy_unknown_coverage():
    empty = normalize([], source_pages=receipts(0, 1), partial=True)
    empty_registry = event_registry(empty)
    assert empty_registry["events"] == []
    assert empty_registry["coverage"]["unindexed_verified_page_count"] == 2
    partial = normalize([page(1, panel("second"))], source_pages=receipts(1, 2), partial=True)
    assert event_registry(partial)["coverage"]["unindexed_verified_page_count"] == 1
    legacy = {"panels": [PanelV2.model_validate(panel("not-proof")).legacy_panel().model_dump(mode="json")], "uncertainty": []}
    registry = event_registry(normalize([legacy], source_pages=receipts(2), partial=True))
    assert registry["events"] == []
    assert registry["coverage"]["ineligible_region_counts"] == {"legacy_unclassified": 1}
    assert registry["coverage"]["source_coverage_verified"] is False


@pytest.mark.parametrize("mutation", ["missing_hash", "retained_edit", "rehash_retained_edit", "source_hash", "page_pixels"])
def test_event_registry_rejects_unbound_or_rehashed_semantic_receipts(mutation):
    result = normalize([page(0, panel("main"))])
    if mutation == "missing_hash":
        result.pop("normalization_sha256")
    elif mutation in {"retained_edit", "rehash_retained_edit"}:
        result["retained_regions"][0]["declared_event_key"] = "invented"
    elif mutation == "source_hash":
        result["source"]["source_sha256"] = "f" * 64
    else:
        result["source_pages"][0]["sha256"] = "f" * 64
    if mutation in {"rehash_retained_edit", "source_hash", "page_pixels"}:
        result["normalization_sha256"] = digest({key: value for key, value in result.items() if key != "normalization_sha256"})
    with pytest.raises(ValueError):
        event_registry(result)


@pytest.mark.parametrize("kwargs", [
    {"max_events": True}, {"max_events": 65}, {"max_events": -1}, {"max_events": 2.0},
    {"max_bytes": True}, {"max_bytes": 0}, {"max_bytes": 24_001}, {"max_bytes": 1},
])
def test_event_registry_rejects_unbounded_or_unrepresentable_receipts(kwargs):
    with pytest.raises(ValueError):
        event_registry(normalize([page(0, panel("main"))]), **kwargs)


def test_zero_event_registry_budget_keeps_explicit_omission_evidence():
    registry = event_registry(normalize([page(0, panel("main"))]), max_events=0)
    assert registry["events"] == []
    assert registry["coverage"]["omitted_eligible_events"] == 1
    assert not registry["coverage"]["complete_known_event_key_coverage"]
