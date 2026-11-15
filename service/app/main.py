from __future__ import annotations

import hmac
import json
import os
import shutil
import tempfile
import time
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .archive import ArchiveError, save_uploaded_files
from .builder import BuildError, build_release
from .config import BuildConfig

VERSION = "0.1.0"
DATA_DIR = Path(os.getenv("MINTPACK_DATA_DIR", "./mintpack-data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
API_KEY = os.getenv("MINTPACK_API_KEY", "")
CORS_ORIGINS = [x.strip() for x in os.getenv(
    "MINTPACK_CORS_ORIGINS",
    "http://localhost:8080,http://127.0.0.1:8080,https://appassets.androidplatform.net"
).split(",") if x.strip()]

app = FastAPI(title="MintPack Studio Build Service", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)
executor = ThreadPoolExecutor(max_workers=int(os.getenv("BUILD_WORKERS", "1")))
lock = threading.RLock()
jobs: dict[str, dict[str, Any]] = {}
previews: dict[str, Path] = {}
PREVIEW_TTL_SECONDS = 24 * 60 * 60


def _prune_previews() -> None:
    base = DATA_DIR / "previews"
    if not base.exists():
        return
    cutoff = time.time() - PREVIEW_TTL_SECONDS
    for folder in base.iterdir():
        if folder.is_dir():
            try:
                if folder.stat().st_mtime < cutoff:
                    shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                continue
    with lock:
        for preview_id, root in list(previews.items()):
            if not root.exists():
                previews.pop(preview_id, None)
        while len(previews) > 50:
            oldest_id, _oldest_root = next(iter(previews.items()))
            previews.pop(oldest_id, None)
            shutil.rmtree(base / oldest_id, ignore_errors=True)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not API_KEY or len(API_KEY) < 32:
        raise HTTPException(status_code=503, detail="Build service is not configured: set a 32+ character MINTPACK_API_KEY")
    if not x_api_key or not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="کلید دسترسی سرویس معتبر نیست.")


def _is_image(data: bytes, suffix: str) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n") if suffix == "png" else data.startswith(b"\xff\xd8\xff")


async def read_project_uploads(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if not files:
        raise HTTPException(status_code=400, detail="فایل پروژه ارسال نشده است.")
    results = []
    total = 0
    max_total = 200 * 1024 * 1024
    for item in files:
        if item.size is not None and total + item.size > max_total:
            raise HTTPException(status_code=413, detail="حجم کل فایل‌های ارسالی بیش از ۲۰۰ مگابایت است.")
        chunks: list[bytes] = []
        current_size = 0
        while True:
            chunk = await item.read(1024 * 1024)
            if not chunk:
                break
            current_size += len(chunk)
            total += len(chunk)
            if total > max_total:
                raise HTTPException(status_code=413, detail="حجم کل فایل‌های ارسالی بیش از ۲۰۰ مگابایت است.")
            chunks.append(chunk)
        results.append((item.filename or "upload.bin", b"".join(chunks)))
    return results


@app.get("/health")
def health(_: None = Depends(require_api_key)):
    return {"status": "ok", "version": VERSION, "builder": "Gradle Android APK"}


@app.post("/api/inspect")
async def inspect_project(project_files: list[UploadFile] = File(...), _: None = Depends(require_api_key)):
    _prune_previews()
    incoming = await read_project_uploads(project_files)
    preview_id = uuid.uuid4().hex
    folder = DATA_DIR / "previews" / preview_id
    try:
        web_root = save_uploaded_files(incoming, folder / "source")
    except ArchiveError as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Report original ZIP location to the user while preview paths are rooted
    # at the discovered web root (as they will be in the packaged APK).
    source_entrypoint = (web_root.relative_to(folder / "source") / "index.html").as_posix()
    index_path = "index.html"
    with lock:
        previews[preview_id] = web_root
        # Bound both the in-memory registry and on-disk preview folders.
        while len(previews) > 50:
            oldest, _old_root = next(iter(previews.items()))
            previews.pop(oldest, None)
            shutil.rmtree(DATA_DIR / "previews" / oldest, ignore_errors=True)
    return {
        "valid": True,
        "preview_id": preview_id,
        "entrypoint": source_entrypoint,
        "preview_url": f"/api/previews/{preview_id}/{index_path}",
    }


@app.delete("/api/previews/{preview_id}")
def delete_preview(preview_id: str, _: None = Depends(require_api_key)):
    with lock:
        root = previews.pop(preview_id, None)
    if root is None:
        raise HTTPException(status_code=404, detail="پیش‌نمایش پیدا نشد یا قبلاً حذف شده است.")
    shutil.rmtree(DATA_DIR / "previews" / preview_id, ignore_errors=True)
    return {"deleted": True}


@app.get("/api/previews/{preview_id}/{asset_path:path}")
def preview_asset(preview_id: str, asset_path: str):
    with lock:
        root = previews.get(preview_id)
    if root is None:
        raise HTTPException(status_code=404, detail="پیش‌نمایش منقضی یا پیدا نشد.")
    target = (root / asset_path).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise HTTPException(status_code=400, detail="مسیر نامعتبر است.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="فایل پیش‌نمایش پیدا نشد.")
    response = FileResponse(target, headers={
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox allow-scripts; default-src 'self' https: http: data: blob:; script-src 'self' 'unsafe-inline' https: http:; style-src 'self' 'unsafe-inline' https: http:; img-src 'self' data: blob: https: http:; font-src 'self' data: https: http:; object-src 'none'; base-uri 'self'; form-action 'none'",
        "Referrer-Policy": "no-referrer",
    })
    return response


def _set_job(job_id: str, **values: Any) -> None:
    with lock:
        if job_id in jobs:
            jobs[job_id].update(values)


def _run_build(job_id: str, web_root: Path, config: BuildConfig, keystore: Path,
               key_alias: str, store_password: str, key_password: str, job_dir: Path,
               app_icon: tuple[bytes, str] | None, splash_image: tuple[bytes, str] | None) -> None:
    def progress(percent: int, message: str) -> None:
        _set_job(job_id, status="building", progress=percent, message=message)
    try:
        progress(20, "در حال آماده‌سازی قالب Kotlin و منابع وب...")
        apk = build_release(web_root, config, keystore, key_alias, store_password,
                            key_password, job_dir / "output", progress, app_icon, splash_image)
        _set_job(job_id, status="succeeded", progress=100,
                 message="APK واقعی ساخته و امضای آن با apksigner بررسی شد.",
                 artifact=apk.name, download_url=f"/api/jobs/{job_id}/download")
    except BuildError as exc:
        # Only controlled errors are surfaced. Raw Gradle output may contain user source or secrets.
        _set_job(job_id, status="failed", progress=0, message=str(exc)[:500])
    except Exception:
        _set_job(job_id, status="failed", progress=0,
                 message="خطای داخلی هنگام ساخت رخ داد؛ خروجی خام ابزارها در پاسخ API نمایش داده نمی‌شود.")
    finally:
        try:
            keystore.unlink(missing_ok=True)
            shutil.rmtree(job_dir / "android-project", ignore_errors=True)
            shutil.rmtree(job_dir / "project-upload", ignore_errors=True)
        except OSError:
            pass


@app.post("/api/build", status_code=202)
async def start_build(
    project_files: list[UploadFile] = File(...),
    config: str = Form(...),
    keystore: UploadFile = File(...),
    key_alias: str = Form(...),
    store_password: str = Form(...),
    key_password: str = Form(...),
    app_icon: UploadFile | None = File(default=None),
    splash_image: UploadFile | None = File(default=None),
    _: None = Depends(require_api_key),
):
    with lock:
        active_jobs = sum(1 for job in jobs.values() if job.get("status") in {"queued", "building"})
    if active_jobs >= int(os.getenv("MAX_PENDING_JOBS", "3")):
        raise HTTPException(status_code=429, detail="ظرفیت صف ساخت پر است؛ پس از پایان یک Job دوباره تلاش کنید.")
    try:
        parsed_config = BuildConfig.model_validate_json(config)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="تنظیمات ساخت معتبر نیستند.") from exc
    if not (keystore.filename or "").lower().endswith((".jks", ".keystore")):
        raise HTTPException(status_code=400, detail="فایل امضا باید JKS یا KEYSTORE باشد.")
    if keystore.size is not None and keystore.size > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم فایل keystore خالی یا بیش از ۲۰ مگابایت است.")
    key_bytes = await keystore.read(20 * 1024 * 1024 + 1)
    if not key_bytes or len(key_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم فایل keystore خالی یا بیش از ۲۰ مگابایت است.")
    if not key_alias.strip() or not store_password or not key_password:
        raise HTTPException(status_code=400, detail="اطلاعات امضای APK کامل نیست.")
    def read_optional_image(upload: UploadFile | None) -> tuple[bytes, str] | None:
        if upload is None:
            return None
        name = (upload.filename or "").lower()
        if name.endswith(".png"):
            suffix = "png"
        elif name.endswith((".jpg", ".jpeg")):
            suffix = "jpg"
        else:
            raise HTTPException(status_code=400, detail="آیکون و تصویر شروع باید PNG یا JPEG باشند.")
        if upload.size is not None and upload.size > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="آیکون و تصویر شروع باید حداکثر ۵ مگابایت باشند.")
        return (b"", suffix)  # bytes are read asynchronously below
    icon_meta = read_optional_image(app_icon)
    splash_meta = read_optional_image(splash_image)
    if app_icon is not None:
        icon_bytes = await app_icon.read(5 * 1024 * 1024 + 1)
        if len(icon_bytes) > 5 * 1024 * 1024 or not _is_image(icon_bytes, icon_meta[1]):
            raise HTTPException(status_code=400, detail="فایل آیکون خراب یا بزرگ‌تر از ۵ مگابایت است.")
        icon_meta = (icon_bytes, icon_meta[1])
    if splash_image is not None:
        splash_bytes = await splash_image.read(5 * 1024 * 1024 + 1)
        if len(splash_bytes) > 5 * 1024 * 1024 or not _is_image(splash_bytes, splash_meta[1]):
            raise HTTPException(status_code=400, detail="تصویر شروع خراب یا بزرگ‌تر از ۵ مگابایت است.")
        splash_meta = (splash_bytes, splash_meta[1])
    incoming = await read_project_uploads(project_files)
    job_id = uuid.uuid4().hex
    job_dir = DATA_DIR / "jobs" / job_id
    project_dir = job_dir / "project-upload"
    try:
        web_root = save_uploaded_files(incoming, project_dir)
    except ArchiveError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_dir.mkdir(parents=True, exist_ok=True)
    key_path = job_dir / "signing-upload.jks"
    key_path.write_bytes(key_bytes)
    with lock:
        jobs[job_id] = {"job_id": job_id, "status": "queued", "progress": 5,
                        "message": "در صف ساخت قرار گرفت.", "artifact": None, "download_url": None}
    executor.submit(_run_build, job_id, web_root, parsed_config, key_path,
                    key_alias.strip(), store_password, key_password, job_dir, icon_meta, splash_meta)
    return {"job_id": job_id, "status": "queued", "message": "درخواست ساخت ثبت شد."}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, _: None = Depends(require_api_key)):
    with lock:
        result = jobs.get(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job پیدا نشد.")
    return result


@app.get("/api/jobs/{job_id}/download")
def download_apk(job_id: str, _: None = Depends(require_api_key)):
    with lock:
        job = jobs.get(job_id)
    if not job or job.get("status") != "succeeded" or not job.get("artifact"):
        raise HTTPException(status_code=404, detail="APK آماده دانلود نیست.")
    file_path = DATA_DIR / "jobs" / job_id / "output" / job["artifact"]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="فایل خروجی پیدا نشد.")
    return FileResponse(file_path, media_type="application/vnd.android.package-archive",
                        filename=file_path.name, headers={"Cache-Control": "no-store"})


@app.exception_handler(Exception)
async def safe_unhandled_error(_request, _exc):
    return JSONResponse(status_code=500, content={"detail": "خطای داخلی سرویس؛ جزئیات خصوصی در پاسخ نمایش داده نمی‌شود."})
