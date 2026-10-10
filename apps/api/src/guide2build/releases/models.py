"""Source-aware scenes and immutable publication contracts (not physical certification)."""
from __future__ import annotations
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from guide2build.core.models import StrictModel, SceneManifest, StepSnapshot, PartInstance
import hashlib
import json


def canonical(value) -> bytes:
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class Source(StrictModel):
    guide_id: str = Field(pattern=r'^[a-z0-9-]+$')
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    official_url: str
    page_count: int = Field(gt=0)

    @model_validator(mode='after')
    def official(self):
        u = urlsplit(self.official_url)
        if u.scheme != 'https' or u.hostname != 'www.lego.com' or u.username or u.password or u.port or u.fragment:
            raise ValueError('Only official LEGO HTTPS source links are accepted')
        return self


class Section(StrictModel):
    section_id: str = Field(pattern=r'^[a-z0-9-]+$')
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    label: str = Field(min_length=1, max_length=200)


class StepV2(StepSnapshot):
    section_id: str = Field(pattern=r'^[a-z0-9-]+$')
    main_step_number: int | None = Field(default=None, ge=1)


class SceneV2(StrictModel):
    schema_version: Literal['2.0'] = '2.0'
    set_number: str = Field(pattern=r'^[0-9]{4,7}$')
    guide_id: str = Field(pattern=r'^[a-z0-9-]+$')
    revision: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    coordinate_system: Literal['right_handed_y_up_ldu'] = 'right_handed_y_up_ldu'
    # Publication approval is separate; v2 does not yet transport human assembly-review evidence.
    status: Literal['candidate', 'needs_review', 'agent_reviewed']
    geometry_check: Literal['not_run', 'pass', 'fail'] = 'not_run'
    connector_check: Literal['not_run', 'pass', 'fail'] = 'not_run'
    physical_build_check: Literal['not_run', 'pass', 'fail'] = 'not_run'
    sources: list[Source] = Field(min_length=1)
    sections: list[Section] = Field(min_length=1)
    instances: list[PartInstance] = Field(min_length=1)
    steps: list[StepV2] = Field(min_length=1)

    @model_validator(mode='after')
    def consistent(self):
        sources = {s.source_sha256: s for s in self.sources}
        sections = {s.section_id: s for s in self.sections}
        if len(sources) != len(self.sources) or len(sections) != len(self.sections):
            raise ValueError('Duplicate source or section identity')
        if self.source_sha256 != self.sources[0].source_sha256:
            raise ValueError('Primary source must be first source')
        if any(s.source_sha256 not in sources for s in self.sections):
            raise ValueError('Section source missing')
        section_order = {s.section_id: i for i, s in enumerate(self.sections)}
        previous_order, previous_number = -1, 0
        for item in [*self.instances, *self.steps]:
            source = sources.get(item.source.source_sha256)
            if not source or item.source.page_index >= source.page_count:
                raise ValueError('Unknown source or out-of-range page')
        for step in self.steps:
            section = sections.get(step.section_id)
            if not section or section.source_sha256 != step.source.source_sha256:
                raise ValueError('Step source differs from section')
            order = section_order[step.section_id]
            if order < previous_order:
                raise ValueError('Sections cannot move backwards')
            if order != previous_order:
                previous_number = 0
            if step.main_step_number is not None:
                if step.main_step_number < previous_number:
                    raise ValueError('Printed numbers cannot move backwards within a section')
                previous_number = step.main_step_number
            previous_order = order
        # Reuse the proven identity/pose invariants, normalizing ONLY for structural checking.
        data = self.model_dump(mode='json', exclude={'sources', 'sections'})
        data.update(schema_version='1.0', status='candidate', reviews=[])
        for part in data['instances']:
            part['source']['source_sha256'] = self.source_sha256
        for index, step in enumerate(data['steps']):
            step.pop('section_id')
            step['main_step_number'] = index + 1
            step['source']['source_sha256'] = self.source_sha256
        SceneManifest.model_validate(data)
        return self


def adapt_v1(scene: SceneManifest, official_url: str, page_count: int) -> SceneV2:
    data = scene.model_dump(mode='json', exclude={'reviews'})
    data.update(schema_version='2.0', sources=[dict(guide_id=scene.guide_id,
        source_sha256=scene.source_sha256, official_url=official_url, page_count=page_count)],
        sections=[dict(section_id='main', source_sha256=scene.source_sha256, label='Main build')])
    for step in data['steps']:
        step['section_id'] = 'main'
    return SceneV2.model_validate(data)


def coverage_keys(scene: SceneV2) -> list[str]:
    return list(dict.fromkeys(f'{s.section_id}:{s.main_step_number}' if s.main_step_number is not None
                             else f'{s.section_id}:unnumbered:{s.step_id}' for s in scene.steps))


class ReleaseValidation(StrictModel):
    scene_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    coverage_index_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_step_keys: list[str] = Field(min_length=1)
    covered_step_keys: list[str]
    source_evidence_verified: bool
    geometry_provenance_verified: bool
    assembly_review: Literal['pass', 'fail', 'not_run']
    blockers: list[str]
    artifact_kind: Literal['automatic_reconstruction', 'pdf_assisted_authoring', 'fixture']

    def check(self, scene: SceneV2):
        if self.scene_sha256 != digest(scene):
            raise ValueError('Stale validation: scene hash differs')
        if (self.artifact_kind == 'fixture' or self.blockers or self.assembly_review != 'pass'
                or not self.source_evidence_verified or not self.geometry_provenance_verified):
            raise ValueError('Release validation has unresolved gates')
        if (set(self.covered_step_keys) != set(self.expected_step_keys)
                or set(coverage_keys(scene)) != set(self.expected_step_keys)):
            raise ValueError('Incomplete or mismatched source coverage')
        if scene.geometry_check != 'pass' or scene.connector_check != 'pass':
            raise ValueError('Geometry and connector checks must pass before publication')
