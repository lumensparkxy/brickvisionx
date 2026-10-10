import copy
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from jsonschema import Draft202012Validator
from guide2build.core.models import SceneManifest, Pose, SourcePanel
from guide2build.core.bom import bill_of_materials


def test_original_fixture_is_structurally_valid(scene_data):
    scene = SceneManifest.model_validate(scene_data)
    assert len(scene.instances) == 2
    assert scene.geometry_check == "not_run"


def test_bom_does_not_count_step_reappearances(scene_data):
    scene = SceneManifest.model_validate(scene_data)
    assert bill_of_materials(scene) == [{"part_id": "synthetic-part", "color_code": "15", "quantity": 2}]


def test_duplicate_instance_is_rejected(scene_data):
    scene_data["instances"].append(copy.deepcopy(scene_data["instances"][0]))
    with pytest.raises(ValidationError, match="Duplicate physical"):
        SceneManifest.model_validate(scene_data)


def test_reintroduced_part_is_rejected(scene_data):
    scene_data["steps"][2]["introduced_instance_ids"] = ["a"]
    with pytest.raises(ValidationError, match="introduced only once"):
        SceneManifest.model_validate(scene_data)


def test_missing_pose_is_rejected(scene_data):
    del scene_data["steps"][1]["poses"]["b"]
    with pytest.raises(ValidationError, match="exactly one pose"):
        SceneManifest.model_validate(scene_data)


def test_early_visibility_is_rejected(scene_data):
    scene_data["steps"][0]["visible_instance_ids"].append("b")
    with pytest.raises(ValidationError, match="has not been introduced"):
        SceneManifest.model_validate(scene_data)


def test_hash_mismatch_is_rejected(scene_data):
    scene_data["steps"][0]["source"]["source_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="hash does not match"):
        SceneManifest.model_validate(scene_data)


def test_non_unit_quaternion_is_rejected():
    with pytest.raises(ValidationError, match="unit-length"):
        Pose(position_ldu=(0,0,0), quaternion_xyzw=(0,0,0,2))


def test_nonfinite_pose_is_rejected():
    with pytest.raises(ValidationError):
        Pose(position_ldu=(float("inf"),0,0), quaternion_xyzw=(0,0,0,1))


def test_invalid_crop_is_rejected():
    with pytest.raises(ValidationError):
        SourcePanel(page_index=0, bbox=(.8,0,.2,1), source_sha256="0"*64)


def test_geometry_path_escape_is_rejected(scene_data):
    scene_data["instances"][0]["geometry_ref"] = "parts/../../secrets.dat"
    with pytest.raises(ValidationError, match="Unsafe geometry"):
        SceneManifest.model_validate(scene_data)


def test_color_cannot_inject_ldraw_commands(scene_data):
    scene_data["instances"][0]["color_code"] = "15\n1 16 0 0 0"
    with pytest.raises(ValidationError):
        SceneManifest.model_validate(scene_data)


def test_review_cannot_be_invented_by_status_only(scene_data):
    scene_data["status"] = "human_reviewed"
    with pytest.raises(ValidationError, match="matching review"):
        SceneManifest.model_validate(scene_data)


def test_agent_review_does_not_grant_human_review(scene_data):
    scene_data["status"] = "human_reviewed"
    scene_data["reviews"] = [{"actor_type":"agent", "actor_id":"test-agent", "reviewed_revision":"fixture-r1",
       "evidence_paths":["synthetic-test-only"], "decision":"accepted", "recorded_at":"2026-10-01T00:00:00Z"}]
    with pytest.raises(ValidationError, match="matching review"):
        SceneManifest.model_validate(scene_data)


def test_generated_json_schema_accepts_fixture(scene_data):
    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "packages/contracts/scene.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(scene_data)
