"""Publication source gate. Pins are maintained from downloaded official PDFs, not proposals."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Literal
from pydantic import Field
from guide2build.core.models import StrictModel
from guide2build.releases.models import SceneV2, ReleaseValidation, digest

ROOT = Path(__file__).resolve().parents[5]


class SourceCoverage(StrictModel):
    verification: Literal['independently_verified']
    sources: list[str] = Field(min_length=1)
    expected_step_keys: list[str] = Field(min_length=1)


def source_registry() -> dict:
    return json.loads((ROOT / 'config/release-sources.json').read_text())


def verify_source_evidence(scene: SceneV2, validation: ReleaseValidation, registry: dict, index: dict):
    coverage = SourceCoverage.model_validate(index)
    if digest(coverage) != validation.coverage_index_sha256:
        raise ValueError('Coverage index hash differs from independently held index')
    if set(coverage.expected_step_keys) != set(validation.expected_step_keys):
        raise ValueError('Coverage denominator differs from independent source index')
    if set(coverage.sources) != {s.source_sha256 for s in scene.sources}:
        raise ValueError('Coverage index source hashes differ')
    verify_source_pins(scene, registry)
    return coverage


def verify_source_pins(scene: SceneV2, registry: dict):
    """Official source identities remain mandatory for every publication category."""
    if registry.get('schema_version') != 1 or not isinstance(registry.get('sources'), list):
        raise ValueError('Trusted source pin registry is missing or invalid')
    for source in scene.sources:
        pin = next((x for x in registry['sources'] if x['set_number'] == scene.set_number
                    and x['guide_id'] == source.guide_id
                    and x.get('source_sha256') == source.source_sha256), None)
        if not pin or any(pin.get(k) != getattr(source, k) for k in ('source_sha256', 'official_url', 'page_count')):
            raise ValueError('Scene is not bound to a pinned official source')
    if any('synthetic' in p.part_id.lower() or 'synthetic' in p.geometry_ref.lower() for p in scene.instances):
        raise ValueError('Synthetic fixture geometry is not a release input')
