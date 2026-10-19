#!/usr/bin/env python3
"""Fail-closed GATE for the real Titanium-native Android Chromium APK.

No fake Flutter AAR and no separately signed Chromium "research" APK count
as a release. The native candidate and its pinned source/provenance must
match exactly, and independent automated Android functional evidence is
required. No such evidence is produced yet: CI must NOT pass in its absence.
Phone-only acceptance is still post-release, not a substitute for CI tests.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from tool.chromium.titanium_pin import (
    CHROMIUM_VERSION, PRODUCT_PACKAGE, REQUIRED_ADBLOCK_ID,
    SOURCE_REPO, SOURCE_SHA, VANADIUM_SHA,
)

REQUIRED_AUTOMATED_CHECKS = (
    "native_browser_launch",
    "in_app_https_navigation",
    "tab_back_forward",
    "adblock_mv3_service_worker",
    "adblock_network_request_blocked",
    "byedpi_chromium_route",
    "offline_video_playback",
    "existing_library_migration",
    "android_settings_and_samsung_security_guide",
)

PROVENANCE_KIND = "CHROMIUM_NATIVE_PRODUCT_CANDIDATE_NOT_RELEASE"


def _read_json(path: str | None, label: str, errors: list[str]) -> dict:
    if not path or not Path(path).is_file():
        errors.append(f"Missing {label}. Real native Chromium compilation and CI integration tests required.")
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        errors.append(f"Invalid {label}: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object")
        return {}
    return data


def readiness_errors(
    apk: str | None,
    provenance: str | None,
    smoke_report: str | None,
    version: str,
    version_code: int,
    integration_commit: str = "",
) -> list[str]:
    errors: list[str] = []
    digest: str | None = None
    if not apk or not Path(apk).is_file() or Path(apk).stat().st_size == 0:
        errors.append("Missing actual Titanium-native Chromium product APK. Flutter APK is not acceptable.")
    else:
        digest = sha256(Path(apk).read_bytes()).hexdigest()

    report = _read_json(provenance, "pinned native Chromium provenance", errors)
    expected = {
        "kind": PROVENANCE_KIND,
        "engine_source": SOURCE_REPO,
        "engine_source_commit": SOURCE_SHA,
        "vanadium_source_commit": VANADIUM_SHA,
        "chromium_version_reference": CHROMIUM_VERSION,
        "candidate_android_package": PRODUCT_PACKAGE,
        "production_android_package_id": PRODUCT_PACKAGE,
        "production_id_matched": True,
        "built_as_chromium_android_application": True,
        "disposable_test_signer_not_upgrade_compatible": True,
        "app_version": version,
        "android_version_code": version_code,
        "required_adblock_id": REQUIRED_ADBLOCK_ID,
    }
    for key, value in expected.items():
        if report.get(key) != value:
            errors.append(f"Native Chromium provenance mismatch: {key}")
    if digest and report.get("apk_sha256") != digest:
        errors.append("Native Chromium binary does not match its source provenance SHA-256")
    if integration_commit and report.get("integration_commit") != integration_commit:
        errors.append("Native Chromium build is from a different GitHub commit")

    # The report MUST be produced by an actual automated emulator / device
    # instrumentation job against this exact APK. Never author canned pass JSON.
    smoke = _read_json(smoke_report, "real Android Chromium CI smoke report", errors)
    if smoke:
        if smoke.get("test_environment") != "android-ci-emulator":
            errors.append("Chrome smoke evidence must originate from Android CI emulator")
        if digest and smoke.get("apk_sha256") != digest:
            errors.append("Android smoke report tested a different APK")
        if integration_commit and smoke.get("integration_commit") != integration_commit:
            errors.append("Android smoke report targeted the wrong commit")
        checks = smoke.get("checks")
        for check in REQUIRED_AUTOMATED_CHECKS:
            if not isinstance(checks, dict) or checks.get(check) is not True:
                errors.append(f"Native Chromium integration incomplete: {check}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", required=True)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--smoke-report", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--version-code", required=True, type=int)
    parser.add_argument("--integration-commit", default="")
    args = parser.parse_args()
    if not re.fullmatch(r"0\.\d+\.\d+", args.version):
        parser.error("Only v0.x release versions are supported")
    if args.version_code <= 0:
        parser.error("Invalid Android versionCode")
    errors = readiness_errors(
        args.apk, args.provenance, args.smoke_report,
        args.version, args.version_code, args.integration_commit,
    )
    if errors:
        for error in errors:
            print(f"::error title=Native Chromium v0.x release blocker::{error}")
        return 1
    print("Native Chromium provenance and independent automated integration evidence passed.")
    print("Physical-device acceptance remains after release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
