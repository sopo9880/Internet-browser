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
import shutil
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
        self.diagnostics = []

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
            try:
                response = json.loads(self.socket.recv(timeout=20))
            except TimeoutError as error:
                raise TimeoutError(f'{method}: browser reply timed out after 20 seconds') from error
            if response.get('id') != identifier:
                if response.get('method') in ('Runtime.exceptionThrown', 'Log.entryAdded') and len(self.diagnostics) < 30:
                    self.diagnostics.append(response)
                continue
            if 'error' in response:
                raise RuntimeError(f'{method}: {response["error"]}')
            return response.get('result', {})

    def evaluate(self, session: str, expression: str, *, user_gesture: bool = False):
        response = self.call('Runtime.evaluate', {
            'expression': expression, 'awaitPromise': True, 'returnByValue': True, 'userGesture': user_gesture,
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
def controlled_server(media: bytes | None = None):
    requests = Counter()
    lock = Lock()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock:
                requests[self.path] += 1
            if self.path == '/download.webm' and media is not None:
                body = media
                mime = 'video/webm'
            elif self.path == '/control.js':
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
            if self.path == '/download.webm':
                self.send_header('Content-Disposition', 'attachment; filename=downloaded.webm')
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


def run(executable: Path, report_file: Path, work: Path, media_fixture: Path | None = None) -> dict:
    executable = executable.resolve(strict=True)
    work = work.resolve()
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
    temporary = None
    try:
        with TemporaryDirectory(prefix='native-windows-smoke-', dir=work,
                                ignore_cleanup_errors=True) as temporary:
            profile = Path(temporary) / 'profile'
            profile.mkdir()
            # Keep this fixture independent of the user's previous DPI choice.
            (profile / 'internet-browser.json').write_text(
                json.dumps({'enabled': False, 'preset': 'balanced'}) + '\n', encoding='utf-8')
            library = Path(temporary) / 'Videos'
            legacy = Path(temporary) / 'legacy'
            library.mkdir(); legacy.mkdir()
            extension_fixture = Path(temporary) / 'fixture-extension'
            shutil.copytree(FIXTURE, extension_fixture, ignore=shutil.ignore_patterns('_metadata'))
            fixture = media_fixture or executable.parents[2] / 'media/test/data/bear-320x240.webm'
            shutil.copyfile(fixture, library / 'sample.webm')
            subtitle = library / 'saved-captions.srt'
            original_subtitle = '1\r\n00:00:00,000 --> 00:00:10,000\r\n저장된 외부 자막\r\n'.encode('utf-16')
            subtitle.write_bytes(original_subtitle)
            (library / 'sample.srt').write_text('1\n00:00:00,000 --> 00:00:10,000\nFallback subtitle\n', encoding='utf-8')
            old_library = json.dumps({'version': 1, 'items': {'sample.webm': {
                'subtitlePath': str(subtitle),
                'title': 'Saved fixture', 'lastPositionMs': 1000}}}).encode()
            old_preferences = json.dumps({'flutter.bookmarks': ['https://example.test/bookmark'],
                'flutter.history': ['https://example.test/visit'], 'flutter.update_auto_check': False}).encode()
            (library / 'library.json').write_bytes(old_library)
            (legacy / 'shared_preferences.json').write_bytes(old_preferences)
            def saved_video():
                files = list(profile.glob('*/internet-browser-video-state.json'))
                return json.loads(files[0].read_text()).get('sample.webm', {}) if files else {}
            with (work / f'native-browser-{time.time_ns()}.log').open('wb') as log:
                browser = subprocess.Popen([
                    str(executable), '--headless=new', '--disable-gpu',
                    '--enable-logging=stderr', '--vmodule=video_player=1',
                    '--no-first-run', '--no-default-browser-check',
                    '--test-type=browser', f'--internet-browser-test-library={library}',
                    f'--internet-browser-test-legacy-directory={legacy}',
                    '--disable-background-networking', '--disable-component-update', '--remote-debugging-port=0',
                    '--remote-debugging-address=127.0.0.1',
                    f'--user-data-dir={profile}', f'--load-extension={extension_fixture}',
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
                    report['initial_target_types'] = [
                        {'type': item['type'], 'subtype': item.get('subtype'),
                         'blank': item.get('url') == 'about:blank'} for item in targets]
                    page = next(item for item in targets
                                if item['type'] == 'page' and item.get('url') == 'about:blank'
                                and not item.get('subtype'))
                    page_session = cdp.call('Target.attachToTarget', {
                        'targetId': page['targetId'], 'flatten': True})['sessionId']
                    cdp.call('Page.enable', session=page_session)
                    cdp.call('Runtime.enable', session=page_session)
                    cdp.call('Log.enable', session=page_session)
                    cdp.call('Page.navigate', {'url': 'chrome://internet-browser/'}, session=page_session)
                    eventually(lambda: cdp.evaluate(page_session,
                        "document.querySelector('#transport-status')?.textContent"),
                        lambda value: bool(value) and '확인 중' not in value)
                    checks['native_product_webui'] = cdp.evaluate(page_session,
                        "document.title === 'Internet Browser 설정' && !!document.querySelector('#dpi-form')")
                    eventually(lambda: cdp.evaluate(page_session, "document.querySelector('#videos button')?.textContent === 'Saved fixture'"))
                    cdp.evaluate(page_session, "document.querySelector('#tab-library').click();document.querySelector('.rename-video').click()")
                    cdp.evaluate(page_session, "document.querySelector('dialog input').value='Renamed fixture';document.querySelector('dialog button[value=accept]').click()")
                    eventually(lambda: cdp.evaluate(page_session, "document.querySelector('#videos button')?.textContent === 'Renamed fixture'"))
                    checks['native_video_title_saved'] = eventually(lambda: saved_video().get('title')) == 'Renamed fixture'
                    checks['title_edit_preserves_legacy_position_fallback'] = 'lastPositionMs' not in saved_video()
                    def import_bookmarks():
                        cdp.evaluate(page_session, "document.querySelector('#import-status').textContent = ''; document.querySelector('#import-bookmarks').click()")
                        status = eventually(lambda: cdp.evaluate(page_session,
                            "!document.querySelector('#import-bookmarks').disabled && document.querySelector('#import-status').textContent"))
                        report.setdefault('bookmark_import_results', []).append(status)
                        return status
                    imported = import_bookmarks()
                    if '1개의 북마크를 가져왔습니다' not in imported:
                        raise RuntimeError('Native bookmark import failed: ' + imported)
                    checks['native_legacy_bookmark_import'] = bool(imported)
                    checks['native_legacy_bookmark_dedup'] = '0개의 북마크를 가져왔습니다' in import_bookmarks()
                    cdp.call('Page.navigate', {'url': 'chrome://internet-browser/licenses.html'},
                             session=page_session)
                    notice_manifest = json.loads((Path(__file__).resolve().parents[2] / 'third_party/native-notices/manifest.json').read_text(encoding='utf-8'))
                    notice_count = sum('windows' in entry['platforms'] for entry in notice_manifest)
                    notices = eventually(lambda: cdp.evaluate(page_session,
                        "document.querySelector('h1')?.textContent === '오픈소스 안내' && document.querySelectorAll('section').length === " + str(notice_count)))
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
                    downloaded = Path(temporary) / 'BrowserDownloads'
                    downloaded.mkdir()
                    cdp.call('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(downloaded)})
                    with controlled_server(fixture.read_bytes()) as (url, received):
                        cdp.call('Page.navigate', {'url': url}, session=page_session)
                        eventually(lambda: cdp.evaluate(page_session, 'window.controlLoaded === true'))
                        checks['controlled_navigation'] = received['/control.js'] > 0
                        time.sleep(1)
                        checks['fixture_dnr_request_blocked'] = (
                            received['/tracker.js'] == 0 and cdp.evaluate(
                                page_session, 'window.trackerLoaded === undefined'))
                        cdp.call('Page.navigate', {'url': url + '/download.webm'}, session=page_session)
                        checks['native_browser_video_download'] = eventually(lambda:
                            (downloaded / 'downloaded.webm').is_file() and
                            (downloaded / 'downloaded.webm').read_bytes() == fixture.read_bytes())
                    cdp.call('Page.navigate', {
                        'url': f'chrome-extension://{extension_id}/popup.html'}, session=page_session)
                    checks['fixture_popup_document'] = eventually(lambda: cdp.evaluate(
                        page_session, "document.querySelector('#smoke-popup')?.textContent")) == 'Native extension popup document'
                    report['stage'] = 'reopen_library_after_extension'
                    cdp.call('Page.navigate', {'url': 'chrome://internet-browser/'}, session=page_session)
                    eventually(lambda: cdp.evaluate(page_session, 'document.querySelector(\'#videos .play-video[data-video-url$="/sample.webm"]\')?.textContent === "Renamed fixture"'))
                    cdp.evaluate(page_session, 'document.querySelector(\'#videos .play-video[data-video-url$="/sample.webm"]\').click()')
                    report['stage'] = 'open_saved_video_player'
                    eventually(lambda: cdp.evaluate(page_session, "!!document.querySelector('#internet-browser-player')"))
                    report['stage'] = 'load_saved_subtitle'
                    checks['native_saved_external_subtitle_loaded'] = eventually(lambda: cdp.evaluate(page_session,
                        'document.querySelector("video").textTracks[0]?.cues?.[0]?.getCueAsHTML().textContent')) == '저장된 외부 자막'
                    cdp.evaluate(page_session, "document.querySelector('video').pause()")
                    checks['native_player_resume_from_legacy'] = eventually(lambda: cdp.evaluate(page_session,
                        "document.querySelector('video').readyState >= 1 && Math.abs(document.querySelector('video').currentTime - 1) < 0.4"))
                    cdp.evaluate(page_session, "(async()=>{const video=document.querySelector('video');video.currentTime=1.4;await video.play();await new Promise(resolve=>setTimeout(resolve,200));video.pause();})()", user_gesture=True)
                    position = eventually(lambda: saved_video().get('lastPositionMs'), lambda value: value is not None and 1250 < value < 2300)
                    checks['native_player_position_saved'] = bool(position)
                    checks['native_playback_preserves_edited_title'] = saved_video().get('title') == 'Renamed fixture'
                    cdp.call('Page.navigate', {'url': 'chrome://internet-browser/'}, session=page_session)
                    eventually(lambda: cdp.evaluate(page_session, 'document.querySelector(\'#videos .play-video[data-video-url$="/sample.webm"]\')?.textContent === "Renamed fixture"'))
                    cdp.evaluate(page_session, 'document.querySelector(\'#videos .play-video[data-video-url$="/sample.webm"]\').click()')
                    eventually(lambda: cdp.evaluate(page_session, "!!document.querySelector('#internet-browser-player')"))
                    cdp.evaluate(page_session, "document.querySelector('video').pause()")
                    checks['native_player_reopen_resume'] = eventually(lambda: cdp.evaluate(page_session,
                        f"document.querySelector('video').readyState >= 1 && Math.abs(document.querySelector('video').currentTime - {position / 1000}) < 0.5"))
                    cdp.call('Page.navigate', {'url': 'chrome://internet-browser/'}, session=page_session)
                    checks['native_completed_download_in_library'] = eventually(lambda: cdp.evaluate(page_session, 'document.querySelector(\'#refresh-videos\')?.click(); !!document.querySelector(\'#videos .play-video[data-video-url$="/downloaded.webm"]\')'))
                    cdp.evaluate(page_session, 'document.querySelector(\'#videos .play-video[data-video-url$="/downloaded.webm"]\').click()')
                    checks['native_downloaded_video_player'] = eventually(lambda: cdp.evaluate(page_session, "!!document.querySelector('#internet-browser-player') && document.querySelector('video').readyState >= 1"))
                    checks['original_library_unchanged'] = (library / 'library.json').read_bytes() == old_library
                    checks['original_subtitle_unchanged'] = subtitle.read_bytes() == original_subtitle
                    checks['original_preferences_unchanged'] = (legacy / 'shared_preferences.json').read_bytes() == old_preferences
                    if not all(checks.values()):
                        raise RuntimeError('One or more controlled native smoke checks failed')
                finally:
                    if cdp:
                        try:
                            report['final_page'] = cdp.evaluate(page_session,
                                "({url:location.href,text:document.body?.innerText?.slice(0,1500),video:document.querySelector('video')?{readyState:document.querySelector('video').readyState,error:document.querySelector('video').error?.message}:null})")
                        except Exception:
                            pass
                        report['browser_diagnostics'] = cdp.diagnostics
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
        report['error_type'] = type(error).__name__
    finally:
        report['temporary_test_directory_retained'] = bool(temporary and Path(temporary).exists())
        report_file.parent.mkdir(exist_ok=True, parents=True)
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--media-fixture', type=Path)
    args = parser.parse_args()
    result = run(args.exe, args.report, args.work, args.media_fixture)
    print(json.dumps(result, ensure_ascii=True))
    raise SystemExit(1 if 'error' in result else 0)
