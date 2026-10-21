"""Apply the pinned upstream Android patch selection without deleting sources."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import subprocess

try:
    from .titanium_pin import SOURCE_SHA, VANADIUM_SHA
except ImportError:
    from titanium_pin import SOURCE_SHA, VANADIUM_SHA

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = json.loads((ROOT / 'native/chromium/product.json').read_text(encoding='utf-8'))
# The exact exclusions used by pinned Titanium build.sh, without mutating its
# upstream patch directory. The remaining Vanadium authorship stays intact.
EXCLUDED = (
    '*trichrome-apk-build-targets.patch', '*trichrome-browser-apk-targets.patch',
    '*detailed-language*.patch', '*supported-language*.patch',
    '*javascript-optimizer-site-setting.patch', '*javascript-optimizer-settings-UI.patch',
    '*component-updates.patch', '*pdf*.patch', '*PDF*.patch',
    '*for-content-public*.patch', '*toolbar-button*.patch',
    '*configs-from-config-app*.patch', '*config-app-parsing*.patch',
    '*new-tab-card*.patch', '*predictive-back*.patch',
)


def selected(name: str) -> bool:
    return name.endswith('.patch') and not any(fnmatch.fnmatchcase(name, pattern) for pattern in EXCLUDED)


def branded_patch(data: bytes) -> bytes:
    # Upstream's global replacement also renames attribution. Keep original
    # copyright and licence lines while adapting functional identifiers.
    return b''.join(line if any(word in line.lower() for word in
                    (b'copyright', b'license', b'licence')) else
                    line.replace(b'VANADIUM', b'TITANIUM').replace(b'Vanadium', b'Titanium').replace(b'vanadium', b'titanium')
                    for line in data.splitlines(keepends=True))


def head(path: Path) -> str:
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


def prepare(workspace: Path) -> dict:
    import fcntl
    workspace = workspace.resolve()
    with (workspace / '.native-android-source.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        titanium = workspace / 'titanium'
        source = titanium / 'chromium/src'
        if head(titanium) != SOURCE_SHA or head(titanium / 'vanadium') != VANADIUM_SHA:
            raise ValueError('Titanium or Vanadium source pin differs')
        if head(source) != PRODUCT['chromium_revision']:
            raise ValueError('Patch application requires the exact pristine Chromium base')
        status = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '-uno'], text=True)
        if status.strip():
            raise ValueError('Chromium base contains edits; refusing to reset it')
        stamp = workspace / 'titanium-patches.json'
        patch_dir = workspace / 'reviewed-vanadium-patches'
        if stamp.exists() or patch_dir.exists():
            raise ValueError('Patch preparation already exists; inspect its previous result before retrying')
        originals = sorted(path for path in (titanium / 'vanadium/patches').glob('*.patch') if selected(path.name))
        if not originals:
            raise ValueError('No pinned Vanadium patches found')
        patch_dir.mkdir()
        hashes = {}
        for original in originals:
            data = branded_patch(original.read_bytes())
            (patch_dir / original.name).write_bytes(data)
            hashes[original.name] = hashlib.sha256(data).hexdigest()
        env = os.environ.copy()
        epoch = subprocess.check_output(['git', '-C', str(titanium), 'show', '-s', '--format=%ct', 'HEAD'], text=True).strip()
        env.update({'GIT_COMMITTER_NAME': 'Internet-browser Chromium Build',
                    'GIT_COMMITTER_EMAIL': 'internet-browser-ci@users.noreply.github.com',
                    'GIT_COMMITTER_DATE': '@' + epoch + ' +0000'})
        subprocess.run(['git', '-C', str(source), '-c', 'commit.gpgsign=false',
                        '-c', 'core.hooksPath=/dev/null', 'am', '--whitespace=nowarn',
                        '--keep-non-patch', *[str(patch_dir / path.name) for path in originals]],
                       env=env, check=True)
        report = {'chromium_base': PRODUCT['chromium_revision'], 'patched_head': head(source),
                  'titanium_revision': SOURCE_SHA, 'vanadium_revision': VANADIUM_SHA,
                  'patches': hashes, 'compiled': False, 'release_approved': False}
        stamp.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(f'Applied {len(hashes)} pinned Android patches. No dependencies or build scripts executed.')
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.workspace)
