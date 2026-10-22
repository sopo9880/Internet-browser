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
    dash_video = (media/'bear-640x360-v_frag.mp4').read_bytes()
    dash_audio = (media/'bear-640x360-a_frag.mp4').read_bytes()
    transport = (media/'bear-1280x720-hls.ts').read_bytes()
    def split_track(data):
        offset = 0
        while offset + 8 <= len(data):
            size, kind = struct.unpack_from('>I4s', data, offset)
            if kind == b'sidx': return data[:offset], data[offset:]
            if size < 8: break
            offset += size
        raise ValueError('Controlled DASH track needs MP4 fragments')
    vi, vp = split_track(dash_video); ai, ap = split_track(dash_audio)
    chunks.update({'/dash-v-init.mp4':vi, '/dash-v-000.m4s':vp, '/dash-v-001.m4s':vp,
        '/dash-a-init.mp4':ai, '/dash-a-001.m4s':ap, '/dash-video.mp4':dash_video, '/dash-audio.mp4':dash_audio})
    dash = '''<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT2.8S"><Period>
    <AdaptationSet contentType="video" mimeType="video/mp4">
      <Representation id="v" height="360" bandwidth="450000"><SegmentList><Initialization sourceURL="dash-v-init.mp4"/><SegmentURL media="dash-v-000.m4s"/></SegmentList></Representation>
      <Representation id="v2" height="360" bandwidth="460000"><SegmentTemplate initialization="dash-v-init.mp4" media="dash-v-$Time%03d$.m4s" timescale="10"><SegmentTimeline><S t="0" d="30" r="0"/></SegmentTimeline></SegmentTemplate></Representation>
    </AdaptationSet><AdaptationSet contentType="audio" mimeType="audio/mp4" lang="ko"><Representation id="a" bandwidth="128000"><BaseURL>dash-audio.mp4</BaseURL></Representation></AdaptationSet>
    </Period></MPD>'''
    template = '''<MPD type="static" mediaPresentationDuration="PT2.8S"><Period>
    <AdaptationSet mimeType="video/mp4"><SegmentTemplate initialization="dash-v-init.mp4" duration="3" startNumber="1"/><Representation id="v" height="360"><SegmentTemplate media="dash-v-$Number%03d$.m4s"/></Representation></AdaptationSet>
    <AdaptationSet mimeType="audio/mp4"><Representation id="a"><SegmentTemplate initialization="dash-a-init.mp4" media="dash-a-$Number%03d$.m4s" duration="3" startNumber="1"/></Representation></AdaptationSet>
    </Period></MPD>'''
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = self.path.split('?')[0]
            if 'guard=1' in self.path and self.headers.get('Referer') != self.base+'/hls-pair':
                self.send_error(403); return
            if route == '/privacy.mp4' and self.headers.get('Referer'):
                self.send_error(403); return
            mime = 'text/html; charset=utf-8'
            body = b''
            if route in chunks: body, mime = chunks[route], 'video/mp4'
            elif route in ['/clip.ts','/slow-second.ts']: body, mime = transport, 'video/mp2t'
            elif route == '/bad.ts': body, mime = b'not-a-transport-stream'*100, 'video/mp2t'
            elif route.endswith('.webm'): body, mime = webm, 'video/webm'
            elif route.endswith('.mp4'): body, mime = video, 'video/mp4'
            elif route == '/master.m3u8':
                body = b'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=1280x720,CODECS="avc1,mp4a"\nvod.m3u8\n'
                mime = 'application/vnd.apple.mpegurl'
            elif route == '/vod.m3u8':
                body = b'#EXTM3U\n#EXT-X-TARGETDURATION:5\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:1,\none.m4s\n#EXTINF:2,\ntwo.m4s\n#EXT-X-ENDLIST\n'
                mime = 'application/vnd.apple.mpegurl'
            elif route == '/ts.m3u8':
                body = b'#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:2.76,\nclip.ts\n#EXT-X-ENDLIST\n'; mime = 'application/vnd.apple.mpegurl'
            elif route in ['/paired-master.m3u8','/mixed-master.m3u8']:
                video_list = 'paired-video.m3u8' if route == '/paired-master.m3u8' else 'ts.m3u8'
                body = ('#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="main",DEFAULT=YES,LANGUAGE="ko",URI="paired-audio.m3u8?guard=1"\n'
                        '#EXT-X-STREAM-INF:BANDWIDTH=600000,RESOLUTION=640x360,AUDIO="main"\n'+video_list+'?guard=1\n').encode()
                mime = 'application/vnd.apple.mpegurl'
            elif route in ['/paired-video.m3u8','/paired-audio.m3u8']:
                track = 'v' if route == '/paired-video.m3u8' else 'a'
                part = '000' if track == 'v' else '001'
                body = f'#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXT-X-MAP:URI="dash-{track}-init.mp4?guard=1"\n#EXTINF:2.8,\ndash-{track}-{part}.m4s?guard=1\n#EXT-X-ENDLIST\n'.encode()
                mime = 'application/vnd.apple.mpegurl'
            elif route == '/ts-slow.m3u8':
                body = b'#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:2.76,\nclip.ts\n#EXTINF:2.76,\nslow-second.ts\n#EXT-X-ENDLIST\n'; mime = 'application/vnd.apple.mpegurl'
            elif route == '/encrypted.m3u8':
                body = b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key"\none.ts\n#EXT-X-ENDLIST\n'; mime = 'application/vnd.apple.mpegurl'
            elif route in ['/dash.mpd','/dash-template.mpd','/dash-protected.mpd','/dash-external.mpd','/dash-empty-audio.mpd']:
                text = template if route == '/dash-template.mpd' else dash
                if route == '/dash-protected.mpd': text = text.replace('<Period>', '<Period><ContentProtection schemeIdUri="urn:uuid:controlled-protected"/>')
                if route == '/dash-external.mpd': text = '<!DOCTYPE MPD [<!ENTITY secret SYSTEM "file:///private">]>'+dash
                if route == '/dash-empty-audio.mpd': text = dash.replace('<Representation id="a" bandwidth="128000"><BaseURL>dash-audio.mp4</BaseURL></Representation>', '')
                body = text.encode(); mime = 'application/dash+xml'
            elif route in ('/bad-video.mp4', '/fake-video.mp4'):
                body = b'<!doctype html><html>Sign in to continue</html>'
                mime = 'text/html' if route == '/bad-video.mp4' else 'video/mp4'
            elif route == '/bad-video-page':
                body = b'<title>Invalid video fixture</title><video src="/bad-video.mp4"></video><video src="/fake-video.mp4"></video>'
            elif route == '/extension.webm':
                body = webm; mime = 'video/webm'
            elif route == '/generic':
                body = '<title>일반 영상 테스트</title><video controls src="/clip.webm" preload="metadata"></video>'.encode()
            elif route == '/youtube':
                data = {'streamingData': {'formats': [{'url': self.base+'/muxed.mp4', 'mimeType': 'video/mp4', 'qualityLabel': '360p'}],
                    'adaptiveFormats': [{'url':self.base+'/dash-video.mp4','mimeType':'video/mp4','qualityLabel':'360p'},
                        {'url':self.base+'/dash-audio.mp4','mimeType':'audio/mp4','bitrate':128000}]}}
                body = ('<title>YouTube 형식 테스트</title><script>var ytInitialPlayerResponse = '+json.dumps(data)+';</script>').encode()
            elif route == '/instagram':
                body = '<title>Instagram 형식 테스트</title><meta property="og:video" content="/reel.mp4"><meta property="og:video:type" content="video/mp4">'.encode()
            elif route == '/hls':
                body = b'<title>HLS fixture</title><video src="/master.m3u8"></video><video src="/encrypted.m3u8"></video>'
            elif route == '/hls-pair':
                body = b'<title>Generic HLS pair</title><video src="/paired-master.m3u8"></video><video src="/mixed-master.m3u8"></video>'
            elif route == '/no-referrer':
                body = b'<title>No referrer fixture</title><meta name="referrer" content="origin"><video src="/privacy.mp4"></video>'
            elif route == '/private': body = b'<title>Private fixture</title><video src="/private.webm"></video>'
            elif route == '/dash': body = b'<title>DASH fixture</title><video src="/dash.mpd"></video><video src="/dash-template.mpd"></video><video src="/dash-protected.mpd"></video><video src="/dash-external.mpd"></video><video src="/dash-empty-audio.mpd"></video>'
            elif route == '/ts-page': body = b'<title>TS fixture</title><video src="/ts.m3u8"></video><video src="/ts-slow.m3u8"></video><a download href="/clip.ts">direct</a><a download href="/bad.ts">invalid</a>'
            else:
                self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            if route == '/extension.webm': self.send_header('Content-Disposition', 'attachment; filename="extension.webm"')
            if route == '/no-referrer': self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            if route.endswith('.m4s'): time.sleep(0.4)
            if route == '/slow-second.ts': time.sleep(2)
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
        def log_message(self, *_): pass
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    Handler.base = f'http://127.0.0.1:{http.server_port}'
    thread = Thread(target=http.serve_forever, daemon=True); thread.start()
    try: yield Handler.base, video, webm, dash_video, dash_audio
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
                cdp.call('Runtime.enable', session=session)
                cdp.call('Log.enable', session=session)
                eventually(lambda: cdp.evaluate(session, 'document.readyState === "complete"'))
                return target, session
            with server(media) as (base, video, webm, dash_video, dash_audio):
                pages = [open_page(base+route) for route in ['/generic','/youtube','/instagram','/hls']]
                context = cdp.call('Target.createBrowserContext')['browserContextId']
                open_page(base+'/private', browserContextId=context)
                _, hub = open_page('chrome://internet-browser/')
                eventually(lambda: cdp.evaluate(hub, '!!document.querySelector("#scan-videos")'))
                def api(command, *args):
                    return cdp.evaluate(hub, '(async()=>{const {sendWithPromise}=await import("chrome://resources/js/cr.js");return await sendWithPromise("internetBrowserCapture",'+','.join(json.dumps(x) for x in (command,*args))+');})()')
                tab_rows = api('tabs')['tabs']
                source_tab = next(row for row in tab_rows if row['url']==base+'/generic')
                checks['tab_picker_excludes_other_profile'] = not any(row['url']==base+'/private' for row in tab_rows)
                cdp.evaluate(hub, 'document.querySelector("#capture-tab").value='+json.dumps(source_tab['token'])+';document.querySelector("#scan-videos").click()')
                eventually(lambda: cdp.evaluate(hub, 'document.querySelectorAll("#capture-results article").length === 1'))
                checks['capture_screen_and_quality_options'] = cdp.evaluate(hub, 'document.querySelector("#capture-results h3").textContent.includes("일반 영상")')
                scoped = api('scan', source_tab['token'])
                checks['native_scan_only_selected_tab'] = bool(scoped['items']) and all(row['page']==base+'/generic' for row in scoped['items'])
                checks['forged_tab_token_rejected'] = bool(api('scan', 'not-a-browser-token').get('error'))
                # Refill the UI with its own tokens after the direct API check.
                cdp.evaluate(hub, 'document.querySelector("#scan-videos").click()')
                eventually(lambda: cdp.evaluate(hub, '!document.querySelector("#scan-videos").disabled'))
                cdp.call('Browser.setDownloadBehavior', {'behavior':'default'})
                cdp.evaluate(hub, '[...document.querySelectorAll("#capture-results article")].find(row=>row.querySelector("h3").textContent.includes("일반 영상")).querySelector("button").click()')
                eventually(lambda: any(file.read_bytes()==webm for file in profile.glob('*/InternetBrowserVideos/*/video.webm')))
                checks['native_capture_download_exact_bytes'] = True
                _, bad_page = open_page(base+'/bad-video-page')
                bad_tab = next(row for row in api('tabs')['tabs'] if row['url']==base+'/bad-video-page')
                bad_candidates = api('scan', bad_tab['token'])['items']
                assert len(bad_candidates)==2
                for candidate in bad_candidates:
                    job = api('download', candidate['token'])
                    assert job.get('started'), job
                    failed = eventually(lambda: next((row for row in api('transfers')['items'] if row['guid']==job['guid'] and row['state']==3), None))
                    checks['html_response_rejected_'+candidate['url'].rsplit('/',1)[1]] = bool(failed['error']) and not list(profile.glob('*/InternetBrowserVideos/stream-'+job['guid'].split(':')[1]+'/complete.json'))
                cdp.call('Page.navigate', {'url':'about:blank'}, session=bad_page)
                # Keep independent coverage of ordinary browser-managed downloads,
                # including files an extension can hand to the download manager.
                cdp.call('Browser.setDownloadBehavior', {'behavior':'allow', 'downloadPath':str(downloads)})
                cdp.call('Page.navigate', {'url':base+'/extension.webm'}, session=bad_page)
                eventually(lambda: any(file.read_bytes()==webm for file in downloads.glob('*.webm')))
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
                completed = [path for path in profile.glob('*/InternetBrowserVideos/*/complete.json') if json.loads(path.read_text(encoding='utf-8')).get('title')=='HLS fixture']
                checks['hls_exact_assembled_bytes'] = len(completed)==1 and completed[0].with_name('video.mp4').read_bytes()==video
                checks['hls_partial_files_removed'] = not list(profile.glob('*/InternetBrowserVideos/*/video.part'))
                cancellation = api('download', stream['token'])
                if not cancellation.get('started'): raise RuntimeError(str(cancellation))
                cancelled = api('control', cancellation['guid'], 'cancel')
                checks['hls_cancel'] = any(row['guid']==cancellation['guid'] and row['state']==2 for row in cancelled.get('items',[]))
                eventually(lambda: not list(profile.glob('*/InternetBrowserVideos/*/video.part')))
                checks['hls_cancel_not_in_library'] = not list(profile.glob('*/InternetBrowserVideos/stream-'+cancellation['guid'].split(':')[1]+'/complete.json'))
                def library():
                    return cdp.evaluate(hub, '(async()=>{const {sendWithPromise}=await import("chrome://resources/js/cr.js");return await sendWithPromise("internetBrowserVideos");})()')
                eventually(lambda: cdp.evaluate(hub, '!document.querySelector("#clear-video-transfers").disabled'))
                cdp.evaluate(hub, 'document.querySelector("#clear-video-transfers").click()')
                eventually(lambda: cdp.evaluate(hub, 'document.querySelectorAll("#video-transfers .video-transfer").length===0'))
                checks['progress_history_clear_preserves_saved_media'] = completed[0].with_name('video.mp4').read_bytes()==video and bool(library()['videos'])
                cdp.call('Page.navigate', {'url':'chrome://internet-browser/'}, session=hub)
                eventually(lambda: cdp.evaluate(hub, 'document.querySelector("#video-transfers")?.textContent.includes("표시할")'))
                checks['progress_history_dismissal_survives_hub_reload'] = cdp.evaluate(hub, 'document.querySelectorAll("#video-transfers .video-transfer").length===0')
                catalog = eventually(library, lambda value: any(item.get('name','').startswith('stream:') for item in value.get('videos',[])))
                saved = next(item for item in catalog['videos'] if item['name'].startswith('stream:') and item['title']=='HLS fixture')
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
                checks['navigated_tab_token_rejected'] = bool(api('scan', source_tab['token']).get('error'))
                open_page(base+'/dash')
                discovered = api('scan')
                yt_pair = next(row for row in discovered['items'] if row.get('paired') and row['page'].endswith('/youtube'))
                checks['youtube_adaptive_pair_detected'] = yt_pair['quality']=='360p'
                yt_saved = api('download', yt_pair['token'])
                if not yt_saved.get('started'): raise RuntimeError(str(yt_saved))
                yt_status = eventually(lambda: next((row for row in api('transfers')['items'] if row['guid']==yt_saved['guid'] and row['state'] in (1,3)),None))
                if yt_status['state']!=1: raise RuntimeError(str(yt_status))
                yt_marker = next(path for path in profile.glob('*/InternetBrowserVideos/*/complete.json') if json.loads(path.read_text(encoding='utf-8')).get('title')=='YouTube 형식 테스트')
                checks['youtube_adaptive_pair_exact_bytes'] = yt_marker.with_name('video.mp4').read_bytes()==dash_video and yt_marker.with_name('audio.mp4').read_bytes()==dash_audio
                def dash_candidate(suffix): return next(row for row in discovered['items'] if row['url'].endswith(suffix))
                protected = api('inspect', dash_candidate('/dash-protected.mpd')['token'])
                checks['protected_dash_rejected'] = '보호' in protected.get('error','')
                external = api('inspect', dash_candidate('/dash-external.mpd')['token'])
                checks['dash_external_entities_rejected'] = bool(external.get('error'))
                incomplete = api('inspect', dash_candidate('/dash-empty-audio.mpd')['token'])
                checks['dash_missing_declared_audio_rejected'] = bool(incomplete.get('error'))
                resolved = api('inspect', dash_candidate('/dash.mpd')['token'])
                if resolved.get('error'): raise RuntimeError(resolved['error'])
                variants = resolved['items']
                checks['dash_segment_list_and_timeline_resolved'] = len(variants)==2 and all(row.get('paired') and row['quality']=='360p' for row in variants)
                numbered = api('inspect', dash_candidate('/dash-template.mpd')['token'])
                checks['dash_numbered_template_resolved'] = len(numbered.get('items',[]))==1 and numbered['items'][0].get('paired') is True
                saved_pair = api('download', variants[1]['token'])
                if not saved_pair.get('started'): raise RuntimeError(str(saved_pair))
                pair_status = eventually(lambda: next((row for row in api('transfers')['items'] if row['guid']==saved_pair['guid'] and row['state'] in (1,3)),None))
                if pair_status['state']!=1: raise RuntimeError(str(pair_status))
                pair_marker = next(path for path in profile.glob('*/InternetBrowserVideos/*/complete.json') if json.loads(path.read_text(encoding='utf-8')).get('title')=='DASH fixture')
                checks['dash_tracks_exact_original_bytes'] = pair_marker.with_name('video.mp4').read_bytes()==dash_video and pair_marker.with_name('audio.mp4').read_bytes()==dash_audio
                pair_row = next(row for row in library()['videos'] if row['title']=='DASH fixture')
                checks['dash_library_includes_companion_audio'] = pair_row.get('audioUrl','').endswith('/audio.mp4')
                report['stage'] = 'open_dash_offline_pair'
                cdp.evaluate(hub, '(async()=>{const {sendWithPromise}=await import("chrome://resources/js/cr.js");return await sendWithPromise("internetBrowserOpenVideo",'+json.dumps(pair_row['url'])+');})()')
                cdp.call('Page.bringToFront', session=hub)
                eventually(lambda: cdp.evaluate(hub, 'document.querySelector("#internet-browser-companion-audio")?.readyState>=1 && document.querySelector("video")?.readyState>=1'))
                report['stage'] = 'play_dash_offline_pair'
                cdp.evaluate(hub, '[...document.querySelectorAll(".ib-controls button")].find(button=>button.textContent==="재생").click()', user_gesture=True)
                checks['dash_video_and_audio_play_together'] = eventually(lambda: cdp.evaluate(hub, '(()=>{const v=document.querySelector("video"),a=document.querySelector("audio");return !v.paused&&!a.paused&&v.currentTime>0.1&&a.currentTime>0.1&&Math.abs(v.currentTime-a.currentTime)<0.25;})()'))
                cdp.evaluate(hub, '(()=>{const v=document.querySelector("video");v.currentTime=0.6;v.playbackRate=1.5;v.volume=0.3;})()')
                checks['dash_seek_rate_and_volume_synchronized'] = eventually(lambda: cdp.evaluate(hub, '(()=>{const v=document.querySelector("video"),a=document.querySelector("audio");return a.playbackRate===1.5&&Math.abs(a.volume-0.3)<0.001&&Math.abs(a.currentTime-v.currentTime)<0.25;})()'))
                cdp.evaluate(hub, 'document.querySelector("video").pause()')
                checks['dash_pause_stops_audio'] = eventually(lambda: cdp.evaluate(hub, 'document.querySelector("video").paused && document.querySelector("audio").paused'))
                # The pair is a durable library entry, not an in-memory job.
                command = browser.args
                cdp.call('Browser.close'); cdp.close(); cdp = None; browser.wait(timeout=20)
                endpoint.unlink(missing_ok=True)
                browser = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                port = eventually(lambda: endpoint.read_text().splitlines()[0] if endpoint.exists() else None)
                cdp = Cdp(json.load(urlopen(f'http://127.0.0.1:{port}/json/version'))['webSocketDebuggerUrl'])
                _, hub = open_page('chrome://internet-browser/')
                durable = next(row for row in library()['videos'] if row['title']=='DASH fixture')
                checks['dash_pair_survives_browser_restart'] = durable.get('audioUrl')==pair_row['audioUrl'] and durable['url']==pair_row['url']
                checks['saved_pair_reports_combined_size'] = durable.get('sizeBytes') == pair_marker.with_name('video.mp4').stat().st_size + pair_marker.with_name('audio.mp4').stat().st_size
                def delete_video(url, files):
                    return cdp.evaluate(hub, '(async()=>{const {sendWithPromise}=await import("chrome://resources/js/cr.js");return await sendWithPromise("internetBrowserDeleteVideo",'+json.dumps(url)+','+json.dumps(files)+');})()')
                sentinel = profile/'Default'/'v024-delete-sentinel.txt'; sentinel.write_bytes(b'protected non-library fixture')
                rejected = delete_video(sentinel.as_uri(), True)
                checks['non_library_file_delete_rejected'] = bool(rejected.get('error')) and sentinel.read_bytes()==b'protected non-library fixture'
                webm_files = {path:path.read_bytes() for path in downloads.glob('*.webm')}
                assert webm_files and all(path.is_relative_to(root) for path in webm_files)
                owned_urls = {path.as_uri() for path in webm_files}
                webm_row = next(row for row in library()['videos'] if row['url'] in owned_urls)
                hidden = delete_video(webm_row['url'], False)
                checks['record_only_delete_preserves_media_bytes'] = hidden.get('deleted') is True and all(path.read_bytes()==data for path,data in webm_files.items()) and not any(row['url']==webm_row['url'] for row in library()['videos'])
                erased = delete_video(durable['url'], True)
                checks['pair_delete_removes_video_audio_and_completion_marker'] = erased.get('deleted') is True and all(not pair_marker.with_name(name).exists() for name in ('video.mp4','audio.mp4','complete.json'))
                checks['pair_delete_preserves_other_saved_video'] = yt_marker.with_name('video.mp4').read_bytes()==dash_video and yt_marker.with_name('audio.mp4').read_bytes()==dash_audio
                checks['deleted_pair_disappears_from_library'] = not any(row['url']==durable['url'] for row in library()['videos'])
                open_page(base+'/no-referrer')
                private_candidate = next(row for row in api('scan')['items'] if row['url'].endswith('/privacy.mp4'))
                cdp.call('Browser.setDownloadBehavior', {'behavior':'allow','downloadPath':str(downloads)})
                private_saved = api('download', private_candidate['token'])
                if not private_saved.get('started'): raise RuntimeError(str(private_saved))
                private_status = eventually(lambda: next((row for row in api('transfers')['items'] if row['guid']==private_saved['guid'] and row['state'] in (1,3)),None))
                checks['source_no_referrer_policy_preserved'] = private_status['state']==1
                cdp.call('Browser.setDownloadBehavior', {'behavior':'default'})
                open_page(base+'/hls-pair')
                hls_found = api('scan')['items']
                for suffix, label in [('/paired-master.m3u8','generic_hls_pair'),('/mixed-master.m3u8','generic_hls_mixed_pair')]:
                    master = next(row for row in hls_found if row['url'].endswith(suffix))
                    choices = api('inspect', master['token'])
                    if choices.get('error'): raise RuntimeError(str(choices))
                    choice = choices['items'][0]
                    checks[label+'_quality_and_audio'] = choice.get('paired') is True and choice.get('audioLanguage')=='ko'
                    plan = api('inspect', choice['token'])
                    if plan.get('error'): raise RuntimeError(str(plan))
                    saved = api('download', plan['items'][0]['token'])
                    if not saved.get('started'): raise RuntimeError(str(saved))
                    status = eventually(lambda: next((row for row in api('transfers')['items'] if row['guid']==saved['guid'] and row['state'] in (1,3)),None))
                    if status['state']!=1: raise RuntimeError(str(status))
                    marker = next(profile.glob('*/InternetBrowserVideos/stream-'+saved['guid'].split(':')[1]+'/complete.json'))
                    checks[label+'_audio_exact_bytes'] = marker.with_name('audio.mp4').read_bytes()==dash_audio and json.loads(marker.read_text())['separateAudio'] is True
                    if label=='generic_hls_pair':
                        checks['generic_hls_pair_video_exact_bytes'] = marker.with_name('video.mp4').read_bytes()==dash_video
                    else:
                        converted = marker.with_name('video.mp4').read_bytes()
                        checks['generic_hls_mixed_pair_video_converted'] = len(converted)>8 and converted[4:8]==b'ftyp'
                open_page(base+'/ts-page')
                _, hub = open_page('chrome://internet-browser/')
                transport_candidates = api('scan')['items']
                manifest_row = next(row for row in transport_candidates if row['url'].endswith('/ts.m3u8'))
                transport_plan = api('inspect', manifest_row['token'])
                if transport_plan.get('error'): raise RuntimeError(transport_plan['error'])
                ts_row = transport_plan['items'][0]
                checks['hls_transport_stream_resolved'] = ts_row.get('convertedFromTs') is True
                ts_saved = api('download', ts_row['token'])
                if not ts_saved.get('started'): raise RuntimeError(str(ts_saved))
                ts_status = eventually(lambda: next((row for row in api('transfers')['items'] if row['guid']==ts_saved['guid'] and row['state'] in (1,3)),None))
                if ts_status['state']!=1: raise RuntimeError(str(ts_status))
                checks['transport_processing_origin_isolated'] = ts_status.get('isolatedProcessor') is True
                ts_path = next(profile.glob('*/InternetBrowserVideos/stream-'+ts_saved['guid'].split(':')[1]+'/video.mp4'))
                checks['transport_stream_saved_as_mp4'] = ts_path.read_bytes()[4:8]==b'ftyp'
                ts_catalog = next(row for row in library()['videos'] if row['url']==ts_path.as_uri())
                cdp.evaluate(hub, '(async()=>{const {sendWithPromise}=await import("chrome://resources/js/cr.js");return await sendWithPromise("internetBrowserOpenVideo",'+json.dumps(ts_catalog['url'])+');})()')
                cdp.call('Page.bringToFront',session=hub)
                eventually(lambda: cdp.evaluate(hub, '!!document.querySelector("#internet-browser-player") && document.querySelector("video").readyState>=1'))
                cdp.evaluate(hub, 'document.querySelector("video").play()',user_gesture=True)
                checks['transport_mp4_video_and_audio_decoded'] = eventually(lambda: cdp.evaluate(hub, '(()=>{const v=document.querySelector("video");return v.currentTime>0.2&&v.webkitAudioDecodedByteCount>0&&v.webkitVideoDecodedByteCount>0&&v.videoWidth===1280&&v.videoHeight===720&&!v.error;})()'))
                _, hub = open_page('chrome://internet-browser/')
                direct_ts = next(row for row in transport_candidates if row['url'].endswith('/clip.ts'))
                direct_saved = api('download', direct_ts['token'])
                if not direct_saved.get('started'): raise RuntimeError(str(direct_saved))
                direct_status = eventually(lambda: next((row for row in api('transfers')['items'] if row['guid']==direct_saved['guid'] and row['state'] in (1,3)),None))
                checks['direct_transport_stream_converted'] = direct_status['state']==1
                invalid = next(row for row in transport_candidates if row['url'].endswith('/bad.ts'))
                invalid_saved = api('download', invalid['token'])
                invalid_status = eventually(lambda: next((row for row in api('transfers')['items'] if row['guid']==invalid_saved['guid'] and row['state'] in (1,3)),None))
                checks['invalid_transport_stream_not_registered'] = invalid_status['state']==3 and not list(profile.glob('*/InternetBrowserVideos/stream-'+invalid_saved['guid'].split(':')[1]+'/complete.json'))
                checks['transmux_processor_released'] = eventually(lambda: not any(target.get('url')=='chrome://internet-browser-transmux/' for target in cdp.call('Target.getTargets')['targetInfos']))
                slow = next(row for row in transport_candidates if row['url'].endswith('/ts-slow.m3u8'))
                slow_plan = api('inspect', slow['token'])
                slow_saved = api('download', slow_plan['items'][0]['token'])
                if not slow_saved.get('started'): raise RuntimeError(str(slow_saved))
                eventually(lambda: any(row['guid']==slow_saved['guid'] and row['state']==0 and row.get('completedParts',0)>=1 for row in api('transfers')['items']))
                report['stage'] = 'close_browser_with_active_transmux'
                cdp.call('Browser.close'); cdp.close(); cdp=None; browser.wait(timeout=20)
                checks['active_transmux_browser_shutdown'] = browser.returncode==0
                checks['active_transmux_partial_cleanup'] = not list(profile.glob('*/InternetBrowserVideos/stream-'+slow_saved['guid'].split(':')[1]))
                report['assembled_mp4_sha256'] = hashlib.sha256(video).hexdigest()
                report['all_checks_passed'] = all(checks.values())
        except Exception as error:
            report['error'] = repr(error); report['all_checks_passed'] = False
            if cdp:
                try: report['transfers_at_failure'] = api('transfers')
                except Exception: pass
                try: report['final_page'] = cdp.evaluate(hub, '({url:location.href,visibility:document.visibilityState,text:document.body?.innerText?.slice(-1600),media:[...document.querySelectorAll("video,audio")].map(v=>({tag:v.tagName,src:v.currentSrc||v.src,readyState:v.readyState,networkState:v.networkState,preload:v.preload,paused:v.paused,time:v.currentTime,error:v.error?{code:v.error.code,message:v.error.message}:null}))})')
                except Exception: pass
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
