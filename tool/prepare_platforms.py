#!/usr/bin/env python3
"""Prepare the generated AndroidManifest.xml for browser network access.

Never place a permission between the XML prolog and the <manifest> root.
Validate XML after insertion and make repeated runs safe.
"""

from pathlib import Path
import re
import xml.etree.ElementTree as ET

manifest = Path("android/app/src/main/AndroidManifest.xml")
if not manifest.exists():
    raise SystemExit("AndroidManifest.xml missing; run flutter create first.")

source = manifest.read_text(encoding="utf-8")
permission = '<uses-permission android:name="android.permission.INTERNET" />'
if "android.permission.INTERNET" not in source:
    opening = re.search(r"<manifest\b[^>]*>", source)
    if opening is None:
        raise SystemExit("AndroidManifest.xml has no manifest root.")
    source = source[:opening.end()] + "\n    " + permission + source[opening.end():]

try:
    root = ET.fromstring(source)
except ET.ParseError as exc:
    raise SystemExit(f"AndroidManifest.xml is invalid: {exc}") from exc

if root.tag != "manifest":
    raise SystemExit(f"Unexpected Android manifest root: {root.tag}")

manifest.write_text(source, encoding="utf-8")
print("Android manifest permission and XML validated.")
