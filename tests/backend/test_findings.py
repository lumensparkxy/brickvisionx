import pytest
from guide2build.core.models import SceneManifest
from guide2build.jobs.store import Store
from guide2build.review.models import CorrectionRequest
from guide2build.review.service import ReviewService


def test_source_findings_survive_import_and_correction(tmp_path, scene_data):
    scene = SceneManifest.model_validate(scene_data)
    service = ReviewService(Store(tmp_path))
    service.import_scene(scene)
    finding = {"item_id": "hidden-connection", "kind": "occluded_connection", "message": "Unresolved contact",
               "instance_ids": ["a"], "step_ids": ["s1"], "source": scene_data["steps"][0]["source"], "status": "open"}
    service.import_scene(scene, [finding])
    service.import_scene(scene)
    assert finding in service.items(scene.revision)
    request = CorrectionRequest.model_validate({"expected_revision": scene.revision, "actor_type": "agent",
        "actor_id": "test-agent", "reason": "Synthetic test correction", "source": finding["source"],
        "command": {"type": "pose", "step_id": "s1", "instance_id": "a",
                    "pose": {"position_ldu": [20, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]}}})
    revised = service.apply(scene.revision, request, "test-correction")
    assert finding in service.items(revised.revision)
    assert revised.connector_check == "not_run"


def test_foreign_source_finding_rejected(tmp_path, scene_data):
    scene = SceneManifest.model_validate(scene_data)
    finding = {"item_id": "bad", "kind": "pose", "message": "Wrong source", "instance_ids": [], "step_ids": [],
               "source": {**scene_data["steps"][0]["source"], "source_sha256": "0"*64}, "status": "open"}
    with pytest.raises(ValueError, match="does not match"):
        ReviewService(Store(tmp_path)).import_scene(scene, [finding])
