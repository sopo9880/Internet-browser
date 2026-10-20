"""Regression checks for explicitly user-approved Chromium v0.2.1 release artifact."""
from copy import deepcopy
import unittest

from tool.release_pinned_native import (
    INPUT_APK, REPO_ID, SIGNED_APK_SHA256, SIGNED_ARCHIVE_SHA256,
    SIGNED_ARTIFACT_ID, SIGNED_ARTIFACT_NAME, SIGNING_RUN_ID,
    SIGNING_RUN_SHA, validate_source,
)
from tool.chromium.sign_candidate import (
    APP_PACKAGE, BUILT_HEAD_SHA, PRODUCTION_CERT_SHA256, VERSION_CODE, VERSION_NAME,
)


class PinnedNativeReleaseTests(unittest.TestCase):
    def fixtures(self):
        run = {
            "id": SIGNING_RUN_ID, "event": "workflow_dispatch",
            "status": "completed", "conclusion": "success",
            "head_sha": SIGNING_RUN_SHA, "head_branch": "main",
            "repository": {"id": REPO_ID},
        }
        artifact = {
            "id": SIGNED_ARTIFACT_ID, "name": SIGNED_ARTIFACT_NAME,
            "expired": False, "digest": "sha256:" + SIGNED_ARCHIVE_SHA256,
            "size_in_bytes": 148414763,
            "workflow_run": {
                "id": SIGNING_RUN_ID, "head_sha": SIGNING_RUN_SHA,
                "repository_id": REPO_ID,
            },
        }
        report = {
            "kind": "UNVERIFIED_OFFICIAL_KEY_SIGNED_CANDIDATE_NOT_RELEASE",
            "version": VERSION_NAME, "version_code": VERSION_CODE,
            "package": APP_PACKAGE, "source_run_id": 39225095884,
            "source_job_id": 117970070549,
            "source_artifact_id": 12204054700,
            "source_commit": BUILT_HEAD_SHA,
            "original_ci_merge_checkout_commit": "36a1953e25d7016a9b8b4bb5cd48442c28d8d74b",
            "original_apk_sha256": "7ad29f39db1580a1d07f062e1adf6001d89a1bae3ad42329c07c391d457bd25e",
            "signed_apk_sha256": SIGNED_APK_SHA256,
            "release_certificate_sha256": PRODUCTION_CERT_SHA256,
            "runtime_integration_test_passed": False,
            "physical_device_validation_performed": False,
            "existing_user_data_migration_verified": False,
            "github_release_published": False,
        }
        sums = f"{SIGNED_APK_SHA256}  {INPUT_APK}\n"
        version = "name: internet_browser\nversion: 0.2.1+1\n"
        return run, artifact, report, sums, version

    def test_release_cli_imports_as_module_without_secrets(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-m", "tool.release_pinned_native", "--help"],
            capture_output=True, text=True, check=True,
        )
        self.assertIn("--artifact-dir", result.stdout)
        self.assertIn("--apksigner", result.stdout)

    def test_original_verified_candidate_is_allowed_for_release(self):
        validate_source(*self.fixtures())

    def test_rejects_substituted_signing_run_or_zip(self):
        for obj, field, bad in (
            (0, "head_sha", "0" * 40),
            (0, "conclusion", "failure"),
            (1, "id", 1),
            (1, "digest", "sha256:" + "0" * 64),
            (1, "expired", True),
            (2, "signed_apk_sha256", "0" * 64),
            (2, "release_certificate_sha256", "0" * 64),
            (2, "source_commit", "0" * 40),
            (2, "runtime_integration_test_passed", True),
            (2, "existing_user_data_migration_verified", True),
        ):
            with self.subTest(obj=obj, field=field):
                fixtures = list(deepcopy(self.fixtures()))
                fixtures[obj][field] = bad
                with self.assertRaises(ValueError):
                    validate_source(*fixtures)

    def test_rejects_repackaged_apk_checksum_and_incorrect_version_code(self):
        f = list(self.fixtures())
        f[3] = f[3].replace(SIGNED_APK_SHA256, "0" * 64)
        with self.assertRaisesRegex(ValueError, "SHA256SUMS"):
            validate_source(*f)
        f = list(self.fixtures())
        f[4] = "version: 0.2.1+2\n"
        with self.assertRaisesRegex(ValueError, "versionCode"):
            validate_source(*f)

    def test_release_notes_must_explicitly_disclose_unverified_runtime(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        notes = (root / "docs/releases/v0.2.1.md").read_text(encoding="utf-8")
        self.assertIn("AdBlock", notes)
        self.assertIn("ByeDPI", notes)
        self.assertIn("v0.2.2", notes)
        self.assertIn("검증", notes)
        flow = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("39334182017", flow)
        self.assertIn("12226545642", flow)
        self.assertIn("tool/release_pinned_native.py", flow)
        self.assertIn("python3 -m tool.release_pinned_native", flow)
        self.assertNotIn("python3 tool/release_pinned_native.py", flow)
        self.assertIn("docs/releases/v0.2.1.md", flow)


if __name__ == "__main__":
    unittest.main()
