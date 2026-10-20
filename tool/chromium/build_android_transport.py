"""Build the pinned ByeDPI ARM64 PIE with Chromium's pinned Android NDK."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

REVISION = '7efde1b1296eaaa187b70e951894dde17527489c'
REPOSITORY = 'https://github.com/hufrea/byedpi.git'
NDK_VERSION = '30.0.16248370'  # Pinned Chromium 155 DEPS: 2@30.0.16248370.


def build(checkout: Path, workspace: Path) -> Path:
    ndk = checkout / 'third_party/android_toolchain/ndk'
    properties = (ndk / 'source.properties').read_text(encoding='utf-8')
    if not any(line.strip() == 'Pkg.Revision = ' + NDK_VERSION for line in properties.splitlines()):
        raise ValueError('Android NDK revision differs from the pinned Chromium toolchain')
    compiler = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android24-clang'
    if not compiler.is_file():
        raise ValueError('Pinned Android ARM64 compiler missing')
    workspace.mkdir(parents=True, exist_ok=True)
    source = workspace / 'byedpi'
    if not source.exists():
        subprocess.run(['git', 'init', str(source)], check=True)
        subprocess.run(['git', '-C', str(source), 'remote', 'add', 'origin', REPOSITORY], check=True)
        subprocess.run(['git', '-C', str(source), 'fetch', '--depth', '1', 'origin', REVISION], check=True)
        subprocess.run(['git', '-C', str(source), 'checkout', '--detach', REVISION], check=True)
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    status = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '-uno'], text=True)
    if actual != REVISION or status.strip():
        raise ValueError('ByeDPI source pin or tracked files differ')
    subprocess.run(['make', 'clean'], cwd=source, check=True)
    subprocess.run(['make', '-j', '1', 'all', 'CC=' + str(compiler),
        'CFLAGS=-I. -std=c99 -O2 -Wall -Wextra -Wno-unused-parameter -fPIE -fstack-protector-strong -D_FORTIFY_SOURCE=2',
        'LDFLAGS=-pie -Wl,-z,relro,-z,now,-z,max-page-size=16384'], cwd=source, check=True)
    binary = (source / 'ciadpi').read_bytes()
    if binary[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<HH', binary, 16) != (3, 183):
        raise ValueError('ByeDPI output is not an ARM64 Android PIE')
    output = workspace / 'libciadpi.so'
    shutil.copyfile(source / 'ciadpi', output)
    report = {'source_revision': REVISION, 'ndk_version': NDK_VERSION,
              'sha256': hashlib.sha256(binary).hexdigest(), 'abi': 'arm64-v8a',
              'compiled': True, 'device_verified': False, 'release_approved': False}
    (workspace / 'transport-provenance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkout', required=True, type=Path)
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args()
    print('Built Android-native transport:', build(args.checkout.resolve(), args.workspace.resolve()))
