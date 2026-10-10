import hashlib
import json
from pathlib import Path
import pytest
from guide2build.core.models import SceneManifest
from guide2build.releases.models import SceneV2, adapt_v1, digest, coverage_keys, ReleaseValidation
from guide2build.releases.packaging import package_release, verify_bundle, verify_manifest
from guide2build.releases.auth import GoogleIdentity, APPROVER
from guide2build.releases.store import SQLiteReleaseStore, RequestLimit


@pytest.fixture
def v2(scene_data):
    return adapt_v1(SceneManifest.model_validate(scene_data),
                    'https://www.lego.com/en-us/service/building-instructions/30669', 10)


def validation(scene):
    return ReleaseValidation(scene_sha256=digest(scene), coverage_index_sha256='b'*64,
        expected_step_keys=coverage_keys(scene), covered_step_keys=coverage_keys(scene),
        source_evidence_verified=True, geometry_provenance_verified=True, assembly_review='pass',
        blockers=[], artifact_kind='automatic_reconstruction')


def test_multisource_sections_and_number_reset(v2):
    data = v2.model_dump(mode='json')
    data['sources'].append(dict(data['sources'][0], guide_id='second', source_sha256='c'*64))
    data['sections'].append(dict(section_id='second', source_sha256='c'*64, label='Second'))
    data['steps'][-1].update(section_id='second', main_step_number=1)
    data['steps'][-1]['source']['source_sha256'] = 'c'*64
    scene = SceneV2.model_validate(data)
    assert scene.steps[-1].main_step_number == 1
    data['steps'][-1]['source']['source_sha256'] = 'd'*64
    with pytest.raises(ValueError, match='Unknown source'):
        SceneV2.model_validate(data)


def test_v2_no_duplicate_piece_on_attachment(v2):
    data = v2.model_dump(mode='json')
    data['steps'][-1]['introduced_instance_ids'] = ['a']
    with pytest.raises(ValueError, match='introduced only once'):
        SceneV2.model_validate(data)


def test_release_gates_stale_partial_fixture(v2):
    v2.geometry_check = v2.connector_check = 'pass'
    report = validation(v2)
    report.check(v2)
    for field, value in [('artifact_kind', 'fixture'), ('blockers', ['floating slope']),
                         ('assembly_review', 'not_run'), ('source_evidence_verified', False),
                         ('covered_step_keys', []), ('scene_sha256', 'a'*64)]:
        changed = report.model_copy(update={field: value})
        with pytest.raises(ValueError):
            changed.check(v2)


def test_request_dedup_and_global_cap(tmp_path):
    store = SQLiteReleaseStore(tmp_path/'release.db', daily_cap=1)
    assert store.request('30669') is False
    assert store.request('30669') is True
    with pytest.raises(RequestLimit):
        store.request('60400')
    assert SQLiteReleaseStore(tmp_path/'release.db').requests()[0]['set_number'] == '30669'


def minimal_manifest(revision='one'):
    data = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/synthetic.scene.json').read_text())
    scene = adapt_v1(SceneManifest.model_validate(data), 'https://www.lego.com/en-us/service/building-instructions/30669', 10)
    m = scene.model_dump(mode='json', exclude={'steps'})
    m.update(set_number='30669', guide_id='alt-02', revision=revision, reviews=[], step_index=[], chunks=[], preview={'path':'preview.png','scene_sha256':digest(scene)},
        files={p: {'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()} for p in
               ['coverage.json', 'preview.png', 'validation.json', 'ldraw/provenance.json', 'ldraw/NOTICES.txt']})
    return dict(m, release_sha256=digest(m))


def test_approval_exact_hash_atomic_head_and_rollback(tmp_path):
    store = SQLiteReleaseStore(tmp_path/'release.db')
    human = GoogleIdentity(APPROVER, 'verified-test-subject', True)
    first, second = minimal_manifest(), minimal_manifest('two')
    store.stage(first)
    assert store.head('30669', 'alt-02') is None
    with pytest.raises(PermissionError):
        store.approve(first['release_sha256'], GoogleIdentity('engine@project.iam.gserviceaccount.com', 's', True))
    with pytest.raises(ValueError, match='approval'):
        store.promote(first['release_sha256'], human)
    store.approve(first['release_sha256'], human)
    store.promote(first['release_sha256'], human)
    store.stage(second)
    with pytest.raises(ValueError, match='approval'):
        store.promote(second['release_sha256'], human, first['release_sha256'])
    store.approve(second['release_sha256'], human)
    with pytest.raises(ValueError, match='Stale'):
        store.promote(second['release_sha256'], human)
    assert store.head('30669', 'alt-02')['revision'] == 'one'
    store.promote(second['release_sha256'], human, first['release_sha256'])
    store.promote(first['release_sha256'], human, second['release_sha256'])
    assert store.head('30669', 'alt-02')['revision'] == 'one'


def test_manifest_cannot_smuggle_pdf():
    manifest = minimal_manifest()
    manifest['files']['source.pdf'] = {'bytes': 0, 'sha256': 'a'*64}
    manifest['release_sha256'] = digest({k:v for k,v in manifest.items() if k != 'release_sha256'})
    with pytest.raises(ValueError, match='allowlist'):
        verify_manifest(manifest)


def test_package_is_atomic_allowlisted_and_hash_checked(v2, tmp_path, monkeypatch):
    # Synthetic geometry is only a unit test; no resulting bundle is published.
    for part in v2.instances:
        part.part_id = '3020'
        part.geometry_ref = 'parts/3020.dat'
    root = tmp_path/'geometry'
    (root/'parts').mkdir(parents=True)
    refs = sorted({i.geometry_ref for i in v2.instances})
    # Synthetic authored test input; no bundle from this test is published.
    resource = b'0 Test geometry\n0 !LDRAW_ORG Part\n0 !LICENSE Licensed under CC BY 4.0 : see CAreadme.txt\n'
    records = {}
    for ref in refs:
        (root/ref).write_bytes(resource)
        records[ref] = dict(url='https://library.ldraw.org/library/official/'+ref,
                            sha256=hashlib.sha256(resource).hexdigest(), dependencies=[], classification='Part', notices=['0 !LICENSE Licensed under CC BY 4.0 : see CAreadme.txt'])
    (root/'LDConfig.ldr').write_bytes(b'0 material')
    material = dict(url='https://library.ldraw.org/library/official/LDConfig.ldr',sha256=hashlib.sha256(b'0 material').hexdigest())
    (root/'provenance.json').write_text(json.dumps(dict(resources=records, materials={'LDConfig.ldr':material},file_map={})))
    v2.geometry_check = v2.connector_check = 'pass'
    output = tmp_path/'bundle'
    from PIL import Image
    preview = tmp_path/'synthetic-test-preview.png'
    Image.new('RGB', (32,32), 'blue').save(preview)
    index = dict(verification='independently_verified', sources=[v2.source_sha256], expected_step_keys=coverage_keys(v2))
    report = validation(v2).model_copy(update={'coverage_index_sha256': digest(index)})
    registry = {'schema_version':1,'sources':[dict(v2.sources[0].model_dump(), set_number=v2.set_number)]}
    monkeypatch.setattr('guide2build.releases.evidence.source_registry', lambda: registry)
    manifest = package_release(v2, report, root, output, preview, registry, index)
    assert verify_bundle(output)['release_sha256'] == manifest['release_sha256']
    assert all(not {'poses', 'visible_instance_ids', 'active_instance_ids'} & s.keys() for s in manifest['step_index'])
    assert [s['visible_instance_count'] for s in manifest['step_index']] == [len(s.visible_instance_ids) for s in v2.steps]
    altered = json.loads((output/'manifest.json').read_text())
    altered['step_index'][0]['visible_instance_count'] += 1
    altered['release_sha256'] = digest({k:v for k,v in altered.items() if k != 'release_sha256'})
    (output/'manifest.json').write_text(json.dumps(altered))
    with pytest.raises(ValueError, match='index differs'):
        verify_bundle(output)
    (output/'manifest.json').write_text(json.dumps(manifest))
    assert not (output/'source.pdf').exists()
    (output/'chunks/00000.json').write_text('{}')
    with pytest.raises(ValueError, match='bytes differ'):
        verify_bundle(output)


def test_renaming_fixture_does_not_change_artifact_origin(v2):
    v2.set_number = '10316'
    v2.guide_id = 'booklet-01'
    v2.revision = 'looks-like-production'
    v2.geometry_check = v2.connector_check = 'pass'
    report = validation(v2).model_copy(update={'artifact_kind': 'fixture'})
    with pytest.raises(ValueError, match='unresolved gates'):
        report.check(v2)


def test_unexpected_source_payload_never_public_manifest():
    m = minimal_manifest()
    m['private_source_path'] = '/private/local/source.pdf'
    m['release_sha256'] = digest({k:v for k,v in m.items() if k != 'release_sha256'})
    with pytest.raises(ValueError, match='manifest fields'):
        verify_manifest(m)


def test_named_databases_are_mandatory(monkeypatch):
    from guide2build.releases.store import FirestoreReleaseStore
    with pytest.raises(ValueError, match='Dedicated'):
        FirestoreReleaseStore('test-project', database='(default)')


def test_real_source_pins_reject_relabelled_synthetic_scene(v2):
    from guide2build.releases.evidence import verify_source_evidence, source_registry
    v2.set_number = '30669'
    v2.guide_id = 'alt-02'
    index = dict(verification='independently_verified', sources=[v2.source_sha256], expected_step_keys=coverage_keys(v2))
    report = validation(v2).model_copy(update={'coverage_index_sha256': digest(index)})
    with pytest.raises(ValueError, match='pinned official source'):
        verify_source_evidence(v2, report, source_registry(), index)


def test_unverified_coverage_is_not_a_release_denominator(v2):
    from guide2build.releases.evidence import verify_source_evidence
    index = dict(verification='automatic_unverified', sources=[v2.source_sha256], expected_step_keys=coverage_keys(v2))
    with pytest.raises(ValueError):
        verify_source_evidence(v2, validation(v2), {}, index)


def test_source_pin_history_accepts_old_and_new_editions(v2):
    from guide2build.releases.evidence import verify_source_evidence
    for part in v2.instances:
        part.part_id = '3020'
        part.geometry_ref = 'parts/3020.dat'
    old = v2.model_copy(deep=True)
    new = v2.model_copy(deep=True)
    new_hash = 'c'*64
    new.source_sha256 = new_hash
    new.sources[0].source_sha256 = new_hash
    new.sections[0].source_sha256 = new_hash
    for item in [*new.instances, *new.steps]:
        item.source.source_sha256 = new_hash
    registry = {'schema_version':1, 'sources':[
        dict(old.sources[0].model_dump(), set_number=old.set_number),
        dict(new.sources[0].model_dump(), set_number=new.set_number)]}
    for scene in (old, new):
        index = dict(verification='independently_verified', sources=[scene.source_sha256],
                     expected_step_keys=coverage_keys(scene))
        report = validation(scene).model_copy(update={'coverage_index_sha256':digest(index)})
        verify_source_evidence(scene, report, registry, index)
    registry['sources'].pop()
    with pytest.raises(ValueError, match='pinned official source'):
        verify_source_evidence(new, report, registry, index)


def test_compact_index_grows_linearly_even_when_every_piece_is_active(v2):
    from guide2build.releases.packaging import compact_step_index
    from guide2build.releases.models import canonical
    base = v2.steps[0]

    def serialized_index(count):
        result = []
        for index in range(count):
            cumulative = [f'piece-{piece:05d}' for piece in range(index + 1)]
            # This transport stress fixture deliberately activates the whole cumulative assembly.
            step = base.model_copy(update={'step_id':f'step-{index:05d}', 'main_step_number':index+1,
                'introduced_instance_ids':[cumulative[-1]], 'active_instance_ids':cumulative,
                'visible_instance_ids':cumulative, 'poses':{}})
            result.append(compact_step_index(step, index // 8))
        return result, len(canonical(result))

    first, small = serialized_index(300)
    second, large = serialized_index(600)
    assert large < small * 2.1
    assert sum(len(s['introduced_instance_ids']) for s in second) == 600
    assert first[-1]['visible_instance_count'] == first[-1]['active_instance_count'] == 300
    assert second[-1]['visible_instance_count'] == second[-1]['active_instance_count'] == 600
    assert all('visible_instance_ids' not in s and 'active_instance_ids' not in s for s in second)


def test_catalogue_changes_atomically_with_promotion_and_rollback(tmp_path):
    store = SQLiteReleaseStore(tmp_path/'db')
    identity = GoogleIdentity(APPROVER, 'unit-test-identity', True)
    old, new = minimal_manifest(), minimal_manifest('two')
    new['sources'][0]['official_url'] = 'https://www.lego.com/cdn/product-assets/product.bi.core.pdf/new-edition.pdf'
    new['release_sha256'] = digest({k:v for k,v in new.items() if k != 'release_sha256'})
    for manifest in (old, new):
        store.stage(manifest)
        store.approve(manifest['release_sha256'], identity)
    assert store.published_catalogue() == []
    store.promote(old['release_sha256'], identity)
    assert store.published_catalogue()[0]['release_sha256'] == old['release_sha256']
    with pytest.raises(ValueError, match='Stale'):
        store.promote(new['release_sha256'], identity)
    assert store.published_catalogue()[0]['release_sha256'] == old['release_sha256']
    store.promote(new['release_sha256'], identity, old['release_sha256'])
    assert store.published_catalogue()[0]['source']['official_url'] == new['sources'][0]['official_url']
    store.promote(old['release_sha256'], identity, new['release_sha256'])
    assert store.published_catalogue()[0]['source']['official_url'] == old['sources'][0]['official_url']


def test_catalogue_limit_failure_leaves_existing_head_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr('guide2build.releases.store.CATALOGUE_MAX_ENTRIES', 1)
    store = SQLiteReleaseStore(tmp_path/'db')
    identity = GoogleIdentity(APPROVER, 'unit-test-identity', True)
    first, second = minimal_manifest(), minimal_manifest('two')
    second['set_number'] = '99999'
    second['release_sha256'] = digest({k:v for k,v in second.items() if k != 'release_sha256'})
    for manifest in (first, second):
        store.stage(manifest)
        store.approve(manifest['release_sha256'], identity)
    store.promote(first['release_sha256'], identity)
    with pytest.raises(ValueError, match='entry bound'):
        store.promote(second['release_sha256'], identity)
    assert store.head('99999', 'alt-02') is None
    assert len(store.published_catalogue()) == 1
    assert store.head('30669', 'alt-02')['release_sha256'] == first['release_sha256']
