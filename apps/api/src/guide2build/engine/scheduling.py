"""Bounded local scheduling for independent sets; instruction order stays inside each job."""
from __future__ import annotations

import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait


def run_queue_wave(store, *, job_ids=None, workers=1, max_jobs=0, max_panels=None,
                   on_result=None, run_job=None):
    """Attempt each eligible selected job once, with at most two independent sets active.

    No worker is started until this function is explicitly called. SQLite claims
    remain authoritative across separate CLI processes; an unclaimable job is
    attempted once rather than spinning or falling back to an unrelated job.
    """
    if type(workers) is not int or not 1 <= workers <= 2:
        raise ValueError("Worker count must be an integer between 1 and 2")
    if type(max_jobs) is not int or max_jobs < 0:
        raise ValueError("Job ceiling must be a nonnegative integer")
    if max_panels is not None and (type(max_panels) is not int or max_panels < 1):
        raise ValueError("Instruction limit must be a positive integer")
    if run_job is None:
        from .runner import run_once
        run_job = run_once
    selected = job_ids is not None
    if selected:
        job_ids = list(job_ids)
        if len(set(job_ids)) != len(job_ids):
            raise ValueError("Selected job IDs must be unique")
    now = time.time()
    snapshot = store.queue_snapshot(job_ids)
    if selected:
        by_id = {job["id"]: job for job in snapshot}
        snapshot = [by_id[identity] for identity in job_ids if identity in by_id]
    pending = [job for job in snapshot if not job["cancel"] and not job["alpha_source_complete"]
               and (job["state"] == "queued" or selected and job["state"] == "paused"
                    or job["owner"] is not None and (job["lease_until"] or 0) <= now)]
    stop_event = threading.Event()
    active, active_sets = {}, set()
    processed, attempted = 0, 0
    results = []
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="guide2build-set")
    try:
        while pending or active:
            if store.provider_pause():
                pending.clear()
                stop_event.set()
            while pending and len(active) < workers and not stop_event.is_set():
                # Reserving at most the remaining ceiling avoids overshooting it
                # when both futures complete at the same time.
                if max_jobs and processed + len(active) >= max_jobs:
                    break
                index = next((i for i, job in enumerate(pending)
                              if job["set_number"] not in active_sets), None)
                if index is None:
                    break
                job = pending.pop(index)
                future = executor.submit(run_job, store, job_id=job["id"], max_panels=max_panels,
                                         max_concurrent_jobs=workers, stop_event=stop_event)
                active[future] = job
                active_sets.add(job["set_number"])
                attempted += 1
            if not active:
                break
            # Short timed waits let Ctrl-C or a provider pause stop the other
            # in-flight worker through its existing cancellation checks.
            finished, _ = wait(active, timeout=0.25, return_when=FIRST_COMPLETED)
            for future in finished:
                job = active.pop(future)
                active_sets.remove(job["set_number"])
                did_process = bool(future.result())
                processed += did_process
                result = {"job_id": job["id"], "set_number": job["set_number"],
                          "guide_id": job["guide_id"], "processed": did_process}
                results.append(result)
                if on_result is not None:
                    on_result(result)
            if max_jobs and processed >= max_jobs:
                pending.clear()
    except BaseException:
        stop_event.set()
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    return {"workers": workers, "attempted_jobs": attempted, "processed_jobs": processed,
            "results": results, "provider_pause": store.provider_pause()}
