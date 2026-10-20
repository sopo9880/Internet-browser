"""Obtain immutable native Android source pins in a dedicated Linux cache.

This phase intentionally runs no third-party build scripts, hooks or sudo.
It can overlap Windows compilation; Android compilation must be serialized.
"""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path
import platform
import shutil
import subprocess

from titanium_pin import SOURCE_REPO, SOURCE_SHA, VANADIUM_SHA

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = json.loads((ROOT / 'native/chromium/product.json').read_text(encoding='utf-8'))


def run(*args, cwd: Path | None = None) -> None:
    subprocess.run([str(value) for value in args], cwd=cwd, check=True)


def obtain(path: Path, repository: str, revision: str) -> None:
    if not path.exists():
        path.mkdir(parents=True)
        run('git', 'init', path)
        run('git', '-C', path, 'remote', 'add', 'origin', repository)
    if not (path / '.git').is_dir():
        raise ValueError(f'Existing path is not an owned Git checkout: {path}')
    remote = subprocess.check_output(['git', '-C', str(path), 'remote', 'get-url', 'origin'], text=True).strip()
    if remote != repository:
        raise ValueError(f'Existing source repository differs: {path}')
    status = subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '-uno'], text=True)
    head = subprocess.run(['git', '-C', str(path), 'rev-parse', '--verify', 'HEAD'], capture_output=True, text=True)
    # An unmaterialized clone has index deletions; permit it only when its
    # index is empty and no tracked worktree exists. Never reset an edited tree.
    index = subprocess.check_output(['git', '-C', str(path), 'ls-files'], text=True)
    if status.strip() and index.strip():
        raise ValueError(f'Source checkout contains edits: {path}')
    if head.stdout.strip() != revision or not index.strip():
        if index.strip():
            raise ValueError(f'Existing checkout revision differs: {path}')
        run('git', '-C', path, 'fetch', '--depth', '1', 'origin', revision)
        run('git', '-C', path, 'checkout', '--detach', revision)
    actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != revision:
        raise ValueError('Source pin verification failed')


def prepare(workspace: Path) -> None:
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
        raise ValueError('Android source preparation requires Linux x64')
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(workspace).free < 120 * 1024**3:
        raise ValueError('Android source cache requires at least 120 GiB free')
    with (workspace / '.native-android-source.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        titanium = workspace / 'titanium'
        obtain(titanium, SOURCE_REPO, SOURCE_SHA)
        run('git', '-C', titanium, 'submodule', 'update', '--init', '--depth', '1', 'vanadium')
        actual = subprocess.check_output(['git', '-C', str(titanium / 'vanadium'), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != VANADIUM_SHA:
            raise ValueError('Vanadium submodule revision differs')
        obtain(titanium / 'depot_tools', PRODUCT['depot_tools_repository'], PRODUCT['depot_tools_revision'])
        client = titanium / 'chromium'
        client.mkdir(exist_ok=True)
        obtain(client / 'src', PRODUCT['chromium_repository'], PRODUCT['chromium_revision'])
        report = {'titanium_revision': SOURCE_SHA, 'vanadium_revision': VANADIUM_SHA,
                  'chromium_revision': PRODUCT['chromium_revision'],
                  'depot_tools_revision': PRODUCT['depot_tools_revision'],
                  'source_pins_verified': True, 'dependencies_synced': False,
                  'compiled': False, 'release_approved': False}
        (workspace / 'source-preparation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('Pinned native Android source obtained; dependencies, product integration and compilation remain.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args()
    prepare(args.workspace)
