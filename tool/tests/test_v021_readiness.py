"""The native Chromium/Android release gate must fail unless real evidence exists."""
import json
from pathlib import Path
import tempfile
import unittest
from hashlib import sha256

from tool.chromium.require_native_engine import (
    REQUIRED_AUTOMATED_CHECKS, readiness_errors, PROVENANCE_KIND,
)
from tool.chromium.titanium_pin import (
    PRODUCT_PACKAGE, SOURCE_REPO, SOURCE_SHA, VANADIUM_SHA, CHROMIUM_VERSION,
    REQUIRED_ADBLOCK_ID,
)


class ChromiumReadinessTests(unittest.TestCase):
    @staticmethod
    def _fixture(root: Path) -> tuple[Path, Path, Path]:
        # Synthetic bytes ONLY test strict gates; they never imply a real APK.
        apk = root / "native.apk"
        apk.write_bytes(b"synthetic nonrelease test fixture")
        digest = sha256(apk.read_bytes()).hexdigest()
        provenance = root / "provenance.json"
        provenance.write_text(json.dumps({
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
            "app_version": "0.2.1",
            "android_version_code": 2001001,
            "required_adblock_id": REQUIRED_ADBLOCK_ID,
            "apk_sha256": digest,
            "integration_commit": "e" * 40,
        }), encoding="utf-8")
        smoke = root / "android-ci.json"
        smoke.write_text(json.dumps({
            "test_environment": "android-ci-emulator",
            "apk_sha256": digest,
            "integration_commit": "e" * 40,
            "checks": {k: True for k in REQUIRED_AUTOMATED_CHECKS},
        }), encoding="utf-8")
        return apk, provenance, smoke

    def test_missing_compiled_chromium_and_smoke_fail(self):
        errors = readiness_errors(None, None, None, "0.2.1", 2001001)
        self.assertTrue(any("Missing actual Titanium" in x for x in errors))
        self.assertTrue(any("smoke report" in x for x in errors))

    def test_built_apk_without_real_smoke_must_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk, provenance, smoke = self._fixture(Path(tmp))
            errors = readiness_errors(str(apk), str(provenance),
                                      str(smoke) + ".missing",
                                      "0.2.1", 2001001, "e" * 40)
            self.assertTrue(any("smoke report" in x for x in errors))

    def test_old_flutter_package_and_missing_extension_proof_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk, provenance, smoke = self._fixture(Path(tmp))
            p = json.loads(provenance.read_text())
            p["candidate_android_package"] = "io.github.sopo9880.internet_browser.flutter"
            provenance.write_text(json.dumps(p))
            s = json.loads(smoke.read_text())
            s["checks"]["adblock_network_request_blocked"] = False
            smoke.write_text(json.dumps(s))
            errors = readiness_errors(str(apk), str(provenance), str(smoke),
                                      "0.2.1", 2001001, "e" * 40)
            self.assertTrue(any("candidate_android_package" in x for x in errors))
            self.assertTrue(any("adblock_network_request_blocked" in x for x in errors))

    def test_changed_apk_hash_and_downgrade_version_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk, provenance, smoke = self._fixture(Path(tmp))
            errors = readiness_errors(str(apk), str(provenance), str(smoke),
                                      "0.2.1", 2000001, "e" * 40)
            self.assertTrue(any("android_version_code" in x for x in errors))
            apk.write_bytes(b"different bytes")
            errors = readiness_errors(str(apk), str(provenance), str(smoke),
                                      "0.2.1", 2001001, "e" * 40)
            self.assertTrue(any("SHA-256" in x for x in errors))

    def test_valid_synthetic_fixture_only_tests_parser_not_real_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk, provenance, smoke = self._fixture(Path(tmp))
            self.assertEqual(
                readiness_errors(str(apk), str(provenance), str(smoke),
                                 "0.2.1", 2001001, "e" * 40),
                [],
            )


if __name__ == "__main__":
    unittest.main()
