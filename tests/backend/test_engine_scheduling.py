"""Original local queue fixtures, with no provider calls or reconstruction claims."""
import importlib.util
from pathlib import Path
import sys
import threading

import pytest

from guide2build.engine.runner import Heartbeat, WorkerStopped, run_once
from guide2build.engine.scheduling import run_queue_wave
from guide2build.engine.store import EngineStore


def _jobs(store):
    return [store.enqueue(set_number, guide, {"model": "synthetic", "revision": "queue-fixture"})
            for set_number, guide in [("30669", "alt-02"), ("30669", "alt-01"),
                                      ("60400", "booklet-01"), ("31134", "booklet-01")]]


def test_two_workers_overlap_independent_sets_and_serialize_same_set(tmp_path):
    store = EngineStore(tmp_path)
    jobs = _jobs(store)
    seen, active = [], set()
    lock = threading.Lock()
    paired = threading.Event()
    peaks = []

    def local_run(store, *, job_id, max_concurrent_jobs, **kwargs):
        job = store.claim(job_id, job_id=job_id, max_concurrent_jobs=max_concurrent_jobs)
        assert job is not None
        with lock:
            assert job["set_number"] not in active
            active.add(job["set_number"])
            seen.append(job_id)
            peaks.append(len(active))
            if len(active) == 2:
                paired.set()
        if job_id in {jobs[0]["id"], jobs[2]["id"]}:
            assert paired.wait(5), "Independent set never overlapped the first worker"
        with lock:
            active.remove(job["set_number"])
        store.checkpoint(job_id, job_id, {"completed_panels": 1}, "paused")
        return True

    report = run_queue_wave(store, job_ids=[j["id"] for j in jobs], workers=2, run_job=local_run)
    assert report["processed_jobs"] == 4 and max(peaks) == 2
    assert seen.index(jobs[0]["id"]) < seen.index(jobs[1]["id"])
    assert all(store.get(job["id"])["state"] == "paused" for job in jobs)


def test_job_ceiling_does_not_overshoot_with_parallel_workers(tmp_path):
    store = EngineStore(tmp_path)
    jobs = _jobs(store)
    barrier = threading.Barrier(2)

    def local_run(store, *, job_id, max_concurrent_jobs, **kwargs):
        assert store.claim(job_id, job_id=job_id, max_concurrent_jobs=max_concurrent_jobs)
        barrier.wait(timeout=5)
        store.checkpoint(job_id, job_id, {}, "paused")
        return True

    report = run_queue_wave(store, workers=2, max_jobs=2, run_job=local_run)
    assert report["processed_jobs"] == report["attempted_jobs"] == 2
    assert sum(job["state"] == "queued" for job in store.list()) == 2
    assert {result["set_number"] for result in report["results"]} == {"30669", "60400"}
    assert store.get(jobs[1]["id"])["state"] == "queued"


def test_pause_stops_new_claims_without_busy_retry(tmp_path):
    store = EngineStore(tmp_path)
    jobs = _jobs(store)
    calls = []

    def local_run(store, *, job_id, **kwargs):
        calls.append(job_id)
        store.pause_provider({"code": "subscription_limit", "message": "Original synthetic quota fixture"})
        return False

    report = run_queue_wave(store, workers=1, run_job=local_run)
    assert calls == [jobs[0]["id"]]
    assert report["processed_jobs"] == 0 and report["attempted_jobs"] == 1
    assert all(job["state"] == "queued" for job in store.list())


def test_unclaimable_jobs_are_attempted_once_and_never_fall_back(tmp_path):
    store = EngineStore(tmp_path)
    jobs = _jobs(store)
    store.claim("external", job_id=jobs[0]["id"])
    calls = []

    def local_run(store, *, job_id, **kwargs):
        calls.append(job_id)
        return run_once(store, job_id=job_id, **kwargs)

    report = run_queue_wave(store, job_ids=[jobs[2]["id"]], run_job=local_run)
    assert report["processed_jobs"] == 0 and calls == [jobs[2]["id"]]
    assert store.get(jobs[2]["id"])["state"] == "queued"


def test_queue_stop_retains_accepted_checkpoint_and_releases_lease(tmp_path):
    store = EngineStore(tmp_path)
    job = _jobs(store)[0]
    assert store.claim("seed", job_id=job["id"])
    store.checkpoint(job["id"], "seed", {"completed_panels": 2}, "paused")
    stopped = threading.Event()
    stopped.set()
    assert run_once(store, job_id=job["id"], stop_event=stopped)
    latest = store.get(job["id"])
    assert latest["state"] == "paused" and latest["owner"] is None
    assert latest["checkpoint"]["completed_panels"] == 2
    assert latest["error"]["code"] == "queue_stopped" and latest["cancel"] == 0


def test_heartbeat_uses_only_control_state_and_honours_queue_stop(tmp_path, monkeypatch):
    store = EngineStore(tmp_path)
    job = _jobs(store)[0]
    monkeypatch.setattr(store, "get", lambda *args: pytest.fail("Heartbeat hydrated a candidate"))
    event = threading.Event()
    heartbeat = Heartbeat(store, job["id"], "synthetic", stop_event=event)
    heartbeat.check()
    event.set()
    with pytest.raises(WorkerStopped):
        heartbeat.check()


def test_default_wave_never_resumes_paused_or_completed_alpha(tmp_path):
    store = EngineStore(tmp_path)
    jobs = _jobs(store)
    store.claim("seed", job_id=jobs[0]["id"])
    store.checkpoint(jobs[0]["id"], "seed", {}, "paused")
    store.claim("seed", job_id=jobs[2]["id"])
    store.checkpoint(jobs[2]["id"], "seed", {"alpha_source_complete": True}, "paused")
    calls = []
    run_queue_wave(store, job_ids=[jobs[0]["id"], jobs[2]["id"]],
                   run_job=lambda store, **kw: calls.append(kw["job_id"]) or False)
    assert calls == [jobs[0]["id"]]
    calls.clear()
    run_queue_wave(store, run_job=lambda store, **kw: calls.append(kw["job_id"]) or False)
    assert jobs[0]["id"] not in calls and jobs[2]["id"] not in calls


@pytest.mark.parametrize("workers", [0, 3, True, 1.5])
def test_worker_bound_rejected_before_scheduling(tmp_path, workers):
    store = EngineStore(tmp_path)
    with pytest.raises(ValueError, match="Worker count"):
        run_queue_wave(store, workers=workers)


@pytest.fixture
def campaign_module():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("efficiency_campaign", root / "tools/alpha_campaign.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(root / "tools"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


@pytest.fixture
def engine_cli():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("efficiency_engine_cli", root / "tools/engine.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(root / "tools"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


@pytest.mark.parametrize("policy,profile,expected", [
    ("explore", None, "incremental-v1"), ("explore", "legacy", None), ("strict", None, None)])
def test_enqueue_cli_versions_new_exploration_without_changing_model(tmp_path, engine_cli, monkeypatch,
                                                                   policy, profile, expected):
    arguments = ["engine.py", "--data-dir", str(tmp_path), "enqueue", "--set", "30669", "--guide", "alt-02",
                 "--execution-policy", policy, "--revision", "synthetic-efficiency-cli"]
    if profile is not None:
        arguments.extend(["--efficiency-profile", profile])
    monkeypatch.setattr(sys, "argv", arguments)
    assert engine_cli.main() == 0
    jobs = EngineStore(tmp_path).list()
    assert len(jobs) == 1 and jobs[0]["state"] == "queued"
    assert jobs[0]["config"].get("efficiency_profile") == expected
    assert jobs[0]["config"]["model"] == "gemini-3.8-flash" and jobs[0]["config"]["thinking_level"] == "medium"
    assert jobs[0]["checkpoint"] == {}  # Enqueue did not perform inference.


def test_strict_cli_rejects_incremental_prompt_before_enqueuing(tmp_path, engine_cli, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["engine.py", "--data-dir", str(tmp_path), "enqueue", "--set", "30669",
        "--guide", "alt-02", "--execution-policy", "strict", "--efficiency-profile", "incremental-v1"])
    with pytest.raises(SystemExit) as error:
        engine_cli.main()
    assert error.value.code == 2 and EngineStore(tmp_path).list() == []


def test_alpha_round_defers_dependent_booklet_without_inference(tmp_path, campaign_module):
    store = EngineStore(tmp_path)
    first = store.enqueue("10316", "booklet-01", {"revision": "synthetic-prefix"})
    second = store.enqueue("10316", "booklet-02", {"revision": "synthetic-prefix"})
    unrelated = store.enqueue("30669", "alt-02", {"revision": "synthetic-prefix"})
    manifest = {"job_ids": [first["id"], second["id"], unrelated["id"]]}
    calls = []

    def local_run(store, *, job_id, max_concurrent_jobs, **kwargs):
        calls.append(job_id)
        assert store.claim(job_id, job_id=job_id, max_concurrent_jobs=max_concurrent_jobs)
        store.checkpoint(job_id, job_id, {"alpha_completed_pages": 4}, "paused")
        return True

    result = campaign_module.run_campaign_round(store, manifest, workers=2, run_job=local_run)
    assert result["progressed"] and set(calls) == {first["id"], unrelated["id"]}
    assert store.get(second["id"])["state"] == "queued"
    store.claim("complete", job_id=first["id"])
    store.checkpoint(first["id"], "complete", {"alpha_completed_pages": 8, "alpha_source_complete": True}, "paused")
    calls.clear()
    campaign_module.run_campaign_round(store, manifest, workers=2, run_job=local_run)
    assert second["id"] in calls and first["id"] not in calls


def test_campaign_progress_cache_reuses_only_unchanged_jobs(tmp_path, campaign_module, monkeypatch):
    store = EngineStore(tmp_path)
    jobs = [store.enqueue("30669", guide, {"model": "gpt-6-astra", "revision": "synthetic-progress-cache"})
            for guide in ("alt-02", "alt-01")]
    manifest = {"job_ids": [job["id"] for job in jobs]}
    original = store.get
    reads = []
    monkeypatch.setattr(store, "get", lambda identity: reads.append(identity) or original(identity))
    cache = {}
    campaign_module.summary(store, manifest, cache=cache)
    campaign_module.summary(store, manifest, cache=cache)
    assert reads == [job["id"] for job in jobs]
    store.claim("advance", job_id=jobs[0]["id"])
    store.checkpoint(jobs[0]["id"], "advance", {"alpha_completed_pages": 4}, "paused")
    reads.clear()
    result = campaign_module.summary(store, manifest, cache=cache)
    assert reads == [jobs[0]["id"]] and result["jobs"][0]["completed_pages"] == 4
    reads.clear()
    campaign_module.summary(store, manifest)
    assert reads == [job["id"] for job in jobs]  # Final report always verifies again.
