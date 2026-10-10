"""Loopback API for durable assisted preparation and immutable scene review."""
from pathlib import Path
import hashlib
import json
import os
import re
import uuid
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from .catalog import ROOT, find_set, find_guide
from .core.models import SceneManifest
from .core.bom import bill_of_materials
from .jobs.models import ConversionRequest
from .jobs.store import Conflict, Store
from .jobs.source_cache import cached_receipt
from .review.models import CorrectionRequest, ReviewRequest
from .review.service import ReviewService


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = (data_dir or Path(os.getenv("GUIDE2BUILD_DATA_DIR", str(ROOT / "var")))).resolve()
    app = FastAPI(title="Guide2Build 3D", version="0.2.0")
    store = Store(data_dir)
    reviews = ReviewService(store)
    app.state.store = store
    app.state.reviews = reviews
    public_dir = data_dir / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    parts_dir = public_dir / "ldraw"
    parts_dir.mkdir(exist_ok=True)
    app.mount("/assets-local/ldraw", StaticFiles(directory=parts_dir, follow_symlink=False), name="local-parts")

    @app.middleware("http")
    async def request_boundary(request: Request, call_next):
        request_id = uuid.uuid4().hex
        # Local-only service: avoid browser cross-origin writes to the unauthenticated review API.
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in {
                "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}:
            return JSONResponse(status_code=403, content={"detail": {"code": "origin_rejected",
                "message": "Only the local application may submit changes.", "retryable": False,
                "job_id": None, "request_id": request_id}})
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        detail = error.detail if isinstance(error.detail, dict) else {"code": "request_failed", "message": error.detail}
        return JSONResponse(status_code=error.status_code, content={"detail": {
            "retryable": False, "job_id": None, "request_id": getattr(request.state, "request_id", None), **detail}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return JSONResponse(status_code=422, content={"detail": {"code": "invalid_request",
            "message": "Request fields failed validation.", "retryable": False, "job_id": None,
            "request_id": getattr(request.state, "request_id", None)}})

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return await http_error(request, HTTPException(409, detail={"code": "revision_or_idempotency_conflict",
                                                                   "message": str(error)}))

    def missing(code, message, status=404):
        raise HTTPException(status, detail={"code": code, "message": message})

    def operation_key(key):
        if not key or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key):
            missing("invalid_idempotency_key", "A valid Idempotency-Key header is required.", 422)
        return key

    @app.get("/api/v1/config")
    def runtime_config():
        return {"mode": "local", "source_images": True, "requests_enabled": False}

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "stage": "local_prototype", "runtime_vision_provider": "disabled",
                "durable_jobs": True, "revisioned_review": True}

    def known_guide(set_number: str, guide_id: str) -> dict:
        try:
            return find_guide(set_number, guide_id)
        except ValueError:
            missing("invalid_set_number", "Set number must contain 4 to 7 digits", 422)
        except KeyError:
            missing("unsupported_guide", "Guide not supported")

    @app.get("/api/v1/sets/{set_number}")
    def set_detail(set_number: str):
        try:
            item = find_set(set_number)
        except ValueError:
            missing("invalid_set_number", "Set number must contain 4 to 7 digits", 422)
        except KeyError:
            missing("unsupported_set", "This set is not supported yet")
        for guide in item["guides"]:
            try:
                load_scene(set_number, guide["guide_id"], candidate=True)
                guide["tutorial_available"] = True
            except HTTPException:
                guide["tutorial_available"] = False
        return item

    def import_reference(set_number, guide_id):
        path = data_dir / "reconstructions" / set_number / guide_id / "scene.json"
        if path.is_file():
            try:
                scene = SceneManifest.model_validate_json(path.read_text())
                if scene.set_number != set_number or scene.guide_id != guide_id:
                    raise ValueError("Scene identity mismatch")
                guide = known_guide(set_number, guide_id)
                receipt = cached_receipt(data_dir, set_number, guide_id, guide["pdf_url"])
                if not receipt:
                    missing("source_evidence_unavailable", "Cached official source evidence is missing or invalid.", 409)
                if scene.source_sha256 != receipt["sha256"]:
                    missing("source_revision_mismatch", "The reference belongs to an older source; review the changed booklet.", 409)
                findings_path = path.with_name("review-items.json")
                findings = json.loads(findings_path.read_text()).get("items", []) if findings_path.is_file() else []
                reviews.import_scene(scene, findings)
            except (ValidationError, ValueError):
                missing("invalid_reconstruction", "The stored reconstruction failed validation and needs review.", 409)

    def load_scene(set_number: str, guide_id: str, candidate: bool = False) -> SceneManifest:
        known_guide(set_number, guide_id)
        import_reference(set_number, guide_id)
        head = reviews.heads(set_number, guide_id)
        if not head:
            missing("reconstruction_not_available",
                    "Official guide located; the 3D reconstruction has not been prepared yet.", 409)
        revision = head["latest_revision"] if candidate else head["reviewed_revision"]
        if not revision:
            missing("reconstruction_needs_review", "The candidate is available for review, not an accepted tutorial.", 409)
        scene = reviews.get(revision)
        guide = known_guide(set_number, guide_id)
        receipt = cached_receipt(data_dir, set_number, guide_id, guide["pdf_url"])
        if not receipt or receipt["sha256"] != scene.source_sha256:
            missing("source_revision_mismatch", "This reconstruction does not match the verified current source.", 409)
        return scene

    @app.get("/api/v1/sets/{set_number}/guides/{guide_id}/scene")
    def scene_detail(set_number: str, guide_id: str, candidate: bool = False):
        return load_scene(set_number, guide_id, candidate)

    @app.get("/api/v1/sets/{set_number}/guides/{guide_id}/bom")
    def bom_detail(set_number: str, guide_id: str, candidate: bool = False):
        scene = load_scene(set_number, guide_id, candidate)
        return {"revision": scene.revision, "items": bill_of_materials(scene)}

    @app.post("/api/v1/conversions", status_code=202)
    def convert(request: ConversionRequest, idempotency_key: str | None = Header(default=None)):
        key = operation_key(idempotency_key)
        guide = known_guide(request.set_number, request.guide_id)
        if request.mode == "automated":
            missing("provider_unavailable", "No runtime vision provider configured. Choose PDF-assisted review.", 503)
        receipt = cached_receipt(data_dir, request.set_number, request.guide_id, guide["pdf_url"])
        return store.enqueue(request, key, json.dumps(guide, sort_keys=True),
                             source_hash=receipt["sha256"] if receipt else None)

    def job_or_404(job_id):
        try:
            return store.get(job_id)
        except KeyError:
            missing("job_not_found", "Job not found")

    @app.get("/api/v1/jobs/{job_id}")
    def job_status(job_id: str):
        return job_or_404(job_id)

    @app.get("/api/v1/jobs/{job_id}/events")
    def job_events(job_id: str):
        job_or_404(job_id)
        return {"events": store.events(job_id)}

    @app.post("/api/v1/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        job_or_404(job_id)
        return store.cancel(job_id)

    @app.post("/api/v1/jobs/{job_id}/retry")
    def retry_job(job_id: str):
        job_or_404(job_id)
        return store.retry(job_id)

    @app.get("/api/v1/sets/{set_number}/guides/{guide_id}/status")
    def guide_status(set_number: str, guide_id: str):
        guide = known_guide(set_number, guide_id)
        import_reference(set_number, guide_id)
        head = reviews.heads(set_number, guide_id)
        scene = reviews.get(head["latest_revision"]) if head else None
        receipt = cached_receipt(data_dir, set_number, guide_id, guide["pdf_url"])
        return {"source_available": receipt is not None, "latest_candidate_revision": head["latest_revision"] if head else None,
                "latest_reviewed_revision": head["reviewed_revision"] if head else None,
                "job": store.latest_job(set_number, guide_id), "coverage": {
                    "main_steps": len({s.main_step_number for s in scene.steps}) if scene else 0,
                    "expected_main_steps": guide["expected_main_steps"], "microsteps": len(scene.steps) if scene else 0,
                    "physical_instances": len(scene.instances) if scene else 0,
                    "mode": "pdf_assisted_authoring" if scene else None}}

    def revision_or_404(revision):
        try:
            return reviews.get(revision)
        except KeyError:
            missing("revision_not_found", "Scene revision not found")

    @app.get("/api/v1/reconstructions/{revision}/scene")
    def revision_scene(revision: str):
        return revision_or_404(revision)

    @app.get("/api/v1/reconstructions/{revision}/review-items")
    def review_items(revision: str):
        revision_or_404(revision)
        return {"revision": revision, "items": reviews.items(revision)}

    def apply_operation(revision, request, key):
        revision_or_404(revision)
        try:
            scene = reviews.apply(revision, request, operation_key(key))
        except Conflict:
            raise
        except ValueError:
            missing("invalid_review_operation", "Correction or review evidence is invalid. Human identity is not verified by this API.", 422)
        return {"revision": scene.revision, "scene": scene, "checks": {
            "structure": "pass", "geometry": "not_run", "connectors": "not_run", "physical": "not_run"}}

    @app.post("/api/v1/reconstructions/{revision}/corrections")
    def correction(revision: str, request: CorrectionRequest, idempotency_key: str | None = Header(default=None)):
        return apply_operation(revision, request, idempotency_key)

    @app.post("/api/v1/reconstructions/{revision}/review")
    def review(revision: str, request: ReviewRequest, idempotency_key: str | None = Header(default=None)):
        return apply_operation(revision, request, idempotency_key)

    @app.get("/api/v1/sources/{source_hash}/pages/{page_index}")
    def source_page(source_hash: str, page_index: int):
        if not re.fullmatch(r"[a-f0-9]{64}", source_hash) or page_index < 0:
            missing("invalid_page", "Invalid source page identifier", 422)
        root = (public_dir / "pages").resolve()
        directory = root / source_hash
        path = directory / f"page-{page_index:03d}.png"
        manifest = directory / "pages.json"
        # Only a committed, checksum-verified page belongs to a prepared source.
        # Incomplete batches and symlinked files are never exposed by this route.
        if (directory.resolve() != directory or path.resolve() != path or
                manifest.resolve() != manifest or not path.is_file() or not manifest.is_file()):
            missing("page_not_found", "Rendered source page not available")
        try:
            if manifest.stat().st_size > 8 * 1024 * 1024:
                raise ValueError("Manifest too large")
            pages = json.loads(manifest.read_text())
            if not isinstance(pages, list):
                raise ValueError("Invalid manifest")
            records = [p for p in pages if isinstance(p, dict) and p.get("page_index") == page_index]
            if len(records) != 1 or records[0].get("file") != path.name:
                raise ValueError("Page not committed")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != records[0].get("sha256"):
                raise ValueError("Page changed")
        except (OSError, ValueError, TypeError):
            missing("page_not_found", "Rendered source page not available")
        return FileResponse(path, media_type="image/png")

    return app


app = create_app()
