"""Signed MV3 first-run Chromium welcome extension tests."""
from io import BytesIO
from pathlib import Path
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from zipfile import ZipFile

from tool.chromium.pack_welcome_crx import (
    ADBLOCK_ID, extension_id, package_welcome, proto_bytes, varint,
)

SOURCE = Path(__file__).resolve().parents[1] / "chromium" / "welcome_extension"
TEMPLATE = """import("//build/config/android/rules.gni")

android_assets("extension_assets") {
  disable_compression = true
  renaming_sources = [
    "bundled.json",
  ]
  renaming_destinations = [
    "extensions/bundled.json",
  ]
}
"""


def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    number = 0
    shift = 0
    while True:
        value = data[offset]
        offset += 1
        number |= (value & 0x7F) << shift
        if not value & 0x80:
            return number, offset
        shift += 7


def read_fields(data: bytes) -> dict[int, list[bytes]]:
    fields: dict[int, list[bytes]] = {}
    offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        length, offset = read_varint(data, offset)
        fields.setdefault(tag >> 3, []).append(data[offset:offset + length])
        offset += length
    return fields


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required")
class FirstRunCrxTests(unittest.TestCase):
    def test_unsigned_first_run_assets_do_not_install_adblock_silently(self):
        worker = (SOURCE / "background.js").read_text(encoding="utf-8")
        html = (SOURCE / "welcome.html").read_text(encoding="utf-8")
        self.assertIn("details.reason !== 'install'", worker)
        self.assertIn("welcomeShown", worker)
        self.assertIn(ADBLOCK_ID, html)
        self.assertIn("chromewebstore.google.com", html)
        self.assertNotIn("chrome.management.install", worker)
        self.assertNotIn("chrome.management.install", html)

    def test_crx3_is_signed_and_id_persists_with_same_private_key(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            template = root / "BUILD.gn"
            template.write_text(TEMPLATE, encoding="utf-8")
            dist = root / "dist"
            key = root / "welcome-key.pem"
            first_id = package_welcome(SOURCE, template, dist, key)
            self.assertEqual(len(first_id), 32)
            self.assertTrue(all('a' <= ch <= 'p' for ch in first_id))
            self.assertEqual(
                package_welcome(SOURCE, template, dist, key), first_id,
            )

            index = json.loads((dist / "bundled.json").read_text())
            self.assertIn(first_id, index)
            self.assertEqual(index[first_id]["external_crx"], "welcome.crx")
            gn = (dist / "BUILD.gn").read_text()
            self.assertIn('"welcome.crx"', gn)
            self.assertIn('"extensions/welcome.crx"', gn)

            crx = (dist / "welcome.crx").read_bytes()
            self.assertEqual(crx[:4], b"Cr24")
            self.assertEqual(struct.unpack("<I", crx[4:8])[0], 3)
            header_length = struct.unpack("<I", crx[8:12])[0]
            header = read_fields(crx[12:12 + header_length])
            payload = crx[12 + header_length:]
            proof = read_fields(header[2][0])
            signed_data = header[10000][0]
            der = proof[1][0]
            signature = proof[2][0]
            self.assertEqual(
                read_fields(signed_data)[1][0],
                bytes.fromhex("".join(format(ord(ch) - 97, "x") for ch in first_id)),
            )
            self.assertEqual(extension_id(der), first_id)
            with ZipFile(BytesIO(payload)) as archive:
                self.assertEqual(
                    json.loads(archive.read("manifest.json"))["manifest_version"], 3,
                )
                self.assertIn(ADBLOCK_ID, archive.read("welcome.html").decode())

            public_pem = root / "public.pem"
            public_pem.write_bytes(subprocess.run(
                ["openssl", "pkey", "-in", str(key), "-pubout"],
                capture_output=True, check=True,
            ).stdout)
            sigfile = root / "signature.bin"
            sigfile.write_bytes(signature)
            signed = (
                b"CRX3 SignedData\x00" +
                struct.pack("<I", len(signed_data)) + signed_data + payload
            )
            verification = subprocess.run(
                ["openssl", "dgst", "-sha256",
                 "-verify", str(public_pem), "-signature", str(sigfile),
                 "-sigopt", "rsa_padding_mode:pss",
                 "-sigopt", "rsa_pss_saltlen:-1"],
                input=signed, capture_output=True,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr)

    def test_protobuf_integer_encoding(self):
        self.assertEqual(varint(300), b"\xac\x02")
        self.assertEqual(proto_bytes(1, b"abc"), b"\x0a\x03abc")


if __name__ == "__main__":
    unittest.main()
