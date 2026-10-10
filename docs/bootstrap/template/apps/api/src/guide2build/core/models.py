"""Canonical scene contracts. Validation here is structural, not a physics certification."""
from __future__ import annotations
from math import isfinite, sqrt
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Pose(StrictModel):
    position_ldu: tuple[float, float, float]
    quaternion_xyzw: tuple[float, float, float, float]

    @field_validator("quaternion_xyzw")
    @classmethod
    def unit_quaternion(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not all(isfinite(x) for x in value) or abs(sqrt(sum(x*x for x in value)) - 1) > 1e-5:
            raise ValueError("Quaternion must be finite and unit-length")
        return value


class SourcePanel(StrictModel):
    page_index: int = Field(ge=0)
    # Top-left normalized [x0, y0, x1, y1], after page rotation is applied.
    bbox: tuple[float, float, float, float]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("bbox")
    @classmethod
    def rectangle(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        x0, y0, x1, y1 = value
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("Expected a non-empty normalized top-left rectangle")
        return value


class PartInstance(StrictModel):
    instance_id: str = Field(min_length=1)
    part_id: str = Field(min_length=1)
    color_code: str = Field(min_length=1)
    # Relative to the curated local LDraw root, e.g. parts/3020.dat.
    geometry_ref: str = Field(pattern=r"^(parts|p)/[a-zA-Z0-9_./-]+\.dat$")
    source: SourcePanel
    origin: Literal["vision_proposal", "pdf_assisted_authoring", "human_correction"]
    mapping_status: Literal["candidate", "agent_reviewed", "human_reviewed"] = "candidate"

    @field_validator("geometry_ref")
    @classmethod
    def confined_ref(cls, value: str) -> str:
        if any(piece in ("..", "") for piece in value.split("/")) or "\\" in value:
            raise ValueError("Unsafe geometry reference")
        return value


class StepSnapshot(StrictModel):
    step_id: str = Field(min_length=1)
    main_step_number: int = Field(ge=1)
    substep_label: str | None = None
    instruction: str = Field(min_length=1)
    source: SourcePanel
    introduced_instance_ids: list[str]
    active_instance_ids: list[str]
    visible_instance_ids: list[str]
    poses: dict[str, Pose]
    action: Literal["add_parts", "build_subassembly", "attach_subassembly", "inspect"]
    assembly_group_id: str | None = None


class ReviewRecord(StrictModel):
    actor_type: Literal["agent", "human"]
    actor_id: str = Field(min_length=1)
    reviewed_revision: str = Field(min_length=1)
    evidence_paths: list[str] = Field(min_length=1)
    decision: Literal["accepted", "changes_requested"]
    recorded_at: str = Field(min_length=1)


class SceneManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    set_number: str = Field(pattern=r"^[0-9]{4,7}$")
    guide_id: str = Field(pattern=r"^[a-z0-9-]+$")
    revision: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    coordinate_system: Literal["right_handed_y_up_ldu"] = "right_handed_y_up_ldu"
    status: Literal["candidate", "needs_review", "agent_reviewed", "human_reviewed"]
    geometry_check: Literal["not_run", "pass", "fail"] = "not_run"
    connector_check: Literal["not_run", "pass", "fail"] = "not_run"
    physical_build_check: Literal["not_run", "pass", "fail"] = "not_run"
    instances: list[PartInstance] = Field(min_length=1)
    steps: list[StepSnapshot] = Field(min_length=1)
    reviews: list[ReviewRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def traceable_and_consistent(self) -> "SceneManifest":
        ids = [x.instance_id for x in self.instances]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate physical instance ID")
        all_ids = set(ids)
        introduced: set[str] = set()
        step_ids: set[str] = set()
        previous_main = 0
        for instance in self.instances:
            if instance.source.source_sha256 != self.source_sha256:
                raise ValueError("Part provenance hash does not match the scene")
        for step in self.steps:
            if step.step_id in step_ids:
                raise ValueError("Duplicate step ID")
            step_ids.add(step.step_id)
            if step.main_step_number < previous_main:
                raise ValueError("Main-step numbers must not move backwards")
            previous_main = step.main_step_number
            if step.source.source_sha256 != self.source_sha256:
                raise ValueError("Step provenance hash does not match the scene")
            for seq in (step.visible_instance_ids, step.active_instance_ids, step.introduced_instance_ids):
                if len(seq) != len(set(seq)):
                    raise ValueError("Duplicate instance ID in a step list")
                if not set(seq) <= all_ids:
                    raise ValueError("Step refers to an unknown instance")
            new_ids = set(step.introduced_instance_ids)
            if new_ids & introduced:
                raise ValueError("A physical instance may be introduced only once")
            introduced |= new_ids
            visible = set(step.visible_instance_ids)
            if not visible <= introduced:
                raise ValueError("Visible part has not been introduced")
            if not new_ids <= visible or not set(step.active_instance_ids) <= visible:
                raise ValueError("New and active instances must be visible")
            if set(step.poses) != visible:
                raise ValueError("Snapshot needs exactly one pose per visible instance")
        if introduced != all_ids:
            raise ValueError("Some physical instances are never introduced")
        if self.status in ("agent_reviewed", "human_reviewed"):
            actor = "human" if self.status == "human_reviewed" else "agent"
            if not any(r.actor_type == actor and r.reviewed_revision == self.revision and
                       r.decision == "accepted" for r in self.reviews):
                raise ValueError("Reviewed status requires a matching review record")
        return self
