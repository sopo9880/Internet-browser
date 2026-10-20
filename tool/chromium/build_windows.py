#!/usr/bin/env python3
"""Build native Chromium without depending on PowerShell execution policy."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = json.loads((ROOT / 'native/chromium/product.json').read_text())


@contextmanager
def workspace_lock(workspace: Path):
    import msvcrt
    with (workspace / '.internet-browser-build.lock').open('a+b') as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError('Native workspace is already in use by another build') from error
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def run(command, *, cwd: Path, env: dict):
    command = [str(part) for part in command]
    if command[0].lower().endswith(('.bat', '.cmd')):
        command = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', *command]
    print('Running:', Path(command[0]).name, flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def build(workspace: Path, jobs: int, prepare_only: bool,
          stage: Path | None) -> None:
    if os.name != 'nt':
        raise RuntimeError('The native Windows builder requires Windows x64')
    workspace = workspace.resolve()
    if any(character.isspace() for character in str(workspace)):
        raise ValueError('Chromium workspace path must not contain spaces')
    workspace.mkdir(exist_ok=True, parents=True)
    if shutil.disk_usage(workspace).free < 120 * 1024 ** 3:
        raise RuntimeError('Native Chromium requires at least 120 GiB of free disk')
    env = os.environ.copy()
    env.update({
        'DEPOT_TOOLS_WIN_TOOLCHAIN': '0', 'DEPOT_TOOLS_UPDATE': '0',
        'DEPOT_TOOLS_METRICS': '0',
        'DEPOT_TOOLS_BUILD_TELEMETRY': '0',
        'GIT_CONFIG_COUNT': '2', 'GIT_CONFIG_KEY_0': 'core.longpaths',
        'GIT_CONFIG_VALUE_0': 'true', 'GIT_CONFIG_KEY_1': 'core.autocrlf',
        'GIT_CONFIG_VALUE_1': 'false',
    })
    with workspace_lock(workspace):
        depot = workspace / 'depot_tools'
        source = workspace / 'src'
        if not (depot / '.git').exists():
            run(['git', 'clone', PRODUCT['depot_tools_repository'], depot], cwd=workspace, env=env)
        run(['git', '-C', depot, 'fetch', '--depth', '1', 'origin', PRODUCT['depot_tools_revision']], cwd=workspace, env=env)
        run(['git', '-C', depot, 'checkout', '--detach', PRODUCT['depot_tools_revision']], cwd=workspace, env=env)
        env['PATH'] = str(depot) + os.pathsep + env['PATH']
        if not (source / '.git').exists():
            run(['git', 'clone', '--depth', '1', '--branch', PRODUCT['chromium_version'],
                 '--single-branch', PRODUCT['chromium_repository'], source], cwd=workspace, env=env)
        revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], env=env, text=True).strip()
        if revision != PRODUCT['chromium_revision']:
            raise RuntimeError('Chromium source revision differs from the reviewed pin')
        client = workspace / '.gclient'
        expected_client = ('solutions = [{"name": "src", "url": "' + PRODUCT['chromium_repository'] +
            '", "managed": False, "custom_deps": {}, "custom_vars": {}}]\ntarget_os = ["win"]\n')
        if client.exists() and client.read_text(encoding='utf-8').strip() != expected_client.strip():
            raise RuntimeError('Existing .gclient differs from the native Windows configuration')
        client.write_text(expected_client, encoding='utf-8', newline='\n')
        overlay = ROOT / 'tool/chromium/prepare_windows.py'
        run([sys.executable, overlay, '--checkout', source, '--remove'], cwd=ROOT, env=env)
        run([depot / 'gclient.bat', 'sync', '--no-history', '--nohooks', '-j', '2',
             '--revision', 'src@' + PRODUCT['chromium_revision']], cwd=workspace, env=env)
        if prepare_only:
            print('Pinned Windows source/dependencies prepared. No compilation performed.')
            return
        vswhere = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
        visual_studio = subprocess.check_output([str(vswhere), '-latest', '-products', '*',
            '-version', '[18.0,19.0)', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
            '-property', 'installationPath'], text=True).strip()
        if not visual_studio:
            raise RuntimeError('VS 2026 Desktop C++ and ATL/MFC are required')
        env['vs2026_install'] = visual_studio
        run([depot / 'gclient.bat', 'runhooks'], cwd=workspace, env=env)
        run([sys.executable, overlay, '--checkout', source], cwd=ROOT, env=env)
        output = source / 'out/InternetBrowser'
        output.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(ROOT / 'native/chromium/windows/args.gn', output / 'args.gn')
        from bundle_windows_transport import bundle
        transport = bundle(output)
        # gclient bootstraps vpython. Invoke the pinned Python entry points
        # through it so GN and its scripts share a complete Python runtime.
        # The legacy .bat shims require a second, independently bootstrapped
        # python-bin runtime and can fail even after a successful sync.
        vpython = depot / '.cipd_bin/vpython3.exe'
        if not vpython.is_file():
            raise RuntimeError('gclient did not bootstrap its pinned vpython runtime')
        run([vpython, depot / 'gn.py', 'gen', 'out/InternetBrowser'], cwd=source, env=env)
        # Compile the product's own translation units first. This schedules
        # their generated-header dependencies and catches API drift before
        # spending hours on unrelated Chromium C++ targets.
        run([vpython, depot / 'autoninja.py', '-C', 'out/InternetBrowser', '-j', str(jobs),
             'obj/chrome/browser/internet_browser/transport/transport.obj',
             'obj/chrome/browser/internet_browser/legacy_data/legacy_data.obj',
             'obj/chrome/browser/internet_browser/ui/internet_browser_ui.obj'], cwd=source, env=env)
        run([vpython, depot / 'autoninja.py', '-C', 'out/InternetBrowser', '-j', str(jobs),
             'chrome', 'mini_installer'], cwd=source, env=env)
        names = ['chrome.exe', 'chrome.7z', 'mini_installer.exe']
        for name in names:
            if not (output / name).is_file() or not (output / name).stat().st_size:
                raise RuntimeError('Missing actual native build output: ' + name)
        report = {
            'product': PRODUCT,
            'integration_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'files': {name: sha256(output / name) for name in names},
            'overlay': json.loads((source / '.internet-browser-overlay.json').read_text(encoding='utf-8')),
            'native_source_compiled': True, 'runtime_verified': False,
            'byedpi': transport,
            'release_approved': False,
        }
        report_file = output / 'native-provenance.json'
        report_file.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if stage:
            stage = stage.resolve()
            stage.mkdir(exist_ok=True, parents=True)
            for name in ['chrome.7z', 'mini_installer.exe', 'native-provenance.json']:
                shutil.copyfile(output / name, stage / name)
        if os.environ.get('GITHUB_OUTPUT'):
            with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as outputs:
                outputs.write(f'chrome_exe={output / "chrome.exe"}\n')
        print('Native Chromium compiled. Runtime/AdBlock/release acceptance remains required.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--jobs', type=int, choices=range(1, 5), default=3)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--stage', type=Path)
    args = parser.parse_args()
    build(args.workspace, args.jobs, args.prepare_only, args.stage)
