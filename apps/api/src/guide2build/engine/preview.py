"""Private, read-only engine candidate transport. No publication or review authority."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import sqlite3
import threading
from contextlib import closing
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from ..catalog import ROOT, find_guide, find_set
from ..jobs.source_cache import cached_receipt
from ..releases.models import SceneV2, canonical, digest
from ..releases.packaging import compact_step_index, geometry_closure
from ..source_limits import MAX_BYTES
from .checkpoint_artifacts import checkpoint_artifact_stat, hydrate_checkpoint
from .quality import quality_summary


def confined_path(root: Path, relative: str, limit: int) -> Path:
    """Reject symlinks at any path component, traversal, and oversized assets."""
    if root.resolve() != root:
        raise ValueError('Unsafe preview root')
    target = root / relative
    if (not relative or '\\' in relative or Path(relative).is_absolute()
            or '..' in Path(relative).parts or target.resolve() != target
            or not target.resolve().is_relative_to(root) or not target.is_file()
            or target.stat().st_size > limit):
        raise ValueError('Unavailable or unsafe preview asset')
    return target


def confined_bytes(root: Path, relative: str, limit: int) -> bytes:
    return confined_path(root, relative, limit).read_bytes()


def _file_identity(path: Path) -> tuple[int, ...]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _uncertainty_text(note) -> str | None:
    if isinstance(note, str):
        return note
    if not isinstance(note, dict):
        return None
    text = note.get('reason') or note.get('message') or note.get('description')
    if not isinstance(text, str):
        return None
    resolution = note.get('resolution')
    return f'{text} {resolution}' if isinstance(resolution, str) and resolution else text


def exploration_status(config: dict, checkpoint: dict) -> dict | None:
    """Expose bounded, plain-text diagnostics without private proposal paths."""
    from .repair_feedback import compact_feedback
    if config.get('execution_policy', 'strict') != 'explore':
        return None
    records = checkpoint.get('instruction_results', [])
    if isinstance(records, dict):
        records = list(records.values())
    instructions = []
    for record in records[:4096]:
        panel = record.get('panel', {})
        findings = record.get('findings', [])
        plain = [({'description': item} if isinstance(item, str) else item)
                 for item in findings if isinstance(item, (str, dict))]
        focused = compact_feedback(plain, record.get('step_ids', []), input_truncated=None)
        clean = []
        for group in focused['findings']:
            finding = group['finding']
            message = str(finding.get('description', finding.get('message', finding.get('reason', 'Needs inspection'))))[:2000]
            if group['occurrence_count'] > 1:
                message += f" (Recorded {group['occurrence_count']} times.)"
            clean.append({'category': str(finding.get('category', finding.get('code', 'quality')))[:100],
                          'message': message[:2000],
                          'instance_ids': [str(v)[:160] for v in group['instance_ids']],
                          'step_ids': [str(v)[:160] for v in group['step_ids']]})
        instructions.append({'ordinal': int(record.get('ordinal', len(instructions))),
                             'main_step_number': panel.get('number', record.get('main_step_number')),
                             'page_index': int(record.get('page_index', 0)),
                             'step_ids': [str(v)[:160] for v in record.get('step_ids', [])[:256]],
                             'reconstructed': bool(record.get('reconstructed', record.get('step_ids'))),
                             'needs_recheck': bool(record.get('checks_invalidated')),
                             'finding_count': len(findings), 'findings': clean})
    return {'processed_panels': checkpoint.get('processed_panels', len(instructions)),
            'reconstructed_panels': checkpoint.get('reconstructed_panels', 0),
            'model_calls_used': checkpoint.get('model_calls_used', 0),
            'max_model_calls': config.get('max_model_calls', 100),
            'instructions': instructions}


class _CandidatePreview:
    def __init__(self, data_dir: Path, db: Path, job_id: str, verified_sources: dict):
        self.data_dir, self.db, self.job_id = data_dir, db, job_id
        self.directory = data_dir / 'engine/jobs' / job_id
        self.snapshots: dict[str, tuple[dict, dict[str, bytes]]] = {}
        self.verified_sources = verified_sources
        self._cache_lock = threading.RLock()
        self._job_cache = None
        self._scene_cache = None
        self._exploration_cache = None
        self._checkpoint_storage = None
        self._checkpoint_stat = None
        selected = self.job()
        self.set_number, self.guide_id = selected['set_number'], selected['guide_id']
        self.guide = find_guide(self.set_number, self.guide_id)

    def job(self):
        # SQLite's main file and WAL identities change on committed writes,
        # including updates that do not touch the engine's updated timestamp.
        # Avoid parsing megabytes of unchanged checkpoint poses on each poll.
        with self._cache_lock:
            files = (self.db, self.db.with_name(self.db.name + '-wal'))
            identity = tuple(_file_identity(path) if path.exists() else None for path in files)
            if self._job_cache is not None and self._job_cache[0] == identity:
                artifact = checkpoint_artifact_stat(self.db.parent, self.job_id, self._job_cache[2])
                if artifact == self._job_cache[3]:
                    return self._job_cache[1]
            value = self._read_job()
            after = tuple(_file_identity(path) if path.exists() else None for path in files)
            if after == identity:
                self._job_cache = identity, value, self._checkpoint_storage, self._checkpoint_stat
            return value

    def _read_job(self):
        with closing(sqlite3.connect(self.db.as_uri() + '?mode=ro', uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute('SELECT * FROM engine_jobs WHERE id=?', (self.job_id,)).fetchone()
        if row is None:
            raise ValueError('Engine job does not exist')
        value = dict(row)
        for key in ('config', 'error'):
            value[key] = json.loads(value[key]) if value[key] else None
        stored = value['checkpoint']
        before = checkpoint_artifact_stat(self.db.parent, self.job_id, stored)
        value['checkpoint'] = hydrate_checkpoint(self.db.parent, self.job_id, stored)
        after = checkpoint_artifact_stat(self.db.parent, self.job_id, stored)
        if after != before:
            raise ValueError('Checkpoint candidate changed during preview verification')
        self._checkpoint_storage, self._checkpoint_stat = stored, after
        return value

    def _source_receipt(self, guide_id: str, official_url: str):
        source_dir = self.data_dir / 'sources' / self.set_number / guide_id
        receipt_bytes = confined_bytes(source_dir, 'source.receipt.json', 1_000_000)
        # Share ingestion's PDF bound. cached_receipt verifies the hash in a
        # stream rather than reading a large official booklet into RAM.
        pdf = confined_path(source_dir, 'source.pdf', MAX_BYTES)
        identity = (_file_identity(pdf), hashlib.sha256(receipt_bytes).hexdigest())
        key = self.set_number, guide_id, official_url
        saved = self.verified_sources.get(key)
        if saved is not None and saved[0] == identity:
            return saved[1]
        receipt = cached_receipt(self.data_dir, self.set_number, guide_id, official_url)
        if (receipt is None or _file_identity(confined_path(source_dir, 'source.pdf', MAX_BYTES)) != identity[0]
                or confined_bytes(source_dir, 'source.receipt.json', 1_000_000) != receipt_bytes):
            raise ValueError('Candidate source differs from verified cached official PDF')
        self.verified_sources[key] = identity, receipt
        return receipt

    def candidate(self, current: dict | None = None):
        current = current or self.job()
        file = confined_path(self.directory, 'scene.json', 256_000_000)
        identity = _file_identity(file)
        with self._cache_lock:
            cached = self._scene_cache
            if cached is not None and cached[0] == identity and cached[1] is current:
                scene = cached[2]
            else:
                scene = self._validate_candidate(current, file)
                if _file_identity(file) != identity:
                    raise ValueError('Candidate changed during validation')
                self._scene_cache = identity, current, scene
        # Retain live source-file checks even when the assembly is unchanged.
        for source in scene.sources:
            official = find_guide(self.set_number, source.guide_id)
            receipt = self._source_receipt(source.guide_id, official['pdf_url'])
            if receipt['sha256'] != source.source_sha256:
                raise ValueError('Candidate source differs from verified cached official PDF')
            if source.official_url != official['pdf_url'] or source.page_count != official['expected_page_count']:
                raise ValueError('Candidate source differs from curated official booklet')
        return scene

    def _validate_candidate(self, current: dict, file: Path):
        scene = SceneV2.model_validate_json(file.read_bytes())
        selected_sources = [source for source in scene.sources if source.guide_id == self.guide_id]
        # A cumulative scene retains the first booklet as its primary source.
        # The checkpoint instead binds this job's current booklet.
        if (scene.set_number != self.set_number or scene.guide_id != self.guide_id
                or digest(scene) != digest(current['checkpoint'].get('candidate'))
                or len(selected_sources) != 1
                or selected_sources[0].source_sha256 != current['checkpoint'].get('source_sha256')):
            raise ValueError('Candidate does not match the persisted job checkpoint')
        return scene

    def _exploration_status(self, current: dict):
        # The job cache replaces this object after a committed DB change. Group
        # unchanged findings once, while candidate/source checks remain live.
        with self._cache_lock:
            saved = self._exploration_cache
            if saved is None or saved[0] is not current:
                value = exploration_status(current['config'], current['checkpoint'])
                self._exploration_cache = current, value
            return deepcopy(self._exploration_cache[1])

    def status(self):
        try:
            current = self.job()
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(409, {'code': 'checkpoint_unavailable',
                'message': 'The saved candidate checkpoint is unavailable or changed. Retained evidence needs inspection.'}) from None
        checkpoint = current['checkpoint']
        available = False
        reason = revision = None
        step_count = instance_count = main_step_count = 0
        try:
            scene = self.candidate(current)
            available, revision, step_count = True, scene.revision, len(scene.steps)
            instance_count = len(scene.instances)
            main_step_count = len({(step.section_id, step.main_step_number) for step in scene.steps
                                   if step.main_step_number is not None
                                   and step.source.source_sha256 == checkpoint.get('source_sha256', scene.source_sha256)})
        except (OSError, ValueError, KeyError, TypeError):
            reason = 'No valid candidate is available from this job checkpoint yet.'
        fast = current['config'].get('generation_mode') == 'alpha_fast'
        measured = any(review.get('source_view_checks') for review in checkpoint.get('panel_reviews', []))
        notes = checkpoint.get('uncertainty_notes', [])
        # Provider notes remain plain text; they are not executable content.
        details = notes if isinstance(notes, list) else []
        notes = [text for note in details if (text := _uncertainty_text(note)) is not None]
        return {'job_id': self.job_id, 'set_number': self.set_number, 'guide_id': self.guide_id,
                'state': current['state'], 'stage': checkpoint.get('stage', 'queued'),
                'error': current['error'], 'candidate_available': available, 'candidate_message': reason,
                'revision': revision, 'experiment_revision': current['config'].get('revision'),
                'step_count': step_count, 'instance_count': instance_count, 'main_step_count': main_step_count,
                'completed_panels': main_step_count if fast else checkpoint.get('completed_panels', 0),
                'total_panels': (main_step_count if checkpoint.get('alpha_source_complete') else None)
                                if fast else checkpoint.get('total_panels'),
                'completed_pages': checkpoint.get('completed_pages', 0), 'page_count': checkpoint.get('page_count'),
                'source_coverage': checkpoint.get('source_coverage'),
                'generation_mode': 'alpha_fast' if fast else 'standard',
                'uncertainty_notes': notes, 'uncertainty_details': details,
                'repair': checkpoint.get('current_panel_attempt'),
                'image_quality': quality_summary(current['config'], checkpoint),
                'camera_alignment_check': 'measured_per_instruction' if measured and not fast else 'not_run',
                'artifact_kind': checkpoint.get('artifact_kind') or current['config'].get('artifact_kind', 'engine_candidate_preview'),
                'execution_policy': current['config'].get('execution_policy', 'strict'),
                'exploration': self._exploration_status(current),
                'publication': 'not_performed'}

    def snapshot(self):
        scene = self.candidate()
        key = digest(scene)
        if key not in self.snapshots:
            geometry = self.directory / 'geometry'
            if geometry.resolve() != geometry:
                raise ValueError('Unsafe geometry root')
            confined_bytes(geometry, 'provenance.json', 32_000_000)
            files = {'ldraw/' + path: data for path, data in
                     geometry_closure(geometry, [part.geometry_ref for part in scene.instances]).items()}
            manifest = scene.model_dump(mode='json', exclude={'steps'})
            manifest.update(reviews=[], step_index=[], chunks=[])
            base = f'/candidate-assets/{key}/'
            manifest.update(asset_base_url=base, geometry_base_url=base + 'ldraw/')
            for offset in range(0, len(scene.steps), 8):
                index = offset // 8
                steps = scene.steps[offset:offset + 8]
                path = f'chunks/{index:05d}.json'
                content = canonical({'steps': [step.model_dump(mode='json') for step in steps]})
                if len(content) > 32_000_000:
                    raise ValueError('Candidate chunk exceeds transport bound')
                files[path] = content
                manifest['chunks'].append({'index': index, 'path': path,
                    'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
                    'step_ids': [step.step_id for step in steps]})
                manifest['step_index'].extend(compact_step_index(step, index) for step in steps)
            # Viewer transport uses this digest; it is not release approval.
            manifest['release_sha256'] = digest(manifest)
            if len(self.snapshots) >= 2:
                del self.snapshots[next(iter(self.snapshots))]
            self.snapshots[key] = manifest, files
        return self.snapshots[key][0]


def create_campaign_preview_app(data_dir: Path, job_ids: list[str], frontend: Path | None = None) -> FastAPI:
    """Serve only explicitly selected jobs; never discover or mutate other jobs."""
    if (not isinstance(job_ids, list) or not job_ids or len(job_ids) > 100
            or any(not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}', identity) for identity in job_ids)
            or len(set(job_ids)) != len(job_ids)):
        raise ValueError('Select unique valid engine job identifiers (1–100)')
    data_dir = Path(data_dir).resolve()
    frontend = Path(frontend or ROOT / 'apps/web/dist').resolve()
    db = data_dir / 'engine/jobs.sqlite3'
    if db.resolve() != db or not db.is_file():
        raise ValueError('Existing engine database required')
    verified_sources: dict = {}
    previews = [_CandidatePreview(data_dir, db, identity, verified_sources) for identity in job_ids]
    by_guide = {(preview.set_number, preview.guide_id): preview for preview in previews}
    if len(by_guide) != len(previews):
        raise ValueError('Select at most one candidate per set and guide')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def local_read_only(request: Request, call_next):
        if request.url.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            return Response('Loopback preview only', status_code=403)
        if request.method not in {'GET', 'HEAD'}:
            return Response('Read-only candidate preview', status_code=405)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/api/v1/config')
    def config():
        return {'mode': 'preview', 'source_images': True, 'requests_enabled': False}

    @app.get('/api/v1/engine-preview')
    def preview_status(set_number: str | None = None, guide_id: str | None = None):
        chosen = [preview for preview in previews if (set_number is None or preview.set_number == set_number)
                  and (guide_id is None or preview.guide_id == guide_id)]
        if not chosen:
            raise HTTPException(404, 'Selected candidate unavailable')
        statuses = [preview.status() for preview in chosen]
        if len(previews) == 1 or set_number is not None and guide_id is not None:
            return statuses[0]
        return {'candidates': statuses, 'artifact_kind': 'engine_campaign_preview', 'publication': 'not_performed'}

    @app.get('/api/v1/sets/{number}')
    def get_set(number: str):
        chosen = [preview for preview in previews if preview.set_number == number]
        if not chosen:
            raise HTTPException(404, 'This preview contains only explicitly selected engine jobs.')
        info = find_set(number)
        return {'set_number': number, 'name': info['name'], 'official_page': info['official_page'],
                'guides': [{**preview.guide, 'tutorial_available': preview.status()['candidate_available']}
                           for preview in chosen]}

    @app.get('/api/v1/sets/{number}/guides/{identity}/release')
    def get_candidate(number: str, identity: str):
        preview = by_guide.get((number, identity))
        if preview is None:
            raise HTTPException(404, 'Candidate unavailable')
        try:
            return preview.snapshot()
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(409, {'code': 'candidate_not_ready', 'message': 'Candidate or verified individual geometry is not ready.'}) from None

    @app.get('/candidate-assets/{scene_hash}/{path:path}')
    def asset(scene_hash: str, path: str):
        for preview in previews:
            entry = preview.snapshots.get(scene_hash)
            if entry is not None and path in entry[1]:
                return Response(entry[1][path], media_type='application/json' if path.endswith('.json') else 'text/plain')
        raise HTTPException(404, 'Candidate asset unavailable')

    @app.get('/api/v1/sources/{source_hash}/pages/{page_index}')
    def source_page(source_hash: str, page_index: int):
        try:
            if not re.fullmatch(r'[a-f0-9]{64}', source_hash):
                raise ValueError('Unselected source')
            selected_source = None
            for preview in previews:
                try:
                    selected_source = next((s for s in preview.candidate().sources if s.source_sha256 == source_hash), None)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                if selected_source is not None:
                    break
            if selected_source is None or not 0 <= page_index < selected_source.page_count:
                raise ValueError('Unselected source')
            root = data_dir / 'public/pages'
            records = json.loads(confined_bytes(root, f'{source_hash}/pages.json', 8_000_000))
            name = f'page-{page_index:03d}.png'
            matches = [row for row in records if row.get('page_index') == page_index and row.get('file') == name]
            data = confined_bytes(root, f'{source_hash}/{name}', 32_000_000)
            if len(matches) != 1 or hashlib.sha256(data).hexdigest() != matches[0]['sha256']:
                raise ValueError('Source page receipt mismatch')
            return Response(data, media_type='image/png')
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(404, 'Verified source page unavailable') from None

    @app.get('/{path:path}')
    def frontend_asset(path: str):
        if path and not path.startswith(('assets/', 'images/', 'fonts/')):
            raise HTTPException(404, 'Unavailable')
        try:
            data = confined_bytes(frontend, path or 'index.html', 16_000_000)
        except (OSError, ValueError):
            raise HTTPException(404, 'Build the local frontend before opening preview.') from None
        return Response(data, media_type=mimetypes.guess_type(path or 'index.html')[0] or 'application/octet-stream')

    return app


def create_preview_app(data_dir: Path, job_id: str, frontend: Path | None = None) -> FastAPI:
    return create_campaign_preview_app(data_dir, [job_id], frontend)
