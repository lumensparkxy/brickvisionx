"""Invocation-local catalogue reuse with an unconditional filesystem exit fence.

Only a hypothesis search installs this scope. It retains small parsed catalogues
and file identities, never a process-wide trusted geometry cache. Every observed
input is checked again before any result (including a raw fallback) can escape.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from pathlib import Path
import stat


# The assembly asset union already has an 8192-file / 256 MB boundary. Allow the
# two bounded JSON inputs in addition; neither geometry bytes nor meshes persist.
MAX_FILES = 8194
MAX_BYTES = 268_000_000
MAX_CATALOGUES = 4
_ACTIVE = ContextVar("hypothesis_catalogue_verification", default=None)


def _identity(path):
    """Bind replacement/rename/symlink changes, without directory mtime noise."""
    resolved = path.resolve(strict=True)
    entry = path.lstat()
    if not stat.S_ISREG(entry.st_mode):
        raise ValueError("Verified catalogue input is not a regular file")
    ancestors = []
    for parent in dict.fromkeys([*path.parents, *resolved.parents]):
        value = parent.lstat()
        ancestors.append((str(parent), value.st_dev, value.st_ino, value.st_mode,
                          str(parent.readlink()) if stat.S_ISLNK(value.st_mode) else None))
    return (str(resolved), entry.st_dev, entry.st_ino, entry.st_mode,
            entry.st_size, entry.st_mtime_ns, entry.st_ctime_ns, tuple(ancestors))


@dataclass(frozen=True)
class _ObservedFile:
    identity: tuple
    sha256: str
    size: int
    bound: int


class _Verification:
    def __init__(self):
        self.files = {}
        self.catalogues = {}
        self.byte_count = 0
        self.closed = False

    def _live(self):
        if self.closed:
            raise ValueError("Hypothesis verification scope is closed")

    def read(self, path, bound):
        self._live()
        path = Path(path).absolute()
        before = _identity(path)
        if before[4] > bound:
            raise ValueError("Verified catalogue input exceeds its byte bound")
        with path.open("rb") as stream:
            data = stream.read(bound + 1)
        if len(data) > bound or _identity(path) != before:
            raise ValueError("Verified catalogue inputs changed during hypothesis search")
        observed = _ObservedFile(before, hashlib.sha256(data).hexdigest(), len(data), bound)
        previous = self.files.get(path)
        if previous is not None:
            if (observed.identity, observed.sha256) != (previous.identity, previous.sha256):
                raise ValueError("Verified catalogue inputs changed during hypothesis search")
        else:
            if len(self.files) >= MAX_FILES or self.byte_count + len(data) > MAX_BYTES:
                raise ValueError("Hypothesis verification resource limit exceeded")
            self.files[path] = observed
            self.byte_count += len(data)
        return data

    def catalogue(self, key, load):
        self._live()
        if key not in self.catalogues:
            if len(self.catalogues) >= MAX_CATALOGUES:
                raise ValueError("Hypothesis catalogue scope limit exceeded")
            self.catalogues[key] = load()
        # Solver/diagnostic callers can never alter a subsequent candidate's
        # catalogue, even when a future implementation mutates its local values.
        return deepcopy(self.catalogues[key])

    def verify_unchanged(self):
        self._live()
        for path, observed in self.files.items():
            try:
                if _identity(path) != observed.identity:
                    raise ValueError("File or path identity changed")
                with path.open("rb") as stream:
                    data = stream.read(observed.bound + 1)
                if (len(data) != observed.size or hashlib.sha256(data).hexdigest() != observed.sha256
                        or _identity(path) != observed.identity):
                    raise ValueError("File bytes or identity changed")
            except (OSError, RuntimeError, ValueError) as error:
                raise ValueError("Verified catalogue inputs changed during hypothesis search") from error

    def close(self):
        self.closed = True
        self.catalogues.clear()
        self.files.clear()


def current_verification():
    return _ACTIVE.get()


@contextmanager
def catalogue_verification_scope():
    verification = _Verification()
    token = _ACTIVE.set(verification)
    try:
        yield
    finally:
        try:
            verification.verify_unchanged()
        finally:
            verification.close()
            _ACTIVE.reset(token)
