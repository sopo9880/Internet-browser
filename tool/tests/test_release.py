"""PR-safe tests: release versions and Gradle signing are validated without keys."""
import base64
from pathlib import Path
import tempfile
import unittest

from tool.release_metadata import parse_pubspec
from tool.configure_android_signing import configure, decode_key, patch_gradle


TEMPLATE = '''plugins {
    id("com.android.application")
}
android {
    namespace = "io.github.sopo9880.internet_browser"
    ndkVersion = flutter.ndkVersion
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}
'''


class ReleaseMetadataTests(unittest.TestCase):
    def test_release_version_code_increases_monotonically(self):
        versions = ("0.1.0+1", "0.1.0+2", "0.1.1+1", "0.2.0+1", "0.4.12+1")
        codes = [parse_pubspec(f"version: {v}\n").version_code for v in versions]
        self.assertEqual(codes, sorted(codes))
        self.assertEqual(parse_pubspec("version: 0.1.0+1\n").tag, "v0.1.0")

    def test_rejects_nonzero_major_and_invalid_build_number(self):
        for version in ("1.0.0+1", "0.1.0", "0.1.0+0", "0.1.0+1000", "0.1.1000+1"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                parse_pubspec(f"version: {version}\n")

    def test_release_metadata_not_ambiguous(self):
        with self.assertRaises(ValueError):
            parse_pubspec("version: 0.1.0+1\nversion: 0.1.0+2\n")


class SigningTests(unittest.TestCase):
    def test_patches_only_release_debug_signing(self):
        result = patch_gradle(TEMPLATE)
        self.assertIn('create("release")', result)
        self.assertIn('getByName("release")', result)
        self.assertNotIn('getByName("debug")', result)
        self.assertIn("ANDROID_RELEASE_KEYSTORE_FILE", result)
        with self.assertRaises(ValueError):
            patch_gradle(result)

    def test_refuses_changed_template(self):
        with self.assertRaises(ValueError):
            patch_gradle('android {\\n    buildTypes {}\\n}')

    def test_validation_does_not_read_secrets_or_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "build.gradle.kts"
            file.write_text(TEMPLATE, encoding="utf-8")
            self.assertIsNone(configure(file, env={}, write=False))
            self.assertEqual(file.read_text(encoding="utf-8"), TEMPLATE)

    def test_missing_secrets_fail_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "build.gradle.kts"
            file.write_text(TEMPLATE, encoding="utf-8")
            with self.assertRaises(ValueError):
                configure(file, env={"RUNNER_TEMP": tmp}, write=True)
            self.assertEqual(file.read_text(encoding="utf-8"), TEMPLATE)

    def test_rejects_invalid_keystore_blob(self):
        with self.assertRaises(ValueError):
            decode_key(base64.b64encode(b"no secret key").decode())
        with self.assertRaises(ValueError):
            decode_key("not base64!!!!!!!!")

    def test_writes_key_only_to_runner_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            gradle = Path(tmp) / "build.gradle.kts"
            gradle.write_text(TEMPLATE, encoding="utf-8")
            fake_pkcs12 = bytes([0x30]) + bytes(range(1, 129))
            env = {
                "RUNNER_TEMP": tmp,
                "ANDROID_KEYSTORE_BASE64": base64.b64encode(fake_pkcs12).decode(),
                "ANDROID_KEYSTORE_PASSWORD": "example-password",
                "ANDROID_KEY_ALIAS": "internet_browser_release",
                "ANDROID_KEY_PASSWORD": "example-password",
            }
            key_file = configure(gradle, env=env, write=True)
            self.assertIsNotNone(key_file)
            self.assertEqual(key_file.read_bytes(), fake_pkcs12)
            self.assertIn('getByName("release")', gradle.read_text())
            self.assertNotIn("example-password", gradle.read_text())


class WorkflowSafetyTests(unittest.TestCase):
    def test_pull_request_workflow_never_reads_release_credentials(self):
        root = Path(__file__).resolve().parents[2]
        ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("${{ secrets.", ci)

    def test_release_workflow_only_runs_for_trusted_main(self):
        root = Path(__file__).resolve().parents[2]
        release = (root / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("branches: [main]", release)
        self.assertIn("if: github.ref == 'refs/heads/main'", release)
        self.assertNotIn("pull_request:", release)
        self.assertIn("gh release create", release)
        self.assertIn("apksigner", release)


    def test_v021_uses_one_native_android_and_windows_ci_pipeline(self):
        root = Path(__file__).resolve().parents[2]
        ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        release = (root / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("android_chromium_runtime_gate:", ci)
        self.assertIn("name: android-titanium-native-candidate", ci)
        self.assertIn("tool/chromium/build_titanium_prototype.sh", ci)
        self.assertIn("tool/chromium/build_titanium_prototype.sh", release)
        self.assertIn("python3 -m tool.chromium.require_native_engine", ci)
        self.assertIn("python3 -m tool.chromium.require_native_engine", release)
        self.assertIn("android_gate:", release)
        self.assertIn("android_sign:", release)
        self.assertIn("needs: [prepare, quality, android, android_gate, android_sign, windows]", release)
        self.assertIn("08116054e3a1de465da9357649c045fbb06e6d06f2c6108cda5e6dfd81d82e4a", release)
        for workflow in (ci, release):
            self.assertIn("runs-on: [self-hosted, linux, x64, chromium-wsl2]", workflow)
            self.assertNotIn("runs-on: [self-hosted, linux, x64, chromium-large]", workflow)
            self.assertNotIn("flutter build apk", workflow)
        self.assertFalse(
            (root / ".github/workflows/chromium-extension-prototype.yml").exists()
        )

    def test_unattended_wsl_build_has_scoped_git_am_identity(self):
        root = Path(__file__).resolve().parents[2]
        builder = (root / "tool/chromium/build_titanium_prototype.sh").read_text()
        self.assertIn('export GIT_COMMITTER_NAME=', builder)
        self.assertIn('export GIT_COMMITTER_EMAIL=', builder)
        self.assertNotIn("git config --global user.", builder)

    def test_wsl_chromium_runner_is_resource_capped(self):
        root = Path(__file__).resolve().parents[2]
        builder = (root / "tool/chromium/build_titanium_prototype.sh").read_text()
        self.assertIn("build_resources.py", builder)
        self.assertIn('CHROMIUM_NINJA_JOBS', builder)
        self.assertIn('CHROMIUM_SYNC_JOBS', builder)
        for name in ("ci.yml", "release.yml"):
            workflow = (root / ".github/workflows" / name).read_text()
            self.assertIn("timeout-minutes: 1440", workflow)
            self.assertIn("CHROMIUM_NINJA_JOBS: '3'", workflow)
            self.assertIn("CHROMIUM_SYNC_JOBS: '2'", workflow)

    def test_device_acceptance_is_post_release_not_a_required_gate(self):
        root = Path(__file__).resolve().parents[2]
        ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        release = (root / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("android_chromium_adblock_acceptance:", ci)
        self.assertNotIn("python3 tool/chromium_extension_acceptance.py", ci)
        self.assertNotIn("python3 tool/chromium_extension_acceptance.py", release)
        self.assertTrue((root / "tool/chromium_extension_acceptance.py").is_file())
        self.assertTrue((root / "docs/POST_RELEASE_ANDROID_VALIDATION.md").is_file())
        self.assertIn("docs/POST_RELEASE_ANDROID_VALIDATION.md", release)
        # Pre-release safeguards stay in place: no secret in PR CI and
        # release publication still requires the signed platform builds.
        self.assertNotIn("${{ secrets.", ci)
        self.assertIn("needs: [prepare, quality, android, android_gate, android_sign, windows]", release)
        self.assertIn('"$APKSIGNER" verify', release)


if __name__ == "__main__":
    unittest.main()
