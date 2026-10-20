"""Run the pinned Android dependency hooks before applying product source."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from prepare_android_hooks import prepare as prepare_hooks
from prepare_titanium_patches import PRODUCT, head
from titanium_pin import SOURCE_SHA, VANADIUM_SHA


def run_hooks(workspace: Path) -> None:
    import fcntl
    workspace = workspace.resolve()
    with (workspace / '.native-android-source.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        titanium = workspace / 'titanium'
        source = titanium / 'chromium/src'
        depot = titanium / 'depot_tools'
        report = json.loads((workspace / 'titanium-dependencies.json').read_text(encoding='utf-8'))
        if (not report.get('dependencies_synced') or report['chromium_base'] != PRODUCT['chromium_revision'] or
                report['titanium_revision'] != SOURCE_SHA or report['vanadium_revision'] != VANADIUM_SHA or
                head(source) != report['patched_head'] or head(titanium) != SOURCE_SHA or
                head(titanium / 'vanadium') != VANADIUM_SHA or head(depot) != PRODUCT['depot_tools_revision']):
            raise ValueError('Synchronized Android source pins differ')
        if (source / '.internet-browser-android-overlay.json').exists():
            raise ValueError('Dependency hooks must run before the product overlay')
        prepare_hooks(titanium)
        env = os.environ.copy()
        env.update({'DEPOT_TOOLS_UPDATE': '0', 'DEPOT_TOOLS_METRICS': '0',
                    'DEPOT_TOOLS_BUILD_TELEMETRY': '0',
                    'GIT_COMMITTER_NAME': 'Internet-browser Chromium Build',
                    'GIT_COMMITTER_EMAIL': 'internet-browser-ci@users.noreply.github.com',
                    'GIT_CONFIG_COUNT': '3', 'GIT_CONFIG_KEY_0': 'core.autocrlf',
                    'GIT_CONFIG_VALUE_0': 'false', 'GIT_CONFIG_KEY_1': 'commit.gpgsign',
                    'GIT_CONFIG_VALUE_1': 'false', 'GIT_CONFIG_KEY_2': 'core.hooksPath',
                    'GIT_CONFIG_VALUE_2': '/dev/null'})
        env['PATH'] = str(depot) + os.pathsep + env.get('PATH', '')
        subprocess.run([str(depot / 'gclient'), 'runhooks'], cwd=titanium / 'chromium', env=env, check=True)
        if head(source) != report['patched_head']:
            raise ValueError('Android hook unexpectedly changed the root source revision')
        filters = source / 'titanium/android_config/filter_lists'
        report.update({'hooks_run': True, 'compiled': False, 'release_approved': False,
                       'filter_list_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                              for path in sorted(filters.glob('*.txt'))}})
        (workspace / 'titanium-hooks.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('Pinned Android hooks completed. Product overlay, GN and compilation remain.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args()
    run_hooks(args.workspace)
