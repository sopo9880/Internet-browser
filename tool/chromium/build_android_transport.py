"""Build the pinned ByeDPI ARM64 PIE with Chromium's pinned Android NDK."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

REVISION = '7efde1b1296eaaa187b70e951894dde17527489c'
REPOSITORY = 'https://github.com/hufrea/byedpi.git'
NDK_VERSION = '30.0.16248370'  # Pinned Chromium 155 DEPS: 2@30.0.16248370.
LLVM_VERSION = 'llvmorg-24-init-7747-g62397f8b-27'


def build(checkout: Path, workspace: Path) -> Path:
    ndk = checkout / 'third_party/android_toolchain/ndk'
    deps = (checkout / 'DEPS').read_text(encoding='utf-8')
    if "'android_ndk_version': Str('2@" + NDK_VERSION + "')" not in deps:
        raise ValueError('Android NDK revision differs from the pinned Chromium toolchain')
    # Chromium ships an NDK sysroot subset and its own pinned LLVM, rather
    # than the Android SDK's standalone compiler-wrapper scripts.
    llvm = checkout / 'third_party/llvm-build/Release+Asserts'
    compiler = llvm / 'bin/clang'
    sysroot = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/sysroot'
    if not compiler.is_file() or not sysroot.is_dir():
        raise ValueError('Pinned Android ARM64 compiler missing')
    if (llvm / 'cr_build_revision').read_text(encoding='utf-8').strip() != LLVM_VERSION:
        raise ValueError('Chromium LLVM revision differs')
    if not all(re.fullmatch(r'[A-Za-z0-9_./+-]+', str(path)) for path in (compiler, sysroot, workspace)):
        raise ValueError('Native make workspace paths must contain no spaces or shell metacharacters')
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
    compiler_command = str(compiler) + ' --target=aarch64-linux-android24 --sysroot=' + str(sysroot)
    subprocess.run(['make', '-j', '1', 'all', 'CC=' + compiler_command,
        'CFLAGS=-I. -std=c99 -O2 -Wall -Wextra -Wno-unused-parameter -fPIE -fstack-protector-strong -D_FORTIFY_SOURCE=2',
        'LDFLAGS=-pie -Wl,-z,relro,-z,now,-z,max-page-size=16384'], cwd=source, check=True)
    binary = (source / 'ciadpi').read_bytes()
    if binary[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<HH', binary, 16) != (3, 183):
        raise ValueError('ByeDPI output is not an ARM64 Android PIE')
    output = workspace / 'libciadpi.so'
    shutil.copyfile(source / 'ciadpi', output)
    report = {'source_revision': REVISION, 'ndk_version': NDK_VERSION, 'llvm_revision': LLVM_VERSION,
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
