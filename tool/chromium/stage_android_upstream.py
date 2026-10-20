"""Apply Titanium's pinned driver once and record its reusable source state."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from prepare_titanium_patches import PRODUCT, head
from titanium_pin import SOURCE_SHA, VANADIUM_SHA


def git(repository: Path, *arguments: str, env: dict | None = None) -> bytes:
    return subprocess.check_output(['git', '-C', str(repository), *arguments], env=env)


def stage(workspace: Path) -> None:
    import fcntl
    workspace = workspace.resolve()
    with (workspace / '.native-android-source.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        titanium = workspace / 'titanium'
        source = titanium / 'chromium/src'
        report = json.loads((workspace / 'titanium-hooks.json').read_text(encoding='utf-8'))
        destination = workspace / 'titanium-upstream.json'
        if destination.exists():
            raise ValueError('Titanium source driver already has a recorded result')
        if (not report.get('hooks_run') or head(source) != report['patched_head'] or
                report['chromium_base'] != PRODUCT['chromium_revision'] or
                head(titanium) != SOURCE_SHA or head(titanium / 'vanadium') != VANADIUM_SHA):
            raise ValueError('Prepared Android hook/source state differs')
        driver = titanium / 'patch.sh'
        if driver.read_bytes() != git(titanium, 'show', 'HEAD:patch.sh'):
            raise ValueError('Pinned Titanium driver contains edits')
        expected_subprojects = {'v8', 'third_party/search_engines_data/resources'}
        changed = set(git(source, 'diff', '--name-only').decode().splitlines())
        if changed - expected_subprojects or git(source, 'diff', '--cached', '--name-only').strip():
            raise ValueError('Unexpected root source edits before the pinned driver')
        repositories = ['v8', 'third_party/search_engines_data/resources',
                        'third_party/devtools-frontend/src', 'titanium']
        inputs = {}
        for relative in repositories:
            repository = source / relative
            if git(repository, 'status', '--porcelain', '-uno').strip():
                raise ValueError(f'Subproject has edits before the driver: {relative}')
            inputs[relative] = head(repository)
        arcore = source / 'third_party/arcore-android-sdk-client/AndroidManifest_basesplit.xml'
        arcore_before = arcore.read_bytes()
        original = workspace / 'upstream-arcore-original.xml'
        if original.exists():
            raise ValueError('Unfinished prior driver preparation; inspect it before retrying')
        original.write_bytes(arcore_before)
        env = os.environ.copy()
        epoch = git(titanium, 'show', '-s', '--format=%ct', 'HEAD').decode().strip()
        env.update({'VERSION': PRODUCT['chromium_version'],
                    'GIT_COMMITTER_NAME': 'Internet-browser Chromium Build',
                    'GIT_COMMITTER_EMAIL': 'internet-browser-ci@users.noreply.github.com',
                    'GIT_AUTHOR_NAME': 'Internet-browser Chromium Build',
                    'GIT_AUTHOR_EMAIL': 'internet-browser-ci@users.noreply.github.com',
                    'GIT_COMMITTER_DATE': '@' + epoch + ' +0000',
                    'GIT_AUTHOR_DATE': '@' + epoch + ' +0000'})
        subprocess.run(['bash', '-e', '-u', '-o', 'pipefail', '-c',
                        'source "$1/common.sh"\nsource "$SCRIPT_DIR/patch.sh"',
                        str(titanium / 'build.sh'), str(titanium)], cwd=source, env=env, check=True)
        # The driver writes a fixed, empty product helper asset directory.
        dist = source / 'titanium/dist'
        expected_assets = {'BUILD.gn': git(titanium, 'show', 'HEAD:extensions/BUILD.gn'),
                           'bundled.json': b'{}\n',
                           'stage_bundled_extensions.inc': git(titanium, 'show', 'HEAD:extensions/stage_bundled_extensions.inc')}
        if {path.name for path in dist.iterdir()} != set(expected_assets):
            raise ValueError('Unexpected bundled extension payload after pinned driver')
        for name, data in expected_assets.items():
            if (dist / name).read_bytes() != data:
                raise ValueError('Bundled product helper assets differ')
        commits = {}
        for relative in ['third_party/devtools-frontend/src', 'titanium', '.']:
            repository = source / relative
            if relative == 'titanium':
                git(repository, 'add', '-f', '--', *['dist/' + name for name in expected_assets], env=env)
            git(repository, 'add', '-u', '--', env=env)
            difference = git(repository, 'diff', '--cached', '--binary')
            if difference:
                subprocess.run(['git', '-C', str(repository), '-c', 'commit.gpgsign=false',
                    '-c', 'core.hooksPath=/dev/null', 'commit', '-m',
                    'Apply pinned Titanium Android source driver'], env=env, check=True)
            commits[relative] = {'head': head(repository), 'diff_sha256': hashlib.sha256(difference).hexdigest()}
        report.update({'upstream_driver_applied': True, 'root_after_driver': head(source),
                       'driver_sha256': hashlib.sha256(driver.read_bytes()).hexdigest(),
                       'subproject_inputs': inputs, 'driver_commits': commits,
                       'arcore_manifest_before_sha256': hashlib.sha256(arcore_before).hexdigest(),
                       'arcore_manifest_after_sha256': hashlib.sha256(arcore.read_bytes()).hexdigest(),
                       'compiled': False, 'release_approved': False})
        destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('Pinned Titanium driver recorded. Product overlay and native build remain.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args()
    stage(args.workspace)
