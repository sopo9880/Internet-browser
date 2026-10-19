#!/usr/bin/env python3
"""Prepare a reproducible Chromium Android baseline (NOT an extensions APK).

Stock upstream Chromium on normal Android phones does not supply the full
Chrome Web Store extensions runtime. This tool never claims otherwise.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

_COMMIT = re.compile(r"[a-f0-9]{40}\Z")


def validated_revision(revision: str) -> str:
    if not _COMMIT.fullmatch(revision):
        raise ValueError("Expected a pinned full 40-hex upstream Chromium commit")
    return revision


def gn_args(target_cpu: str = "arm64") -> str:
    if target_cpu not in ("arm64", "x64"):
        raise ValueError("Only Android arm64 and x64 baseline builds are supported")
    return (
        'target_os = "android"\n'
        f'target_cpu = "{target_cpu}"\n'
        "is_debug = false\n"
        "is_component_build = false\n"
        "is_official_build = false\n"
        "symbol_level = 0\n"
    )


def write_config(
    source: Path,
    out_dir: Path,
    revision: str,
    checkout_sha: str,
    target_cpu: str = "arm64",
) -> Path:
    validated_revision(revision)
    if revision != checkout_sha:
        raise ValueError("Chromium source revision mismatch")
    if not (source / ".gn").is_file() or not (source / "chrome").is_dir():
        raise FileNotFoundError("Expected a full upstream Chromium checkout")
    args = source / out_dir / "args.gn"
    args.parent.mkdir(parents=True, exist_ok=True)
    args.write_text(gn_args(target_cpu), encoding="utf-8")
    return args


def save_baseline_metadata(
    output: Path, revision: str, apk_sha256: str,
) -> None:
    validated_revision(revision)
    if not re.fullmatch(r"[a-f0-9]{64}", apk_sha256):
        raise ValueError("Invalid Chromium APK SHA-256")
    report = {
        "kind": "upstream-chromium-android-baseline-NOT-a-release",
        "chromium_commit": revision,
        "android_target": "chrome_public_apk",
        "apk_sha256": apk_sha256,
        "native_flutter_chromium_embedded": False,
        "manifest_v3_extensions_implemented": False,
        "required_adblock_id": "gighmmpiobklfepjocnamgkkbiglidom",
        "required_adblock_tested": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("out/InternetBrowser"))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--cpu", choices=("arm64", "x64"), default="arm64")
    arguments = parser.parse_args()
    output = write_config(
        arguments.source, arguments.out, arguments.revision,
        arguments.checkout_sha, arguments.cpu,
    )
    print(f"Prepared upstream Chromium build configuration: {output}")
    print("This baseline is NOT a working Android Chrome-extension browser.")


if __name__ == "__main__":
    main()
