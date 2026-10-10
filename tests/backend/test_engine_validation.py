import hashlib
import pytest
from guide2build.engine.validation import EvidenceFile, ValidationBundle


def test_validation_evidence_root_confined_and_hash_bound(tmp_path):
    folder = tmp_path / "bundle"
    folder.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"data")
    sha = hashlib.sha256(b"data").hexdigest()
    with pytest.raises(ValueError, match="escapes"):
        EvidenceFile(path="../outside", sha256=sha).verify(folder)
    (folder / "good").write_bytes(b"data")
    assert EvidenceFile(path="good", sha256=sha).verify(folder).name == "good"
    with pytest.raises(ValueError, match="hash"):
        EvidenceFile(path="good", sha256="a"*64).verify(folder)


def test_independent_bundle_requires_rendered_review_not_boolean_assertion():
    with pytest.raises(ValueError):
        ValidationBundle.model_validate({"candidate_sha256": "a"*64, "source_index": {},
            "connector_report": {"status": "pass"}, "assembly_report": {"status": "pass"}})


def test_caller_json_cannot_register_a_passing_deterministic_checker():
    from guide2build.engine.checkers import run_registered_checks
    with pytest.raises(ValueError, match="Unsupported deterministic"):
        run_registered_checks(None, None, "pretend-passed-checker", "1")


def test_local_validation_cannot_impersonate_human_review():
    from guide2build.engine.validation import AssemblyReport
    with pytest.raises(ValueError):
        AssemblyReport.model_validate({"scene_sha256": "a"*64, "review_kind": "source_render_comparison",
            "actor_type": "human", "reviewer_id": "pretend-human", "status": "pass",
            "render_report": {"path": "report.json", "sha256": "b"*64},
            "comparisons": [{"step_id": "one", "source_page_sha256": "c"*64,
                "render": {"path": "one.png", "sha256": "d"*64}, "decision": "pass"}]})
