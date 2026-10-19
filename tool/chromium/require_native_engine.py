#!/usr/bin/env python3
"""v0.2.1 gate: a compiled Flutter shell is not a usable Chromium browser.

A native Chromium AAR must be linked into the Android app and verified by
automated in-app navigation, extensions and DPI integration tests. This script
does not build the currently missing runtime or fabricate acceptance proof.
Device-only acceptance is post-release, per project policy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

from tool.chromium.verify_runtime import verify_aar

REQUIRED_AUTOMATED_CHECKS = (
    "native_engine_initialized",
    "in_app_https_navigation",
    "tab_back_forward",
    "extension_host_initialized",
    "byedpi_route_connected",
    "offline_media_player_available",
    "existing_settings_retained",
)


def readiness_errors(
    aar_path: str | None,
    aar_digest: str | None,
    report_path: str | None,
) -> list[str]:
    errors: list[str] = []
    if not aar_path or not aar_digest:
        errors.append(
            "Missing real EMBEDDED Chromium AAR and matching SHA-256. "
            "The standalone Titanium research APK cannot be embedded as an AAR."
        )
    else:
        try:
            verify_aar(Path(aar_path), aar_digest)
        except (ValueError, FileNotFoundError, OSError) as exc:
            errors.append(f"Invalid Chromium AAR: {exc}")

    if not report_path or not Path(report_path).is_file():
        errors.append(
            "No trusted CI-generated Android integration smoke report. "
            "An APK build does not prove Chromium browsing."
        )
        return errors
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        errors.append(f"Invalid Chromium integration report: {exc}")
        return errors
    if not isinstance(report, dict):
        return errors + ["The integration report must be a JSON object"]
    if report.get("app_version") != "0.2.1":
        errors.append("Integration report must target v0.2.1")
    if report.get("engine") != "android-chromium":
        errors.append("Real native Chromium engine not identified")
    if report.get("test_environment") != "android-ci-emulator":
        errors.append("Android CI emulator integration test required")
    if report.get("aar_sha256") != aar_digest:
        errors.append("Smoke report AAR digest does not match the supplied engine")
    if not re.fullmatch(r"[a-f0-9]{64}", str(report.get("apk_sha256", ""))):
        errors.append("CI smoke report does not contain a valid APK SHA-256")
    checks = report.get("checks")
    for check in REQUIRED_AUTOMATED_CHECKS:
        if not isinstance(checks, dict) or checks.get(check) is not True:
            errors.append(f"Missing passing automated integration check: {check}")
    return errors


def main() -> int:
    errors = readiness_errors(
        os.getenv("BROWSER_ANDROID_CHROMIUM_AAR"),
        os.getenv("BROWSER_ANDROID_CHROMIUM_AAR_SHA256"),
        os.getenv("BROWSER_CHROMIUM_CI_SMOKE_REPORT"),
    )
    if errors:
        for error in errors:
            print(f"::error title=v0.2.1 native Chromium blocker::{error}")
        return 1
    print(
        "Engine package and claimed integration report validated structurally. "
        "The report MUST come from trusted instrumentation against the APK "
        "with this exact engine linked; document that CI provenance before "
        "treating the gate as sufficient. Physical-device QA is post-release."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
