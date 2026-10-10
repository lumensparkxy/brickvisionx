import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from fastapi.testclient import TestClient
from guide2build.main import create_app
from guide2build.jobs.models import ConversionRequest
from guide2build.jobs.store import Store, Conflict, LostLease
from guide2build.jobs.worker import LeaseHeartbeat, run_once

REQUEST = ConversionRequest(set_number="30669", guide_id="alt-02", mode="assisted")


def test_persisted_idempotency_and_parameter_conflict(tmp_path):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "same", "source-v1")
    restarted = Store(tmp_path)
    assert restarted.enqueue(REQUEST, "same", "source-v1")["job_id"] == job["job_id"]
    assert restarted.enqueue(REQUEST, "another", "source-v1")["job_id"] == job["job_id"]
    with pytest.raises(Conflict):
        restarted.enqueue(REQUEST, "same", "source-v2")
    assert len(restarted.events(job["job_id"])) == 1


def test_two_workers_cannot_claim_one_job(tmp_path):
    store = Store(tmp_path)
    store.enqueue(REQUEST, "one", "v1")
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(store.claim, ["worker-a", "worker-b"]))
    assert sum(c is not None for c in claims) == 1


def test_expired_lease_resumes_checkpoint_and_rejects_old_worker(tmp_path):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "one", "v1")
    store.claim("dead")
    store.checkpoint(job["job_id"], "dead", "rendering", {"source_sha256": "a" * 64})
    with store.connect(write=True) as db:
        db.execute("UPDATE jobs SET lease_until=?", (time.time() - 1,))
    resumed, checkpoint = Store(tmp_path).claim("new")
    assert resumed["attempts"] == 2
    assert checkpoint["source_sha256"] == "a" * 64
    with pytest.raises(LostLease):
        store.checkpoint(job["job_id"], "dead", "ready", {})


def test_cancel_running_job_finishes_current_stage_and_retry_keeps_checkpoint(tmp_path):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "one", "v1")
    store.claim("worker")
    store.cancel(job["job_id"])
    result = store.checkpoint(job["job_id"], "worker", "rendering", {"done": "fetching"})
    assert result["state"] == "cancelled"
    assert store.cancel(job["job_id"])["state"] == "cancelled"
    assert store.retry(job["job_id"])["state"] == "queued"
    with store.connect(write=True) as db:
        db.execute("UPDATE jobs SET available_at=0")
    assert store.claim("worker")[1] == {"done": "fetching"}


def test_automated_request_fails_explicitly_without_queueing(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/v1/conversions", json={**REQUEST.model_dump(), "mode": "automated"},
                           headers={"Idempotency-Key": "automatic"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_unavailable"
    assert client.app.state.store.claim("worker") is None


def test_conversion_requires_key_and_validated_input(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.post("/api/v1/conversions", json=REQUEST.model_dump()).status_code == 422
    response = client.post("/api/v1/conversions", json=REQUEST.model_dump(), headers={"Idempotency-Key": "one"})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert client.get(f"/api/v1/jobs/{job_id}").json()["state"] == "queued"
    assert client.get(f"/api/v1/jobs/{job_id}/events").json()["events"]
    assert client.post(f"/api/v1/jobs/{job_id}/cancel").json()["state"] == "cancelled"
    assert client.post("/api/v1/conversions", json={**REQUEST.model_dump(), "source_url": "http://localhost"},
                       headers={"Idempotency-Key": "two"}).status_code == 422


def test_worker_no_reference_is_needs_review_not_success(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "one", "v1")
    monkeypatch.setattr("guide2build.jobs.worker.download_pdf", lambda *args, **kwargs: {"sha256": "a" * 64})
    monkeypatch.setattr("guide2build.jobs.worker.render_pages", lambda *args, **kwargs: [{"page_index": i} for i in range(8)])
    assert run_once(store)
    actual = store.get(job["job_id"])
    assert actual["state"] == "needs_review"
    assert actual["output_revision"] is None
    assert actual["error"]["code"] == "assisted_reference_unavailable"


def test_worker_failure_is_redacted_and_retryable(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "one", "v1")
    def failure(*args, **kwargs):
        raise httpx.ConnectError("secret-path-or-token")
    monkeypatch.setattr("guide2build.jobs.worker.download_pdf", failure)
    run_once(store)
    actual = store.get(job["job_id"])
    assert actual["state"] == "failed"
    assert actual["error"]["retryable"]
    assert "secret-path-or-token" not in json.dumps(actual)
    assert store.retry(job["job_id"])["state"] == "queued"


def test_cross_origin_write_rejected_and_private_files_not_served(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/v1/conversions", json=REQUEST.model_dump(), headers={
        "Origin": "https://malicious.example", "Idempotency-Key": "one"})
    assert response.status_code == 403
    assert client.get("/assets-local/guide2build.sqlite3").status_code == 404


def test_source_route_confines_symlinks(tmp_path):
    pages = tmp_path / "public/pages" / ("a" * 64)
    pages.mkdir(parents=True)
    private = tmp_path / "secret.png"
    private.write_text("private")
    (pages / "page-000.png").symlink_to(private)
    client = TestClient(create_app(tmp_path))
    assert client.get(f"/api/v1/sources/{'a' * 64}/pages/0").status_code == 404


def test_new_source_hash_creates_new_job_but_same_key_stays_idempotent(tmp_path):
    store = Store(tmp_path)
    original = store.enqueue(REQUEST, "one", "catalog-v1", source_hash="a" * 64)
    changed = store.enqueue(REQUEST, "two", "catalog-v1", source_hash="b" * 64)
    assert original["job_id"] != changed["job_id"]
    assert store.enqueue(REQUEST, "one", "catalog-v1", source_hash="b" * 64)["job_id"] == original["job_id"]


def test_provisional_job_deduplicates_after_source_discovery(tmp_path):
    store = Store(tmp_path)
    original = store.enqueue(REQUEST, "one", "catalog-v1")
    store.claim("worker")
    store.checkpoint(original["job_id"], "worker", "needs_review", {}, source_sha256="a" * 64)
    actual = store.enqueue(REQUEST, "two", "catalog-v1", source_hash="a" * 64)
    assert actual["job_id"] == original["job_id"]


def test_revised_assisted_reference_does_not_reuse_old_job(tmp_path):
    store = Store(tmp_path)
    reference = tmp_path / "reconstructions/30669/alt-02/scene.json"
    reference.parent.mkdir(parents=True)
    reference.write_text('{"revision":"test-v1"}')
    original = store.enqueue(REQUEST, "reference-one", "catalog-v1")
    reference.write_text('{"revision":"test-v2"}')
    revised = store.enqueue(REQUEST, "reference-two", "catalog-v1")
    assert revised["job_id"] != original["job_id"]


def test_fetch_timestamp_does_not_invalidate_identical_parts(tmp_path):
    import json
    store = Store(tmp_path)
    path = tmp_path / "public/ldraw/provenance.json"
    path.parent.mkdir(parents=True)
    manifest = {"fetched_at": "first", "resources": {"parts/3022.dat": {"sha256": "a" * 64,
                "url": "https://library.ldraw.org/library/official/parts/3022.dat", "dependencies": []}}}
    path.write_text(json.dumps(manifest))
    original = store.enqueue(REQUEST, "timestamp-one", "catalog-v1")
    manifest["fetched_at"] = "later"
    path.write_text(json.dumps(manifest))
    repeated = store.enqueue(REQUEST, "timestamp-two", "catalog-v1")
    assert repeated["job_id"] == original["job_id"]


def test_heartbeat_renews_owned_lease_without_changing_checkpoint(tmp_path):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "heartbeat", "v1")
    store.claim("worker")
    store.checkpoint(job["job_id"], "worker", "rendering", {"completed_pages": 25})
    with store.connect(write=True) as db:
        db.execute("UPDATE jobs SET lease_until=?", (time.time() + 5,))
    store.heartbeat(job["job_id"], "worker", lease_seconds=60)
    with store.connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job["job_id"],)).fetchone()
    assert row["lease_until"] > time.time() + 50
    assert json.loads(row["checkpoint"]) == {"completed_pages": 25}
    assert store.claim("other") is None
    assert len(store.events(job["job_id"])) == 3  # heartbeats do not flood the event log


def test_heartbeat_cannot_revive_expired_or_stolen_lease(tmp_path):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "expired", "v1")
    store.claim("old")
    with store.connect(write=True) as db:
        db.execute("UPDATE jobs SET lease_until=?", (time.time() - 1,))
    with pytest.raises(LostLease):
        store.heartbeat(job["job_id"], "old")
    store.claim("new")
    with pytest.raises(LostLease):
        store.heartbeat(job["job_id"], "old")
    with pytest.raises(LostLease):
        store.check_active(job["job_id"], "old")


def test_background_heartbeat_runs_without_stage_progress(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "background", "v1")
    store.claim("worker")
    renewed = threading.Event()
    original = store.heartbeat

    def heartbeat(*args, **kwargs):
        original(*args, **kwargs)
        if threading.current_thread().name == "preparation-heartbeat":
            renewed.set()

    monkeypatch.setattr(store, "heartbeat", heartbeat)
    lease = LeaseHeartbeat(store, job["job_id"], "worker", interval=0.01)
    try:
        lease.start()
        assert renewed.wait(1)
        store.cancel(job["job_id"])
        with pytest.raises((InterruptedError, LostLease)):
            lease.check(force=True)
        assert store.get(job["job_id"])["state"] == "cancelled"
    finally:
        lease.close()
    assert not lease.thread.is_alive()


def test_cancel_during_download_prevents_rendering(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "cancel-download", "v1")

    def download(*args, check_cancel):
        store.cancel(job["job_id"])
        check_cancel(force=True)
        pytest.fail("Cancelled download continued")

    monkeypatch.setattr("guide2build.jobs.worker.download_pdf", download)
    monkeypatch.setattr("guide2build.jobs.worker.render_pages", lambda *args, **kwargs: pytest.fail("Rendered"))
    assert run_once(store)
    assert store.get(job["job_id"])["state"] == "cancelled"


def test_cancelled_render_keeps_actual_page_progress_for_retry(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "cancel-render", "v1")
    monkeypatch.setattr("guide2build.jobs.worker.download_pdf", lambda *args, **kwargs: {"sha256": "a" * 64})

    def render(*args, check_cancel, on_progress, **kwargs):
        on_progress(25, 400)
        actual = store.get(job["job_id"])
        assert (actual["completed_units"], actual["total_units"]) == (25, 400)
        store.cancel(job["job_id"])
        check_cancel(force=True)
        pytest.fail("Cancelled render continued")

    monkeypatch.setattr("guide2build.jobs.worker.render_pages", render)
    assert run_once(store)
    actual = store.get(job["job_id"])
    assert actual["state"] == "cancelled"
    store.retry(job["job_id"])
    with store.connect(write=True) as db:
        db.execute("UPDATE jobs SET available_at=0")
    _, retained = store.claim("resumed")
    assert retained["render_progress"] == {"completed_pages": 25, "total_pages": 400}
    assert retained["source_sha256"] == "a" * 64


def test_worker_losing_lease_cannot_publish_or_fail_replacement_job(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "lost-render", "v1")
    monkeypatch.setattr("guide2build.jobs.worker.download_pdf", lambda *args, **kwargs: {"sha256": "a" * 64})

    def render(*args, check_cancel, on_progress, **kwargs):
        on_progress(25, 400)
        with store.connect(write=True) as db:
            db.execute("UPDATE jobs SET lease_until=?", (time.time() - 1,))
        replacement, _ = store.claim("replacement")
        assert replacement["job_id"] == job["job_id"]
        check_cancel(force=True)
        pytest.fail("Stale worker continued")

    monkeypatch.setattr("guide2build.jobs.worker.render_pages", render)
    assert run_once(store, owner="original")
    actual = store.get(job["job_id"])
    assert actual["state"] == "fetching"
    assert actual["error"] is None
    assert actual["output_revision"] is None
    store.check_active(job["job_id"], "replacement")


@pytest.mark.parametrize("expected,state", [(None, "needs_review"), (8, "failed")])
def test_unknown_page_count_accepts_measured_count_but_known_count_is_enforced(tmp_path, monkeypatch, expected, state):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "page-count", "v1")
    monkeypatch.setattr("guide2build.jobs.worker.find_guide", lambda *args: {
        "pdf_url": "https://www.lego.com/cdn/product-assets/product.bi.core.pdf/example.pdf",
        "expected_page_count": expected})
    monkeypatch.setattr("guide2build.jobs.worker.download_pdf", lambda *args, **kwargs: {"sha256": "a" * 64})

    def render(*args, on_progress, **kwargs):
        on_progress(12, 12)
        return [{"page_index": i} for i in range(12)]

    monkeypatch.setattr("guide2build.jobs.worker.render_pages", render)
    assert run_once(store)
    actual = store.get(job["job_id"])
    assert actual["state"] == state
    assert actual["output_revision"] is None
    assert (actual["completed_units"], actual["total_units"]) == (12, 12)


def test_source_changed_after_receipt_verification_cannot_complete_preparation(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = store.enqueue(REQUEST, "source-changed", "v1")
    receipt_digest = "a" * 64

    def download(url, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Simulate another fetch replacing the mutable source after receipt A was verified.
        destination.write_bytes(b"%PDF-replacement-B")
        return {"sha256": receipt_digest}

    def render(source, destination, *, expected_sha256, **kwargs):
        assert expected_sha256 == receipt_digest
        assert destination.name == receipt_digest
        assert source.read_bytes() == b"%PDF-replacement-B"
        raise ValueError("Source digest does not match the expected receipt")

    monkeypatch.setattr("guide2build.jobs.worker.download_pdf", download)
    monkeypatch.setattr("guide2build.jobs.worker.render_pages", render)
    assert run_once(store)
    actual = store.get(job["job_id"])
    assert actual["state"] == "failed"
    assert actual["error"]["code"] == "preparation_failed"
    assert actual["output_revision"] is None
    assert not (tmp_path / "public/pages" / receipt_digest / "pages.json").exists()
