import json
import hashlib
from types import SimpleNamespace

import pytest

from guide2build.engine import geometry


def test_assembly_fetch_keeps_per_design_budget_and_prior_receipts(tmp_path, monkeypatch):
    calls = []

    def fetch(parts, directory):
        assert len(parts) == 1
        calls.append(parts[0])
        (directory / "provenance.json").write_text(json.dumps({"resources": {
            f"parts/{parts[0]}.dat": {"bytes": 10, "sha256": parts[0]}},
            "file_map": {f"{parts[0]}.dat": f"parts/{parts[0]}.dat"}}))

    def materials(directory):
        return None

    loader = SimpleNamespace(exec_module=lambda module: None)
    monkeypatch.setattr(geometry.importlib.util, "spec_from_file_location", lambda *args: SimpleNamespace(loader=loader))
    monkeypatch.setattr(geometry.importlib.util, "module_from_spec", lambda spec:
        SimpleNamespace(fetch_parts=fetch, fetch_materials=materials))
    monkeypatch.setattr(geometry, "verify_assets", lambda *args: {"status": "synthetic_test_only"})
    monkeypatch.setattr(geometry, "verify_individual_assets", lambda *args: {"status": "synthetic_test_only"})
    instances = [SimpleNamespace(part_id=str(i), geometry_ref=f"parts/{i}.dat") for i in range(520)]
    private, shared = tmp_path / "private", tmp_path / "shared"
    shared.mkdir()
    geometry.prepare_geometry(SimpleNamespace(instances=instances), private, shared)
    assert len(calls) == 520
    assert len(json.loads((private / "provenance.json").read_text())["resources"]) == 520
    # A second checkpoint uses hash-verified existing roots and fetches only its new design.
    instances.append(SimpleNamespace(part_id="521", geometry_ref="parts/521.dat"))
    geometry.prepare_geometry(SimpleNamespace(instances=instances), private, shared)
    assert calls[-1] == "521" and len(calls) == 521


def test_actual_individual_closures_scale_without_relaxing_hash_checks(tmp_path):
    records = {}
    shared = "p/synthetic-shared.dat"
    resources = {shared: "0 Original synthetic primitive\n3 16 0 0 0 20 0 0 0 0 20\n"}
    refs = [f"parts/synthetic-{index}.dat" for index in range(514)]
    for relative in refs:
        resources[relative] = "0 Original synthetic individual part\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 synthetic-shared.dat\n"
    for relative, text in resources.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        records[relative] = {"classification": "Part" if relative in refs else "Primitive",
            "url": "https://library.ldraw.org/library/official/" + relative,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "dependencies": [shared] if relative in refs else [], "bytes": target.stat().st_size}
    material = tmp_path / "LDConfig.ldr"
    material.write_text("0 Original synthetic material\n")
    (tmp_path / "provenance.json").write_text(json.dumps({"resources": records,
        "file_map": {"synthetic-shared.dat": shared}, "materials": {"LDConfig.ldr": {
            "url": "https://library.ldraw.org/library/official/LDConfig.ldr",
            "sha256": hashlib.sha256(material.read_bytes()).hexdigest()}}}))
    # The old assembly-wide verifier reproduces the real aggregate failure.
    with pytest.raises(ValueError, match="Dependency resource limit"):
        geometry.verify_assets(tmp_path, refs)
    result = geometry.verify_individual_assets(tmp_path, refs)
    assert result["individual_designs"] == 514
    assert result["reachable_geometry_files"] == 515  # Shared primitive counted once.
    assert result["geometry_bytes"] == sum((tmp_path / name).stat().st_size for name in resources)
    (tmp_path / shared).write_text("0 Tampered synthetic primitive\n")
    with pytest.raises(ValueError, match="Geometry hash mismatch"):
        geometry.verify_individual_assets(tmp_path, refs)
