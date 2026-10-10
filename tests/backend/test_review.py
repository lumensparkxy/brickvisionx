import pytest
from fastapi.testclient import TestClient
from guide2build.core.models import SceneManifest
from guide2build.main import create_app
from guide2build.jobs.store import Store, Conflict
from guide2build.review.models import CorrectionRequest, ReviewRequest
from guide2build.review.service import ReviewService


def correction(scene_data, **changes):
    return CorrectionRequest(expected_revision=scene_data["revision"], actor_type="agent", actor_id="test-agent",
        reason="Synthetic contract test only", source=scene_data["steps"][0]["source"],
        command={"type": "pose", "step_id": "s1", "instance_id": "a", "pose": {
            "position_ldu": [20, 0, 0], "quaternion_xyzw": [0, 0, 0, 1]}}, **changes)


def test_correction_immutable_idempotent_and_stale_safe(tmp_path, scene_data):
    service = ReviewService(Store(tmp_path))
    original = SceneManifest.model_validate(scene_data)
    service.import_scene(original)
    request = correction(scene_data)
    updated = service.apply(original.revision, request, "correction-one")
    assert updated.revision != original.revision
    assert updated.status == "needs_review"
    assert updated.geometry_check == updated.connector_check == updated.physical_build_check == "not_run"
    assert service.get(original.revision) == original
    assert updated.steps[0].poses["a"].position_ldu == (20, 0, 0)
    assert service.apply(original.revision, request, "correction-one") == updated
    with pytest.raises(Conflict):
        service.apply(original.revision, request, "correction-two")


def test_correction_audit_records_prior_value_and_source(tmp_path, scene_data):
    store = Store(tmp_path)
    service = ReviewService(store)
    service.import_scene(SceneManifest.model_validate(scene_data))
    service.apply(scene_data["revision"], correction(scene_data), "correction")
    with store.connect() as db:
        import json
        record = json.loads(db.execute("SELECT payload FROM review_actions").fetchone()[0])
    assert record["before"]["position_ldu"] == [0, 0, 0]
    assert record["source"]["source_sha256"] == scene_data["source_sha256"]
    assert record["origin"] == "local_api_declared_agent"


def test_unverified_human_claim_is_rejected(tmp_path, scene_data):
    service = ReviewService(Store(tmp_path))
    service.import_scene(SceneManifest.model_validate(scene_data))
    request = ReviewRequest(expected_revision=scene_data["revision"], actor_type="human", actor_id="pretend",
                            decision="accepted", evidence_paths=["evidence/example.txt"])
    with pytest.raises(ValueError, match="Human review identity"):
        service.apply(scene_data["revision"], request, "fake-human")
    assert service.get(scene_data["revision"]).status == "candidate"


def test_agent_review_new_revision_requires_real_local_evidence(tmp_path, scene_data):
    service = ReviewService(Store(tmp_path))
    service.import_scene(SceneManifest.model_validate(scene_data))
    request = ReviewRequest(expected_revision=scene_data["revision"], actor_type="agent", actor_id="test-agent",
                            decision="accepted", evidence_paths=["evidence/test.txt"])
    with pytest.raises(ValueError):
        service.apply(scene_data["revision"], request, "review")
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/test.txt").write_text("Synthetic contract test; not target model review evidence.")
    result = service.apply(scene_data["revision"], request, "review")
    assert result.status == "agent_reviewed"
    assert result.reviews[-1].reviewed_revision == result.revision
    assert service.get(scene_data["revision"]).status == "candidate"


def test_mapping_rejects_unavailable_and_traversing_geometry(tmp_path, scene_data):
    service = ReviewService(Store(tmp_path))
    service.import_scene(SceneManifest.model_validate(scene_data))
    for geometry in ("parts/missing.dat", "parts/../../outside.dat"):
        data = correction(scene_data).model_dump()
        data["command"] = {"type": "mapping", "instance_id": "a", "part_id": "x",
                           "color_code": "15", "geometry_ref": geometry}
        with pytest.raises(ValueError):
            service.apply(scene_data["revision"], CorrectionRequest.model_validate(data), "mapping")


def test_review_api_rejects_stale_revision_and_does_not_leak_validation(tmp_path, scene_data):
    client = TestClient(create_app(tmp_path))
    client.app.state.reviews.import_scene(SceneManifest.model_validate(scene_data))
    payload = correction(scene_data).model_dump(mode="json")
    route = f"/api/v1/reconstructions/{scene_data['revision']}/corrections"
    response = client.post(route, json=payload, headers={"Idempotency-Key": "one"})
    assert response.status_code == 200
    assert response.json()["checks"]["structure"] == "pass"
    assert client.post(route, json=payload, headers={"Idempotency-Key": "two"}).status_code == 409
    payload["command"]["pose"]["quaternion_xyzw"] = [1, 2, 3, 4]
    bad = client.post(route, json=payload, headers={"Idempotency-Key": "three"})
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "invalid_request"


def test_candidate_route_rejects_stale_source_and_keeps_historical_revision(tmp_path, scene_data):
    import hashlib
    import json
    from guide2build.catalog import find_guide
    from guide2build.jobs.store import now
    from guide2build.jobs.source_cache import cached_receipt
    # Original test-authored bytes and fixture-derived scene are not real LEGO evidence.
    content = b"%PDF-test-original"
    digest = hashlib.sha256(content).hexdigest()
    scene_data.update(set_number="30669", guide_id="alt-02", source_sha256=digest)
    for instance in scene_data["instances"]:
        instance["source"]["source_sha256"] = digest
    for step in scene_data["steps"]:
        step["source"]["source_sha256"] = digest
    source = tmp_path / "sources/30669/alt-02/source.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    url = find_guide("30669", "alt-02")["pdf_url"]
    receipt = {"requested_url": url, "resolved_url": url, "sha256": digest,
               "size_bytes": len(content), "downloaded_at": now()}
    source.with_suffix(".receipt.json").write_text(json.dumps(receipt))
    path = tmp_path / "reconstructions/30669/alt-02/scene.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(scene_data))
    client = TestClient(create_app(tmp_path))
    route = "/api/v1/sets/30669/guides/alt-02/scene?candidate=true"
    assert client.get(route).status_code == 200
    assert client.get(route.split("?")[0]).status_code == 409
    # A stale receipt fails validation; a new valid receipt must not bless an old scene.
    source.write_bytes(b"%PDF-test-new-source")
    assert cached_receipt(tmp_path, "30669", "alt-02", url) is None
    receipt.update(sha256=hashlib.sha256(source.read_bytes()).hexdigest(), size_bytes=source.stat().st_size)
    source.with_suffix(".receipt.json").write_text(json.dumps(receipt))
    response = client.get(route)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "source_revision_mismatch"
    assert client.get(f"/api/v1/reconstructions/{scene_data['revision']}/scene").status_code == 200


def test_declared_human_correction_never_grants_review(tmp_path, scene_data):
    store = Store(tmp_path)
    service = ReviewService(store)
    service.import_scene(SceneManifest.model_validate(scene_data))
    data = correction(scene_data).model_dump()
    data["actor_type"] = "human"
    import pytest
    with pytest.raises(ValueError, match="Human review identity is not verified"):
        service.apply(scene_data["revision"], CorrectionRequest.model_validate(data), "operator")
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM review_actions").fetchone()[0] == 0
