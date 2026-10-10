"""Synthetic prompt/recovery checks; no inference or assembly-accuracy claim."""
from copy import deepcopy
import hashlib
import json
import re

import pytest

from guide2build.engine import attachment_prompt, event_scope_prompt, exploration
from guide2build.engine.instruction import SequenceEvidence, validate_sequence
from guide2build.engine.store import execution_config
from guide2build.releases.models import SceneV2, digest
import test_engine_exploration as fixtures


harness = fixtures.harness
LEGACY_LEAD = "Construct this indexed main instruction and all printed callouts/attachments. "
# Captured by running the unchanged original synthetic harness before this slice.
# Bind initial and repair prompts, review/index prompts, and the entire policy.
LEGACY_INDEX_HASHES = [
    "faa3c8a39a61398572e62f7661f61e938839ac39fc94dec93242c5d633fb582e",
    "2a58bc98c6411b6eece3a80597e903a2fd9b514b48d18d9655179272540c678c",
    "b49aa8708f2e582df11edab475461a2a4765ea9ff241cb3512df3952ce9dd75b",
    "84d7b5474ba83761b109062fa8dcfac0945d51254cbdf2a497cb725fdcebe97b",
    "89a548f5ce92db65b1a4c04506f6dea2922dc36583a9ac42eeca781ef0178a6b",
    "c17fd0ebd2c59ff22543166d37a5a4937fde81805a49b10ae5c6f8975af801f6",
    "ee55b483033f45616b5555b1a22b1f9a6e9feea9e2a9f1b376a07fc8b9ac7afd",
    "7242b8e9522b49517c783f5c8dc770d4816d0991689219255505a0f378dc2edc",
]
LEGACY_REVIEW_HASH = "f02c29a2d3ec0878f31a47857dfa1cf8a65f4e3ce9aa53efc7ba6b57392fad09"


def context(prompt):
    return json.JSONDecoder().raw_decode(prompt[prompt.index('{"set_number"'):])[0]


@pytest.mark.parametrize(("profile", "policy_hash", "proposal_hashes"), [
    ("baseline", "a3f54e1c506e7a4a9471c130a160e25506a08033365344026f183a19dd7da34c", [
        "ff2dc749dcf522972f7fa340fa802651f9fbebbfd996964cdd0da36963fe6ba3",
        "704df20f8ac930aa47f129add2aa5fbc674d56c7ad97b26c98e01da60e113c54"]),
    ("attachment-reasoning", "a5ed93c2194b5f2aa9a8282854967465a7286ea06b8ac55958abc290beabdc6a", [
        "16702ec866afbd338d79e65d6991b5aeab0ad7bab908ab8c848ea02414bc05ee",
        "c2489a4876925e7f8545595b7bf7d32f7ccc4a472b5cd753a2b3f203a461fc71"]),
])
def test_legacy_prompts_and_nonruntime_policies_remain_byte_identical(harness, profile, policy_hash, proposal_hashes):
    h = harness
    if profile != "baseline":
        h.job["config"]["proposal_profile"] = profile
    exploration.run_exploration(**h.args, max_panels=1)
    expected = {f"index-{i:04d}": value for i, value in enumerate(LEGACY_INDEX_HASHES)}
    for i, value in enumerate(proposal_hashes, 1):
        expected[f"instruction-0000-attempt-{i}-proposal"] = value
        expected[f"instruction-0000-attempt-{i}-review"] = LEGACY_REVIEW_HASH
    assert {call["key"]: hashlib.sha256(call["prompt"].encode()).hexdigest()
            for call in h.provider.calls} == expected
    policy = h.cp["exploration_policy"]
    assert policy["runtime_choice"] == {"provider": "google_adk", "model": h.job["config"]["model"],
        "thinking_level": "medium", "provider_timeout": 120}
    historical_policy = dict(policy, runtime_choice={"model": h.job["config"]["model"], "reasoning": "high"})
    assert digest(historical_policy) == policy_hash
    assert h.cp["model_calls_used"] == 12


def test_event_profile_is_explicit_and_changes_only_proposal_wording(harness):
    from guide2build.engine.contracts import strict_schema
    from guide2build.engine.delta import SceneDelta

    h = harness
    original_config = deepcopy(h.job["config"])
    normalized = execution_config(original_config | {"proposal_profile": event_scope_prompt.PROFILE})
    assert normalized["proposal_profile"] == "event-scoped"
    assert "proposal_profile" not in original_config
    with pytest.raises(ValueError, match="explore"):
        execution_config({"proposal_profile": event_scope_prompt.PROFILE})
    h.job["config"]["proposal_profile"] = event_scope_prompt.PROFILE
    schema = strict_schema(exploration.exploration_proposal_type())
    exploration.run_exploration(**h.args, max_panels=1)
    proposal_calls = [call for call in h.provider.calls if call["key"].endswith("proposal")]
    assert len(proposal_calls) == 2
    for call in proposal_calls:
        text = call["prompt"]
        assert LEGACY_LEAD not in text
        assert event_scope_prompt.CONSTRUCTION_INSTRUCTION in text
        assert text.count(event_scope_prompt.PROMPT_SUFFIX) == 1
        data = context(text)
        assert data["source_region_rule"] == event_scope_prompt.SOURCE_REGION_RULE
        assert data["required_callouts"] == []
        assert data["scene_delta_schema"] == SceneDelta.model_json_schema()
        assert attachment_prompt.PROMPT_SUFFIX not in text
    for call in h.provider.calls:
        if not call["key"].endswith("proposal"):
            assert event_scope_prompt.PROMPT_SUFFIX not in call["prompt"]
            expected = (LEGACY_REVIEW_HASH if call["key"].endswith("review") else
                        LEGACY_INDEX_HASHES[int(call["key"].split("-")[1])])
            assert hashlib.sha256(call["prompt"].encode()).hexdigest() == expected
    expected_policy = exploration._policy(original_config, {}, fixtures.SOURCE, h.args["page_count"])
    expected_policy["proposal_profile"] = event_scope_prompt.binding()
    assert h.cp["exploration_policy"] == expected_policy
    assert strict_schema(exploration.exploration_proposal_type()) == schema
    assert h.cp["model_calls_used"] == 12
    assert {call["inputs"]["model"] for call in h.cp["exploration_calls"].values()} == {h.provider.model}
    assert {call["inputs"]["thinking_level"] for call in h.cp["exploration_calls"].values()} == {"high"}


@pytest.mark.parametrize("change", ["CONSTRUCTION_INSTRUCTION", "SOURCE_REGION_RULE", "PROMPT_SUFFIX", "VERSION",
                                    "baseline", "attachment-reasoning"])
def test_event_profile_resume_rejects_any_wording_version_or_profile_drift(harness, monkeypatch, change):
    h = harness
    h.job["config"]["proposal_profile"] = event_scope_prompt.PROFILE
    exploration.run_exploration(**h.args, max_panels=1)
    before = deepcopy(h.cp)
    count = len(h.provider.calls)
    if change in attachment_prompt.PROFILES:
        h.job["config"]["proposal_profile"] = change
    else:
        monkeypatch.setattr(event_scope_prompt, change, getattr(event_scope_prompt, change) + " changed")
    with pytest.raises(ValueError, match="changed on resume"):
        exploration.run_exploration(**h.args)
    assert h.cp == before and len(h.provider.calls) == count


@pytest.mark.parametrize("profile", ["baseline", "attachment-reasoning"])
def test_existing_run_cannot_silently_adopt_event_profile(harness, profile):
    h = harness
    h.job["config"]["proposal_profile"] = profile
    exploration.run_exploration(**h.args, max_panels=1)
    before = deepcopy(h.cp)
    count = len(h.provider.calls)
    h.job["config"]["proposal_profile"] = event_scope_prompt.PROFILE
    with pytest.raises(ValueError, match="changed on resume"):
        exploration.run_exploration(**h.args)
    assert h.cp == before and len(h.provider.calls) == count


def _panels(original):
    base = original["panels"][0]
    main = {**base, "number": 7, "label": "Synthetic grouped operation", "region_id": "main-event",
            "event_key": "main-event", "bbox": [0.05, 0.4, 0.95, 0.95]}
    thumbnail = {**base, "number": None, "label": "Unestablished synthetic thumbnail", "kind": "substep",
        "region_id": "thumbnail", "role": "ambiguous", "event_key": None, "semantic_status": "uncertain",
        "bbox": [0.05, 0.05, 0.4, 0.25], "evidence": "Synthetic thumbnail has no established construction action.",
        "uncertainty": ["Its role is unresolved."]}
    callouts = [{**base, "number": number, "label": f"Synthetic local operation {number}", "kind": "substep",
        "region_id": f"local-{number}", "event_key": f"local-{number}",
        "associated_event": {"page_index": 0, "event_key": "main-event"}, "bbox": bbox}
        for number, bbox in [(1, [0.1, 0.5, 0.45, 0.9]), (2, [0.55, 0.5, 0.9, 0.9])]]
    return [thumbnail, main, *callouts]


def _grouped_proposal(reply, data):
    delta = json.loads(reply["delta_json"])
    part = delta["new_instances"][0]
    step = delta["new_steps"][0]
    delta["new_instances"], delta["new_steps"], reply["sequence"] = [], [], []
    visible = []
    for callout in data["required_callouts"]:
        panel = callout["panel"]
        label = str(panel["number"])
        identity = "synthetic-local-" + label
        source = {**part["source"], "bbox": panel["bbox"]}
        # A quantity has multiple physical instances within the actual operation;
        # it does not create extra callout snapshots or labels.
        copies = [f"synthetic-copy-{label}-{copy}" for copy in ("a", "b")]
        visible.extend(copies)
        delta["new_instances"].extend({**part, "instance_id": name, "source": source} for name in copies)
        delta["new_steps"].append({**step, "step_id": identity, "main_step_number": data["panel"]["number"],
            "substep_label": label, "source": source, "action": "build_subassembly",
            "assembly_group_id": "synthetic-detached-group", "introduced_instance_ids": copies,
            "active_instance_ids": copies, "visible_instance_ids": list(visible),
            "poses": {name: {"position_ldu": [20 * i, 8 * panel["number"], 0],
                             "quaternion_xyzw": [0, 0, 0, 1]} for i, name in enumerate(copies)}})
        reply["sequence"].append({"step_id": identity, "kind": "numbered_callout", "printed_label": label,
                                 "bbox": panel["bbox"], "explanation": "Synthetic printed local operation."})
    reply["delta_json"] = json.dumps(delta)
    return reply


def test_ambiguous_null_event_stays_unresolved_then_real_grouped_callouts_run(harness, monkeypatch):
    h = harness
    h.job["config"].update(proposal_profile=event_scope_prompt.PROFILE, efficiency_profile="incremental-v1")
    h.provider.modes[0] = "none"
    h.provider.review_mode = "pass"
    original = h.provider.call
    def source_scoped(prompt, images, schema, evidence, check):
        reply = original(prompt, images, schema, evidence, check)
        key = evidence.parent.name
        if key.startswith("index-"):
            reply["panels"] = _panels(reply) if key == "index-0000" else []
        elif key.endswith("proposal"):
            data = context(prompt)
            if data["panel"]["number"] is None:
                assert data["required_callouts"] == []
                assert len(data["full_page_index"]["panels"]) == 4  # Siblings remain visible as context.
                reply["blockers"] = [f"Source {fixtures.SOURCE}, page 0, bbox {data['panel']['bbox']}: "
                                     "the requested thumbnail establishes no construction action."]
                assert reply["delta_json"] is None
            else:
                reply = _grouped_proposal(reply, data)
        return reply
    monkeypatch.setattr(h.provider, "call", source_scoped)
    exploration.run_exploration(**h.args)
    first, main = h.cp["instruction_results"]
    assert first["outcome"] == "unresolved" and first["step_ids"] == [] and first["attempt_count"] == 2
    assert first["findings"] and "no construction action" in first["findings"][0]["description"]
    assert main["outcome"] == "provisional" and main["attempt_count"] == 1
    assert main["step_ids"] == ["synthetic-local-1", "synthetic-local-2"]
    scene = SceneV2.model_validate(h.cp["candidate"])
    assert len(scene.instances) == 4 and len(scene.steps) == 2
    proposal = json.loads((h.directory / "exploration/instructions/0001/attempt-1/proposal.json").read_bytes())
    validate_sequence(scene, None, [SequenceEvidence.model_validate(item) for item in proposal["sequence"]])
    regions = json.loads((h.directory / "source-regions.json").read_bytes())
    queue = exploration._exploration_event_queue(regions)
    assert len(regions["retained_regions"]) == 4 and len(queue) == 2
    assert queue[0]["grouped_callouts"] == []
    assert [item["panel"]["number"] for item in queue[1]["grouped_callouts"]] == [1, 2]
    assert h.cp["model_calls_used"] == 12 and len(h.renders) == 1
    count = len(h.provider.calls)
    exploration.run_exploration(**h.args)
    assert len(h.provider.calls) == count  # Same-profile recovery consumes no new fake calls.


def test_standalone_local_event_does_not_gain_sibling_callouts(harness, monkeypatch):
    h = harness
    h.job["config"]["proposal_profile"] = event_scope_prompt.PROFILE
    h.provider.modes[0] = "none"
    original = h.provider.call
    def orphan(prompt, images, schema, evidence, check):
        reply = original(prompt, images, schema, evidence, check)
        if evidence.parent.name == "index-0000":
            callouts = _panels(reply)[2:]
            for callout in callouts:
                callout["associated_event"] = None
            reply["panels"] = callouts
        return reply
    monkeypatch.setattr(h.provider, "call", orphan)
    exploration.run_exploration(**h.args, max_panels=1)
    proposals = [call for call in h.provider.calls if call["key"].endswith("proposal")]
    for call in proposals:
        data = context(call["prompt"])
        assert data["panel"]["kind"] == "substep" and data["panel"]["number"] == 1
        assert data["required_callouts"] == [] and len(data["full_page_index"]["panels"]) == 2
        assert "including when empty" in data["source_region_rule"]
    assert h.cp["processed_panels"] == 1 and h.cp["instruction_results"][0]["outcome"] == "unresolved"


def test_all_event_wording_is_bound_and_has_no_benchmark_answers():
    wording = {"construction_instruction": event_scope_prompt.CONSTRUCTION_INSTRUCTION,
               "source_region_rule": event_scope_prompt.SOURCE_REGION_RULE,
               "prompt_suffix": event_scope_prompt.PROMPT_SUFFIX}
    encoded = json.dumps(wording, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert event_scope_prompt.binding() == {"name": "event-scoped", "version": "event-scope-v1",
                                           "prompt_sha256": hashlib.sha256(encoded).hexdigest()}
    text = "\n".join(wording.values())
    assert not re.search(r"\d|https?://|(?:parts|var|evidence)/|\.(?:dat|ldr|mpd|json)\b", text)
    assert not re.search(r"\b(?:wheel|tire|wing|airplane|canopy|tail)\b", text, re.IGNORECASE)
    assert "delta_json=null" in text and "source hash, page and bbox" in text
    assert attachment_prompt.PROFILES == ("baseline", "attachment-reasoning", "event-scoped")
