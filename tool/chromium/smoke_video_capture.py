"""Exercise native capture with owned pages/media, never a user's profile.

Embedded YouTube/Instagram data are controlled fixtures, not a claim that every
live site stream is supported. Uses the browser's real download/library/player.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import struct
import subprocess
from threading import Thread
import time
from urllib.request import urlopen
try:
    from .smoke_windows import Cdp, eventually
except ImportError:
    from smoke_windows import Cdp, eventually


@contextmanager
def server(media: Path):
    video = (media/'bear-1280x720-av_frag.mp4').read_bytes()
    webm = (media/'bear-320x240.webm').read_bytes()
    boundaries = []
    offset = 0
    while offset + 8 <= len(video):
        size, kind = struct.unpack_from('>I4s', video, offset)
        if size < 8: raise ValueError('Invalid controlled MP4 fixture')
        if kind == b'sidx': boundaries.append(offset)
        offset += size
    if len(boundaries) < 2: raise ValueError('Fixture needs fragmented MP4')
    chunks = {'/init.mp4': video[:boundaries[0]], '/one.m4s': video[boundaries[0]:boundaries[1]], '/two.m4s': video[boundaries[1]:]}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = self.path.split('?')[0]
            mime = 'text/html; charset=utf-8'
            body = b''
            if route in chunks: body, mime = chunks[route], 'video/mp4'
            elif route.endswith('.webm'): body, mime = webm, 'video/webm'
            elif route.endswith('.mp4'): body, mime = video, 'video/mp4'
            elif route == '/master.m3u8':
                body = b'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=1280x720,CODECS="avc1,mp4a"\nvod.m3u8\n'
                mime = 'application/vnd.apple.mpegurl'
            elif route == '/vod.m3u8':
                body = b'#EXTM3U\n#EXT-X-TARGETDURATION:5\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:1,\none.m4s\n#EXTINF:2,\ntwo.m4s\n#EXT-X-ENDLIST\n'
                mime = 'application/vnd.apple.mpegurl'
            elif route == '/encrypted.m3u8':
                body = b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key"\none.ts\n#EXT-X-ENDLIST\n'; mime = 'application/vnd.apple.mpegurl'
            elif route == '/generic':
                body = '<title>일반 영상 테스트</title><video controls src="/clip.webm" preload="metadata"></video>'.encode()
            elif route == '/youtube':
                data = {'streamingData': {'formats': [{'url': self.base+'/muxed.mp4', 'mimeType': 'video/mp4', 'qualityLabel': '360p'}]}}
                body = ('<title>YouTube 형식 테스트</title><script>var ytInitialPlayerResponse = '+json.dumps(data)+';</script>').encode()
            elif route == '/instagram':
                body = '<title>Instagram 형식 테스트</title><meta property="og:video" content="/reel.mp4"><meta property="og:video:type" content="video/mp4">'.encode()
            elif route == '/hls':
                body = b'<title>HLS fixture</title><video src="/master.m3u8"></video><video src="/encrypted.m3u8"></video>'
            elif route == '/private': body = b'<title>Private fixture</title><video src="/private.webm"></video>'
            else:
                self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if route.endswith('.m4s'): time.sleep(0.4)
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
        def log_message(self, *_): pass
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    Handler.base = f'http://127.0.0.1:{http.server_port}'
    thread = Thread(target=http.serve_forever, daemon=True); thread.start()
    try: yield Handler.base, video, webm
    finally: http.shutdown(); http.server_close(); thread.join(timeout=5)


def file_hash(path: Path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(8*1024*1024), b''): digest.update(block)
    return digest.hexdigest()


def run(executable: Path, media: Path, root: Path, report_file: Path | None = None):
    root.mkdir(exist_ok=False, parents=True)
    profile = root/'profile'; profile.mkdir()
    downloads = root/'downloads'; downloads.mkdir()
    (profile/'internet-browser.json').write_text('{"enabled":false,"preset":"balanced"}')
    report = {'kind': 'NATIVE_CONTROLLED_VIDEO_CAPTURE_SMOKE', 'chrome_exe_sha256': file_hash(executable),
        'chrome_dll_sha256': file_hash(executable.with_name('chrome.dll')), 'checks': {}, 'live_youtube_instagram_verified': False, 'release_approved': False}
    checks = report['checks']; cdp = None
    with (root/'browser.log').open('wb') as log:
        browser = subprocess.Popen([str(executable), '--headless=new', '--no-first-run', '--no-default-browser-check',
            '--disable-background-networking', '--disable-component-update', '--remote-debugging-address=127.0.0.1',
            '--remote-debugging-port=0', '--user-data-dir='+str(profile), 'about:blank'], stdout=log, stderr=subprocess.STDOUT)
        try:
            endpoint = profile/'DevToolsActivePort'
            port = eventually(lambda: endpoint.read_text().splitlines()[0] if endpoint.exists() else None)
            cdp = Cdp(json.load(urlopen(f'http://127.0.0.1:{port}/json/version'))['webSocketDebuggerUrl'])
            cdp.call('Browser.setDownloadBehavior', {'behavior':'allow', 'downloadPath':str(downloads)})
            def open_page(url, **extra):
                target = cdp.call('Target.createTarget', {'url': url, **extra})['targetId']
                session = cdp.call('Target.attachToTarget', {'targetId':target, 'flatten':True})['sessionId']
                cdp.call('Page.enable', session=session)
                eventually(lambda: cdp.evaluate(session, 'document.readyState === "complete"'))
                return target, session
            with server(media) as (base, video, webm):
                pages = [open_page(base+route) for route in ['/generic','/youtube','/instagram','/hls']]
                context = cdp.call('Target.createBrowserContext')['browserContextId']
                open_page(base+'/private', browserContextId=context)
                _, hub = open_page('chrome://internet-browser/')
                eventually(lambda: cdp.evaluate(hub, '!!document.querySelector("#scan-videos")'))
                def api(command, *args):
                    return cdp.evaluate(hub, '(async()=>{const {sendWithPromise}=await import("chrome://resources/js/cr.js");return await sendWithPromise("internetBrowserCapture",'+','.join(json.dumps(x) for x in (command,*args))+');})()')
                cdp.evaluate(hub, 'document.querySelector("#scan-videos").click()')
                eventually(lambda: cdp.evaluate(hub, 'document.querySelectorAll("#capture-results article").length >= 4'))
                checks['capture_screen_and_quality_options'] = cdp.evaluate(hub, '[...document.querySelectorAll("#capture-results option")].some(option=>option.textContent.includes("360p"))')
                cdp.evaluate(hub, '[...document.querySelectorAll("#capture-results article")].find(row=>row.querySelector("h3").textContent.includes("일반 영상")).querySelector("button").click()')
                eventually(lambda: any(file.read_bytes()==webm for file in downloads.glob('*.webm')))
                checks['native_capture_download_exact_bytes'] = True
                found = api('scan')
                if found.get('error'): raise RuntimeError(found['error'])
                checks['generic_video_detected'] = any(item['url'].endswith('/clip.webm') for item in found['items'])
                checks['youtube_muxed_quality_detected'] = any(item['url'].endswith('/muxed.mp4') and item['quality']=='360p' for item in found['items'])
                checks['instagram_video_detected'] = any(item['url'].endswith('/reel.mp4') for item in found['items'])
                checks['other_profile_excluded'] = not any('private.webm' in item['url'] for item in found['items'])
                generic = next(item for item in found['items'] if item['url'].endswith('/clip.webm'))
                # Restore the real download delegate before testing explicit
                # private stream paths and its ordinary safety checks.
                cdp.call('Browser.setDownloadBehavior', {'behavior':'default'})
                encrypted = next(item for item in found['items'] if item['url'].endswith('/encrypted.m3u8'))
                rejected = api('inspect', encrypted['token']); checks['encrypted_hls_rejected_with_reason'] = '암호화' in rejected.get('error','')
                master = next(item for item in found['items'] if item['url'].endswith('/master.m3u8'))
                variants = api('inspect', master['token'])
                if variants.get('error'): raise RuntimeError(variants['error'])
                selected = variants['items'][0]
                checks['hls_actual_quality_selected'] = selected['quality']=='1280x720'
                resolved = api('inspect', selected['token'])
                if resolved.get('error'): raise RuntimeError(resolved['error'])
                stream = resolved['items'][0]
                checks['hls_resolved_to_mp4_parts'] = stream['kind']=='stream'
                result = api('download', stream['token'])
                if not result.get('started'): raise RuntimeError(str(result))
                guid = result['guid']
                paused = api('control', guid, 'pause')
                checks['hls_pause'] = any(row['guid']==guid and row['paused'] for row in paused.get('items',[]))
                time.sleep(0.7)
                boundary = next(row for row in api('transfers')['items'] if row['guid']==guid)
                checks['hls_pause_at_part_boundary'] = boundary['paused'] and boundary['state']==0 and boundary['completedParts'] < boundary['totalParts']
                resumed = api('control', guid, 'resume')
                checks['hls_resume'] = 'error' not in resumed
                # Destroy and reopen the hub: the profile owns the running job.
                cdp.call('Page.navigate', {'url':'about:blank'}, session=hub)
                cdp.call('Page.navigate', {'url':'chrome://internet-browser/'}, session=hub)
                eventually(lambda: cdp.evaluate(hub, '!!document.querySelector("#scan-videos")'))
                status = eventually(lambda: next((row for row in api('transfers')['items'] if row['guid']==guid and row['state'] in (1,3)), None))
                if status['state'] != 1: raise RuntimeError(str(status))
                checks['hls_survives_hub_navigation'] = True
                completed = list(profile.glob('*/InternetBrowserVideos/*/complete.json'))
                checks['hls_exact_assembled_bytes'] = len(completed)==1 and completed[0].with_name('video.mp4').read_bytes()==video
                checks['hls_partial_files_removed'] = not list(profile.glob('*/InternetBrowserVideos/*/video.part'))
                cancellation = api('download', stream['token'])
                if not cancellation.get('started'): raise RuntimeError(str(cancellation))
                cancelled = api('control', cancellation['guid'], 'cancel')
                checks['hls_cancel'] = any(row['guid']==cancellation['guid'] and row['state']==2 for row in cancelled.get('items',[]))
                eventually(lambda: not list(profile.glob('*/InternetBrowserVideos/*/video.part')))
                checks['hls_cancel_not_in_library'] = len(list(profile.glob('*/InternetBrowserVideos/*/complete.json')))==1
                def library():
                    return cdp.evaluate(hub, '(async()=>{const {sendWithPromise}=await import("chrome://resources/js/cr.js");return await sendWithPromise("internetBrowserVideos");})()')
                catalog = eventually(library, lambda value: any(item.get('name','').startswith('stream:') for item in value.get('videos',[])))
                saved = next(item for item in catalog['videos'] if item['name'].startswith('stream:'))
                checks['hls_automatically_in_library'] = saved['title']=='HLS fixture'
                cdp.evaluate(hub, '(async()=>{const {sendWithPromise}=await import("chrome://resources/js/cr.js");return await sendWithPromise("internetBrowserOpenVideo",'+json.dumps(saved['url'])+');})()')
                checks['hls_saved_video_playable'] = eventually(lambda: cdp.evaluate(hub, '!!document.querySelector("#internet-browser-player") && document.querySelector("video").readyState >= 1'))
                _, hub = open_page('chrome://internet-browser/')
                cdp.evaluate(pages[0][1], 'history.pushState({}, "", "/generic?video=changed")')
                changed = api('download', generic['token'])
                checks['same_document_video_change_rejected'] = bool(changed.get('error'))
                # A candidate cannot be used after the original document changes.
                cdp.call('Page.navigate', {'url':'about:blank'}, session=pages[0][1])
                eventually(lambda: cdp.evaluate(pages[0][1], 'location.href === "about:blank" && document.readyState === "complete"'))
                _, hub = open_page('chrome://internet-browser/')
                stale = api('download', generic['token'])
                checks['stale_source_document_rejected'] = bool(stale.get('error'))
                report['assembled_mp4_sha256'] = hashlib.sha256(video).hexdigest()
                report['all_checks_passed'] = all(checks.values())
        except Exception as error:
            report['error'] = repr(error); report['all_checks_passed'] = False
        finally:
            if cdp:
                report['diagnostics'] = cdp.diagnostics
                try: cdp.call('Browser.close')
                except Exception: pass
                cdp.close()
            try: browser.wait(timeout=20)
            except subprocess.TimeoutExpired: browser.terminate(); browser.wait(timeout=10)
            (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            if report_file:
                report_file.parent.mkdir(exist_ok=True,parents=True)
                report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--exe',type=Path,required=True); parser.add_argument('--media',type=Path,required=True); parser.add_argument('--work',type=Path,required=True); parser.add_argument('--report',type=Path)
    args=parser.parse_args(); result=run(args.exe.resolve(),args.media.resolve(),args.work.resolve(),args.report)
    print(json.dumps(result,ensure_ascii=True,indent=2))
    raise SystemExit(0 if result['all_checks_passed'] else 1)
