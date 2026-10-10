"""Single-worker SQLite queue: short transactions, expiring leases, durable checkpoints."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sqlite3
import time
import uuid
from .models import ConversionJob, ConversionRequest

PIPELINE_VERSION = "assisted-batched-v3"
TERMINAL = {"ready", "needs_review", "failed", "cancelled"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class LostLease(RuntimeError):
    pass


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "guide2build.sqlite3"
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL, state TEXT NOT NULL, lease_owner TEXT,
                    lease_until REAL, cancel_requested INTEGER NOT NULL DEFAULT 0,
                    available_at REAL NOT NULL DEFAULT 0, checkpoint TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS eligible_jobs ON jobs(state, available_at, lease_until);
                CREATE TABLE IF NOT EXISTS job_keys (key TEXT PRIMARY KEY, request_key TEXT NOT NULL,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id));
                CREATE TABLE IF NOT EXISTS job_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL, stage TEXT NOT NULL, state TEXT NOT NULL,
                    message TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (revision TEXT PRIMARY KEY, set_number TEXT NOT NULL,
                    guide_id TEXT NOT NULL, scene TEXT NOT NULL, items TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS guide_heads (set_number TEXT NOT NULL, guide_id TEXT NOT NULL,
                    latest_revision TEXT NOT NULL, reviewed_revision TEXT, PRIMARY KEY(set_number,guide_id));
                CREATE TABLE IF NOT EXISTS review_actions (operation_key TEXT PRIMARY KEY,
                    request_hash TEXT NOT NULL, base_revision TEXT NOT NULL, result_revision TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _event(self, db, job, message):
        db.execute("INSERT INTO job_events(job_id,stage,state,message,created_at) VALUES(?,?,?,?,?)",
                   (job["job_id"], job["stage"], job["state"], message, now()))

    def _save(self, db, job):
        job["updated_at"] = now()
        ConversionJob.model_validate(job)
        db.execute("UPDATE jobs SET payload=?,state=? WHERE job_id=?",
                   (json.dumps(job), job["state"], job["job_id"]))

    def enqueue(self, request: ConversionRequest, key: str, source_revision: str, *, source_hash: str | None = None) -> dict:
        reference = self.data_dir / "reconstructions" / request.set_number / request.guide_id / "scene.json"
        reference_hash = (hashlib.sha256(reference.read_bytes()).hexdigest()
                          if request.mode == "assisted" and reference.is_file() else None)
        scope = {**request.model_dump(), "source_revision": source_revision,
                 "pipeline": PIPELINE_VERSION, "provider": "disabled", "prompt": "none",
                 "parts": self.parts_revision(), "assisted_reference": reference_hash}
        fingerprint = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
        artifact_request = hashlib.sha256((fingerprint + (source_hash or "pending-source")).encode()).hexdigest()
        with self.connect(write=True) as db:
            previous = db.execute("SELECT * FROM job_keys WHERE key=?", (key,)).fetchone()
            if previous and previous["request_key"] != fingerprint:
                raise Conflict("Idempotency key already used for a different request")
            if previous:
                row = db.execute("SELECT payload FROM jobs WHERE job_id=?", (previous["job_id"],)).fetchone()
                return json.loads(row["payload"])
            row = db.execute("SELECT payload FROM jobs WHERE request_key=?", (artifact_request,)).fetchone()
            if not row and source_hash:
                for candidate in db.execute("SELECT DISTINCT jobs.payload FROM jobs JOIN job_keys USING(job_id) "
                                            "WHERE job_keys.request_key=?", (fingerprint,)):
                    if json.loads(candidate[0]).get("source_sha256") == source_hash:
                        row = candidate
                        break
            if row:
                job = json.loads(row["payload"])
            else:
                job = ConversionJob(job_id=uuid.uuid4().hex, **request.model_dump(), state="queued",
                                    stage="queued", created_at=now(), updated_at=now()).model_dump()
                db.execute("INSERT INTO jobs(job_id,request_key,payload,state) VALUES(?,?,?,?)",
                           (job["job_id"], artifact_request, json.dumps(job), "queued"))
                self._event(db, job, "PDF-assisted source preparation queued; no automatic conversion claimed.")
            db.execute("INSERT OR IGNORE INTO job_keys VALUES(?,?,?)", (key, fingerprint, job["job_id"]))
            return job

    def parts_revision(self):
        root = self.data_dir / "public/ldraw"
        path = root / "provenance.json"
        if not path.is_file():
            return hashlib.sha256(b"no-part-catalogue").hexdigest()
        manifest = json.loads(path.read_text())
        # A fetch timestamp is not a new library revision; scope jobs to content.
        identity = {kind: {name: {key: item.get(key) for key in ("sha256", "url", "dependencies")}
                           for name, item in manifest.get(kind, {}).items()}
                    for kind in ("resources", "materials")}
        identity["file_map"] = manifest.get("file_map", {})
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def get(self, job_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            raise KeyError(job_id)
        return ConversionJob.model_validate_json(row["payload"]).model_dump()

    def events(self, job_id):
        self.get(job_id)
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM job_events WHERE job_id=? ORDER BY event_id", (job_id,))]

    def latest_job(self, set_number, guide_id):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM jobs ORDER BY rowid DESC").fetchall()
        return next((j for r in rows if (j := json.loads(r[0]))["set_number"] == set_number
                     and j["guide_id"] == guide_id), None)

    def claim(self, owner: str, lease_seconds=300) -> tuple[dict, dict] | None:
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE (state='queued' AND available_at<=?) OR "
                             "(lease_owner IS NOT NULL AND lease_until<?) ORDER BY rowid LIMIT 1",
                             (time.time(), time.time())).fetchone()
            if not row:
                return None
            job = json.loads(row["payload"])
            if row["cancel_requested"]:
                job["state"] = "cancelled"
                self._save(db, job)
                db.execute("UPDATE jobs SET lease_owner=NULL,lease_until=NULL WHERE job_id=?", (job["job_id"],))
                self._event(db, job, "Cancelled before the next bounded stage.")
                return None
            job["attempts"] += 1
            job["state"] = "fetching"
            job["error"] = None
            self._save(db, job)
            db.execute("UPDATE jobs SET lease_owner=?,lease_until=? WHERE job_id=?",
                       (owner, time.time() + lease_seconds, job["job_id"]))
            self._event(db, job, "Worker claimed job; retained prior checkpoints.")
            return job, json.loads(row["checkpoint"])

    def heartbeat(self, job_id: str, owner: str, *, lease_seconds=300) -> None:
        """Renew only a live owned lease, or durably acknowledge cancellation."""
        cancelled = False
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            self._require_lease(row, owner)
            job = json.loads(row["payload"])
            if row["cancel_requested"]:
                cancelled = True
                job.update(state="cancelled", stage="cancelled")
                self._save(db, job)
                db.execute("UPDATE jobs SET lease_owner=NULL,lease_until=NULL WHERE job_id=?", (job_id,))
                self._event(db, job, "Cancelled; committed source and page checkpoints retained.")
            else:
                db.execute("UPDATE jobs SET lease_until=? WHERE job_id=?", (time.time() + lease_seconds, job_id))
        if cancelled:
            raise InterruptedError("Cancelled")

    @staticmethod
    def _require_lease(row, owner):
        if (not row or row["lease_owner"] != owner or row["lease_until"] is None
                or row["lease_until"] < time.time() or row["state"] in TERMINAL):
            raise LostLease("Worker no longer owns the job")

    def check_active(self, job_id: str, owner: str) -> None:
        """Read-only cancellation/ownership probe unless cancellation needs acknowledgement."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            self._require_lease(row, owner)
            cancelled = row["cancel_requested"]
        if cancelled:
            self.heartbeat(job_id, owner)

    def checkpoint(self, job_id, owner, stage, checkpoint, *, state=None, message="Stage completed", **updates):
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            self._require_lease(row, owner)
            job = json.loads(row["payload"])
            job.update(updates, stage=stage, state=state or stage)
            if row["cancel_requested"]:
                job["state"] = "cancelled"
                message = "Cancelled after the current bounded stage."
            self._save(db, job)
            terminal = job["state"] in TERMINAL
            db.execute("UPDATE jobs SET checkpoint=?,lease_owner=?,lease_until=? WHERE job_id=?",
                       (json.dumps(checkpoint), None if terminal else owner,
                        None if terminal else time.time() + 300, job_id))
            self._event(db, job, message)
            return job

    def cancel(self, job_id):
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            job = json.loads(row["payload"])
            if job["state"] not in TERMINAL:
                db.execute("UPDATE jobs SET cancel_requested=1 WHERE job_id=?", (job_id,))
                if not row["lease_owner"]:
                    job["state"] = "cancelled"
                    self._save(db, job)
                self._event(db, job, "Cancellation requested.")
            return job

    def retry(self, job_id):
        with self.connect(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            job = json.loads(row["payload"])
            if job["state"] == "queued":
                return job
            if job["state"] not in {"failed", "cancelled", "needs_review"}:
                raise Conflict("Only stopped jobs can be retried")
            if job["state"] == "failed" and not (job.get("error") or {}).get("retryable"):
                raise Conflict("This failure requires a source or configuration correction")
            if job["attempts"] >= 3:
                raise Conflict("Retry limit reached; inspect retained evidence")
            job.update(state="queued", error=None)
            self._save(db, job)
            db.execute("UPDATE jobs SET cancel_requested=0,lease_owner=NULL,lease_until=NULL,available_at=? "
                       "WHERE job_id=?", (time.time() + min(2 ** job["attempts"], 30), job_id))
            self._event(db, job, "Retry queued from retained checkpoint.")
            return job
