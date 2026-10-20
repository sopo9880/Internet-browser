#!/usr/bin/env python3
"""Stage the already production-signed Chromium v0.2.1 APK for user-requested QA release.

This deliberately does NOT claim runtime integration passed. The source build,
original signing workflow, exact archive and resulting APK are all pinned.
Never use this exception to release a different version or a recompiled APK.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

from tool.chromium.sign_candidate import (
    APP_PACKAGE, BUILT_HEAD_SHA, PRODUCTION_CERT_SHA256, REPO_ID,
    VERSION_CODE, VERSION_NAME, verify_apk_identity,
)
from tool.release_metadata import parse_pubspec

SIGNING_RUN_ID = 39334182017
SIGNING_RUN_SHA = "3b84f1f7e92628aa5ab0ecac1803b1d8965ae1ce"
SIGNED_ARTIFACT_ID = 12226545642
SIGNED_ARTIFACT_NAME = "UNVERIFIED-official-key-native-candidate-v0.2.1-NOT-RELEASE"
SIGNED_ARCHIVE_SHA256 = "d09ba5d9d21820a8c184419fa8ffcd490c876e18bd3a28e3de508a9c8e54abb2"
SIGNED_APK_SHA256 = "8b259fe741e4e536002f0e496c55b9d85898cbf8a3415481482e8b34ebb08b1b"
SOURCE_APK_SHA256 = "7ad29f39db1580a1d07f062e1adf6001d89a1bae3ad42329c07c391d457bd25e"
INPUT_APK = f"Internet-browser-Android-v{VERSION_NAME}-UNVERIFIED-SIGNED-CANDIDATE.apk"
OUTPUT_APK = f"Internet-browser-Android-v{VERSION_NAME}.apk"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_source(run: dict, artifact: dict, report: dict,
                    sums: str, version_source: str) -> None:
    info = parse_pubspec(version_source)
    _require((info.version, info.version_code) == (VERSION_NAME, VERSION_CODE),
             "Release source version or Android versionCode differs from pinned APK")
    for field, value in (
        ("id", SIGNING_RUN_ID), ("event", "workflow_dispatch"),
        ("head_sha", SIGNING_RUN_SHA), ("head_branch", "main"),
        ("status", "completed"), ("conclusion", "success"),
    ):
        _require(run.get(field) == value, f"Unapproved signing run: {field}")
    _require(run.get("repository", {}).get("id") == REPO_ID,
             "Signing run belongs to the wrong GitHub repository")
    for field, value in (
        ("id", SIGNED_ARTIFACT_ID), ("name", SIGNED_ARTIFACT_NAME),
        ("expired", False), ("digest", f"sha256:{SIGNED_ARCHIVE_SHA256}"),
    ):
        _require(artifact.get(field) == value, f"Unapproved signed artifact: {field}")
    _require(artifact.get("size_in_bytes", 0) > 100_000_000,
             "Signed artifact archive unexpectedly small")
    source = artifact.get("workflow_run", {})
    _require(source.get("id") == SIGNING_RUN_ID and
             source.get("head_sha") == SIGNING_RUN_SHA and
             source.get("repository_id") == REPO_ID,
             "Artifact provenance does not match the pinned signed run")
    expected_report = {
        "kind": "UNVERIFIED_OFFICIAL_KEY_SIGNED_CANDIDATE_NOT_RELEASE",
        "version": VERSION_NAME,
        "version_code": VERSION_CODE,
        "package": APP_PACKAGE,
        "source_run_id": 39225095884,
        "source_job_id": 117970070549,
        "source_artifact_id": 12204054700,
        "source_commit": BUILT_HEAD_SHA,
        "original_ci_merge_checkout_commit": "36a1953e25d7016a9b8b4bb5cd48442c28d8d74b",
        "original_apk_sha256": SOURCE_APK_SHA256,
        "signed_apk_sha256": SIGNED_APK_SHA256,
        "release_certificate_sha256": PRODUCTION_CERT_SHA256,
        "runtime_integration_test_passed": False,
        "physical_device_validation_performed": False,
        "existing_user_data_migration_verified": False,
    }
    for field, value in expected_report.items():
        _require(report.get(field) == value, f"Signed source report mismatch: {field}")
    # This report was generated before any GitHub release existed.
    _require(report.get("github_release_published") is False,
             "Signed source report unexpectedly claims an existing release")
    _require(sums.strip() == f"{SIGNED_APK_SHA256}  {INPUT_APK}",
             "Original signed artifact SHA256SUMS.txt mismatch")


def stage_release_apk(src: Path, target: Path, aapt2: Path, apksigner: Path) -> None:
    _require(src.is_file() and src.stat().st_size > 250_000_000,
             "Missing or unexpectedly small signed native Chromium APK")
    _require(_sha256_file(src) == SIGNED_APK_SHA256,
             "Signed native APK SHA-256 does not match the verified original")
    _require(verify_apk_identity(src, aapt2, apksigner) == PRODUCTION_CERT_SHA256,
             "APK certificate is not the original v0.2.0 production signing key")
    _require(target.name == OUTPUT_APK, "Cannot stage an unexpected release filename")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".staging")
    try:
        shutil.copyfile(src, temp)
        _require(_sha256_file(temp) == SIGNED_APK_SHA256,
                 "Staged Android APK differs from verified native candidate")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    print(f"Staged original officially signed, runtime-UNVERIFIED Android {VERSION_NAME}: {target}")
    print(f"SHA-256: {SIGNED_APK_SHA256}")
    print("AdBlock, ByeDPI, navigation, media and data migration are NOT validated.")


def main() -> None:
    parser = argparse.ArgumentParser()
    for arg in ("run", "artifact", "artifact-dir", "target", "aapt2", "apksigner", "pubspec"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_dir
    source = root / INPUT_APK
    report = json.loads((root / "UNVERIFIED-SIGNATURE-REPORT.json").read_text(encoding="utf-8"))
    run = json.loads(args.run.read_text(encoding="utf-8"))
    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    sums = (root / "SHA256SUMS.txt").read_text(encoding="utf-8")
    version = args.pubspec.read_text(encoding="utf-8")
    validate_source(run, artifact, report, sums, version)
    stage_release_apk(source, args.target, args.aapt2, args.apksigner)


if __name__ == "__main__":
    main()
