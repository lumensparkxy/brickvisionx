"""Transactional publication heads and bounded, deduplicated request intake."""
from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Literal
from pydantic import Field
from guide2build.core.models import StrictModel
from guide2build.releases.models import Source, canonical, digest

CATALOGUE_MAX_ENTRIES = 1000
CATALOGUE_MAX_BYTES = 500_000


class PublishedEntry(StrictModel):
    set_number: str = Field(pattern=r"^[0-9]{4,7}$")
    guide_id: str = Field(pattern=r"^[a-z0-9-]{1,80}$")
    release_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source: Source
    release_kind: Literal['unverified_alpha'] | None = None


def publication_entry(manifest):
    source = next((s for s in manifest["sources"] if s["guide_id"] == manifest["guide_id"]), manifest["sources"][0])
    return PublishedEntry.model_validate({k:manifest[k] for k in ("set_number", "guide_id", "release_sha256")}
        | {"source":source, "release_kind":manifest.get('release_kind')}).model_dump(mode="json", exclude_none=True)


def validate_catalogue(entries):
    if not isinstance(entries, list) or len(entries) > CATALOGUE_MAX_ENTRIES:
        raise ValueError("Published catalogue entry bound")
    validated = [PublishedEntry.model_validate(e).model_dump(mode="json", exclude_none=True) for e in entries]
    keys = [(e["set_number"], e["guide_id"]) for e in validated]
    if len(set(keys)) != len(keys) or len(canonical(validated)) > CATALOGUE_MAX_BYTES:
        raise ValueError("Published catalogue identity or byte bound")
    return validated


def replace_catalogue_entry(entries, entry):
    key = (entry["set_number"], entry["guide_id"])
    result = [e for e in entries if (e["set_number"], e["guide_id"]) != key] + [entry]
    return validate_catalogue(sorted(result, key=lambda e:(e["set_number"], e["guide_id"])))


class RequestLimit(ValueError):
    pass


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class SQLiteReleaseStore:
    def __init__(self, path: Path, daily_cap: int = 100):
        self.path, self.daily_cap = Path(path), daily_cap
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS public_requests(set_number TEXT PRIMARY KEY, created_at TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'requested');
            CREATE TABLE IF NOT EXISTS releases(hash TEXT PRIMARY KEY, set_number TEXT NOT NULL,
              guide_id TEXT NOT NULL, manifest TEXT NOT NULL, staged_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS release_approvals(hash TEXT PRIMARY KEY, email TEXT NOT NULL,
              approved_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS release_heads(set_number TEXT, guide_id TEXT, hash TEXT NOT NULL,
              PRIMARY KEY(set_number, guide_id));
            CREATE TABLE IF NOT EXISTS public_catalogue(set_number TEXT, guide_id TEXT, hash TEXT,
              metadata TEXT NOT NULL, PRIMARY KEY(set_number, guide_id));
            CREATE TABLE IF NOT EXISTS release_events(id INTEGER PRIMARY KEY, set_number TEXT,
              guide_id TEXT, hash TEXT, action TEXT, at TEXT);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def request(self, set_number: str) -> bool:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM public_requests WHERE set_number=?', (set_number,)).fetchone():
                return True
            today = utcnow()[:10]
            count = db.execute('SELECT count(*) FROM public_requests WHERE created_at>=?', (today,)).fetchone()[0]
            if count >= self.daily_cap:
                raise RequestLimit('Daily request capacity reached')
            db.execute('INSERT INTO public_requests(set_number,created_at) VALUES(?,?)', (set_number, utcnow()))
            return False

    def requests(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM public_requests ORDER BY created_at')]

    def published_catalogue(self):
        with self.connect() as db:
            rows = db.execute("""SELECT c.metadata FROM public_catalogue c
                JOIN release_heads h ON c.set_number=h.set_number AND c.guide_id=h.guide_id AND c.hash=h.hash
                JOIN release_approvals a ON a.hash=h.hash ORDER BY c.set_number,c.guide_id""").fetchall()
            return validate_catalogue([json.loads(r[0]) for r in rows])

    def head(self, set_number, guide_id):
        with self.connect() as db:
            row = db.execute('''SELECT r.manifest FROM release_heads h JOIN releases r ON r.hash=h.hash
              JOIN release_approvals a ON a.hash=r.hash WHERE h.set_number=? AND h.guide_id=?''',
              (set_number, guide_id)).fetchone()
            return json.loads(row[0]) if row else None

    def head_info(self, set_number, guide_id):
        manifest = self.head(set_number, guide_id)
        return {k: manifest[k] for k in ('set_number', 'guide_id', 'release_sha256')} if manifest else None

    def stage(self, manifest):
        from guide2build.releases.packaging import verify_manifest
        verify_manifest(manifest)
        encoded = json.dumps(manifest, sort_keys=True)
        with self.connect() as db:
            row = db.execute('SELECT manifest FROM releases WHERE hash=?', (manifest['release_sha256'],)).fetchone()
            if row and row[0] != encoded:
                raise ValueError('Immutable release differs')
            db.execute('INSERT OR IGNORE INTO releases VALUES(?,?,?,?,?)',
                (manifest['release_sha256'], manifest['set_number'], manifest['guide_id'], encoded, utcnow()))

    def approve(self, release_hash, identity):
        identity.require_approver()
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM releases WHERE hash=?', (release_hash,)).fetchone():
                raise ValueError('Unknown staged release')
            db.execute('INSERT OR IGNORE INTO release_approvals VALUES(?,?,?)',
                       (release_hash, identity.email, utcnow()))

    def promote(self, release_hash, identity, expected_head=None):
        identity.require_approver()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT r.set_number,r.guide_id FROM releases r JOIN release_approvals a
              ON r.hash=a.hash WHERE r.hash=? AND a.email=?''', (release_hash, identity.email)).fetchone()
            if not row:
                raise ValueError('Exact release hash has no authorized approval')
            old = db.execute('SELECT hash FROM release_heads WHERE set_number=? AND guide_id=?', tuple(row)).fetchone()
            if (old[0] if old else None) != expected_head:
                raise ValueError('Stale release head')
            manifest = json.loads(db.execute('SELECT manifest FROM releases WHERE hash=?', (release_hash,)).fetchone()[0])
            from guide2build.releases.packaging import verify_manifest
            verify_manifest(manifest)
            entry = publication_entry(manifest)
            current = [json.loads(r[0]) for r in db.execute('SELECT metadata FROM public_catalogue')]
            replace_catalogue_entry(current, entry)  # fail before changing either pointer
            db.execute('INSERT OR REPLACE INTO release_heads VALUES(?,?,?)', (*tuple(row), release_hash))
            db.execute('INSERT OR REPLACE INTO public_catalogue VALUES(?,?,?,?)',
                       (*tuple(row), release_hash, json.dumps(entry)))
            db.execute('INSERT INTO release_events(set_number,guide_id,hash,action,at) VALUES(?,?,?,?,?)',
                       (*tuple(row), release_hash, 'promote', utcnow()))


class FirestoreReleaseStore:
    def __init__(self, project: str, database: str = 'guide2build', daily_cap: int = 100, credentials=None):
        if database != 'guide2build':
            raise ValueError('Dedicated guide2build database is required')
        from google.cloud import firestore
        self.fs = firestore
        self.db = firestore.Client(project=project, database=database, credentials=credentials)
        request_database = os.getenv('GUIDE2BUILD_REQUEST_DATABASE', 'guide2build-requests')
        if request_database != 'guide2build-requests':
            raise ValueError('Dedicated guide2build-requests database is required')
        self.request_db = firestore.Client(project=project, database=request_database, credentials=credentials)
        self.daily_cap = daily_cap

    def request(self, set_number):
        request = self.request_db.collection('requests').document(set_number)
        counter = self.request_db.collection('intake_days').document(utcnow()[:10])
        @self.fs.transactional
        def write(tx):
            existing, day = request.get(transaction=tx), counter.get(transaction=tx)
            if existing.exists:
                return True
            count = (day.to_dict() or {}).get('count', 0)
            if not isinstance(count, int) or count >= self.daily_cap:
                raise RequestLimit('Daily request capacity reached')
            tx.set(counter, {'count': count + 1})
            tx.create(request, {'set_number': set_number, 'created_at': utcnow(), 'status': 'requested'})
            return False
        return write(self.request_db.transaction())

    def requests(self):
        return [x.to_dict() for x in self.request_db.collection('requests').limit(1000).stream()]

    def published_catalogue(self):
        document = self.db.collection('catalogue').document('published').get()
        return validate_catalogue(document.to_dict().get('entries', [])) if document.exists else []

    def head_info(self, set_number, guide_id):
        head = self.db.collection('heads').document(f'{set_number}-{guide_id}').get()
        if not head.exists:
            return None
        value = head.to_dict()
        release = self.db.collection('releases').document(value['hash']).get()
        approval = self.db.collection('approvals').document(value['hash']).get()
        from guide2build.releases.auth import APPROVER
        if not release.exists or not approval.exists or approval.to_dict().get('email') != APPROVER:
            return None
        return release.to_dict()['identity']

    def head(self, set_number, guide_id):
        identity = self.head_info(set_number, guide_id)
        if identity is None:
            return None
        value = {'hash': identity['release_sha256']}
        from google.cloud import storage
        bucket = os.environ['GUIDE2BUILD_PUBLIC_BUCKET']
        blob = storage.Client(project=self.db.project, credentials=self.db._credentials).bucket(bucket).blob(value['hash'] + '/manifest.json')
        blob.reload()
        if not blob.size or blob.size > 32_000_000:
            raise ValueError('Manifest size limit')
        manifest = json.loads(blob.download_as_bytes(if_generation_match=blob.generation))
        from guide2build.releases.packaging import verify_manifest
        verify_manifest(manifest)
        if manifest['release_sha256'] != value['hash'] or manifest['set_number'] != set_number or manifest['guide_id'] != guide_id:
            raise ValueError('Published manifest identity mismatch')
        return manifest

    def stage(self, manifest):
        from guide2build.releases.packaging import verify_manifest
        verify_manifest(manifest)
        entry = publication_entry(manifest)
        entry_sha256 = digest(entry)
        ref = self.db.collection('releases').document(manifest['release_sha256'])
        @self.fs.transactional
        def write(tx):
            old = ref.get(transaction=tx)
            if old.exists:
                if old.to_dict()['identity'] != {k: manifest[k] for k in ('set_number', 'guide_id', 'release_sha256')}:
                    raise ValueError('Immutable release differs')
                if (old.to_dict().get('catalogue_entry') != entry
                        or old.to_dict().get('catalogue_entry_sha256') != entry_sha256):
                    tx.update(ref, {'catalogue_entry': entry, 'catalogue_entry_sha256': entry_sha256})
                return
            tx.create(ref, {'catalogue_entry': entry, 'catalogue_entry_sha256': entry_sha256,
                           'identity': {k: manifest[k] for k in ('set_number', 'guide_id', 'release_sha256')}, 'staged_at': utcnow()})
        write(self.db.transaction())

    def approve(self, release_hash, identity):
        identity.require_approver()
        if not self.db.collection('releases').document(release_hash).get().exists:
            raise ValueError('Unknown staged release')
        self.db.collection('approvals').document(release_hash).set(
            {'email': identity.email, 'approved_at': utcnow()})

    def promote(self, release_hash, identity, expected_head=None):
        identity.require_approver()
        @self.fs.transactional
        def write(tx):
            release = self.db.collection('releases').document(release_hash).get(transaction=tx)
            approval = self.db.collection('approvals').document(release_hash).get(transaction=tx)
            if not release.exists or not approval.exists or approval.to_dict().get('email') != identity.email:
                raise ValueError('Exact release hash has no authorized approval')
            manifest = release.to_dict()['identity']
            head = self.db.collection('heads').document(f"{manifest['set_number']}-{manifest['guide_id']}")
            old = head.get(transaction=tx)
            if (old.to_dict().get('hash') if old.exists else None) != expected_head:
                raise ValueError('Stale release head')
            catalogue = self.db.collection('catalogue').document('published')
            current = catalogue.get(transaction=tx)
            entries = validate_catalogue(current.to_dict().get('entries', [])) if current.exists else []
            entry = PublishedEntry.model_validate(release.to_dict()['catalogue_entry']).model_dump(mode='json', exclude_none=True)
            if digest(entry) != release.to_dict().get('catalogue_entry_sha256'):
                raise ValueError('Published metadata differs from its staged receipt')
            if any(entry[k] != manifest[k] for k in ('set_number', 'guide_id', 'release_sha256')):
                raise ValueError('Published metadata does not bind the approved release')
            entries = replace_catalogue_entry(entries, entry)
            tx.set(head, {'hash': release_hash, 'at': utcnow()})
            tx.set(catalogue, {'entries': entries, 'updated_at': utcnow()})
            tx.create(self.db.collection('release_events').document(),
                      {'hash': release_hash, 'action': 'promote', 'at': utcnow()})
        write(self.db.transaction())
