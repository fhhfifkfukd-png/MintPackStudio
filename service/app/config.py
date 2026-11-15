from __future__ import annotations

import re
from html import escape
from pydantic import BaseModel, Field, field_validator, model_validator

ALLOWED_PERMISSIONS = {
    "INTERNET", "ACCESS_NETWORK_STATE", "POST_NOTIFICATIONS", "VIBRATE",
    "FOREGROUND_SERVICE", "FOREGROUND_SERVICE_DATA_SYNC", "RECEIVE_BOOT_COMPLETED"
}
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")


class BuildConfig(BaseModel):
    app_name: str = Field(min_length=1, max_length=48)
    package_name: str
    version_name: str = Field(min_length=1, max_length=24)
    version_code: int = Field(ge=1, le=2_100_000_000)
    target_sdk: int = Field(default=36, ge=35, le=36)
    orientation: str = "portrait"
    status_bar_color: str = "#17152d"
    navigation_bar_color: str = "#ffffff"
    full_screen: bool = False
    javascript_enabled: bool = True
    offline_storage: bool = True
    allow_internet: bool = True
    native_bridge: bool = False
    rubika_mode: bool = False
    permissions: list[str] = Field(default_factory=lambda: ["INTERNET"])

    @field_validator("app_name")
    @classmethod
    def app_name_is_safe(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(ch) < 32 for ch in value):
            raise ValueError("نام برنامه خالی یا دارای نویسه کنترلی است.")
        return value

    @field_validator("version_name")
    @classmethod
    def version_name_is_safe(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,23}", value):
            raise ValueError("نسخه باید فقط شامل حروف، اعداد، نقطه، +، _ یا - باشد.")
        return value

    @field_validator("package_name")
    @classmethod
    def package_is_valid(cls, value: str) -> str:
        if not PACKAGE_RE.fullmatch(value):
            raise ValueError("Package Name معتبر نیست.")
        return value

    @field_validator("orientation")
    @classmethod
    def orientation_is_valid(cls, value: str) -> str:
        if value not in {"portrait", "landscape", "sensor"}:
            raise ValueError("جهت صفحه معتبر نیست.")
        return value

    @field_validator("status_bar_color", "navigation_bar_color")
    @classmethod
    def color_is_valid(cls, value: str) -> str:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("رنگ باید با قالب #RRGGBB باشد.")
        return value.lower()

    @field_validator("permissions")
    @classmethod
    def permissions_are_allowed(cls, values: list[str]) -> list[str]:
        unknown = set(values) - ALLOWED_PERMISSIONS
        if unknown:
            raise ValueError("مجوز پشتیبانی‌نشده: " + ", ".join(sorted(unknown)))
        return sorted(set(values))

    @model_validator(mode="after")
    def cross_validate(self):
        if self.rubika_mode:
            self.allow_internet = True
            self.javascript_enabled = True
            self.native_bridge = True
            self.permissions = sorted(set(self.permissions) | {"INTERNET", "ACCESS_NETWORK_STATE", "FOREGROUND_SERVICE", "FOREGROUND_SERVICE_DATA_SYNC", "POST_NOTIFICATIONS"})
        if "FOREGROUND_SERVICE_DATA_SYNC" in self.permissions and "FOREGROUND_SERVICE" not in self.permissions:
            self.permissions.append("FOREGROUND_SERVICE")
        if self.native_bridge and (not self.allow_internet or not self.javascript_enabled):
            raise ValueError("پل بومی به JavaScript و اینترنت نیاز دارد.")
        if "RECEIVE_BOOT_COMPLETED" in self.permissions and "POST_NOTIFICATIONS" not in self.permissions:
            raise ValueError("برای نمایش یادآوری پس از روشن شدن گوشی، مجوز اعلان‌ها را هم انتخاب کنید.")
        if self.allow_internet and "INTERNET" not in self.permissions:
            self.permissions.append("INTERNET")
        if not self.allow_internet:
            self.permissions = [p for p in self.permissions if p != "INTERNET"]
        return self


def manifest_permissions(config: BuildConfig) -> str:
    return "\n    ".join(
        f'<uses-permission android:name="android.permission.{name}" />'
        for name in config.permissions
    )


def render_manifest(config: BuildConfig) -> str:
    service = ""
    if "FOREGROUND_SERVICE_DATA_SYNC" in config.permissions:
        service = '''\n        <service android:name=".RubikaPollingService" android:exported="false" android:foregroundServiceType="dataSync" />'''
    receiver = ""
    if "RECEIVE_BOOT_COMPLETED" in config.permissions:
        receiver = '''\n        <receiver android:name=".BootNoticeReceiver" android:enabled="true" android:exported="false">\n            <intent-filter><action android:name="android.intent.action.BOOT_COMPLETED" /></intent-filter>\n        </receiver>'''
    return f'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    {manifest_permissions(config)}
    <application android:allowBackup="false" android:supportsRtl="true" android:label="{escape(config.app_name)}" android:icon="@drawable/mintpack_icon" android:usesCleartextTraffic="false" android:theme="@style/MintPackTheme">
        <activity android:name=".MainActivity" android:exported="true" android:screenOrientation="{config.orientation}" android:configChanges="orientation|screenSize|keyboardHidden">
            <intent-filter><action android:name="android.intent.action.MAIN" /><category android:name="android.intent.category.LAUNCHER" /></intent-filter>
        </activity>{service}{receiver}
    </application>
</manifest>
'''
