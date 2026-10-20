#!/usr/bin/env python3
"""Apply the product overlay to a pinned *native* Chromium checkout.

No prebuilt Chromium, WebView2 wrapper or binary resource editing is used.
The upstream engine version is retained separately from the product version.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = json.loads((ROOT / 'native/chromium/product.json').read_text())
STAMP = '.internet-browser-overlay.json'

try:
    from .windows_artwork import ARTWORK_PATHS, artwork
except ImportError:
    from windows_artwork import ARTWORK_PATHS, artwork


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f'Pinned source anchor changed: {old!r}')
    return text.replace(old, new, 1)


def brand_metadata(text: str) -> str:
    for key in ('PRODUCT_FULLNAME', 'PRODUCT_SHORTNAME'):
        text = replace_once(text, f'{key}=Chromium\n',
                            f'{key}=Internet Browser\n')
    for key in ('PRODUCT_INSTALLER_FULLNAME', 'PRODUCT_INSTALLER_SHORTNAME'):
        text = replace_once(text, f'{key}=Chromium Installer\n',
                            f'{key}=Internet Browser Installer\n')
    # Chromium copyright, author identity and licence attribution are retained.
    return text


def brand_install_modes(text: str) -> str:
    replacements = {
        'kProductPathName[] = L"Chromium"':
            'kProductPathName[] = L"Internet Browser"',
        '.base_app_name = L"Chromium"':
            '.base_app_name = L"Internet Browser"',
        '.base_app_id = L"Chromium"':
            '.base_app_id = L"InternetBrowser"',
        '.browser_prog_id_prefix = L"ChromiumHTM"':
            '.browser_prog_id_prefix = L"InternetBrowserHTM"',
        'L"Chromium HTML Document"': 'L"Internet Browser HTML Document"',
        '.direct_launch_url_scheme = "chromium"':
            '.direct_launch_url_scheme = "internet-browser"',
        '.pdf_prog_id_prefix = L"ChromiumPDF"':
            '.pdf_prog_id_prefix = L"InternetBrowserPDF"',
        'L"Chromium PDF Document"': 'L"Internet Browser PDF Document"',
        'L"{7D2B3E1D-D096-4594-9D8F-A6667F12E0AC}"':
            'L"{57452552-D43D-4DAD-AD1B-6F4E32063543}"',
    }
    for old, new in replacements.items():
        text = replace_once(text, old, new)
    return text


def brand_messages(text: str, *, xtb: bool = False) -> str:
    """Keep message IDs, placeholders and copyright intact.

    Changing GRD messages changes their GRIT fingerprints. The caller must
    remap XTB IDs with the exact pinned GRIT implementation below. Latin-only
    boundaries also match Korean suffixes such as Chromium의 and Chromium에서.
    """
    tag = 'translation' if xtb else 'message'
    pattern = rf'(<{tag}\b[^>]*>)(.*?)(</{tag}>)'
    def transform(match: re.Match) -> str:
        body = match[2]
        if 'Copyright' not in body and 'Chromium Authors' not in body:
            body = re.sub(r'(?<![A-Za-z])Chromium(?![A-Za-z])', 'Internet Browser', body)
        return match[1] + body + match[3]
    result = re.sub(pattern, transform, text, flags=re.S)
    ET.fromstring(result)
    return result


def translation_id_map(checkout: Path, before: str, after: str) -> dict[str, str]:
    """Use upstream GRIT itself; never guess translation fingerprints."""
    import io
    sys.path.insert(0, str(checkout / 'tools/grit'))
    try:
        from grit import grd_reader
        from grit.node.message import MessageNode
        def messages(text):
            node = grd_reader.Parse(io.StringIO(text),
                dir=str(checkout / 'chrome/app'), tags_to_ignore={'translations'},
                skip_validation_checks=True)
            return node.GetChildrenOfType(MessageNode)
        original, branded = messages(before), messages(after)
        if len(original) != len(branded):
            raise ValueError('Branding unexpectedly changed GRD message structure')
        result = {}
        for old, new in zip(original, branded):
            if old.attrs['name'] != new.attrs['name']:
                raise ValueError('Branding unexpectedly changed message order')
            old_id = str(old.GetCliques()[0].GetId())
            new_id = str(new.GetCliques()[0].GetId())
            if old_id != new_id:
                if old_id in result and result[old_id] != new_id:
                    raise ValueError('Ambiguous translation ID remapping')
                result[old_id] = new_id
        return result
    finally:
        sys.path.pop(0)


def remap_translation_ids(text: str, mapping: dict[str, str]) -> str:
    return re.sub(r'(<translation\b[^>]*\bid=")([^"]+)(")',
        lambda match: match[1] + mapping.get(match[2], match[2]) + match[3], text)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def overlay_path(checkout: Path, relative: str) -> Path:
    allowed = {
        'chrome/app/theme/chromium/BRANDING',
        'chrome/app/theme/chromium/win/chromium.ico',
        'chrome/app/chromium_strings.grd',
        'chrome/install_static/chromium_install_modes.h',
        'chrome/browser/chrome_browser_main_win.cc',
        'chrome/browser/BUILD.gn',
        'chrome/browser/ui/webui/chrome_web_ui_configs.cc',
        'chrome/browser/ui/webui/BUILD.gn',
        'chrome/installer/mini_installer/chrome.release',
        'chrome/installer/mini_installer/BUILD.gn',
        'chrome/browser/internet_browser/ciadpi.exe',
        'chrome/browser/internet_browser/LICENSE-byeDPI.txt',
    }
    localized = re.fullmatch(r'chrome/app/resources/chromium_strings_[a-zA-Z0-9_-]+\.xtb', relative)
    owned = re.fullmatch(r'chrome/browser/internet_browser/[a-z_]+\.(?:cc|h|gn)', relative)
    # BUILD.gn includes uppercase letters, so handle that owned name explicitly.
    if not (relative in allowed or relative in ARTWORK_PATHS or localized or owned or
            relative == 'chrome/browser/internet_browser/BUILD.gn'):
        raise ValueError(f'Unexpected overlay path: {relative}')
    path = (checkout / relative).resolve()
    if not path.is_relative_to(checkout):
        raise ValueError('Overlay path escapes the Chromium workspace')
    return path


def remove_overlay(checkout: Path) -> None:
    """Undo only our exact, hash-verified overlay before gclient synchronizes.

    Unrelated source modifications and changed generated files are never reset.
    No recursive deletion or broad git reset/clean is performed.
    """
    checkout = checkout.resolve(strict=True)
    stamp = checkout / STAMP
    if not stamp.exists():
        return
    old = json.loads(stamp.read_text(encoding='utf-8'))
    head = subprocess.check_output(
        ['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    if head != old['product']['chromium_revision']:
        raise ValueError('Source revision changed since overlay application')
    originals: dict[Path, bytes | None] = {}
    tracked = []
    for relative, expected in old['files'].items():
        path = overlay_path(checkout, relative)
        if digest(path) != expected:
            raise ValueError(f'Refusing to overwrite edits to {relative}')
        original = subprocess.run(['git', '-C', str(checkout), 'show',
                                   f'HEAD:{relative}'], capture_output=True)
        if original.returncode == 0:
            originals[path] = original.stdout
            tracked.append(relative)
        elif relative.startswith('chrome/browser/internet_browser/'):
            originals[path] = None
        else:
            raise ValueError(f'Cannot restore original source file: {relative}')
    for path, content in originals.items():
        if content is None:
            path.unlink()
        else:
            path.write_bytes(content)
    # Git for Windows can retain stale CRLF/stat metadata after restoring a
    # byte-identical blob. Refresh only the verified original tracked paths.
    if tracked:
        subprocess.run(['git', '-C', str(checkout), 'add', '--', *tracked], check=True)
        staged = subprocess.check_output(['git', '-C', str(checkout), 'diff-index',
                                           '--cached', '--name-only', 'HEAD'], text=True)
        if staged.strip():
            raise ValueError('Restoring exact upstream bytes unexpectedly changed the source index')
    stamp.unlink()


def resource_header(android: bool = False) -> bytes:
    try:
        from .native_notices import license_page
    except ImportError:
        from native_notices import license_page
    resources = ['#ifndef CHROME_BROWSER_INTERNET_BROWSER_RESOURCES_H_',
                 '#define CHROME_BROWSER_INTERNET_BROWSER_RESOURCES_H_',
                 'namespace internet_browser {']
    for filename, constant in [('index.html', 'kIndexHtml'), ('app.js', 'kAppJs'),
                               ('style.css', 'kStyleCss'), ('video_player.js', 'kVideoPlayerJs')]:
        content = (ROOT / 'native/chromium/windows/resources' / filename).read_text(encoding='utf-8')
        if ')IBRESOURCE"' in content:
            raise ValueError('Unexpected raw-string delimiter in native resources')
        resources.append(f'inline constexpr char {constant}[] = R"IBRESOURCE({content})IBRESOURCE";')
    logo = (ROOT / 'assets/icon/parcel.svg').read_text(encoding='utf-8')
    if ')IBRESOURCE"' in logo:
        raise ValueError('Unexpected raw-string delimiter in product logo')
    resources.append(f'inline constexpr char kLogoSvg[] = R"IBRESOURCE({logo})IBRESOURCE";')
    notices = license_page(android)
    if ')IBRESOURCE"' in notices:
        raise ValueError('Unexpected raw-string delimiter in upstream notices')
    resources.append(f'inline constexpr char kLicensesHtml[] = R"IBRESOURCE({notices})IBRESOURCE";')
    resources.extend(['}', '#endif', ''])
    return '\n'.join(resources).encode()


def prepare(checkout: Path, transport_directory: Path | None = None) -> dict:
    checkout = checkout.resolve(strict=True)
    revision = subprocess.check_output(
        ['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PRODUCT['chromium_revision']:
        raise ValueError('Refusing to modify an unpinned Chromium source revision')
    stamp = checkout / STAMP
    if stamp.exists():
        old = json.loads(stamp.read_text(encoding='utf-8'))
        if old['product'] != PRODUCT:
            raise ValueError('Overlay product changed; use a fresh source checkout')
        for relative, expected in old['files'].items():
            if digest(overlay_path(checkout, relative)) != expected:
                raise ValueError(f'Applied overlay has unexpected changes: {relative}')
        return old

    # Refuse unrelated edits, even if they would otherwise match an anchor.
    status = subprocess.check_output(
        ['git', '-C', str(checkout), 'status', '--porcelain', '-uno'], text=True)
    if status.strip():
        raise ValueError('Chromium checkout has tracked modifications; use a fresh checkout')
    changes: dict[str, bytes] = {}
    if transport_directory is None:
        raise ValueError('Verified transport payload directory is required')
    binary = (transport_directory / 'ciadpi.exe').read_bytes()
    if hashlib.sha256(binary).hexdigest() != 'eb53ceeeb981cc6735ac24bb1e51e725280b86630e80fdf19ddc4ee4a5b54ef4':
        raise ValueError('Verified ByeDPI executable payload differs')
    changes['chrome/browser/internet_browser/ciadpi.exe'] = binary
    changes['chrome/browser/internet_browser/LICENSE-byeDPI.txt'] = (
        ROOT / 'third_party/byedpi/LICENSE').read_bytes()
    def update(relative: str, transform) -> None:
        path = checkout / relative
        changes[relative] = transform(path.read_text(encoding='utf-8')).encode()

    update('chrome/app/theme/chromium/BRANDING', brand_metadata)
    # Version-directory payloads are moved and removed atomically by Chromium's
    # installer. DIR_MODULE resolves beside chrome.dll in both installed and
    # build-output layouts, so transport follows the running browser version.
    update('chrome/installer/mini_installer/chrome.release', lambda text:
        replace_once(text, '[GENERAL]\n', '[GENERAL]\n'
            'tools\\ciadpi.exe: %(VersionDir)s\\tools\\\n'
            'tools\\LICENSE-byeDPI.txt: %(VersionDir)s\\tools\\\n'))
    update('chrome/installer/mini_installer/BUILD.gn', lambda text:
        replace_once(replace_once(text,
            '    ":chrome_runtime_deps",\n',
            '    ":chrome_runtime_deps",\n'
            '    "//chrome/browser/internet_browser:transport_payload",\n'),
            '    "$root_out_dir/chrome.dll",\n',
            '    "$root_out_dir/chrome.dll",\n'
            '    "$root_out_dir/tools/ciadpi.exe",\n'
            '    "$root_out_dir/tools/LICENSE-byeDPI.txt",\n'))
    update('chrome/install_static/chromium_install_modes.h', brand_install_modes)
    grd_before = (checkout / 'chrome/app/chromium_strings.grd').read_text(encoding='utf-8')
    grd_after = brand_messages(grd_before)
    mapping = translation_id_map(checkout, grd_before, grd_after)
    changes['chrome/app/chromium_strings.grd'] = grd_after.encode()
    for path in sorted((checkout / 'chrome/app/resources').glob('chromium_strings_*.xtb')):
        update(path.relative_to(checkout).as_posix(),
               lambda text: remap_translation_ids(brand_messages(text, xtb=True), mapping))

    include = '#include "chrome/browser/internet_browser/transport.h"\n'
    def integrate_main(text: str) -> str:
        text = replace_once(text,
            '#include "chrome/browser/chrome_browser_main_win.h"\n',
            '#include "chrome/browser/chrome_browser_main_win.h"\n' + include +
            '#include "chrome/browser/prefs/session_startup_pref.h"\n')
        text = replace_once(text,
            '  ChromeBrowserMainParts::PostProfileInit(profile, is_initial_profile);\n',
            '  ChromeBrowserMainParts::PostProfileInit(profile, is_initial_profile);\n'
            '  if (is_initial_profile) {\n'
            '    auto* settings = profile->GetPrefs();\n'
            '    if (SessionStartupPref::TypeIsDefault(settings)) {\n'
            '      SessionStartupPref startup(SessionStartupPref::URLS);\n'
            '      startup.urls.emplace_back("chrome://internet-browser/");\n'
            '      SessionStartupPref::SetStartupPref(profile, startup);\n'
            '    }\n'
            '    if (settings->FindPreference(prefs::kHomePage)->IsDefaultValue()) {\n'
            '      settings->SetString(prefs::kHomePage, "chrome://internet-browser/");\n'
            '      settings->SetBoolean(prefs::kHomePageIsNewTabPage, false);\n'
            '    }\n'
            '    if (settings->FindPreference(prefs::kShowHomeButton)->IsDefaultValue())\n'
            '      settings->SetBoolean(prefs::kShowHomeButton, true);\n'
            '  }\n')
        text = replace_once(text,
            'void ChromeBrowserMainPartsWin::PostMainMessageLoopRun() {\n',
            'void ChromeBrowserMainPartsWin::PostMainMessageLoopRun() {\n'
            '  internet_browser::StopTransport();\n')
        # Start after initial relaunch/de-elevation decisions, before network
        # contexts exist. Only the browser process starts this owned service.
        anchor = ('  return content::RESULT_CODE_NORMAL_EXIT;\n}\n\n'
                  'void ChromeBrowserMainPartsWin::ToolkitInitialized()')
        return replace_once(text, anchor,
            '  internet_browser::StartTransport();\n' + anchor)
    update('chrome/browser/chrome_browser_main_win.cc', integrate_main)
    update('chrome/browser/BUILD.gn', lambda text: replace_once(text,
        '  if (is_win) {\n    sources += [\n      "chrome_browser_main_win.cc",',
        '  if (is_win) {\n'
        '    deps += [ "//chrome/browser/internet_browser:transport" ]\n'
        '    sources += [\n      "chrome_browser_main_win.cc",'))
    def integrate_configs(text: str) -> str:
        text = replace_once(text,
            '#include "chrome/browser/ui/webui/conflicts/conflicts_ui.h"\n',
            '#include "chrome/browser/ui/webui/conflicts/conflicts_ui.h"\n'
            '#include "chrome/browser/internet_browser/internet_browser_ui.h"\n')
        return replace_once(text,
            '  map.AddWebUIConfig(std::make_unique<ConflictsUIConfig>());',
            '  map.AddWebUIConfig(std::make_unique<ConflictsUIConfig>());\n'
            '  map.AddWebUIConfig(std::make_unique<InternetBrowserUIConfig>());')
    update('chrome/browser/ui/webui/chrome_web_ui_configs.cc', integrate_configs)
    def integrate_config_build(text: str) -> str:
        prefix, rest = text.split('source_set("configs") {', 1)
        body, suffix = rest.split('source_set("webui") {', 1)
        body = replace_once(body, '  deps = [\n',
                            '  deps = [\n    "//chrome/browser/internet_browser:ui",\n')
        return prefix + 'source_set("configs") {' + body + 'source_set("webui") {' + suffix
    update('chrome/browser/ui/webui/BUILD.gn', integrate_config_build)
    for path in sorted((ROOT / 'native/chromium/common/overlay').glob('*')):
        if path.is_file():
            changes['chrome/browser/internet_browser/' + path.name] = path.read_bytes()
    for path in sorted((ROOT / 'native/chromium/windows/overlay').glob('*')):
        if path.is_file():
            changes['chrome/browser/internet_browser/' + path.name] = path.read_bytes()
    changes['chrome/browser/internet_browser/resources.h'] = resource_header()

    # Generate all native product images without touching provider artwork.
    changes.update(artwork(checkout, ROOT))
    # Validate everything before changing any source file.
    for relative, data in changes.items():
        path = overlay_path(checkout, relative)
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(data)
    result = {'product': PRODUCT, 'files': {
        path: hashlib.sha256(data).hexdigest() for path, data in changes.items()},
        'translation_ids_remapped': len(mapping),
        'native_build_verified': False, 'runtime_verified': False}
    stamp.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkout', required=True, type=Path)
    parser.add_argument('--remove', action='store_true')
    parser.add_argument('--transport-dir', type=Path)
    options = parser.parse_args()
    if options.remove:
        remove_overlay(options.checkout)
        print('Removed only the exact hash-verified product overlay.')
        raise SystemExit(0)
    report = prepare(options.checkout, options.transport_dir)
    print(f"Applied native Windows product overlay: {len(report['files'])} files. "
          'Compilation and extension runtime verification are still required.')
