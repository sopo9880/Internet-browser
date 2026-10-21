"""Synchronize pinned Android dependencies without executing build hooks."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

from prepare_android_hooks import prepare as prepare_hooks
from prepare_titanium_patches import PRODUCT, head
from titanium_pin import SOURCE_SHA, VANADIUM_SHA


def sync(workspace: Path) -> None:
    import fcntl
    workspace = workspace.resolve()
    with (workspace / '.native-android-source.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        titanium = workspace / 'titanium'
        source = titanium / 'chromium/src'
        depot = titanium / 'depot_tools'
        report = json.loads((workspace / 'titanium-patches.json').read_text(encoding='utf-8'))
        if (report['chromium_base'] != PRODUCT['chromium_revision'] or
                report['titanium_revision'] != SOURCE_SHA or report['vanadium_revision'] != VANADIUM_SHA or
                head(source) != report['patched_head'] or head(titanium) != SOURCE_SHA or
                head(titanium / 'vanadium') != VANADIUM_SHA or head(depot) != PRODUCT['depot_tools_revision']):
            raise ValueError('Prepared Android source pins differ')
        if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '-uno'], text=True).strip():
            raise ValueError('Android source has unreviewed tracked edits')
        prepare_hooks(titanium)
        env = os.environ.copy()
        env.update({'DEPOT_TOOLS_UPDATE': '0', 'DEPOT_TOOLS_METRICS': '0',
                    'DEPOT_TOOLS_BUILD_TELEMETRY': '0', 'GIT_CONFIG_COUNT': '1',
                    'GIT_CONFIG_KEY_0': 'core.autocrlf', 'GIT_CONFIG_VALUE_0': 'false'})
        env['PATH'] = str(depot) + os.pathsep + env.get('PATH', '')
        subprocess.run([str(depot / 'gclient'), 'sync', '--no-history', '--nohooks', '-j', '2'],
                       cwd=titanium / 'chromium', env=env, check=True)
        report.update({'dependencies_synced': True, 'hooks_run': False, 'compiled': False,
                       'release_approved': False})
        (workspace / 'titanium-dependencies.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('Android dependency synchronization completed. Hooks and compilation remain.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args()
    sync(args.workspace)
