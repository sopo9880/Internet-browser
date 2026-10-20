"""Checks APK staging invariants without pretending a ZIP fixture is an APK."""
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import zipfile
from tool.chromium.build_native_android import verify_payload

class NativeAndroidPayloadTests(unittest.TestCase):
    def fixture(self, root, *, changed_transport=False, wrong_arch=False, missing_license=False):
        payload=b'controlled-transport-payload'
        (root/'transport').write_bytes(payload)
        (root/'LICENSE').write_bytes(b'controlled upstream notice')
        header=bytearray(20);header[:6]=b'\x7fELF\x02\x01'
        struct.pack_into('<HH',header,16,3,62 if wrong_arch else 183)
        with zipfile.ZipFile(root/'fixture.zip','w') as z:
            z.writestr('lib/arm64-v8a/libciadpi.so',b'changed' if changed_transport else payload)
            z.writestr('lib/arm64-v8a/libchrome.so',header)
            if not missing_license:z.writestr('assets/licenses/ByeDPI.txt',b'controlled upstream notice')
        return root/'fixture.zip',root/'transport',root/'LICENSE'

    def test_payload_comparison_and_arm64_header(self):
        with TemporaryDirectory() as tmp:
            verify_payload(*self.fixture(Path(tmp)))

    def test_rejects_changed_transport_wrong_architecture_and_missing_notice(self):
        for setting in ('changed_transport','wrong_arch','missing_license'):
            with self.subTest(setting=setting),TemporaryDirectory() as tmp:
                with self.assertRaises((ValueError,KeyError)):
                    verify_payload(*self.fixture(Path(tmp),**{setting:True}))

    def test_missing_chromium_engine_is_rejected(self):
        with TemporaryDirectory() as tmp:
            paths=self.fixture(Path(tmp))
            with zipfile.ZipFile(paths[0],'w') as z:
                z.writestr('lib/arm64-v8a/libciadpi.so',paths[1].read_bytes())
                z.writestr('assets/licenses/ByeDPI.txt',paths[2].read_bytes())
            with self.assertRaisesRegex(ValueError,'Chromium engine'):
                verify_payload(*paths)

if __name__=='__main__':unittest.main()
