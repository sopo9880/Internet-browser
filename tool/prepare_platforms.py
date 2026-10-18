#!/usr/bin/env python3
from pathlib import Path
manifest = Path("android/app/src/main/AndroidManifest.xml")
if not manifest.exists():
    raise SystemExit("Run flutter create --platforms=android . first")
s = manifest.read_text(encoding="utf-8")
permission = '<uses-permission android:name="android.permission.INTERNET" />'
if "android.permission.INTERNET" not in s:
    s = s.replace(">", ">\n    " + permission, 1)
manifest.write_text(s, encoding="utf-8")
