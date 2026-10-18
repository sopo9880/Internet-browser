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
permission = '<uses-permission android:name="android.permission.INTERNET" />'
if "android.permission.INTERNET" not in source:
    opening = re.search(r"<manifest\b[^>]*>", source)
    if opening is None:
        raise SystemExit("AndroidManifest.xml has no manifest root.")
    source = source[:opening.end()] + "\n    " + permission + source[opening.end():]

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
