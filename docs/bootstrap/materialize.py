"""Restore the bundled starter without network access or overwriting existing files.

Usage (Python 3.11+): python3 docs/bootstrap/materialize.py [--dry-run]
Run only a bundle you trust. This writes source files; it does not execute them.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(base: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or any(p in {".", ".."} for p in relative.split("/")) or "\\" in relative:
        raise ValueError(f"Unsafe bundle path: {relative!r}")
    candidate = base.joinpath(*path.parts)
    current = base
    for component in path.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"Refusing symlink path: {current}")
    if not candidate.resolve().is_relative_to(base.resolve()):
        raise ValueError(f"Path escapes project: {relative}")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    root = folder.parents[1]
    template = folder / "template"
    try:
        if template.is_symlink() or not template.is_dir():
            raise ValueError("Missing or symlinked bootstrap template")
        manifest = json.loads((folder / "manifest.json").read_text())
        if manifest.get("version") != 1 or not isinstance(manifest.get("files"), list):
            raise ValueError("Unsupported bootstrap manifest")
        planned: list[tuple[Path, bytes, int]] = []
        conflicts: list[str] = []
        seen: set[str] = set()
        identical = 0
        for record in manifest["files"]:
            relative = record["path"]
            if relative in seen:
                raise ValueError(f"Duplicate manifest path: {relative}")
            seen.add(relative)
            source = safe_path(template, relative)
            target = safe_path(root, relative)
            data = source.read_bytes()
            if digest(data) != record["sha256"] or len(data) != record["bytes"]:
                raise ValueError(f"Bundle integrity failure: {relative}")
            mode = record.get("mode", 0o644)
            if mode not in {0o644, 0o755}:
                raise ValueError(f"Unsafe file mode: {relative}")
            if os.path.lexists(target):
                if not target.is_file() or target.read_bytes() != data:
                    conflicts.append(relative)
                else:
                    identical += 1
            else:
                if any(p.exists() and not p.is_dir() for p in target.parents if p != root.parent):
                    raise ValueError(f"Non-directory parent: {relative}")
                planned.append((target, data, mode))
        if conflicts:
            print("CONFLICT: no files written. Preserve or merge these existing files:")
            for relative in conflicts:
                print(f"  {relative}")
            return 2
        if args.dry_run:
            print(f"DRY RUN: {len(planned)} missing files; {identical} identical; no writes.")
            return 0
        for target, data, mode in planned:
            # Recheck symlinks and exclusive create to avoid overwriting a concurrent edit.
            safe_path(root, target.relative_to(root).as_posix())
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(data)
            target.chmod(mode)
        print(f"Materialized {len(planned)} files; left {identical} identical files unchanged.")
        print("Read AGENTS.md and docs/prompts/BUILD_V1.md. No dependencies installed or external calls made.")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
