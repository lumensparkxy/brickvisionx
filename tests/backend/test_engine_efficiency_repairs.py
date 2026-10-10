"""Actionable repair policy through actual offline orchestration and recovery."""
from copy import deepcopy
import json

import pytest

from guide2build.engine import exploration
from guide2build.engine.repair_decision import decide_repair
from guide2build.releases.models import canonical
import test_engine_exploration as fixtures
from test_engine_efficiency_context import nested_scene
from test_engine_spatial import group_scene

harness = fixtures.harness


@pytest.fixture
def incremental(harness, monkeypatch):
    harness.job["config"]["efficiency_profile"] = "incremental-v1"
    original = fixtures.synthetic_proposal
    def decode(prompt, ordinal, **kwargs):
        marker = prompt.index('{"set_number"')
        context, end = json.JSONDecoder().raw_decode(prompt[marker:])
        assembly = context["current_own_assembly"]
        if assembly and assembly.get("encoding"):
            assembly["physical_instances"] = [{**assembly["inventory_defaults"], **dict(zip(assembly["inventory_fields"], row, strict=True))}
                                               for row in assembly["physical_instances"]]
            prompt = prompt[:marker] + json.dumps(context) + prompt[marker+end:]
        return original(prompt, ordinal, **kwargs)
    monkeypatch.setattr(fixtures, "synthetic_proposal", decode)
    return harness


def test_camera_uncertainty_and_failed_review_preserve_evidence_without_regeneration(incremental):
    h = incremental
    h.provider.review_mode = "malformed"
    exploration.run_exploration(**h.args)
    assert h.cp["processed_panels"] == 2
    assert [r["attempt_count"] for r in h.cp["instruction_results"]] == [1, 1]
    assert h.cp["model_calls_used"] == 12  # Eight index calls, two proposals, two comparisons.
    assert len(h.renders) == 2
    assert {"source_view", "unsupported_connector", "visual_review_not_run"} <= {
        item["category"] for item in h.cp["provisional_findings"]}
    for result in h.cp["instruction_results"]:
        decision = json.loads((h.directory / result["repair_decisions"][0]["path"]).read_text())
        assert decision["action"] == "continue" and decision["reason"] == "no_actionable_assembly_defect"
        assert decision["remaining_findings"] and decision["camera_and_visual_review"] == "unchanged"
    before = len(h.provider.calls)
    exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == before


@pytest.mark.parametrize("mode", ["none", "bad_delta"])
def test_no_renderable_or_structural_proposal_gets_bounded_repair_then_later_panel(incremental, mode):
    h = incremental
    h.provider.modes[0] = mode
    exploration.run_exploration(**h.args)
    assert [r["attempt_count"] for r in h.cp["instruction_results"]] == [2, 1]
    assert [r["reconstructed"] for r in h.cp["instruction_results"]] == [False, True]
    result = h.cp["instruction_results"][0]
    decisions = [json.loads((h.directory / item["path"]).read_text()) for item in result["repair_decisions"]]
    assert [value["action"] for value in decisions] == ["repair", "continue"]
    assert decisions[-1]["reason"] == "attempt_limit_reached"
    assert "assembly_repair_decision" in next(item["prompt"] for item in h.provider.calls
        if item["key"] == "instruction-0000-attempt-2-proposal")


def test_typed_current_visible_defect_repairs_once_and_keeps_review(incremental, monkeypatch):
    h = incremental
    original = h.provider.call
    def visible(prompt, images, schema, evidence, check):
        value = original(prompt, images, schema, evidence, check)
        key = evidence.parent.name
        if key == "instruction-0000-attempt-1-review":
            value["reviews"][0]["visible_defects"] = [{"domain": "placement", "severity": "major",
                "step_ids": ["synthetic-step-1"], "instance_ids": ["synthetic-part-1"],
                "description": "Original synthetic source has this piece on the opposite side."}]
        return value
    monkeypatch.setattr(h.provider, "call", visible)
    exploration.run_exploration(**h.args, max_panels=1)
    result = h.cp["instruction_results"][0]
    assert result["attempt_count"] == 2 and len(h.renders) == 2
    first = json.loads((h.directory / result["repair_decisions"][0]["path"]).read_text())
    assert first["reason"] == "current_assembly_defect"
    assert first["scope"]["instance_ids"] == ["synthetic-part-1"]
    assert first["scope"]["history_edit_allowed"] is False


def test_repair_scope_expands_whole_group_and_ignores_historical_or_camera_defects():
    raw, _, _ = group_scene()
    candidate = raw.model_dump(mode="json")
    previous = deepcopy(candidate)
    previous["steps"] = candidate["steps"][:-1]
    record = {"candidate": candidate, "rendered": True, "findings": [
        {"code": "nonrigid_group", "severity": "error", "step_id": "attach", "instance_ids": ["strip"]},
        {"code": "exact_coincident_geometry", "severity": "error", "step_id": "one", "instance_ids": ["main"]},
        {"category": "source_view", "step_ids": ["attach"], "description": "poor fit"}]}
    value = decide_repair(record, previous, attempts_used=1, max_attempts=2, calls_remaining=10)
    assert value["action"] == "repair" and len(value["actionable_defects"]) == 1
    assert value["scope"]["instance_ids"] == ["callout", "strip"]
    assert len(value["remaining_findings"]) == 3
    assert decide_repair(record, previous, attempts_used=1, max_attempts=2, calls_remaining=0)["action"] == "continue"


@pytest.mark.parametrize("ambiguous", [False, True])
def test_nested_attachment_repair_never_scopes_only_the_outer_anchor(ambiguous):
    candidate = nested_scene(ambiguous=ambiguous)
    previous = deepcopy(candidate)
    previous["steps"] = previous["steps"][:-1]
    record = {"candidate": candidate, "rendered": True, "findings": [
        {"code": "nonrigid_group", "severity": "error", "step_id": "outer-attach", "instance_ids": ["outer"]}]}
    decision = decide_repair(record, previous, attempts_used=1, max_attempts=2, calls_remaining=10)
    assert decision["action"] == "repair"
    assert decision["scope"]["instance_ids"] == sorted({"inner", "outer", "strip"} | ({"main"} if ambiguous else set()))
    assert decision["scope"]["group_ids"] == ["inner-group", "outer-group"]
    assert decision["scope"]["group_membership_uncertain"] is ambiguous
    assert decision["scope"]["membership_scope"] == ("full_inventory_conservative" if ambiguous else "declared_complete_groups")
    assert decision["scope"]["history_edit_allowed"] is False
    assert decision["remaining_findings"]  # A repair decision does not resolve the defect.


@pytest.mark.parametrize("target", ["repair", "context", "profile"])
def test_resume_rejects_decision_context_or_profile_tampering_before_calls(incremental, target):
    h = incremental
    exploration.run_exploration(**h.args, max_panels=1)
    result = h.cp["instruction_results"][0]
    if target == "profile":
        h.job["config"]["efficiency_profile"] = "legacy"
    else:
        binding = result["repair_decisions"][0] if target == "repair" else result["context_binding"]
        path = h.directory / binding["path"]
        path.write_text(path.read_text() + " ")
    count = len(h.provider.calls)
    with pytest.raises(ValueError, match="changed"):
        exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == count


def test_interruption_after_decision_recovers_without_another_proposal(incremental):
    h = incremental
    save = h.save
    def interrupt(stage, *args):
        save(stage, *args)
        if stage == "exploration_repair_decided":
            raise InterruptedError("Synthetic checkpoint stop")
    with pytest.raises(InterruptedError):
        exploration.run_exploration(**{**h.args, "save": interrupt})
    before = len([item for item in h.provider.calls if item["key"].endswith("proposal")])
    exploration.run_exploration(**h.args, max_panels=1)
    assert len([item for item in h.provider.calls if item["key"].endswith("proposal")]) == before
    assert h.cp["instruction_results"][0]["attempt_count"] == 1


def test_absent_and_explicit_legacy_policy_are_identical_and_stop_propagates(incremental, monkeypatch):
    h = incremental
    config = {key: value for key, value in h.job["config"].items() if key != "efficiency_profile"}
    assert canonical(exploration._policy(config, {}, fixtures.SOURCE, 8)) == canonical(
        exploration._policy({**config, "efficiency_profile": "legacy"}, {}, fixtures.SOURCE, 8))
    from guide2build.engine.runner import WorkerStopped
    original = h.provider.call
    def stop(prompt, images, schema, evidence, check):
        if evidence.parent.name.endswith("proposal"):
            raise WorkerStopped("Synthetic local stop")
        return original(prompt, images, schema, evidence, check)
    monkeypatch.setattr(h.provider, "call", stop)
    with pytest.raises(WorkerStopped):
        exploration.run_exploration(**h.args)
    assert not h.cp.get("instruction_results")
