import time
import pytest
from guide2build.engine.store import EngineStore, LeaseLost
from guide2build.engine.provider import child_environment


def enqueue(store, guide="alt-02"):
    return store.enqueue("30669", guide, {"model": "test"})


def test_durable_dedupe_and_single_global_lease(tmp_path):
    store = EngineStore(tmp_path)
    first = enqueue(store)
    assert enqueue(store)["id"] == first["id"]
    enqueue(store, "alt-01")
    claimed = store.claim("worker1")
    assert claimed["id"] == first["id"]
    assert EngineStore(tmp_path).claim("worker2") is None
    store.checkpoint(first["id"], "worker1", {"completed_panels": 3}, "blocked")
    assert EngineStore(tmp_path).get(first["id"])["checkpoint"]["completed_panels"] == 3
    assert store.claim("worker2")["guide_id"] == "alt-01"


def test_proposal_profiles_are_explicit_durable_and_preserve_baseline_dedupe(tmp_path):
    store = EngineStore(tmp_path)
    config = {"model": "test", "execution_policy": "explore", "revision": "synthetic-profile"}
    baseline = store.enqueue("30669", "alt-02", config)
    assert store.enqueue("30669", "alt-02", config | {"proposal_profile": "baseline"})["id"] == baseline["id"]
    variant = store.enqueue("30669", "alt-02", config | {"proposal_profile": "attachment-reasoning"})
    assert variant["id"] != baseline["id"]
    assert EngineStore(tmp_path).get(variant["id"])["config"]["proposal_profile"] == "attachment-reasoning"
    assert "proposal_profile" not in EngineStore(tmp_path).get(baseline["id"])["config"]
    with pytest.raises(ValueError, match="explore"):
        store.enqueue("30669", "alt-02", {"model": "test", "proposal_profile": "attachment-reasoning"})
    with pytest.raises(ValueError, match="profile"):
        store.enqueue("30669", "alt-02", config | {"proposal_profile": "unregistered"})


def test_expired_lease_is_fenced_and_resumes_checkpoint(tmp_path):
    store = EngineStore(tmp_path)
    job = enqueue(store)
    store.claim("old")
    store.checkpoint(job["id"], "old", {"completed_panels": 2})
    with store.connect() as con:
        con.execute("UPDATE engine_jobs SET lease_until=?", (time.time()-1,))
    recovered = store.claim("new")
    assert recovered["checkpoint"]["completed_panels"] == 2
    with pytest.raises(LeaseLost):
        store.checkpoint(job["id"], "old", {"completed_panels": 9})


def test_cancel_retry_and_provider_pause(tmp_path):
    store = EngineStore(tmp_path)
    job = enqueue(store)
    store.cancel(job["id"])
    assert store.claim("a") is None
    store.retry(job["id"])
    store.pause_provider({"code": "subscription_limit"})
    assert EngineStore(tmp_path).claim("a") is None
    store.resume_provider()
    assert store.claim("a")["id"] == job["id"]
    store.cancel(job["id"])
    with pytest.raises(InterruptedError):
        store.checkpoint(job["id"], "a", {})
    assert store.get(job["id"])["state"] == "cancelled"


def test_environment_excludes_keys_cloud_and_parent_agent_state():
    env = child_environment({"HOME": "/home/user", "PATH": "/bin", "OPENAI_API_KEY": "secret",
        "GEMINI_API_KEY": "secret", "GOOGLE_APPLICATION_CREDENTIALS": "secret", "CODEX_HOME": "/other",
        "AWS_SECRET_ACCESS_KEY": "secret", "CODEX_THREAD_ID": "parent"})
    assert env == {"HOME": "/home/user", "PATH": "/bin"}


def test_campaign_gate_requires_staged_pilot(tmp_path):
    store = EngineStore(tmp_path)
    pilot = enqueue(store)
    other = enqueue(store, "alt-01")
    store.gate_campaign()
    assert store.claim("one")["id"] == pilot["id"]
    store.checkpoint(pilot["id"], "one", {}, "blocked")
    assert store.claim("two") is None
    # Simulate a previously verified stage transition; this is queue behavior, not release evidence.
    with store.connect() as con:
        con.execute("UPDATE engine_jobs SET state='awaiting_approval' WHERE id=?", (pilot["id"],))
    assert store.claim("two")["id"] == other["id"]


def test_reset_preserves_rejected_candidate_and_source_index(tmp_path):
    store = EngineStore(tmp_path)
    job = enqueue(store)
    store.claim("one")
    store.checkpoint(job["id"], "one", {"candidate": {"test": True}, "page_indexes": [1]}, "blocked")
    directory = store.root / "jobs" / job["id"]
    directory.mkdir(parents=True)
    (directory / "scene.json").write_text('{"test":true}')
    store.reset_candidate(job["id"])
    assert "candidate" not in store.get(job["id"])["checkpoint"]
    assert store.get(job["id"])["checkpoint"]["page_indexes"] == [1]
    assert len(list((directory / "rejected").glob("*/scene.json"))) == 1


def test_targeted_claim_and_explicit_pause_resume(tmp_path):
    store = EngineStore(tmp_path)
    first = enqueue(store)
    target = enqueue(store, "alt-01")
    assert store.claim("guided", job_id=target["id"])["id"] == target["id"]
    assert store.get(first["id"])["state"] == "queued"
    store.checkpoint(target["id"], "guided", {"completed_panels": 1}, "paused")
    assert store.get(target["id"])["owner"] is None
    assert store.claim("batch")["id"] == first["id"]
    store.checkpoint(first["id"], "batch", {}, "blocked")
    assert store.claim("batch") is None
    resumed = store.claim("guided", job_id=target["id"])
    assert resumed["checkpoint"]["completed_panels"] == 1


def test_targeted_claim_never_falls_back_or_bypasses_campaign_gate(tmp_path):
    store = EngineStore(tmp_path)
    pilot = enqueue(store)
    other = enqueue(store, "alt-01")
    store.gate_campaign()
    assert store.claim("guided", job_id=other["id"]) is None
    assert store.claim("guided", job_id="missing") is None
    assert store.claim("guided", job_id=pilot["id"])["id"] == pilot["id"]
    store.checkpoint(pilot["id"], "guided", {}, "blocked")
    assert store.claim("guided", job_id=pilot["id"]) is None
    assert store.get(other["id"])["state"] == "queued"
