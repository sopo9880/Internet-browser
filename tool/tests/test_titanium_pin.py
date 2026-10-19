"""Pinned real Chromium extension research source, not WebView mocks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from tool.chromium import titanium_pin as pin


class TitaniumSourcePinTests(unittest.TestCase):
    def test_exact_current_source_and_adblock(self):
        pin.validate_pins()
        self.assertEqual(pin.REQUIRED_ADBLOCK_ID, "gighmmpiobklfepjocnamgkkbiglidom")
        self.assertEqual(pin.CHROMIUM_VERSION, "155.0.8059.84")
        self.assertNotEqual(pin.PROTOTYPE_PACKAGE,
                            "io.github.sopo9880.internet_browser")
        self.assertFalse(pin.SOURCE_TREE_IS_EMBEDDABLE)

    def test_refuses_source_or_submodule_drift(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "args.gn").touch()
            (root / "patch.sh").touch()
            (root / "vanadium").mkdir()
            (root / "vanadium" / "args.gn").touch()
            with self.assertRaisesRegex(ValueError, "changed"):
                pin.verify_checkout(root, "0" * 40, pin.VANADIUM_SHA)
            with self.assertRaisesRegex(ValueError, "changed"):
                pin.verify_checkout(root, pin.SOURCE_SHA, "f" * 40)
            pin.verify_checkout(root, pin.SOURCE_SHA, pin.VANADIUM_SHA)

    def test_prototype_report_cannot_be_adblock_acceptance(self):
        with TemporaryDirectory() as tmp:
            apk = Path(tmp) / "prototype.apk"
            apk.write_bytes(b"nonrelease fixture only")
            report = Path(tmp) / "report.json"
            pin.write_prototype_report(report, apk)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(data["embedded_in_internet_browser"])
            self.assertFalse(data["release_approved"])
            self.assertFalse(data["adblock_install_verified"])
            self.assertFalse(data["adblock_request_blocking_verified"])


if __name__ == "__main__":
    unittest.main()
