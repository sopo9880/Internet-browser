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


ARGS = (
    SOURCE_PACKAGE + "\n" + SOURCE_CPU + "\n"
    + "v8_enable_drumbrake = true\n"
    + "v8_drumbrake_bounds_checks = true\n"
)
BUILD = "#!/bin/bash\nsource common.sh\n" + ARM32_TARGET + (
    "autoninja -C out/Default chrome_public_apk chrome_public_bundle\n"
) + ARM32_SIGN + "sign_apk out/tmp/$VERSION-arm64-v8a.apk out/release/$VERSION-arm64-v8a.apk\n"


class TitaniumNativeProductTests(unittest.TestCase):
    def test_true_chromium_product_app_id_instead_of_dummy_aar(self):
        gn, build = prepare_source(ARGS, BUILD, PRODUCT_PACKAGE)
        self.assertIn(f'chrome_public_manifest_package = "{PRODUCT_PACKAGE}"', gn)
        self.assertIn('target_cpu = "arm64"', gn)
        self.assertIn("v8_enable_drumbrake = false", gn)
        self.assertIn("v8_drumbrake_bounds_checks = false", gn)
        self.assertIn("set -e\nset -o pipefail\nsource common.sh", build)
        self.assertNotIn("armeabi-v7a", build)
        self.assertIn("autoninja -C out/Default chrome_public_apk chrome_public_bundle", build)

    def test_fail_closed_when_upstream_drops_known_android_gn_switches(self):
        for changed in (
            ARGS.replace("v8_enable_drumbrake = true", ""),
            ARGS.replace("v8_drumbrake_bounds_checks = true", ""),
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(
                ValueError, "template changed",
            ):
                prepare_source(changed, BUILD, PRODUCT_PACKAGE)

    def test_fail_closed_when_upstream_script_loses_failfast_anchor(self):
        with self.assertRaisesRegex(ValueError, "template changed"):
            prepare_source(
                ARGS,
                BUILD.replace("#!/bin/bash\nsource common.sh\n", ""),
                PRODUCT_PACKAGE,
            )

    def test_native_product_uses_expected_upgrade_version_code(self):
        gn, _ = prepare_source(
            ARGS, BUILD, PRODUCT_PACKAGE,
            version_code=2_001_001, version_name="0.2.1",
        )
        self.assertIn('android_override_version_code = "2001001"', gn)
        self.assertIn('android_override_version_name = "0.2.1"', gn)

    def test_wrong_product_versions_fail_closed(self):
        for code, name in [(2_000_001, "0.2.1"), (2_001_001, "1.0.0"),
                           (None, "0.2.1"), (2_001_001, None)]:
            with self.subTest(code=code, name=name):
                with self.assertRaises(ValueError):
                    prepare_source(
                        ARGS, BUILD, PRODUCT_PACKAGE,
                        version_code=code, version_name=name,
                    )

    def test_23gib_wsl_build_limits_upstream_autoninja_and_sync(self):
        build_with_gclient = (
            "gclient sync -D --no-history --nohooks\n" + BUILD
        )
        _, patched = prepare_source(
            ARGS, build_with_gclient, PRODUCT_PACKAGE,
            ninja_jobs=3, sync_jobs=2,
        )
        self.assertIn(
            "autoninja -j 3 -C out/Default chrome_public_apk chrome_public_bundle",
            patched,
        )
        self.assertIn("gclient sync -j 2 -D --no-history --nohooks", patched)
        self.assertNotIn("autoninja -C out/Default", patched)

    def test_unexpected_upstream_sync_template_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "template changed"):
            prepare_source(
                ARGS, BUILD, PRODUCT_PACKAGE,
                ninja_jobs=3, sync_jobs=2,
            )

    def test_invalid_parallelism_must_fail(self):
        build_with_gclient = (
            "gclient sync -D --no-history --nohooks\n" + BUILD
        )
        for ninja, sync in [(0, 2), (9, 2), (3, 0), (3, 5)]:
            with self.subTest(ninja=ninja, sync=sync), self.assertRaises(ValueError):
                prepare_source(
                    ARGS, build_with_gclient, PRODUCT_PACKAGE,
                    ninja_jobs=ninja, sync_jobs=sync,
                )

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

    def test_signed_apk_must_match_requested_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            apk = Path(tmp) / "native.apk"
            apk.write_bytes(b"not a real APK, subprocess is mocked")
            aapt = Path(tmp) / "aapt2"
            aapt.touch()
            with patch(
                "tool.chromium.titanium_product.subprocess.run",
                side_effect=[
                    CompletedProcess([], 0, stdout=PRODUCT_PACKAGE + "\n"),
                    CompletedProcess([], 0, stdout=(
                        "package: name='io.github.sopo9880.internet_browser' "
                        "versionCode='2001001' versionName='0.2.1'\n"
                    )),
                ],
            ):
                verify_native_apk(
                    apk, aapt, PRODUCT_PACKAGE,
                    version_code=2001001, version_name="0.2.1",
                )


if __name__ == "__main__":
    unittest.main()
