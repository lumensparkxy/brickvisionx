"""Corrections carry exact base revision, source evidence, and declared actor provenance."""
from typing import Annotated, Literal
from pydantic import Field
from ..core.models import Pose, SourcePanel, StrictModel


class ReviewItem(StrictModel):
    item_id: str = Field(min_length=1, max_length=150)
    kind: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=3000)
    instance_ids: list[str]
    step_ids: list[str]
    source: SourcePanel
    status: Literal["open", "resolved"]


class PoseCorrection(StrictModel):
    type: Literal["pose"]
    step_id: str
    instance_id: str
    pose: Pose


class MappingCorrection(StrictModel):
    type: Literal["mapping"]
    instance_id: str
    part_id: str = Field(min_length=1, max_length=100)
    color_code: str = Field(min_length=1, max_length=30)
    geometry_ref: str


class GroupCorrection(StrictModel):
    type: Literal["group"]
    step_id: str
    assembly_group_id: str = Field(min_length=1, max_length=100)


class CorrectionRequest(StrictModel):
    expected_revision: str
    actor_type: Literal["agent", "human"]
    actor_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)
    source: SourcePanel
    command: Annotated[PoseCorrection | MappingCorrection | GroupCorrection, Field(discriminator="type")]


class ReviewRequest(StrictModel):
    expected_revision: str
    actor_type: Literal["agent", "human"]
    actor_id: str = Field(min_length=1, max_length=100)
    decision: Literal["accepted", "changes_requested"]
    evidence_paths: list[str] = Field(min_length=1, max_length=30)
