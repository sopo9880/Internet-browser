#!/usr/bin/env python3
"""Prepare the generated AndroidManifest.xml for browser network access.

Never place a permission between the XML prolog and the <manifest> root.
Validate XML after insertion and make repeated runs safe.
"""

from pathlib import Path
import os
import re
import xml.etree.ElementTree as ET

manifest = Path("android/app/src/main/AndroidManifest.xml")
if not manifest.exists():
    raise SystemExit("AndroidManifest.xml missing; run flutter create first.")

source = manifest.read_text(encoding="utf-8")
permissions = {
    "android.permission.INTERNET": '<uses-permission android:name="android.permission.INTERNET" />',
    "android.permission.FOREGROUND_SERVICE": '<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />',
    "android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK": '<uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK" />',
    "android.permission.POST_NOTIFICATIONS": '<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />',
    "android.permission.WAKE_LOCK": '<uses-permission android:name="android.permission.WAKE_LOCK" />',
    "android.permission.REQUEST_INSTALL_PACKAGES": (
        '<uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />'
    ),
}
for name, declaration in permissions.items():
    if name in source:
        continue
    opening = re.search(r"<manifest\b[^>]*>", source)
    if opening is None:
        raise SystemExit("AndroidManifest.xml has no manifest root.")
    source = source[:opening.end()] + "\n    " + declaration + source[opening.end():]

# Always respect Android system status/navigation bars (Flutter SafeArea).
# PiP requires an explicit resizable Activity; foreground playback service
# must be declared in the generated Android manifest.
if 'android:extractNativeLibs=' not in source:
    source = source.replace('<application',
        '<application android:extractNativeLibs="true"', 1)
if 'android:supportsPictureInPicture=' not in source:
    source = source.replace('<activity ',
        '<activity android:supportsPictureInPicture="true" android:resizeableActivity="true" ', 1)
if 'BrowserPlaybackService' not in source:
    source = source.replace('</application>',
        '    <service android:name=".BrowserPlaybackService" '
        'android:enabled="true" android:exported="false" '
        'android:foregroundServiceType="mediaPlayback" />\n    </application>', 1)

# Keep Kotlin method channels in source-controlled templates. Flutter's
# generated wrappers are ignored and regenerated in each CI job.
package_dir = Path('android/app/src/main/kotlin/io/github/sopo9880/internet_browser')
package_dir.mkdir(parents=True, exist_ok=True)
for filename in ('MainActivity.kt', 'BrowserPlaybackService.kt', 'EmbeddedChromiumRuntime.kt'):
    origin = Path('tool/android') / filename
    if not origin.is_file():
        raise SystemExit(f'Missing native Android template: {origin}')
    (package_dir / filename).write_bytes(origin.read_bytes())

app_gradle = Path('android/app/build.gradle.kts')
if app_gradle.exists():
    gradle = app_gradle.read_text(encoding='utf-8')
    if 'useLegacyPackaging = true' not in gradle:
        insertion = '    packaging {\n        jniLibs {\n            useLegacyPackaging = true\n        }\n    }\n'
        gradle = gradle.replace('android {', 'android {\n' + insertion, 1)
    app_gradle.write_text(gradle, encoding='utf-8')

# Chromium is no longer an external Chrome APK or WebView replacement intent.
# When a custom Chromium embedder library exists, statically link it INSIDE
# this app and verify its exact content hash and provider class.
engine_aar_env = os.environ.get("BROWSER_ANDROID_CHROMIUM_AAR")
engine_digest = os.environ.get("BROWSER_ANDROID_CHROMIUM_AAR_SHA256")
if engine_aar_env:
    if not engine_digest:
        raise SystemExit(
            "CHROMIUM_AAR set without BROWSER_ANDROID_CHROMIUM_AAR_SHA256"
        )
    from chromium.verify_runtime import verify_aar
    import shutil

    source_aar = Path(engine_aar_env).resolve()
    try:
        verify_aar(source_aar, engine_digest)
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"Chromium embedder AAR verification failed: {exc}")
    target_aar = Path("android/app/libs/chromium-engine.aar")
    target_aar.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_aar, target_aar)
    if not app_gradle.exists():
        raise SystemExit("Missing Gradle app file for Chromium engine linking")
    gradle = app_gradle.read_text(encoding="utf-8")
    dep = 'implementation(files("libs/chromium-engine.aar"))'
    if dep not in gradle:
        gradle += '\ndependencies {\n    ' + dep + '\n}\n'
        app_gradle.write_text(gradle, encoding="utf-8")
    print("Verified and linked Chromium embedder AAR; runtime validation pending")
elif engine_digest:
    raise SystemExit("Chromium engine SHA supplied without its AAR path")

try:
    root = ET.fromstring(source)
except ET.ParseError as exc:
    raise SystemExit(f"AndroidManifest.xml is invalid: {exc}") from exc

if root.tag != "manifest":
    raise SystemExit(f"Unexpected Android manifest root: {root.tag}")

manifest.write_text(source, encoding="utf-8")
print("Android manifest permission and XML validated.")


# GitHub-hosted Ubuntu 24.04 runners have NDK 27.3 preinstalled.
# Flutter 3.35 defaults to NDK 27.0 and attempts to download it if missing.
# CI explicitly selects the installed version to avoid a corrupt NDK download.
ndk_version = os.environ.get("BROWSER_ANDROID_NDK_VERSION")
if ndk_version:
    if not re.fullmatch(r"\d+\.\d+\.\d+", ndk_version):
        raise SystemExit(f"Invalid BROWSER_ANDROID_NDK_VERSION: {ndk_version}")
    sdk_dir = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not sdk_dir:
        raise SystemExit("ANDROID_SDK_ROOT or ANDROID_HOME is required for CI NDK")
    installed = Path(sdk_dir, "ndk", ndk_version, "source.properties")
    if not installed.is_file():
        raise SystemExit(f"NDK {ndk_version} not present: {installed}")
    build_gradle = Path("android/app/build.gradle.kts")
    gradle = build_gradle.read_text(encoding="utf-8")
    target = "ndkVersion = flutter.ndkVersion"
    if target not in gradle:
        raise SystemExit("Flutter template changed: missing ndkVersion entry")
    gradle = gradle.replace(target, f'ndkVersion = "{ndk_version}"', 1)
    build_gradle.write_text(gradle, encoding="utf-8")
    print(f"Using runner-preinstalled Android NDK {ndk_version}")
