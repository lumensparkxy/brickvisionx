from fastapi.testclient import TestClient
from guide2build.main import create_app
import hashlib
import json


def test_health(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/v1/health").json()["stage"] == "local_prototype"


def test_known_set_has_official_source(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/v1/sets/30669")
    assert response.status_code == 200
    assert response.json()["guides"][0]["source_sha256"] is None
    assert response.json()["guides"][0]["tutorial_available"] is False


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


def test_source_pages_follow_committed_manifest_not_old_250_page_ceiling(tmp_path):
    directory = tmp_path / "public/pages" / ("a" * 64)
    directory.mkdir(parents=True)
    path = directory / "page-512.png"
    content = b"test raster bytes"
    path.write_bytes(content)
    client = TestClient(create_app(tmp_path))
    url = f"/api/v1/sources/{'a' * 64}/pages/512"
    assert client.get(url).status_code == 404  # An unfinished batch is not committed.
    assert client.get(f"/assets-local/pages/{'a' * 64}/page-512.png").status_code == 404
    (directory / "pages.json").write_text(json.dumps([{
        "page_index": 512, "file": path.name, "sha256": hashlib.sha256(content).hexdigest(),
    }]))
    assert client.get(url).content == content
    assert client.get(f"/assets-local/pages/{'a' * 64}/pages.json").status_code == 404
    assert client.get(f"/api/v1/sources/{'a' * 64}/pages/513").status_code == 404
    path.write_bytes(b"changed after publication")
    assert client.get(url).status_code == 404


def test_source_manifest_cannot_point_to_a_different_source(tmp_path):
    root = tmp_path / "public/pages"
    real = root / ("b" * 64)
    real.mkdir(parents=True)
    (root / ("a" * 64)).symlink_to(real, target_is_directory=True)
    content = b"another source"
    (real / "page-000.png").write_bytes(content)
    (real / "pages.json").write_text(json.dumps([{
        "page_index": 0, "file": "page-000.png", "sha256": hashlib.sha256(content).hexdigest(),
    }]))
    client = TestClient(create_app(tmp_path))
    assert client.get(f"/api/v1/sources/{'a' * 64}/pages/0").status_code == 404
