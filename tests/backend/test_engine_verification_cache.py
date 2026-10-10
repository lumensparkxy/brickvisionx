"""Original tiny meshes exercise reuse, output parity, and the final integrity fence."""
from contextlib import nullcontext
from contextvars import copy_context
from copy import deepcopy
import json
import os
import shutil

import pytest

from guide2build.engine import connectors, hypotheses, spatial, verification_cache
from guide2build.releases.models import canonical
from test_engine_connectors import fixture_catalogue as _fixture_catalogue
from test_engine_spatial import connection, pose, scene, step

fixture_catalogue = _fixture_catalogue


@pytest.fixture
def searchable(fixture_catalogue):
    root, metadata, metadata_path = fixture_catalogue
    metadata["limits"] = {"max_instances": 512, "max_steps": 128, "max_connections": 512}
    part = metadata["parts"][0]
    part["bounds_ldu"] = [[-10, -8, -10], [30, 0, 10]]
    for feature in part["connectors"]:
        feature.update(normal=[0, 1 if feature["kind"] == "stud" else -1, 0],
            tangent=[1, 0, 0], allowed_quarter_turns=[0, 1, 2, 3], engagement_ldu=4)
    second = deepcopy(part["connectors"][0])
    second.update(connector_id="stud:20:0:0", position_ldu=[20, 0, 0])
    part["connectors"].append(second)
    metadata_path.write_text(json.dumps(metadata))
    raw = scene({"base": "1", "moving": "1"}, [
        step("one", {"base": pose(), "moving": pose(0, 8)}, ["base", "moving"])])
    choices = [connection(moving="moving", moving_site="socket:0:-8:0", target_site="stud:0:0:0")]
    roots = [{"step_id": "one", "instance_id": "base"}]
    return root, metadata_path, raw, {"connections": choices, "roots": roots}


def test_search_reuses_verified_catalogues_without_changing_any_output(searchable, monkeypatch):
    root, _, raw, options = searchable
    before = canonical(raw)
    loads = []
    original = connectors._load_connector_catalogue
    def tracked(*args, **kwargs):
        loads.append(args[1] if len(args) > 1 else None)
        return original(*args, **kwargs)
    monkeypatch.setattr(connectors, "_load_connector_catalogue", tracked)
    with monkeypatch.context() as context:
        context.setattr(hypotheses, "catalogue_verification_scope", nullcontext)
        fresh = hypotheses.enumerate_hypotheses(raw, None, root, **options)
    fresh_count = len(loads)
    loads.clear()
    reused = hypotheses.enumerate_hypotheses(raw, None, root, **options)
    assert len(loads) == 2 and fresh_count > 10
    assert reused["evaluated_count"] == fresh["evaluated_count"] == 8
    assert canonical(fresh) == canonical(reused)
    assert canonical(raw) == before
    assert verification_cache.current_verification() is None


def test_parsed_catalogue_values_are_independent_and_direct_calls_are_fresh(searchable, monkeypatch):
    root, _, raw, options = searchable
    original = connectors._load_connector_catalogue
    calls = []
    def tracked(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(connectors, "_load_connector_catalogue", tracked)
    with verification_cache.catalogue_verification_scope():
        first = connectors.load_connector_catalogue(root)
        expected = deepcopy(first)
        first[0]["parts"][0]["connectors"].clear()
        first[1].clear()
        assert connectors.load_connector_catalogue(root) == expected
    assert len(calls) == 1
    for _ in range(2):
        hypotheses.diagnose_candidate(raw, None, root)
        spatial.solve_candidate(raw, None, options["connections"], options["roots"], root)
    assert len(calls) == 5


def _mutate(kind, root, metadata_path):
    target = root / "p/test.dat"
    if kind == "content_restored_mtime":
        before = target.stat()
        target.write_bytes(target.read_bytes().replace(b"primitive", b"PRIMITIVE"))
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif kind in {"provenance", "metadata"}:
        target = root / "provenance.json" if kind == "provenance" else metadata_path
        target.write_bytes(target.read_bytes() + b" ")
    elif kind == "replace_same_bytes":
        replacement = target.with_suffix(".replacement")
        replacement.write_bytes(target.read_bytes())
        replacement.replace(target)
    elif kind == "symlink":
        replacement = target.with_suffix(".replacement")
        replacement.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(replacement)
    elif kind == "renamed_root":
        relocated = root.with_name("renamed-geometry")
        root.rename(relocated)
        shutil.copytree(relocated, root)
    elif kind == "symlink_ancestor":
        primitives = root / "p"
        relocated = root / "original-primitives"
        primitives.rename(relocated)
        primitives.symlink_to(relocated, target_is_directory=True)
    elif kind == "removed":
        target.unlink()
    else:
        raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["content_restored_mtime", "provenance", "metadata", "replace_same_bytes",
    "symlink", "renamed_root", "symlink_ancestor", "removed"])
def test_mid_search_mutations_fail_before_any_candidate_is_returned(searchable, monkeypatch, kind):
    root, metadata_path, raw, options = searchable
    original = hypotheses.solve_candidate
    mutated = False
    def solve(*args, **kwargs):
        nonlocal mutated
        result = original(*args, **kwargs)
        if not mutated:
            _mutate(kind, root, metadata_path)
            mutated = True
        return result
    monkeypatch.setattr(hypotheses, "solve_candidate", solve)
    with pytest.raises(ValueError, match="Verified catalogue inputs changed"):
        hypotheses.enumerate_hypotheses(raw, None, root, **options)
    assert mutated and verification_cache.current_verification() is None


def test_final_fence_also_covers_unsupported_raw_fallback(searchable, monkeypatch):
    root, metadata_path, _, _ = searchable
    raw = scene({"unknown": "99999"}, [step("one", {"unknown": pose()}, ["unknown"])])
    original = hypotheses._diagnostic_summary
    def summary(report):
        result = original(report)
        _mutate("content_restored_mtime", root, metadata_path)
        return result
    monkeypatch.setattr(hypotheses, "_diagnostic_summary", summary)
    with pytest.raises(ValueError, match="Verified catalogue inputs changed"):
        hypotheses.enumerate_hypotheses(raw, None, root)
    assert verification_cache.current_verification() is None


@pytest.mark.parametrize("mutate", [False, True])
def test_exception_unwinds_and_revalidates_scope(searchable, monkeypatch, mutate):
    root, metadata_path, raw, options = searchable
    def fail(*args, **kwargs):
        if mutate:
            _mutate("metadata", root, metadata_path)
        raise RuntimeError("synthetic solver interruption")
    monkeypatch.setattr(hypotheses, "solve_candidate", fail)
    expected = ValueError if mutate else RuntimeError
    with pytest.raises(expected, match="changed" if mutate else "interruption"):
        hypotheses.enumerate_hypotheses(raw, None, root, **options)
    assert verification_cache.current_verification() is None


def test_next_invocation_never_reuses_a_previous_verified_scope(searchable):
    root, metadata_path, raw, options = searchable
    hypotheses.enumerate_hypotheses(raw, None, root, **options)
    _mutate("content_restored_mtime", root, metadata_path)
    with pytest.raises(ValueError, match="hash mismatch"):
        hypotheses.enumerate_hypotheses(raw, None, root, **options)


def test_nested_and_copied_contexts_cannot_reuse_closed_verification(searchable):
    root, _, _, _ = searchable
    with verification_cache.catalogue_verification_scope():
        connectors.load_connector_catalogue(root)
        outer = verification_cache.current_verification()
        with verification_cache.catalogue_verification_scope():
            connectors.load_connector_catalogue(root)
            assert verification_cache.current_verification() is not outer
        assert verification_cache.current_verification() is outer
        copied = copy_context()
    assert verification_cache.current_verification() is None
    with pytest.raises(ValueError, match="scope is closed"):
        copied.run(connectors.load_connector_catalogue, root)


@pytest.mark.parametrize("bound,value", [("MAX_FILES", 1), ("MAX_BYTES", 10), ("MAX_CATALOGUES", 1)])
def test_reuse_bookkeeping_is_bounded_and_fail_closed(searchable, monkeypatch, bound, value):
    root, _, raw, options = searchable
    monkeypatch.setattr(verification_cache, bound, value)
    with pytest.raises(ValueError, match="limit exceeded"):
        hypotheses.enumerate_hypotheses(raw, None, root, **options)
    assert verification_cache.current_verification() is None


@pytest.mark.parametrize("change,match", [
    ({"classification": "Model"}, "provenance"),
    ({"url": "https://example.com/model.dat"}, "provenance"),
    ({"dependencies": []}, "receipt mismatch")])
def test_reuse_preserves_original_provenance_and_dependency_failures(searchable, change, match):
    root, _, _, _ = searchable
    path = root / "provenance.json"
    document = json.loads(path.read_text())
    document["resources"]["parts/1.dat"].update(change)
    path.write_text(json.dumps(document))
    for scope in (nullcontext, verification_cache.catalogue_verification_scope):
        with pytest.raises(ValueError, match=match), scope():
            connectors.load_connector_catalogue(root)
