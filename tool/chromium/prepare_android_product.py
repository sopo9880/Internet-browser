"""Product branding and security overlay for pinned Titanium Android source.

Run after Titanium's patches and before GN generation. This is source preparation,
not evidence of a compiled, safe, or release-ready APK.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

try:
    from .prepare_windows import ROOT, PRODUCT, translation_id_map, remap_translation_ids
except ImportError:
    from prepare_windows import ROOT, PRODUCT, translation_id_map, remap_translation_ids


def brand(text: str, *, xtb: bool = False) -> str:
    tag = 'translation' if xtb else 'message'
    def replace(match):
        body = match[2]
        if not re.search(r'copyright|authors|licen[cs]e', body, re.I):
            body = re.sub(r'(?<![A-Za-z])(?:Titanium|Vanadium|Chromium)(?![A-Za-z])',
                          'Internet Browser', body)
        return match[1] + body + match[3]
    result = re.sub(rf'(<{tag}\b[^>]*>)(.*?)(</{tag}>)', replace, text, flags=re.S)
    ET.fromstring(result)
    return result


def fingerprints(checkout: Path, before: str, after: str) -> dict[str, str]:
    # A clique fingerprint depends on the message and its meaning, not its
    # enclosing resource file. Wrap just the local message nodes so included
    # GRDP files can each be translated without reading already modified parts.
    def wrap(text):
        nodes = re.findall(r'<message\b[^>]*>.*?</message>', text, re.S)
        return ('<grit latest_public_release="0" current_release="1" source_lang_id="en">'
                '<release seq="1"><messages>' + ''.join(nodes) + '</messages></release></grit>')
    return translation_id_map(checkout, wrap(before), wrap(after))


def prepare(checkout: Path) -> dict:
    subprocess.run(['git', '-C', str(checkout), 'merge-base', '--is-ancestor',
                    PRODUCT['chromium_revision'], 'HEAD'], check=True)
    stamp = checkout / '.internet-browser-android-overlay.json'
    if stamp.exists():
        raise ValueError('Android product overlay is already applied; use its verified build cache')
    manifest = checkout / 'chrome/android/java/AndroidManifest.xml'
    manifest_text = manifest.read_text(encoding='utf-8')
    if 'android:extractNativeLibs="false"' not in manifest_text:
        raise ValueError('Pinned Titanium native-library manifest anchor changed')
    changes: dict[Path, bytes] = {}
    # A packaged executable under nativeLibraryDir needs OS extraction. It is
    # never downloaded into writable app data for execution.
    changes[manifest] = manifest_text.replace(
        'android:extractNativeLibs="false"', 'android:extractNativeLibs="true"', 1).encode()
    safety = checkout / 'chrome/browser/extensions/extension_safety_check_utils.cc'
    safety_text = safety.read_text(encoding='utf-8')
    bypass = 'if (extension.location() == mojom::ManifestLocation::kExternalPref) return false;\n'
    if safety_text.count(bypass) != 1:
        raise ValueError('Pinned Titanium external-extension safety bypass changed')
    changes[safety] = safety_text.replace(bypass, '', 1).encode()

    mapping: dict[str, str] = {}
    # Resource XML only: source identifiers and upstream copyright stay intact.
    for directory in ('chrome', 'components'):
        for pattern in ('*.grd', '*.grdp'):
            for path in sorted((checkout / directory).rglob(pattern)):
                before = path.read_text(encoding='utf-8')
                after = brand(before)
                if before == after:
                    continue
                for old, new in fingerprints(checkout, before, after).items():
                    if old in mapping and mapping[old] != new:
                        raise ValueError('Ambiguous Android translation fingerprint')
                    mapping[old] = new
                changes[path] = after.encode()
    for directory in ('chrome', 'components'):
        for path in sorted((checkout / directory).rglob('*.xtb')):
            before = path.read_text(encoding='utf-8')
            after = remap_translation_ids(brand(before, xtb=True), mapping)
            if after != before:
                changes[path] = after.encode()

    from PIL import Image
    icon = Image.open(ROOT / 'assets/icon/parcel.png').convert('RGBA')
    resource_root = checkout / 'chrome/android/java/res_titanium_base'
    if not resource_root.is_dir():
        raise ValueError('Pinned Titanium launcher resource directory missing')
    for path in resource_root.rglob('*.png'):
        with Image.open(path) as old:
            size = old.size
        image = Image.new('RGBA', size, 'black') if path.name == 'layered_app_icon_background.png' else icon.resize(size, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format='PNG')
        changes[path] = output.getvalue()
    # Reuse the exact parcel vector for the monochrome Android themed icon.
    svg = ET.fromstring((ROOT / 'assets/icon/parcel.svg').read_text(encoding='utf-8'))
    parcel = svg.find('{http://www.w3.org/2000/svg}path').attrib['d']
    vector = ('<vector xmlns:android="http://schemas.android.com/apk/res/android" '
              'android:width="108dp" android:height="108dp" '
              'android:viewportWidth="1254" android:viewportHeight="1254">'
              '<path android:fillColor="#000000" android:fillType="evenOdd" '
              f'android:pathData="{parcel}"/></vector>\n')
    changes[resource_root / 'drawable/themed_app_icon.xml'] = vector.encode()
    # Vanadium's adaptive foreground otherwise retains its original artwork.
    changes[resource_root / 'mipmap-nodpi/layered_app_icon_foreground.xml'] = (
        '<bitmap xmlns:android="http://schemas.android.com/apk/res/android" '
        'android:src="@mipmap/app_icon" android:gravity="center"/>\n').encode()
    for path, data in changes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    report = {'product': PRODUCT, 'files': {
        path.relative_to(checkout).as_posix(): hashlib.sha256(data).hexdigest()
        for path, data in changes.items()}, 'translation_ids_remapped': len(mapping),
        'external_extension_safety_bypass_removed': True,
        'compiled': False, 'device_security_verdict_verified': False,
        'release_approved': False}
    stamp.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkout', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.checkout.resolve())
    print(f"Prepared Android product overlay ({len(result['files'])} files). APK validation remains required.")
