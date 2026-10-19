"""Real Chromium-native product path; never treat a Flutter shell as Chromium."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

from tool.chromium.titanium_product import (
    ARM32_SIGN, ARM32_TARGET, PRODUCT_PACKAGE, RESEARCH_PACKAGE,
    SOURCE_CPU, SOURCE_PACKAGE, prepare_source, verify_native_apk,
)


ARGS = SOURCE_PACKAGE + "\n" + SOURCE_CPU + "\n"
BUILD = ARM32_TARGET + (
    "autoninja -C out/Default chrome_public_apk chrome_public_bundle\n"
) + ARM32_SIGN + "sign_apk out/tmp/$VERSION-arm64-v8a.apk out/release/$VERSION-arm64-v8a.apk\n"


class TitaniumNativeProductTests(unittest.TestCase):
    def test_true_chromium_product_app_id_instead_of_dummy_aar(self):
        gn, build = prepare_source(ARGS, BUILD, PRODUCT_PACKAGE)
        self.assertIn(f'chrome_public_manifest_package = "{PRODUCT_PACKAGE}"', gn)
        self.assertIn('target_cpu = "arm64"', gn)
        self.assertNotIn("armeabi-v7a", build)
        self.assertIn("autoninja -C out/Default chrome_public_apk chrome_public_bundle", build)

    def test_keeps_separate_research_variant(self):
        gn, _ = prepare_source(ARGS, BUILD, RESEARCH_PACKAGE)
        self.assertIn(RESEARCH_PACKAGE, gn)

    def test_rejects_upstream_template_drift(self):
        with self.assertRaisesRegex(ValueError, "template changed"):
            prepare_source(ARGS.replace(SOURCE_CPU, 'target_cpu = "x64"'),
                           BUILD, PRODUCT_PACKAGE)

    def test_rejects_arbitrary_package(self):
        with self.assertRaisesRegex(ValueError, "Only explicit"):
            prepare_source(ARGS, BUILD, "com.malicious.app")

    def test_native_apk_manifest_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk = Path(tmp) / "native.apk"
            apk.write_bytes(b"stub APK data -- subprocess is mocked")
            aapt = Path(tmp) / "aapt2"
            aapt.touch()
            with patch(
                "tool.chromium.titanium_product.subprocess.run",
                return_value=CompletedProcess(
                    args=[], returncode=0, stdout=RESEARCH_PACKAGE + "\n", stderr="",
                ),
            ):
                with self.assertRaisesRegex(ValueError, "package mismatch"):
                    verify_native_apk(apk, aapt, PRODUCT_PACKAGE)
                verify_native_apk(apk, aapt, RESEARCH_PACKAGE)


if __name__ == "__main__":
    unittest.main()
