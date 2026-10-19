"""v0.2.0 release cannot be satisfied by a stub or an old WebView app."""
import unittest

from tool.chromium_extension_acceptance import (
    REQUIRED_CHECKS,
    REQUIRED_EXTENSION_ID,
    validate_report,
)


class ExtensionAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.pass_report = {
            "app_version": "0.2.0",
            "engine": "android-chromium",
            "extension_id": REQUIRED_EXTENSION_ID,
            "test_environment": "android-physical-device",
            "apk_sha256": "c" * 64,
            "device_model": "Instrumented device",
            "checks": {key: True for key in REQUIRED_CHECKS},
        }

    def test_webview_must_fail(self):
        report = dict(self.pass_report, engine="android-webview")
        self.assertTrue(validate_report(report))

    def test_different_adblock_or_internal_filter_must_fail(self):
        report = dict(
            self.pass_report,
            extension_id="not-the-chrome-web-store-extension",
        )
        self.assertTrue(validate_report(report))

    def test_missing_declarative_network_rules_must_fail(self):
        self.pass_report["checks"]["declarative_net_request_blocks_ads"] = False
        self.assertTrue(validate_report(self.pass_report))

    def test_no_device_proof_fails(self):
        report = dict(self.pass_report)
        report.pop("apk_sha256")
        self.assertTrue(validate_report(report))
        report["apk_sha256"] = "c" * 64
        report["test_environment"] = "simulator"
        self.assertTrue(validate_report(report))

    def test_schema_fully_valid_only_if_every_gate_passed(self):
        self.assertEqual(validate_report(self.pass_report), [])
        self.assertGreaterEqual(len(REQUIRED_CHECKS), 10)


if __name__ == "__main__":
    unittest.main()
