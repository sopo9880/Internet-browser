#!/usr/bin/env python3
"""Prepare the pinned Titanium/Chromium native Android browser candidate.

This chooses Chromium itself as the Android application. Signing is deliberately
separate: the caller must verify the original release certificate for upgrades.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shlex
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


def prepare_source(
    args: str,
    build: str,
    package: str,
    *,
    version_code: int | None = None,
    version_name: str | None = None,
    ninja_jobs: int | None = None,
    sync_jobs: int | None = None,
    preprovisioned_deps: bool = False,
    product_overlay: bool = False,
) -> tuple[str, str]:
    if package not in ALLOWED_PACKAGES:
        raise ValueError("Only explicit research/product Android package IDs are allowed")
    if package == PRODUCT_PACKAGE:
        if version_code is None or version_name is None:
            raise ValueError("Chromium product versionCode/versionName must both be explicit")
        if version_code is not None:
            if not (2_000_002 <= version_code <= 2_100_000_000):
                raise ValueError("Chromium versionCode must increase beyond v0.2.0")
            if not re.fullmatch(r"0\.[0-9]+\.[0-9]+", version_name or ""):
                raise ValueError("Production Chromium requires 0.x versionName")
            _, minor, patch = map(int, version_name.split('.'))
            version_base = minor * 1_000_000 + patch * 1000
            if not version_base < version_code <= version_base + 999:
                raise ValueError("Native versionCode does not match the product versionName")
            # Chromium GN recognizes both overrides for chrome_public_apk.
            # Without this, Chromium's upstream versionCode can break upgrades.
            if "android_override_version_code" in args or "android_override_version_name" in args:
                raise ValueError("Upstream version overrides unexpectedly present")
            args += (
                f'\nandroid_override_version_code = "{version_code}"\n'
                f'android_override_version_name = "{version_name}"\n'
            )
    elif version_code is not None or version_name is not None:
        raise ValueError("Research builds must not impersonate release metadata")
    args = replace_exact(args, SOURCE_PACKAGE,
                         f'chrome_public_manifest_package = "{package}"')
    args = replace_exact(args, SOURCE_CPU, 'target_cpu = "arm64"')
    # Upstream Titanium targets Android ARM64; V8 DrumBrake is not supported
    # on Android, including the arm64 build (the upstream GN args enable it).
    # A silent GN failure previously cascaded into "missing APK" errors.
    args = replace_exact(args, "v8_enable_drumbrake = true",
                         "v8_enable_drumbrake = false")
    args = replace_exact(args, "v8_drumbrake_bounds_checks = true",
                         "v8_drumbrake_bounds_checks = false")
    # Pinned upstream build.sh does not fail on git am failures: gclient
    # then fetches dependencies for a Chromium tree with NO Titanium patches.
    # Keep git am and patch errors fatal, not just the last sign_apk error.
    build = replace_exact(
        build, "#!/bin/bash\nsource common.sh\n",
        "#!/bin/bash\nset -e\nset -o pipefail\nsource common.sh\n",
    )
    build = replace_exact(build, ARM32_TARGET, "# ARM64-only native Chromium candidate\n")
    build = replace_exact(build, ARM32_SIGN, "")
    arm64_target = "autoninja -C out/Default chrome_public_apk chrome_public_bundle"
    if build.count(arm64_target) != 1:
        raise ValueError("Pinned upstream ARM64 Chromium APK build target missing")
    if ninja_jobs is not None:
        if not isinstance(ninja_jobs, int) or not 1 <= ninja_jobs <= 8:
            raise ValueError("Chromium ninja job count must be 1..8")
        build = replace_exact(
            build, arm64_target,
            f"autoninja -j {ninja_jobs} -C out/Default chrome_public_apk chrome_public_bundle",
        )
    if sync_jobs is not None:
        if not isinstance(sync_jobs, int) or not 1 <= sync_jobs <= 4:
            raise ValueError("Chromium gclient job count must be 1..4")
        build = replace_exact(
            build, "gclient sync -D --no-history --nohooks",
            f"gclient sync -j {sync_jobs} -D --no-history --nohooks",
        )
    if preprovisioned_deps:
        # The runner administrator provisions dependencies once. A build only
        # checks them; it cannot silently invoke sudo or change the machine.
        system_install = (
            "sudo apt-get update\n"
            "sudo apt-get install -y sudo lsb-release file nano git curl python3 python3-pillow imagemagick librsvg2-bin\n"
            "sudo dpkg --add-architecture i386; sudo apt-get update; sudo apt-get install -y libgcc-s1:i386\n"
        )
        build = replace_exact(build, system_install,
                              "# System dependencies are preprovisioned.\n")
        build = replace_exact(build,
            "./build/install-build-deps.sh --no-prompt",
            "python3 build/install-build-deps.py --quick-check --android --no-arm --no-chromeos-fonts")
        if re.search(r"(?m)^\s*sudo\s", build):
            raise ValueError("Unexpected privileged command in pinned build template")
    if product_overlay:
        if package != PRODUCT_PACKAGE:
            raise ValueError('Product overlay requires the explicit product package')
        script = Path(__file__).resolve().with_name('prepare_android_product.py')
        hooks = script.with_name('prepare_android_hooks.py')
        build = replace_exact(build, 'gclient runhooks\n',
            f'python3 {shlex.quote(str(hooks))} --source "$SCRIPT_DIR"\n'
            'gclient runhooks\n')
        build = replace_exact(build, 'source $SCRIPT_DIR/patch.sh\n',
            'source $SCRIPT_DIR/patch.sh\n'
            f'python3 {shlex.quote(str(script))} --checkout "$PWD"\n')
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


def verify_native_apk(
    apk: Path,
    aapt2: Path,
    package: str,
    *,
    version_code: int | None = None,
    version_name: str | None = None,
) -> None:
    if package not in ALLOWED_PACKAGES:
        raise ValueError("Unapproved package ID")
    actual = read_native_package(apk, aapt2)
    if actual != package:
        raise ValueError(f"Chromium APK package mismatch: {actual} != {package}")
    if version_code is not None or version_name is not None:
        if version_code is None or not version_name:
            raise ValueError("Version code and name must be supplied together")
        output = subprocess.run(
            [str(aapt2), "dump", "badging", str(apk)],
            capture_output=True, text=True, check=True,
        ).stdout
        manifest = next((line for line in output.splitlines()
                         if line.startswith("package:")), "")
        if (f"versionCode='{version_code}'" not in manifest or
                f"versionName='{version_name}'" not in manifest):
            raise ValueError(
                "Native Chromium APK manifest version does not match requested "
                f"versionCode={version_code} versionName={version_name}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    config = sub.add_parser("configure")
    config.add_argument("--args", type=Path, required=True)
    config.add_argument("--build", type=Path, required=True)
    config.add_argument("--package", required=True)
    config.add_argument("--version-code", type=int)
    config.add_argument("--version-name")
    config.add_argument("--ninja-jobs", type=int)
    config.add_argument("--sync-jobs", type=int)
    config.add_argument("--preprovisioned-deps", action="store_true")
    config.add_argument("--product-overlay", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("--apk", type=Path, required=True)
    verify.add_argument("--aapt2", type=Path, required=True)
    verify.add_argument("--package", required=True)
    verify.add_argument("--version-code", type=int)
    verify.add_argument("--version-name")
    options = parser.parse_args()
    if options.command == "configure":
        before_args = options.args.read_text(encoding="utf-8")
        before_build = options.build.read_text(encoding="utf-8")
        patched_args, patched_build = prepare_source(
            before_args, before_build, options.package,
            version_code=options.version_code, version_name=options.version_name,
            ninja_jobs=options.ninja_jobs, sync_jobs=options.sync_jobs,
            preprovisioned_deps=options.preprovisioned_deps,
            product_overlay=options.product_overlay,
        )
        options.args.write_text(patched_args, encoding="utf-8")
        options.build.write_text(patched_build, encoding="utf-8")
        print(f"Configured pinned ARM64 Titanium Chromium for {options.package}")
    else:
        verify_native_apk(
            options.apk, options.aapt2, options.package,
            version_code=options.version_code, version_name=options.version_name,
        )
        print(f"Verified REAL native Chromium APK package: {options.package}")


if __name__ == "__main__":
    main()
