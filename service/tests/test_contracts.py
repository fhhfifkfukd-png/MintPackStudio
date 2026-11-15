from pathlib import Path

import pytest
from pydantic import ValidationError

from service.app.config import BuildConfig, render_manifest

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android-template/app/src/main/java/com/mintpack/runtime"


def base_config(**overrides):
    values = {
        "app_name": "MintPack Test",
        "package_name": "org.example.mintpack",
        "version_name": "1.0.0",
        "version_code": 1,
    }
    values.update(overrides)
    return BuildConfig(**values)


def test_version_name_cannot_escape_apk_output_path():
    with pytest.raises(ValidationError):
        base_config(version_name="../../outside")


def test_rubika_mode_adds_only_required_runtime_permissions():
    config = base_config(rubika_mode=True)
    manifest = render_manifest(config)
    assert config.native_bridge and config.javascript_enabled and config.allow_internet
    assert 'android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC"' in manifest
    assert 'android:foregroundServiceType="dataSync"' in manifest
    assert '.RubikaPollingService' in manifest


def test_native_bridge_is_origin_scoped_and_does_not_use_legacy_interface():
    source = (ANDROID / "MainActivity.kt").read_text(encoding="utf-8")
    assert "WebViewCompat.addWebMessageListener" in source
    assert "setOf(APP_ORIGIN)" in source
    assert "!isMainFrame" in source
    assert "window.mintNative.onmessage" in source
    assert "addJavascriptInterface" not in source


def test_rubika_client_uses_fixed_https_api_origin():
    source = (ANDROID / "RubikaApi.kt").read_text(encoding="utf-8")
    assert '"https://botapi.rubika.ir"' in source
    assert '.addPathSegment("v3")' in source
    assert '.post(body)' in source
    assert "Log." not in source


def test_polling_uses_documented_offset_id_pair_and_persists_events_first():
    source = (ANDROID / "RubikaPollingService.kt").read_text(encoding="utf-8")
    assert 'payload.put("offset_id", it)' in source
    assert 'result.optString("next_offset_id")' in source
    assert source.index("store.enqueueUpdates(botId, updates)") < source.index(
        'store.saveOffset(botId, result.optString("next_offset_id")'
    )
    assert "POLL_INTERVAL_MS = 5_000L" in source


def test_tokens_are_kept_in_android_keystore_backed_storage():
    secret = (ANDROID / "SecretStore.kt").read_text(encoding="utf-8")
    store = (ANDROID / "BotStore.kt").read_text(encoding="utf-8")
    assert '"AndroidKeyStore"' in secret
    assert 'KeyProperties.BLOCK_MODE_GCM' in secret
    assert "secretStore.encrypt(token)" in store
    assert "putString(\"token.$id\", token)" not in store


def test_pending_rubika_updates_are_encrypted_before_cursor_persistence():
    store = (ANDROID / "BotStore.kt").read_text(encoding="utf-8")
    assert '"enc:" + secretStore.encrypt(encoded)' in store
    assert 'prefs.edit().putString("pending.$id", encrypted).commit()' in store
    assert 'prefs.edit().putString("offset.$id", value).commit()' in store


def test_rubika_mode_overrides_optional_permissions_and_internet_flags():
    config = base_config(rubika_mode=True, allow_internet=False, javascript_enabled=False,
                         native_bridge=False, permissions=[])
    assert config.allow_internet and config.javascript_enabled and config.native_bridge
    assert {"INTERNET", "FOREGROUND_SERVICE", "FOREGROUND_SERVICE_DATA_SYNC", "POST_NOTIFICATIONS"}.issubset(set(config.permissions))
