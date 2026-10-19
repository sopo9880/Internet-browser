#!/usr/bin/env python3
"""Verify a single pinned Chromium artifact and its release-key signing.

This does NOT waive the runtime integration gate or authorize GitHub Releases.
Only this source's pinned failed-overall / successful-Android Actions run is
eligible. All metadata and the binary are checked before production secrets
are made available in the GitHub-hosted signing job.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

from tool.chromium.titanium_pin import (
    CHROMIUM_VERSION, REQUIRED_ADBLOCK_ID, SOURCE_REPO, SOURCE_SHA, VANADIUM_SHA,
)

RUN_ID = 39225095884
JOB_ID = 117970070549
ARTIFACT_ID = 12204054700
ARTIFACT_NAME = "android-titanium-native-candidate"
ARTIFACT_ZIP_SHA256 = "0f58291262c754ac596c2158077d09f1e5cac39753d8af1bf483a0105b391c79"
BUILT_HEAD_SHA = "97f37cd99b318764374605f5df72b5aebfd11551"
# pull_request Actions use the generated merge commit as GITHUB_SHA,
# not the PR branch head. Both fixed SHAs were verified from GitHub.
BUILD_MERGE_SHA = "36a1953e25d7016a9b8b4bb5cd48442c28d8d74b"
BUILD_BASE_SHA = "9cddceb0c1f7834220f0d92deea5fc5953467aec"
REPO_ID = 1424387583
APP_PACKAGE = "io.github.sopo9880.internet_browser"
VERSION_NAME = "0.2.1"
VERSION_CODE = 2001001
PRODUCTION_CERT_SHA256 = "08116054e3a1de465da9357649c045fbb06e6d06f2c6108cda5e6dfd81d82e4a"
PROVENANCE_KIND = "CHROMIUM_NATIVE_PRODUCT_CANDIDATE_NOT_RELEASE"


def _require(condition: bool, explanation: str) -> None:
    if not condition:
        raise ValueError(explanation)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for piece in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def _load(path: Path) -> dict:
    content = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(content, dict), f"Invalid JSON object: {path.name}")
    return content


def verify_source_metadata(run: dict, job: dict, artifact: dict,
                           merge_commit: dict) -> None:
    """Allow a failed overall CI only when its actual Android job passed."""
    for field, value in (
        ("id", RUN_ID), ("status", "completed"), ("event", "pull_request"),
        ("head_sha", BUILT_HEAD_SHA), ("head_branch", "feat/v0.2.1-browser-recovery"),
    ):
        _require(run.get(field) == value, f"Unapproved source run {field}")
    _require(run.get("conclusion") in ("failure", "success"), "Source run not finished")
    _require(run.get("repository", {}).get("id") == REPO_ID, "Foreign source repository")
    _require(run.get("head_repository", {}).get("id") == REPO_ID, "Foreign PR source repository")
    for field, value in (
        ("id", JOB_ID), ("run_id", RUN_ID), ("name", "android"),
        ("status", "completed"), ("conclusion", "success"),
    ):
        _require(job.get(field) == value, f"Required Android compilation did not pass: {field}")
    for field, value in (
        ("id", ARTIFACT_ID), ("name", ARTIFACT_NAME), ("expired", False),
        ("digest", f"sha256:{ARTIFACT_ZIP_SHA256}"),
    ):
        _require(artifact.get(field) == value, f"Source artifact mismatch: {field}")
    _require(artifact.get("size_in_bytes", 0) > 100_000_000, "Unexpectedly small Chromium artifact")
    wf = artifact.get("workflow_run", {})
    for field, value in (
        ("id", RUN_ID), ("repository_id", REPO_ID),
        ("head_repository_id", REPO_ID), ("head_sha", BUILT_HEAD_SHA),
    ):
        _require(wf.get(field) == value, f"Artifact workflow provenance mismatch: {field}")

    # PR Actions checkout refs/pull/4/merge; verify exact synthetic commit.
    prs = run.get("pull_requests")
    _require(isinstance(prs, list) and len(prs) == 1,
             "Expected exactly one pinned source pull request")
    pr = prs[0]
    _require(pr.get("number") == 4, "Source run PR number mismatch")
    _require(pr.get("head", {}).get("sha") == BUILT_HEAD_SHA,
             "Source PR head SHA mismatch")
    _require(pr.get("base", {}).get("sha") == BUILD_BASE_SHA,
             "Source PR base SHA mismatch")
    _require(merge_commit.get("sha") == BUILD_MERGE_SHA,
             "Unexpected pull request merge checkout SHA")
    _require([parent.get("sha") for parent in merge_commit.get("parents", [])]
             == [BUILD_BASE_SHA, BUILT_HEAD_SHA],
             "Build merge checkout parents differ from approved PR head/base")


def verify_provenance(apk: Path, report: dict) -> str:
    _require(apk.is_file() and apk.stat().st_size > 1_000_000, "Missing compiled native APK")
    expected = {
        "kind": PROVENANCE_KIND,
        "engine_source": SOURCE_REPO,
        "engine_source_commit": SOURCE_SHA,
        "vanadium_source_commit": VANADIUM_SHA,
        "chromium_version_reference": CHROMIUM_VERSION,
        "candidate_android_package": APP_PACKAGE,
        "production_android_package_id": APP_PACKAGE,
        "production_id_matched": True,
        "built_as_chromium_android_application": True,
        "disposable_test_signer_not_upgrade_compatible": True,
        "app_version": VERSION_NAME,
        "android_version_code": VERSION_CODE,
        "required_adblock_id": REQUIRED_ADBLOCK_ID,
        "integration_commit": BUILD_MERGE_SHA,
    }
    for field, value in expected.items():
        _require(report.get(field) == value, f"Native candidate provenance mismatch: {field}")
    digest = _sha256_file(apk)
    _require(report.get("apk_sha256") == digest, "Native APK SHA-256 mismatch")
    return digest


def _output(*args: str) -> str:
    return subprocess.run(args, text=True, capture_output=True, check=True).stdout


def parse_verified_certificate_sha256(certificates: str) -> str:
    """Read the SINGLE verified APK signer from old and new Android build-tools.

    Build-tools through 36 use "Signer #1 certificate SHA-256 digest";
    newer apksigner versions prefix it with a scheme, e.g.
    "V2 Signer: certificate SHA-256 digest" or "V3.0 Signer: ...".
    An APK verified across multiple signing schemes may report the SAME
    certificate repeatedly. Require one signer AND exactly one distinct
    certificate digest; never silently select the first of different keys.
    """
    counts = re.findall(r"^Number of signers:\s*(\d+)\s*$",
                        certificates, flags=re.MULTILINE)
    _require(counts == ["1"], "APK must have exactly one verified signer")
    certificate_lines = re.findall(
        r"^(?:Signer #\d+|Signer \(minSdkVersion=\d+,\s*maxSdkVersion=\d+\)"
        r"|V\d+(?:\.\d+)? Signer(?: #\d+)?)"
        r":?\s+certificate SHA-256 digest:\s*([0-9a-f]{64})\s*$",
        certificates, flags=re.MULTILINE | re.IGNORECASE,
    )
    _require(bool(certificate_lines), "APK verified signer certificate digest missing")
    # Both legacy multi-signers and future scheme-indexed multi-signers fail.
    _require(re.search(r"\bSigner #(?:[2-9]|\d{2,})\b", certificates) is None,
             "APK must have exactly one verified signer")
    digests = {digest.lower() for digest in certificate_lines}
    _require(len(digests) == 1,
             "APK signing schemes have inconsistent certificate identities")
    return digests.pop()


def verify_apk_identity(apk: Path, aapt2: Path, apksigner: Path) -> str:
    package = _output(str(aapt2), "dump", "packagename", str(apk)).strip()
    _require(package == APP_PACKAGE, "Native APK package name differs from existing app")
    lines = _output(str(aapt2), "dump", "badging", str(apk)).splitlines()
    info = next((line for line in lines if line.startswith("package:")), "")
    _require(f"name='{APP_PACKAGE}'" in info, "Native manifest package mismatch")
    _require(f"versionCode='{VERSION_CODE}'" in info, "Native manifest versionCode mismatch")
    _require(f"versionName='{VERSION_NAME}'" in info, "Native manifest versionName mismatch")
    certificates = _output(str(apksigner), "verify", "--verbose", "--print-certs", str(apk))
    return parse_verified_certificate_sha256(certificates)


def verify_unsigned_candidate(apk: Path, provenance: Path, aapt2: Path, apksigner: Path) -> str:
    digest = verify_provenance(apk, _load(provenance))
    signer = verify_apk_identity(apk, aapt2, apksigner)
    _require(signer != PRODUCTION_CERT_SHA256,
             "Source must be the original disposable-key candidate, not a replaced APK")
    return digest


def verify_signed_candidate(candidate: Path, signed: Path, aapt2: Path,
                            apksigner: Path) -> dict:
    _require(candidate.is_file() and signed.is_file() and signed.stat().st_size > 1_000_000,
             "Candidate or signed Chromium APK missing")
    signer = verify_apk_identity(signed, aapt2, apksigner)
    _require(signer == PRODUCTION_CERT_SHA256,
             "Signing certificate SHA-256 DOES NOT match v0.2.0 release")
    original = _sha256_file(candidate)
    final = _sha256_file(signed)
    _require(original != final, "Signing step did not produce an updated APK")
    return {
        "kind": "UNVERIFIED_OFFICIAL_KEY_SIGNED_CANDIDATE_NOT_RELEASE",
        "version": VERSION_NAME,
        "version_code": VERSION_CODE,
        "package": APP_PACKAGE,
        "source_run_id": RUN_ID,
        "source_job_id": JOB_ID,
        "source_artifact_id": ARTIFACT_ID,
        "source_commit": BUILT_HEAD_SHA,
        "original_ci_merge_checkout_commit": BUILD_MERGE_SHA,
        "original_apk_sha256": original,
        "signed_apk_sha256": final,
        "release_certificate_sha256": signer,
        "runtime_integration_test_passed": False,
        "physical_device_validation_performed": False,
        "github_release_published": False,
        "existing_user_data_migration_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["metadata", "source", "signed"])
    parser.add_argument("--run", type=Path)
    parser.add_argument("--job", type=Path)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--merge-commit", type=Path)
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--signed", type=Path)
    parser.add_argument("--aapt2", type=Path)
    parser.add_argument("--apksigner", type=Path)
    parser.add_argument("--report", type=Path)
    options = parser.parse_args()
    if options.command == "metadata":
        if not all((options.run, options.job, options.artifact, options.merge_commit)):
            parser.error("metadata requires --run --job --artifact --merge-commit")
        verify_source_metadata(_load(options.run), _load(options.job),
                               _load(options.artifact), _load(options.merge_commit))
        print("Pinned historical run, Android job and immutable artifact digest verified.")
    elif options.command == "source":
        if not all((options.apk, options.provenance, options.aapt2, options.apksigner)):
            parser.error("source requires --apk --provenance --aapt2 --apksigner")
        digest = verify_unsigned_candidate(
            options.apk, options.provenance, options.aapt2, options.apksigner)
        print(f"Pinned native Chromium candidate verified, SHA-256={digest}.")
        print("NO runtime checks are implied by a successful source build.")
    else:
        if not all((options.candidate, options.signed, options.aapt2, options.apksigner, options.report)):
            parser.error("signed requires --candidate --signed --aapt2 --apksigner --report")
        report = verify_signed_candidate(
            options.candidate, options.signed, options.aapt2, options.apksigner)
        options.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("Official v0.2.0 certificate verified for UNVERIFIED candidate. No release published.")


if __name__ == "__main__":
    main()
