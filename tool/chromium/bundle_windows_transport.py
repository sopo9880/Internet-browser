"""Stage the existing SHA-256 pinned ByeDPI distribution for native Chromium."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

VERSION = '0.17.3'
ARCHIVE = 'byedpi-17.3-x86_64-w64.zip'
SHA256 = '70d2c94147193cb915f9c6eb5144b8d404dacbcfa90bda2383b6b211afafa456'
ROOT = Path(__file__).resolve().parents[2]


def bundle(output: Path) -> dict[str, str]:
    url = f'https://github.com/hufrea/byedpi/releases/download/v{VERSION}/{ARCHIVE}'
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read(16 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('ByeDPI archive SHA-256 mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        matches = [name for name in archive.namelist()
                   if name.replace('\\', '/').split('/')[-1] == 'ciadpi.exe']
        if len(matches) != 1:
            raise ValueError('Expected exactly one pinned ciadpi.exe')
        binary = archive.read(matches[0])
    if not binary.startswith(b'MZ'):
        raise ValueError('ByeDPI executable is not a Windows PE file')
    target = output / 'tools'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'ciadpi.exe').write_bytes(binary)
    (target / 'LICENSE-byeDPI.txt').write_bytes(
        (ROOT / 'third_party/byedpi/LICENSE').read_bytes())
    return {'version': VERSION, 'archive_sha256': SHA256,
            'executable_sha256': hashlib.sha256(binary).hexdigest()}
