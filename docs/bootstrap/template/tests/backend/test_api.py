from fastapi.testclient import TestClient
from guide2build.main import create_app


def test_health(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v1/health").json()["stage"] == "scaffold"


def test_known_set_has_official_source(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/v1/sets/30669")
    assert response.status_code == 200
    assert response.json()["guides"][0]["source_sha256"] is None


def test_unknown_set_is_not_faked(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v1/sets/99999").status_code == 404


def test_invalid_set_rejected(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v1/sets/abc").status_code == 422


def test_missing_reconstruction_is_explicit(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/v1/sets/30669/guides/alt-02/scene")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "reconstruction_not_available"


def test_unknown_guide_cannot_be_used_as_file_path(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v1/sets/30669/guides/not-a-guide/scene").status_code == 404


def test_invalid_reconstruction_is_not_served(tmp_path):
    directory = tmp_path / "reconstructions/30669/alt-02"
    directory.mkdir(parents=True)
    (directory / "scene.json").write_text('{"invented":"model"}')
    response = TestClient(create_app(tmp_path)).get("/api/v1/sets/30669/guides/alt-02/scene")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_reconstruction"
