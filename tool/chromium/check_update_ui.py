"""Renderer update-flow regression check with a stub native service.

Does not download or execute any installer; native download/hash/OS acceptance
is separate and must run against the product before release.
"""
import argparse, base64, hashlib, json, subprocess, shutil, os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen
try:
    from .smoke_windows import Cdp, eventually
except ImportError:
    from smoke_windows import Cdp, eventually
ROOT = Path(__file__).resolve().parents[2]

def run(browser, work):
    work.mkdir(parents=True, exist_ok=True)
    checks = {}
    with TemporaryDirectory(prefix='update-ui-', dir=work) as temporary:
        directory = Path(temporary); profile = directory/'profile'
        resources = ROOT/'native/chromium/windows/resources'
        html = (resources/'index.html').read_text(encoding='utf-8').replace('<script type="module" src="app.js"></script>', '')
        (directory/'index.html').write_text(html, encoding='utf-8')
        shutil.copyfile(resources/'style.css', directory/'style.css')
        shutil.copyfile(ROOT/'assets/icon/parcel.svg', directory/'logo.svg')
        process = subprocess.Popen([str(browser), '--headless=new', '--disable-gpu', '--no-first-run',
            '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-address=127.0.0.1',
            '--remote-debugging-port=0', f'--user-data-dir={profile}', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cdp = None
        try:
            active = profile/'DevToolsActivePort'
            port = eventually(lambda: active.read_text().splitlines()[0] if active.exists() else None)
            info = json.load(urlopen(f'http://127.0.0.1:{port}/json/version', timeout=10))
            cdp = Cdp(info['webSocketDebuggerUrl'])
            page = next(x for x in cdp.call('Target.getTargets')['targetInfos'] if x['type']=='page')
            session = cdp.call('Target.attachToTarget', {'targetId':page['targetId'],'flatten':True})['sessionId']
            cdp.call('Page.enable', session=session)
            cdp.call('Page.navigate', {'url':(directory/'index.html').as_uri()}, session=session)
            eventually(lambda: cdp.evaluate(session, '!!document.querySelector("#update-check")'))
            evaluate = lambda code: cdp.evaluate(session, code)
            evaluate('''globalThis.calls=[];globalThis.confirm=()=>false;globalThis.failDownload=false;globalThis.videoTitle='Saved example';
              globalThis.sendWithPromise=async (name,...args)=>{
                calls.push([name,...args]);
                if(name==='internetBrowserStatus')return {enabled:false,status:'테스트'};
                if(name==='internetBrowserLegacy')return {found:false,settings:{update_auto_check:false}};
                if(name==='internetBrowserVideos')return {videos:[{title:videoTitle,url:'file:///controlled/sample.webm'},{title:'Scoped example',url:'content://media/external/downloads/42'}]};
                if(name==='internetBrowserRenameVideo'){videoTitle=args[1].trim();return {saved:true,title:videoTitle};}
                if(name==='internetBrowserOpenVideo')return {opened:true};
                if(name==='internetBrowserCapture'&&args[0]==='tabs')return {tabs:[{token:'first',title:'First page',url:'https://example.test/one',active:true},{token:'second',title:'Second page',url:'https://example.test/two'}]};
                if(name==='internetBrowserCapture'&&args[0]==='scan')return {items:[],reasons:[]};
                if(name==='internetBrowserDeleteVideo')return {deleted:true};
                if(name==='internetBrowserUpdate'){
                  if(args[0]==='check')return {available:true,canInstall:true,version:'0.3.0',tag:'v0.3.0',description:'<img src=x onerror=alert(1)>',releasePage:'https://github.com/sopo9880/Internet-browser/releases/tag/v0.3.0',android:!!globalThis.androidUpdate};
                  if(args[0]==='download') {
                    if(globalThis.holdDownload)return new Promise(resolve=>{globalThis.finishUpdate=()=>resolve({verified:true});});
                    return failDownload?{error:'SHA-256 mismatch'}:{verified:true};
                  }
                  if(args[0]==='progress')return globalThis.downloadProgress||{};
                  if(['security','location','settings'].includes(args[0]))return {opened:true};
                  if(args[0]==='install')return {opened:true};
                }
                return {};
              };''')
            source=(resources/'app.js').read_text(encoding='utf-8').split('\n',1)[1]
            evaluate('(async()=>{'+source+'\n})()')
            evaluate("document.querySelector('.rename-video').click()")
            evaluate("document.querySelector('dialog button[value=cancel]').click()")
            checks['rename_cancel_keeps_original'] = evaluate("!calls.some(x=>x[0]==='internetBrowserRenameVideo')&&document.querySelector('#videos button').textContent==='Saved example'")
            evaluate("document.querySelector('.rename-video').click()")
            evaluate("document.querySelector('dialog input').value='<img src=x> 새 제목';document.querySelector('dialog button[value=accept]').click()")
            eventually(lambda:evaluate("document.querySelector('#videos button').textContent==='<img src=x> 새 제목'"))
            checks['renamed_title_is_literal'] = evaluate("!document.querySelector('#videos img')&&calls.some(x=>x[0]==='internetBrowserRenameVideo'&&x[1]==='file:///controlled/sample.webm')")
            evaluate("document.querySelector('#refresh-videos').click()")
            eventually(lambda:evaluate("!document.querySelector('#refresh-videos').disabled"))
            checks['library_refresh_keeps_titles_without_duplicate_rows'] = evaluate("document.querySelectorAll('#videos li').length===2 && document.querySelector('#videos button').textContent==='<img src=x> 새 제목'")
            evaluate("[...document.querySelectorAll('#videos button')].find(x=>x.textContent==='Scoped example').click()")
            checks['scoped_uri_is_passed_to_native_lookup'] = evaluate("calls.some(x=>x[0]==='internetBrowserOpenVideo'&&x[1]==='content://media/external/downloads/42')")
            checks['legacy_auto_check_choice'] = evaluate("!document.querySelector('#update-auto').checked && !calls.some(x=>x[0]==='internetBrowserUpdate'&&x[1]==='check')")
            evaluate("document.querySelector('#tab-video').click();document.querySelector('#capture-tab').value='second';document.querySelector('#scan-videos').click()")
            eventually(lambda:evaluate("calls.some(x=>x[0]==='internetBrowserCapture'&&x[1]==='scan'&&x[2]==='second')"))
            checks['selected_tab_only_requested'] = True
            checks['settings_tabs_switch_panels'] = evaluate("!document.querySelector('#panel-video').hidden&&document.querySelector('#panel-general').hidden&&document.querySelector('#tab-video').getAttribute('aria-selected')==='true'")
            evaluate("document.querySelector('#tab-updates').click()")
            evaluate("document.querySelector('#update-check').click()")
            eventually(lambda:evaluate("!document.querySelector('#update-release').hidden"))
            checks['notes_are_literal'] = evaluate("document.querySelector('#update-notes').textContent === '<img src=x onerror=alert(1)>' && !document.querySelector('#update-notes img')")
            checks['install_hidden_before_verification'] = evaluate("document.querySelector('#update-install').hidden")
            evaluate("document.querySelector('#update-download').click()")
            eventually(lambda:evaluate("!document.querySelector('#update-install').hidden"))
            checks['install_shown_after_verification'] = True
            evaluate("document.querySelector('#update-install').click()")
            checks['cancel_never_requests_install'] = evaluate("!calls.some(x=>x[0]==='internetBrowserUpdate'&&x[1]==='install')")
            evaluate("document.querySelector('dialog button[value=cancel]').click()")
            eventually(lambda:evaluate("!document.querySelector('dialog')"))
            evaluate("document.querySelector('#update-install').click()")
            evaluate("document.querySelector('dialog button[value=accept]').click()")
            eventually(lambda:evaluate("calls.filter(x=>x[0]==='internetBrowserUpdate'&&x[1]==='install').length===1"))
            checks['confirm_requests_install_once'] = True
            evaluate("document.querySelector('#update-check').click()")
            eventually(lambda:evaluate("!document.querySelector('#update-check').disabled"))
            evaluate("globalThis.failDownload=true;document.querySelector('#update-download').click()")
            eventually(lambda:evaluate("document.querySelector('#update-status').textContent.includes('SHA-256 mismatch')"))
            checks['hash_error_does_not_offer_install'] = evaluate("document.querySelector('#update-install').hidden")
            evaluate("document.querySelector('#update-snooze').click()")
            checks['snooze_is_tag_specific'] = evaluate("localStorage.getItem('update_snoozed_tag')==='v0.3.0'&&Number(localStorage.getItem('update_snoozed_until'))>Date.now()&&document.querySelector('#update-release').hidden")
            evaluate("globalThis.androidUpdate=true;globalThis.failDownload=false;document.querySelector('#update-check').click()")
            eventually(lambda:evaluate("!document.querySelector('#update-release').hidden&&!document.querySelector('#update-check').disabled"))
            evaluate("globalThis.holdDownload=true;globalThis.downloadProgress={phase:'downloading',receivedBytes:52428800,totalBytes:104857600};document.querySelector('#update-download').click()")
            eventually(lambda:evaluate("document.querySelector('#update-progress-label').textContent.includes('50%')"))
            checks['download_progress_shows_percent_and_byte_counts'] = evaluate("document.querySelector('#update-progress').value===50&&document.querySelector('#update-progress-label').textContent.includes('50 MB / 100 MB')")
            evaluate("globalThis.finishUpdate()")
            eventually(lambda:evaluate("calls.some(x=>x[0]==='internetBrowserUpdate'&&x[1]==='security')&&!document.querySelector('#update-install').hidden"))
            checks['android_verified_download_opens_security_screen'] = True
            evaluate("window.dispatchEvent(new Event('focus'));document.querySelector('#update-location').click()")
            eventually(lambda:evaluate("calls.some(x=>x[0]==='internetBrowserUpdate'&&x[1]==='location')"))
            checks['android_return_offers_install_retry_and_export_location'] = evaluate("!document.querySelector('#update-install').hidden&&!document.querySelector('#update-location').hidden&&!document.querySelector('#update-return-help').hidden")
            for label, width, height in [('desktop',1200,900),('mobile',390,844)]:
                checks['video_downloadhelper_below_adblock'] = evaluate("(()=>{const cards=[...document.querySelectorAll('#panel-general article')];return cards[0]?.querySelector('h3')?.textContent==='AdBlock'&&cards[1]?.querySelector('h3')?.textContent==='Video DownloadHelper'&&cards[1].querySelector('a').href==='https://chromewebstore.google.com/detail/video-download-helper/lmjnegcaeklhafolokijcfjliaokphfk';})()")
                cdp.call('Emulation.setDeviceMetricsOverride', {'width':width,'height':height,'deviceScaleFactor':1,'mobile':label=='mobile'}, session=session)
                screenshot=cdp.call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':True}, session=session)
                (work/(label+'-settings.png')).write_bytes(base64.b64decode(screenshot['data']))
            result={'kind':'UPDATE_RENDERER_FLOW_WITH_STUB_NATIVE_SERVICE','checks':checks,
                    'chrome_exe_sha256':hashlib.sha256(browser.read_bytes()).hexdigest(),
                    'chrome_dll_sha256':hashlib.sha256(browser.with_name('chrome.dll').read_bytes()).hexdigest(),
                    'renderer_sources':{name:hashlib.sha256((resources/name).read_bytes()).hexdigest()
                                        for name in ('index.html','app.js','style.css')},
                    'native_download_hash_verified':False,'native_download_library_verified':False,'installer_executed':False,'release_approved':False}
            if not all(checks.values()):raise RuntimeError(str(result))
            (work/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            return result
        finally:
            if cdp:
                try:cdp.call('Browser.close')
                except Exception:pass
                cdp.close()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(run(args.browser.resolve(),args.work.resolve())))
