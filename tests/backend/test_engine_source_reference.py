"""Offline source-singleton contract tests; no provider, network or target scenes."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from guide2build.engine import exploration, source_reference as sr
from guide2build.engine.contracts import strict_schema
from guide2build.engine.corrections import CorrectionRequest, fork_correction
from guide2build.engine.store import execution_config
from guide2build.releases.models import canonical, digest
from test_engine_corrections import seed_job, correction_request, write_json

SOURCE = "a" * 64


def proposal(page=0):
    return {"delta_json": None, "blockers": [], "observations": [], "connections": [],
            "roots": [], "sequence": [], "source_views": [], "placement_hints": [],
            "part_observations": [{"observation_id": "synthetic-observation", "source": {
                "page_index": page, "source_sha256": SOURCE, "bbox": [0, 0, .2, .2]},
                "quantity": 1, "shape_cues": ["synthetic plate"], "colour_description": "red",
                "candidates": [{"part_id": "synthetic", "reason": "Synthetic evidence", "color_codes": ["4"]}],
                "uncertainties": []}]}


class Provider:
    model = "gemini-3.8-flash"
    thinking_level = "high"

    def __init__(self, response):
        self.response, self.calls = response, []

    def call(self, prompt, images, schema, evidence, check):
        check()
        self.calls.append({"prompt": prompt, "schema": deepcopy(schema), "images": [p.name for p in images]})
        evidence.mkdir(parents=True)
        (evidence / "prompt.txt").write_text(prompt)
        (evidence / "schema.json").write_text(json.dumps(schema))
        return deepcopy(self.response)


def call_fixture(tmp_path, response=None):
    image = tmp_path / "page.png"
    image.write_bytes(b"original synthetic image input")
    cp = {"model_calls_used": 0, "local_model_calls_used": 0}
    provider = Provider(response or proposal())
    calls = exploration.ExplorationCalls(provider, tmp_path, cp, lambda *_: None,
        SimpleNamespace(check=lambda: None), {"max_model_calls": 10})
    return calls, provider, cp, [image]


def test_schema_singletons_only_valid_invalid_and_no_legacy_mutation():
    model = exploration.exploration_proposal_type()
    legacy = strict_schema(model)
    original = canonical(legacy)
    bound = sr.bound_proposal_schema(model, source_hash=SOURCE, page_index=0, page_count=8)
    expected = deepcopy(legacy)
    expected["$defs"]["SourcePanel"]["properties"]["source_sha256"]["enum"] = [SOURCE]
    expected["$defs"]["SourcePanel"]["properties"]["page_index"]["enum"] = [0]
    assert bound == expected and canonical(strict_schema(model)) == original
    Draft202012Validator.check_schema(bound)
    sr.validate_bound_response(proposal(), bound)
    for key, value in [("source_sha256", "b" * 64), ("page_index", 1)]:
        wrong = proposal()
        wrong["part_observations"][0]["source"][key] = value
        assert not list(Draft202012Validator(legacy).iter_errors(wrong))
        with pytest.raises(ValueError, match="Bound proposal schema"):
            sr.validate_bound_response(wrong, bound)
    for values in [("bad", 0, 8), (SOURCE, True, 8), (SOURCE, 8, 8), (SOURCE, 0, False)]:
        with pytest.raises(ValueError):
            sr.bound_proposal_schema(model, source_hash=values[0], page_index=values[1], page_count=values[2])
    opaque = proposal()
    opaque["delta_json"] = json.dumps({"untrusted_source_hash": "b" * 64})
    sr.validate_bound_response(opaque, bound)  # The string is deliberately not rewritten or certified.
    assert opaque["delta_json"] == json.dumps({"untrusted_source_hash": "b" * 64})


def test_config_policy_scope_normalization_and_existing_policy_cannot_upgrade():
    base = {"execution_policy": "explore", "model": "gemini-3.8-flash", "thinking_level": "high"}
    assert execution_config(base) == execution_config(base | {"source_reference_profile": "legacy"})
    selected = execution_config(base | {"source_reference_profile": sr.PROFILE, "quality_profile": "alpha"})
    assert selected["source_reference_profile"] == sr.PROFILE
    for config in [base | {"source_reference_profile": "unknown"},
                   {"source_reference_profile": sr.PROFILE},
                   base | {"source_reference_profile": sr.PROFILE, "generation_mode": "alpha_fast"}]:
        with pytest.raises(ValueError, match="source reference"):
            execution_config(config)
    checkpoint = {}
    original = exploration._policy(base, checkpoint, SOURCE, 8)
    assert "source_reference_profile" not in original
    before = deepcopy(checkpoint)
    with pytest.raises(ValueError, match="changed on resume"):
        exploration._policy(selected, checkpoint, SOURCE, 8)
    assert checkpoint == before
    new = exploration._policy(selected, {}, SOURCE, 8)
    assert new["source_reference_profile"] == sr.binding(exploration.exploration_proposal_type())
    assert new["max_model_calls"] == original["max_model_calls"] == 3
    assert new["runtime_choice"] == original["runtime_choice"]
    assert {k: v for k, v in new.items() if k != "source_reference_profile"} == original


def test_actual_call_receipts_replay_same_schema_reject_drift_and_bound_result(tmp_path):
    calls, provider, cp, images = call_fixture(tmp_path)
    model = exploration.exploration_proposal_type()
    schema = sr.bound_proposal_schema(model, source_hash=SOURCE, page_index=0, page_count=8)
    result = calls.call("proposal", "Unchanged source prompt", images, model, schema_override=schema)
    target = tmp_path / "exploration/calls/proposal"
    inputs = json.loads((target / "inputs.json").read_text())
    assert inputs["schema_sha256"] == digest(schema)
    retained = {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
    assert calls.call("proposal", "Unchanged source prompt", images, model, schema_override=schema) == result
    assert len(provider.calls) == cp["model_calls_used"] == 1
    assert retained == {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
    for changed in [None, sr.bound_proposal_schema(model, source_hash=SOURCE, page_index=1, page_count=8)]:
        with pytest.raises(ValueError, match="image/schema/runtime"):
            calls.call("proposal", "Unchanged source prompt", images, model, schema_override=changed)
    # Even a self-consistent private test receipt cannot bypass the saved bound schema.
    wrong = json.loads((target / "result.json").read_text())
    wrong["part_observations"][0]["source"]["source_sha256"] = "b" * 64
    exploration._write(target / "result.json", wrong)
    receipt = json.loads((target / "receipt.json").read_text())
    receipt["result_sha256"] = hashlib.sha256((target / "result.json").read_bytes()).hexdigest()
    exploration._write(target / "receipt.json", receipt)
    cp["exploration_calls"]["proposal"]["receipt_sha256"] = hashlib.sha256((target / "receipt.json").read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="Bound proposal schema"):
        calls.call("proposal", "Unchanged source prompt", images, model, schema_override=schema)
    assert len(provider.calls) == cp["model_calls_used"] == 1


def test_fresh_invalid_source_is_retained_integrity_failure_not_rewritten(tmp_path):
    bad = proposal()
    bad["part_observations"][0]["source"]["page_index"] = 1
    calls, provider, cp, images = call_fixture(tmp_path, bad)
    model = exploration.exploration_proposal_type()
    bound = sr.bound_proposal_schema(model, source_hash=SOURCE, page_index=0, page_count=8)
    with pytest.raises(ValueError, match="Bound proposal schema"):
        calls.call("proposal", "Unchanged prompt", images, model, schema_override=bound)
    target = tmp_path / "exploration/calls/proposal"
    receipt = json.loads((target / "receipt.json").read_text())
    assert receipt["error"]["code"] == "integrity_failure" and not (target / "result.json").exists()
    assert provider.response == bad and bad["part_observations"][0]["source"]["page_index"] == 1
    with pytest.raises(ValueError, match="schema or integrity"):
        calls.call("proposal", "Unchanged prompt", images, model, schema_override=bound)
    assert len(provider.calls) == cp["model_calls_used"] == 1


def test_trial_binds_only_verified_target_without_prompt_change(tmp_path):
    captures = []
    class Capture:
        def call(self, key, prompt, images, model, **options):
            captures.append({"key": key, "prompt": prompt, "images": images, "options": options})
            value = proposal(49)
            return model.model_validate(value)
    for selected in ["legacy", sr.PROFILE]:
        trial = tmp_path / selected / "attempt-1"
        result = exploration._trial(job={"config": {"execution_policy": "explore", "source_reference_profile": selected}},
            previous=None, ordinal=47, page_index=49, panel={}, page_count=60, source_hash=SOURCE,
            pages_dir=tmp_path, directory=tmp_path, trial=trial, calls=Capture(), prompt="Identical target/context prompt",
            images=[tmp_path / "page-049.png", tmp_path / "page-048.png"], heartbeat=SimpleNamespace(check=lambda: None), feedback={})
        assert result["candidate"] is None
    assert captures[0]["prompt"] == captures[1]["prompt"] and captures[0]["images"] == captures[1]["images"]
    assert captures[0]["options"] == {}
    fields = captures[1]["options"]["schema_override"]["$defs"]["SourcePanel"]["properties"]
    assert fields["source_sha256"]["enum"] == [SOURCE] and fields["page_index"]["enum"] == [49]


def test_restart_only_correction_control_preserves_parent_calls_and_lineage(tmp_path, scene_data):
    store, identity, scene, directory = seed_job(tmp_path, scene_data,
        config={"model": "gemini-3.8-flash", "thinking_level": "high", "execution_policy": "explore", "max_model_calls": 10})
    parent = store.get(identity)
    parent_files = {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    invalid = json.loads(correction_request(tmp_path, scene, source_reference_profile=sr.PROFILE).read_text())
    class NoStore:
        def get(self, *_):
            pytest.fail("Invalid source-reference control reached job/source access")
    bad_path = tmp_path / "invalid.json"
    for request in [invalid, invalid | {"source_reference_profile": "legacy"}, invalid | {"source_reference_profile": "unknown"}]:
        write_json(bad_path, request)
        with pytest.raises(ValueError):
            fork_correction(NoStore(), "never-read", bad_path, "invalid")
    path = correction_request(tmp_path, scene, commands=[], restart_main_step=2,
        guidance=["Review the official target source."], source_reference_profile=sr.PROFILE)
    request = json.loads(path.read_text())
    request["commands"] = []
    write_json(path, request)
    assert CorrectionRequest.model_validate(request).source_reference_profile == sr.PROFILE
    child = fork_correction(store, identity, path, "source-schema-restart")
    assert child["config"]["source_reference_profile"] == sr.PROFILE
    assert child["config"].get("review_profile", "legacy") == "legacy"
    assert child["checkpoint"]["model_calls_used"] == child["checkpoint"]["inherited_model_calls_used"] == 5
    assert child["checkpoint"]["local_model_calls_used"] == 0
    assert child["config"]["max_model_calls"] == 10
    lineage = child["checkpoint"]["correction_lineage"][-1]
    assert lineage["requested_controls"]["source_reference_profile"] == sr.PROFILE
    assert "source_reference_profile" in lineage["exploration_policy_transition"]["changed_fields"]
    assert lineage["unassisted"] is False
    assert store.get(identity) == parent
    assert parent_files == {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def test_cli_profile_is_explicit_and_default_bytes_omit_it(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "tools"))
    spec = importlib.util.spec_from_file_location("source_reference_cli", root / "tools/engine.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    captured = []
    class Store:
        def __init__(self, path):self.data_dir = path
        def enqueue(self, set_number, guide_id, config):
            captured.append(execution_config(config))
            return {"id": "synthetic", "set_number": set_number, "guide_id": guide_id, "state": "queued"}
    monkeypatch.setattr(cli, "EngineStore", Store)
    monkeypatch.setattr(cli, "cached_receipt", lambda *_: None)
    base = ["engine.py", "--data-dir", str(tmp_path), "enqueue", "--set", "30669", "--guide", "alt-02"]
    for extra in [[], ["--source-reference-profile", "legacy"], ["--execution-policy", "explore", "--source-reference-profile", sr.PROFILE]]:
        monkeypatch.setattr(sys, "argv", base + extra)
        cli.main()
    assert captured[0] == captured[1] and "source_reference_profile" not in captured[0]
    assert captured[2]["source_reference_profile"] == sr.PROFILE
    assert captured[2]["model"] == "gemini-3.8-flash" and captured[2]["thinking_level"] == "medium"
    for extra in [["--source-reference-profile", "unknown"], ["--source-reference-profile", sr.PROFILE]]:
        monkeypatch.setattr(sys, "argv", base + extra)
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 2
    assert len(captured) == 3
