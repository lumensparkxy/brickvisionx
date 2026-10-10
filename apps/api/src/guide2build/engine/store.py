"""Durable bounded queue with fenced leases and hash-bound resumable checkpoints."""
from __future__ import annotations
import hashlib
import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .checkpoint_artifacts import checkpoint_metadata, hydrate_checkpoint, serialize_checkpoint
from .runtime import DEFAULT_MAX_MODEL_CALLS, reject_secret_config, runtime_choice

PIPELINE = "adk-spatial-repair-v1"
TERMINAL = {"blocked", "failed", "cancelled", "awaiting_approval", "paused"}


def execution_config(config):
    """Persist an explicit policy and finite experiment limits, without relaxing source checks."""
    if not isinstance(config, dict):
        raise ValueError("Engine configuration must be an object")
    config = dict(config)
    reject_secret_config(config)
    if "reasoning" in config:
        raise ValueError("Use thinking_level for the Google ADK runtime")
    config.update(runtime_choice(config))
    config.setdefault("max_model_calls", DEFAULT_MAX_MODEL_CALLS)
    policy = config.setdefault("execution_policy", "strict")
    if policy not in {"strict", "explore"}:
        raise ValueError("Unknown execution policy")
    from .closure_publication import profile
    new_part_profile = profile(config)
    config.pop("new_part_failure_profile", None)
    if new_part_profile != "legacy":
        config["new_part_failure_profile"] = new_part_profile
    efficiency_profile = config.pop("efficiency_profile", "legacy")
    if not isinstance(efficiency_profile, str) or efficiency_profile not in {"legacy", "incremental-v1"}:
        raise ValueError("Unknown efficiency profile")
    if efficiency_profile == "incremental-v1":
        if policy != "explore" or config.get("generation_mode", "strict") != "strict":
            raise ValueError("The incremental efficiency profile requires the exploration engine")
        config["efficiency_profile"] = efficiency_profile
    from .attachment_prompt import prompt_suffix
    proposal_profile = config.pop("proposal_profile", "baseline")
    suffix = prompt_suffix(proposal_profile)
    if suffix:
        if policy != "explore":
            raise ValueError("A proposal profile requires the explore execution policy")
        config["proposal_profile"] = proposal_profile
    from .localized_review import normalize_profile
    review_profile = normalize_profile(config.pop("review_profile", "legacy"))
    if review_profile != "legacy":
        if policy != "explore" or config.get("generation_mode", "strict") != "strict":
            raise ValueError("A source review profile requires the exploration engine")
        config["review_profile"] = review_profile
    from .source_reference import profile as source_reference_profile
    exact_source = source_reference_profile(config)
    config.pop("source_reference_profile", None)
    if exact_source != "legacy":
        config["source_reference_profile"] = exact_source
    if policy == "explore":
        config.setdefault("max_repair_passes", 2)
        attempts = config.setdefault("max_panel_attempts", 2)
        if type(attempts) is not int or not 1 <= attempts <= 2:
            raise ValueError("Exploration permits one proposal and at most one targeted repair")
    for key, lower, upper in (("max_model_calls", 1, 1000), ("max_repair_passes", 0, 2),
                              ("max_placement_candidates", 1, 64), ("max_assembly_alternatives", 1, 8)):
        if key in config and (type(config[key]) is not int or not lower <= config[key] <= upper):
            raise ValueError(f"{key} must be a finite integer from {lower} to {upper}")
    # Reject NaN/Infinity anywhere, including otherwise opaque provider configuration.
    json.dumps(config, allow_nan=False)
    return config


class LeaseLost(RuntimeError):
    pass


class EngineStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir).resolve()
        self.root = self.data_dir / "engine"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "jobs.sqlite3"
        if self.root.resolve() != self.root or self.db.is_symlink():
            raise ValueError("Engine storage must remain inside its configured private root")
        with self.connect() as con:
            con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS engine_jobs (
                id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
                set_number TEXT NOT NULL, guide_id TEXT NOT NULL, config TEXT NOT NULL,
                state TEXT NOT NULL, checkpoint TEXT NOT NULL DEFAULT '{}',
                owner TEXT, lease_until REAL, cancel INTEGER NOT NULL DEFAULT 0,
                error TEXT, created REAL NOT NULL, updated REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS engine_queue ON engine_jobs(state, created);
            CREATE TABLE IF NOT EXISTS engine_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                created REAL NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS engine_control (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS engine_corrections (
                correction_id TEXT PRIMARY KEY, parent_job_id TEXT NOT NULL,
                child_job_id TEXT NOT NULL UNIQUE, request_sha256 TEXT NOT NULL,
                parent_scene_sha256 TEXT NOT NULL, created REAL NOT NULL);
            """)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def decode(self, row):
        value = dict(row)
        for key in ("config", "error"):
            value[key] = json.loads(value[key]) if value[key] else None
        value["checkpoint"] = hydrate_checkpoint(self.root, value["id"], value["checkpoint"])
        return value

    def event(self, con, job_id, event, detail):
        con.execute("INSERT INTO engine_events(job_id,created,event,detail) VALUES(?,?,?,?)",
                    (job_id, time.time(), event, json.dumps(detail)))

    def enqueue(self, set_number, guide_id, config):
        from ..catalog import find_guide
        from .quality import source_view_policy
        config = execution_config(config)
        source_view_policy(config.get("quality_profile", "strict"))
        mode = config.get("generation_mode", "strict")
        if mode not in {"strict", "alpha_fast"}:
            raise ValueError("Unknown generation mode")
        if mode == "alpha_fast" and config.get("quality_profile") != "alpha":
            raise ValueError("Fast alpha generation requires the explicit alpha profile")
        guide = find_guide(set_number, guide_id)
        identity = {"set": set_number, "guide": guide_id, "url": guide["pdf_url"],
                    "pipeline": PIPELINE, "config": config}
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        # New explicit defaults must not enqueue a second paid conversion for an
        # otherwise identical pre-policy request. Existing rows remain unchanged.
        legacy_config = dict(config)
        if config["execution_policy"] == "strict":
            legacy_config.pop("execution_policy")
        elif config.get("max_panel_attempts") == 2:
            legacy_config.pop("max_panel_attempts")
        legacy_fingerprint = hashlib.sha256(json.dumps(identity | {"config": legacy_config}, sort_keys=True).encode()).hexdigest()
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            old = con.execute("SELECT * FROM engine_jobs WHERE fingerprint IN (?,?)",
                              (fingerprint, legacy_fingerprint)).fetchone()
            if old:
                return self.decode(old)
            job_id = uuid.uuid4().hex
            now = time.time()
            con.execute("""INSERT INTO engine_jobs
                (id,fingerprint,set_number,guide_id,config,state,created,updated) VALUES(?,?,?,?,?,'queued',?,?)""",
                (job_id, fingerprint, set_number, guide_id, json.dumps(config), now, now))
            self.event(con, job_id, "queued", identity)
        return self.get(job_id)

    def fork_revision(self, parent_job_id, *, correction_id, expected_scene_sha256,
                      request_sha256, config, checkpoint, materialize, expected_checkpoint_sha256=None):
        """Fence a correction against leases and stale scenes; publish its new job atomically.

        ``materialize`` writes only the newly allocated private directory. No rendering or
        inference happens while holding the transaction. A failed copy remains private and
        unreferenced, never becoming a resumable job or altering the parent.
        """
        from ..releases.models import SceneV2, digest
        config = execution_config(config)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM engine_jobs WHERE id=?", (parent_job_id,)).fetchone()
            if not row:
                raise KeyError(parent_job_id)
            if row["owner"] and (row["lease_until"] or 0) > time.time():
                raise ValueError("Cannot correct an actively leased job")
            if con.execute("SELECT 1 FROM engine_corrections WHERE correction_id=?", (correction_id,)).fetchone():
                raise ValueError("Duplicate correction_id; the existing immutable correction is retained")
            parent = self.decode(row)
            if expected_checkpoint_sha256 is not None and digest(parent["checkpoint"]) != expected_checkpoint_sha256:
                raise ValueError("Parent checkpoint changed during correction preparation")
            candidate = parent["checkpoint"].get("candidate")
            scene_file = self.root / "jobs" / parent_job_id / "scene.json"
            if not candidate or digest(SceneV2.model_validate(candidate)) != expected_scene_sha256:
                raise ValueError("Stale expected scene hash")
            if (scene_file.is_symlink() or not scene_file.resolve().is_relative_to(self.root.resolve())
                    or not scene_file.is_file() or scene_file.stat().st_size > 128_000_000
                    or digest(SceneV2.model_validate_json(scene_file.read_text())) != expected_scene_sha256):
                raise ValueError("Stored scene differs from the expected correction base")
            revision = config.get("revision")
            if revision == parent["config"].get("revision") or revision == candidate.get("revision"):
                raise ValueError("A correction requires a new revision")
            for sibling in con.execute("SELECT config FROM engine_jobs WHERE set_number=? AND guide_id=?",
                                       (parent["set_number"], parent["guide_id"])):
                if json.loads(sibling["config"]).get("revision") == revision:
                    raise ValueError("Correction revision already exists")
            child_id = uuid.uuid4().hex
            destination = self.root / "jobs" / child_id
            destination.mkdir(parents=True, exist_ok=False)
            materialize(destination)
            now = time.time()
            fingerprint = digest({"parent": parent_job_id, "request": request_sha256, "config": config})
            con.execute("""INSERT INTO engine_jobs
                (id,fingerprint,set_number,guide_id,config,state,checkpoint,created,updated)
                VALUES(?,?,?,?,?,'paused',?,?,?)""", (child_id, fingerprint, parent["set_number"],
                    parent["guide_id"], json.dumps(config, allow_nan=False),
                    serialize_checkpoint(self.root, child_id, checkpoint), now, now))
            con.execute("INSERT INTO engine_corrections VALUES(?,?,?,?,?,?)", (correction_id, parent_job_id,
                        child_id, request_sha256, expected_scene_sha256, now))
            self.event(con, child_id, "correction_forked", {"parent_job_id": parent_job_id,
                "correction_id": correction_id, "request_sha256": request_sha256,
                "parent_scene_sha256": expected_scene_sha256, "artifact_kind": "agent_corrected_exploration"})
        return self.get(child_id)

    def lineage_model_calls_used(self, root_job_id):
        """Aggregate local reservations across sibling repairs without counting inherited calls twice.

        Same-set leases exclude simultaneous sibling reservations even when two
        different sets run concurrently. ``model_calls_used`` is an aggregate
        watermark, not an additive per-job count. Metadata reads do not hydrate
        every sibling candidate merely to count model calls.
        """
        root_used = 0
        descendants_used = 0
        with self.connect() as con:
            rows = con.execute("SELECT id,config,checkpoint FROM engine_jobs").fetchall()
        for job in rows:
            checkpoint = checkpoint_metadata(job["checkpoint"])
            config = json.loads(job["config"])
            origin = checkpoint.get("budget_root_job_id", config.get("budget_root_job_id", job["id"]))
            if job["id"] != root_job_id and origin != root_job_id:
                continue
            calls = max(len(checkpoint.get("exploration_calls", {})),
                        len(checkpoint.get("model_requests", {})))
            local = checkpoint.get("local_model_calls_used", calls)
            if job["id"] == root_job_id:
                local = checkpoint.get("local_model_calls_used", max(calls, checkpoint.get("model_calls_used", 0)))
            floor = checkpoint.get("budget_origin_model_calls_used", 0)
            if any(type(value) is not int or value < 0 for value in (local, floor)):
                raise ValueError("Corrupt lineage model-call accounting")
            root_used = max(root_used, floor)
            if job["id"] == root_job_id:
                root_used = max(root_used, local)
            else:
                descendants_used += max(local, calls)
        return root_used + descendants_used

    def get(self, job_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM engine_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self.decode(row)

    def list(self):
        with self.connect() as con:
            rows = con.execute("SELECT * FROM engine_jobs ORDER BY created").fetchall()
        return [self.decode(row) for row in rows]

    def queue_snapshot(self, job_ids=None):
        """Scheduler control fields only: no candidate artifact reads or hashing."""
        where, parameters = "", ()
        if job_ids is not None:
            if (not isinstance(job_ids, (list, tuple, set)) or len(job_ids) > 1000
                    or any(not isinstance(identity, str) for identity in job_ids)):
                raise ValueError("Queue job IDs must be a bounded collection of strings")
            if not job_ids:
                return []
            parameters = tuple(job_ids)
            where = " WHERE id IN (" + ",".join("?" for _ in parameters) + ")"
        with self.connect() as con:
            rows = con.execute("SELECT id,set_number,guide_id,state,owner,lease_until,cancel,updated,config,checkpoint,error "
                "FROM engine_jobs" + where + " ORDER BY created,id", parameters).fetchall()
        result = []
        for row in rows:
            config = json.loads(row["config"])
            checkpoint = checkpoint_metadata(row["checkpoint"])
            complete = checkpoint.get("alpha_source_complete") is True
            error = json.loads(row["error"]) if row["error"] else None
            counters = {key: checkpoint.get(key, 0) for key in ("completed_pages", "completed_panels")}
            counters["alpha_completed_pages"] = checkpoint.get("alpha_completed_pages", counters["completed_pages"])
            if any(type(value) is not int or value < 0 for value in counters.values()):
                raise ValueError("Invalid checkpoint queue progress counters")
            error_code = error.get("code") if isinstance(error, dict) else None
            result.append({key: row[key] for key in ("id", "set_number", "guide_id", "state", "owner", "lease_until", "cancel", "updated")} | {
                "generation_mode": config.get("generation_mode", "strict"), "alpha_source_complete": complete,
                "revision": config.get("revision"),
                "error_code": error_code, "error": {"code": error_code} if error is not None else None,
                **counters})
        return result

    def cancel_requested(self, job_id):
        """Heartbeat check that never reads or hydrates a checkpoint."""
        with self.connect() as con:
            row = con.execute("SELECT cancel FROM engine_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return bool(row["cancel"])

    def claim(self, owner, seconds=120, job_id=None, max_concurrent_jobs=1):
        if type(max_concurrent_jobs) is not int or not 1 <= max_concurrent_jobs <= 2:
            raise ValueError("max_concurrent_jobs must be an integer from 1 to 2")
        if (not isinstance(owner, str) or not owner or len(owner) > 200
                or isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or not 0 < seconds <= 3600):
            raise ValueError("A claim needs a bounded owner and finite positive lease")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT 1 FROM engine_control WHERE key='provider_pause'").fetchone():
                return None
            now = time.time()
            active = con.execute("SELECT set_number FROM engine_jobs WHERE owner IS NOT NULL AND lease_until>?", (now,)).fetchall()
            if len(active) >= max_concurrent_jobs:
                return None  # Global count, including workers launched by another CLI.
            active_sets = {item["set_number"] for item in active}
            rows = con.execute("""SELECT * FROM engine_jobs WHERE
                (state='queued' OR (state='paused' AND id=?) OR
                (owner IS NOT NULL AND lease_until<=?)) AND (? IS NULL OR id=?)
                ORDER BY created""", (job_id, now, job_id, job_id)).fetchall()
            gated = con.execute("SELECT 1 FROM engine_control WHERE key='pilot_gate'").fetchone()
            passed = con.execute("""SELECT 1 FROM engine_jobs WHERE set_number='30669' AND guide_id='alt-02'
                AND state='awaiting_approval'""").fetchone()
            row = next((row for row in rows if row["set_number"] not in active_sets and (not gated or passed or
                        (json.loads(row["config"]).get("generation_mode") == "alpha_fast" and
                         json.loads(row["config"]).get("quality_profile") == "alpha") or
                        (row["set_number"] == "30669" and row["guide_id"] == "alt-02"))), None)
            if not row:
                return None
            # Reject a corrupt candidate before publishing the new lease.
            claimed = self.decode(row)
            state = "cancelled" if row["cancel"] else "constructing"
            con.execute("UPDATE engine_jobs SET owner=?,lease_until=?,state=?,updated=? WHERE id=?",
                        (owner, now + seconds, state, now, row["id"]))
            self.event(con, row["id"], "claimed", {"owner": owner, "max_concurrent_jobs": max_concurrent_jobs})
            claimed.update(owner=owner, lease_until=now + seconds, state=state, updated=now)
        return claimed

    def checkpoint(self, job_id, owner, checkpoint, state="constructing", error=None):
        # Publishing can be slower than SQL; never hold a write transaction while
        # serializing a growing assembly. Recheck the lease under the final fence.
        with self.connect() as con:
            row = con.execute("SELECT owner,lease_until FROM engine_jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row["owner"] != owner or (row["lease_until"] or 0) < time.time():
            raise LeaseLost(job_id)
        encoded_error = json.dumps(error, allow_nan=False) if error else None
        encoded = serialize_checkpoint(self.root, job_id, checkpoint)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM engine_jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["owner"] != owner or (row["lease_until"] or 0) < time.time():
                raise LeaseLost(job_id)
            if row["cancel"]:
                state = "cancelled"
            terminal = state in TERMINAL
            con.execute("""UPDATE engine_jobs SET checkpoint=?,state=?,error=?,updated=?,owner=?,lease_until=?
                WHERE id=?""", (encoded, state, encoded_error, time.time(),
                                None if terminal else owner, None if terminal else time.time()+120, job_id))
            self.event(con, job_id, state, {"stage": checkpoint.get("stage"), "error": error})
        if state == "cancelled":
            raise InterruptedError("Job cancelled")

    def heartbeat(self, job_id, owner):
        with self.connect() as con:
            updated = con.execute("""UPDATE engine_jobs SET lease_until=? WHERE id=? AND owner=?
                AND lease_until>? AND cancel=0""", (time.time()+120, job_id, owner, time.time()))
            if updated.rowcount != 1:
                raise LeaseLost(job_id)

    def cancel(self, job_id):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT owner,lease_until FROM engine_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            now = time.time()
            inactive = row["owner"] is None or (row["lease_until"] or 0) <= now
            con.execute("""UPDATE engine_jobs SET cancel=1,
                state=CASE WHEN ? THEN 'cancelled' ELSE state END,
                owner=CASE WHEN ? THEN NULL ELSE owner END,
                lease_until=CASE WHEN ? THEN NULL ELSE lease_until END,updated=? WHERE id=?""",
                (inactive, inactive, inactive, now, job_id))
            self.event(con, job_id, "cancel_requested", {})

    def retry(self, job_id):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM engine_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            if row["owner"] and row["lease_until"] > time.time():
                raise ValueError("Cannot retry an actively leased job")
            if row["state"] == "awaiting_approval":
                raise ValueError("A staged candidate needs review, not inference retry")
            con.execute("UPDATE engine_jobs SET state='queued',cancel=0,owner=NULL,lease_until=NULL,error=NULL WHERE id=?",
                        (job_id,))
            self.event(con, job_id, "resumed", {})

    def pause_provider(self, reason):
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO engine_control(key,value) VALUES('provider_pause',?)",
                        (json.dumps(reason),))

    def resume_provider(self):
        with self.connect() as con:
            con.execute("DELETE FROM engine_control WHERE key='provider_pause'")

    def provider_pause(self):
        with self.connect() as con:
            row = con.execute("SELECT value FROM engine_control WHERE key='provider_pause'").fetchone()
            return json.loads(row[0]) if row else None

    def gate_campaign(self):
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO engine_control(key,value) VALUES('pilot_gate','true')")

    def staged(self, job_id, manifest):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM engine_jobs WHERE id=?", (job_id,)).fetchone()
            if not row or (row["owner"] and row["lease_until"] > time.time()):
                raise ValueError("Cannot stage unknown or actively leased job")
            from ..releases.packaging import verify_manifest
            verify_manifest(manifest)
            if manifest["set_number"] != row["set_number"] or manifest["guide_id"] != row["guide_id"]:
                raise ValueError("Staged manifest identity does not match the queued job")
            checkpoint = hydrate_checkpoint(self.root, job_id, row["checkpoint"])
            if manifest["source_sha256"] != checkpoint.get("candidate", {}).get("source_sha256"):
                raise ValueError("Staged manifest does not bind the job source")
            checkpoint["staged_manifest"] = manifest
            con.execute("UPDATE engine_jobs SET state='awaiting_approval',checkpoint=?,error=NULL WHERE id=?",
                        (serialize_checkpoint(self.root, job_id, checkpoint), job_id))
            self.event(con, job_id, "awaiting_approval", {"publication": "not_performed"})
            if row["set_number"] == "10316" and row["guide_id"] in {"booklet-01", "booklet-02"}:
                successor = "booklet-02" if row["guide_id"] == "booklet-01" else "booklet-03"
                revision = json.loads(row["config"]).get("revision")
                for waiting in con.execute("SELECT * FROM engine_jobs WHERE set_number='10316' AND guide_id=? AND state='blocked'", (successor,)).fetchall():
                    error = json.loads(waiting["error"]) if waiting["error"] else {}
                    if error.get("code") == "prior_booklet_required" and json.loads(waiting["config"]).get("revision") == revision:
                        con.execute("UPDATE engine_jobs SET state='queued',error=NULL WHERE id=?", (waiting["id"],))
                        self.event(con, waiting["id"], "dependency_available", {"predecessor_job_id": job_id})

    def reset_candidate(self, job_id):
        """Reserve a maintenance transaction so a watcher cannot claim during file quarantine."""
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM engine_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            job = self.decode(row)
            if (job["owner"] and job["lease_until"] > time.time()) or job["state"] == "awaiting_approval":
                raise ValueError("Cannot reset an active or staged candidate; enqueue a new revision")
            directory = self.root / "jobs" / job_id
            quarantine = directory / "rejected" / uuid.uuid4().hex
            quarantine.mkdir(parents=True, exist_ok=True)
            for name in ("scene.json", "validated-scene.json", "release-validation.json", "validation-import.json"):
                source = directory / name
                if source.exists():
                    source.replace(quarantine / name)
            checkpoint = job["checkpoint"]
            for key in ("candidate", "completed_panels", "page_reviews", "panel_reviews", "staged_manifest", "render_directory",
                        "render_scene_sha256", "render_report_sha256"):
                checkpoint.pop(key, None)
            con.execute("UPDATE engine_jobs SET checkpoint=? WHERE id=?",
                        (serialize_checkpoint(self.root, job_id, checkpoint), job_id))
            self.event(con, job_id, "candidate_quarantined", {"reason": "Explicit reset; retained raw evidence"})

    def record_render(self, job_id, output, report):
        from ..releases.models import SceneV2, digest
        directory = self.root / "jobs" / job_id
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM engine_jobs WHERE id=?", (job_id,)).fetchone()
            if not row or (row["owner"] and row["lease_until"] > time.time()):
                raise ValueError("Cannot attach external render to unknown or actively changing job")
            scene = SceneV2.model_validate_json((directory / "scene.json").read_text())
            if report["scene_sha256"] != digest(scene):
                raise ValueError("Candidate changed during rendering")
            checkpoint = hydrate_checkpoint(self.root, job_id, row["checkpoint"])
            checkpoint.update(render_directory=str(output.resolve()), render_scene_sha256=digest(scene),
                              render_report_sha256=hashlib.sha256((output / "report.json").read_bytes()).hexdigest())
            con.execute("UPDATE engine_jobs SET checkpoint=? WHERE id=?",
                        (serialize_checkpoint(self.root, job_id, checkpoint), job_id))
            self.event(con, job_id, "render_recorded", {"scene_sha256": digest(scene)})
