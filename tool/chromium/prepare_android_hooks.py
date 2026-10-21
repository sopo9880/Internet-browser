"""Exclude the unrelated, unpinned Titanium helper CRX from product builds."""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import pprint
import subprocess

try:
    from .titanium_pin import SOURCE_SHA
except ImportError:
    from titanium_pin import SOURCE_SHA

HOOK_NAME = 'fetch_titanium_extension'
HOOK_ACTION = ['python3', '../extensions/bundle.py', '../extensions/dist',
               'titanium', 'https://github.com/jqssun/android-titanium-extension/releases/latest/download/titanium.crx']


def configuration(text: str) -> dict:
    result = {}
    for node in ast.parse(text).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise ValueError('Unexpected executable code in pinned gclient configuration')
        name = node.targets[0].id
        if name not in ('solutions', 'hooks', 'target_os') or name in result:
            raise ValueError('Unexpected gclient configuration assignment')
        result[name] = ast.literal_eval(node.value)
    hooks = result.get('hooks', [])
    candidates = [hook for hook in hooks if hook.get('name') == HOOK_NAME]
    if len(candidates) != 1 or candidates[0].get('action') != HOOK_ACTION:
        raise ValueError('Pinned Titanium helper-download hook changed')
    result['hooks'] = [hook for hook in hooks if hook.get('name') != HOOK_NAME]
    return result


def prepare(source: Path) -> None:
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != SOURCE_SHA:
        raise ValueError('Unpinned Titanium source')
    upstream = source / '.gclient'
    upstream_bytes = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:.gclient'])
    if upstream.read_bytes() != upstream_bytes:
        raise ValueError('Pinned upstream hook configuration contains edits')
    config = configuration(upstream_bytes.decode('utf-8'))
    destination = source / 'chromium/.gclient'
    if not destination.parent.is_dir():
        raise ValueError('Chromium source workspace has not been prepared')
    distribution = source / 'extensions/dist'
    template = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:extensions/BUILD.gn'])
    expected = {'BUILD.gn': template, 'bundled.json': b'{}\n'}
    if distribution.exists():
        for path in distribution.iterdir():
            if path.name not in expected or not path.is_file() or path.read_bytes() != expected[path.name]:
                raise ValueError('Unexpected existing product helper payload; refusing CRX files')
    distribution.mkdir(parents=True, exist_ok=True)
    (distribution / 'BUILD.gn').write_bytes(template)
    (distribution / 'bundled.json').write_text('{}\n', encoding='utf-8')
    configured = ''.join(
        name + ' = ' + pprint.pformat(value, sort_dicts=False) + '\n'
        for name, value in config.items())
    if destination.exists() and destination.read_text(encoding='utf-8') not in (upstream_bytes.decode('utf-8'), configured):
        raise ValueError('Existing Chromium hook configuration contains unknown edits')
    destination.write_text(configured, encoding='utf-8')
    print('Product hooks prepared: no automatic Titanium helper installation. AdBlock remains a user-controlled store installation.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source.resolve())
