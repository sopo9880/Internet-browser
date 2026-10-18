#!/usr/bin/env python3
"""Verify a separately built Android Chromium embedder AAR before packaging.

A stock ChromePublic.apk cannot be embedded in Flutter as an AAR. The
extension-capable Chromium fork must export a provider implementation
matching the Kotlin EmbeddedChromiumEngine interface and be independently
validated for licensing, CVEs and the real AdBlock extension.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile, BadZipFile

PROVIDER = (
    "io/github/sopo9880/internet_browser/chromium/"
    "ChromiumEngineProvider.class"
)


def verify_aar(path: Path, expected_sha256: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("BROWSER_ANDROID_CHROMIUM_AAR_SHA256 is required")
    if not path.is_file():
        raise FileNotFoundError(f"Chromium embedder AAR missing: {path}")
    actual = sha256(path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise ValueError("Chromium embedder AAR SHA-256 mismatch")
    try:
        with ZipFile(path) as aar:
            if "classes.jar" not in aar.namelist():
                raise ValueError("AAR has no classes.jar")
            with ZipFile(BytesIO(aar.read("classes.jar"))) as classes:
                if PROVIDER not in classes.namelist():
                    raise ValueError(
                        "AAR lacks the embedded ChromiumEngineProvider contract"
                    )
    except BadZipFile as exc:
        raise ValueError("Invalid Chromium embedder AAR/JAR archive") from exc
    return actual
