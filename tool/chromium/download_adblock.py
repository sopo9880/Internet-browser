"""Obtain and authenticate the actual requested AdBlock for isolated testing.

This does not install an extension or certify browser/runtime compatibility.
CRX3 framing and the publisher key follow pinned Chromium components/crx_file.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile

EXTENSION_ID = 'gighmmpiobklfepjocnamgkkbiglidom'
PUBLISHER_KEY_SHA256 = '61f7f2a6bfcf74cd0bc1fe2497cc9b04254c658f79f2145392867ea8366367cf'
MAX_BYTES = 128 * 1024 * 1024


def varint(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if position >= len(data):
            raise ValueError('Truncated CRX3 protobuf')
        byte = data[position]
        position += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, position
    raise ValueError('Oversized CRX3 varint')


def fields(data: bytes) -> list[tuple[int, bytes]]:
    result = []
    position = 0
    while position < len(data):
        tag, position = varint(data, position)
        if tag >> 3 == 0 or tag & 7 != 2:
            raise ValueError('Unexpected CRX3 protobuf wire type')
        length, position = varint(data, position)
        if length > len(data) - position:
            raise ValueError('Truncated CRX3 field')
        result.append((tag >> 3, data[position:position + length]))
        position += length
    return result


def extension_id(data: bytes) -> str:
    return ''.join(chr(97 + nibble) for byte in data for nibble in (byte >> 4, byte & 15))


def verify(data: bytes, openssl: Path) -> dict:
    if len(data) < 12 or len(data) > MAX_BYTES or data[:4] != b'Cr24':
        raise ValueError('Invalid or oversized CRX3 package')
    version, size = struct.unpack('<II', data[4:12])
    if version != 3 or size > 1024 * 1024 or 12 + size >= len(data):
        raise ValueError('Invalid CRX3 header')
    header = fields(data[12:12 + size])
    signed = [value for number, value in header if number == 10000]
    if len(signed) != 1:
        raise ValueError('Expected one CRX3 signed header')
    declared = [value for number, value in fields(signed[0]) if number == 1]
    if len(declared) != 1 or len(declared[0]) != 16 or extension_id(declared[0]) != EXTENSION_ID:
        raise ValueError('Package does not have the requested AdBlock identity')
    archive = data[12 + size:]
    signed_bytes = b'CRX3 SignedData\0' + struct.pack('<I', len(signed[0])) + signed[0] + archive
    publisher = developer = False
    proofs = [value for number, value in header if number in (2, 3)]
    if not proofs or len(proofs) > 16:
        raise ValueError('Missing or excessive CRX3 signing proofs')
    with tempfile.TemporaryDirectory(prefix='adblock_crx_verify_') as temporary:
        folder = Path(temporary)
        message = folder / 'signed-data.bin'
        message.write_bytes(signed_bytes)
        for proof in proofs:
            entries = fields(proof)
            keys = [value for number, value in entries if number == 1]
            signatures = [value for number, value in entries if number == 2]
            if len(keys) != 1 or len(signatures) != 1:
                raise ValueError('Ambiguous CRX3 signing proof')
            key, signature = keys[0], signatures[0]
            (folder / 'key.der').write_bytes(key)
            (folder / 'signature.bin').write_bytes(signature)
            result = subprocess.run([str(openssl), 'dgst', '-sha256', '-verify', str(folder / 'key.der'),
                '-keyform', 'DER', '-signature', str(folder / 'signature.bin'), str(message)], capture_output=True)
            if result.returncode:
                raise ValueError('CRX3 signature verification failed')
            digest = hashlib.sha256(key).digest()
            developer |= digest[:16] == declared[0]
            publisher |= digest.hex() == PUBLISHER_KEY_SHA256
    if not developer or not publisher:
        raise ValueError('Missing valid developer or official Web Store publisher proof')
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        manifest_info = zipped.getinfo('manifest.json')
        if manifest_info.file_size > 512 * 1024:
            raise ValueError('Oversized extension manifest')
        manifest = json.loads(zipped.read(manifest_info))
    return {'extension_id': EXTENSION_ID, 'version': manifest['version'],
            'manifest_version': manifest['manifest_version'], 'background': manifest.get('background'),
            'sha256': hashlib.sha256(data).hexdigest(), 'publisher_signature_verified': publisher,
            'developer_signature_verified': developer, 'store_installation_verified': False,
            'runtime_verified': False, 'request_blocking_verified': False, 'release_approved': False}


def download(destination: Path, openssl: Path) -> dict:
    product = json.loads((Path(__file__).resolve().parents[2] / 'native/chromium/product.json').read_text(encoding='utf-8'))
    query = urllib.parse.urlencode({'response': 'redirect', 'prodversion': product['chromium_version'],
                                   'acceptformat': 'crx3', 'x': 'id=' + EXTENSION_ID + '&uc'})
    url = 'https://clients2.google.com/service/update2/crx?' + query
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(MAX_BYTES + 1)
    report = verify(data, openssl)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'adblock.crx').write_bytes(data)
    report['source_url'] = url
    (destination / 'package-verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--openssl', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(download(args.destination, args.openssl), ensure_ascii=True))
