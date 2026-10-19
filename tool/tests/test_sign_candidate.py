"""No-secrets validation for intentionally UNVERIFIED native candidate signing."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tool.chromium.sign_candidate import (
    ARTIFACT_ID, ARTIFACT_NAME, ARTIFACT_ZIP_SHA256, BUILT_HEAD_SHA,
    BUILD_BASE_SHA, BUILD_MERGE_SHA,
    JOB_ID, PRODUCTION_CERT_SHA256, REPO_ID, RUN_ID,
    verify_apk_identity, verify_provenance, verify_signed_candidate,
    verify_source_metadata,
)
from tool.chromium.titanium_pin import (
    CHROMIUM_VERSION, REQUIRED_ADBLOCK_ID, SOURCE_REPO, SOURCE_SHA, VANADIUM_SHA,
)


class SignCandidateTests(unittest.TestCase):
    def source_objects(self):
        run = {
            "id": RUN_ID, "status": "completed", "conclusion": "failure",
            "event": "pull_request", "head_sha": BUILT_HEAD_SHA,
            "head_branch": "feat/v0.2.1-browser-recovery",
            "repository": {"id": REPO_ID}, "head_repository": {"id": REPO_ID},
            "pull_requests": [{"number": 4,
                               "head": {"sha": BUILT_HEAD_SHA},
                               "base": {"sha": BUILD_BASE_SHA}}],
        }
        job = {
            "id": JOB_ID, "run_id": RUN_ID, "name": "android",
            "status": "completed", "conclusion": "success",
        }
        artifact = {
            "id": ARTIFACT_ID, "name": ARTIFACT_NAME, "expired": False,
            "size_in_bytes": 145817144, "digest": "sha256:" + ARTIFACT_ZIP_SHA256,
            "workflow_run": {
                "id": RUN_ID, "repository_id": REPO_ID,
                "head_repository_id": REPO_ID, "head_sha": BUILT_HEAD_SHA,
            },
        }
        merge_commit = {"sha": BUILD_MERGE_SHA, "parents": [
            {"sha": BUILD_BASE_SHA}, {"sha": BUILT_HEAD_SHA}]}
        return run, job, artifact, merge_commit

    def source_report(self, digest):
        return {
            "kind": "CHROMIUM_NATIVE_PRODUCT_CANDIDATE_NOT_RELEASE",
            "engine_source": SOURCE_REPO, "engine_source_commit": SOURCE_SHA,
            "vanadium_source_commit": VANADIUM_SHA,
            "chromium_version_reference": CHROMIUM_VERSION,
            "candidate_android_package": "io.github.sopo9880.internet_browser",
            "production_android_package_id": "io.github.sopo9880.internet_browser",
            "production_id_matched": True, "built_as_chromium_android_application": True,
            "disposable_test_signer_not_upgrade_compatible": True,
            "app_version": "0.2.1", "android_version_code": 2001001,
            "required_adblock_id": REQUIRED_ADBLOCK_ID,
            "integration_commit": BUILD_MERGE_SHA,
            "apk_sha256": digest,
        }

    def test_only_specific_successful_android_job_on_failed_overall_run(self):
        verify_source_metadata(*self.source_objects())
        run, job, artifact, merge_commit = self.source_objects()
        job["conclusion"] = "failure"
        with self.assertRaisesRegex(ValueError, "Android compilation"):
            verify_source_metadata(run, job, artifact, merge_commit)

    def test_rejects_artifact_drift_other_repo_other_commit_or_digest(self):
        for category, name, value in (
            ("run", "head_sha", "0" * 40),
            ("run", "event", "workflow_dispatch"),
            ("job", "id", 1),
            ("artifact", "id", 1),
            ("artifact", "digest", "sha256:" + "0" * 64),
            ("artifact", "expired", True),
            ("merge_commit", "sha", "0" * 40),
        ):
            with self.subTest(category=category, name=name):
                run, job, artifact, merge_commit = self.source_objects()
                {"run": run, "job": job, "artifact": artifact,
                 "merge_commit": merge_commit}[category][name] = value
                with self.assertRaises(ValueError):
                    verify_source_metadata(run, job, artifact, merge_commit)

    def test_original_ci_merge_sha_is_not_pr_head_and_parents_are_pinned(self):
        self.assertNotEqual(BUILD_MERGE_SHA, BUILT_HEAD_SHA)
        run, job, artifact, merge_commit = self.source_objects()
        merge_commit["parents"][0]["sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "parents"):
            verify_source_metadata(run, job, artifact, merge_commit)
        run, job, artifact, merge_commit = self.source_objects()
        run["pull_requests"][0]["head"]["sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "head SHA"):
            verify_source_metadata(run, job, artifact, merge_commit)

    def test_rejects_binary_or_provenance_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "candidate.apk"
            apk.write_bytes(b"x" * 1_100_000)
            report = self.source_report(sha256(apk.read_bytes()).hexdigest())
            self.assertEqual(verify_provenance(apk, report), report["apk_sha256"])
            for changed in ("kind", "integration_commit", "android_version_code",
                            "built_as_chromium_android_application"):
                bad = deepcopy(report)
                bad[changed] = "UNTRUSTED"
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    verify_provenance(apk, bad)
            apk.write_bytes(b"y" * 1_100_000)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verify_provenance(apk, report)

    def test_manifest_and_cert_must_match_without_android_sdk_at_test_time(self):
        with patch("tool.chromium.sign_candidate._output") as command:
            command.side_effect = [
                "io.github.sopo9880.internet_browser\n",
                "package: name='io.github.sopo9880.internet_browser' versionCode='2001001' versionName='0.2.1'\n",
                "Signer #1 certificate SHA-256 digest: " + PRODUCTION_CERT_SHA256 + "\n",
            ]
            actual = verify_apk_identity(
                Path("candidate.apk"), Path("aapt2"), Path("apksigner"))
            self.assertEqual(actual, PRODUCTION_CERT_SHA256)
        with patch("tool.chromium.sign_candidate._output") as command:
            command.side_effect = [
                "fake.package\n", "", "Signer #1 certificate SHA-256 digest: " + PRODUCTION_CERT_SHA256,
            ]
            with self.assertRaisesRegex(ValueError, "package name"):
                verify_apk_identity(Path("candidate.apk"), Path("aapt2"), Path("apksigner"))

    def test_signed_candidate_rejects_incorrect_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            old, new = Path(directory) / "old.apk", Path(directory) / "new.apk"
            old.write_bytes(b"o" * 1_100_000)
            new.write_bytes(b"n" * 1_100_000)
            with patch("tool.chromium.sign_candidate.verify_apk_identity",
                       return_value="0" * 64):
                with self.assertRaisesRegex(ValueError, "certificate"):
                    verify_signed_candidate(old, new, Path("aapt2"), Path("apksigner"))
            with patch("tool.chromium.sign_candidate.verify_apk_identity",
                       return_value=PRODUCTION_CERT_SHA256):
                output = verify_signed_candidate(old, new, Path("aapt2"), Path("apksigner"))
                self.assertFalse(output["runtime_integration_test_passed"])
                self.assertFalse(output["github_release_published"])
                self.assertFalse(output["existing_user_data_migration_verified"])

    def test_release_key_is_only_used_in_manual_main_only_job(self):
        workflow = (
            Path(__file__).resolve().parents[2]
            / ".github/workflows/sign-native-candidate.yml"
        ).read_text(encoding="utf-8")
        safety, secret_job = workflow.split("\n  sign_candidate:\n", 1)
        self.assertNotIn("secrets.", safety)
        self.assertIn("github.event_name == 'workflow_dispatch'", secret_job)
        self.assertIn("github.ref == 'refs/heads/main'", secret_job)
        self.assertIn("SIGN_UNVERIFIED_NO_RELEASE", secret_job)
        self.assertIn("needs: safety", secret_job)
        self.assertIn("runs-on: ubuntu-24.04", secret_job)
        self.assertNotIn("self-hosted", secret_job)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("flutter build", workflow)
        self.assertNotIn("build_titanium_prototype.sh", workflow)
        self.assertIn("12204054700", workflow)
        self.assertIn("39225095884", workflow)
        self.assertIn("36a1953e25d7016a9b8b4bb5cd48442c28d8d74b", workflow)
        self.assertIn("--merge-commit", workflow)
        self.assertIn("apksigner", workflow)
        self.assertIn("UNVERIFIED", workflow)
        self.assertIn("retention-days: 30", workflow)


if __name__ == "__main__":
    unittest.main()
