"""Synthetic request/lease checks; these never invoke Google or prove LEGO accuracy."""
from copy import deepcopy
import os

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


def test_local_dotenv_preserves_exported_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-exported")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    (tmp_path / ".env").write_text("GOOGLE_API_KEY=synthetic-file\nGOOGLE_GENAI_USE_VERTEXAI=FALSE\n")
    load_local_environment(tmp_path)
    assert os.environ["GOOGLE_API_KEY"] == "synthetic-exported"
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "FALSE"
