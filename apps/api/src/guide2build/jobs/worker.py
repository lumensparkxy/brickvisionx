"""Bounded assisted preparation. No reference access occurs in automated mode."""
import hashlib
import json
import threading
import time
import uuid
import httpx
from ..catalog import find_guide
from ..core.models import SceneManifest
from ..source import download_pdf, render_pages
from ..review.service import ReviewService
from .store import LostLease, Store, PIPELINE_VERSION
from .source_cache import cached_receipt


class LeaseHeartbeat:
    """Keep a long stage alive independently of download/render progress."""

    def __init__(self, store, job_id, owner, *, interval=10):
        self.store, self.job_id, self.owner = store, job_id, owner
        self.interval = interval
        self.stopped = threading.Event()
        self.error = None
        self.last_check = 0.0
        self.thread = threading.Thread(target=self._run, name="preparation-heartbeat", daemon=True)

    def _run(self):
        while not self.stopped.wait(self.interval):
            try:
                self.store.heartbeat(self.job_id, self.owner)
            except Exception as error:
                self.error = error
                return

    def start(self):
        self.store.heartbeat(self.job_id, self.owner)
        self.thread.start()

    def check(self, *, force=False):
        if self.error:
            raise self.error
        current = time.monotonic()
        if force or current - self.last_check >= 0.25:
            self.store.check_active(self.job_id, self.owner)
            self.last_check = current

    def close(self):
        self.stopped.set()
        if self.thread.ident is not None:
            self.thread.join()


def run_once(store: Store, *, owner: str | None = None) -> bool:
    owner = owner or uuid.uuid4().hex
    claimed = store.claim(owner)
    if not claimed:
        return False
    job, checkpoint = claimed
    job_id = job["job_id"]
    heartbeat = LeaseHeartbeat(store, job_id, owner)

    def advance(stage, **kwargs):
        nonlocal job
        job = store.checkpoint(job_id, owner, stage, checkpoint, **kwargs)
        if job["state"] == "cancelled":
            raise InterruptedError("Cancelled")

    try:
        heartbeat.start()
        if job["mode"] != "assisted":
            advance("blocked", state="failed", error={"code": "provider_unavailable", "message":
                "No runtime vision provider configured. Assisted authoring is a separate workflow.", "retryable": False})
            return True
        guide = find_guide(job["set_number"], job["guide_id"])
        source_dir = store.data_dir / "sources" / job["set_number"] / job["guide_id"]
        source_file = source_dir / "source.pdf"
        advance("fetching", message="Resolving curated official booklet.")
        receipt = cached_receipt(store.data_dir, job["set_number"], job["guide_id"], guide["pdf_url"])
        if receipt is None:
            receipt = download_pdf(guide["pdf_url"], source_file, check_cancel=heartbeat.check)
        heartbeat.check(force=True)
        digest = receipt["sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid source receipt digest")
        checkpoint["source_sha256"] = digest
        artifact_key = hashlib.sha256((digest + PIPELINE_VERSION + store.parts_revision()).encode()).hexdigest()
        advance("rendering", source_sha256=digest, artifact_key=artifact_key,
                completed_units=0, total_units=None, message="Official source bytes retained and SHA-256 verified.")
        page_dir = store.data_dir / "public/pages" / digest

        def page_progress(completed, total):
            heartbeat.check(force=True)
            checkpoint["render_progress"] = {"completed_pages": completed, "total_pages": total}
            advance("rendering", completed_units=completed, total_units=total,
                    message=f"Rendered and verified {completed} of {total} official pages.")

        pages = render_pages(source_file, page_dir, expected_sha256=digest,
                             check_cancel=heartbeat.check, on_progress=page_progress)
        heartbeat.check(force=True)
        if guide.get("expected_page_count") is not None and len(pages) != guide["expected_page_count"]:
            raise ValueError("Official source page count changed; guide identity needs review")
        checkpoint["pages"] = pages
        advance("validating", completed_units=len(pages), total_units=len(pages),
                message="Rendered official pages; checking available assisted reference.")
        reference = store.data_dir / "reconstructions" / job["set_number"] / job["guide_id"] / "scene.json"
        if not reference.is_file():
            advance("needs_review", state="needs_review",
                    error={"code": "assisted_reference_unavailable", "message":
                        "Official pages are ready. Source-backed part mappings and placements need authoring and review.",
                        "retryable": False}, message="Source prepared; assembly remains unresolved.")
            return True
        scene = SceneManifest.model_validate_json(reference.read_text())
        if (scene.source_sha256 != digest or scene.set_number != job["set_number"] or scene.guide_id != job["guide_id"]):
            raise ValueError("Reference does not match the downloaded source identity")
        if any(i.origin == "vision_proposal" for i in scene.instances):
            raise ValueError("Assisted reference cannot masquerade as an automatic proposal")
        findings_path = reference.with_name("review-items.json")
        findings = json.loads(findings_path.read_text()).get("items", []) if findings_path.is_file() else []
        heartbeat.check(force=True)
        ReviewService(store).import_scene(scene, findings)
        checkpoint["reference_loaded"] = True
        # An authored reference may be explored even while unresolved. Never upgrade its review status here.
        state = "ready" if scene.status in {"agent_reviewed", "human_reviewed"} else "needs_review"
        advance(state, state=state, output_revision=scene.revision,
                message="Loaded existing PDF-assisted reference; this was not an automatic reconstruction.")
    except (InterruptedError, LostLease):
        pass
    except Exception as error:
        retryable = isinstance(error, (httpx.TransportError, TimeoutError)) or (
            isinstance(error, httpx.HTTPStatusError) and error.response.status_code in {429, 500, 502, 503, 504})
        code = "source_temporarily_unavailable" if retryable else "preparation_failed"
        try:
            advance("failed", state="failed", error={"code": code,
                    "message": "Source preparation failed; retained checkpoints can be inspected locally.",
                    "retryable": retryable}, message="Preparation stopped; no reconstruction success recorded.")
        except (InterruptedError, LostLease):
            pass
    finally:
        heartbeat.close()
    return True
