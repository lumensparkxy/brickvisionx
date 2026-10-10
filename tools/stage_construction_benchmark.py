"""Stage real source-backed reconstruction attempts in an isolated local benchmark API.

This checks contracts/provenance only. It never promotes partial attempts to accepted tutorials.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from _paths import ROOT
from guide2build.catalog import find_guide
from guide2build.core.models import SceneManifest
from guide2build.jobs.source_cache import cached_receipt


def copy_verified(source: Path, target: Path, expected: str | None = None) -> None:
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if expected and digest != expected:
        raise ValueError(f'Checksum mismatch: {source}')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() == digest:
                return
    temporary = target.with_name(target.name + '.staging')
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def stage_cases(cases_path: Path, destination: Path) -> dict:
    cases = json.loads(cases_path.read_text())
    destination = destination.resolve()
    if not destination.is_relative_to((ROOT / 'var/evidence/ten-set-construction').resolve()):
        raise ValueError('Benchmark data must stay in its isolated evidence directory')
    assets = destination / 'public/ldraw'
    combined = {'library': 'https://library.ldraw.org/library/official/', 'scope': 'individual parts only',
                'resources': {}, 'file_map': {}, 'materials': {}, 'roots': []}
    records = []
    for case in cases:
        scene_path = ROOT / case['scene_path']
        scene = SceneManifest.model_validate_json(scene_path.read_text())
        if scene.set_number != case['set_number'] or scene.guide_id != case['guide_id']:
            raise ValueError('Case identity does not match candidate')
        if scene.status not in {'candidate', 'needs_review'}:
            raise ValueError('This harness accepts explicitly unaccepted candidates only')
        guide = find_guide(scene.set_number, scene.guide_id)
        receipt = cached_receipt(ROOT / 'var', scene.set_number, scene.guide_id, guide['pdf_url'])
        if not receipt or receipt['sha256'] != scene.source_sha256:
            raise ValueError('Candidate lacks matching verified official source')
        original = ROOT / 'var/sources' / scene.set_number / scene.guide_id
        target = destination / 'sources' / scene.set_number / scene.guide_id
        copy_verified(original / 'source.pdf', target / 'source.pdf', scene.source_sha256)
        copy_verified(original / 'source.receipt.json', target / 'source.receipt.json')
        pages_root = ROOT / 'var/public/pages' / scene.source_sha256
        pages = json.loads((pages_root / 'pages.json').read_text())
        page_indices = {p['page_index'] for p in pages}
        if any(p.page_index not in page_indices for p in [*[s.source for s in scene.steps], *[i.source for i in scene.instances]]):
            raise ValueError('Candidate references an unavailable source page')
        for page in pages:
            copy_verified(pages_root / page['file'], destination / 'public/pages' / scene.source_sha256 / page['file'], page['sha256'])
        copy_verified(pages_root / 'pages.json', destination / 'public/pages' / scene.source_sha256 / 'pages.json')
        source_assets = ROOT / case['assets_path']
        provenance = json.loads((source_assets / 'provenance.json').read_text())
        visited = set()
        def collect(path: str):
            if path in visited:
                return
            if '..' in Path(path).parts or Path(path).is_absolute():
                raise ValueError('Unsafe asset reference')
            visited.add(path)
            record = provenance['resources'][path]
            if record['url'] != combined['library'] + path:
                raise ValueError('Unexpected asset origin')
            if path in combined['resources'] and combined['resources'][path]['sha256'] != record['sha256']:
                raise ValueError('Conflicting individual geometry revisions')
            copy_verified(source_assets / path, assets / path, record['sha256'])
            combined['resources'][path] = record
            for child in record['dependencies']:
                collect(child)
        for part in scene.instances:
            collect(part.geometry_ref)
        for key, path in provenance.get('file_map', {}).items():
            if path in visited:
                if key in combined['file_map'] and combined['file_map'][key] != path:
                    raise ValueError('Conflicting part dependency map')
                combined['file_map'][key] = path
        material = provenance['materials']['LDConfig.ldr']
        if combined['materials'] and combined['materials']['LDConfig.ldr']['sha256'] != material['sha256']:
            raise ValueError('Conflicting material versions')
        copy_verified(source_assets / 'LDConfig.ldr', assets / 'LDConfig.ldr', material['sha256'])
        combined['materials']['LDConfig.ldr'] = material
        combined['roots'] = sorted(set(combined['roots']) | {i.part_id for i in scene.instances})
        scene_target = destination / 'reconstructions' / scene.set_number / scene.guide_id / 'scene.json'
        copy_verified(scene_path, scene_target)
        # Findings remain with each original attempt; this harness never invents review records.
        records.append({**case, 'revision': scene.revision, 'source_sha256': scene.source_sha256,
                        'steps': len(scene.steps), 'instances': len(scene.instances),
                        'unique_main_steps': len({s.main_step_number for s in scene.steps}),
                        'asset_dependency_files': len(visited), 'structural_validation': 'pass',
                        'geometry_correctness': 'not_established', 'human_review': 'not_run'})
    assets.mkdir(parents=True, exist_ok=True)
    (assets / 'provenance.json').write_text(json.dumps(combined, indent=2) + '\n')
    result = {'purpose': 'Real candidate browser benchmark; partials are not complete tutorials.', 'cases': records}
    (destination.parent / 'staged-cases.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cases', type=Path)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'var/evidence/ten-set-construction/runtime')
    args = parser.parse_args()
    print(json.dumps(stage_cases(args.cases, args.data_dir), indent=2))
