"""Tests that a missing Chromium runtime cannot pass the v0.2.1 release gate."""
from pathlib import Path
import tempfile
import unittest

from tool.chromium.require_native_engine import (
    REQUIRED_AUTOMATED_CHECKS,
    readiness_errors,
)


class ChromiumReadinessTests(unittest.TestCase):
    def test_no_engine_cannot_pass(self):
        errors = readiness_errors(None, None, None)
        self.assertTrue(any("EMBEDDED Chromium AAR" in msg for msg in errors))
        self.assertTrue(any("smoke report" in msg for msg in errors))

    def test_report_without_engine_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            import json
            path.write_text(json.dumps({
                "app_version": "0.2.1",
                "engine": "android-chromium",
                "test_environment": "android-ci-emulator",
                "apk_sha256": "a" * 64,
                "checks": {key: True for key in REQUIRED_AUTOMATED_CHECKS},
            }), encoding="utf-8")
            errors = readiness_errors(None, None, str(path))
            self.assertTrue(errors)
            self.assertTrue(any("EMBEDDED Chromium AAR" in x for x in errors))

    def test_corrupt_report_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            path.write_text("{not json", encoding="utf-8")
            errors = readiness_errors(None, None, str(path))
            self.assertTrue(any("Invalid Chromium integration report" in x
                                for x in errors))


if __name__ == "__main__":
    unittest.main()
