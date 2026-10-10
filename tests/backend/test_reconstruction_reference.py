"""Reference integrity regressions. Synthetic assets below are safety fixtures only."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from guide2build.reconstruction.checks import four_step_connector_report, verify_assets
from guide2build.reconstruction.reference import build_reference

BASE = "https://library.ldraw.org/library/official/"


def asset_fixture(tmp_path):
    files = {
        "parts/3022.dat": "0 Test individual geometry safety fixture\n0 !LDRAW_ORG Part\n0 !LICENSE CC BY 4.0\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 box.dat\n",
        "p/box.dat": "0 Test primitive safety fixture\n0 !LDRAW_ORG Primitive\n0 !LICENSE CC BY 4.0\n",
        "LDConfig.ldr": "0 !LDRAW_ORG Configuration\n0 !COLOUR Test CODE 15 VALUE #FFFFFF EDGE #000000\n",
    }
    records = {}
    for path, content in files.items():
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        records[path] = {
            "url": BASE + path,
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "dependencies": ["p/box.dat"] if path == "parts/3022.dat" else [],
        }
    manifest = {
        "resources": {k: v for k, v in records.items() if k.endswith(".dat")},
        "materials": {"LDConfig.ldr": records["LDConfig.ldr"]},
        "file_map": {"box.dat": "p/box.dat"},
    }
    (tmp_path / "provenance.json").write_text(json.dumps(manifest))
    return tmp_path


def test_transitive_provenance_tamper_and_missing(tmp_path):
    root = asset_fixture(tmp_path)
    assert verify_assets(root, ["parts/3022.dat"])["reachable_geometry_files"] == 2
    dependency = root / "p/box.dat"
    dependency.write_text(dependency.read_text() + "0 tampered\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_assets(root, ["parts/3022.dat"])
    dependency.unlink()
    with pytest.raises(FileNotFoundError):
        verify_assets(root, ["parts/3022.dat"])


def test_material_tamper_rejected(tmp_path):
    root = asset_fixture(tmp_path)
    (root / "LDConfig.ldr").write_text("0 changed")
    with pytest.raises(ValueError, match="Material hash mismatch"):
        verify_assets(root, ["parts/3022.dat"])


def test_missing_receipt_rejected(tmp_path):
    root = asset_fixture(tmp_path)
    manifest = json.loads((root / "provenance.json").read_text())
    del manifest["resources"]["p/box.dat"]
    (root / "provenance.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Missing asset provenance"):
        verify_assets(root, ["parts/3022.dat"])


def test_source_candidate_counts_and_floating_connector():
    scene, items, report = build_reference()
    assert len(scene.instances) == 32
    assert {s.main_step_number for s in scene.steps} == set(range(1, 13))
    assert len([p for p in scene.instances if p.source.page_index <= 2]) == 11
    assert scene.status == "needs_review" and items["items"]
    assert report["four_step_gate"]["status"] == "needs_review"
    assert four_step_connector_report(scene)["status"] == "pass"
    attached = next(s for s in scene.steps if s.step_id == "main-04-attach")
    attached.poses["keel-left"].position_ldu = (-10, 40, 0)
    assert four_step_connector_report(scene)["status"] == "fail"


def test_attachment_preserves_rigid_group_and_physical_ids():
    scene, _, _ = build_reference()
    for n in (3, 4):
        before = next(s for s in scene.steps if s.step_id == f"main-{n:02d}-callout-2")
        after = next(s for s in scene.steps if s.step_id == f"main-{n:02d}-attach")
        assert not after.introduced_instance_ids
        translations = []
        for ident in after.active_instance_ids:
            translations.append(
                tuple(
                    a - b for a, b in zip(after.poses[ident].position_ldu, before.poses[ident].position_ldu)
                )
            )
            assert after.poses[ident].quaternion_xyzw == before.poses[ident].quaternion_xyzw
        assert len(set(translations)) == 1


def test_unreceipted_cache_cannot_be_relabelled_official(tmp_path):
    project = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project / "tools"))
    spec = importlib.util.spec_from_file_location("fetch_parts_under_test", project / "tools/fetch_parts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dest = tmp_path / "parts/3022.dat"
    dest.parent.mkdir()
    dest.write_text("0 local authored shape\n")
    with pytest.raises(ValueError, match="no matching official-origin receipt"):
        module.fetch_parts(["3022"], tmp_path)
