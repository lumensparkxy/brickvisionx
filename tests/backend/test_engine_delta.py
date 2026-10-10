import copy
import json
import pytest
from guide2build.core.models import SceneManifest
from guide2build.releases.models import adapt_v1
from guide2build.engine.delta import assemble_delta, current_context


@pytest.fixture
def previous(scene_data):
    return adapt_v1(SceneManifest.model_validate(scene_data),
                    "https://www.lego.com/en-us/service/building-instructions/30669", 10).model_dump(mode="json")


def test_delta_appends_without_rewriting_history_and_inherits_unchanged_poses(previous):
    before = copy.deepcopy(previous)
    step = copy.deepcopy(previous["steps"][-1])
    step.update(step_id="next-step", main_step_number=step["main_step_number"]+1,
                introduced_instance_ids=[], active_instance_ids=[], poses={})
    delta = {"new_sections": [], "new_instances": [], "new_steps": [step]}
    result = assemble_delta(json.dumps(delta), {"id": "test", "set_number": previous["set_number"],
                            "guide_id": previous["guide_id"]}, previous["source_sha256"], 10, previous)
    actual = result.model_dump(mode="json")
    assert previous == before
    assert actual["steps"][:-1] == before["steps"]
    assert actual["steps"][-1]["poses"] == before["steps"][-1]["poses"]
    delta["historical_steps"] = []
    with pytest.raises(ValueError):
        assemble_delta(json.dumps(delta), {"id": "test"}, previous["source_sha256"], 10, previous)


def test_context_size_does_not_repeat_historical_snapshots(previous):
    initial = current_context(previous)
    repeated = copy.deepcopy(previous)
    repeated["steps"] *= 100
    assert current_context(repeated) == initial
    assert "steps" not in initial


def test_delta_rejects_unknown_visible_instance_without_explicit_pose(previous):
    step = copy.deepcopy(previous["steps"][-1])
    step.update(step_id="next", introduced_instance_ids=[], poses={}, visible_instance_ids=["unknown"])
    with pytest.raises(ValueError, match="explicit poses"):
        assemble_delta(json.dumps({"new_sections": [], "new_instances": [], "new_steps": [step]}),
            {"id": "test", "guide_id": previous["guide_id"]}, previous["source_sha256"], 10, previous)
