"""Read-only terminal activity from durable engine events, without scene hydration.

This observer has no provider, lease or checkpoint-writing authority. Logging is
best effort; a broken output stream or unavailable database must not stop a run.
"""
from __future__ import annotations

from contextlib import closing
import json
import logging
from pathlib import Path
import re
import sqlite3
import threading
import time


LOGGER = logging.getLogger("guide2build.engine.activity")
_STAGES = {
    "source": "Checking official PDF and rendering source pages",
    "indexing": "Source page indexed",
    "source_indexed": "Booklet index saved",
    "spatial_context_ready": "Individual-part and connector context ready",
    "constructing": "Instruction reconstruction checkpoint saved",
    "instruction_ready": "Instruction saved; paused for inspection",
    "rendering_candidate": "Rendering candidate",
    "validating": "Checking rendered candidate",
    "needs_validation": "Candidate requires assembly validation",
    "construction_complete_needs_validation": "Reconstruction pass finished; validation pending",
    "exploration_source_ready": "Verified exploration source pages ready",
    "exploration_indexing": "Source page indexed",
    "exploration_call_reserved": "Model call reserved; request checkpoint saved",
    "exploration_call_completed": "Model response and call receipt saved",
    "exploration_call_failed": "Model call failed; receipt and consumed attempt retained",
    "exploration_request_recovered": "Saved model request recovered",
    "exploration_context_frozen": "Instruction context saved",
    "exploration_instruction_reserved": "Instruction proposal or repair attempt reserved",
    "exploration_trial_recorded": "Trial, render outcome and diagnostic findings saved",
    "exploration_repair_decided": "Targeted repair decision saved",
    "exploration_instruction_recorded": "Provisional instruction selection saved",
    "exploration_instruction_complete": "Instruction processed; candidate checkpoint saved",
    "exploration_instruction_ready": "Instruction saved; paused for inspection",
    "exploration_complete_with_findings": "Complete exploration pass saved; findings retained for inspection",
    "exploration_budget_exhausted": "Model-call budget exhausted; resumable checkpoint saved",
    "queue_stopped": "Worker stopped; resumable checkpoint saved",
    "provider_blocked": "Provider blocked; checkpoint retained",
    "cancelled": "Cancellation checkpoint saved",
    "blocked": "Run blocked; checkpoint retained",
}
_EVENTS = {
    "queued": "Job queued",
    "claimed": "Worker acquired job lease",
    "resumed": "Job requeued for resume",
    "cancel_requested": "Cancellation requested",
    "correction_forked": "Correction revision created",
    "candidate_quarantined": "Candidate quarantined; historical evidence retained",
    "render_recorded": "Render evidence recorded",
    "awaiting_approval": "Validated candidate staged for approval",
    "dependency_available": "Predecessor booklet available",
}
_TERMINAL = {"paused", "blocked", "failed", "cancelled", "awaiting_approval", "completed"}

# Extract only progress fields. Both legacy inline checkpoints and immutable
# candidate envelopes are supported; no candidate JSON/files reach Python.
_SNAPSHOTS = """
WITH metadata AS (
    SELECT id, set_number, guide_id, state, owner, lease_until, updated, config, error,
        CASE WHEN json_extract(checkpoint, '$._guide2build_checkpoint_storage') IS NOT NULL
             THEN json_extract(checkpoint, '$.checkpoint') ELSE checkpoint END AS cp
    FROM engine_jobs {where}
)
SELECT id, set_number, guide_id, state, owner, lease_until, updated,
    json_extract(config, '$.model') AS model,
    json_extract(config, '$.max_model_calls') AS call_limit,
    json_extract(error, '$.code') AS error_code,
    json_extract(cp, '$.stage') AS stage,
    COALESCE(json_array_length(cp, '$.page_indexes'), 0) AS indexed,
    json_extract(cp, '$.page_count') AS pages,
    COALESCE(json_extract(cp, '$.processed_panels'), json_extract(cp, '$.completed_panels'), 0) AS processed,
    COALESCE(json_extract(cp, '$.reconstructed_panels'), json_extract(cp, '$.completed_panels'), 0) AS reconstructed,
    json_extract(cp, '$.total_panels') AS instructions,
    json_extract(cp, '$.processed_source_events') AS processed_events,
    json_extract(cp, '$.reconstructed_source_events') AS reconstructed_events,
    json_extract(cp, '$.model_calls_used') AS calls,
    COALESCE(json_array_length(cp, '$.provisional_findings'), 0)
        + COALESCE(json_array_length(cp, '$.source_index_findings'), 0) AS findings,
    (SELECT json_object('id', key, 'number', json_extract(value, '$.call_number'),
                        'status', json_extract(value, '$.status'))
     FROM json_each(cp, '$.exploration_calls')
     ORDER BY json_extract(value, '$.call_number') DESC LIMIT 1) AS latest_call
FROM metadata
"""


def _label(value):
    """Allow only short single-line identifiers, never arbitrary model/error text."""
    return re.sub(r"[^A-Za-z0-9_./: -]", "?", str(value))[:128]


def log_activity(level, message, *args):
    try:
        LOGGER.log(level, message, *args)
    except Exception:
        # Observability must not become an engine failure (e.g. closed stderr).
        pass


class ActivityObserver:
    def __init__(self, data_dir: Path, job_id: str | None = None, *, interval=1.0, wait_seconds=30.0):
        self.db = Path(data_dir).resolve() / "engine/jobs.sqlite3"
        self.job_id = job_id
        self.interval = interval
        self.wait_seconds = wait_seconds
        self.cursor = None
        self.snapshots = {}
        self._signatures = {}
        self._last_progress = {}
        self._warned = False
        self._stop = threading.Event()
        self._thread = None

    def _read(self):
        # mode=ro prevents creation/migrations; query_only also forbids writes.
        with closing(sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True, timeout=0.25)) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            con.execute("BEGIN")  # Events and counters belong to one read snapshot.
            latest = con.execute("SELECT COALESCE(MAX(seq), 0) FROM engine_events").fetchone()[0]
            cursor = latest if self.cursor is None else self.cursor
            rows = con.execute(
                "SELECT seq, job_id, event, detail FROM engine_events WHERE seq > ?"
                + (" AND job_id = ?" if self.job_id else "") + " ORDER BY seq LIMIT 500",
                (cursor, self.job_id) if self.job_id else (cursor,),
            ).fetchall()
            if self.job_id:
                where, params = "WHERE id = ?", (self.job_id,)
            else:
                # Queue observers include current workers and jobs whose events
                # arrived since their last poll, without replaying old jobs.
                ids = sorted({row["job_id"] for row in rows})
                where = "WHERE owner IS NOT NULL"
                params = tuple(ids)
                if ids:
                    where += " OR id IN (" + ",".join("?" for _ in ids) + ")"
            snapshots = [dict(row) for row in con.execute(_SNAPSHOTS.format(where=where), params)]
        # Advance only after a successful complete read; bounded backlogs drain
        # over subsequent polls instead of skipping events past the batch limit.
        self.cursor = rows[-1]["seq"] if len(rows) == 500 else latest
        return rows, snapshots

    def poll(self, *, required=False):
        try:
            events, snapshots = self._read()
            if self.job_id and not snapshots:
                raise LookupError("Job not found in the selected engine database")
            by_id = {snapshot["id"]: snapshot for snapshot in snapshots}
            for event in events:
                detail = json.loads(event["detail"])
                stage = detail.get("stage")
                code = (detail.get("error") or {}).get("code")
                level = logging.WARNING if (
                    code or stage == "exploration_call_failed"
                    or event["event"] in {"blocked", "failed", "cancelled"}) else logging.INFO
                message = _STAGES.get(stage) or _EVENTS.get(event["event"]) or _label(stage or event["event"])
                log_activity(level, "[%s] %s%s", _label(event["job_id"]), message,
                             f"; error={_label(code)}" if code else "")
            now = time.monotonic()
            for job_id, snapshot in by_id.items():
                signature = tuple(snapshot[key] for key in (
                    "state", "stage", "indexed", "pages", "processed", "reconstructed", "instructions",
                    "processed_events", "reconstructed_events", "calls", "findings", "latest_call", "error_code"))
                if signature != self._signatures.get(job_id):
                    self._summary(snapshot)
                    self._signatures[job_id] = signature
                    self._last_progress[job_id] = now
                elif snapshot["owner"] and now - self._last_progress[job_id] >= self.wait_seconds:
                    active = snapshot["lease_until"] is not None and snapshot["lease_until"] > time.time()
                    log_activity(logging.INFO, "[%s] Still at %s; %s; no new checkpoint for %.0fs",
                                 _label(job_id), _label(snapshot["stage"] or snapshot["state"]),
                                 "lease active" if active else "lease expired", now - self._last_progress[job_id])
                    self._last_progress[job_id] = now
            self.snapshots = by_id
            self._warned = False
            return True
        except Exception:
            if required:
                raise
            if not self._warned:
                log_activity(logging.WARNING, "Activity log unavailable; reconstruction continues; logs will retry")
                self._warned = True
            return False

    @staticmethod
    def _summary(snapshot):
        def count(value):
            return "?" if value is None else str(value)

        call = json.loads(snapshot["latest_call"]) if snapshot["latest_call"] else None
        details = (
            f"state={_label(snapshot['state'])}; stage={_label(snapshot['stage'] or 'not_started')}; "
            f"indexed pages={snapshot['indexed']}/{count(snapshot['pages'])}; "
            f"processed instructions={snapshot['processed']}/{count(snapshot['instructions'])}; "
            f"reconstructed instructions={snapshot['reconstructed']}/{count(snapshot['instructions'])}; "
            f"model calls={count(snapshot['calls'])}/{count(snapshot['call_limit'])}; "
            f"findings={snapshot['findings']}"
        )
        if snapshot["processed_events"] is not None:
            details += (f"; source events incl. callouts processed={snapshot['processed_events']}"
                        f", reconstructed={count(snapshot['reconstructed_events'])}")
        if call:
            details += f"; latest call={_label(call['id'])} ({_label(call['status'])})"
        if snapshot["error_code"]:
            details += f"; error={_label(snapshot['error_code'])}"
        level = logging.WARNING if snapshot["error_code"] or snapshot["state"] in {"blocked", "failed"} else logging.INFO
        log_activity(level, "[%s %s/%s model=%s] %s", _label(snapshot["id"]),
              _label(snapshot["set_number"]), _label(snapshot["guide_id"]), _label(snapshot["model"]), details)

    @property
    def finished(self):
        return bool(self.job_id and self.snapshots and all(
            row["state"] in _TERMINAL and not row["owner"] for row in self.snapshots.values()))

    def _watch(self):
        while not self._stop.wait(self.interval):
            self.poll()

    def __enter__(self):
        self.poll()
        self._thread = threading.Thread(target=self._watch, name="engine-activity-log", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exception):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if not self._thread or not self._thread.is_alive():
            self.poll()  # Flush the worker's final saved checkpoint.


def follow_activity(data_dir: Path, job_id: str, *, follow=False):
    """Stop only this observer on Ctrl-C; never cancel/requeue the observed job."""
    observer = ActivityObserver(data_dir, job_id)
    try:
        observer.poll(required=True)
        while follow and not observer.finished:
            time.sleep(observer.interval)
            observer.poll()
    except KeyboardInterrupt:
        log_activity(logging.INFO, "Stopped activity observer; job %s is unchanged", _label(job_id))
