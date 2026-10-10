from fastapi.testclient import TestClient
from guide2build.public import create_app, MESSAGE
from guide2build.releases.store import SQLiteReleaseStore


def client(tmp_path, cap=100):
    return TestClient(create_app(SQLiteReleaseStore(tmp_path/'public.db', daily_cap=cap), web_dist=tmp_path/'missing'))


def test_public_does_not_import_local_routes(tmp_path):
    c = client(tmp_path)
    assert c.get('/api/v1/config').json() == dict(mode='public',source_images=False,requests_enabled=True)
    for path in ['/api/v1/conversions','/api/v1/jobs/private','/api/v1/sources/'+'a'*64+'/pages/1',
                 '/api/v1/reconstructions/private/scene','/assets-local/pages/private.png',
                 '/api/v1/sets/30669/guides/alt-02/scene']:
        assert c.get(path).status_code == 404
    assert c.post('/api/v1/conversions',json={}).status_code == 404
    item = c.get('/api/v1/sets/30669').json()
    assert all(not g['tutorial_available'] for g in item['guides'])
    assert c.get('/api/v1/sets/30669/guides/alt-02/release').status_code == 404


def test_unknown_requests_only_confirm_after_persist(tmp_path):
    c = client(tmp_path, cap=1)
    assert c.get('/api/v1/sets/99999').json()['status'] == 'not_ready'
    first = c.post('/api/v1/requests',json={'set_number':'99999'})
    assert first.status_code == 202 and first.json()['message'] == MESSAGE
    assert c.post('/api/v1/requests',json={'set_number':'99999'}).json()['duplicate'] is True
    limited = c.post('/api/v1/requests',json={'set_number':'30669'})
    assert limited.status_code == 429 and MESSAGE not in limited.text
    assert c.post('/api/v1/requests',json={'set_number':'30669','actor_type':'human'}).status_code == 422
    assert c.post('/api/v1/requests',json={'set_number':'123'},headers={'Origin':'https://evil.example'}).status_code == 403
    assert c.post('/api/v1/requests',content='x'*600).status_code == 413


def test_spa_does_not_turn_private_api_into_html(tmp_path):
    dist = tmp_path/'dist'
    dist.mkdir()
    (dist/'index.html').write_text('<html>Public portal</html>')
    c = TestClient(create_app(SQLiteReleaseStore(tmp_path/'db'),web_dist=dist))
    assert c.get('/build/30669').status_code == 200
    assert c.get('/api/v1/secret').status_code == 404
    assert c.get('/assets-local/source.pdf').status_code == 404
    assert c.get('/missing.js').status_code == 404


def test_request_admission_bounds_duplicate_database_reads(tmp_path):
    c = client(tmp_path)
    for _ in range(60):
        assert c.post('/api/v1/requests',json={'set_number':'30669'}).status_code == 202
    assert c.post('/api/v1/requests',json={'set_number':'30669'}).status_code == 429


def test_firestore_catalogue_is_cached_and_unknown_searches_never_read_heads(tmp_path, monkeypatch):
    from guide2build.releases.store import FirestoreReleaseStore
    store = object.__new__(FirestoreReleaseStore)
    calls = []
    store.published_catalogue = lambda: calls.append('catalogue') or []
    store.head = lambda s,g: calls.append((s,g,'full')) or None
    now = [100.0]
    monkeypatch.setattr('guide2build.public.time.monotonic', lambda:now[0])
    c = TestClient(create_app(store, web_dist=tmp_path/'missing'))
    c.get('/api/v1/sets/30669')
    c.get('/api/v1/sets/30669')
    assert calls == ['catalogue']
    c.get('/api/v1/sets/99999/guides/unknown/release')
    assert calls == ['catalogue']
    now[0] += 31
    c.get('/api/v1/sets/30669')
    assert calls == ['catalogue', 'catalogue']
    assert c.get('/api/v1/sets/30669').headers['Cache-Control'] == 'public,max-age=30'


def test_new_approved_set_is_discoverable_without_changing_container_catalogue(tmp_path):
    from test_releases import minimal_manifest
    from guide2build.releases.models import digest
    from guide2build.releases.auth import GoogleIdentity, APPROVER
    store = SQLiteReleaseStore(tmp_path/'db')
    catalogue = tmp_path/'catalogue.json'
    catalogue.write_text('{"sets":[]}')
    c = TestClient(create_app(store, catalogue_path=catalogue, web_dist=tmp_path/'missing'))
    manifest = minimal_manifest()
    manifest['set_number'] = '99999'
    manifest['sources'][0]['official_url'] = 'https://www.lego.com/cdn/product-assets/product.bi.core.pdf/approved.pdf'
    manifest['release_sha256'] = digest({k:v for k,v in manifest.items() if k != 'release_sha256'})
    store.stage(manifest)
    assert c.get('/api/v1/sets/99999').json()['status'] == 'not_ready'
    identity = GoogleIdentity(APPROVER, 'unit-test-identity', True)
    store.approve(manifest['release_sha256'], identity)
    assert c.get('/api/v1/sets/99999').json()['guides'] == []
    store.promote(manifest['release_sha256'], identity)
    item = c.get('/api/v1/sets/99999').json()
    assert item['name'] == 'Set 99999'
    assert item['guides'][0]['tutorial_available'] is True
    assert item['guides'][0]['pdf_url'] == manifest['sources'][0]['official_url']
    assert item['official_page'] == manifest['sources'][0]['official_url']
    assert c.get(item['guides'][0]['release_manifest_url']).json()['release_sha256'] == manifest['release_sha256']
