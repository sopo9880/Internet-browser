"""Renderer update-flow regression check with a stub native service.

Does not download or execute any installer; native download/hash/OS acceptance
is separate and must run against the product before release.
"""
import argparse, json, subprocess, shutil, os
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
            evaluate('''globalThis.calls=[];globalThis.confirm=()=>false;globalThis.failDownload=false;
              globalThis.sendWithPromise=async (name,...args)=>{
                calls.push([name,...args]);
                if(name==='internetBrowserStatus')return {enabled:false,status:'테스트'};
                if(name==='internetBrowserLegacy')return {found:false,settings:{update_auto_check:false}};
                if(name==='internetBrowserVideos')return {videos:[]};
                if(name==='internetBrowserUpdate'){
                  if(args[0]==='check')return {available:true,canInstall:true,version:'0.3.0',tag:'v0.3.0',description:'<img src=x onerror=alert(1)>',releasePage:'https://github.com/sopo9880/Internet-browser/releases/tag/v0.3.0',android:false};
                  if(args[0]==='download')return failDownload?{error:'SHA-256 mismatch'}:{verified:true};
                  if(args[0]==='install')return {opened:true};
                }
                return {};
              };''')
            source=(resources/'app.js').read_text(encoding='utf-8').split('\n',1)[1]
            evaluate('(async()=>{'+source+'\n})()')
            checks['legacy_auto_check_choice'] = evaluate("!document.querySelector('#update-auto').checked && !calls.some(x=>x[0]==='internetBrowserUpdate')")
            evaluate("document.querySelector('#update-check').click()")
            eventually(lambda:evaluate("!document.querySelector('#update-release').hidden"))
            checks['notes_are_literal'] = evaluate("document.querySelector('#update-notes').textContent === '<img src=x onerror=alert(1)>' && !document.querySelector('#update-notes img')")
            checks['install_hidden_before_verification'] = evaluate("document.querySelector('#update-install').hidden")
            evaluate("document.querySelector('#update-download').click()")
            eventually(lambda:evaluate("!document.querySelector('#update-install').hidden"))
            checks['install_shown_after_verification'] = True
            evaluate("document.querySelector('#update-install').click()")
            checks['cancel_never_requests_install'] = evaluate("!calls.some(x=>x[0]==='internetBrowserUpdate'&&x[1]==='install')")
            evaluate("globalThis.confirm=()=>true;document.querySelector('#update-install').click()")
            eventually(lambda:evaluate("calls.filter(x=>x[0]==='internetBrowserUpdate'&&x[1]==='install').length===1"))
            checks['confirm_requests_install_once'] = True
            evaluate("document.querySelector('#update-check').click()")
            eventually(lambda:evaluate("!document.querySelector('#update-check').disabled"))
            evaluate("globalThis.failDownload=true;document.querySelector('#update-download').click()")
            eventually(lambda:evaluate("document.querySelector('#update-status').textContent.includes('SHA-256 mismatch')"))
            checks['hash_error_does_not_offer_install'] = evaluate("document.querySelector('#update-install').hidden")
            evaluate("document.querySelector('#update-snooze').click()")
            checks['snooze_is_tag_specific'] = evaluate("localStorage.getItem('update_snoozed_tag')==='v0.3.0'&&Number(localStorage.getItem('update_snoozed_until'))>Date.now()&&document.querySelector('#update-release').hidden")
            result={'kind':'UPDATE_RENDERER_FLOW_WITH_STUB_NATIVE_SERVICE','checks':checks,
                    'native_download_hash_verified':False,'installer_executed':False,'release_approved':False}
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
