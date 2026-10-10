"""Compact camera/landmark context from this job's own accepted evidence only."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

from ..releases.models import SceneV2, digest as scene_digest
from .connectors import world_landmark
from .preview import confined_bytes
from .source_view import SourceCamera, SourceViewObservation

SOURCE_VIEWS_MAX_BYTES = 1_000_000
SOURCE_PAGE_MAX_BYTES = 16_000_000


def accepted_alignment_context(directory: Path, checkpoint: dict, candidate: dict | None) -> dict | None:
    """Reuse named correspondences, never a camera or pose from another revision.

    Missing legacy/rebased receipts yield no context. A receipt claiming the exact
    current scene must be complete, confined to this job, and match its file hash;
    corruption never falls back to older or rejected trial evidence.
    """
    if candidate is None:
        return None
    attempts = checkpoint.get("panel_attempts")
    if attempts is None:
        return None
    if not isinstance(attempts, dict):
        raise ValueError("Malformed accepted alignment checkpoint")
    candidate_hash = scene_digest(candidate)
    matches = []
    for state in attempts.values():
        if not isinstance(state, dict):
            raise ValueError("Malformed accepted alignment instruction state")
        accepted = state.get("accepted")
        if accepted is None:
            continue
        if not isinstance(accepted, dict):
            raise ValueError("Malformed accepted alignment receipt")
        if accepted.get("scene_sha256") == candidate_hash:
            matches.append((state, accepted))
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("Multiple accepted alignment receipts claim the current scene")

    state, accepted = matches[0]
    scene = SceneV2.model_validate(candidate)
    step = scene.steps[-1]
    source_hash = step.source.source_sha256
    if (accepted.get("source_sha256") != source_hash
            or checkpoint.get("source_sha256", source_hash) != source_hash
            or type(accepted.get("page_index")) is not int
            or accepted.get("page_index") != step.source.page_index):
        raise ValueError("Accepted alignment receipt differs from the current source or last snapshot")
    directory = Path(directory).absolute()
    trial_name, trials = accepted.get("directory"), state.get("trials")
    if not isinstance(trial_name, str) or not isinstance(trials, list) or trial_name not in trials:
        raise ValueError("Accepted alignment trial is not registered in this job")
    trial = Path(trial_name)
    proposals = directory / "proposals"
    if (not trial.is_absolute() or directory.resolve() != directory
            or not trial.is_relative_to(proposals) or trial == proposals or trial.resolve() != trial):
        raise ValueError("Accepted alignment trial escapes this job's proposals")
    files = accepted.get("files")
    expected_hash = files.get("source-views.json") if isinstance(files, dict) else None
    if (not isinstance(expected_hash, str) or len(expected_hash) != 64
            or any(char not in "0123456789abcdef" for char in expected_hash)):
        raise ValueError("Accepted alignment receipt lacks a source-view file hash")
    data = confined_bytes(directory, str(trial.relative_to(directory) / "source-views.json"), SOURCE_VIEWS_MAX_BYTES)
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("Accepted alignment source-view evidence hash changed")
    record = json.loads(data)
    if (not isinstance(record, dict) or record.get("scene_sha256") != candidate_hash
            or record.get("source_sha256") != source_hash
            or type(record.get("source_page")) is not int or record["source_page"] != step.source.page_index
            or record.get("source_image_sha256") != accepted.get("source_image_sha256")):
        raise ValueError("Accepted alignment evidence differs from its scene/source receipt")
    image_hash = record.get("source_image_sha256")
    if (not isinstance(image_hash, str) or len(image_hash) != 64
            or any(char not in "0123456789abcdef" for char in image_hash)):
        raise ValueError("Accepted alignment evidence lacks a source image hash")
    observations = record.get("observations")
    if not isinstance(observations, list) or not 1 <= len(observations) <= 20:
        raise ValueError("Accepted alignment observations exceed the instruction bound")
    selected = [item for item in observations if isinstance(item, dict) and item.get("step_id") == step.step_id]
    if len(selected) != 1:
        raise ValueError("Accepted alignment evidence lacks a unique last-snapshot observation")
    observation = SourceViewObservation.model_validate(selected[0])
    if len(observation.landmarks) < 4:
        raise ValueError("Accepted alignment needs at least four named source landmarks")
    fits = record.get("fits")
    fit = fits.get(step.step_id) if isinstance(fits, dict) else None
    if not isinstance(fit, dict) or fit.get("status") != "fitted":
        raise ValueError("Accepted alignment last snapshot lacks a fitted camera")
    camera = SourceCamera.model_validate(fit.get("camera"))
    if len(directory.parents) < 3:
        raise ValueError("Accepted alignment job has no source image root")
    pages = directory.parents[2] / "public" / "pages"
    page_bytes = confined_bytes(pages, f"{source_hash}/page-{step.source.page_index:03d}.png", SOURCE_PAGE_MAX_BYTES)
    if hashlib.sha256(page_bytes).hexdigest() != image_hash:
        raise ValueError("Accepted alignment source page image hash changed")
    try:
        with Image.open(BytesIO(page_bytes)) as page:
            if page.format != "PNG" or page.size != camera.image_size:
                raise ValueError("Accepted alignment camera dimensions differ from its source page image")
            page.verify()
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError("Accepted alignment source page image is invalid") from error
    geometry = directory / "geometry"
    if geometry.resolve() != geometry:
        raise ValueError("Accepted alignment geometry escapes this job")
    parts = {part.instance_id: part for part in scene.instances}
    visible = set(step.visible_instance_ids)
    landmarks = []
    for item in observation.landmarks:
        if item.instance_id not in visible or item.instance_id not in parts:
            raise ValueError("Accepted alignment landmark is not in the last visible snapshot")
        landmarks.append({"instance_id": item.instance_id, "landmark_id": item.landmark_id,
                          "image_uv": list(item.image_uv),
                          "world_ldu": world_landmark(step.poses[item.instance_id],
                              parts[item.instance_id].geometry_ref, item.landmark_id, geometry)})
    return {"step_id": step.step_id, "scene_sha256": candidate_hash,
            "source_page": step.source.page_index, "source_sha256": source_hash,
            "source_image_sha256": image_hash, "image_size": list(camera.image_size),
            "image_coordinates": "full_page_top_left_normalized", "view_family": observation.view_family,
            "camera": {"right": list(camera.right), "up": list(camera.up)}, "landmarks": landmarks}
