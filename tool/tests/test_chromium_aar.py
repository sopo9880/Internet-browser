"""Only a verified engine AAR can be linked to our Flutter APK."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import tempfile
import unittest

from tool.chromium.verify_runtime import PROVIDER, verify_aar


class ChromiumAarTests(unittest.TestCase):
    def _fake_aar(self, path: Path, provider: bool) -> str:
        jar = BytesIO()
        with ZipFile(jar, "w") as j:
            if provider:
                j.writestr(PROVIDER, b"test-class-placeholder")
            else:
                j.writestr("Unrelated.class", b"not a Chromium embedder")
        with ZipFile(path, "w") as aar:
            aar.writestr("classes.jar", jar.getvalue())
        return sha256(path.read_bytes()).hexdigest()

    def test_rejects_aar_without_native_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "engine.aar"
            digest = self._fake_aar(p, False)
            with self.assertRaisesRegex(ValueError, "lacks"):
                verify_aar(p, digest)

    def test_rejects_wrong_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "engine.aar"
            self._fake_aar(p, True)
            with self.assertRaisesRegex(ValueError, "mismatch"):
                verify_aar(p, "f" * 64)

    def test_checks_class_and_digest_without_claiming_extension_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "engine.aar"
            digest = self._fake_aar(p, True)
            self.assertEqual(verify_aar(p, digest), digest)
            # Passing this package-structure test does not prove AdBlock.
