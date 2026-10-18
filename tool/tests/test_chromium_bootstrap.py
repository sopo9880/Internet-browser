"""Pin, build safety, and fail-closed checks for Chromium Android bring-up."""
from pathlib import Path
import tempfile
import unittest

from tool.chromium.prepare_android import (
    gn_args,
    save_baseline_metadata,
    validated_revision,
    write_config,
)

SHA = "1" * 40


class ChromiumBootstrapTests(unittest.TestCase):
    def test_revision_is_immutable_40_hex_sha(self):
        for bad in ("main", "stable", "a" * 39, "1" * 41, "a" * 39 + ";"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validated_revision(bad)
        self.assertEqual(validated_revision(SHA), SHA)

    def test_requires_matching_source_and_generates_gn_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / ".gn").touch()
            (source / "chrome").mkdir()
            with self.assertRaises(ValueError):
                write_config(source, Path("out/Test"), SHA, "2" * 40)
            args = write_config(source, Path("out/Test"), SHA, SHA)
            contents = args.read_text(encoding="utf-8")
            self.assertIn('target_os = "android"', contents)
            self.assertIn('target_cpu = "arm64"', contents)
            self.assertNotIn("enable_extensions = true", contents)

    def test_unknown_cpu_is_rejected(self):
        with self.assertRaises(ValueError):
            gn_args("arm")

    def test_baseline_cannot_be_treated_as_adblock_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp, "baseline.json")
            save_baseline_metadata(destination, SHA, "f" * 64)
            data = destination.read_text(encoding="utf-8")
            self.assertIn('"required_adblock_tested": false', data)
            self.assertIn('"native_flutter_chromium_embedded": false', data)
            self.assertIn('"manifest_v3_extensions_implemented": false', data)


if __name__ == "__main__":
    unittest.main()
