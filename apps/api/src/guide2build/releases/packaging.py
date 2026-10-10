"""Allowlist-only, content-addressed export. Never copy a job directory wholesale."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import zlib
from io import BytesIO
from guide2build.releases.models import SceneV2, ReleaseValidation, canonical, digest
from guide2build.releases.alpha import (
    AlphaCoverage, AlphaDisclosure, AlphaPreviewBinding, AlphaReleaseValidation, check_alpha_scene,
)

SAFE = re.compile(r'^(parts/(?:s/)?|p/(?:8/|48/)?)[a-z0-9_-]+\.dat$')
SAFE_ALIAS = re.compile(r'^(?:(?:s|8|48)/)?[a-z0-9_-]+\.dat$')
GEOMETRY_LICENSES = {
    '0 !LICENSE Licensed under CC BY 4.0 : see CAreadme.txt',
    '0 !LICENSE Licensed under CC BY 2.0 and CC BY 4.0 : see CAreadme.txt',
}
TRANSPORT_FIELDS = {'reviews', 'step_index', 'chunks', 'files', 'release_sha256', 'preview',
                    'release_kind', 'alpha'}


def compact_step_index(step, chunk_index: int) -> dict:
    """Navigation metadata is linear in steps + unique introductions, never cumulative state."""
    return dict(step.model_dump(mode='json', exclude={'poses', 'visible_instance_ids', 'active_instance_ids'}),
                visible_instance_count=len(step.visible_instance_ids),
                active_instance_count=len(step.active_instance_ids), chunk_index=chunk_index)


def read_step_chunk(data: bytes) -> list[dict]:
    chunk = json.loads(data)
    if (not isinstance(chunk, dict) or set(chunk) != {'steps'} or not isinstance(chunk['steps'], list)
            or not 1 <= len(chunk['steps']) <= 8 or any(not isinstance(s, dict) for s in chunk['steps'])):
        raise ValueError('Unexpected or oversized public step chunk')
    return chunk['steps']


def geometry_closure(root: Path, refs: list[str]) -> dict[str, bytes]:
    root = root.resolve()
    provenance = root / 'provenance.json'
    if provenance.is_symlink() or not provenance.is_file() or provenance.stat().st_size > 32_000_000:
        raise ValueError('Unsafe or oversized geometry provenance')
    manifest = json.loads(provenance.read_text())
    aliases = manifest.get('file_map', {})
    if (not isinstance(aliases, dict) or len(aliases) > 40_000
            or any(not isinstance(name, str) or len(name) > 200 or not SAFE_ALIAS.fullmatch(name)
                   or not isinstance(path, str) or not SAFE.fullmatch(path) for name, path in aliases.items())):
        raise ValueError('Unsafe geometry alias or reference name')
    records, selected, visiting = manifest['resources'], {}, set()
    total = 0

    def read(path, record):
        nonlocal total
        target = root / path
        if target.is_symlink() or not target.resolve().is_relative_to(root) or target.stat().st_size > 1_000_000:
            raise ValueError('Unsafe or oversized geometry asset')
        data = target.read_bytes()
        total += len(data)
        if total > 256_000_000 or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Geometry hash or total byte bound failed')
        if 'bytes' in record and record['bytes'] != len(data):
            raise ValueError('Geometry byte receipt mismatch')
        if record.get('url') != 'https://library.ldraw.org/library/official/' + path:
            raise ValueError('Unexpected geometry provenance origin')
        return data

    def walk(path, depth=0):
        if not SAFE.fullmatch(path) or path in visiting or depth > 32:
            raise ValueError('Unsafe or cyclic dependency')
        if path in selected:
            return
        if len(selected) + len(visiting) >= 20000:
            raise ValueError('Geometry closure resource bound')
        record = records[path]
        data = read(path, record)
        classes = re.findall(r'^0 !LDRAW_ORG (\S+)', data.decode('utf-8-sig'), re.MULTILINE)
        if not classes or classes[0] not in {'Part', 'Subpart', 'Primitive', '48_Primitive', '8_Primitive', 'Shortcut'}:
            raise ValueError('Asset is not permitted individual geometry')
        if classes[0] == 'Shortcut':
            raise ValueError('Assembly shortcuts are not permitted release inputs')
        if record.get('classification') != classes[0]:
            raise ValueError('Geometry classification receipt mismatch')
        licenses = [line for line in data.decode('utf-8-sig').splitlines() if re.match(r'^0\s+!LICENSE(?:\s|$)', line)]
        if not licenses:
            raise ValueError('Missing retained geometry license')
        if any(line not in GEOMETRY_LICENSES for line in licenses):
            raise ValueError('Unapproved geometry license declaration')
        if any(note not in data.decode('utf-8-sig').splitlines() for note in record.get('notices', [])):
            raise ValueError('Geometry notice receipt differs from original bytes')
        visiting.add(path)
        dependencies = []
        for line in data.decode('utf-8-sig').splitlines():
            fields = line.split(maxsplit=14)
            if fields and fields[0] == '1':
                if len(fields) != 15:
                    raise ValueError('Invalid individual geometry reference')
                name = fields[14].lower().replace('\\', '/')
                if not SAFE_ALIAS.fullmatch(name):
                    raise ValueError('Unsafe geometry dependency reference name')
                dependency = aliases.get(name)
                if dependency is None:
                    raise ValueError('Unknown geometry dependency')
                dependencies.append(dependency)
        if set(dependencies) != set(record.get('dependencies', [])):
            raise ValueError('Geometry receipt dependency mismatch')
        for dependency in dependencies:
            walk(dependency, depth + 1)
        visiting.remove(path)
        selected[path] = data

    for ref in refs:
        walk(ref)
    material_record = manifest['materials']['LDConfig.ldr']
    selected['LDConfig.ldr'] = read('LDConfig.ldr', material_record)
    material_lines = selected['LDConfig.ldr'].decode('utf-8-sig').splitlines()
    if any(note not in material_lines for note in material_record.get('notices', [])):
        raise ValueError('Material notice receipt differs from original bytes')
    has_material_license = any('!LICENSE' in line for line in material_lines)
    if ('license_notice_in_file' in material_record
            and material_record['license_notice_in_file'] is not has_material_license):
        raise ValueError('Material in-file license receipt differs from original bytes')
    if (material_record.get('legal_reference') is not None
            and material_record['legal_reference'] != 'https://www.ldraw.org/legal-info'):
        raise ValueError('Unexpected material rights origin')
    material = {k: material_record[k] for k in ('url', 'sha256', 'bytes', 'notices',
                'license_notice_in_file', 'legal_reference', 'fetched_at') if k in material_record}
    if 'fetched_at' in material:
        from datetime import datetime
        datetime.fromisoformat(material['fetched_at'])
    # Keep original notices but strip any unrelated local receipt metadata.
    public_records = {p: {k: records[p][k] for k in ('url', 'sha256', 'notices', 'dependencies', 'classification')
                          if k in records[p]} for p in selected if p != 'LDConfig.ldr'}
    selected['provenance.json'] = canonical({'resources': public_records, 'materials': {'LDConfig.ldr': material},
        'file_map': {k: v for k, v in aliases.items() if v in selected}})
    notices = sorted({line for r in [*public_records.values(), material] for line in r.get('notices', [])})
    selected['NOTICES.txt'] = (
        'Individual LDraw DAT bytes are unchanged; original authors and notices are retained in each file.\n'
        'Assembly poses are separate authored candidates, not LDraw assembly models.\n'
        'Per-file license notices and origin URLs appear in provenance.json and the original DAT headers.\n'
        'Some files use CC BY 4.0; some permit CC BY 2.0 or CC BY 4.0. Each original header is authoritative.\n'
        'https://creativecommons.org/licenses/by/4.0/\n'
        'https://creativecommons.org/licenses/by/2.0/\n'
        'https://www.ldraw.org/legal-info\n'
        'LDConfig.ldr rights are recorded separately; a missing in-file license is not an invented license.\n'
        + '\n'.join(notices)).encode()
    return selected


def validate_png_framing(data: bytes):
    """Only image chunks and fixed-size public colour/scale metadata may reach IEND."""
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Preview must be a bounded PNG model render')
    offset, seen, saw_pixels, pixels_ended = 8, set(), False, False
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError('Truncated PNG chunk framing')
        size = int.from_bytes(data[offset:offset + 4], 'big')
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data):
            raise ValueError('Truncated PNG chunk framing')
        if kind not in {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'sRGB', b'gAMA', b'cHRM', b'pHYs'}:
            raise ValueError('Preview contains non-public metadata')
        content = data[offset + 8:offset + 8 + size]
        crc = int.from_bytes(data[offset + 8 + size:end], 'big')
        if zlib.crc32(kind + content) != crc:
            raise ValueError('Invalid PNG chunk checksum')
        if offset == 8 and kind != b'IHDR' or kind != b'IDAT' and kind in seen:
            raise ValueError('Invalid PNG chunk ordering')
        if kind == b'IHDR':
            if size != 13:
                raise ValueError('Invalid PNG image header')
            width, height = int.from_bytes(content[:4], 'big'), int.from_bytes(content[4:8], 'big')
            if not (32 <= width <= 4096 and 32 <= height <= 4096):
                raise ValueError('Preview must be a bounded PNG model render')
        elif kind == b'IDAT':
            if pixels_ended:
                raise ValueError('Invalid PNG pixel chunk ordering')
            saw_pixels = True
        elif kind == b'IEND':
            if size != 0 or not saw_pixels or end != len(data):
                raise ValueError('PNG must end at IEND without trailing bytes')
            return
        else:
            if saw_pixels:
                pixels_ended = True
                raise ValueError('Invalid PNG metadata ordering')
            sizes = {b'sRGB': 1, b'gAMA': 4, b'cHRM': 32, b'pHYs': 9}
            if kind == b'PLTE':
                if not 3 <= size <= 768 or size % 3:
                    raise ValueError('Invalid PNG palette framing')
            elif size != sizes[kind]:
                raise ValueError('Invalid PNG metadata framing')
        seen.add(kind)
        offset = end
    raise ValueError('PNG has no terminal IEND')


def validate_preview_bytes(data: bytes):
    """Decode a bounded PNG while rejecting metadata outside the public image allowlist."""
    from PIL import Image
    if not isinstance(data, bytes) or not data or len(data) > 20_000_000:
        raise ValueError('Unsafe or oversized preview')
    validate_png_framing(data)
    with Image.open(BytesIO(data)) as image:
        if image.format != 'PNG' or not (32 <= image.width <= 4096 and 32 <= image.height <= 4096):
            raise ValueError('Preview must be a bounded PNG model render')
        if any(k not in {'srgb', 'gamma', 'chromaticity', 'dpi'} for k in image.info):
            raise ValueError('Preview contains non-public metadata')
        image.verify()
    with Image.open(BytesIO(data)) as image:
        image.load()


def read_preview(preview: Path | None) -> bytes:
    if preview is None:
        raise ValueError('A real model-render PNG preview is required before release packaging')
    preview = Path(preview)
    if preview.is_symlink() or not preview.is_file() or preview.stat().st_size > 20_000_000:
        raise ValueError('Unsafe or oversized preview')
    data = preview.read_bytes()
    validate_preview_bytes(data)
    return data


def package_release(scene: SceneV2, validation: ReleaseValidation, geometry_root: Path, output: Path, preview: Path | None = None, trusted_source_registry: dict | None = None, source_index: dict | None = None) -> dict:
    validation.check(scene)
    from guide2build.releases.evidence import verify_source_evidence, source_registry
    if source_index is None:
        raise ValueError('An independently verified source coverage index is required')
    coverage = verify_source_evidence(scene, validation, trusted_source_registry or source_registry(), source_index)
    return emit_release(scene, validation, coverage, geometry_root, output, read_preview(preview))


def package_alpha_release(scene: SceneV2, alpha: AlphaDisclosure | dict, geometry_root: Path,
                          output: Path, preview: Path, *, source_index: dict,
                          preview_binding: AlphaPreviewBinding | dict,
                          trusted_source_registry: dict | None = None) -> dict:
    """Package only the frozen PDF-assisted candidate; no check or review is promoted."""
    from guide2build.releases.evidence import verify_source_pins, source_registry
    scene = SceneV2.model_validate(scene.model_dump(mode='json'))
    check_alpha_scene(scene)
    alpha = AlphaDisclosure.model_validate(alpha.model_dump(mode='json') if isinstance(alpha, AlphaDisclosure) else alpha)
    coverage = AlphaCoverage.model_validate(source_index)
    binding = AlphaPreviewBinding.model_validate(preview_binding.model_dump(mode='json')
                                                if isinstance(preview_binding, AlphaPreviewBinding) else preview_binding)
    verify_source_pins(scene, trusted_source_registry or source_registry())
    image = read_preview(preview)
    report = AlphaReleaseValidation(release_kind='unverified_alpha', artifact_kind=alpha.artifact_kind,
        scene_sha256=digest(scene), coverage_index_sha256=digest(coverage), preview_binding=binding,
        geometry_provenance_verified=True, accuracy='unverified', assembly_review='not_run', physical_build='not_run')
    report.check(scene, coverage, hashlib.sha256(image).hexdigest())
    return emit_release(scene, report, coverage, geometry_root, output, image, alpha=alpha)


def emit_release(scene, validation, coverage, geometry_root, output, image, *, alpha=None):
    """The two publication categories share only deterministic asset packaging."""
    output = Path(output)
    if output.exists():
        raise ValueError('Release output must be a new directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    files = {'ldraw/' + p: b for p, b in geometry_closure(geometry_root,
                sorted({p.geometry_ref for p in scene.instances})).items()}
    metadata = scene.model_dump(mode='json', exclude={'steps'})
    if alpha is not None:
        metadata.update(release_kind='unverified_alpha', alpha=alpha.model_dump(mode='json'))
    files['preview.png'] = image
    metadata['preview'] = {'path': 'preview.png', 'scene_sha256': digest(scene)}
    metadata['reviews'] = []
    metadata['step_index'], metadata['chunks'] = [], []
    for offset in range(0, len(scene.steps), 8):
        index = offset // 8
        steps = scene.steps[offset:offset + 8]
        data = canonical({'steps': [s.model_dump(mode='json') for s in steps]})
        path = f'chunks/{index:05d}.json'
        files[path] = data
        metadata['chunks'].append(dict(index=index, path=path, sha256=hashlib.sha256(data).hexdigest(),
                                       bytes=len(data), step_ids=[s.step_id for s in steps]))
        metadata['step_index'].extend(compact_step_index(s, index) for s in steps)
    # Only typed validation summary, never private evidence paths or prompts.
    files['validation.json'] = canonical(validation)
    files['coverage.json'] = canonical(coverage)
    metadata['files'] = {p: {'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)} for p, b in files.items()}
    release_hash = digest(metadata)
    metadata['release_sha256'] = release_hash
    verify_manifest(metadata)
    files['manifest.json'] = canonical(metadata)
    if len(files['manifest.json']) > 32_000_000:
        raise ValueError('Manifest size limit')
    temp = Path(tempfile.mkdtemp(prefix='.release-', dir=output.parent))
    try:
        for name, data in files.items():
            target = temp / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        temp.rename(output)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return metadata


def verify_bundle(directory: Path) -> dict:
    directory = directory.resolve()
    manifest_path = directory / 'manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 32_000_000:
        raise ValueError('Unsafe or oversized manifest')
    manifest = verify_manifest(json.loads(manifest_path.read_text()))
    expected = set(manifest['files']) | {'manifest.json'}
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if expected != actual:
        raise ValueError('Unexpected or missing bundle files')
    for name, receipt in manifest['files'].items():
        if name.startswith('/') or '..' in name.split('/') or '\\' in name:
            raise ValueError('Unsafe bundle path')
        path = directory / name
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError('Unsafe bundle asset')
        if path.stat().st_size != receipt['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != receipt['sha256']:
            raise ValueError('Bundle bytes differ from manifest')
    scene_data = {k: v for k, v in manifest.items() if k not in TRANSPORT_FIELDS}
    scene_data['steps'] = []
    for chunk in manifest['chunks']:
        scene_data['steps'].extend(read_step_chunk((directory / chunk['path']).read_bytes()))
    validate_scene_manifest(manifest, scene_data['steps'], (directory / 'validation.json').read_bytes(),
                            json.loads((directory / 'coverage.json').read_text()))
    validate_preview_bytes((directory / 'preview.png').read_bytes())
    if manifest.get('release_kind') == 'unverified_alpha':
        validate_geometry_bundle(directory, manifest)
    return manifest


def verify_manifest(manifest: dict):
    if not isinstance(manifest, dict):
        raise ValueError('Public manifest must be an object')
    allowed_fields = (set(SceneV2.model_fields) - {'steps'}) | {'reviews', 'step_index', 'chunks', 'files', 'release_sha256', 'preview'}
    alpha = manifest.get('release_kind') == 'unverified_alpha'
    if alpha:
        allowed_fields |= {'release_kind', 'alpha'}
        AlphaDisclosure.model_validate(manifest.get('alpha'))
        sources = manifest.get('sources')
        if (not isinstance(sources, list)
                or sum(isinstance(s, dict) and s.get('guide_id') == manifest.get('guide_id') for s in sources) != 1):
            raise ValueError('Alpha guide identity must select exactly one of its pinned sources')
        if (manifest.get('status') != 'needs_review' or any(manifest.get(k) != 'not_run' for k in
                ('geometry_check', 'connector_check', 'physical_build_check'))):
            raise ValueError('Alpha publication preserves needs_review and not_run assembly checks')
    if set(manifest) != allowed_fields or manifest.get('reviews') != []:
        raise ValueError('Unexpected or missing public manifest fields')
    release_hash = manifest.get('release_sha256')
    if not isinstance(release_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', release_hash):
        raise ValueError('Invalid release hash')
    if digest({k: v for k, v in manifest.items() if k != 'release_sha256'}) != release_hash:
        raise ValueError('Manifest hash mismatch')
    if (not isinstance(manifest.get('set_number'), str) or not isinstance(manifest.get('guide_id'), str)
            or not re.fullmatch(r'[0-9]{4,7}', manifest['set_number'])
            or not re.fullmatch(r'[a-z0-9-]{1,80}', manifest['guide_id'])):
        raise ValueError('Invalid release identity')
    allowed = re.compile(r'^(preview\.png|coverage\.json|validation\.json|chunks/[0-9]{5}\.json|ldraw/(?:provenance\.json|NOTICES\.txt|LDConfig\.ldr|(?:parts/(?:s/)?|p/(?:8/|48/)?)[a-z0-9_-]+\.dat))$')
    files = manifest.get('files', {})
    if (not isinstance(files, dict) or not files or len(files) > 22000
            or any(not isinstance(p, str) or not allowed.fullmatch(p) for p in files)):
        raise ValueError('Bundle file outside publication allowlist')
    if 'coverage.json' not in files or 'preview.png' not in files or 'validation.json' not in files or 'ldraw/provenance.json' not in files or 'ldraw/NOTICES.txt' not in files:
        raise ValueError('Required publication evidence missing')
    for receipt in files.values():
        if (not isinstance(receipt, dict) or set(receipt) != {'bytes', 'sha256'}
                or type(receipt.get('bytes')) is not int or not 0 <= receipt['bytes'] <= 32_000_000
                or not isinstance(receipt.get('sha256'), str)
                or not re.fullmatch(r'[a-f0-9]{64}', receipt['sha256'])):
            raise ValueError('Invalid asset receipt')
    if sum(r['bytes'] for r in files.values()) > 512_000_000:
        raise ValueError('Release exceeds total asset byte bound')
    chunks, index = manifest['chunks'], manifest['step_index']
    if not isinstance(chunks, list) or len(chunks) > 6250 or not isinstance(index, list) or len(index) > 50_000:
        raise ValueError('Publication instruction count bound')
    for number, chunk in enumerate(chunks):
        if (not isinstance(chunk, dict) or set(chunk) != {'index', 'path', 'sha256', 'bytes', 'step_ids'}
                or type(chunk.get('index')) is not int or chunk['index'] != number
                or chunk.get('path') != f'chunks/{number:05d}.json'
                or not isinstance(chunk.get('step_ids'), list) or not 1 <= len(chunk['step_ids']) <= 8
                or any(not isinstance(s, str) or not 1 <= len(s) <= 200 for s in chunk['step_ids'])
                or files.get(chunk['path']) != {'bytes': chunk.get('bytes'), 'sha256': chunk.get('sha256')}):
            raise ValueError('Invalid publication chunk receipt or ordering')
    if alpha and (not chunks or not index or 'ldraw/LDConfig.ldr' not in files):
        raise ValueError('Required alpha scene or material assets missing')
    return manifest



def validate_scene_manifest(manifest: dict, steps: list[dict], report: bytes, source_index: dict, trusted_source_registry=None):
    verify_manifest(manifest)
    data = {k: v for k, v in manifest.items() if k not in TRANSPORT_FIELDS}
    data['steps'] = steps
    scene = SceneV2.model_validate(data)
    from guide2build.releases.evidence import verify_source_evidence, verify_source_pins, source_registry
    registry = trusted_source_registry or source_registry()
    if manifest.get('release_kind') == 'unverified_alpha':
        coverage = AlphaCoverage.model_validate(source_index)
        validation = AlphaReleaseValidation.model_validate_json(report)
        if validation.artifact_kind != manifest['alpha']['artifact_kind']:
            raise ValueError('Alpha validation differs from its disclosed artifact kind')
        validation.check(scene, coverage, manifest['files']['preview.png']['sha256'])
        verify_source_pins(scene, registry)
    else:
        validation = ReleaseValidation.model_validate_json(report)
        validation.check(scene)
        verify_source_evidence(scene, validation, registry, source_index)
    if manifest.get('preview') != {'path': 'preview.png', 'scene_sha256': digest(scene)}:
        raise ValueError('Preview is not bound to the validated scene')
    expected_index, offset = [], 0
    for index, chunk in enumerate(manifest['chunks']):
        if chunk['index'] != index or chunk['path'] != f'chunks/{index:05d}.json':
            raise ValueError('Chunk ordering mismatch')
        if not 1 <= len(chunk['step_ids']) <= 8:
            raise ValueError('Chunk size mismatch')
        selection = scene.steps[offset:offset + len(chunk['step_ids'])]
        if [s.step_id for s in selection] != chunk['step_ids']:
            raise ValueError('Chunk step identity mismatch')
        receipt = manifest['files'].get(chunk['path'])
        if not receipt or any(receipt[k] != chunk[k] for k in ('bytes', 'sha256')):
            raise ValueError('Chunk receipt mismatch')
        expected_index.extend(compact_step_index(s, index) for s in selection)
        offset += len(selection)
    if offset != len(scene.steps) or expected_index != manifest['step_index']:
        raise ValueError('Lightweight step index differs from canonical snapshots')
    return scene


def validate_geometry_bundle(directory: Path, manifest: dict):
    """An alpha package contains exactly its licensed individual-part dependency closure."""
    expected = geometry_closure(directory / 'ldraw', sorted({p['geometry_ref'] for p in manifest['instances']}))
    actual = {p[6:] for p in manifest['files'] if p.startswith('ldraw/')}
    if set(expected) != actual:
        raise ValueError('Published geometry differs from its required dependency closure')
    if any((directory / 'ldraw' / p).read_bytes() != data for p, data in expected.items()):
        raise ValueError('Public geometry provenance contains unexpected metadata')
