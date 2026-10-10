"""Unverified alpha publication is a distinct artifact, never a reviewed tutorial."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from guide2build.core.models import StrictModel
from guide2build.releases.models import SceneV2, coverage_keys, digest

PRIVATE_TEXT = re.compile(
    r"(?:file://|/Users/|/home/|/private/|/tmp/|[A-Za-z]:\\|"
    r"(?:^|[\s\"'])var/(?:engine|sources|providers|evidence)/|"
    r"\b(?:api[_ -]?key|access[_ -]?token|secret|authorization|password)\s*[:=])",
    re.IGNORECASE,
)


def check_public_text(value: str) -> str:
    if PRIVATE_TEXT.search(value) or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('Private or unsafe text is not a public alpha disclosure')
    return value


class AlphaDisclosure(StrictModel):
    artifact_kind: Literal['pdf_assisted_alpha_completion', 'exploration_candidate']
    generation_mode: Literal['alpha_fast', 'explore']
    source_coverage: str = Field(min_length=1, max_length=120)
    coverage_text: str = Field(min_length=1, max_length=1000)
    uncertainty_notes: list[str] = Field(min_length=1, max_length=100)
    accuracy: Literal['unverified']
    human_review: Literal['not_run']
    physical_build: Literal['not_run']

    @field_validator('source_coverage', 'coverage_text')
    @classmethod
    def public_text(cls, value):
        return check_public_text(value)

    @field_validator('uncertainty_notes')
    @classmethod
    def public_notes(cls, notes):
        if (sum(len(s.encode('utf-8')) for s in notes) > 40_000
                or any(not s.strip() or len(s) > 2000 for s in notes)):
            raise ValueError('Alpha uncertainty disclosure exceeds its text bounds')
        for note in notes:
            check_public_text(note)
        return notes

    @model_validator(mode='after')
    def unverified_labels(self):
        if self.generation_mode != {
            'pdf_assisted_alpha_completion': 'alpha_fast',
            'exploration_candidate': 'explore',
        }[self.artifact_kind]:
            raise ValueError('Alpha artifact kind differs from its generation mode')
        if ('unverified' not in self.source_coverage
                or 'independently_verified' in self.source_coverage
                or not self.coverage_text.startswith('Reported coverage (unverified): ')):
            raise ValueError('Alpha source coverage must be reported and unverified')
        return self


class AlphaCoverage(StrictModel):
    verification: Literal['reported_unverified']
    sources: list[str] = Field(min_length=1, max_length=32)
    reported_step_keys: list[str] = Field(min_length=1, max_length=50_000)

    @field_validator('sources', 'reported_step_keys')
    @classmethod
    def bounded_identities(cls, values, info):
        if len(set(values)) != len(values):
            raise ValueError('Duplicate reported source coverage identity')
        pattern = r'[a-f0-9]{64}' if info.field_name == 'sources' else r'[a-z0-9-]+:(?:[0-9]+|unnumbered:[A-Za-z0-9_-]+)'
        if any(not re.fullmatch(pattern, item) or len(item) > 240 for item in values):
            raise ValueError('Invalid reported source coverage identity')
        return values


class AlphaPreviewBinding(StrictModel):
    scene_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    renderer: Literal['threejs']
    rendered_step_id: str = Field(min_length=1, max_length=200)


class AlphaReleaseValidation(StrictModel):
    release_kind: Literal['unverified_alpha']
    artifact_kind: Literal['pdf_assisted_alpha_completion', 'exploration_candidate']
    scene_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    coverage_index_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    preview_binding: AlphaPreviewBinding
    geometry_provenance_verified: Literal[True]
    accuracy: Literal['unverified']
    assembly_review: Literal['not_run']
    physical_build: Literal['not_run']

    def check(self, scene: SceneV2, coverage: AlphaCoverage, preview_sha256: str):
        check_alpha_scene(scene)
        if self.scene_sha256 != digest(scene):
            raise ValueError('Stale alpha validation: scene hash differs')
        if (self.coverage_index_sha256 != digest(coverage)
                or set(coverage.sources) != {s.source_sha256 for s in scene.sources}
                or coverage.reported_step_keys != coverage_keys(scene)):
            raise ValueError('Reported alpha coverage differs from its bound scene')
        if (self.preview_binding.scene_sha256 != self.scene_sha256
                or self.preview_binding.preview_sha256 != preview_sha256
                or self.preview_binding.rendered_step_id != scene.steps[-1].step_id):
            raise ValueError('Alpha render preview binding differs from the final scene')


def check_alpha_scene(scene: SceneV2):
    if sum(s.guide_id == scene.guide_id for s in scene.sources) != 1:
        raise ValueError('Alpha guide identity must select exactly one of its pinned sources')
    if (scene.status != 'needs_review' or scene.geometry_check != 'not_run'
            or scene.connector_check != 'not_run' or scene.physical_build_check != 'not_run'):
        raise ValueError('Alpha publication preserves needs_review and not_run assembly checks')
    if any(p.mapping_status == 'human_reviewed' or p.origin == 'human_correction' for p in scene.instances):
        raise ValueError('An unverified alpha cannot claim an unrecorded human part review')

    def visit(value):
        if isinstance(value, str):
            check_public_text(value)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)

    visit(scene.model_dump(mode='json'))


def package_alpha_release(scene: SceneV2, alpha: AlphaDisclosure | dict, geometry_root: Path,
                          output: Path, preview: Path, *, source_index: dict,
                          preview_binding: AlphaPreviewBinding | dict,
                          trusted_source_registry: dict | None = None) -> dict:
    from guide2build.releases.packaging import package_alpha_release as package
    return package(scene, alpha, geometry_root, output, preview, source_index=source_index,
                   preview_binding=preview_binding, trusted_source_registry=trusted_source_registry)
