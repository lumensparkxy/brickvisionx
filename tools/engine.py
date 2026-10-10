"""Local batch engine entrypoint. No cloud identity or publication authority is required."""
import argparse
import hashlib
import json
import logging
import math
import sqlite3
import sys
import time
from pathlib import Path
from _paths import ROOT
from guide2build.catalog import find_guide
from guide2build.engine.store import EngineStore, PIPELINE
from guide2build.engine.runtime import DEFAULT_MODEL, DEFAULT_THINKING_LEVEL, DEFAULT_INFERENCE_TIMEOUT_SECONDS
from guide2build.engine.runner import run_once
from guide2build.engine.scheduling import run_queue_wave
from guide2build.engine.activity_logging import ActivityObserver, LOGGER, follow_activity, log_activity
from guide2build.jobs.source_cache import cached_receipt


def configure_activity_logging(level):
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s",
                                           datefmt="%Y-%m-%dT%H:%M:%S%z"))
    LOGGER.handlers = [handler]
    LOGGER.setLevel(level)
    LOGGER.propagate = False


def provider_timeout_argument(value):
    if value == "none":
        return None
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Use 'none' or a positive timeout up to 3600 seconds") from None
    if not math.isfinite(seconds) or not 0 < seconds <= 3600:
        raise argparse.ArgumentTypeError("Use 'none' or a positive timeout up to 3600 seconds")
    return seconds


def shared_budget_config(store, root_id, *, set_number, guide_id, source_sha256,
                         model, thinking_level, maximum, execution_policy):
    """Link a fresh source-only revision to an existing immutable experiment budget."""
    root = store.get(root_id)
    config = root["config"]
    checkpoint_root = root["checkpoint"].get("budget_root_job_id", root_id)
    config_root = config.get("budget_root_job_id", root_id)
    if checkpoint_root != root_id or config_root != root_id:
        raise ValueError("Share the original budget root, not a descendant job")
    if execution_policy != "explore" or config.get("execution_policy") != "explore":
        raise ValueError("Shared experiment budgets require exploration jobs")
    if (root["set_number"], root["guide_id"]) != (set_number, guide_id):
        raise ValueError("Shared experiment budgets require the same set and booklet")
    if not source_sha256 or config.get("source_sha256") != source_sha256:
        raise ValueError("Shared experiment budgets require the same verified source hash")
    if (config["model"], config["thinking_level"], config["max_model_calls"]) != (
            model, thinking_level, maximum):
        raise ValueError("Shared experiment model, thinking level and request ceiling must stay unchanged")
    if root["owner"] and (root["lease_until"] or 0) > time.time():
        raise ValueError("Do not create a runtime revision while the budget root is running")
    if store.lineage_model_calls_used(root_id) >= maximum:
        raise ValueError("The shared experiment model-call budget is exhausted")
    return {"budget_root_job_id": root_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "var")
    parser.add_argument("--log-level", choices=("INFO", "WARNING", "ERROR"), default="INFO",
                        help="Activity logs go to stderr; JSON results stay on stdout (default INFO)")
    commands = parser.add_subparsers(dest="command", required=True)
    enqueue = commands.add_parser("enqueue")
    enqueue.add_argument("--all", action="store_true", help="Enqueue all 19 curated booklets")
    enqueue.add_argument("--set", dest="set_number")
    enqueue.add_argument("--guide")
    enqueue.add_argument("--model", default=DEFAULT_MODEL)
    enqueue.add_argument("--thinking-level", choices=("low", "medium", "high"), default=DEFAULT_THINKING_LEVEL)
    enqueue.add_argument("--provider-timeout", type=provider_timeout_argument, default=DEFAULT_INFERENCE_TIMEOUT_SECONDS,
                         help="Per-request seconds or 'none' for no client deadline; frozen in this job")
    enqueue.add_argument("--share-budget-with", metavar="JOB_ID",
                         help="Fresh exploration revision sharing an existing same-source request ceiling")
    enqueue.add_argument("--execution-policy", choices=("strict", "explore"), default="strict",
                         help="Explore retains quality findings and continues through the booklet")
    enqueue.add_argument("--proposal-profile", choices=("baseline", "attachment-reasoning", "event-scoped"), default="baseline",
                         help="Opt-in exploration prompt experiment; baseline preserves the existing prompt")
    enqueue.add_argument("--review-profile", choices=("legacy", "localized-source-v4"), default="legacy",
                         help="Opt-in rendered instance localization; legacy preserves retained review behavior")
    enqueue.add_argument("--source-reference-profile", choices=("legacy", "exact-source-v1"), default="legacy",
                         help="Opt-in exploration only: constrain structured source references to the verified current PDF/page")
    enqueue.add_argument("--efficiency-profile", choices=("legacy", "incremental-v1"),
                         help="New explore jobs default to incremental-v1; legacy preserves original context/repair policy")
    enqueue.add_argument("--new-part-failure-profile", choices=("legacy", "new-design-rejection-v2"), default="legacy",
                         help="Opt-in exploration only: reject newly proposed Shortcut designs without publishing incomplete closures")
    enqueue.add_argument("--max-model-calls", type=int, default=3,
                         help="Frozen inference ceiling for all modes, including retries and correction calls")
    enqueue.add_argument("--revision", default="1", help="Explicit new experiment identity; never overwrites old jobs")
    enqueue.add_argument("--max-panel-attempts", type=int, choices=range(1, 6), default=None,
                         help="Persisted proposal/repair ceiling per instruction (1–5; retries retain it)")
    enqueue.add_argument("--quality-profile", choices=("strict", "alpha"), default="strict",
                         help="Image-fit RMS limit: strict 4 px, alpha 8 px (both retain the 12 px point cap). Alpha samples remain unverified.")
    step = commands.add_parser("step", help="Process at most one new main instruction for this job, then pause")
    step.add_argument("job_id")
    for command in ("run", "watch"):
        worker = commands.add_parser(command)
        if command == "run":
            worker.add_argument("--job-id", help="Run only this experiment, including a paused correction fork")
        worker.add_argument("--sync-cloud", action="store_true", help="Sync requests every 300s using uploader identity")
        worker.add_argument("--project", default="lumensparkxy")
        worker.add_argument("--max-jobs", type=int, default=1 if command == "run" else 0,
                            help="0 drains queue; watch then polls until interrupted")
        worker.add_argument("--workers", type=int, choices=(1, 2), default=1,
                            help="Explicit local concurrency; different sets only, default one")
        worker.add_argument("--poll-seconds", type=int, default=30)
    for command in ("status", "report"):
        commands.add_parser(command)
    logs = commands.add_parser("logs", help="Read saved activity/progress without starting or changing a job")
    logs.add_argument("job_id")
    logs.add_argument("--follow", action="store_true", help="Follow until the job stops; Ctrl-C stops only the observer")
    for command in ("retry", "cancel"):
        action = commands.add_parser(command)
        action.add_argument("job_id")
        if command == "retry":
            action.add_argument("--reset-candidate", action="store_true", help="Quarantine invalid candidate; preserve raw calls and source index")
    resume = commands.add_parser("resume")
    resume.add_argument("job_id", nargs="?")
    resume.add_argument("--provider", action="store_true", help="Clear global pause after authentication/quota recovery")
    resume.add_argument("--retry-provider-calls", action="store_true",
                        help="Explicit explore-only retry in fresh evidence slots; failed attempts stay charged")
    render = commands.add_parser("render")
    render.add_argument("job_id")
    render.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("job_id")
    validate.add_argument("--bundle", type=Path, required=True)
    package = commands.add_parser("package")
    package.add_argument("job_id")
    package.add_argument("--output", type=Path, required=True)
    evaluate = commands.add_parser("evaluate", help="Measure a candidate and write private comparison evidence")
    evaluate.add_argument("job_id")
    evaluate.add_argument("--reference", type=Path, help="Source-reviewed scoring annotations")
    evaluate.add_argument("--baseline", type=Path, help="Frozen comparison scene; not independent ground truth")
    evaluate.add_argument("--output", type=Path)
    correction = commands.add_parser("fork-correction", help="Create an immutable corrected experiment or replay branch")
    correction.add_argument("job_id")
    correction.add_argument("--request", type=Path, required=True)
    correction.add_argument("--revision", required=True)
    args = parser.parse_args()
    if args.command in {"run", "watch", "step", "logs"}:
        configure_activity_logging(args.log_level)
    if args.command == "logs":
        # Do not construct EngineStore: read-only observation must not create,
        # migrate or alter a live or historical database.
        try:
            follow_activity(args.data_dir, args.job_id, follow=args.follow)
        except (sqlite3.Error, LookupError, ValueError, OSError):
            parser.exit(2, "Activity logs unavailable: check the job ID and --data-dir; no job was changed.\n")
        return 0
    store = EngineStore(args.data_dir)
    if args.command == "enqueue":
        if args.new_part_failure_profile != "legacy" and args.execution_policy != "explore":
            parser.error("New-part rejection requires --execution-policy explore")
        if args.proposal_profile != "baseline" and args.execution_policy != "explore":
            parser.error("A proposal profile requires --execution-policy explore")
        if args.review_profile != "legacy" and args.execution_policy != "explore":
            parser.error("A source review profile requires --execution-policy explore")
        if args.source_reference_profile != "legacy" and args.execution_policy != "explore":
            parser.error("A source reference profile requires --execution-policy explore")
        efficiency_profile = args.efficiency_profile or (
            "incremental-v1" if args.execution_policy == "explore" else "legacy")
        if efficiency_profile != "legacy" and args.execution_policy != "explore":
            parser.error("The incremental efficiency profile requires --execution-policy explore")
        panel_attempts = args.max_panel_attempts or (2 if args.execution_policy == "explore" else 3)
        if args.execution_policy == "explore" and panel_attempts > 2:
            parser.error("Exploration permits an initial proposal and at most one targeted repair per instruction")
        if not 1 <= args.max_model_calls <= 1000:
            parser.error("Use a model-call ceiling between 1 and 1000")
        if args.all:
            if args.set_number or args.guide:
                parser.error("--all cannot be combined with --set or --guide")
            if args.share_budget_with:
                parser.error("Shared budgets require one selected set and booklet")
            store.gate_campaign()
            catalogue = json.loads((ROOT / "config/sets.json").read_text())
            pairs = [(s["set_number"], g["guide_id"]) for s in catalogue["sets"] for g in s["guides"]]
        elif args.set_number and args.guide:
            pairs = [(args.set_number, args.guide)]
        else:
            parser.error("Provide --all or both --set and --guide")
        result = []
        provenance = store.data_dir / "public/ldraw/provenance.json"
        library = hashlib.sha256(provenance.read_bytes()).hexdigest() if provenance.is_file() else "missing"
        for set_number, guide_id in pairs:
            guide = find_guide(set_number, guide_id)
            receipt = cached_receipt(store.data_dir, set_number, guide_id, guide["pdf_url"])
            shared = {}
            if args.share_budget_with:
                try:
                    shared = shared_budget_config(store, args.share_budget_with,
                        set_number=set_number, guide_id=guide_id,
                        source_sha256=receipt["sha256"] if receipt else None,
                        model=args.model, thinking_level=args.thinking_level,
                        maximum=args.max_model_calls, execution_policy=args.execution_policy)
                except (KeyError, ValueError) as error:
                    parser.error(str(error))
            job = store.enqueue(set_number, guide_id, {"model": args.model, "thinking_level": args.thinking_level,
                "provider_timeout": args.provider_timeout, "provider": "google_adk",
                "revision": args.revision, "pipeline": PIPELINE, "parts_revision": library,
                "max_panel_attempts": panel_attempts,
                "execution_policy": args.execution_policy, "max_model_calls": args.max_model_calls,
                "quality_profile": args.quality_profile,
                "source_sha256": receipt["sha256"] if receipt else None,
                **shared,
                **({"new_part_failure_profile": args.new_part_failure_profile} if args.new_part_failure_profile != "legacy" else {}),
                **({"efficiency_profile": efficiency_profile} if efficiency_profile != "legacy" else {}),
                **({"proposal_profile": args.proposal_profile} if args.proposal_profile != "baseline" else {}),
                **({"review_profile": args.review_profile} if args.review_profile != "legacy" else {}),
                **({"source_reference_profile": args.source_reference_profile} if args.source_reference_profile != "legacy" else {})})
            result.append({key: job[key] for key in ("id", "set_number", "guide_id", "state")})
        print(json.dumps(result, indent=2))
    elif args.command == "step":
        job = store.get(args.job_id)
        print(json.dumps({"job_id": job["id"], "action": "one_main_instruction",
                          "note": "First invocation indexes the official booklet before constructing instruction 1."}), flush=True)
        with ActivityObserver(args.data_dir, job["id"]):
            processed = run_once(store, job_id=job["id"], max_panels=1)
        job = store.get(job["id"])
        print(json.dumps({"job_id": job["id"], "processed": processed, "state": job["state"],
            "completed_panels": job["checkpoint"].get("completed_panels", 0),
            "total_panels": job["checkpoint"].get("total_panels"),
            "error": job["error"], "provider_pause": store.provider_pause(),
            "scene": str(store.root / "jobs" / job["id"] / "scene.json") if job["checkpoint"].get("candidate") else None,
            "note": "Paused candidates require inspection; no review or publication is implied."}, indent=2))
    elif args.command in {"run", "watch"}:
        if args.max_jobs < 0 or not 1 <= args.poll_seconds <= 300:
            parser.error("Use nonnegative --max-jobs and --poll-seconds between 1 and 300")
        if getattr(args, "job_id", None) and args.workers != 1:
            parser.error("A targeted job runs with one worker; use the queue for independent sets")
        completed = 0
        sync_loop = None
        if args.sync_cloud:
            from guide2build.engine.cloud_sync import RequestSyncLoop
            sync_loop = RequestSyncLoop(store, {"model": DEFAULT_MODEL, "thinking_level": DEFAULT_THINKING_LEVEL,
                                        "provider": "google_adk", "max_model_calls": 3, "revision": "cloud-request-v1"},
                                        args.project, lambda value: print(json.dumps(value), flush=True))
            sync_loop.start()
        with ActivityObserver(args.data_dir, getattr(args, "job_id", None)):
            log_activity(logging.INFO, "Starting %s worker; workers=%d; max_jobs=%d",
                         args.command, args.workers, args.max_jobs)
            try:
                while True:
                    reported = 0

                    def report_result(result):
                        nonlocal reported
                        reported += int(result["processed"])
                        print(json.dumps(result | {"processed_jobs": completed + reported}), flush=True)

                    target = getattr(args, "job_id", None)
                    wave = run_queue_wave(store, job_ids=[target] if target else None, workers=args.workers,
                        max_jobs=max(0, args.max_jobs-completed) if args.max_jobs else 0,
                        on_result=report_result)
                    completed += wave["processed_jobs"]
                    if wave["processed_jobs"]:
                        if getattr(args, "job_id", None) or args.max_jobs and completed >= args.max_jobs:
                            break
                    elif args.command == "run" or store.provider_pause():
                        break
                    else:
                        log_activity(logging.INFO, "Queue idle; checking again in %ds", args.poll_seconds)
                        time.sleep(args.poll_seconds)
            except KeyboardInterrupt:
                log_activity(logging.INFO, "Queue interrupted; accepted checkpoints and consumed attempts retained")
                print("Stopped; accepted checkpoints and consumed attempts are retained for resume.")
            finally:
                if sync_loop:
                    sync_loop.close()
        log_activity(logging.INFO, "Worker stopped; processed jobs=%d", completed)
        print(json.dumps({"provider_pause": store.provider_pause(), "processed_jobs": completed}))
    elif args.command in {"status", "report"}:
        jobs = store.list()
        result = {"pipeline": PIPELINE, "provider_pause": store.provider_pause(), "jobs": []}
        for job in jobs:
            cp = job["checkpoint"]
            from guide2build.engine.evaluation import summarize_job_calls
            from guide2build.engine.quality import quality_summary
            metrics = summarize_job_calls(store.root / "jobs" / job["id"])
            result["jobs"].append({key: job[key] for key in ("id", "set_number", "guide_id", "state", "error")}
                | {"stage": cp.get("stage"), "source_sha256": cp.get("source_sha256"),
                   **metrics, "subscription_cost": "not_reported_by_cli",
                   "indexed_pages": len(cp.get("page_indexes", [])), "page_count": cp.get("page_count"),
                   "completed_panels": cp.get("completed_panels", 0), "total_panels": cp.get("total_panels"),
                   "execution_policy": job["config"].get("execution_policy", "strict"),
                   "processed_panels": cp.get("processed_panels", cp.get("completed_panels", 0)),
                   "reconstructed_panels": cp.get("reconstructed_panels", cp.get("completed_panels", 0)),
                   "model_calls_used": cp.get("model_calls_used"),
                   "max_model_calls": job["config"].get("max_model_calls"),
                   "current_panel_attempt": cp.get("current_panel_attempt"),
                   "image_quality": quality_summary(job["config"], cp),
                   "evidence": str(store.root / "jobs" / job["id"]), "human_review": "not_run",
                   "physical_build": "not_run", "published": False})
        print(json.dumps(result, indent=2))
    elif args.command == "evaluate":
        from guide2build.engine.evaluation import evaluate_job
        report = evaluate_job(store, args.job_id, reference_path=args.reference,
                              baseline_path=args.baseline, output=args.output)
        # Full findings and image receipts stay in the report; long booklets can
        # otherwise produce megabytes of repeated review evidence on stdout.
        print(json.dumps({key: report[key] for key in (
            "job_id", "scene_sha256", "assisted", "coverage", "source_scores",
            "diagnostic_finding_counts", "final_assembly_diagnostic_finding_counts",
            "measurements", "correction_count", "repair_passes", "artifacts",
        ) if key in report}, indent=2))
    elif args.command == "fork-correction":
        from guide2build.engine.corrections import fork_correction
        derived = fork_correction(store, args.job_id, args.request, args.revision)
        print(json.dumps({key: derived[key] for key in ("id", "state", "set_number", "guide_id", "config")}, indent=2))
    elif args.command == "cancel":
        store.cancel(args.job_id)
        print(json.dumps({"job_id": args.job_id, "cancel_requested": True}))
    elif args.command in {"retry", "resume"}:
        if args.command == "resume" and args.retry_provider_calls and not args.job_id:
            parser.error("--retry-provider-calls requires a job ID")
        if args.job_id:
            if args.command == "retry" and args.reset_candidate:
                store.reset_candidate(args.job_id)
            store.retry(args.job_id, retry_provider_calls=(args.command == "resume" and args.retry_provider_calls))
        elif not args.provider:
            parser.error("Provide a job ID or --provider")
        if args.command == "resume" and args.provider:
            store.resume_provider()
        print(json.dumps({"job_id": args.job_id, "provider_pause": store.provider_pause()}))
    elif args.command == "render":
        from guide2build.engine.rendering import render_candidate
        job = store.get(args.job_id)
        directory = store.root / "jobs" / job["id"]
        report = render_candidate(directory / "scene.json", directory / "geometry", args.output)
        store.record_render(job["id"], args.output, report)
        print(json.dumps(report, indent=2))
    elif args.command == "validate":
        from guide2build.engine.validation import import_validation
        print(json.dumps(import_validation(store, args.job_id, args.bundle), indent=2))
    elif args.command == "package":
        from guide2build.releases.models import SceneV2, ReleaseValidation
        from guide2build.releases.packaging import package_release
        job = store.get(args.job_id)
        directory = store.root / "jobs" / job["id"]
        scene = SceneV2.model_validate_json((directory / "validated-scene.json").read_text())
        validation = ReleaseValidation.model_validate_json((directory / "release-validation.json").read_text())
        imported = json.loads((directory / "validation-import.json").read_text())
        from guide2build.releases.models import digest
        raw = SceneV2.model_validate_json((directory / "scene.json").read_text())
        if digest(raw) != imported["raw_scene_sha256"]:
            raise ValueError("Raw candidate changed after independent validation")
        from guide2build.engine.validation import import_validation, ValidationBundle
        bundle_dir = Path(imported["bundle_directory"])
        bundle = ValidationBundle.model_validate_json((bundle_dir / "validation-bundle.json").read_text())
        if digest(bundle) != imported["validation_bundle_sha256"]:
            raise ValueError("Independent validation bundle changed after import")
        import_validation(store, job["id"], bundle_dir)
        scene = SceneV2.model_validate_json((directory / "validated-scene.json").read_text())
        validation = ReleaseValidation.model_validate_json((directory / "release-validation.json").read_text())
        manifest = package_release(scene, validation, directory / "geometry", args.output,
            preview=Path(imported["preview"]),
            source_index=json.loads((directory / "verified-source-index.json").read_text()))
        store.staged(job["id"], manifest)
        print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
