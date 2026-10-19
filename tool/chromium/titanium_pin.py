#!/usr/bin/env python3
"""Pinned, reviewable research source for the real Android extensions engine.

Titanium is an extension-capable Chromium Android application, NOT an AAR.
It cannot be presented as an integrated Internet-browser engine until
navigation, DPI, media and storage are migrated and device-tested.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

SOURCE_REPO = "https://github.com/jqssun/android-titanium-browser.git"
SOURCE_SHA = "e59e03dc83bc940d73cf29a7683286fca390b393"
VANADIUM_SHA = "20526e052e304b62cf3e80114b423934e2d1c540"
CHROMIUM_VERSION = "155.0.8059.84"
REQUIRED_ADBLOCK_ID = "gighmmpiobklfepjocnamgkkbiglidom"
PROTOTYPE_PACKAGE = "io.github.sopo9880.internet_browser.chromiumtest"
SOURCE_LICENSE = "GPL-2.0"
SOURCE_TREE_IS_EMBEDDABLE = False

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_EXT = re.compile(r"[a-p]{32}\Z")


def validate_pins() -> None:
    if not _SHA.fullmatch(SOURCE_SHA) or not _SHA.fullmatch(VANADIUM_SHA):
        raise ValueError("Immutable 40-hex source and submodule pins required")
    if not _EXT.fullmatch(REQUIRED_ADBLOCK_ID):
        raise ValueError("Invalid required Chrome extension ID")
    if PROTOTYPE_PACKAGE == "io.github.sopo9880.internet_browser":
        raise ValueError("Prototype must not replace the released app")
    if SOURCE_TREE_IS_EMBEDDABLE:
        raise ValueError("A standalone Chromium APK is not an embedded engine")


def verify_checkout(source: Path, head_sha: str, vanadium_sha: str) -> None:
    validate_pins()
    if head_sha != SOURCE_SHA or vanadium_sha != VANADIUM_SHA:
        raise ValueError("Pinned Chromium extension source changed")
    if not (source / "patch.sh").is_file():
        raise FileNotFoundError("Missing Chromium extension patch driver")
    if not (source / "args.gn").is_file():
        raise FileNotFoundError("Missing Chromium Android GN arguments")
    if not (source / "vanadium" / "args.gn").is_file():
        raise FileNotFoundError("Missing pinned Vanadium Chromium version")


def write_prototype_report(path: Path, apk: Path) -> None:
    validate_pins()
    if not apk.is_file() or apk.stat().st_size == 0:
        raise FileNotFoundError("No actual Chromium extensions APK compiled")
    data = {
        "kind": "RESEARCH_ONLY_STANDALONE_CHROMIUM_EXTENSIONS_APK",
        "engine_source": SOURCE_REPO,
        "engine_source_commit": SOURCE_SHA,
        "vanadium_source_commit": VANADIUM_SHA,
        "chromium_version_reference": CHROMIUM_VERSION,
        "source_license": SOURCE_LICENSE,
        "apk_sha256": sha256(apk.read_bytes()).hexdigest(),
        "prototype_package": PROTOTYPE_PACKAGE,
        "required_adblock_id": REQUIRED_ADBLOCK_ID,
        "adblock_install_verified": False,
        "adblock_request_blocking_verified": False,
        "embedded_in_internet_browser": False,
        "byedpi_media_migrated": False,
        "release_approved": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--checkout", type=Path)
    p.add_argument("--head-sha")
    p.add_argument("--vanadium-sha")
    p.add_argument("--apk", type=Path)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    validate_pins()
    if args.checkout:
        if not args.head_sha or not args.vanadium_sha:
            p.error("Checkouts require source and Vanadium SHA")
        verify_checkout(args.checkout, args.head_sha, args.vanadium_sha)
    if args.apk:
        if not args.report:
            p.error("Compiled APK requires --report")
        write_prototype_report(args.report, args.apk)
    print("Chromium 155 extension-engine source pin verified; no device success implied")


if __name__ == "__main__":
    main()
