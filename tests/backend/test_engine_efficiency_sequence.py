"""Unnumbered attachments must not spend a repair on a missing printed number."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from guide2build.engine import exploration
import test_engine_efficiency_repairs as fixtures

harness = fixtures.harness
incremental = fixtures.incremental


@pytest.mark.parametrize("kind,number,parent,snapshot,mismatch", [
    ("attachment", None, None, 3, False),
    ("attachment", None, 3, 3, False),
    ("attachment", None, 3, 2, True),
    ("substep", 1, 3, 3, False),
    ("substep", 1, 3, 1, True),
    ("substep", 1, None, 3, False),
    ("main", 3, None, 3, False),
    ("main", 3, None, 2, True),
    ("attachment", 3, None, 2, True),
])
def test_source_numbers_distinguish_parent_from_callout(kind, number, parent, snapshot, mismatch):
    panel = {"kind": kind, "number": number, "parent_main_step_number": parent}
    assert exploration._indexed_sequence_mismatch(panel, [SimpleNamespace(main_step_number=snapshot)],
        incremental=True) is mismatch


def test_legacy_sequence_diagnostic_remains_frozen():
    unnumbered = {"kind": "attachment", "number": None, "parent_main_step_number": 3}
    callout = {"kind": "substep", "number": 1, "parent_main_step_number": 3}
    assert exploration._indexed_sequence_mismatch(unnumbered, [SimpleNamespace(main_step_number=3)])
    assert not exploration._indexed_sequence_mismatch(callout, [SimpleNamespace(main_step_number=1)])


def test_valid_unnumbered_attachment_reaches_later_instructions_without_repair(incremental, monkeypatch):
    h = incremental
    original = h.provider.call

    def attachment(prompt, images, schema, evidence, check):
        value = original(prompt, images, schema, evidence, check)
        key = evidence.parent.name
        if key == "index-0001":
            value["panels"][0].update(number=None, label="Synthetic unnumbered attachment", kind="attachment")
        elif key.startswith("instruction-0001-") and key.endswith("-proposal"):
            delta = json.loads(value["delta_json"])
            callout = delta["new_steps"][0]
            callout.update(main_step_number=1, substep_label="1", action="build_subassembly",
                assembly_group_id="synthetic-callout", visible_instance_ids=["synthetic-part-2"])
            attached = deepcopy(callout)
            attached.update(step_id="synthetic-attach", substep_label=None, action="attach_subassembly",
                introduced_instance_ids=[], visible_instance_ids=["synthetic-part-1", "synthetic-part-2"], poses={})
            delta["new_steps"].append(attached)
            value["delta_json"] = json.dumps(delta)
            value["sequence"] = [
                {"step_id": "synthetic-step-2", "kind": "numbered_callout", "printed_label": "1",
                 "bbox": [0, 0, 1, 1], "explanation": "Synthetic explicit callout."},
                {"step_id": "synthetic-attach", "kind": "attachment", "printed_label": None,
                 "bbox": [0, 0, 1, 1], "explanation": "Synthetic unnumbered attachment into existing main."},
            ]
        return value

    monkeypatch.setattr(h.provider, "call", attachment)
    exploration.run_exploration(**h.args)
    result = h.cp["instruction_results"][1]
    assert result["attempt_count"] == 1 and h.cp["processed_panels"] == 2
    assert not [f for f in result["findings"] if f.get("code") in {
        "sequence_contract_violation", "indexed_sequence_mismatch"}]
    assert not exploration._source_coverage_findings(h.cp["page_indexes"], h.cp["candidate"], h.args["source_hash"])


def test_wrong_printed_main_number_still_requests_a_bounded_repair(incremental, monkeypatch):
    h = incremental
    original = h.provider.call

    def wrong_number(prompt, images, schema, evidence, check):
        value = original(prompt, images, schema, evidence, check)
        if evidence.parent.name == "instruction-0000-attempt-1-proposal":
            delta = json.loads(value["delta_json"])
            delta["new_steps"][0]["main_step_number"] = 7
            value["delta_json"] = json.dumps(delta)
        return value

    monkeypatch.setattr(h.provider, "call", wrong_number)
    exploration.run_exploration(**h.args)
    result = h.cp["instruction_results"][0]
    assert result["attempt_count"] == 2 and h.cp["processed_panels"] == 2
    decision = json.loads((h.directory / result["repair_decisions"][0]["path"]).read_text())
    assert decision["action"] == "repair"
    assert "indexed_sequence_mismatch" in {item["code"] for item in decision["actionable_defects"]}
