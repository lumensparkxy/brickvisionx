"""Synthetic job metadata only: no network, inference, render or assembly claims."""
import hashlib
import importlib.util
import io
import json
import logging
from pathlib import Path
import sys

import pytest

from guide2build.engine import activity_logging as activity
from guide2build.engine.store import EngineStore


@pytest.fixture(autouse=True)
def synthetic_source(monkeypatch):
    # Register the fictional source in this test module only; no real booklet
    # or source asset is accessed by the synthetic logging/queue checks.
    monkeypatch.setattr("guide2build.catalog.find_guide", lambda *args: {
        "pdf_url": "https://example.invalid/synthetic-booklet.pdf"})


@pytest.fixture
def log_output():
    logger = activity.LOGGER
    old = logger.handlers, logger.level, logger.propagate
    output = io.StringIO()
    logger.handlers = [logging.StreamHandler(output)]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield output
    finally:
        logger.handlers, logger.level, logger.propagate = old


@pytest.fixture
def engine_cli(log_output):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("activity_engine_cli", root / "tools/engine.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(root / "tools"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def _job(store, revision="synthetic-logging"):
    return store.enqueue("99999", "synthetic-booklet", {
        "model": "synthetic", "revision": revision, "execution_policy": "explore", "max_model_calls": 10})


def _progress(**updates):
    return {
        "stage": "exploration_instruction_complete", "page_indexes": [{}, {}], "page_count": 3,
        "processed_panels": 2, "reconstructed_panels": 1, "total_panels": 3,
        "processed_source_events": 4, "reconstructed_source_events": 2,
        "model_calls_used": 3, "provisional_findings": [{"code": "synthetic-floating"}],
        "source_index_findings": [{"code": "synthetic-index"}],
        "exploration_calls": {"synthetic-proposal": {"call_number": 3, "status": "reserved"}},
        **updates,
    }


def _rows(store):
    with store.connect() as con:
        return [tuple(row) for row in con.execute("SELECT * FROM engine_jobs ORDER BY id")], [
            tuple(row) for row in con.execute("SELECT * FROM engine_events ORDER BY seq")]


@pytest.mark.parametrize("envelope", [False, True])
def test_progress_reads_legacy_and_external_checkpoint_without_hydration(tmp_path, log_output, envelope):
    store = EngineStore(tmp_path)
    job = _job(store)
    assert store.claim("synthetic-owner", job_id=job["id"])
    cp = _progress(candidate={"synthetic": "NEVER_LOAD_OR_LOG_SCENE"})
    if envelope:
        store.checkpoint(job["id"], "synthetic-owner", cp)
        # The observer still works if the fixture's candidate artifact is absent.
        for candidate in (store.root / "checkpoint-artifacts").rglob("*.json"):
            candidate.unlink()
    else:
        with store.connect() as con:
            con.execute("UPDATE engine_jobs SET checkpoint=? WHERE id=?", (json.dumps(cp), job["id"]))
    before = _rows(store), hashlib.sha256(store.db.read_bytes()).hexdigest()
    observer = activity.ActivityObserver(tmp_path, job["id"])
    assert observer.poll(required=True)
    output = log_output.getvalue()
    assert "indexed pages=2/3" in output
    assert "processed instructions=2/3" in output and "reconstructed instructions=1/3" in output
    assert "model calls=3/10" in output and "findings=2" in output
    assert "source events incl. callouts processed=4, reconstructed=2" in output
    assert "synthetic-proposal (reserved)" in output and "NEVER_LOAD_OR_LOG_SCENE" not in output
    assert before == (_rows(store), hashlib.sha256(store.db.read_bytes()).hexdigest())


def test_events_are_deduplicated_filtered_and_never_dump_error_payloads(tmp_path, log_output):
    store = EngineStore(tmp_path)
    job, other = _job(store), _job(store, "synthetic-other")
    observer = activity.ActivityObserver(tmp_path, job["id"])
    observer.poll()
    assert store.claim("synthetic-owner", job_id=job["id"])
    store.checkpoint(job["id"], "synthetic-owner", _progress(stage="exploration_call_failed"))
    store.checkpoint(job["id"], "synthetic-owner", _progress(stage="provider_blocked"), "blocked",
                     {"code": "synthetic_failure", "message": "RAW_PROMPT_OR_CREDENTIAL_DO_NOT_LOG"})
    with store.connect() as con:
        store.event(con, other["id"], "claimed", {})
    assert observer.poll()
    output = log_output.getvalue()
    assert output.count("Worker acquired job lease") == 1
    assert output.count("Model call failed") == 1
    assert "error=synthetic_failure" in output and "RAW_PROMPT_OR_CREDENTIAL_DO_NOT_LOG" not in output
    assert other["id"] not in output and observer.finished
    assert observer.poll() and output == log_output.getvalue()


def test_event_backlog_is_bounded_without_dropping_events(tmp_path, log_output):
    store = EngineStore(tmp_path)
    job = _job(store)
    observer = activity.ActivityObserver(tmp_path, job["id"])
    observer.poll()
    with store.connect() as con:
        for _ in range(501):
            store.event(con, job["id"], "render_recorded", {})
    observer.poll()
    assert log_output.getvalue().count("Render evidence recorded") == 500
    observer.poll()
    assert log_output.getvalue().count("Render evidence recorded") == 501
    observer.poll()
    assert log_output.getvalue().count("Render evidence recorded") == 501


def test_queue_observer_catches_new_jobs_without_replaying_old_history(tmp_path, log_output):
    store = EngineStore(tmp_path)
    old, job = _job(store, "synthetic-old"), _job(store)
    store.claim("synthetic-owner", job_id=old["id"])
    store.checkpoint(old["id"], "synthetic-owner", _progress(), "paused")
    observer = activity.ActivityObserver(tmp_path)
    observer.poll()
    assert not log_output.getvalue()
    store.claim("synthetic-owner", job_id=job["id"])
    store.checkpoint(job["id"], "synthetic-owner", _progress(), "paused")
    observer.poll()
    assert job["id"] in log_output.getvalue() and old["id"] not in log_output.getvalue()
    assert "processed instructions=2/3" in log_output.getvalue()


def test_wait_messages_are_throttled_and_expired_lease_is_not_called_active(tmp_path, log_output, monkeypatch):
    store = EngineStore(tmp_path)
    job = _job(store)
    store.claim("synthetic-owner", job_id=job["id"])
    store.checkpoint(job["id"], "synthetic-owner", _progress())
    clock = [100.0]
    monkeypatch.setattr(activity.time, "monotonic", lambda: clock[0])
    observer = activity.ActivityObserver(tmp_path, job["id"], wait_seconds=30)
    observer.poll()
    clock[0] += 29
    observer.poll()
    assert "Still at" not in log_output.getvalue()
    clock[0] += 1
    observer.poll()
    assert "lease active; no new checkpoint for 30s" in log_output.getvalue()
    with store.connect() as con:
        con.execute("UPDATE engine_jobs SET lease_until=0 WHERE id=?", (job["id"],))
    clock[0] += 30
    observer.poll()
    assert "lease expired; no new checkpoint for 30s" in log_output.getvalue()
    assert log_output.getvalue().count("Still at") == 2


def test_missing_database_is_not_created_and_transient_errors_warn_once(tmp_path, log_output):
    observer = activity.ActivityObserver(tmp_path, "synthetic-missing")
    assert not observer.poll() and not observer.poll()
    assert not (tmp_path / "engine").exists()
    assert log_output.getvalue().count("Activity log unavailable") == 1
    store = EngineStore(tmp_path)
    job = _job(store)
    observer.job_id = job["id"]
    assert observer.poll()
    assert "synthetic-booklet" in log_output.getvalue()


def test_stopping_follow_does_not_cancel_or_requeue_job(tmp_path, log_output, monkeypatch):
    store = EngineStore(tmp_path)
    job = _job(store)
    store.claim("synthetic-owner", job_id=job["id"])
    store.checkpoint(job["id"], "synthetic-owner", _progress())
    before = _rows(store)

    def interrupt(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(activity.time, "sleep", interrupt)
    activity.follow_activity(tmp_path, job["id"], follow=True)
    assert _rows(store) == before
    assert "Stopped activity observer" in log_output.getvalue()


def test_follow_interruption_during_initial_read_is_graceful(tmp_path, log_output, monkeypatch):
    def interrupt_read(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(activity.ActivityObserver, "_read", interrupt_read)
    activity.follow_activity(tmp_path, "synthetic-initial-interrupt", follow=True)
    assert "Stopped activity observer" in log_output.getvalue()
    assert not (tmp_path / "engine").exists()


@pytest.mark.parametrize("broken_logging", [False, True])
def test_run_logs_on_stderr_preserves_json_and_survives_output_failure(
        tmp_path, engine_cli, monkeypatch, capsys, broken_logging):
    store = EngineStore(tmp_path)
    job = _job(store)

    def synthetic_wave(store, *, job_ids, on_result, **kwargs):
        assert job_ids == [job["id"]]
        assert store.claim("synthetic-owner", job_id=job["id"])
        store.checkpoint(job["id"], "synthetic-owner", _progress(), "paused")
        on_result({"job_id": job["id"], "processed": True})
        return {"processed_jobs": 1}

    monkeypatch.setattr(engine_cli, "run_queue_wave", synthetic_wave)
    if broken_logging:
        def broken_output(*args, **kwargs):
            raise OSError("synthetic closed stderr")
        monkeypatch.setattr(activity.LOGGER, "log", broken_output)
    monkeypatch.setattr(sys, "argv", ["engine.py", "--data-dir", str(tmp_path), "run", "--job-id", job["id"]])
    assert engine_cli.main() == 0
    output = capsys.readouterr()
    results = [json.loads(line) for line in output.out.splitlines()]
    assert results[-1]["processed_jobs"] == 1
    if not broken_logging:
        assert "INFO" in output.err and "processed instructions=2/3" in output.err
        assert "Worker acquired job lease" in output.err  # Final observer flush.
    assert store.get(job["id"])["state"] == "paused"


def test_logs_command_never_constructs_store_and_warning_level_suppresses_info(
        tmp_path, engine_cli, monkeypatch, capsys):
    store = EngineStore(tmp_path)
    job = _job(store)
    store.claim("synthetic-owner", job_id=job["id"])
    store.checkpoint(job["id"], "synthetic-owner", _progress(), "paused")
    before = _rows(store)
    monkeypatch.setattr(engine_cli, "EngineStore", lambda *args: pytest.fail("Read-only logs constructed store"))
    monkeypatch.setattr(sys, "argv", ["engine.py", "--data-dir", str(tmp_path), "--log-level", "WARNING",
                                    "logs", job["id"], "--follow"])
    assert engine_cli.main() == 0
    output = capsys.readouterr()
    assert not output.out and not output.err
    assert before == _rows(store)
