"""Public deployment entrypoint. Never imports the local application or mounts var/."""
from __future__ import annotations
import json
import os
import re
import time
from collections import deque, OrderedDict
from threading import RLock
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field
from guide2build.core.models import StrictModel
from guide2build.releases.store import (
    SQLiteReleaseStore, FirestoreReleaseStore, RequestLimit, publication_entry, validate_catalogue,
)

ROOT = Path(__file__).resolve().parents[4]
MESSAGE = 'This build isn’t ready yet. We’ve added it to our building list. Come back later to see what’s new!'


class SetRequest(StrictModel):
    set_number: str = Field(pattern=r'^[0-9]{4,7}$')


def error(status, code, message):
    raise HTTPException(status, detail={'code': code, 'message': message})


def create_app(store=None, catalogue_path: Path | None = None, web_dist: Path | None = None):
    app = FastAPI(title='Guide2Build public portal', docs_url=None, redoc_url=None, openapi_url=None)
    if store is None:
        if os.getenv('GUIDE2BUILD_PUBLIC_STORE') == 'firestore':
            store = FirestoreReleaseStore(project=os.environ['GOOGLE_CLOUD_PROJECT'],
                database=os.getenv('GUIDE2BUILD_FIRESTORE_DATABASE', 'guide2build'))
        else:
            store = SQLiteReleaseStore(Path(os.getenv('GUIDE2BUILD_PUBLIC_DB', str(ROOT / 'var/publication.sqlite3'))))
    catalogue = json.loads((catalogue_path or ROOT / 'config/sets.json').read_text())['sets']
    app.state.store = store
    admission = deque()
    release_cache = OrderedDict()
    catalogue_cache = [0.0, []]
    cache_lock = RLock()

    def published_catalogue():
        if not isinstance(store, FirestoreReleaseStore):
            return validate_catalogue(store.published_catalogue())
        with cache_lock:
            now = time.monotonic()
            if now >= catalogue_cache[0]:
                catalogue_cache[:] = [now + 30, validate_catalogue(store.published_catalogue())]
            return catalogue_cache[1]

    def read_release(set_number, guide_id):
        entry = next((e for e in published_catalogue()
                      if e['set_number'] == set_number and e['guide_id'] == guide_id), None)
        if entry is None:
            return None  # random searches never create per-set database reads or cache entries
        def checked_head():
            from guide2build.releases.packaging import verify_manifest
            try:
                manifest = store.head(set_number, guide_id)
                if manifest is None:
                    return None
                verify_manifest(manifest)
                if publication_entry(manifest) != entry:
                    raise ValueError('Publication catalogue differs from its manifest')
                return manifest
            except ValueError:
                error(503, 'publication_state_unavailable',
                      'This model’s publication status is updating. Please try again shortly.')
        if not isinstance(store, FirestoreReleaseStore):
            return checked_head()
        with cache_lock:
            key = (set_number, guide_id, entry['release_sha256'])
            cached = release_cache.get(key)
            now = time.monotonic()
            if cached is not None and now < cached[0]:
                if cached[1] is not None and publication_entry(cached[1]) != entry:
                    error(503, 'publication_state_unavailable',
                          'This model’s publication status is updating. Please try again shortly.')
                release_cache.move_to_end(key)
                return cached[1]
            value = checked_head()
            release_cache[key] = (now + 30, value)
            release_cache.move_to_end(key)
            while len(release_cache) > 4:
                release_cache.popitem(last=False)
            return value

    asset_base = os.getenv('GUIDE2BUILD_ASSET_BASE_URL', '/published-assets/').rstrip('/') + '/'

    @app.middleware('http')
    async def safe_headers(request, call_next):
        if request.method == 'POST':
            length = request.headers.get('content-length')
            if length is None or not length.isdigit() or int(length) > 512:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=413, content={'detail': {'code': 'request_too_large', 'message': 'Request is too large.'}})
            origin = request.headers.get('origin')
            if origin and origin != f'{request.url.scheme}://{request.url.netloc}':
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=403, content={'detail': {'code': 'origin_rejected', 'message': 'Request origin is not allowed.'}})
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if request.method == 'GET' and response.status_code == 200:
            immutable = re.fullmatch(r'/assets/[^/]+-[A-Za-z0-9_-]{8,}\.(?:js|css|woff2|png|webp)', request.url.path)
            response.headers['Cache-Control'] = 'public,max-age=31536000,immutable' if immutable else 'public,max-age=30'
        else:
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/v1/health')
    def health():
        return {'status': 'ok', 'mode': 'public'}

    @app.get('/api/v1/config')
    def config():
        return {'mode': 'public', 'source_images': False, 'requests_enabled': True}

    @app.get('/api/v1/sets/{set_number}')
    def lookup(set_number: str):
        if not re.fullmatch(r'[0-9]{4,7}', set_number):
            error(422, 'invalid_set_number', 'Enter a 4–7 digit set number.')
        item = next((x for x in catalogue if x['set_number'] == set_number), None)
        published = {entry['guide_id']:entry for entry in published_catalogue() if entry['set_number'] == set_number}
        if not item and not published:
            return {'set_number': set_number, 'name': None, 'official_page': None, 'guides': [], 'status': 'not_ready'}
        configured = {g['guide_id']:g for g in item['guides']} if item else {}
        guides = []
        for guide_id in dict.fromkeys([*configured, *published]):
            entry = published.get(guide_id)
            guide = configured.get(guide_id)
            if guide:
                metadata = {k: guide[k] for k in ('guide_id', 'label', 'expected_page_count', 'expected_main_steps', 'pdf_url')}
            else:
                metadata = {'guide_id':guide_id, 'label':f'Booklet {guide_id}',
                            'expected_page_count':entry['source']['page_count'], 'expected_main_steps':None,
                            'pdf_url':entry['source']['official_url']}
            if entry:
                metadata.update(pdf_url=entry['source']['official_url'],
                                expected_page_count=entry['source']['page_count'])
            metadata.update(tutorial_available=entry is not None, status='published' if entry else 'not_ready',
                release_manifest_url=f"/api/v1/sets/{set_number}/guides/{guide_id}/release" if entry else None)
            if entry and entry.get('release_kind') == 'unverified_alpha':
                metadata.update(release_kind='unverified_alpha', alpha_available=True, status='alpha_unverified')
            guides.append(metadata)
        status = ('published' if any(e.get('release_kind') != 'unverified_alpha' for e in published.values())
                  else 'alpha_unverified' if published else 'not_ready')
        return {'set_number': set_number, 'name': item['name'] if item else f'Set {set_number}',
                'official_page': item['official_page'] if item else next(iter(published.values()))['source']['official_url'],
                'guides': guides, 'status': status}

    @app.get('/api/v1/sets/{set_number}/guides/{guide_id}/release')
    def release(set_number: str, guide_id: str):
        if not re.fullmatch(r'[0-9]{4,7}', set_number) or not re.fullmatch(r'[a-z0-9-]{1,80}', guide_id):
            error(422, 'invalid_identity', 'Invalid tutorial identifier.')
        manifest = read_release(set_number, guide_id)
        if not manifest:
            error(404, 'tutorial_not_published', 'This tutorial isn’t ready yet.')
        base = asset_base + manifest['release_sha256'] + '/'
        return dict(manifest, asset_base_url=base, geometry_base_url=base + 'ldraw/')

    @app.post('/api/v1/requests', status_code=202)
    async def request_set(request: Request):
        now = time.monotonic()
        while admission and admission[0] < now - 60:
            admission.popleft()
        if len(admission) >= 60:
            error(429, 'request_rate_limit', 'Our building list is busy. Please try again shortly.')
        admission.append(now)
        body = await request.body()
        if len(body) > 512:
            error(413, 'request_too_large', 'Request is too large.')
        try:
            payload = SetRequest.model_validate_json(body)
        except ValueError:
            error(422, 'invalid_request', 'Enter a 4–7 digit set number.')
        try:
            duplicate = store.request(payload.set_number)
        except RequestLimit:
            error(429, 'request_capacity', 'Our building list is busy. Please try again tomorrow.')
        return {'set_number': payload.set_number, 'status': 'requested', 'duplicate': duplicate, 'message': MESSAGE}

    # SPA fallback explicitly excludes API/assets; an unknown private route must stay a 404.
    distribution = web_dist or Path(os.getenv('GUIDE2BUILD_WEB_DIST', str(ROOT / 'apps/web/dist')))
    if distribution.is_dir():
        @app.get('/{path:path}')
        def frontend(path: str):
            if path.startswith(('api/', 'assets-local/', 'published-assets/')):
                error(404, 'not_found', 'Not found.')
            target = (distribution / path).resolve()
            if not target.is_relative_to(distribution.resolve()):
                error(404, 'not_found', 'Not found.')
            if target.is_file():
                return FileResponse(target)
            if Path(path).suffix:
                error(404, 'not_found', 'Not found.')
            return FileResponse(distribution / 'index.html')
    return app


app = create_app()
