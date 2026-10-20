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
import struct
import subprocess
import xml.etree.ElementTree as ET

try:
    from .prepare_windows import ROOT, PRODUCT, translation_id_map, remap_translation_ids, replace_once, resource_header
except ImportError:
    from prepare_windows import ROOT, PRODUCT, translation_id_map, remap_translation_ids, replace_once, resource_header


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


def product_path(checkout: Path, relative: str) -> Path:
    allowed = {
        'chrome/android/java/AndroidManifest.xml',
        'chrome/browser/extensions/extension_safety_check_utils.cc',
        'chrome/browser/chrome_browser_main_android.cc', 'chrome/browser/BUILD.gn',
        'chrome/browser/ui/webui/chrome_web_ui_configs.cc', 'chrome/browser/ui/webui/BUILD.gn',
        'chrome/android/BUILD.gn', 'chrome/android/chrome_java_sources.gni',
        'chrome/android/java/src/org/chromium/chrome/browser/ChromeApplicationImpl.java',
        'chrome/android/java/src/org/chromium/chrome/browser/InternetBrowserLegacySnapshot.java',
        'chrome/android/java/src/org/chromium/chrome/browser/LegacyStringListDecoder.java',
        'chrome/android/java/src/org/chromium/chrome/browser/homepage/HomepageManager.java',
        'chrome/browser/internet_browser/BUILD.gn',
        'chrome/browser/internet_browser/libciadpi.so',
        'chrome/browser/internet_browser/LICENSE-byeDPI.txt',
    }
    resource = re.fullmatch(r'(?:chrome|components|ui)/[A-Za-z0-9_./-]+\.(?:grd|grdp|xtb)', relative)
    icon = re.fullmatch(r'chrome/android/java/res_titanium_base/[A-Za-z0-9_/-]+\.(?:png|xml)', relative)
    owned = re.fullmatch(r'chrome/browser/internet_browser/[a-z_]+\.(?:cc|h)', relative)
    if relative not in allowed and not (resource or icon or owned):
        raise ValueError('Unexpected Android product overlay path')
    path = (checkout / relative).resolve()
    if not path.is_relative_to(checkout) or '\\' in relative or '..' in Path(relative).parts:
        raise ValueError('Android overlay path escapes its source workspace')
    return path


def remove_product_overlay(checkout: Path) -> None:
    checkout = checkout.resolve(strict=True)
    stamp = checkout / '.internet-browser-android-overlay.json'
    if not stamp.exists():
        return
    report = json.loads(stamp.read_text(encoding='utf-8'))
    head = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    if head != report.get('source_revision'):
        raise ValueError('Android source revision changed since product application')
    originals = {}
    for relative, expected in report['files'].items():
        path = product_path(checkout, relative)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Android overlay contains subsequent edits: {relative}')
        original = subprocess.run(['git', '-C', str(checkout), 'show', 'HEAD:' + relative], capture_output=True)
        originals[path] = original.stdout if original.returncode == 0 else None
    # Validate the entire overlay before restoring or deleting any owned file.
    for path, data in originals.items():
        if data is None:
            path.unlink()
        else:
            path.write_bytes(data)
    stamp.unlink()


def native_changes(checkout: Path, transport: Path) -> dict[Path, bytes]:
    binary = transport.read_bytes()
    provenance = json.loads(transport.with_name('transport-provenance.json').read_text(encoding='utf-8'))
    if (binary[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<HH', binary, 16) != (3, 183)
            or provenance.get('sha256') != hashlib.sha256(binary).hexdigest()
            or provenance.get('source_revision') != '7efde1b1296eaaa187b70e951894dde17527489c'
            or provenance.get('ndk_version') != '30.0.16248370' or not provenance.get('compiled')):
        raise ValueError('Android-native transport provenance differs')
    changes = native_source_changes(checkout)
    directory = checkout / 'chrome/browser/internet_browser'
    changes[directory / 'libciadpi.so'] = binary
    changes[directory / 'LICENSE-byeDPI.txt'] = (ROOT / 'third_party/byedpi/LICENSE').read_bytes()
    return changes


def native_source_changes(checkout: Path) -> dict[Path, bytes]:
    """Validate source anchors without applying or claiming compilation."""
    directory = checkout / 'chrome/browser/internet_browser'
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Refusing an existing Android product source overlay')
    changes = {directory / 'resources.h': resource_header()}
    for name in ('internet_browser_ui.cc', 'internet_browser_ui.h', 'transport.h', 'legacy_data.h'):
        changes[directory / name] = (ROOT / 'native/chromium/windows/overlay' / name).read_bytes()
    for path in (ROOT / 'native/chromium/common/overlay').iterdir():
        if path.is_file():
            changes[directory / path.name] = path.read_bytes()
    for path in (ROOT / 'native/chromium/android/overlay').iterdir():
        if path.is_file():
            changes[directory / path.name] = path.read_bytes()
    def update(relative, transform):
        path = checkout / relative
        changes[path] = transform(path.read_text(encoding='utf-8')).encode()
    def main(text):
        text = replace_once(text, '#include "chrome/browser/chrome_browser_main_android.h"\n',
            '#include "chrome/browser/chrome_browser_main_android.h"\n'
            '#include "chrome/browser/internet_browser/transport.h"\n')
        text = replace_once(text, 'ChromeBrowserMainPartsAndroid::~ChromeBrowserMainPartsAndroid() = default;',
            'ChromeBrowserMainPartsAndroid::~ChromeBrowserMainPartsAndroid() {\n'
            '  internet_browser::StopTransport();\n}')
        return replace_once(text, '  content::Compositor::Initialize();',
            '  internet_browser::StartTransport();\n  content::Compositor::Initialize();')
    update('chrome/browser/chrome_browser_main_android.cc', main)
    update('chrome/browser/BUILD.gn', lambda text: replace_once(text,
        '  if (is_android) {\n    sources += [\n      "after_startup_task_utils_android.cc",',
        '  if (is_android) {\n    deps += [ "//chrome/browser/internet_browser:transport" ]\n'
        '    sources += [\n      "after_startup_task_utils_android.cc",'))
    def configs(text):
        text = replace_once(text, '#include "chrome/browser/ui/webui/chrome_web_ui_configs.h"\n',
            '#include "chrome/browser/ui/webui/chrome_web_ui_configs.h"\n'
            '#include "chrome/browser/internet_browser/internet_browser_ui.h"\n')
        return replace_once(text, '  auto& map = content::WebUIConfigMap::GetInstance();',
            '  auto& map = content::WebUIConfigMap::GetInstance();\n'
            '  map.AddWebUIConfig(std::make_unique<InternetBrowserUIConfig>());')
    update('chrome/browser/ui/webui/chrome_web_ui_configs.cc', configs)
    def config_build(text):
        prefix, rest = text.split('source_set("configs") {', 1)
        body, suffix = rest.split('source_set("webui") {', 1)
        body = replace_once(body, '  deps = [\n',
            '  deps = [\n    "//chrome/browser/internet_browser:ui",\n')
        return prefix + 'source_set("configs") {' + body + 'source_set("webui") {' + suffix
    update('chrome/browser/ui/webui/BUILD.gn', config_build)
    payload = ('    asset_deps = [ "//chrome/browser/internet_browser:transport_payload",\n'
               '                   "//chrome/browser/internet_browser:transport_license_assets" ]\n'
               '    loadable_modules = [ "$root_out_dir/libciadpi.so" ]\n')
    def android_build(text):
        text = replace_once(text,
            '  chrome_public_apk_or_module_tmpl("chrome_public_apk") {\n',
            '  chrome_public_apk_or_module_tmpl("chrome_public_apk") {\n' + payload)
        text = replace_once(text, '  chrome_public_bundle("chrome_public_bundle") {\n',
            '  chrome_public_bundle("chrome_public_bundle") {\n' + payload)
        anchor = ('    chrome_public_apk_or_module_tmpl(_base_module_target_name) {\n'
                  '      forward_variables_from(invoker,\n'
                  '                             [\n')
        return replace_once(text, anchor, anchor +
            '                               "asset_deps",\n'
            '                               "loadable_modules",\n')
    update('chrome/android/BUILD.gn', android_build)
    java_directory = checkout / 'chrome/android/java/src/org/chromium/chrome/browser'
    for path in (ROOT / 'native/chromium/android/java').glob('*.java'):
        if (java_directory / path.name).exists():
            raise ValueError('Existing Android migration helper would be overwritten')
        changes[java_directory / path.name] = path.read_bytes()
    update('chrome/android/chrome_java_sources.gni', lambda text: replace_once(text,
        '  "java/src/org/chromium/chrome/browser/ChromeApplicationImpl.java",',
        '  "java/src/org/chromium/chrome/browser/ChromeApplicationImpl.java",\n'
        '  "java/src/org/chromium/chrome/browser/InternetBrowserLegacySnapshot.java",\n'
        '  "java/src/org/chromium/chrome/browser/LegacyStringListDecoder.java",'))
    update('chrome/android/java/src/org/chromium/chrome/browser/ChromeApplicationImpl.java',
        lambda text: replace_once(text, '    public void onCreate() {\n        super.onCreate();\n',
            '    public void onCreate() {\n        super.onCreate();\n'
            '        InternetBrowserLegacySnapshot.prepare(getApplication());\n'))
    def homepage(text):
        text = replace_once(text,
            '    private GURL getDefaultHomepageGurlInternal(boolean isIncognito, boolean forZeroTabs) {\n',
            '    private GURL getDefaultHomepageGurlInternal(boolean isIncognito, boolean forZeroTabs) {\n'
            '        if (!isIncognito) return new GURL("chrome://internet-browser/");\n')
        return replace_once(text, 'boolean defaultEnabled = !isDesktopExceptionEnabled();',
                            'boolean defaultEnabled = true;')
    update('chrome/android/java/src/org/chromium/chrome/browser/homepage/HomepageManager.java', homepage)
    return changes


def prepare(checkout: Path, transport: Path) -> dict:
    subprocess.run(['git', '-C', str(checkout), 'merge-base', '--is-ancestor',
                    PRODUCT['chromium_revision'], 'HEAD'], check=True)
    stamp = checkout / '.internet-browser-android-overlay.json'
    if stamp.exists():
        raise ValueError('Android product overlay is already applied; use its verified build cache')
    manifest = checkout / 'chrome/android/java/AndroidManifest.xml'
    manifest_text = manifest.read_text(encoding='utf-8')
    if 'android:extractNativeLibs="false"' not in manifest_text:
        raise ValueError('Pinned Titanium native-library manifest anchor changed')
    changes: dict[Path, bytes] = native_changes(checkout, transport)
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
    tracked = {checkout / path for path in subprocess.check_output(
        ['git', '-C', str(checkout), 'ls-files', '-z'], text=True).split('\0') if path}
    # Resource XML only: source identifiers and upstream copyright stay intact.
    for directory in ('chrome', 'components', 'ui'):
        for pattern in ('*.grd', '*.grdp'):
            for path in sorted((checkout / directory).rglob(pattern)):
                if path not in tracked:
                    continue
                before = path.read_text(encoding='utf-8')
                after = brand(before)
                if before == after:
                    continue
                for old, new in fingerprints(checkout, before, after).items():
                    if old in mapping and mapping[old] != new:
                        raise ValueError('Ambiguous Android translation fingerprint')
                    mapping[old] = new
                changes[path] = after.encode()
    for directory in ('chrome', 'components', 'ui'):
        for path in sorted((checkout / directory).rglob('*.xtb')):
            if path not in tracked:
                continue
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
        product_path(checkout, path.relative_to(checkout).as_posix())
    for path, data in changes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    report = {'product': PRODUCT, 'source_revision': subprocess.check_output(
        ['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip(), 'files': {
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
    parser.add_argument('--transport', type=Path)
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    if args.remove:
        remove_product_overlay(args.checkout.resolve())
        print('Removed only the exact hash-verified Android product overlay.')
        raise SystemExit(0)
    if args.transport is None:
        parser.error('--transport is required when applying the product overlay')
    result = prepare(args.checkout.resolve(), args.transport.resolve())
    print(f"Prepared Android product overlay ({len(result['files'])} files). APK validation remains required.")
