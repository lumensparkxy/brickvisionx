"""Local starter API. Persistent conversion jobs and review writes are specified, not faked."""
from pathlib import Path
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from .catalog import ROOT, find_set, find_guide
from .core.models import SceneManifest
from .core.bom import bill_of_materials


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = data_dir or Path(os.getenv("GUIDE2BUILD_DATA_DIR", str(ROOT / "var")))
    data_dir = data_dir.resolve()
    app = FastAPI(title="Guide2Build 3D", version="0.1.0")
    # Separate public local artifacts from private receipts, DBs and review logs.
    public_dir = data_dir / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/assets-local", StaticFiles(directory=public_dir), name="local-assets")

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "stage": "scaffold", "runtime_vision_provider": "disabled"}

    def known_guide(set_number: str, guide_id: str) -> dict:
        try:
            return find_guide(set_number, guide_id)
        except (KeyError, ValueError):
            raise HTTPException(404, detail={"code": "unsupported_guide", "message": "Guide not supported"})

    @app.get("/api/v1/sets/{set_number}")
    def set_detail(set_number: str):
        try:
            return find_set(set_number)
        except ValueError as error:
            raise HTTPException(422, detail={"code": "invalid_set_number", "message": str(error)})
        except KeyError:
            raise HTTPException(404, detail={"code": "unsupported_set", "message": "This set is not supported yet"})

    def load_scene(set_number: str, guide_id: str) -> SceneManifest:
        known_guide(set_number, guide_id)
        # Both identifiers have already been resolved against the trusted registry.
        path = data_dir / "reconstructions" / set_number / guide_id / "scene.json"
        if not path.is_file():
            raise HTTPException(409, detail={"code": "reconstruction_not_available", "message":
                "Official guide located; the 3D reconstruction has not been prepared yet."})
        try:
            scene = SceneManifest.model_validate_json(path.read_text())
            if scene.set_number != set_number or scene.guide_id != guide_id:
                raise ValueError("Scene identity mismatch")
        except (ValidationError, ValueError):
            raise HTTPException(409, detail={"code": "invalid_reconstruction", "message":
                "The stored reconstruction failed validation and needs review."})
        return scene

    @app.get("/api/v1/sets/{set_number}/guides/{guide_id}/scene")
    def scene_detail(set_number: str, guide_id: str):
        return load_scene(set_number, guide_id)

    @app.get("/api/v1/sets/{set_number}/guides/{guide_id}/bom")
    def bom_detail(set_number: str, guide_id: str):
        scene = load_scene(set_number, guide_id)
        return {"revision": scene.revision, "items": bill_of_materials(scene)}

    return app


app = create_app()
