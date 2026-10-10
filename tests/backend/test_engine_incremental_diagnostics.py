"""Prefix reuse is an optimization, never a reduced diagnostic contract."""
from contextlib import contextmanager, nullcontext
from contextvars import copy_context
from copy import deepcopy
import hashlib
import json

import pytest

from guide2build.engine import diagnostic_reuse, hypotheses, verification_cache
from guide2build.releases.models import canonical
from test_engine_connectors import fixture_catalogue as _fixture_catalogue
from test_engine_spatial import connection, pose, scene, step
from test_engine_verification_cache import _mutate, searchable as _searchable

fixture_catalogue = _fixture_catalogue
searchable = _searchable


@pytest.fixture
def prefix_search(searchable):
    root, metadata_path, _, _ = searchable
    prefix = [step("one", {"base": pose()}, ["base"]),
              step("inspect", {"base": pose()}, [], action="inspect")]
    previous = scene({"base": "1"}, prefix).model_dump(mode="json")
    raw = scene({"base": "1", "moving": "1"}, [*prefix,
        step("two", {"base": pose(), "moving": pose(0, 11)}, ["moving"])])
    choices = [connection("two", "moving", moving_site="socket:0:-8:0", target_site="stud:0:0:0")]
    return root, metadata_path, raw.model_dump(mode="json"), previous, {"connections": choices}


def _diagnose(raw, previous, root, **kwargs):
    return hypotheses.diagnose_candidate(raw, previous, root, **kwargs)


def test_enumeration_reuses_prefix_with_identical_full_reports_and_counts(prefix_search, monkeypatch):
    root, _, raw, previous, options = prefix_search
    inputs = canonical([raw, previous])
    contacts = []
    original = hypotheses._diagnostic_contacts
    def tracked(*args, **kwargs):
        contacts.append(tuple(args[0]))
        return original(*args, **kwargs)
    monkeypatch.setattr(hypotheses, "_diagnostic_contacts", tracked)
    with monkeypatch.context() as patch:
        patch.setattr(hypotheses, "diagnostic_reuse_scope", nullcontext)
        full = hypotheses.enumerate_hypotheses(raw, previous, root, **options)
    full_calls = len(contacts)
    contacts.clear()
    scopes = []
    @contextmanager
    def counted_scope():
        with diagnostic_reuse.diagnostic_reuse_scope() as reuse:
            scopes.append(reuse)
            yield reuse
    monkeypatch.setattr(hypotheses, "diagnostic_reuse_scope", counted_scope)
    incremental = hypotheses.enumerate_hypotheses(raw, previous, root, **options)
    assert full["evaluated_count"] == incremental["evaluated_count"] == 8
    assert canonical(full) == canonical(incremental)
    assert scopes[0].captures == 1 and scopes[0].hits == 8
    assert full_calls - len(contacts) == scopes[0].reused_snapshots == 16
    assert canonical([raw, previous]) == inputs
    assert diagnostic_reuse.current_diagnostic_reuse() is None
    assert verification_cache.current_verification() is None


def test_suffix_checks_hidden_existing_pieces_contacts_gaps_and_coincidence(searchable):
    root, _, _, _ = searchable
    prefix = [step("one", {"base": pose()}, ["base"]),
              step("two", {"base": pose(), "hidden": pose(0, 8)}, ["hidden"])]
    previous = scene({"base": "1", "hidden": "1"}, prefix)
    branches = [scene({"base": "1", "hidden": "1", "new": "1"}, [*prefix,
        step("three", {"base": pose(), "new": new_pose}, ["new"])])
        for new_pose in (pose(0, 8), pose(0, 11), pose(1, 8), pose(100, 8))]
    full = [_diagnose(value, previous, root) for value in branches]
    with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
        actual = [_diagnose(value, previous, root) for value in branches]
        assert reuse.hits == 3 and reuse.reused_snapshots == 6
    assert canonical(actual) == canonical(full)
    current = [f for f in actual[0]["findings"] if f["step_id"] == "three"]
    assert any(f["code"] == "occupied_connector" and "hidden" in f["instance_ids"] for f in current)
    assert any(f["code"] == "exact_coincident_geometry" and f["instance_ids"] == ["hidden", "new"] for f in current)
    assert any(f["code"] == "near_connector_gap" for f in actual[1]["findings"])
    assert any(f["code"] == "aabb_overlap_candidate" and "hidden" in f["instance_ids"] for f in actual[2]["findings"])
    assert any(f["code"] == "floating_supported_instance" and "new" in f["instance_ids"] for f in actual[3]["findings"])


def test_rigid_group_and_nonrigid_corrections_preserve_full_diagnostics(searchable):
    root, _, _, _ = searchable
    prefix = [step("one", {"base": pose()}, ["base"]),
        step("callout", {"first": pose(120), "second": pose(120, 8)}, ["first", "second"],
             action="build_subassembly", group="group")]
    previous = scene({"base": "1", "first": "1", "second": "1"}, prefix)
    original = previous.model_dump(mode="json")
    original["steps"].append(step("attach", {"base": pose(), "first": pose(0, 8), "second": pose(0, 16)}, [],
                                   action="attach_subassembly", group="group"))
    nonrigid = deepcopy(original)
    nonrigid["steps"][-1]["poses"]["second"] = pose(20, 16)
    movement = deepcopy(original)
    movement["steps"][-1]["action"] = "inspect"
    bad_group = deepcopy(original)
    bad_group["steps"][-1]["assembly_group_id"] = "different-group"
    branches = [original, nonrigid, movement, bad_group]
    expected = [_diagnose(value, previous, root) for value in branches]
    with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
        actual = [_diagnose(value, previous, root) for value in branches]
        assert reuse.hits == 3
    assert canonical(actual) == canonical(expected)
    assert not actual[0]["finding_counts"].get("nonrigid_group")
    assert actual[1]["finding_counts"]["nonrigid_group"] == 1
    assert actual[2]["finding_counts"]["historical_movement"] == 1
    assert actual[3]["finding_counts"]["nonrigid_group"] == 1


def test_nested_group_membership_survives_prefix_reuse(searchable):
    root, _, _, _ = searchable
    parts = {name: "1" for name in ("base", "outer", "inner", "cap")}
    prefix = [step("one", {"base": pose()}, ["base"]),
        step("outer-build", {"outer": pose(100)}, ["outer"], action="build_subassembly", group="outer-group"),
        step("inner-build", {"inner": pose(300), "cap": pose(300, 8)}, ["inner", "cap"],
             action="build_subassembly", group="inner-group"),
        step("inner-attach", {"outer": pose(100), "inner": pose(100, 8), "cap": pose(100, 16)}, [],
             action="attach_subassembly", group="inner-group")]
    previous = scene(parts, prefix)
    raw = previous.model_dump(mode="json")
    raw["steps"].append(step("outer-attach", {"base": pose(), "outer": pose(0, 8),
        "inner": pose(0, 16), "cap": pose(0, 24)}, [], action="attach_subassembly", group="outer-group"))
    damaged = deepcopy(raw)
    damaged["steps"][-1]["poses"]["cap"] = pose(100, 16)
    expected = [_diagnose(value, previous, root) for value in (raw, damaged)]
    with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
        actual = [_diagnose(value, previous, root) for value in (raw, damaged)]
        assert reuse.hits == 1 and reuse.reused_snapshots == 4
    assert canonical(actual) == canonical(expected)
    assert not actual[0]["finding_counts"].get("nonrigid_group")
    failure = next(f for f in actual[1]["findings"] if f["code"] == "nonrigid_group")
    assert failure["instance_ids"] == ["cap", "inner", "outer"]


def test_unsupported_prefix_stays_full_and_report_mutation_cannot_change_reuse(prefix_search):
    root, _, raw, previous, _ = prefix_search
    with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
        first = _diagnose(raw, previous, root)
        expected = canonical(first)
        first["findings"].clear()
        first["snapshots"][0]["status"] = "caller-mutated"
        first["checks"].clear()
        assert canonical(_diagnose(raw, previous, root)) == expected
        assert reuse.hits == 1
    for value in (raw, previous):
        value["instances"][0].update(part_id="99999", geometry_ref="parts/99999.dat")
    expected = _diagnose(raw, previous, root)
    with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
        for _ in range(2):
            assert canonical(_diagnose(raw, previous, root)) == canonical(expected)
        assert reuse.hits == reuse.captures == 0
    assert expected["finding_counts"]["unsupported_connector_geometry"] == 1


@pytest.mark.parametrize("change", ["prefix_pose", "prefix_group", "prefix_source", "part_color", "part_identity",
                                   "unsupported_geometry", "previous", "scope"])
def test_incompatible_branch_falls_back_without_reusing_history(prefix_search, change):
    root, _, raw, previous, _ = prefix_search
    changed, prior, options = deepcopy(raw), deepcopy(previous), {}
    if change == "prefix_pose":
        changed["steps"][0]["poses"]["base"] = pose(20)
    elif change == "prefix_group":
        changed["steps"][0].update(action="build_subassembly", assembly_group_id="detached")
    elif change == "prefix_source":
        changed["steps"][0]["source"]["bbox"] = [0, 0, .5, .5]
    elif change == "part_color":
        changed["instances"][0]["color_code"] = "4"
    elif change == "part_identity":
        changed["instances"][0]["part_id"] = "2"
    elif change == "unsupported_geometry":
        changed["instances"][0].update(part_id="99999", geometry_ref="parts/99999.dat")
    elif change == "previous":
        prior["revision"] = "different-accepted-revision"
    elif change == "scope":
        options = {"checked_step_ids": ["two"]}
    expected = _diagnose(changed, prior, root, **options)
    with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
        _diagnose(raw, previous, root)
        actual = _diagnose(changed, prior, root, **options)
        assert reuse.captures == 1 and reuse.hits == 0
    assert canonical(actual) == canonical(expected)


def test_requested_scope_and_truncated_findings_keep_exact_counts(searchable):
    root, _, _, _ = searchable
    names = {f"part-{i}": "1" for i in range(34)}
    poses = {name: pose(i / 100) for i, name in enumerate(names)}
    prefix = [step("one", poses, list(names)), step("two", poses, [], action="inspect")]
    previous = scene(names, prefix)
    raw = scene(names, [*prefix, step("three", poses, [], action="inspect")])
    for options in ({}, {"checked_step_ids": ["three"]}):
        full = _diagnose(raw, previous, root, **options)
        with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
            _diagnose(raw, previous, root, **options)
            actual = _diagnose(raw, previous, root, **options)
            assert reuse.hits == 1
        assert canonical(actual) == canonical(full)
        assert actual["findings_truncated"] and actual["computed_findings_count"] > 512
        assert len(actual["findings"]) == 512
        assert actual["coverage"]["status"] == "partial"
        if options:
            assert actual["coverage"]["omitted_or_partial_pose_count"] == 68


@pytest.mark.parametrize("has_mesh_proof", [False, True])
def test_symmetry_counters_match_and_unfenced_material_proofs_use_full_path(searchable, monkeypatch, has_mesh_proof):
    root, _, _, _ = searchable
    rotated = pose()
    if has_mesh_proof:
        rotated["quaternion_xyzw"] = [0, 1, 0, 0]
        material = b"0 Original synthetic material fixture\n"
        (root / "LDConfig.ldr").write_bytes(material)
        path = root / "provenance.json"
        document = json.loads(path.read_text())
        document["materials"] = {"LDConfig.ldr": {
            "url": "https://library.ldraw.org/library/official/LDConfig.ldr",
            "sha256": hashlib.sha256(material).hexdigest()}}
        path.write_text(json.dumps(document))
    poses = {"first": pose(), "second": rotated}
    prefix = [step("one", poses, list(poses))]
    previous = scene({name: "1" for name in poses}, prefix)
    raw = scene({name: "1" for name in poses}, [*prefix, step("two", poses, [], action="inspect")])
    monkeypatch.setattr(hypotheses, "MAX_SYMMETRY_PAIRS", 1)
    full = _diagnose(raw, previous, root)
    with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
        _diagnose(raw, previous, root)
        actual = _diagnose(raw, previous, root)
        assert reuse.hits == (0 if has_mesh_proof else 1)
    assert canonical(actual) == canonical(full)
    assert actual["symmetry"]["pairs_checked"] == (1 if has_mesh_proof else 0)
    assert actual["symmetry"]["pairs_considered"] == actual["symmetry"]["pairs_omitted"] == 1
    if has_mesh_proof:
        assert actual["symmetry"]["geometry_receipts"][0]["geometry_files"]
        with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
            _diagnose(raw, previous, root)
            (root / "LDConfig.ldr").write_bytes(b"changed material fixture\n")
            with pytest.raises(ValueError, match="Material hash mismatch"):
                _diagnose(raw, previous, root)
            assert reuse.hits == reuse.captures == 0


@pytest.mark.parametrize("bound,value", [("MAX_PREFIX_STEPS", 1), ("MAX_PREFIX_INSTANCES", 0), ("MAX_STATE_BYTES", 1)])
def test_reuse_bounds_fall_back_to_complete_diagnostics(prefix_search, monkeypatch, bound, value):
    root, _, raw, previous, _ = prefix_search
    expected = _diagnose(raw, previous, root)
    monkeypatch.setattr(diagnostic_reuse, bound, value)
    with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
        for _ in range(2):
            assert canonical(_diagnose(raw, previous, root)) == canonical(expected)
        assert reuse.hits == reuse.captures == 0


@pytest.mark.parametrize("kind", ["metadata", "provenance", "content_restored_mtime", "symlink_ancestor"])
def test_reused_prefix_cannot_escape_final_geometry_fence(prefix_search, kind):
    root, metadata_path, raw, previous, _ = prefix_search
    with pytest.raises(ValueError, match="Verified catalogue inputs changed"):
        with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
            _diagnose(raw, previous, root)
            _mutate(kind, root, metadata_path)
            _diagnose(raw, previous, root)
            assert reuse.hits == 1
    assert diagnostic_reuse.current_diagnostic_reuse() is None
    assert verification_cache.current_verification() is None


def test_standalone_and_closed_or_other_verification_contexts_do_not_reuse(prefix_search, monkeypatch):
    root, _, raw, previous, _ = prefix_search
    calls = []
    original = hypotheses._diagnostic_contacts
    def tracked(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(hypotheses, "_diagnostic_contacts", tracked)
    full = _diagnose(raw, previous, root)
    expected_calls = len(calls)
    with diagnostic_reuse.diagnostic_reuse_scope() as unverified:
        assert canonical(_diagnose(raw, previous, root)) == canonical(full)
        assert unverified.hits == unverified.captures == 0
    assert len(calls) == expected_calls * 2
    with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as outer:
        _diagnose(raw, previous, root)
        with verification_cache.catalogue_verification_scope():
            assert canonical(_diagnose(raw, previous, root)) == canonical(full)
            assert outer.hits == 0
        with diagnostic_reuse.diagnostic_reuse_scope() as nested:
            _diagnose(raw, previous, root)
            assert nested.hits == 0 and nested.captures == 1
        _diagnose(raw, previous, root)
        assert outer.hits == 1
        copied = copy_context()
    assert outer.state is outer.key is None
    with pytest.raises(ValueError, match="scope is closed"):
        copied.run(_diagnose, raw, previous, root)


def test_schema_validation_still_runs_before_reuse(prefix_search):
    root, _, raw, previous, _ = prefix_search
    with verification_cache.catalogue_verification_scope(), diagnostic_reuse.diagnostic_reuse_scope() as reuse:
        _diagnose(raw, previous, root)
        invalid = deepcopy(raw)
        invalid["steps"][-1]["poses"]["moving"]["position_ldu"] = [float("nan"), 0, 0]
        with pytest.raises(ValueError):
            _diagnose(invalid, previous, root)
        with pytest.raises(ValueError, match="Invalid diagnostic snapshot scope"):
            _diagnose(raw, previous, root, checked_step_ids=["not-a-step"])
        assert reuse.hits == 0
