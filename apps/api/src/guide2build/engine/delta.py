"""Append-only model proposals. Historical poses never pass through model output."""
from __future__ import annotations
import json
from pydantic import Field
from ..core.models import StrictModel, PartInstance
from ..releases.models import SceneV2, Section, StepV2
from ..catalog import find_guide

MAX_CONTEXT_BYTES = 400_000


class SceneDelta(StrictModel):
    new_sections: list[Section]
    new_instances: list[PartInstance]
    # poses contains only new/moved piece transforms; unchanged poses are inherited deterministically.
    new_steps: list[StepV2] = Field(min_length=1)


class DeltaConstruction(StrictModel):
    delta_json: str | None
    blockers: list[str]
    observations: list[str]


def current_context(previous):
    if previous is None:
        return None
    poses = {}
    for step in previous["steps"]:
        poses.update(step["poses"])
    result = {"sources": previous["sources"], "sections": previous["sections"],
              "physical_instances": [{key: instance[key] for key in ("instance_id", "part_id", "color_code", "geometry_ref")}
                                     for instance in previous["instances"]],
              "latest_known_poses": poses,
              "last_snapshot": {key: value for key, value in previous["steps"][-1].items() if key != "poses"}}
    if len(json.dumps(result, separators=(",", ":")).encode()) > MAX_CONTEXT_BYTES:
        raise ValueError("Current assembly exceeds 400 KB proposal context; spatial partitioning is required")
    return result


def assemble_delta(value, job, source_hash, page_count, previous):
    delta = SceneDelta.model_validate_json(value)
    if previous:
        # Pydantic gives an independent deep value; never let expansion mutate the checkpoint object.
        data = SceneV2.model_validate(previous).model_dump(mode="json")
    else:
        data = {"schema_version": "2.0", "set_number": job["set_number"], "guide_id": job["guide_id"],
                "revision": "engine-" + job["id"], "source_sha256": source_hash,
                "coordinate_system": "right_handed_y_up_ldu", "status": "candidate", "geometry_check": "not_run",
                "connector_check": "not_run", "physical_build_check": "not_run", "sources": [], "sections": [],
                "instances": [], "steps": []}
    data["guide_id"] = job["guide_id"]
    data["revision"] = "engine-" + job["id"]
    if source_hash not in {source["source_sha256"] for source in data["sources"]}:
        guide = find_guide(job["set_number"], job["guide_id"])
        data["sources"].append({"guide_id": job["guide_id"], "source_sha256": source_hash,
                                "official_url": guide["pdf_url"], "page_count": page_count})
    data["sections"].extend(section.model_dump(mode="json") for section in delta.new_sections)
    data["instances"].extend(part.model_dump(mode="json") for part in delta.new_instances)
    latest = {}
    for step in data["steps"]:
        latest.update(step["poses"])
    for proposed in delta.new_steps:
        step = proposed.model_dump(mode="json")
        if not set(step["poses"]) <= set(step["visible_instance_ids"]):
            raise ValueError("Pose updates must belong to visible instances")
        latest.update(step["poses"])
        if not set(step["visible_instance_ids"]) <= set(latest):
            raise ValueError("New visible instances require explicit poses")
        step["poses"] = {identity: latest[identity] for identity in step["visible_instance_ids"]}
        data["steps"].append(step)
    return SceneV2.model_validate(data)


def page_review_context(candidate, source_hash, page_index):
    parts = {part["instance_id"]: part for part in candidate["instances"]}
    result = []
    for step in candidate["steps"]:
        if step["source"]["source_sha256"] != source_hash or step["source"]["page_index"] != page_index:
            continue
        result.append({"step_id": step["step_id"], "main_step_number": step["main_step_number"],
                       "action": step["action"], "source": step["source"],
                       "introduced_parts": [parts[identity] for identity in step["introduced_instance_ids"]],
                       "active_poses": {identity: step["poses"][identity] for identity in step["active_instance_ids"]}})
    if len(json.dumps(result).encode()) > MAX_CONTEXT_BYTES:
        raise ValueError("Page review exceeds bounded context; split source panels before review")
    return result
