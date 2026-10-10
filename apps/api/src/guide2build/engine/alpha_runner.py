"""Leased official-source execution for explicitly requested approximate alpha jobs."""
from __future__ import annotations

import hashlib
import json
import time

from ..catalog import find_guide
from ..jobs.source_cache import cached_receipt
from ..source import download_pdf, render_pages
from .provider import GoogleAdkProvider, ProviderFailure
from .runtime import PAUSE_PROVIDER_CODES, ModelCallBudgetExhausted, runtime_choice
from .store import LeaseLost

ALPHA_PIPELINE = "adk-direct-alpha-v1"


def alpha_runtime_choice(config, checkpoint, *, historical=False):
    if historical:
        return (checkpoint.get("alpha_runtime_override") or checkpoint.get("runtime_choice")
                or {key: config[key] for key in ("provider", "model", "reasoning", "thinking_level", "provider_timeout")
                    if key in config})
    if checkpoint.get("alpha_runtime_override") is not None:
        raise ValueError("Historical alpha runtime overrides cannot execute; enqueue a new ADK revision")
    return runtime_choice(config, checkpoint)


def run_alpha_claimed(store, job, owner, provider=None, *, max_chunks=None, stop_event=None):
    """Process only the already-claimed alpha job; never grant release approval."""
    from .alpha import generate_alpha
    from .runner import Heartbeat, WorkerStopped, atomic_json

    checkpoint = job["checkpoint"]
    config = job["config"]
    directory = store.root / "jobs" / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    def save(stage, state="constructing", error=None):
        checkpoint["stage"] = stage
        checkpoint["uncertainty_notes"] = checkpoint.get("alpha_review_notes", checkpoint.get("uncertainty_notes", []))
        checkpoint["completed_pages"] = checkpoint.get("alpha_completed_pages", 0)
        checkpoint.setdefault("source_coverage", "partial")
        store.checkpoint(job["id"], owner, checkpoint, state, error)

    try:
        if config.get("generation_mode") != "alpha_fast" or config.get("quality_profile") != "alpha":
            raise ValueError("Direct alpha requires explicit mode and alpha profile")
        if provider is None and (config.get("provider") != "google_adk"
                or str(config.get("pipeline", ALPHA_PIPELINE)).startswith("codex-")):
            save("historical_alpha_runtime_blocked", "blocked", {"code": "fresh_adk_revision_required",
                "message": "Historical provider evidence is preserved; enqueue a new ADK revision."})
            return True
        if checkpoint.get("alpha_runner_version", ALPHA_PIPELINE) != ALPHA_PIPELINE:
            raise ValueError("Alpha pipeline changed; preserve prior experiment and use a new revision")
        checkpoint["alpha_runner_version"] = ALPHA_PIPELINE
        if checkpoint.get("alpha_source_complete"):
            save("alpha_complete", "paused")
            return True
        with Heartbeat(store, job["id"], owner, stop_event=stop_event) as heartbeat:
            heartbeat.check()
            continuation = None
            if job["set_number"] == "10316" and job["guide_id"] in {"booklet-02", "booklet-03"}:
                predecessor = "booklet-01" if job["guide_id"] == "booklet-02" else "booklet-02"
                prior_control = next((value for value in reversed(store.queue_snapshot())
                    if value["set_number"] == job["set_number"] and value["guide_id"] == predecessor
                    and value["generation_mode"] == "alpha_fast"
                    and value["revision"] == config.get("revision")), None)
                if not prior_control or not prior_control["alpha_source_complete"] or prior_control["owner"]:
                    save("alpha_waiting_for_booklet", "blocked", {"code": "alpha_predecessor_required",
                        "message": f"Finish the unverified {predecessor} alpha source before carrying its parts forward."})
                    return True
                # Hydrate and hash only the actual predecessor assembly. Other
                # completed sets contribute no assembly evidence to this job.
                prior = store.get(prior_control["id"])
                if not prior["checkpoint"].get("alpha_source_complete") or prior["owner"]:
                    raise ValueError("Alpha predecessor changed before continuation")
                continuation = prior["checkpoint"].get("candidate")
                if not continuation:
                    raise ValueError("Completed prior alpha booklet has no candidate")
                checkpoint["predecessor_job_id"] = prior["id"]
            guide = find_guide(job["set_number"], job["guide_id"])
            source = store.data_dir / "sources" / job["set_number"] / job["guide_id"] / "source.pdf"
            receipt = cached_receipt(store.data_dir, job["set_number"], job["guide_id"], guide["pdf_url"])
            if receipt is None:
                receipt = download_pdf(guide["pdf_url"], source, check_cancel=heartbeat.check)
            source_hash = receipt["sha256"]
            if (checkpoint.get("source_sha256", source_hash) != source_hash
                    or config.get("source_sha256") not in (None, source_hash)):
                raise ValueError("Official source changed since alpha experiment was created")
            checkpoint["source_sha256"] = source_hash
            pages_dir = store.data_dir / "public/pages" / source_hash
            page_manifest = pages_dir / "pages.json"
            pinned = checkpoint.get("alpha_page_manifest_sha256")
            if pinned:
                if (page_manifest.resolve() != page_manifest or not page_manifest.is_file()
                        or page_manifest.stat().st_size > 8_000_000
                        or hashlib.sha256(page_manifest.read_bytes()).hexdigest() != pinned):
                    raise ValueError("Pinned alpha page manifest changed")
                pages = json.loads(page_manifest.read_text())
            else:
                save("alpha_preparing_source")
                pages = render_pages(source, pages_dir, expected_sha256=source_hash, check_cancel=heartbeat.check)
                checkpoint["alpha_page_manifest_sha256"] = hashlib.sha256(page_manifest.read_bytes()).hexdigest()
            if len(pages) != guide["expected_page_count"]:
                raise ValueError("Official source page count differs from curated booklet")
            checkpoint["page_count"] = len(pages)
            atomic_json(directory / "source-receipt.json", receipt)
            runtime_choice = alpha_runtime_choice(config, checkpoint)
            runtime = provider or GoogleAdkProvider(model=runtime_choice["model"],
                thinking_level=runtime_choice["thinking_level"], timeout=runtime_choice["provider_timeout"])
            scene = generate_alpha(store=store, job=job, provider=runtime, checkpoint=checkpoint,
                directory=directory, source_hash=source_hash, pages_dir=pages_dir, page_count=len(pages),
                save=save, heartbeat=heartbeat, continuation=continuation, max_chunks=max_chunks)
            # The batching module can release its lease at an intermediate checkpoint or blocker.
            latest = store.get(job["id"])
            if latest["owner"] is None:
                return True
            if scene is None:
                raise ValueError("Alpha generation returned no candidate without a recorded blocker")
            notes = checkpoint.get("alpha_review_notes", [])
            checkpoint["uncertainty_notes"] = notes
            checkpoint["completed_pages"] = checkpoint.get("alpha_completed_pages", 0)
            complete = checkpoint["completed_pages"] == len(pages)
            checkpoint["alpha_source_complete"] = complete
            checkpoint["source_coverage"] = "all_pages_processed_approximate_unverified" if complete else "partial"
            atomic_json(directory / "alpha-report.json", {"job_id": job["id"],
                "artifact_kind": checkpoint.get("artifact_kind", config.get("artifact_kind", "automatic_approximate_alpha")),
                "generation_mode": "alpha_fast", "source_sha256": source_hash,
                "primary_scene_source_sha256": scene.source_sha256,
                "source_coverage": checkpoint["source_coverage"], "completed_pages": checkpoint["completed_pages"],
                "page_count": len(pages), "main_steps": len({(s.section_id, s.main_step_number)
                    for s in scene.steps if s.main_step_number is not None
                    and s.source.source_sha256 == source_hash}) if scene else 0,
                "snapshot_count": len(scene.steps), "physical_instances": len(scene.instances),
                "agent_source_corrections": checkpoint.get("alpha_assisted_corrections", []),
                "runtime_choice": runtime_choice, "runtime_changes": checkpoint.get("alpha_runtime_history", []),
                "uncertainty_notes": notes, "camera_agreement": "approximate_unverified",
                "geometry_check": "not_run", "connector_check": "not_run", "human_review": "not_run",
                "physical_build": "not_run", "publication": "not_performed"})
            save("alpha_complete" if complete else "alpha_chunk_ready", "paused")
    except ProviderFailure as error:
        reason = {"code": error.code, "message": str(error)[:2000]}
        if error.code in PAUSE_PROVIDER_CODES:
            store.pause_provider(reason)
        save("alpha_provider_blocked", "blocked", reason)
    except ModelCallBudgetExhausted as error:
        save("alpha_model_call_budget_exhausted", "paused", {"code": "model_call_budget_exhausted", "message": str(error)})
    except KeyboardInterrupt:
        try:
            save("alpha_interrupted", "paused", {"code": "alpha_interrupted",
                "message": "Generation interrupted; accepted chunks and consumed attempts are retained."})
        except (LeaseLost, InterruptedError):
            pass
        raise
    except WorkerStopped as error:
        try:
            save("alpha_queue_stopped", "paused", {"code": "queue_stopped", "message": str(error)})
        except (LeaseLost, InterruptedError):
            pass
    except InterruptedError:
        try:
            save("alpha_cancelled", "cancelled")
        except InterruptedError:
            pass
    except LeaseLost:
        return True
    except Exception as error:
        save("alpha_blocked", "blocked", {"code": "alpha_generation_blocked", "message": str(error)[:2000]})
    finally:
        atomic_json(directory / "alpha-run-timing.json", {"last_pass_elapsed_seconds": time.monotonic()-started,
            "pipeline": ALPHA_PIPELINE, "completion_or_accuracy_claim": False})
    return True
