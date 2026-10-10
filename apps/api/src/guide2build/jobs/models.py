"""Validated transport objects for durable local jobs."""
from typing import Literal
from pydantic import Field
from ..core.models import StrictModel


class ConversionRequest(StrictModel):
    set_number: str = Field(pattern=r"^[0-9]{4,7}$")
    guide_id: str = Field(pattern=r"^[a-z0-9-]+$")
    mode: Literal["automated", "assisted"]


class JobError(StrictModel):
    code: str
    message: str
    retryable: bool = False


class ConversionJob(StrictModel):
    job_id: str
    set_number: str
    guide_id: str
    mode: Literal["automated", "assisted"]
    state: str
    stage: str
    completed_units: int = 0
    total_units: int | None = None
    attempts: int = 0
    source_sha256: str | None = None
    output_revision: str | None = None
    artifact_key: str | None = None
    error: JobError | None = None
    created_at: str
    updated_at: str
