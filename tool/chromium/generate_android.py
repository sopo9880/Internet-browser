"""Validate the prepared product source and generate its real Android graph."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from prepare_titanium_patches import PRODUCT, head
from prepare_android_product import product_path
from titanium_product import PRODUCT_PACKAGE, prepare_source
from titanium_pin import SOURCE_SHA


def generate(workspace: Path, version_code: int) -> None:
    import fcntl
    workspace = workspace.resolve()
    with (workspace / '.native-android-source.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        titanium = workspace / 'titanium'
        source = titanium / 'chromium/src'
        upstream = json.loads((workspace / 'titanium-upstream.json').read_text(encoding='utf-8'))
        overlay = json.loads((source / '.internet-browser-android-overlay.json').read_text(encoding='utf-8'))
        if (head(titanium) != SOURCE_SHA or head(source) != upstream['root_after_driver'] or
                overlay['source_revision'] != head(source) or overlay['product'] != PRODUCT):
            raise ValueError('Prepared Android product source differs')
        for relative, expected in overlay['files'].items():
            if hashlib.sha256(product_path(source, relative).read_bytes()).hexdigest() != expected:
                raise ValueError('Prepared Android product file changed: ' + relative)
        args, _ = prepare_source((titanium / 'args.gn').read_text(encoding='utf-8'),
                                 (titanium / 'build.sh').read_text(encoding='utf-8'),
                                 PRODUCT_PACKAGE, version_code=version_code,
                                 version_name=PRODUCT['app_version'])
        if args.count('symbol_level = 1') != 1:
            raise ValueError('Pinned Android symbol configuration changed')
        args = args.replace('symbol_level = 1', 'symbol_level = 0')
        args += '\nuse_remoteexec = false\n'
        output = source / 'out/InternetBrowserAndroid'
        output.mkdir(parents=True, exist_ok=True)
        (output / 'args.gn').write_text(args, encoding='utf-8')
        depot = titanium / 'depot_tools'
        env = os.environ.copy()
        env.update({'DEPOT_TOOLS_UPDATE': '0', 'DEPOT_TOOLS_METRICS': '0',
                    'DEPOT_TOOLS_BUILD_TELEMETRY': '0'})
        env['PATH'] = str(depot) + os.pathsep + env.get('PATH', '')
        subprocess.run([str(depot / '.cipd_bin/vpython3'), str(depot / 'gn.py'),
                        'gen', 'out/InternetBrowserAndroid'], cwd=source, env=env, check=True)
        report = {'source_revision': head(source), 'product': PRODUCT,
                  'version_code': version_code, 'args_sha256': hashlib.sha256(args.encode()).hexdigest(),
                  'gn_generation_success': True, 'compiled': False, 'release_approved': False}
        (workspace / 'android-graph.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('Actual Android product graph generated. No browser compilation performed.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--version-code', required=True, type=int)
    args = parser.parse_args()
    generate(args.workspace, args.version_code)
