#!/usr/bin/env python3
"""Prepare the pinned Titanium/Chromium native Android browser candidate.

This chooses Chromium itself as the Android application instead of pretending
chrome_public_apk is an AAR. Product-candidate builds use the released Android
package ID but ALWAYS a disposable key. They CANNOT be installed over v0.2.0.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

UPSTREAM_PACKAGE = "io.github.jqssun.helium"
RESEARCH_PACKAGE = "io.github.sopo9880.internet_browser.chromiumtest"
PRODUCT_PACKAGE = "io.github.sopo9880.internet_browser"
ALLOWED_PACKAGES = frozenset((RESEARCH_PACKAGE, PRODUCT_PACKAGE))
SOURCE_PACKAGE = f'chrome_public_manifest_package = "{UPSTREAM_PACKAGE}"'
SOURCE_CPU = 'target_cpu = "arm"'
ARM32_TARGET = (
    "autoninja -C out/Default chrome_public_apk\n"
    "mv $(find out/Default/apks -name 'Chrome*.apk') out/tmp/$VERSION-armeabi-v7a.apk\n"
    "sed -i 's/target_cpu = \"arm\"/target_cpu = \"arm64\"/' out/Default/args.gn\n"
)
ARM32_SIGN = "sign_apk out/tmp/$VERSION-armeabi-v7a.apk out/release/$VERSION-armeabi-v7a.apk\n"


def replace_exact(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError("Pinned upstream Chromium build template changed")
    return source.replace(before, after, 1)


def prepare_source(args: str, build: str, package: str) -> tuple[str, str]:
    if package not in ALLOWED_PACKAGES:
        raise ValueError("Only explicit research/product Android package IDs are allowed")
    args = replace_exact(args, SOURCE_PACKAGE,
                         f'chrome_public_manifest_package = "{package}"')
    args = replace_exact(args, SOURCE_CPU, 'target_cpu = "arm64"')
    build = replace_exact(build, ARM32_TARGET, "# ARM64-only native Chromium candidate\n")
    build = replace_exact(build, ARM32_SIGN, "")
    if "autoninja -C out/Default chrome_public_apk chrome_public_bundle" not in build:
        raise ValueError("Pinned upstream ARM64 Chromium APK build target missing")
    return args, build


def read_native_package(apk: Path, aapt2: Path) -> str:
    if not apk.is_file() or apk.stat().st_size == 0:
        raise ValueError("Compiled Chromium APK missing or empty")
    if not aapt2.is_file():
        raise ValueError("Android build-tools aapt2 missing")
    result = subprocess.run(
        [str(aapt2), "dump", "packagename", str(apk)],
        capture_output=True, text=True, check=True,
    )
    name = result.stdout.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", name):
        raise ValueError("aapt2 did not return an Android package name")
    return name


def verify_native_apk(apk: Path, aapt2: Path, package: str) -> None:
    if package not in ALLOWED_PACKAGES:
        raise ValueError("Unapproved package ID")
    actual = read_native_package(apk, aapt2)
    if actual != package:
        raise ValueError(f"Chromium APK package mismatch: {actual} != {package}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    config = sub.add_parser("configure")
    config.add_argument("--args", type=Path, required=True)
    config.add_argument("--build", type=Path, required=True)
    config.add_argument("--package", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--apk", type=Path, required=True)
    verify.add_argument("--aapt2", type=Path, required=True)
    verify.add_argument("--package", required=True)
    options = parser.parse_args()
    if options.command == "configure":
        before_args = options.args.read_text(encoding="utf-8")
        before_build = options.build.read_text(encoding="utf-8")
        patched_args, patched_build = prepare_source(
            before_args, before_build, options.package,
        )
        options.args.write_text(patched_args, encoding="utf-8")
        options.build.write_text(patched_build, encoding="utf-8")
        print(f"Configured pinned ARM64 Titanium Chromium for {options.package}")
    else:
        verify_native_apk(options.apk, options.aapt2, options.package)
        print(f"Verified REAL native Chromium APK package: {options.package}")


if __name__ == "__main__":
    main()
