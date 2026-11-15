from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Callable

from .config import BuildConfig, render_manifest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "android-template"


class BuildError(RuntimeError):
    pass


def _gradle_bin() -> str:
    return os.getenv("GRADLE_BIN", "gradle")


def _find_apksigner() -> str | None:
    found = shutil.which("apksigner")
    if found:
        return found
    sdk = os.getenv("ANDROID_SDK_ROOT") or os.getenv("ANDROID_HOME")
    if not sdk:
        return None
    candidates = list((Path(sdk) / "build-tools").glob("*/apksigner"))
    def version_key(path: Path) -> tuple[int, ...]:
        match = re.findall(r"\d+", path.parent.name)
        return tuple(int(part) for part in match) if match else (0,)
    candidates.sort(key=version_key, reverse=True)
    return str(candidates[0]) if candidates else None


def _write_android_config(project: Path, config: BuildConfig, web_root: Path, app_icon: tuple[bytes, str] | None = None, splash_image: tuple[bytes, str] | None = None) -> None:
    app = project / "app"
    site = app / "src/main/assets/site"
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(web_root, site, symlinks=False)
    (app / "src/main/AndroidManifest.xml").write_text(render_manifest(config), encoding="utf-8")
    values = app / "src/main/res/values"
    values.mkdir(parents=True, exist_ok=True)
    (values / "strings.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        f'    <string name="app_name">{config.app_name.replace("&", "&amp;").replace("<", "&lt;")}</string>\n'
        '</resources>\n', encoding="utf-8"
    )
    drawable = app / "src/main/res/drawable"
    drawable_nodpi = app / "src/main/res/drawable-nodpi"
    drawable.mkdir(parents=True, exist_ok=True)
    drawable_nodpi.mkdir(parents=True, exist_ok=True)
    if app_icon:
        for old in drawable.glob("mintpack_icon.*"):
            old.unlink(missing_ok=True)
        suffix = app_icon[1]
        (drawable_nodpi / f"mintpack_icon.{suffix}").write_bytes(app_icon[0])
    if splash_image:
        for old in drawable.glob("mintpack_splash.*"):
            old.unlink(missing_ok=True)
        suffix = splash_image[1]
        (drawable_nodpi / f"mintpack_splash.{suffix}").write_bytes(splash_image[0])

    settings = {
        "javascriptEnabled": config.javascript_enabled,
        "offlineStorage": config.offline_storage,
        "allowInternet": config.allow_internet,
        "nativeBridgeEnabled": config.native_bridge,
        "rubikaMode": config.rubika_mode,
        "fullScreen": config.full_screen,
        "statusBarColor": config.status_bar_color,
        "navigationBarColor": config.navigation_bar_color,
    }
    assets = app / "src/main/assets"
    (assets / "mintpack-config.json").write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")


def build_release(
    web_root: Path,
    config: BuildConfig,
    keystore_path: Path,
    key_alias: str,
    store_password: str,
    key_password: str,
    output_dir: Path,
    progress: Callable[[int, str], None] | None = None,
    app_icon: tuple[bytes, str] | None = None,
    splash_image: tuple[bytes, str] | None = None,
) -> Path:
    """Build and verify a genuine signed Android release APK using Gradle."""
    progress = progress or (lambda _p, _m: None)
    if not TEMPLATE.is_dir():
        raise BuildError("قالب Android پیدا نشد.")
    if not keystore_path.is_file():
        raise BuildError("فایل keystore وجود ندارد.")
    if not key_alias or not store_password or not key_password:
        raise BuildError("اطلاعات امضای APK ناقص است.")
    output_dir.mkdir(parents=True, exist_ok=True)
    work = output_dir / "android-project"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(TEMPLATE, work, ignore=shutil.ignore_patterns(".gradle", "build", ".idea"))
    _write_android_config(work, config, web_root, app_icon, splash_image)
    progress(25, "پروژه Android و Manifest تولید شد.")

    # Do not pass the build-service API key or unrelated secrets to Gradle.
    passthrough = (
        "PATH", "HOME", "USER", "TMPDIR", "TEMP", "TMP", "JAVA_HOME",
        "ANDROID_SDK_ROOT", "ANDROID_HOME", "ANDROID_USER_HOME", "GRADLE_USER_HOME",
        "LANG", "LC_ALL",
    )
    env = {name: os.environ[name] for name in passthrough if name in os.environ}
    env.update({
        "MINTPACK_KEYSTORE_FILE": str(keystore_path.resolve()),
        "MINTPACK_STORE_PASSWORD": store_password,
        "MINTPACK_KEY_ALIAS": key_alias,
        "MINTPACK_KEY_PASSWORD": key_password,
        "GRADLE_OPTS": "-Dorg.gradle.daemon=false -Dorg.gradle.parallel=false",
    })
    command = [
        _gradle_bin(), "--no-daemon", "--stacktrace",
        f"-PmintpackPackageName={config.package_name}",
        f"-PmintpackVersionName={config.version_name}",
        f"-PmintpackVersionCode={config.version_code}",
        f"-PmintpackTargetSdk={config.target_sdk}",
        "assembleRelease",
    ]
    progress(35, "Gradle در حال کامپایل پروژه است.")
    try:
        run = subprocess.run(command, cwd=work, env=env, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=int(os.getenv("BUILD_TIMEOUT_SECONDS", "1800")))
    except FileNotFoundError as exc:
        raise BuildError("Gradle پیدا نشد؛ GRADLE_BIN را تنظیم کنید و Android SDK را نصب کنید.") from exc
    except subprocess.TimeoutExpired as exc:
        raise BuildError("زمان مجاز ساخت به پایان رسید.") from exc
    finally:
        # Do not keep signing secrets in the child process environment longer than necessary.
        for key in ("MINTPACK_KEYSTORE_FILE", "MINTPACK_STORE_PASSWORD", "MINTPACK_KEY_ALIAS", "MINTPACK_KEY_PASSWORD"):
            env.pop(key, None)
    if run.returncode != 0:
        # Raw Gradle output can contain user source snippets; never return it through the API.
        raise BuildError("Gradle ساخت را ناموفق اعلام کرد؛ جزئیات خام خروجی برای جلوگیری از افشای کد/اطلاعات خصوصی به API ارسال نشد.")

    candidates = list((work / "app/build/outputs/apk/release").glob("*.apk"))
    if len(candidates) != 1:
        raise BuildError("خروجی APK یکتا در مسیر release پیدا نشد.")
    apk = candidates[0]
    if not apk.is_file() or apk.stat().st_size < 20_000 or not zipfile.is_zipfile(apk):
        raise BuildError("فایل خروجی APK معتبر نیست.")
    with zipfile.ZipFile(apk) as archive:
        names = set(archive.namelist())
        if "AndroidManifest.xml" not in names or "classes.dex" not in names:
            raise BuildError("فایل APK فاقد Manifest یا DEX است.")

    apksigner = _find_apksigner()
    if not apksigner:
        raise BuildError("APK تولید شد اما apksigner برای اعتبارسنجی امضا در PATH یا Android SDK پیدا نشد؛ خروجی تأیید نشد.")
    progress(90, "در حال اعتبارسنجی امضای APK است.")
    verify = subprocess.run([apksigner, "verify", "--verbose", str(apk)], env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    if verify.returncode != 0:
        raise BuildError("اعتبارسنجی امضای APK ناموفق بود: " + "\n".join(verify.stdout.splitlines()[-15:]))

    output_dir.mkdir(parents=True, exist_ok=True)
    final_apk = output_dir / f"{config.package_name.replace('.', '_')}-{config.version_name}.apk"
    shutil.copy2(apk, final_apk)
    progress(100, "APK واقعی ساخته و امضا شده است.")
    return final_apk
