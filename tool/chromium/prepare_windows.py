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
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = json.loads((ROOT / 'native/chromium/product.json').read_text())
STAMP = '.internet-browser-overlay.json'


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

    Changing a translatable GRD message would invalidate its XTB fingerprint.
    Only nontranslatable product names are changed in GRD at this stage.
    Translated messages retain their IDs and have their rendered brand text
    replaced in XTB. Broader English rebranding needs a GRIT ID remap.
    """
    tag = 'translation' if xtb else 'message'
    pattern = rf'(<{tag}\b[^>]*>)(.*?)(</{tag}>)'
    def transform(match: re.Match) -> str:
        body = match[2]
        if (xtb or 'translateable="false"' in match[1]) and (
                'Copyright' not in body and 'Chromium Authors' not in body):
            body = re.sub(r'\bChromium\b', 'Internet Browser', body)
        return match[1] + body + match[3]
    result = re.sub(pattern, transform, text, flags=re.S)
    ET.fromstring(result)
    return result


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
    }
    localized = re.fullmatch(r'chrome/app/resources/chromium_strings_[a-zA-Z0-9_-]+\.xtb', relative)
    owned = re.fullmatch(r'chrome/browser/internet_browser/[a-z_]+\.(?:cc|h|gn)', relative)
    # BUILD.gn includes uppercase letters, so handle that owned name explicitly.
    if not (relative in allowed or localized or owned or
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
    for relative, expected in old['files'].items():
        path = overlay_path(checkout, relative)
        if digest(path) != expected:
            raise ValueError(f'Refusing to overwrite edits to {relative}')
        original = subprocess.run(['git', '-C', str(checkout), 'show',
                                   f'HEAD:{relative}'], capture_output=True)
        if original.returncode == 0:
            originals[path] = original.stdout
        elif relative.startswith('chrome/browser/internet_browser/'):
            originals[path] = None
        else:
            raise ValueError(f'Cannot restore original source file: {relative}')
    for path, content in originals.items():
        if content is None:
            path.unlink()
        else:
            path.write_bytes(content)
    stamp.unlink()


def prepare(checkout: Path) -> dict:
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
    def update(relative: str, transform) -> None:
        path = checkout / relative
        changes[relative] = transform(path.read_text(encoding='utf-8')).encode()

    update('chrome/app/theme/chromium/BRANDING', brand_metadata)
    update('chrome/install_static/chromium_install_modes.h', brand_install_modes)
    update('chrome/app/chromium_strings.grd', brand_messages)
    for path in sorted((checkout / 'chrome/app/resources').glob('chromium_strings_*.xtb')):
        update(path.relative_to(checkout).as_posix(),
               lambda text: brand_messages(text, xtb=True))

    include = '#include "chrome/browser/internet_browser/transport.h"\n'
    def integrate_main(text: str) -> str:
        text = replace_once(text,
            '#include "chrome/browser/chrome_browser_main_win.h"\n',
            '#include "chrome/browser/chrome_browser_main_win.h"\n' + include)
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
    for path in sorted((ROOT / 'native/chromium/windows/overlay').glob('*')):
        if path.is_file():
            changes['chrome/browser/internet_browser/' + path.name] = path.read_bytes()
    resources = ['#ifndef CHROME_BROWSER_INTERNET_BROWSER_RESOURCES_H_',
                 '#define CHROME_BROWSER_INTERNET_BROWSER_RESOURCES_H_',
                 'namespace internet_browser {']
    for filename, constant in [('index.html', 'kIndexHtml'), ('app.js', 'kAppJs'),
                               ('style.css', 'kStyleCss')]:
        content = (ROOT / 'native/chromium/windows/resources' / filename).read_text(encoding='utf-8')
        if ')IBRESOURCE"' in content:
            raise ValueError('Unexpected raw-string delimiter in native resources')
        resources.append(f'inline constexpr char {constant}[] = R"IBRESOURCE({content})IBRESOURCE";')
    resources.extend(['}', '#endif', ''])
    changes['chrome/browser/internet_browser/resources.h'] = '\n'.join(resources).encode()

    # Generate the native Windows icon from this repository's existing asset.
    from PIL import Image
    import io
    icon = Image.open(ROOT / 'assets/icon/parcel.png').convert('RGBA')
    output = io.BytesIO()
    icon.save(output, format='ICO', sizes=[(16, 16), (24, 24), (32, 32),
                                         (48, 48), (64, 64), (128, 128), (256, 256)])
    icon_path = 'chrome/app/theme/chromium/win/chromium.ico'
    if not (checkout / icon_path).is_file():
        raise ValueError('Pinned Chromium native Windows icon path changed')
    changes[icon_path] = output.getvalue()
    # Validate everything before changing any source file.
    for relative, data in changes.items():
        path = overlay_path(checkout, relative)
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(data)
    result = {'product': PRODUCT, 'files': {
        path: hashlib.sha256(data).hexdigest() for path, data in changes.items()},
        'native_build_verified': False, 'runtime_verified': False}
    stamp.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkout', required=True, type=Path)
    parser.add_argument('--remove', action='store_true')
    options = parser.parse_args()
    if options.remove:
        remove_overlay(options.checkout)
        print('Removed only the exact hash-verified product overlay.')
        raise SystemExit(0)
    report = prepare(options.checkout)
    print(f"Applied native Windows product overlay: {len(report['files'])} files. "
          'Compilation and extension runtime verification are still required.')
