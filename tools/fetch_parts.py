"""Fetch curated individual LDraw parts plus bounded primitive/subpart dependencies.
Never accepts or downloads a finished assembly. Original DAT notices are preserved.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx
from _paths import ROOT

BASE = "https://library.ldraw.org/library/official/"
SAFE = re.compile(r"^(parts/(?:s/)?|p/(?:8/|48/)?)[a-z0-9_-]+\.dat$")
MAX_FILES, MAX_BYTES, MAX_DEPTH = 512, 20_000_000, 24


def references(content: str) -> list[str]:
    result = []
    for line in content.splitlines():
        fields = line.split(maxsplit=14)
        if fields and fields[0] == "1":
            if len(fields) != 15:
                raise ValueError("Malformed LDraw reference")
            name = fields[14].lower().replace("\\", "/")
            if not re.fullmatch(r"(?:s/|48/|8/)?[a-z0-9_-]+\.dat", name):
                raise ValueError("Unsafe LDraw dependency")
            result.append(name)
    return sorted(set(result))


def fetch_parts(part_ids: list[str], directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    prior_file = directory / "provenance.json"
    prior_document = json.loads(prior_file.read_text()) if prior_file.exists() else {}
    prior = prior_document.get("resources", {})
    records, visiting = {}, set()
    total = 0
    deadline = time.monotonic() + 300
    with httpx.Client(timeout=30, follow_redirects=False, headers={"Accept-Encoding": "identity"}) as client:

        def obtain(path: str, depth: int = 0) -> str:
            nonlocal total
            if time.monotonic() > deadline:
                raise ValueError("Part fetch wall-time limit exceeded")
            if not SAFE.fullmatch(path) or depth > MAX_DEPTH:
                raise ValueError("Unsafe path or excessive dependency depth")
            if path in visiting:
                raise ValueError("Dependency cycle")
            if path in records:
                return path
            target = directory / path
            if target.is_symlink() or not target.resolve().is_relative_to(directory.resolve()):
                raise ValueError("Asset path escapes root")
            if target.exists():
                if path not in prior or prior[path].get("url") != BASE + path:
                    raise ValueError(
                        "Cached asset has no matching official-origin receipt; preserve it for inspection"
                    )
                if target.stat().st_size > 1_000_000:
                    raise ValueError("Cached resource exceeds byte limit")
                data = target.read_bytes()
                if path in prior and hashlib.sha256(data).hexdigest() != prior[path]["sha256"]:
                    raise ValueError("Cached asset hash differs from receipt")
            else:
                for attempt in range(3):
                    time.sleep(0.4)
                    with client.stream("GET", BASE + path) as response:
                        if response.status_code == 429 and attempt < 2:
                            raw_delay = response.headers.get("retry-after", "10")
                            delay = int(raw_delay) if raw_delay.isdigit() else 10
                            time.sleep(min(30, max(10, delay)))
                            continue
                        response.raise_for_status()
                        if response.headers.get("content-encoding", "identity").lower() != "identity":
                            raise ValueError("Compressed part responses are not accepted")
                        chunks, size = [], 0
                        for chunk in response.iter_bytes():
                            if time.monotonic() > deadline:
                                raise ValueError("Part fetch wall-time limit exceeded")
                            size += len(chunk)
                            if size > 1_000_000:
                                raise ValueError("Individual resource exceeds byte limit")
                            chunks.append(chunk)
                        data = b"".join(chunks)
                        break
            content = data.decode("utf-8-sig")
            match = re.search(r"^0 !LDRAW_ORG (\S+)", content, re.M)
            if not match or match[1] not in {"Part", "Subpart", "Primitive", "8_Primitive", "48_Primitive"}:
                raise ValueError(f"Unapproved LDraw classification: {path}")
            if depth == 0 and match[1] != "Part":
                raise ValueError("A physical root must be a Part")
            if not re.search(r"^0 !LICENSE ", content, re.M):
                raise ValueError("Asset lacks a license notice")
            total += len(data)
            if total > MAX_BYTES or len(records) + len(visiting) >= MAX_FILES:
                raise ValueError("Dependency resource limit exceeded")
            visiting.add(path)
            deps = []
            for name in references(content):
                options = ["parts/" + name] if name.startswith("s/") else ["p/" + name, "parts/" + name]
                options.sort(key=lambda option: not (directory / option).exists())
                for option in options:
                    try:
                        deps.append(obtain(option, depth + 1))
                        break
                    except httpx.HTTPStatusError as error:
                        if error.response.status_code != 404 or option == options[-1]:
                            raise
            visiting.remove(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".partial")
            temporary.write_bytes(data)
            temporary.replace(target)
            records[path] = {
                "url": BASE + path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "classification": match[1],
                "description": content.splitlines()[0][2:],
                "notices": [
                    line
                    for line in content.splitlines()
                    if line.startswith(("0 Author:", "0 !LICENSE", "0 !HISTORY"))
                ],
                "dependencies": deps,
            }
            return path

        for part_id in part_ids:
            if not re.fullmatch(r"[a-z0-9]+", part_id):
                raise ValueError("Invalid curated part ID")
            obtain(f"parts/{part_id}.dat")
    manifest = {
        "library": BASE,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "scope": "individual parts and their primitives/subparts only",
        "roots": part_ids,
        "resources": records,
        "file_map": {path.removeprefix("parts/").removeprefix("p/"): path for path in records},
        "materials": prior_document.get("materials", {}),
    }
    (directory / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest



def stage_individual(part_id, stage, verified_caches, check=lambda: None, *, stage_budget=None):
    """Opt-in unpublished read-through acquisition; legacy fetch_parts is unchanged."""
    from guide2build.reconstruction.individual_closure import closure
    with httpx.Client(timeout=30, follow_redirects=False, headers={"Accept-Encoding": "identity"}) as client:
        def acquire(path, deadline, tick):
            if not SAFE.fullmatch(path):
                raise ValueError("Unsafe individual resource path")
            for attempt in range(3):
                tick()
                time.sleep(0.4)
                with client.stream("GET", BASE + path) as response:
                    if str(response.url) != BASE + path or str(response.request.url) != BASE + path:
                        raise ValueError("Unexpected individual response origin")
                    if response.status_code == 429 and attempt < 2:
                        raw_delay = response.headers.get("retry-after", "10")
                        delay = int(raw_delay) if raw_delay.isdigit() else 10
                        time.sleep(min(30, max(10, delay)))
                        continue
                    response.raise_for_status()
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ValueError("Compressed part responses are not accepted")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        tick()
                        size += len(chunk)
                        if size > 1_000_000:
                            raise ValueError("Individual resource exceeds byte limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
            raise RuntimeError("Bounded individual acquisition returned no response")
        return closure(part_id, stage, verified_caches, acquire, references, check, stage_budget=stage_budget)


def fetch_materials(directory: Path) -> dict:
    destination = directory / "LDConfig.ldr"
    manifest_path = directory / "provenance.json"
    manifest = json.loads(manifest_path.read_text())
    url = BASE + "LDConfig.ldr"
    prior = manifest.get("materials", {}).get("LDConfig.ldr")
    if destination.exists():
        if destination.is_symlink() or not prior or prior.get("url") != url:
            raise ValueError("Material configuration lacks a trusted receipt")
        if destination.stat().st_size > 1_000_000:
            raise ValueError("Cached material configuration exceeds byte limit")
        data = destination.read_bytes()
        if hashlib.sha256(data).hexdigest() != prior["sha256"]:
            raise ValueError("Material configuration hash mismatch")
        return prior
    deadline = time.monotonic() + 45
    with httpx.Client(timeout=30, follow_redirects=False, headers={"Accept-Encoding": "identity"}) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Compressed material responses are not accepted")
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 1_000_000 or time.monotonic() > deadline:
                    raise ValueError("Material configuration resource limit")
                chunks.append(chunk)
    data = b"".join(chunks)
    content = data.decode("utf-8-sig")
    if "0 !LDRAW_ORG Configuration" not in content or "0 !COLOUR" not in content:
        raise ValueError("Not an LDraw colour configuration")
    # This upstream configuration has authorship/update notices but no LICENSE line.
    # Retain actual notices; do not manufacture a file-specific license declaration.
    record = {
        "url": url,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "notices": [
            line
            for line in content.splitlines()
            if line.startswith(("0 Author:", "0 !LICENSE", "0 !LDRAW_ORG"))
        ],
        "license_notice_in_file": "0 !LICENSE" in content,
        "legal_reference": "https://www.ldraw.org/legal-info",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = destination.with_suffix(".partial")
    temporary.write_bytes(data)
    temporary.replace(destination)
    manifest.setdefault("materials", {})["LDConfig.ldr"] = record
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts", nargs="+")
    args = parser.parse_args()
    catalog = json.loads((ROOT / "config/parts-30669-alt-02.json").read_text())
    selected = args.parts or [part["part_id"] for part in catalog["parts"]]
    result = fetch_parts(selected, ROOT / "var/public/ldraw")
    fetch_materials(ROOT / "var/public/ldraw")
    if args.parts is None:
        for section in ("resource_sha256", "material_sha256"):
            for relative, digest in catalog[section].items():
                if hashlib.sha256((ROOT / "var/public/ldraw" / relative).read_bytes()).hexdigest() != digest:
                    raise ValueError(
                        "Current official asset differs from pinned reference; review before use"
                    )
    print(json.dumps({"roots": result["roots"], "resources": len(result["resources"])}))


if __name__ == "__main__":
    main()
