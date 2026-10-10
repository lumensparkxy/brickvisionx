"""Synthetic contract tests, never publication or review evidence for a LEGO model."""
import hashlib
import json
import zlib
from io import BytesIO
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from guide2build.core.models import SceneManifest
from guide2build.public import create_app
from guide2build.releases.alpha import (
    AlphaDisclosure, AlphaPreviewBinding, package_alpha_release,
)
from guide2build.releases.auth import APPROVER, GoogleIdentity
from guide2build.releases.cloud import GCSReleases
from guide2build.releases.models import ReleaseValidation, adapt_v1, canonical, coverage_keys, digest
from guide2build.releases.packaging import (
    package_release, verify_bundle, verify_manifest, geometry_closure, validate_preview_bytes,
)
from guide2build.releases.store import (
    SQLiteReleaseStore, FirestoreReleaseStore, validate_catalogue, publication_entry,
)


@pytest.fixture
def alpha_input(scene_data, tmp_path, monkeypatch):
    scene = adapt_v1(SceneManifest.model_validate(scene_data),
                     'https://www.lego.com/en-us/service/building-instructions/30669', 10)
    scene.set_number, scene.guide_id, scene.status = '30669', 'alt-02', 'needs_review'
    scene.sources[0].guide_id = 'alt-02'
    for part in scene.instances:
        part.part_id, part.geometry_ref = '3020', 'parts/3020.dat'
    geometry = tmp_path / 'geometry'
    (geometry / 'parts').mkdir(parents=True)
    # Authored synthetic unit geometry; this header tests the gate, not target-model rights.
    license_line = '0 !LICENSE Licensed under CC BY 4.0 : see CAreadme.txt'
    resource = ('0 Unit test only\n0 !LDRAW_ORG Part\n' + license_line + '\n').encode()
    (geometry / 'parts/3020.dat').write_bytes(resource)
    (geometry / 'LDConfig.ldr').write_bytes(b'0 material')
    provenance = {'resources': {'parts/3020.dat': {
        'url': 'https://library.ldraw.org/library/official/parts/3020.dat',
        'sha256': hashlib.sha256(resource).hexdigest(), 'dependencies': [], 'classification': 'Part',
        'notices': [license_line]}}, 'file_map': {}, 'materials': {'LDConfig.ldr': {
        'url': 'https://library.ldraw.org/library/official/LDConfig.ldr',
        'sha256': hashlib.sha256(b'0 material').hexdigest()}}}
    (geometry / 'provenance.json').write_bytes(canonical(provenance))
    preview = tmp_path / 'unit-test-render.png'
    Image.new('RGB', (32, 32), 'blue').save(preview)
    registry = {'schema_version': 1, 'sources': [dict(scene.sources[0].model_dump(), set_number=scene.set_number)]}
    monkeypatch.setattr('guide2build.releases.evidence.source_registry', lambda: registry)
    return {
        'scene': scene, 'alpha': dict(artifact_kind='pdf_assisted_alpha_completion', generation_mode='alpha_fast',
            source_coverage='agent_reported_unverified', coverage_text='Reported coverage (unverified): 3 main steps.',
            uncertainty_notes=['Unit-test candidate; placements and colours have not been reviewed.'],
            accuracy='unverified', human_review='not_run', physical_build='not_run'),
        'geometry_root': geometry, 'preview': preview, 'trusted_source_registry': registry,
        'source_index': dict(verification='reported_unverified', sources=[scene.source_sha256],
                             reported_step_keys=coverage_keys(scene)),
        'preview_binding': dict(scene_sha256=digest(scene), preview_sha256=hashlib.sha256(preview.read_bytes()).hexdigest(),
                                renderer='threejs', rendered_step_id=scene.steps[-1].step_id),
    }


def package(inputs, output):
    return package_alpha_release(**inputs, output=output)


def rehash(manifest):
    manifest['release_sha256'] = digest({k: v for k, v in manifest.items() if k != 'release_sha256'})


def test_alpha_package_preserves_unverified_checks_and_has_no_private_artifacts(alpha_input, tmp_path):
    output = tmp_path / 'bundle'
    manifest = package(alpha_input, output)
    assert verify_bundle(output) == manifest
    assert manifest['release_kind'] == 'unverified_alpha'
    assert manifest['alpha'] == alpha_input['alpha']
    assert manifest['status'] == 'needs_review'
    assert manifest['reviews'] == []
    assert all(manifest[k] == 'not_run' for k in ('geometry_check', 'connector_check', 'physical_build_check'))
    assert json.loads((output / 'coverage.json').read_bytes())['verification'] == 'reported_unverified'
    report = json.loads((output / 'validation.json').read_bytes())
    assert report['assembly_review'] == report['physical_build'] == 'not_run'
    assert report['preview_binding'] == alpha_input['preview_binding']
    assert not any(p.endswith(('.pdf', '.html')) or 'prompt' in p or 'source/' in p or 'jobs/' in p for p in manifest['files'])
    assert {p for p in manifest['files'] if p.endswith('.png')} == {'preview.png'}
    assert manifest['preview'] == {'path': 'preview.png', 'scene_sha256': digest(alpha_input['scene'])}
    assert manifest['instances'] == alpha_input['scene'].model_dump(mode='json')['instances']
    with pytest.raises(ValueError, match='new directory'):
        package(alpha_input, output)


def test_exploration_alpha_preserves_partial_coverage_and_generation_provenance(alpha_input, tmp_path):
    alpha_input['alpha'].update(artifact_kind='exploration_candidate', generation_mode='explore',
        source_coverage='all_instructions_processed_partial_reconstruction_unverified',
        coverage_text='Reported coverage (unverified): main step 2 is unresolved.')
    alpha_input['scene'].steps[1].main_step_number = 3
    alpha_input['source_index']['reported_step_keys'] = coverage_keys(alpha_input['scene'])
    alpha_input['preview_binding']['scene_sha256'] = digest(alpha_input['scene'])
    output = tmp_path / 'exploration'
    manifest = package(alpha_input, output)
    assert verify_bundle(output) == manifest
    assert manifest['alpha'] == alpha_input['alpha']
    assert manifest['instances'] == alpha_input['scene'].model_dump(mode='json')['instances']
    assert 'main:2' not in alpha_input['source_index']['reported_step_keys']
    assert json.loads((output / 'validation.json').read_bytes())['artifact_kind'] == 'exploration_candidate'


@pytest.mark.parametrize('artifact_kind,generation_mode', [
    ('pdf_assisted_alpha_completion', 'explore'), ('exploration_candidate', 'alpha_fast'),
])
def test_alpha_rejects_mismatched_generation_provenance(alpha_input, artifact_kind, generation_mode):
    with pytest.raises(ValueError, match='generation mode'):
        AlphaDisclosure.model_validate(alpha_input['alpha'] | {
            'artifact_kind': artifact_kind, 'generation_mode': generation_mode})


def test_alpha_validation_cannot_change_disclosed_provenance(alpha_input, tmp_path):
    from guide2build.releases.packaging import validate_scene_manifest
    alpha_input['alpha'].update(artifact_kind='exploration_candidate', generation_mode='explore')
    output = tmp_path / 'exploration'
    manifest = package(alpha_input, output)
    report = json.loads((output / 'validation.json').read_bytes())
    report['artifact_kind'] = 'pdf_assisted_alpha_completion'
    with pytest.raises(ValueError, match='disclosed artifact kind'):
        validate_scene_manifest(manifest, alpha_input['scene'].model_dump(mode='json')['steps'],
            canonical(report), alpha_input['source_index'], trusted_source_registry=alpha_input['trusted_source_registry'])


@pytest.mark.parametrize('field,value', [
    ('accuracy', 'verified'), ('human_review', 'pass'), ('physical_build', 'pass'),
    ('artifact_kind', 'automatic_reconstruction'), ('source_coverage', 'independently_verified'),
    ('coverage_text', 'All instructions independently verified.'),
    ('uncertainty_notes', ['private report /Users/admin/secret']),
    ('uncertainty_notes', ['api_key=must-not-leak']), ('uncertainty_notes', ['x' * 2001]),
    ('uncertainty_notes', ['x'] * 101), ('uncertainty_notes', ['\u00e9' * 1500] * 14),
])
def test_alpha_disclosures_reject_false_reviews_private_text_and_unbounded_notes(alpha_input, field, value):
    with pytest.raises(ValueError):
        AlphaDisclosure.model_validate(dict(alpha_input['alpha'], **{field: value}))


@pytest.mark.parametrize('field,value', [
    ('status', 'agent_reviewed'), ('status', 'candidate'), ('geometry_check', 'pass'),
    ('connector_check', 'pass'), ('physical_build_check', 'pass'), ('revision', '/private/engine/revision'),
])
def test_alpha_preserves_scene_review_status(alpha_input, tmp_path, field, value):
    alpha_input['scene'] = alpha_input['scene'].model_copy(update={field: value})
    with pytest.raises(ValueError):
        package(alpha_input, tmp_path / 'bundle')


@pytest.mark.parametrize('field,value', [
    ('scene_sha256', 'a' * 64), ('preview_sha256', 'b' * 64),
    ('renderer', 'source_pdf'), ('rendered_step_id', 's1'),
])
def test_alpha_preview_binding_is_exact(alpha_input, tmp_path, field, value):
    alpha_input['preview_binding'][field] = value
    with pytest.raises(ValueError):
        package(alpha_input, tmp_path / 'bundle')


def test_model_instance_cannot_bypass_disclosure_or_preview_validation(alpha_input, tmp_path):
    alpha_input['alpha'] = AlphaDisclosure.model_validate(alpha_input['alpha']).model_copy(update={'human_review': 'pass'})
    with pytest.raises(ValueError):
        package(alpha_input, tmp_path / 'bundle')
    alpha_input['alpha'] = alpha_input['alpha'].model_copy(update={'human_review': 'not_run'})
    alpha_input['preview_binding'] = AlphaPreviewBinding.model_validate(alpha_input['preview_binding']).model_copy(
        update={'renderer': 'source_pdf'})
    with pytest.raises(ValueError):
        package(alpha_input, tmp_path / 'bundle')


def test_alpha_coverage_and_source_pins_cannot_be_relabelled_as_verified(alpha_input, tmp_path):
    original = dict(alpha_input['source_index'])
    for update in ({'verification': 'independently_verified'}, {'sources': ['a' * 64]},
                   {'reported_step_keys': ['main:1']}, {'reported_step_keys': ['main:1', 'main:1']}):
        alpha_input['source_index'] = dict(original, **update)
        with pytest.raises(ValueError):
            package(alpha_input, tmp_path / 'bundle')
    alpha_input['source_index'] = original
    alpha_input['trusted_source_registry'] = {'schema_version': 1, 'sources': []}
    with pytest.raises(ValueError, match='pinned official source'):
        package(alpha_input, tmp_path / 'bundle')


def test_relabelled_synthetic_geometry_remains_rejected(alpha_input, tmp_path):
    alpha_input['scene'].instances[0].part_id = 'synthetic-part'
    with pytest.raises(ValueError, match='Synthetic fixture'):
        package(alpha_input, tmp_path / 'bundle')


def test_alpha_booklet_identity_must_select_its_bound_official_source(alpha_input, tmp_path):
    alpha_input['scene'].guide_id = 'alt-01'
    with pytest.raises(ValueError, match='guide identity'):
        package(alpha_input, tmp_path / 'wrong-booklet')


def test_alpha_manifest_selected_booklet_identity_is_checked_before_asset_reads(alpha_input, tmp_path):
    manifest = package(alpha_input, tmp_path / 'bundle')
    manifest['guide_id'] = 'alt-01'
    rehash(manifest)
    with pytest.raises(ValueError, match='guide identity'):
        verify_manifest(manifest)


def test_alpha_does_not_relax_reviewed_tutorial_package_gate(alpha_input, tmp_path):
    scene = alpha_input['scene']
    report = ReleaseValidation(scene_sha256=digest(scene), coverage_index_sha256='a' * 64,
        expected_step_keys=coverage_keys(scene), covered_step_keys=coverage_keys(scene),
        source_evidence_verified=True, geometry_provenance_verified=True, assembly_review='not_run',
        blockers=[], artifact_kind='pdf_assisted_authoring')
    with pytest.raises(ValueError, match='unresolved gates'):
        package_release(scene, report, alpha_input['geometry_root'], tmp_path / 'reviewed', alpha_input['preview'])
    report.assembly_review = 'pass'
    with pytest.raises(ValueError, match='Geometry and connector'):
        package_release(scene, report, alpha_input['geometry_root'], tmp_path / 'reviewed', alpha_input['preview'])


@pytest.mark.parametrize('mutation', ['remove_kind', 'fake_review', 'smuggle_pdf', 'smuggle_private_field'])
def test_alpha_manifest_rejects_category_and_privacy_tampering(alpha_input, tmp_path, mutation):
    manifest = package(alpha_input, tmp_path / 'bundle')
    if mutation == 'remove_kind':
        manifest.pop('release_kind')
    elif mutation == 'fake_review':
        manifest['alpha']['human_review'] = 'pass'
    elif mutation == 'smuggle_pdf':
        manifest['files']['source.pdf'] = {'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()}
    else:
        manifest['job_directory'] = '/private/jobs/candidate'
    rehash(manifest)
    with pytest.raises(ValueError):
        verify_manifest(manifest)


def test_bundle_rejects_byte_changes_stale_report_and_unbound_step_index(alpha_input, tmp_path):
    output = tmp_path / 'bundle'
    manifest = package(alpha_input, output)
    path = output / 'chunks/00000.json'
    original = path.read_bytes()
    path.write_bytes(b'{}')
    with pytest.raises(ValueError, match='bytes differ'):
        verify_bundle(output)
    path.write_bytes(original)
    manifest['step_index'][0]['visible_instance_count'] += 1
    rehash(manifest)
    (output / 'manifest.json').write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match='index differs'):
        verify_bundle(output)
    manifest['step_index'][0]['visible_instance_count'] -= 1
    report_path = output / 'validation.json'
    report = json.loads(report_path.read_bytes())
    report['scene_sha256'] = 'a' * 64
    data = canonical(report)
    report_path.write_bytes(data)
    manifest['files']['validation.json'] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    rehash(manifest)
    (output / 'manifest.json').write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match='Stale alpha'):
        verify_bundle(output)


def test_preview_png_cannot_contain_private_metadata(alpha_input, tmp_path):
    info = PngInfo()
    info.add_text('prompt', 'private prompt')
    Image.new('RGB', (32, 32)).save(alpha_input['preview'], pnginfo=info)
    with pytest.raises(ValueError, match='non-public metadata'):
        package(alpha_input, tmp_path / 'bundle')


def rewrite_asset(output, manifest, name, data):
    path = output / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    manifest['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    if name.startswith('chunks/'):
        manifest['chunks'][0].update(manifest['files'][name])
    rehash(manifest)
    (output / 'manifest.json').write_bytes(canonical(manifest))


def test_hash_consistent_chunk_cannot_smuggle_private_prompt(alpha_input, tmp_path):
    output = tmp_path / 'bundle'
    manifest = package(alpha_input, output)
    chunk = json.loads((output / 'chunks/00000.json').read_bytes())
    chunk['private_prompt'] = 'Local perception prompt must never be published.'
    rewrite_asset(output, manifest, 'chunks/00000.json', canonical(chunk))
    with pytest.raises(ValueError, match='public step chunk'):
        verify_bundle(output)


@pytest.mark.parametrize('mutation', ['unrelated_part', 'material_private_metadata'])
def test_hash_consistent_geometry_cannot_export_extra_assets_or_private_receipts(alpha_input, tmp_path, mutation):
    output = tmp_path / 'bundle'
    manifest = package(alpha_input, output)
    if mutation == 'unrelated_part':
        rewrite_asset(output, manifest, 'ldraw/parts/unused.dat', b'0 Unrelated asset\n')
    else:
        provenance = json.loads((output / 'ldraw/provenance.json').read_bytes())
        provenance['materials']['LDConfig.ldr']['local_file'] = '/private/runtime/LDConfig.ldr'
        rewrite_asset(output, manifest, 'ldraw/provenance.json', canonical(provenance))
    with pytest.raises(ValueError, match='dependency closure|unexpected metadata'):
        verify_bundle(output)


def test_real_notice_fields_retained_material_private_paths_stripped(alpha_input, tmp_path):
    path = alpha_input['geometry_root'] / 'provenance.json'
    provenance = json.loads(path.read_bytes())
    material = provenance['materials']['LDConfig.ldr']
    material.update(license_notice_in_file=False, legal_reference='https://www.ldraw.org/legal-info',
                    private_source_path='/private/materials/LDConfig.ldr')
    path.write_bytes(canonical(provenance))
    output = tmp_path / 'bundle'
    package(alpha_input, output)
    assert verify_bundle(output)
    public_material = json.loads((output / 'ldraw/provenance.json').read_bytes())['materials']['LDConfig.ldr']
    assert public_material['license_notice_in_file'] is False
    assert public_material['legal_reference'] == 'https://www.ldraw.org/legal-info'
    assert 'private_source_path' not in public_material
    notice = (output / 'ldraw/NOTICES.txt').read_text()
    assert 'https://creativecommons.org/licenses/by/4.0/' in notice
    assert 'https://creativecommons.org/licenses/by/2.0/' in notice
    assert '0 !LICENSE Licensed under CC BY 4.0 : see CAreadme.txt' in notice
    assert 'DAT bytes are unchanged' in notice
    assert (output / 'ldraw/parts/3020.dat').read_bytes() == (alpha_input['geometry_root'] / 'parts/3020.dat').read_bytes()


@pytest.mark.parametrize('payload', [b'private prompt', b'\n%PDF-1.7\nPRIVATE_SOURCE_PDF_PAYLOAD\n'])
def test_png_rejects_private_payload_after_iend(payload):
    stream = BytesIO()
    Image.new('RGB', (32, 32)).save(stream, format='PNG')
    with pytest.raises(ValueError, match='trailing bytes'):
        validate_preview_bytes(stream.getvalue() + payload)


def png_chunk(kind, content):
    return len(content).to_bytes(4, 'big') + kind + content + zlib.crc32(kind + content).to_bytes(4, 'big')


def test_png_rejects_unknown_ancillary_chunk_which_pillow_ignores():
    stream = BytesIO()
    Image.new('RGB', (32, 32)).save(stream, format='PNG')
    png = stream.getvalue()
    altered = png[:33] + png_chunk(b'prIv', b'PRIVATE_SOURCE_PDF_PAYLOAD') + png[33:]
    with pytest.raises(ValueError, match='non-public metadata'):
        validate_preview_bytes(altered)


def test_png_rejects_bad_framing_duplicate_headers_and_corrupt_pixels():
    stream = BytesIO()
    Image.new('RGB', (32, 32)).save(stream, format='PNG')
    png = stream.getvalue()
    for altered in (png[:33] + png[8:33] + png[33:], png[:-12], png[:-3], png[:-1] + b'x'):
        with pytest.raises(ValueError):
            validate_preview_bytes(altered)
    # Well-framed/checksummed IDAT with non-pixel bytes must also fail actual image decoding.
    altered = png[:33] + png_chunk(b'IDAT', b'PRIVATE_SOURCE_PDF_PAYLOAD') + png_chunk(b'IEND', b'')
    with pytest.raises(OSError):
        validate_preview_bytes(altered)


@pytest.mark.parametrize('alias', ['/Users/admin/private-source.pdf', '../part.dat', 'source.pdf',
                                   'https://provider.example/part.dat', 'parts/3020.dat', '3020.DAT'])
def test_geometry_alias_cannot_export_private_paths_or_non_ldraw_names(alpha_input, alias):
    root = alpha_input['geometry_root']
    path = root / 'provenance.json'
    provenance = json.loads(path.read_bytes())
    provenance['file_map'][alias] = 'parts/3020.dat'
    path.write_bytes(canonical(provenance))
    with pytest.raises(ValueError, match='Unsafe geometry alias'):
        geometry_closure(root, ['parts/3020.dat'])


def test_selected_safe_root_aliases_retained_unselected_assets_excluded(alpha_input):
    root = alpha_input['geometry_root']
    path = root / 'provenance.json'
    provenance = json.loads(path.read_bytes())
    provenance['file_map'] = {'3020.dat': 'parts/3020.dat', 'unused.dat': 'parts/unused.dat'}
    path.write_bytes(canonical(provenance))
    public = geometry_closure(root, ['parts/3020.dat'])
    assert json.loads(public['provenance.json'])['file_map'] == {'3020.dat': 'parts/3020.dat'}


@pytest.mark.parametrize('license_line', ['0 !LICENSE Not redistributable', '0 !LICENSE Unit test only',
                                       '0 !LICENSE Licensed under CC BY 4.0 : see private-license.txt', ''])
def test_unapproved_or_missing_dat_license_fails_closed(alpha_input, license_line):
    root = alpha_input['geometry_root']
    data = ('0 Unit test only\n0 !LDRAW_ORG Part\n' + license_line + '\n').encode()
    (root / 'parts/3020.dat').write_bytes(data)
    path = root / 'provenance.json'
    provenance = json.loads(path.read_bytes())
    provenance['resources']['parts/3020.dat'].update(sha256=hashlib.sha256(data).hexdigest(), notices=[license_line] if license_line else [])
    path.write_bytes(canonical(provenance))
    with pytest.raises(ValueError, match='geometry license'):
        geometry_closure(root, ['parts/3020.dat'])


def test_dual_cc_by_license_is_retained_exactly(alpha_input):
    root = alpha_input['geometry_root']
    license_line = '0 !LICENSE Licensed under CC BY 2.0 and CC BY 4.0 : see CAreadme.txt'
    data = ('0 Unit test only\n0 !LDRAW_ORG Part\n' + license_line + '\n').encode()
    (root / 'parts/3020.dat').write_bytes(data)
    path = root / 'provenance.json'
    provenance = json.loads(path.read_bytes())
    provenance['resources']['parts/3020.dat'].update(sha256=hashlib.sha256(data).hexdigest(), notices=[license_line])
    path.write_bytes(canonical(provenance))
    public = geometry_closure(root, ['parts/3020.dat'])
    assert public['parts/3020.dat'] == data
    assert license_line.encode() in public['NOTICES.txt']


def test_exact_hash_approval_cas_rollback_and_truthful_public_availability(alpha_input, tmp_path):
    store = SQLiteReleaseStore(tmp_path / 'release.db')
    c = TestClient(create_app(store, web_dist=tmp_path / 'missing'))
    identity = GoogleIdentity(APPROVER, 'unit-test-identity', True)
    old = package(alpha_input, tmp_path / 'first')
    store.stage(old)
    assert all(not g['tutorial_available'] for g in c.get('/api/v1/sets/30669').json()['guides'])
    with pytest.raises(PermissionError):
        store.approve(old['release_sha256'], GoogleIdentity('engine@example.invalid', 'unit-test', True))
    with pytest.raises(ValueError, match='approval'):
        store.promote(old['release_sha256'], identity)
    store.approve(old['release_sha256'], identity)
    assert store.published_catalogue() == []
    store.promote(old['release_sha256'], identity)
    item = c.get('/api/v1/sets/30669').json()
    assert item['status'] == 'alpha_unverified'
    guide = next(g for g in item['guides'] if g['guide_id'] == 'alt-02')
    assert guide['status'] == 'alpha_unverified' and guide['tutorial_available'] and guide['alpha_available']
    assert guide['release_kind'] == 'unverified_alpha'
    assert all(g['status'] == 'not_ready' for g in item['guides'] if g['guide_id'] != 'alt-02')
    public = c.get(guide['release_manifest_url']).json()
    assert public['release_kind'] == 'unverified_alpha' and public['alpha']['human_review'] == 'not_run'
    assert public['geometry_base_url'].endswith(old['release_sha256'] + '/ldraw/')
    scene = alpha_input['scene'].model_copy(update={'revision': 'unit-test-second'})
    alpha_input['scene'] = scene
    alpha_input['preview_binding']['scene_sha256'] = digest(scene)
    new = package(alpha_input, tmp_path / 'second')
    store.stage(new)
    with pytest.raises(ValueError, match='approval'):
        store.promote(new['release_sha256'], identity, old['release_sha256'])
    store.approve(new['release_sha256'], identity)
    with pytest.raises(ValueError, match='Stale'):
        store.promote(new['release_sha256'], identity)
    assert store.published_catalogue()[0]['release_sha256'] == old['release_sha256']
    store.promote(new['release_sha256'], identity, old['release_sha256'])
    store.promote(old['release_sha256'], identity, new['release_sha256'])
    assert store.head('30669', 'alt-02')['release_sha256'] == old['release_sha256']
    assert store.published_catalogue()[0]['release_kind'] == 'unverified_alpha'
    for path in ('/api/v1/engine-preview', '/api/v1/engine/jobs', '/assets-local/source.pdf'):
        assert c.get(path).status_code == 404


def test_legacy_catalogue_serialization_unchanged():
    from test_releases import minimal_manifest
    from guide2build.releases.store import publication_entry
    entry = publication_entry(minimal_manifest())
    assert set(entry) == {'set_number', 'guide_id', 'release_sha256', 'source'}
    assert validate_catalogue([entry]) == [entry]


@pytest.mark.parametrize('mutation', ['category', 'source', 'hash'])
def test_public_manifest_rejects_catalogue_category_source_and_hash_mismatch(alpha_input, tmp_path, mutation):
    manifest = package(alpha_input, tmp_path / 'bundle')
    entry = publication_entry(manifest)
    if mutation == 'category':
        entry.pop('release_kind')
    elif mutation == 'source':
        entry['source']['official_url'] = 'https://www.lego.com/wrong-booklet.pdf'
    else:
        entry['release_sha256'] = 'a' * 64
    calls = []
    store = SimpleNamespace(published_catalogue=lambda: [deepcopy(entry)],
                            head=lambda s, g: calls.append((s, g)) or deepcopy(manifest))
    client = TestClient(create_app(store, web_dist=tmp_path / 'missing'))
    # Catalogue lookup remains bounded, with no manifest or per-set head reads.
    assert client.get('/api/v1/sets/30669').status_code == 200
    assert calls == []
    response = client.get('/api/v1/sets/30669/guides/alt-02/release')
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'publication_state_unavailable'
    assert response.headers['Cache-Control'] == 'no-store'


def test_cached_catalogue_new_head_race_fails_closed_until_bounded_refresh(alpha_input, tmp_path, monkeypatch):
    old = package(alpha_input, tmp_path / 'old')
    alpha_input['scene'].revision = 'new-unit-test-scene'
    alpha_input['preview_binding']['scene_sha256'] = digest(alpha_input['scene'])
    new = package(alpha_input, tmp_path / 'new')
    published = [publication_entry(old)]
    head, clock, calls = [old], [100.0], []
    store = object.__new__(FirestoreReleaseStore)
    store.published_catalogue = lambda: calls.append('catalogue') or deepcopy(published)
    store.head = lambda s, g: calls.append('head') or deepcopy(head[0])
    monkeypatch.setattr('guide2build.public.time.monotonic', lambda: clock[0])
    client = TestClient(create_app(store, web_dist=tmp_path / 'missing'))
    assert client.get('/api/v1/sets/30669').json()['status'] == 'alpha_unverified'
    head[0], published[0] = new, publication_entry(new)
    path = '/api/v1/sets/30669/guides/alt-02/release'
    assert client.get(path).status_code == 503
    assert calls == ['catalogue', 'head']
    clock[0] += 31
    assert client.get(path).json()['release_sha256'] == new['release_sha256']
    assert calls == ['catalogue', 'head', 'catalogue', 'head']
    assert client.get(path).status_code == 200
    assert calls == ['catalogue', 'head', 'catalogue', 'head']


def test_live_cached_manifest_rejects_same_hash_catalogue_metadata_changes(alpha_input, tmp_path, monkeypatch):
    manifest = package(alpha_input, tmp_path / 'bundle')
    entry = publication_entry(manifest)
    clock, calls = [100.0], []
    store = object.__new__(FirestoreReleaseStore)
    store.published_catalogue = lambda: calls.append('catalogue') or [deepcopy(entry)]
    store.head = lambda s, g: calls.append('head') or deepcopy(manifest)
    monkeypatch.setattr('guide2build.public.time.monotonic', lambda: clock[0])
    client = TestClient(create_app(store, web_dist=tmp_path / 'missing'))
    path = '/api/v1/sets/30669/guides/alt-02/release'
    assert client.get('/api/v1/sets/30669').status_code == 200  # Catalogue TTL starts at100.
    clock[0] += 10
    assert client.get(path).status_code == 200
    clock[0] += 19
    assert client.get(path).status_code == 200  # Renews neither catalogue nor manifest TTL.
    entry.pop('release_kind')
    clock[0] += 2
    # Catalogue expires at130; the hash-bound manifest remains live until140.
    assert client.get('/api/v1/sets/30669').status_code == 200
    assert client.get(path).status_code == 503
    assert calls == ['catalogue', 'head', 'catalogue']  # Integrity check hits cache, with no new head read.


class MemoryDocument:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def get(self, transaction=None):
        value = deepcopy(self.db.data.get(self.path))
        return SimpleNamespace(exists=value is not None, to_dict=lambda: value)

    def set(self, value):
        self.db.data[self.path] = deepcopy(value)


class MemoryFirestore:
    def __init__(self):
        self.data, self.next_id = {}, 0

    def collection(self, collection):
        def document(identity=None):
            if identity is None:
                self.next_id += 1
                identity = str(self.next_id)
            return MemoryDocument(self, (collection, identity))
        return SimpleNamespace(document=document)

    def transaction(self):
        def create(document, value):
            assert document.path not in self.data
            document.set(value)

        def update(document, value):
            document.set(dict(self.data[document.path], **value))

        return SimpleNamespace(create=create, set=lambda document, value: document.set(value), update=update)


def firestore_store():
    store = object.__new__(FirestoreReleaseStore)
    store.fs = SimpleNamespace(transactional=lambda operation: operation)
    store.db = MemoryFirestore()
    return store


@pytest.mark.parametrize('mutation', ['category', 'source', 'hash', 'missing_receipt'])
def test_firestore_staged_catalogue_receipt_rejects_tampered_metadata_before_pointer_writes(alpha_input, tmp_path, mutation):
    manifest = package(alpha_input, tmp_path / 'bundle')
    store = firestore_store()
    release_hash = manifest['release_sha256']
    identity = GoogleIdentity(APPROVER, 'unit-test-identity', True)
    store.stage(manifest)
    store.approve(release_hash, identity)
    release = store.db.data['releases', release_hash]
    assert release['catalogue_entry_sha256'] == digest(publication_entry(manifest))
    if mutation == 'category':
        release['catalogue_entry'].pop('release_kind')
    elif mutation == 'source':
        release['catalogue_entry']['source']['official_url'] = 'https://www.lego.com/wrong-booklet.pdf'
    elif mutation == 'hash':
        release['catalogue_entry']['release_sha256'] = 'a' * 64
    else:
        release.pop('catalogue_entry_sha256')
    with pytest.raises(ValueError, match='staged receipt'):
        store.promote(release_hash, identity)
    assert not any(collection in {'heads', 'catalogue'} for collection, _ in store.db.data)
    # Re-stage actual hash-bound manifest to restore/backfill metadata; exact approval remains.
    store.stage(manifest)
    store.promote(release_hash, identity)
    assert store.db.data['heads', '30669-alt-02']['hash'] == release_hash
    assert store.db.data['catalogue', 'published']['entries'] == [publication_entry(manifest)]


def test_legacy_firestore_release_stages_receipt_and_promotes_without_new_public_fields():
    from test_releases import minimal_manifest
    manifest = minimal_manifest()
    store = firestore_store()
    identity = GoogleIdentity(APPROVER, 'unit-test-identity', True)
    store.stage(manifest)
    store.approve(manifest['release_sha256'], identity)
    store.promote(manifest['release_sha256'], identity)
    entry = store.db.data['catalogue', 'published']['entries'][0]
    assert set(entry) == {'set_number', 'guide_id', 'release_sha256', 'source'}


class MemoryBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name, self.generation, self.size = bucket, name, 1, None

    def exists(self):
        return self.name in self.bucket.data

    def reload(self):
        self.size = len(self.bucket.data[self.name])

    def download_as_bytes(self, if_generation_match):
        assert if_generation_match == self.generation
        return self.bucket.data[self.name]

    def upload_from_filename(self, path, if_generation_match, content_type):
        self.upload_from_string(Path(path).read_bytes(), if_generation_match, content_type)

    def upload_from_string(self, data, if_generation_match, content_type):
        assert if_generation_match == 0
        with self.bucket.lock:
            assert self.name not in self.bucket.data
            self.bucket.data[self.name] = data
        self.size = len(data)


class MemoryBucket:
    def __init__(self):
        self.data, self.lock = {}, Lock()

    def blob(self, name):
        return MemoryBlob(self, name)


def cloud(workers=1):
    client = object.__new__(GCSReleases)
    client.staging, client.public, client.transfer_workers = MemoryBucket(), MemoryBucket(), workers
    return client


@pytest.mark.parametrize('workers', [1, 8])
def test_staging_publish_concurrency_is_bounded_hash_checked_and_resumable(alpha_input, tmp_path, workers):
    directory = tmp_path / 'bundle'
    manifest = package(alpha_input, directory)
    client = cloud(workers)
    client.stage(directory)
    client.stage(directory)  # Generation-zero uploads never overwrite existing bytes.
    release_hash = manifest['release_sha256']
    assert client.validate_staged(release_hash) == manifest
    with pytest.raises(PermissionError):
        client.publish(release_hash, GoogleIdentity('engine@example.invalid', 'unit-test', True))
    assert client.public.data == {}
    published = client.publish(release_hash, GoogleIdentity(APPROVER, 'unit-test', True))
    assert published == manifest
    client.publish(release_hash, GoogleIdentity(APPROVER, 'unit-test', True))
    assert client.public.data == client.staging.data
    client.staging.data[release_hash + '/chunks/00000.json'] = b'{}'
    with pytest.raises(ValueError, match='size mismatch'):
        client.validate_staged(release_hash)


@pytest.mark.parametrize('workers', [0, 9, True, 1.5])
def test_cloud_transfer_concurrency_rejects_unbounded_values(workers):
    with pytest.raises(ValueError, match='Transfer workers'):
        GCSReleases('unit-test', 'staging', 'public', transfer_workers=workers)
