"""Original synthetic meshes test symmetry proof, not target-build accuracy."""
from copy import deepcopy
import hashlib
import json
from math import sin, cos

import pytest

from guide2build.engine import hypotheses
from guide2build.engine.perception import _part_triangles
from guide2build.engine.whole_part_symmetry import (
    AXIS_ROTATIONS, IDENTITY, relative_axis_rotation, verified_origin_symmetries,
)
from test_engine_spatial import pose, scene, step

HALF_TURN = ((-1, 0, 0), (0, 1, 0), (0, 0, -1))


@pytest.fixture
def symmetric_geometry(tmp_path):
    # A box with centred triangle fans: both 180-degree equivalence and triangle
    # multiplicity are explicit, independent of any downloaded part.
    corners = [[(-20, y, -10), (20, y, -10), (20, y, 10), (-20, y, 10)] for y in (-8, 0)]
    quads = [*corners, *[[corners[0][i], corners[0][(i+1) % 4],
                          corners[1][(i+1) % 4], corners[1][i]] for i in range(4)]]
    faces = []
    for quad in quads:
        centre = tuple(sum(point[i] for point in quad)/4 for i in range(3))
        faces.extend([(centre, quad[i], quad[(i+1) % 4]) for i in range(4)])
    records = {}
    root = tmp_path / "geometry"
    (root / "parts").mkdir(parents=True)
    # Removing one face preserves the whole vertex set and bounding box, but
    # creates an asymmetric surface. A vertex/bounds-only proof would be wrong.
    for part_id, triangles in (("101", faces), ("102", faces[1:])):
        name = f"parts/{part_id}.dat"
        content = "0 Original synthetic Part\n" + "\n".join(
            "3 16 " + " ".join(str(value) for point in face for value in point) for face in triangles) + "\n"
        data = content.encode()
        (root / name).write_bytes(data)
        records[name] = {"classification": "Part", "url": "https://library.ldraw.org/library/official/"+name,
                         "sha256": hashlib.sha256(data).hexdigest(), "dependencies": []}
    material = b"0 Original synthetic material fixture\n"
    (root / "LDConfig.ldr").write_bytes(material)
    (root / "provenance.json").write_text(json.dumps({"resources": records, "file_map": {},
        "materials": {"LDConfig.ldr": {"url": "https://library.ldraw.org/library/official/LDConfig.ldr",
                                      "sha256": hashlib.sha256(material).hexdigest()}}}))
    return root


def test_exact_complete_triangles_prove_finite_proper_symmetry(symmetric_geometry):
    proof = verified_origin_symmetries(symmetric_geometry, "parts/101.dat")
    assert proof["rotations_checked"] == 24 == len(AXIS_ROTATIONS)
    assert HALF_TURN in proof["rotations"] and IDENTITY in proof["rotations"]
    assert proof["triangle_count"] == 24
    assert proof["geometry_files"] == {"parts/101.dat": hashlib.sha256((symmetric_geometry / "parts/101.dat").read_bytes()).hexdigest()}
    assert proof["mesh_comparison"] == "exact_triangle_multiset_including_multiplicity_no_rounding"


def test_same_bounds_and_vertex_set_cannot_certify_asymmetric_surface(symmetric_geometry):
    symmetric, _ = _part_triangles(symmetric_geometry, "101")
    asymmetric, _ = _part_triangles(symmetric_geometry, "102")
    assert {p for f in symmetric for p in f} == {p for f in asymmetric for p in f}
    proof = verified_origin_symmetries(symmetric_geometry, "parts/102.dat")
    assert HALF_TURN not in proof["rotations"]


def test_relative_pose_requires_same_origin_and_a_proper_axis_rotation():
    half_turn = {**pose(), "quaternion_xyzw": [0, 1, 0, 0]}
    assert relative_axis_rotation(pose(), half_turn) == HALF_TURN
    assert relative_axis_rotation(pose(), {**half_turn, "position_ldu": [1e-9, 0, 0]}) is None
    assert relative_axis_rotation(pose(), {**pose(), "quaternion_xyzw": [0, sin(.15), 0, cos(.15)]}) is None
    assert relative_axis_rotation(pose(), {**pose(), "quaternion_xyzw": [0, 0, 0, -1]}) == IDENTITY
    assert all(round(sum(matrix[0][i] * (matrix[1][(i+1) % 3]*matrix[2][(i+2) % 3]
                       - matrix[1][(i+2) % 3]*matrix[2][(i+1) % 3]) for i in range(3))) == 1 for matrix in AXIS_ROTATIONS)


def test_symmetry_diagnostic_does_not_merge_designs_or_detached_workspaces(symmetric_geometry, monkeypatch):
    monkeypatch.setattr(hypotheses, "load_connector_catalogue", lambda *_: ({"tolerance_ldu": .05}, {}))
    half_turn = {**pose(), "quaternion_xyzw": [0, 1, 0, 0]}
    raw = scene({"base": "101", "duplicate": "101", "other-design": "102", "detached": "101"}, [
        step("main", {"base": pose(), "duplicate": half_turn, "other-design": half_turn},
             ["base", "duplicate", "other-design"]),
        step("callout", {"detached": half_turn}, ["detached"], action="build_subassembly", group="loose")])
    before = raw.model_dump(mode="json")
    report = hypotheses.diagnose_candidate(raw, None, symmetric_geometry)
    duplicates = [f for f in report["findings"] if f["code"] == "symmetric_coincident_geometry"]
    assert duplicates and all(f["instance_ids"] == ["base", "duplicate"] for f in duplicates)
    assert report["symmetry"]["geometry_receipts"][0]["geometry_ref"] == "parts/101.dat"
    assert raw.model_dump(mode="json") == before
    assert report["checks"]["physical"] == report["checks"]["narrow_phase"] == "not_run"


def test_symmetry_tamper_is_hard_and_not_reused_from_previous_audit(symmetric_geometry, monkeypatch):
    verified_origin_symmetries(symmetric_geometry, "parts/101.dat")
    (symmetric_geometry / "parts/101.dat").write_text("tampered")
    with pytest.raises(ValueError, match="hash"):
        verified_origin_symmetries(symmetric_geometry, "parts/101.dat")
    monkeypatch.setattr(hypotheses, "load_connector_catalogue", lambda *_: ({"tolerance_ldu": .05}, {}))
    raw = scene({"a": "101", "b": "101"}, [step("main", {
        "a": pose(), "b": {**pose(), "quaternion_xyzw": [0, 1, 0, 0]}}, ["a", "b"])])
    with pytest.raises(ValueError, match="hash"):
        hypotheses.diagnose_candidate(raw, None, symmetric_geometry)


def test_symmetry_limits_and_untrusted_classification(symmetric_geometry):
    for reference, bound in (("../101.dat", 10), ("parts/101.dat", 20_001), ("parts/101.dat", True)):
        with pytest.raises(ValueError, match="scope or face budget"):
            verified_origin_symmetries(symmetric_geometry, reference, max_faces=bound)
    limited = verified_origin_symmetries(symmetric_geometry, "parts/101.dat", max_faces=3)
    assert limited["status"] == "unknown_face_limit" and not limited["rotations"]
    path = symmetric_geometry / "provenance.json"
    record = deepcopy(json.loads(path.read_text()))
    record["resources"]["parts/101.dat"]["classification"] = "Model"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="real individual Part"):
        verified_origin_symmetries(symmetric_geometry, "parts/101.dat")


def test_whole_part_pair_budget_is_bounded_and_explicit(symmetric_geometry, monkeypatch):
    monkeypatch.setattr(hypotheses, "load_connector_catalogue", lambda *_: ({"tolerance_ldu": .05}, {}))
    monkeypatch.setattr(hypotheses, "MAX_SYMMETRY_PAIRS", 2)
    poses = {"a": pose(), "b": {**pose(), "quaternion_xyzw": [0, 1, 0, 0]},
             "c": pose(), "d": {**pose(), "quaternion_xyzw": [0, 1, 0, 0]}}
    raw = scene(dict.fromkeys(poses, "101"), [step("main", poses, list(poses))])
    report = hypotheses.diagnose_candidate(raw, None, symmetric_geometry)
    assert report["symmetry"]["pairs_considered"] == 2
    assert report["symmetry"]["pairs_omitted"] == 4
    assert report["coverage"]["status"] == "partial"
    assert "symmetry_diagnostic_limit" in {f["code"] for f in report["findings"]}


def test_geometry_symlink_cannot_become_a_symmetry_receipt(symmetric_geometry):
    path = symmetric_geometry / "parts/101.dat"
    other = symmetric_geometry / "copy.dat"
    other.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(other)
    with pytest.raises(ValueError, match="path|Unsafe|escape|symlink"):
        verified_origin_symmetries(symmetric_geometry, "parts/101.dat")
