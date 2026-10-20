#!/usr/bin/env python3
"""Exercise the real native Chromium executable in an isolated test profile.

The bundled fixture is NOT AdBlock. Its worker/DNR/popup-document checks do
not certify Chrome Web Store installation or a native toolbar popup. Those
checks remain separately required and explicitly false in this report.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from threading import Lock, Thread
import time
from urllib.request import urlopen

from websockets.sync.client import connect

FIXTURE = Path(__file__).with_name('windows_smoke_extension')


class Cdp:
    def __init__(self, url: str):
        # No Origin header and no public debugging interface are enabled.
        self.socket = connect(url, open_timeout=10, close_timeout=2,
                              max_size=8 * 1024 * 1024)
        self.identifier = 0

    def close(self):
        self.socket.close()

    def call(self, method: str, params: dict | None = None,
             *, session: str | None = None) -> dict:
        self.identifier += 1
        identifier = self.identifier
        message = {'id': identifier, 'method': method, 'params': params or {}}
        if session:
            message['sessionId'] = session
        self.socket.send(json.dumps(message))
        while True:
            response = json.loads(self.socket.recv(timeout=20))
            if response.get('id') != identifier:
                continue
            if 'error' in response:
                raise RuntimeError(f'{method}: {response["error"]}')
            return response.get('result', {})

    def evaluate(self, session: str, expression: str):
        response = self.call('Runtime.evaluate', {
            'expression': expression, 'awaitPromise': True, 'returnByValue': True,
        }, session=session)
        if 'exceptionDetails' in response:
            raise RuntimeError(str(response['exceptionDetails']))
        return response['result'].get('value')


def eventually(action, predicate=bool, timeout: float = 30):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = action()
            if predicate(result):
                return result
        except (OSError, RuntimeError, KeyError) as error:
            last_error = error
        time.sleep(0.2)
    raise RuntimeError(f'Native runtime condition timed out: {last_error}')


@contextmanager
def controlled_server():
    requests = Counter()
    lock = Lock()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock:
                requests[self.path] += 1
            if self.path == '/control.js':
                body = b'window.controlLoaded = true;'
                mime = 'text/javascript'
            elif self.path == '/tracker.js':
                body = b'window.trackerLoaded = true;'
                mime = 'text/javascript'
            else:
                body = (b'<!doctype html><title>Controlled native smoke</title>'
                        b'<script src="/control.js"></script>'
                        b'<script src="/tracker.js"></script><p>Native smoke</p>')
                mime = 'text/html'
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run(executable: Path, report_file: Path, work: Path) -> dict:
    executable = executable.resolve(strict=True)
    work.mkdir(exist_ok=True, parents=True)
    report = {
        'kind': 'NATIVE_WINDOWS_CONTROLLED_FIXTURE_SMOKE',
        'chrome_exe_sha256': sha256(executable.read_bytes()).hexdigest(),
        'checks': {},
        'real_adblock_id_verified': False,
        'web_store_install_verified': False,
        'native_toolbar_popup_verified': False,
        'release_approved': False,
    }
    checks = report['checks']
    cdp = None
    browser = None
    try:
        with TemporaryDirectory(prefix='native-windows-smoke-', dir=work) as temporary:
            profile = Path(temporary) / 'profile'
            profile.mkdir()
            # Keep this fixture independent of the user's previous DPI choice.
            (profile / 'internet-browser.json').write_text(
                json.dumps({'enabled': False, 'preset': 'balanced'}) + '\n', encoding='utf-8')
            with (Path(temporary) / 'browser.log').open('wb') as log:
                browser = subprocess.Popen([
                    str(executable), '--headless=new', '--disable-gpu',
                    '--no-first-run', '--no-default-browser-check',
                    '--disable-background-networking', '--remote-debugging-port=0',
                    '--remote-debugging-address=127.0.0.1',
                    f'--user-data-dir={profile}', f'--load-extension={FIXTURE.resolve()}',
                    'about:blank',
                ], stdout=log, stderr=subprocess.STDOUT)
                try:
                    active_port = profile / 'DevToolsActivePort'
                    port = eventually(lambda: active_port.read_text().splitlines()[0]
                                      if active_port.exists() else None)
                    info = json.load(urlopen(f'http://127.0.0.1:{port}/json/version', timeout=10))
                    cdp = Cdp(info['webSocketDebuggerUrl'])
                    checks['native_browser_started'] = True
                    targets = cdp.call('Target.getTargets')['targetInfos']
                    page = next(item for item in targets if item['type'] == 'page')
                    page_session = cdp.call('Target.attachToTarget', {
                        'targetId': page['targetId'], 'flatten': True})['sessionId']
                    cdp.call('Page.enable', session=page_session)
                    cdp.call('Page.navigate', {'url': 'chrome://internet-browser/'}, session=page_session)
                    eventually(lambda: cdp.evaluate(page_session,
                        "document.querySelector('#transport-status')?.textContent"),
                        lambda value: bool(value) and '확인 중' not in value)
                    checks['native_product_webui'] = cdp.evaluate(page_session,
                        "document.title === 'Internet Browser' && !!document.querySelector('#dpi-form')")
                    cdp.call('Page.navigate', {'url': 'chrome://internet-browser/licenses.html'},
                             session=page_session)
                    notices = eventually(lambda: cdp.evaluate(page_session,
                        "document.querySelector('h1')?.textContent === '오픈소스 안내' && document.querySelectorAll('section').length === 2"))
                    checks['native_upstream_notices'] = bool(notices) and cdp.evaluate(
                        page_session, "document.body.textContent.includes('ByeDPI') && document.body.textContent.includes('Chromium')")
                    worker = eventually(lambda: next((item for item in
                        cdp.call('Target.getTargets')['targetInfos']
                        if item['type'] == 'service_worker' and
                        item['url'].endswith('/internet_browser_smoke_worker.js')), None))
                    extension_id = worker['url'].split('/')[2]
                    worker_session = cdp.call('Target.attachToTarget', {
                        'targetId': worker['targetId'], 'flatten': True})['sessionId']
                    checks['fixture_mv3_worker_executed'] = cdp.evaluate(
                        worker_session, 'chrome.runtime.id') == extension_id
                    with controlled_server() as (url, received):
                        cdp.call('Page.navigate', {'url': url}, session=page_session)
                        eventually(lambda: cdp.evaluate(page_session, 'window.controlLoaded === true'))
                        checks['controlled_navigation'] = received['/control.js'] > 0
                        time.sleep(1)
                        checks['fixture_dnr_request_blocked'] = (
                            received['/tracker.js'] == 0 and cdp.evaluate(
                                page_session, 'window.trackerLoaded === undefined'))
                    cdp.call('Page.navigate', {
                        'url': f'chrome-extension://{extension_id}/popup.html'}, session=page_session)
                    checks['fixture_popup_document'] = eventually(lambda: cdp.evaluate(
                        page_session, "document.querySelector('#smoke-popup')?.textContent")) == 'Native extension popup document'
                    if not all(checks.values()):
                        raise RuntimeError('One or more controlled native smoke checks failed')
                finally:
                    if cdp:
                        try:
                            cdp.call('Browser.close')
                        except Exception:
                            pass
                        cdp.close()
                        cdp = None
                    try:
                        browser.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        browser.kill()
                        browser.wait(timeout=10)
    except Exception as error:
        report['error'] = str(error)
    finally:
        report_file.parent.mkdir(exist_ok=True, parents=True)
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    result = run(args.exe, args.report, args.work)
    print(json.dumps(result, ensure_ascii=True))
    raise SystemExit(1 if 'error' in result else 0)
