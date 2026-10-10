"""Validate local source/config packaging; not a build or rendering test."""
from __future__ import annotations
import ast
import hashlib
import json
import re
import sys
import tomllib
from _paths import ROOT

IGNORED = {"node_modules", ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist"}


def main() -> int:
    count = {"python": 0, "json": 0, "toml": 0, "skills": 0, "template": 0}
    errors: list[str] = []
    for file in ROOT.rglob("*"):
        relative = file.relative_to(ROOT)
        if not file.is_file() or any(part in IGNORED for part in relative.parts) or "template" in relative.parts:
            continue
        try:
            if file.suffix == ".py":
                ast.parse(file.read_text(), filename=str(relative))
                count["python"] += 1
            elif file.suffix == ".json":
                json.loads(file.read_text())
                count["json"] += 1
            elif file.suffix == ".toml":
                tomllib.loads(file.read_text())
                count["toml"] += 1
            elif file.name == "SKILL.md":
                text = file.read_text()
                if not text.startswith("---\n"):
                    raise ValueError("Missing skill metadata")
                metadata = text.split("---", 2)[1]
                if not re.search(r"^name:\s*\S+", metadata, re.M) or not re.search(r"^description:\s*\S+", metadata, re.M):
                    raise ValueError("Missing name/description")
                count["skills"] += 1
        except (ValueError, SyntaxError) as error:
            errors.append(f"{relative}: {error}")
    folder = ROOT / "docs/bootstrap"
    if not (folder / "manifest.json").exists():
        errors.append("Bootstrap manifest is missing")
    else:
        manifest = json.loads((folder / "manifest.json").read_text())
        for row in manifest["files"]:
            file = folder / "template" / row["path"]
            try:
                data = file.read_bytes()
                if hashlib.sha256(data).hexdigest() != row["sha256"] or len(data) != row["bytes"]:
                    raise ValueError("hash/size mismatch")
                count["template"] += 1
            except (OSError, ValueError) as error:
                errors.append(f"template/{row['path']}: {error}")
    for number in range(16):
        if not list((ROOT / "docs").glob(f"{number:02d}_*.md")):
            errors.append(f"Missing numbered document {number:02d}")
    for message in errors:
        print("FAIL:", message, file=sys.stderr)
    print(json.dumps({"status": "failed" if errors else "passed", "checked": count}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
