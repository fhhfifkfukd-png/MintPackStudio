import stat
import zipfile
from pathlib import Path

import pytest

from service.app.archive import ArchiveError, safe_extract_zip, save_uploaded_files


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def test_extracts_nested_index_and_keeps_relative_files(tmp_path: Path):
    archive = make_zip(tmp_path / "site.zip", {
        "build/public/index.html": b"<h1>hello</h1>",
        "build/public/css/main.css": b"body{color:#000}",
        "build/public/img/logo.png": b"fake-test-image-data",
    })
    root = safe_extract_zip(archive, tmp_path / "out")
    assert root == (tmp_path / "out/build/public").resolve()
    assert (root / "index.html").read_bytes() == b"<h1>hello</h1>"
    assert (root / "css/main.css").exists()
    assert (root / "img/logo.png").exists()


def test_rejects_zip_slip(tmp_path: Path):
    archive = make_zip(tmp_path / "bad.zip", {
        "../../escaped.txt": b"owned",
        "index.html": b"<h1>x</h1>",
    })
    destination = tmp_path / "safe"
    with pytest.raises(ArchiveError, match="Zip Slip|مسیر ناامن"):
        safe_extract_zip(archive, destination)
    assert not (tmp_path / "escaped.txt").exists()


def test_rejects_symlink(tmp_path: Path):
    archive_path = tmp_path / "link.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        item = zipfile.ZipInfo("index.html")
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(item, "../../escape")
    with pytest.raises(ArchiveError, match="symlink|پیوندی"):
        safe_extract_zip(archive_path, tmp_path / "out")


def test_rejects_multiple_shallowest_index_files(tmp_path: Path):
    archive = make_zip(tmp_path / "ambiguous.zip", {
        "a/index.html": b"a",
        "b/index.html": b"b",
    })
    with pytest.raises(ArchiveError, match="چند index.html"):
        safe_extract_zip(archive, tmp_path / "out")


def test_missing_index_is_rejected(tmp_path: Path):
    archive = make_zip(tmp_path / "missing.zip", {"readme.txt": b"hello"})
    with pytest.raises(ArchiveError, match="index.html"):
        safe_extract_zip(archive, tmp_path / "out")


def test_loose_files_support_html_css_and_js(tmp_path: Path):
    root = save_uploaded_files([
        ("index.html", b"<h1>hello</h1>"),
        ("styles.css", b"body{}"),
        ("app.js", b"console.log('ok')"),
    ], tmp_path / "loose")
    assert root.joinpath("index.html").exists()
    assert root.joinpath("styles.css").exists()
    assert root.joinpath("app.js").exists()


def test_uppercase_index_is_normalized_for_android_assets(tmp_path: Path):
    archive = make_zip(tmp_path / "upper.zip", {
        "public/INDEX.HTML": b"<h1>upper</h1>",
        "public/js/app.js": b"console.log(1)",
    })
    root = safe_extract_zip(archive, tmp_path / "out")
    assert (root / "index.html").read_bytes() == b"<h1>upper</h1>"
    assert not (root / "INDEX.HTML").exists()


def test_rejects_file_directory_path_collision(tmp_path: Path):
    archive = make_zip(tmp_path / "collision.zip", {
        "folder.js": b"not a directory",
        "folder.js/index.html": b"<h1>collision</h1>",
    })
    with pytest.raises(ArchiveError, match="تداخل مسیر"):
        safe_extract_zip(archive, tmp_path / "out")
