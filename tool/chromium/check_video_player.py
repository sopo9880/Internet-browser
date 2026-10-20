"""Exercise player controls in a real Chromium engine using a temporary profile.

This checks the renderer script, not the native observer or final product codec
support. Native acceptance must also run against the built Internet Browser.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.request import urlopen

try:
    from .smoke_windows import Cdp, eventually
except ImportError:
    from smoke_windows import Cdp, eventually

SCRIPT = Path(__file__).resolve().parents[2] / 'native/chromium/windows/resources/video_player.js'


def run(browser_exe: Path, video: Path, work: Path, report: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    result = {'kind': 'LOCAL_PLAYER_SCRIPT_REAL_ENGINE_CHECK', 'checks': {},
              'native_observer_verified': False, 'pip_verified': False,
              'release_approved': False}
    checks = result['checks']
    try:
        with TemporaryDirectory(prefix='local-player-', dir=work) as temporary:
            directory = Path(temporary)
            media = directory / ('fixture' + video.suffix)
            shutil.copyfile(video, media)
            profile = directory / 'profile'
            with open(os.devnull, 'wb') as output:
                process = subprocess.Popen([str(browser_exe), '--headless=new', '--disable-gpu',
                    '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
                    '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
                    f'--user-data-dir={profile}', 'about:blank'], stdout=output, stderr=output)
                cdp = None
                try:
                    active = profile / 'DevToolsActivePort'
                    port = eventually(lambda: active.read_text().splitlines()[0] if active.exists() else None)
                    info = json.load(urlopen(f'http://127.0.0.1:{port}/json/version', timeout=10))
                    result['engine'] = info.get('Browser')
                    cdp = Cdp(info['webSocketDebuggerUrl'])
                    page = next(x for x in cdp.call('Target.getTargets')['targetInfos'] if x['type'] == 'page')
                    session = cdp.call('Target.attachToTarget', {'targetId': page['targetId'], 'flatten': True})['sessionId']
                    cdp.call('Page.enable', session=session)
                    cdp.call('Page.navigate', {'url': media.as_uri()}, session=session)
                    eventually(lambda: cdp.evaluate(session, "document.querySelector('video')?.readyState >= 1"))
                    frame = cdp.call('Page.getFrameTree', session=session)['frameTree']['frame']['id']
                    context = cdp.call('Page.createIsolatedWorld', {'frameId': frame,
                        'worldName': 'internet-browser-player-test'}, session=session)['executionContextId']
                    def evaluate(expression):
                        response = cdp.call('Runtime.evaluate', {'expression': expression,
                            'contextId': context, 'awaitPromise': True, 'returnByValue': True,
                            'userGesture': True}, session=session)
                        if 'exceptionDetails' in response:
                            raise RuntimeError(str(response['exceptionDetails']))
                        return response['result'].get('value')
                    title = '<img src=x onerror=alert(1)> saved title'
                    options = {'title': title, 'lastPositionMs': 1000, 'hasPrevious': False, 'hasNext': True}
                    evaluate('globalThis.__ibMessages = []; console.info = message => __ibMessages.push(message);')
                    evaluate('(() => {const options = ' + json.dumps(options) + ';\n' + SCRIPT.read_text(encoding='utf-8') + '\n})()')
                    checks['title_is_literal'] = evaluate('document.querySelector(".ib-title").textContent') == title
                    checks['resume_position'] = evaluate('Math.abs(document.querySelector("video").currentTime - 1) < 0.2')
                    checks['playlist_bounds'] = evaluate("[...document.querySelectorAll('button')].find(x => x.textContent === '이전').disabled && ![...document.querySelectorAll('button')].find(x => x.textContent === '다음').disabled")
                    evaluate("document.querySelector('video').pause(); document.querySelector('select').value = '1.5'; document.querySelector('select').dispatchEvent(new Event('change'))")
                    checks['playback_rate'] = evaluate('document.querySelector("video").playbackRate === 1.5')
                    evaluate("window.dispatchEvent(new KeyboardEvent('keydown', {key:'5'}))")
                    checks['keyboard_seek_percent'] = evaluate('Math.abs(document.querySelector("video").currentTime - document.querySelector("video").duration / 2) < 0.1')
                    evaluate("[...document.querySelectorAll('button')].find(x => x.textContent === '잠금').click(); window.dispatchEvent(new KeyboardEvent('keydown', {key:'0'}))")
                    checks['lock_blocks_shortcuts'] = evaluate('Math.abs(document.querySelector("video").currentTime - document.querySelector("video").duration / 2) < 0.1')
                    evaluate("[...document.querySelectorAll('button')].find(x => x.textContent === '잠금 해제').click(); [...document.querySelectorAll('button')].find(x => x.textContent === '반복 꺼짐').click(); [...document.querySelectorAll('button')].find(x => x.textContent === '화면 맞춤').click()")
                    checks['loop_and_fit'] = evaluate('document.querySelector("video").loop && document.querySelector("video").style.objectFit === "cover"')
                    evaluate("document.querySelector('video').play()")
                    checks['actual_video_playing'] = eventually(lambda: evaluate('!document.querySelector("video").paused && document.querySelector("video").readyState >= 2'))
                    evaluate("document.querySelector('video').pause(); [...document.querySelectorAll('button')].find(x => x.textContent === '다음').click()")
                    messages = evaluate('__ibMessages.map(x => JSON.parse(x.slice("INTERNET_BROWSER_LOCAL_PLAYER:".length)))')
                    checks['position_reported'] = any(x['action'] == 'position' and x['positionMs'] >= 0 and x['durationMs'] > 0 for x in messages)
                    checks['playlist_preserves_choices'] = any(x['action'] == 'next' and x['rate'] == 1.5 and x['fit'] == 'cover' and x['loop'] for x in messages)
                    result['layout'] = evaluate("['#internet-browser-player','#internet-browser-player video','.ib-controls'].map(selector => {const element=document.querySelector(selector), style=getComputedStyle(element), rect=element.getBoundingClientRect(); return {selector,position:style.position,display:style.display,top:rect.top,height:rect.height,width:rect.width,overflow:style.overflow,flex:style.flex};})")
                    screenshot = cdp.call('Page.captureScreenshot', {'format': 'png'}, session=session)
                    (work / 'video-player-render.png').write_bytes(base64.b64decode(screenshot['data']))
                    checks['controls_not_covered'] = evaluate("(() => {const video=document.querySelector('video').getBoundingClientRect(), controls=document.querySelector('.ib-controls').getBoundingClientRect();return video.bottom <= controls.top + 1 && controls.bottom <= innerHeight + 1 && video.height > 0;})()")
                    if not all(checks.values()):
                        raise RuntimeError('One or more player behavior checks failed')
                finally:
                    if cdp:
                        try: cdp.call('Browser.close')
                        except Exception: pass
                        cdp.close()
                    try: process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=10)
    except Exception as error:
        result['error'] = str(error)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.browser.resolve(), args.video.resolve(), args.work.resolve(), args.report.resolve())
    print(json.dumps(result, ensure_ascii=True))
    raise SystemExit(1 if 'error' in result else 0)
