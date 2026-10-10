"""Actual loopback Three.js renders, never a synthetic success or GPU hardware claim."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from ..catalog import ROOT
from ..releases.models import SceneV2, digest
from .provider import child_environment
from .source_view import SourceCamera, validate_rendered_source_camera


def render_candidate(scene_path: Path, geometry: Path, output: Path, check=lambda: None, timeout=900, first_step=1,
                     source_views: dict | None = None):
    scene = SceneV2.model_validate_json(scene_path.read_text())
    if not isinstance(first_step, int) or not 1 <= first_step <= len(scene.steps):
        raise ValueError("Invalid first render step")
    node = shutil.which("node")
    if not node:
        raise ValueError("Node.js is required for actual candidate browser rendering")
    args = [node, str(ROOT / "tools/render_candidate.mjs"), "--scene", str(scene_path.resolve()),
            "--geometry-root", str(geometry.resolve()), "--output", str(output.resolve()), "--from", str(first_step)]
    output.parent.mkdir(parents=True, exist_ok=True)
    camera_sha = None
    validated_views = {}
    if source_views is not None:
        allowed_steps = {step.step_id for step in scene.steps[first_step-1:]}
        if not isinstance(source_views, dict) or set(source_views)-allowed_steps:
            raise ValueError("Source camera references a step outside the requested render range")
        validated_views = {key: SourceCamera.model_validate(value).model_dump(mode="json")
                           for key, value in source_views.items()}
        camera_bytes = json.dumps(validated_views, sort_keys=True, separators=(",", ":")).encode()
        if len(camera_bytes) > 1_000_000:
            raise ValueError("Source camera evidence exceeds byte bound")
        camera_file = output.with_suffix(".source-views.json")
        with camera_file.open("xb") as stream:
            stream.write(camera_bytes)
        camera_sha = hashlib.sha256(camera_bytes).hexdigest()
        args.extend(["--source-views", str(camera_file.resolve())])
    log = output.with_suffix(".log")
    started = time.monotonic()
    with log.open("w") as stream:
        process = subprocess.Popen(args, cwd=ROOT, env=child_environment(), stdout=stream, stderr=stream,
                                   start_new_session=True)
        try:
            while process.poll() is None:
                check()
                if time.monotonic()-started > timeout or log.stat().st_size > 20_000_000:
                    raise ValueError("Candidate rendering exceeded its time/output bound")
                time.sleep(0.2)
        finally:
            if process.poll() is None:
                import os
                import signal
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    if process.returncode != 0:
        raise ValueError("Actual candidate browser rendering failed; inspect private render log")
    report = json.loads((output / "report.json").read_text())
    if report.get("status") != "rendered" or report.get("scene_sha256") != digest(scene):
        raise ValueError("Render report does not bind the current candidate")
    if report.get("source_views_sha256") != camera_sha:
        raise ValueError("Render report does not bind the requested source cameras")
    if camera_sha is not None:
        camera_copy = output / "source-views.json"
        if camera_copy.is_symlink() or hashlib.sha256(camera_copy.read_bytes()).hexdigest() != camera_sha:
            raise ValueError("Stored source camera evidence hash mismatch")
    if len(report.get("steps", [])) != len(scene.steps) - first_step + 1:
        raise ValueError("Render report does not cover all candidate microsteps")
    for expected, rendered in zip(scene.steps[first_step - 1:], report["steps"], strict=True):
        if rendered["step_id"] != expected.step_id:
            raise ValueError("Rendered step identity mismatch")
        requested_camera = validated_views.get(expected.step_id)
        actual_camera = rendered.get("source_camera")
        if requested_camera is not None:
            if rendered.get("camera_mode") != "source_orthographic":
                raise ValueError("Rendered source camera does not match the requested view")
            validate_rendered_source_camera(requested_camera, actual_camera)
        elif actual_camera is not None:
            raise ValueError("An unrequested source camera was rendered")
        image = output / rendered["screenshot"]
        if image.is_symlink() or not image.resolve().is_relative_to(output.resolve()):
            raise ValueError("Render image escapes evidence directory")
        if hashlib.sha256(image.read_bytes()).hexdigest() != rendered["png_sha256"]:
            raise ValueError("Render image hash mismatch")
    return report
