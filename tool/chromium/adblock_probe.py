"""Prepare a controlled request probe from the authentic requested AdBlock.

The server supplies test requests, not an ad-blocking implementation. No custom
DNR rules or substitute extension are installed. Runtime acceptance is separate.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import struct
from threading import Lock, Thread
import zipfile

try:
    from .download_adblock import verify, EXTENSION_ID, MAX_BYTES
except ImportError:
    from download_adblock import verify, EXTENSION_ID, MAX_BYTES

RULE_PATTERN = '/ads/!rotator/'
AD_PATH = RULE_PATTERN + 'advert.js'
CONTROL_PATH = '/control.js'
INDEX = (f'<!doctype html><meta charset="utf-8"><title>AdBlock controlled request probe</title>'
         f'<script src="{CONTROL_PATH}"></script><script src="{AD_PATH}"></script>'
         '<p>Controlled request probe for the installed AdBlock.</p>').encode()


def select_rule(archive: zipfile.ZipFile, manifest: dict) -> dict:
    for group in manifest.get('declarative_net_request', {}).get('rule_resources', []):
        if group.get('enabled') is not True: continue
        info = archive.getinfo(group['path'])
        if info.file_size > 32 * 1024 * 1024:
            raise ValueError('Oversized AdBlock ruleset')
        rules = json.loads(archive.read(info))
        if not isinstance(rules, list): raise ValueError('Expected an AdBlock ruleset list')
        for rule in rules:
            condition = rule.get('condition', {})
            if (rule.get('action', {}).get('type') != 'block' or
                condition.get('urlFilter') != RULE_PATTERN or
                set(condition) - {'urlFilter', 'resourceTypes', 'isUrlFilterCaseSensitive'} or
                'script' not in condition.get('resourceTypes', ['script'])):
                continue
            return {'ruleset_id': group['id'], 'rule_id': rule['id'],
                    'condition': condition, 'action': rule['action']}
    raise ValueError('The authentic enabled rulesets do not contain the expected unconstrained probe rule')


def prepare(package: Path, openssl: Path, destination: Path) -> dict:
    if package.stat().st_size > MAX_BYTES: raise ValueError('Oversized AdBlock package')
    data = package.read_bytes()
    verified = verify(data, openssl)
    offset = 12 + struct.unpack_from('<I', data, 8)[0]
    with zipfile.ZipFile(io.BytesIO(data[offset:])) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        rule = select_rule(archive, manifest)
    report = {'kind': 'AUTHENTIC_ADBLOCK_PROBE_PREPARATION_NOT_RUNTIME_ACCEPTANCE',
              'extension_id': EXTENSION_ID, 'package_version': verified['version'],
              'package_sha256': verified['sha256'],
              'developer_signature_verified': verified['developer_signature_verified'],
              'publisher_signature_verified': verified['publisher_signature_verified'],
              **rule, 'control_path': CONTROL_PATH, 'ad_path': AD_PATH,
              'store_installation_verified': False, 'worker_verified': False,
              'request_blocking_verified': False, 'native_popup_verified': False,
              'release_approved': False}
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'probe-preparation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


@contextmanager
def probe_server():
    counts = Counter()
    lock = Lock()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock: counts[self.path.split('?', 1)[0]] += 1
            path = self.path.split('?', 1)[0]
            content = {CONTROL_PATH: (b'window.adblockControlLoaded=true;', 'text/javascript'),
                       AD_PATH: (b'window.adblockAdRequestLoaded=true;', 'text/javascript'),
                       '/': (INDEX, 'text/html')}.get(path)
            if content is None:
                self.send_error(404); return
            body, mime = content
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    def snapshot():
        with lock: return dict(counts)
    try:
        yield f'http://127.0.0.1:{server.server_port}', snapshot
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--openssl', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.package, args.openssl, args.destination)))
