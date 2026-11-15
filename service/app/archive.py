from __future__ import annotations

import os
import posixpath
import shutil
import stat
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Iterable

MAX_ENTRIES = 3000
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 80 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
ALLOWED_EXTENSIONS = {
    ".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".json", ".txt",
    ".xml", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico",
    ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".mp4", ".webm", ".pdf",
    ".wasm", ".map", ".webmanifest", ".avif", ".manifest"
}


class ArchiveError(ValueError):
    """Raised when an uploaded web project is unsafe or invalid."""


def _safe_member_name(name: str) -> str:
    if not name or "\x00" in name or "\\" in name:
        raise ArchiveError("نام یکی از فایل‌های ZIP معتبر نیست.")
    # ZIP paths use forward slashes. Do not accept drive prefixes or absolute paths.
    if name.startswith("/") or (len(name) >= 2 and name[1] == ":"):
        raise ArchiveError("مسیر مطلق در ZIP مجاز نیست.")
    path = PurePosixPath(name)
    if any(part in ("..", "") for part in path.parts):
        raise ArchiveError("مسیر ناامن (Zip Slip) در ZIP شناسایی شد.")
    normalized = posixpath.normpath(name)
    if normalized in (".", "..") or normalized.startswith("../"):
        raise ArchiveError("مسیر ناامن در ZIP شناسایی شد.")
    return normalized


def safe_extract_zip(zip_path: Path, destination: Path) -> Path:
    """Extract a ZIP with traversal, symlink, bomb and duplicate-path checks.

    Returns the directory that contains the selected index.html.
    """
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveError("فایل ZIP خراب یا غیرقابل‌خواندن است.") from exc

    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > MAX_ENTRIES:
            raise ArchiveError("تعداد فایل‌های ZIP خالی یا بیش از حد مجاز است.")
        total = 0
        seen: set[str] = set()
        file_names: set[str] = set()
        for info in infos:
            name = _safe_member_name(info.filename)
            if name in seen:
                raise ArchiveError("نام تکراری در ساختار ZIP پیدا شد.")
            seen.add(name)
            if not info.is_dir():
                file_names.add(name)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ArchiveError("فایل پیوندی (symlink) در ZIP مجاز نیست.")
            if info.flag_bits & 0x1:
                raise ArchiveError("ZIP رمزگذاری‌شده پشتیبانی نمی‌شود؛ ابتدا آن را باز کنید.")
            if info.file_size > MAX_SINGLE_FILE_BYTES:
                raise ArchiveError("حجم یکی از فایل‌ها بیش از حد مجاز است.")
            total += info.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise ArchiveError("حجم استخراج‌شده پروژه بیش از حد مجاز است.")
            if info.file_size and info.compress_size == 0:
                raise ArchiveError("ساختار فشرده‌سازی ZIP معتبر نیست.")
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise ArchiveError("نسبت فشرده‌سازی غیرعادی (احتمال ZIP bomb) شناسایی شد.")
            ext = Path(name).suffix.lower()
            if not info.is_dir() and ext not in ALLOWED_EXTENSIONS:
                raise ArchiveError(f"پسوند فایل پشتیبانی نمی‌شود: {ext or '(بدون پسوند)'}")

        # A regular file cannot also be a parent directory of another ZIP member.
        for filename in file_names:
            prefix = filename + "/"
            if any(other.startswith(prefix) for other in seen):
                raise ArchiveError("تداخل مسیر فایل و پوشه در ZIP شناسایی شد.")

        extracted_total = 0
        for info in infos:
            name = _safe_member_name(info.filename)
            target = (destination / name).resolve()
            if target != destination and destination not in target.parents:
                raise ArchiveError("مسیر خروجی از پوشه پروژه خارج می‌شود.")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Enforce limits on bytes actually decompressed, not only ZIP metadata.
            actual_file_bytes = 0
            try:
                with archive.open(info, "r") as source, target.open("xb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        actual_file_bytes += len(chunk)
                        extracted_total += len(chunk)
                        if actual_file_bytes > MAX_SINGLE_FILE_BYTES:
                            raise ArchiveError("حجم استخراج‌شده یکی از فایل‌ها بیش از حد مجاز است.")
                        if extracted_total > MAX_UNCOMPRESSED_BYTES:
                            raise ArchiveError("حجم واقعی استخراج‌شده پروژه بیش از حد مجاز است.")
                        output.write(chunk)
                if actual_file_bytes != info.file_size:
                    raise ArchiveError("اندازه واقعی فایل با اطلاعات ZIP مطابقت ندارد.")
            except ArchiveError:
                target.unlink(missing_ok=True)
                raise
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
                target.unlink(missing_ok=True)
                raise ArchiveError("محتوای ZIP خراب یا با روش فشرده‌سازی پشتیبانی‌نشده است.") from exc
            except Exception:
                target.unlink(missing_ok=True)
                raise

    index_files = [p for p in destination.rglob("*") if p.is_file() and p.name.lower() == "index.html"]
    if not index_files:
        raise ArchiveError("فایل index.html در پروژه پیدا نشد.")
    index_files.sort(key=lambda p: (len(p.relative_to(destination).parts), str(p).lower()))
    min_depth = len(index_files[0].relative_to(destination).parts)
    shallowest = [p for p in index_files if len(p.relative_to(destination).parts) == min_depth]
    if len(shallowest) > 1:
        options = ", ".join(str(p.relative_to(destination)) for p in shallowest[:4])
        raise ArchiveError(f"چند index.html هم‌سطح وجود دارد؛ ساختار را یکتا کنید: {options}")
    selected = shallowest[0]
    if selected.name != "index.html":
        canonical = selected.with_name("index.html")
        if canonical.exists():
            raise ArchiveError("چند فایل ورودی با نام‌های متفاوت پیدا شد؛ مسیر index.html را یکتا کنید.")
        selected.rename(canonical)
    return selected.parent


def save_uploaded_files(files: Iterable[tuple[str, bytes]], destination: Path) -> Path:
    """Save uploads. One ZIP is extracted safely; loose files are flattened."""
    destination.mkdir(parents=True, exist_ok=True)
    items = list(files)
    if not items:
        raise ArchiveError("هیچ فایلی ارسال نشده است.")
    if len(items) == 1 and Path(items[0][0]).suffix.lower() == ".zip":
        zip_path = destination.parent / "upload.zip"
        try:
            zip_path.write_bytes(items[0][1])
            return safe_extract_zip(zip_path, destination)
        finally:
            zip_path.unlink(missing_ok=True)
    if len(items) > MAX_ENTRIES:
        raise ArchiveError("تعداد فایل‌های ارسالی بیش از حد مجاز است.")
    total = 0
    seen: set[str] = set()
    for filename, content in items:
        # For loose files, directory structures are intentionally not trusted.
        name = Path(filename.replace("\\", "/")).name
        if not name or name in (".", "..") or "\x00" in name:
            raise ArchiveError("نام یکی از فایل‌های ارسالی معتبر نیست.")
        if name in seen:
            raise ArchiveError(f"نام تکراری در فایل‌های ارسالی: {name}")
        seen.add(name)
        if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ArchiveError(f"پسوند فایل پشتیبانی نمی‌شود: {Path(name).suffix}")
        if len(content) > MAX_SINGLE_FILE_BYTES:
            raise ArchiveError("حجم یکی از فایل‌ها بیش از حد مجاز است.")
        total += len(content)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ArchiveError("حجم کل فایل‌ها بیش از حد مجاز است.")
        (destination / name).write_bytes(content)
    index = [p for p in destination.iterdir() if p.is_file() and p.name.lower() == "index.html"]
    if not index:
        raise ArchiveError("در فایل‌های انتخاب‌شده باید index.html وجود داشته باشد.")
    if index[0].name != "index.html":
        index[0].rename(destination / "index.html")
    return destination
