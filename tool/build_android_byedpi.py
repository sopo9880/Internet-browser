#!/usr/bin/env python3
"""Build pinned MIT ByeDPI 0.17.3 as Android PIE executables in jniLibs.

These are Android NDK-built native binaries, NOT Linux ARM release binaries.
They are packaged with .so filenames for extraction to nativeLibraryDir.
This is intentionally limited to in-app WebView proxy traffic: no VPN.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

UPSTREAM = "https://github.com/hufrea/byedpi.git"
COMMIT = "7efde1b1296eaaa187b70e951894dde17527489c"
VERSION = os.environ.get("BROWSER_ANDROID_NDK_VERSION", "27.3.13750724")
ANDROID_SDK = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
if not ANDROID_SDK:
    raise SystemExit("ANDROID_SDK_ROOT is required")
ndk = Path(ANDROID_SDK, "ndk", VERSION)
toolchain = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
if not toolchain.exists():
    raise SystemExit(f"Android NDK {VERSION} clang toolchain is unavailable")

targets = {
    "arm64-v8a": "aarch64-linux-android24-clang",
    "armeabi-v7a": "armv7a-linux-androideabi24-clang",
    "x86_64": "x86_64-linux-android24-clang",
}
with tempfile.TemporaryDirectory(prefix="byedpi_android_") as work:
    checkout = Path(work, "byedpi")
    subprocess.run(["git", "clone", "--branch", "v0.17.3",
                    "--depth", "1", UPSTREAM, str(checkout)], check=True)
    resolved = subprocess.check_output(["git", "-C", str(checkout),
                                        "rev-parse", "HEAD"], text=True).strip()
    if resolved != COMMIT:
        raise SystemExit(f"Untrusted ByeDPI source commit: {resolved}")
    for abi, compiler in targets.items():
        cc = toolchain / compiler
        if not cc.is_file():
            raise SystemExit(f"NDK compiler missing: {cc}")
        subprocess.run(["make", "clean"], cwd=checkout, check=True)
        subprocess.run(
            ["make", "all", f"CC={cc}",
             "CFLAGS=-I. -std=c99 -O2 -Wall -Wextra -Wno-unused-parameter -fPIE",
             "LDFLAGS=-pie"],
            cwd=checkout, check=True,
        )
        binary = checkout / "ciadpi"
        if not binary.is_file():
            raise SystemExit(f"No ByeDPI Android binary for {abi}")
        target = Path("android/app/src/main/jniLibs") / abi / "libciadpi.so"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, target)
        print(f"Bundled Android-native ByeDPI: {abi} ({target.stat().st_size} bytes)")
print("Android ByeDPI native binaries produced from pinned MIT source.")
