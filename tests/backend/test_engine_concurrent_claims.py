"""Real SQLite contention over synthetic jobs; never invokes a provider or network."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time

import pytest

from guide2build.engine.store import EngineStore, LeaseLost


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setattr("guide2build.catalog.find_guide", lambda set_number, guide: {
        "pdf_url": "https://www.lego.com/en-us/service/building-instructions/" + set_number})
    return EngineStore(tmp_path)


def enqueue(store, set_number="99999", guide="synthetic", revision="original", **config):
    return store.enqueue(set_number, guide, {"revision": revision, **config})


def test_default_is_global_one_and_explicit_two_stays_global(queue):
    first = enqueue(queue)
    second = enqueue(queue, "99998")
    third = enqueue(queue, "99997")
    assert queue.claim("one")["id"] == first["id"]
    assert EngineStore(queue.data_dir).claim("default-worker") is None
    assert queue.claim("two", max_concurrent_jobs=2)["id"] == second["id"]
    assert EngineStore(queue.data_dir).claim("other-queue", max_concurrent_jobs=2) is None
    assert queue.get(third["id"])["owner"] is None
    queue.checkpoint(first["id"], "one", {}, "paused")
    assert queue.claim("default-worker") is None  # An explicit queue does not raise defaults.
    assert queue.claim("replacement", max_concurrent_jobs=2)["id"] == third["id"]


def test_same_set_guides_and_revisions_are_serial_even_with_two_slots(queue):
    first = enqueue(queue)
    other_guide = enqueue(queue, guide="other-booklet")
    correction = enqueue(queue, revision="correction", budget_root_job_id=first["id"])
    independent = enqueue(queue, "99998")
    assert queue.claim("first", job_id=first["id"], max_concurrent_jobs=2)
    assert queue.claim("same-set-guide", job_id=other_guide["id"], max_concurrent_jobs=2) is None
    assert queue.claim("same-set-correction", job_id=correction["id"], max_concurrent_jobs=2) is None
    assert queue.claim("other-set", max_concurrent_jobs=2)["id"] == independent["id"]
    queue.checkpoint(first["id"], "first", {}, "paused")
    assert queue.claim("next-booklet", job_id=other_guide["id"], max_concurrent_jobs=2)


def test_global_provider_pause_prevents_using_the_second_slot(queue):
    enqueue(queue)
    second = enqueue(queue, "99998")
    queue.claim("first", max_concurrent_jobs=2)
    queue.pause_provider({"code": "synthetic_provider_pause"})
    assert EngineStore(queue.data_dir).claim("second", job_id=second["id"], max_concurrent_jobs=2) is None
    queue.resume_provider()
    assert queue.claim("second", job_id=second["id"], max_concurrent_jobs=2)


def test_expired_owner_resumes_same_set_without_bypassing_other_active_lease(queue):
    first = enqueue(queue)
    second = enqueue(queue, "99998")
    queue.claim("expired", job_id=first["id"], max_concurrent_jobs=2)
    queue.checkpoint(first["id"], "expired", {"candidate": {"synthetic": True}, "completed_panels": 3})
    queue.claim("still-active", job_id=second["id"], max_concurrent_jobs=2)
    with queue.connect() as con:
        con.execute("UPDATE engine_jobs SET lease_until=? WHERE id=?", (time.time() - 1, first["id"]))
    assert queue.claim("default", job_id=first["id"]) is None
    resumed = queue.claim("new", job_id=first["id"], max_concurrent_jobs=2)
    assert resumed["checkpoint"]["completed_panels"] == 3
    with pytest.raises(LeaseLost):
        queue.checkpoint(first["id"], "expired", {})
    with pytest.raises(LeaseLost):
        queue.heartbeat(first["id"], "expired")
    assert queue.get(second["id"])["owner"] == "still-active"


def test_simultaneous_independent_store_claims_cannot_exceed_two(queue):
    jobs = [enqueue(queue, str(90000 + index)) for index in range(10)]
    stores = [EngineStore(queue.data_dir) for _ in range(8)]
    ready = threading.Barrier(len(stores))
    def compete(index):
        ready.wait(timeout=5)
        return stores[index].claim(f"worker-{index}", max_concurrent_jobs=2)
    with ThreadPoolExecutor(max_workers=len(stores)) as pool:
        results = list(pool.map(compete, range(len(stores))))
    winners = [row for row in results if row]
    assert len(winners) == 2 and len({row["id"] for row in winners}) == 2
    snapshot = queue.queue_snapshot([job["id"] for job in jobs])
    assert sum(row["owner"] is not None for row in snapshot) == 2


def test_simultaneous_same_set_claims_cannot_take_both_slots(queue):
    for index in range(8):
        enqueue(queue, revision=f"synthetic-{index}")
    stores = [EngineStore(queue.data_dir) for _ in range(6)]
    ready = threading.Barrier(len(stores))
    def compete(index):
        ready.wait(timeout=5)
        return stores[index].claim(f"worker-{index}", max_concurrent_jobs=2)
    with ThreadPoolExecutor(max_workers=len(stores)) as pool:
        winners = [row for row in pool.map(compete, range(len(stores))) if row]
    assert len(winners) == 1


@pytest.mark.parametrize("limit", [0, 3, -1, True, 1.0, None, "2", float("inf")])
def test_claim_limit_is_explicit_bounded_integer(queue, limit):
    enqueue(queue)
    with pytest.raises(ValueError, match="max_concurrent_jobs"):
        queue.claim("worker", max_concurrent_jobs=limit)
    assert all(row["owner"] is None for row in queue.queue_snapshot())


def test_queue_metadata_retains_explicit_completion_not_inferred_chunk_count(queue):
    pending = enqueue(queue, generation_mode="alpha_fast", quality_profile="alpha")
    queue.claim("pending", job_id=pending["id"])
    queue.checkpoint(pending["id"], "pending", {"alpha_completed_chunks": 2, "alpha_total_chunks": 2,
        "alpha_completed_pages": 8, "completed_panels": 3}, "blocked", {"code": "alpha_source_coverage_mismatch"})
    row = queue.queue_snapshot([pending["id"]])[0]
    assert row["alpha_source_complete"] is False and row["alpha_completed_pages"] == 8
    assert row["error"] == {"code": "alpha_source_coverage_mismatch"}
    assert queue.queue_snapshot([]) == []
    with pytest.raises(KeyError):
        queue.cancel_requested("missing")


def test_efficiency_profile_is_optional_frozen_and_has_no_legacy_default(queue):
    legacy = enqueue(queue, execution_policy="explore")
    explicit_legacy = enqueue(queue, execution_policy="explore", efficiency_profile="legacy")
    efficient = enqueue(queue, execution_policy="explore", efficiency_profile="incremental-v1")
    assert legacy["id"] == explicit_legacy["id"]
    assert legacy["id"] != efficient["id"]
    assert "efficiency_profile" not in queue.get(legacy["id"])["config"]
    assert queue.get(efficient["id"])["config"]["efficiency_profile"] == "incremental-v1"
    with pytest.raises(ValueError, match="efficiency profile"):
        enqueue(queue, efficiency_profile="unknown")
    with queue.connect() as con:
        assert "efficiency_profile" not in json.loads(con.execute("SELECT config FROM engine_jobs WHERE id=?", (legacy["id"],)).fetchone()[0])


@pytest.mark.parametrize("config", [{}, {"execution_policy": "explore", "generation_mode": "alpha_fast", "quality_profile": "alpha"}])
def test_incremental_efficiency_requires_the_exploration_engine(queue, config):
    with pytest.raises(ValueError, match="exploration engine"):
        enqueue(queue, efficiency_profile="incremental-v1", **config)
    assert queue.queue_snapshot() == []


@pytest.mark.parametrize("expired_lease", [None, 0])
def test_cancelling_dead_worker_terminalizes_without_rewriting_checkpoint(queue, expired_lease):
    job = enqueue(queue)
    queue.claim("dead", job_id=job["id"])
    checkpoint = {"candidate": {"retained_synthetic_evidence": True}, "completed_panels": 3}
    queue.checkpoint(job["id"], "dead", checkpoint)
    with queue.connect() as con:
        before = con.execute("SELECT checkpoint FROM engine_jobs WHERE id=?", (job["id"],)).fetchone()[0]
        con.execute("UPDATE engine_jobs SET lease_until=? WHERE id=?", (expired_lease, job["id"]))
    queue.cancel(job["id"])
    row = queue.queue_snapshot([job["id"]])[0]
    assert row["cancel"] and row["state"] == "cancelled"
    assert row["owner"] is None and row["lease_until"] is None
    assert queue.claim("scheduler", job_id=job["id"], max_concurrent_jobs=2) is None
    with queue.connect() as con:
        assert con.execute("SELECT checkpoint FROM engine_jobs WHERE id=?", (job["id"],)).fetchone()[0] == before
    assert queue.get(job["id"])["checkpoint"] == checkpoint


def test_cancelling_live_worker_is_cooperative_and_preserves_its_fence(queue):
    job = enqueue(queue)
    claimed = queue.claim("live", job_id=job["id"])
    queue.cancel(job["id"])
    row = queue.queue_snapshot([job["id"]])[0]
    assert row["cancel"] and row["state"] == "constructing" and row["owner"] == "live"
    assert row["lease_until"] == claimed["lease_until"]
    with pytest.raises(InterruptedError, match="cancelled"):
        queue.checkpoint(job["id"], "live", {})
    final = queue.queue_snapshot([job["id"]])[0]
    assert final["state"] == "cancelled" and final["owner"] is None


@pytest.mark.parametrize("profile", [None, True, [], {}])
def test_invalid_efficiency_profile_is_a_configuration_error(queue, profile):
    with pytest.raises(ValueError, match="efficiency profile"):
        enqueue(queue, efficiency_profile=profile)
