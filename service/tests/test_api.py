import io
import zipfile

from fastapi.testclient import TestClient

from service.app import main


def zip_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("web/index.html", "<!doctype html><html><body><h1>MintPack test</h1></body></html>")
        archive.writestr("web/css/site.css", "body{background:#fff}")
    return buffer.getvalue()


def test_health_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "API_KEY", "t" * 40)
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    client = TestClient(main.app)
    assert client.get("/health").status_code == 401
    response = client.get("/health", headers={"X-API-Key": "t" * 40})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_inspect_zip_and_preview_headers(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "API_KEY", "s" * 40)
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    main.previews.clear()
    client = TestClient(main.app)
    response = client.post(
        "/api/inspect",
        headers={"X-API-Key": "s" * 40},
        files={"project_files": ("my-project.zip", zip_bytes(), "application/zip")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["entrypoint"] == "web/index.html"
    preview = client.get(data["preview_url"])
    assert preview.status_code == 200
    assert "MintPack test" in preview.text
    assert "sandbox allow-scripts" in preview.headers["content-security-policy"]


def test_inspect_rejects_invalid_archive(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "API_KEY", "q" * 40)
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    client = TestClient(main.app)
    response = client.post(
        "/api/inspect",
        headers={"X-API-Key": "q" * 40},
        files={"project_files": ("bad.zip", b"not a zip", "application/zip")},
    )
    assert response.status_code == 400


def test_preview_can_be_deleted(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "API_KEY", "d" * 40)
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    main.previews.clear()
    client = TestClient(main.app)
    response = client.post(
        "/api/inspect",
        headers={"X-API-Key": "d" * 40},
        files={"project_files": ("project.zip", zip_bytes(), "application/zip")},
    )
    preview_id = response.json()["preview_id"]
    assert (tmp_path / "previews" / preview_id).exists()
    deleted = client.delete(f"/api/previews/{preview_id}", headers={"X-API-Key": "d" * 40})
    assert deleted.status_code == 200
    assert not (tmp_path / "previews" / preview_id).exists()
