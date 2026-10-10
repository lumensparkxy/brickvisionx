"""Synthetic request/lease checks; these never invoke Google or prove LEGO accuracy."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sys

import pytest

from guide2build.core.environment import load_local_environment
from guide2build.engine.runtime import ModelCallBudgetExhausted, reserve_model_call, runtime_choice
from guide2build.engine.store import EngineStore, execution_config


@pytest.mark.parametrize("mode", ["strict", "explore", "alpha_fast"])
def test_new_jobs_freeze_adk_defaults_and_never_persist_credentials(tmp_path, mode):
    store = EngineStore(tmp_path)
    config = ({"generation_mode": mode, "quality_profile": "alpha"} if mode == "alpha_fast"
              else {"execution_policy": mode})
    job = store.enqueue("30669", "alt-02", config)
    assert {key: job["config"][key] for key in
        ("provider", "model", "thinking_level", "provider_timeout", "max_model_calls")} == {
        "provider": "google_adk", "model": "gemini-3.8-flash", "thinking_level": "medium",
        "provider_timeout": 120, "max_model_calls": 3}
    assert job["checkpoint"] == {}
    for key in ("GOOGLE_API_KEY", "api_key", "credentials", "access_token"):
        with pytest.raises(ValueError, match="Credentials"):
            store.enqueue("30669", "alt-02", config | {key: "synthetic-secret"})
    assert len(store.list()) == 1


@pytest.mark.parametrize("config", [{"provider": "codex"}, {"thinking_level": "xhigh"},
    {"provider_timeout": float("nan")}, {"provider_timeout": True}, {"max_model_calls": False},
    {"reasoning": "high"}])
def test_invalid_adk_choices_are_rejected_before_enqueue(config):
    with pytest.raises(ValueError):
        execution_config(config)


def test_failed_and_interrupted_requests_remain_charged_across_retry_and_cancel(tmp_path):
    store = EngineStore(tmp_path)
    job = store.enqueue("30669", "alt-02", {})
    claimed = store.claim("first", job_id=job["id"])
    checkpoint = claimed["checkpoint"]
    def save(stage):
        checkpoint["stage"] = stage
        store.checkpoint(job["id"], "first", checkpoint)
    for number in range(3):
        request = reserve_model_call(job["config"], checkpoint, save, key=f"synthetic-{number}",
                                     store=store, job_id=job["id"])
        request.update(status="failed" if number < 2 else "reserved")
    store.cancel(job["id"])
    with pytest.raises(InterruptedError):
        save("cancelled")
    store.retry(job["id"])
    resumed = store.claim("second", job_id=job["id"])
    assert resumed["checkpoint"]["model_calls_used"] == 3
    assert store.lineage_model_calls_used(job["id"]) == 3
    with pytest.raises(ModelCallBudgetExhausted):
        reserve_model_call(resumed["config"], resumed["checkpoint"], lambda stage: pytest.fail(stage),
                           key="fourth", store=store, job_id=job["id"])


def test_runtime_and_budget_cannot_drift_on_resume():
    checkpoint = {}
    config = execution_config({})
    choice = runtime_choice(config, checkpoint)
    assert choice == checkpoint["runtime_choice"]
    for change in ({"model": "gemini-other"}, {"thinking_level": "low"}, {"provider_timeout": 10}):
        with pytest.raises(ValueError, match="Frozen runtime"):
            runtime_choice(config | change, deepcopy(checkpoint))
    reserve_model_call(config, checkpoint, lambda _: None, key="first")
    with pytest.raises(ValueError, match="Frozen model-call budget"):
        reserve_model_call(config | {"max_model_calls": 4}, checkpoint, lambda _: None, key="second")


def test_explicit_no_deadline_is_durable_and_cannot_replace_a_frozen_deadline(tmp_path):
    store = EngineStore(tmp_path)
    job = store.enqueue("30669", "alt-02", {"provider_timeout": None})
    assert job["config"]["provider_timeout"] is None
    assert job["config"]["max_model_calls"] == 3
    checkpoint = {}
    runtime_choice(job["config"], checkpoint)
    with pytest.raises(ValueError, match="Frozen runtime"):
        runtime_choice(job["config"] | {"provider_timeout": 120}, checkpoint)
    finite_checkpoint = {}
    runtime_choice({}, finite_checkpoint)
    with pytest.raises(ValueError, match="Frozen runtime"):
        runtime_choice({"provider_timeout": None}, finite_checkpoint)


@pytest.fixture
def engine_cli():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("no_deadline_engine_cli", root / "tools/engine.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(root / "tools"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


@pytest.mark.parametrize("argument", ["0", "-1", "nan", "inf", "3601", "unlimited"])
def test_cli_rejects_invalid_deadlines_without_creating_a_job(tmp_path, engine_cli, monkeypatch, argument):
    monkeypatch.setattr(sys, "argv", ["engine.py", "--data-dir", str(tmp_path), "enqueue",
        "--set", "30669", "--guide", "alt-02", "--provider-timeout", argument])
    with pytest.raises(SystemExit) as error:
        engine_cli.main()
    assert error.value.code == 2 and not (tmp_path / "engine/jobs.sqlite3").exists()


def test_cli_no_deadline_shares_prior_request_budget_without_changing_parent(tmp_path, engine_cli, monkeypatch):
    from pydantic import BaseModel
    from guide2build.engine.exploration import ExplorationCalls, ExplorationBudgetExhausted, _policy

    class Result(BaseModel):
        ok: bool

    class Runtime:
        model = "gemini-3.8-flash"
        thinking_level = "medium"
        timeout = None
        calls = 0

        def call(self, prompt, images, schema, evidence, check):
            self.calls += 1
            check()
            return {"ok": True}

    class Heartbeat:
        def check(self):
            pass

    sha = "a" * 64
    store = EngineStore(tmp_path)
    parent = store.enqueue("30669", "alt-02", {"execution_policy": "explore", "source_sha256": sha})
    claimed = store.claim("parent", job_id=parent["id"])
    cp = claimed["checkpoint"]
    reserve_model_call(parent["config"], cp,
        lambda stage: store.checkpoint(parent["id"], "parent", cp), key="initial")
    store.cancel(parent["id"])
    with pytest.raises(InterruptedError):
        store.checkpoint(parent["id"], "parent", cp)
    parent_before = store.get(parent["id"])
    monkeypatch.setattr(engine_cli, "cached_receipt", lambda *args: {"sha256": sha})
    monkeypatch.setattr(sys, "argv", ["engine.py", "--data-dir", str(tmp_path), "enqueue", "--set", "30669",
        "--guide", "alt-02", "--execution-policy", "explore", "--provider-timeout", "none",
        "--revision", "synthetic-no-deadline", "--share-budget-with", parent["id"]])
    assert engine_cli.main() == 0
    child = next(j for j in store.list() if j["id"] != parent["id"])
    assert child["config"]["provider_timeout"] is None
    assert child["config"]["budget_root_job_id"] == parent["id"]
    assert store.get(parent["id"]) == parent_before
    claimed = store.claim("child", job_id=child["id"])
    checkpoint = claimed["checkpoint"]
    policy = _policy(child["config"], checkpoint, sha, 1)
    runtime = Runtime()
    calls = ExplorationCalls(runtime, store.root / "jobs" / child["id"], checkpoint,
        lambda stage: store.checkpoint(child["id"], "child", checkpoint), Heartbeat(), policy, store, parent["id"])
    for key in ("second", "third"):
        assert calls.call(key, "Synthetic output", [], Result).ok
    with pytest.raises(ExplorationBudgetExhausted):
        calls.call("fourth", "Synthetic output", [], Result)
    assert runtime.calls == 2 and store.lineage_model_calls_used(parent["id"]) == 3
    assert store.get(parent["id"]) == parent_before
    store.cancel(child["id"])
    with pytest.raises(InterruptedError):
        store.checkpoint(child["id"], "child", checkpoint)
    store.retry(child["id"])
    assert store.get(child["id"])["config"]["provider_timeout"] is None
    assert store.lineage_model_calls_used(parent["id"]) == 3


@pytest.mark.parametrize("changes", [
    {"guide_id": "different"}, {"source_sha256": "b" * 64},
    {"model": "gemini-other"}, {"thinking_level": "low"}, {"maximum": 4},
    {"execution_policy": "strict"}])
def test_shared_budget_rejects_different_source_model_or_ceiling(tmp_path, engine_cli, changes):
    store = EngineStore(tmp_path)
    parent = store.enqueue("30669", "alt-02", {"execution_policy": "explore", "source_sha256": "a" * 64})
    options = dict(set_number="30669", guide_id="alt-02", source_sha256="a" * 64,
        model=parent["config"]["model"], thinking_level="medium", maximum=3, execution_policy="explore")
    with pytest.raises(ValueError):
        engine_cli.shared_budget_config(store, parent["id"], **(options | changes))
    assert len(store.list()) == 1


def test_shared_budget_rejects_correction_descendant_checkpoint_root(tmp_path, engine_cli):
    store = EngineStore(tmp_path)
    config = {"execution_policy": "explore", "source_sha256": "a" * 64}
    parent = store.enqueue("30669", "alt-02", config)
    descendant = store.enqueue("30669", "alt-02", config | {"revision": "correction-child"})
    claimed = store.claim("correction", job_id=descendant["id"])
    store.checkpoint(descendant["id"], "correction",
        claimed["checkpoint"] | {"budget_root_job_id": parent["id"]})
    store.cancel(descendant["id"])
    with pytest.raises(ValueError, match="original budget root"):
        engine_cli.shared_budget_config(store, descendant["id"], set_number="30669", guide_id="alt-02",
            source_sha256="a" * 64, model=parent["config"]["model"], thinking_level="medium",
            maximum=3, execution_policy="explore")


def test_invalid_all_shared_budget_command_does_not_gate_campaign(tmp_path, engine_cli, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["engine.py", "--data-dir", str(tmp_path), "enqueue",
        "--all", "--share-budget-with", "synthetic-root"])
    with pytest.raises(SystemExit) as error:
        engine_cli.main()
    assert error.value.code == 2
    store = EngineStore(tmp_path)
    with store.connect() as connection:
        assert connection.execute("SELECT value FROM engine_control WHERE key='pilot_gate'").fetchone() is None
    assert not store.list()


def test_local_dotenv_preserves_exported_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-exported")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    (tmp_path / ".env").write_text("GOOGLE_API_KEY=synthetic-file\nGOOGLE_GENAI_USE_VERTEXAI=FALSE\n")
    load_local_environment(tmp_path)
    assert os.environ["GOOGLE_API_KEY"] == "synthetic-exported"
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "FALSE"
