"""The docs-only bootstrap must be offline, repeatable and non-destructive."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def bundle(tmp_path: Path, files: dict[str, str]) -> Path:
    folder = tmp_path / "docs" / "bootstrap"
    folder.mkdir(parents=True)
    shutil.copy2(ROOT / "docs/bootstrap/materialize.py", folder / "materialize.py")
    records = []
    for name, value in files.items():
        data = value.encode()
        file = folder / "template" / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        records.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "mode": 0o644})
    (folder / "manifest.json").write_text(json.dumps({"version": 1, "files": records}))
    return folder


def run(folder: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(folder / "materialize.py"), *args], capture_output=True, text=True)


def test_materialize_dry_run_and_idempotency(tmp_path):
    folder = bundle(tmp_path, {"README.md": "hello", ".codex/config.toml": "# config"})
    assert run(folder, "--dry-run").returncode == 0
    assert not (tmp_path / "README.md").exists()
    assert run(folder).returncode == 0
    assert (tmp_path / "README.md").read_text() == "hello"
    again = run(folder)
    assert again.returncode == 0
    assert "Materialized 0 files" in again.stdout


def test_conflict_writes_nothing(tmp_path):
    folder = bundle(tmp_path, {"README.md": "template", "new.txt": "new"})
    (tmp_path / "README.md").write_text("user work")
    result = run(folder)
    assert result.returncode == 2
    assert (tmp_path / "README.md").read_text() == "user work"
    assert not (tmp_path / "new.txt").exists()


def test_integrity_failure_writes_nothing(tmp_path):
    folder = bundle(tmp_path, {"README.md": "original"})
    (folder / "template/README.md").write_text("tampered")
    assert run(folder).returncode == 2
    assert not (tmp_path / "README.md").exists()


def test_symlink_parent_rejected(tmp_path):
    folder = bundle(tmp_path, {"apps/example.txt": "payload"})
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "apps").symlink_to(outside, target_is_directory=True)
    assert run(folder).returncode == 2
    assert not (outside / "example.txt").exists()


def test_traversal_rejected(tmp_path):
    folder = bundle(tmp_path, {"README.md": "data"})
    file = folder / "manifest.json"
    document = json.loads(file.read_text())
    document["files"][0]["path"] = "../escape.txt"
    file.write_text(json.dumps(document))
    assert run(folder).returncode == 2
    assert not (tmp_path.parent / "escape.txt").exists()
