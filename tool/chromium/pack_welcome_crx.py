#!/usr/bin/env python3
"""Bundle our opt-in first-run MV3 welcome as a signed CRX3.

Only this small Internet-browser welcome extension is bundled. The actual
third-party AdBlock extension must be chosen and installed by the user.
Research builds use a disposable private key; production MUST pin the
welcome extension signing identity before enabling updates.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import os
import struct
import subprocess
import zipfile

WELCOME_FILES = (
    "manifest.json",
    "background.js",
    "welcome.html",
    "welcome.css",
    "welcome.js",
)
ADBLOCK_ID = "gighmmpiobklfepjocnamgkkbiglidom"
CRX_MAGIC = b"Cr24"


def varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("Protobuf unsigned integer cannot be negative")
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result) + bytes([value])


def proto_bytes(field_number: int, value: bytes) -> bytes:
    return varint((field_number << 3) | 2) + varint(len(value)) + value


def extension_id(public_der: bytes) -> str:
    return "".join(
        chr(ord("a") + nibble)
        for b in sha256(public_der).digest()[:16]
        for nibble in (b >> 4, b & 15)
    )


def zip_extension(source: Path) -> bytes:
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 3 or manifest.get("version") != "0.2.0":
        raise ValueError("Expected pinned Manifest V3 welcome extension")
    if manifest.get("background", {}).get("service_worker") != "background.js":
        raise ValueError("Welcome extension requires its own background worker")
    html = (source / "welcome.html").read_text(encoding="utf-8")
    if ADBLOCK_ID not in html:
        raise ValueError("Welcome must link to the exact requested AdBlock")
    if "chromewebstore.google.com/detail/adblock/" not in html:
        raise ValueError("Welcome must link to the legitimate Chrome Web Store")
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in WELCOME_FILES:
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (source / name).read_bytes())
    return payload.getvalue()


def _run(args: list[str], *, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        args, input=input_bytes, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=True,
    )
    return result.stdout


def package_welcome(
    source: Path, template: Path, dist: Path, private_key: Path,
) -> str:
    contents = zip_extension(source)
    private_key.parent.mkdir(parents=True, exist_ok=True)
    if not private_key.exists():
        _run([
            "openssl", "genpkey", "-algorithm", "RSA",
            "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private_key),
        ])
        os.chmod(private_key, 0o600)
    public_der = _run([
        "openssl", "pkey", "-in", str(private_key), "-pubout",
        "-outform", "DER",
    ])
    ext_id = extension_id(public_der)
    crx_id = sha256(public_der).digest()[:16]
    signed_header = proto_bytes(1, crx_id)
    data_to_sign = (
        b"CRX3 SignedData\x00" +
        struct.pack("<I", len(signed_header)) +
        signed_header + contents
    )
    signature = _run(
        [
            "openssl", "dgst", "-sha256", "-sign", str(private_key),
            "-sigopt", "rsa_padding_mode:pss",
            "-sigopt", "rsa_pss_saltlen:-1",
        ],
        input_bytes=data_to_sign,
    )
    proof = proto_bytes(1, public_der) + proto_bytes(2, signature)
    header = proto_bytes(2, proof) + proto_bytes(10000, signed_header)
    crx = (
        CRX_MAGIC + struct.pack("<I", 3) +
        struct.pack("<I", len(header)) + header + contents
    )

    build_file = template.read_text(encoding="utf-8")
    source_anchor = '    "bundled.json",'
    destination_anchor = '    "extensions/bundled.json",'
    if build_file.count(source_anchor) != 1 or build_file.count(destination_anchor) != 1:
        raise ValueError("Titanium extension GN asset template changed")
    build_file = build_file.replace(
        source_anchor, source_anchor + '\n    "welcome.crx",'
    ).replace(
        destination_anchor,
        destination_anchor + '\n    "extensions/welcome.crx",',
    )
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "welcome.crx").write_bytes(crx)
    (dist / "BUILD.gn").write_text(build_file, encoding="utf-8")
    (dist / "bundled.json").write_text(
        json.dumps(
            {ext_id: {
                "external_crx": "welcome.crx",
                "external_version": "0.2.0",
            }},
            sort_keys=True,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return ext_id


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--template", type=Path, required=True)
    p.add_argument("--dist", type=Path, required=True)
    p.add_argument("--key", type=Path, required=True)
    args = p.parse_args()
    extension = package_welcome(
        args.source, args.template, args.dist, args.key,
    )
    print(f"Bundled optional first-run Chromium welcome extension: {extension}")
    print("AdBlock itself was NOT installed or verified.")


if __name__ == "__main__":
    main()
