"""Create an isolated runnable copy from the exact native installer archive.

No registry/default-browser installation is performed. App binaries are never
modified; version-directory files are placed beside the launcher for tests.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import sys
try:
    from .prepare_windows import PRODUCT
except ImportError:
    from prepare_windows import PRODUCT


def sha256(path: Path) -> str:
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def configure_appcontainer(source_script: Path, application: Path) -> str:
    source_script = source_script.resolve(strict=True)
    checkout = source_script.parents[2]
    if source_script != checkout / 'build/win/set_appcontainer_acls.py':
        raise ValueError('Expected the pinned Chromium AppContainer build helper')
    revision = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PRODUCT['chromium_revision']:
        raise ValueError('AppContainer helper source revision differs')
    for relative in ('build/win/set_appcontainer_acls.py', 'testing/scripts/common.py'):
        original = subprocess.check_output(['git', '-C', str(checkout), 'show', revision + ':' + relative])
        if (checkout / relative).read_bytes() != original:
            raise ValueError('Pinned Chromium AppContainer helper has changed: ' + relative)
    # The upstream build does this for out/. Grant only sandboxed-process read
    # and execute on this owned program copy; do not change sandbox policy.
    subprocess.run([sys.executable, str(source_script), '--dir', str(application)], check=True)
    return sha256(source_script)


def archive_paths(listing: str) -> list[str]:
    paths=[];seen=set()
    for line in listing.splitlines():
        if line.startswith(('Symbolic Link =', 'Hard Link =')):
            raise ValueError('Installer runtime archive must contain regular files only')
        if not line.startswith('Path = '):continue
        name=line[7:].replace('\\','/')
        parts=name.split('/')
        path=PureWindowsPath(name)
        if (path.drive or path.root or not parts or parts[0]!='Chrome-bin' or
            any(part in ('','.', '..') or ':' in part or part.endswith(('.', ' ')) for part in parts)):
            raise ValueError('Installer archive path escapes its product directory')
        folded=name.casefold()
        if folded in seen:raise ValueError('Duplicate or case-colliding installer path')
        seen.add(folded);paths.append(name)
    if not paths or 'Chrome-bin/chrome.exe' not in paths:
        raise ValueError('Native installer archive has no product launcher')
    return paths


def prepare(build: Path, runtime: Path, extractor: Path,
            appcontainer_acl_script: Path | None = None) -> dict:
    build=build.resolve(strict=True)
    if runtime.exists() or runtime.is_symlink():raise ValueError('Refusing to overwrite an existing runtime directory')
    runtime=runtime.resolve()
    parent=runtime.parent
    parent.mkdir(parents=True,exist_ok=True)
    report=json.loads((build/'native-provenance.json').read_text(encoding='utf-8'))
    archive=build/'chrome.7z'
    if (report.get('native_source_compiled') is not True or report.get('product')!=PRODUCT or
        sha256(archive)!=report.get('files',{}).get('chrome.7z')):
        raise ValueError('Compiled native archive bytes/product do not match provenance')
    listing=subprocess.check_output([str(extractor),'l','-slt','-ba',str(archive)],text=True,encoding='utf-8',errors='strict')
    archive_paths(listing)
    if os.name == 'nt' and appcontainer_acl_script is None:
        raise ValueError('Windows runtime copies require the pinned AppContainer ACL helper')
    # Public program files inherit the parent's ordinary ACL. Private profiles
    # still belong in private directories. Keep Chrome-bin inside this unique
    # wrapper so no directory rename is required while scanners hold handles.
    runtime.mkdir()
    incomplete = runtime / '.preparing'
    incomplete.write_text('Runtime preparation has not completed.\n', encoding='utf-8')
    try:
        subprocess.run([str(extractor),'x','-y','-o'+str(runtime),str(archive)],check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        application=runtime/'Chrome-bin'
        version=application/PRODUCT['chromium_version']
        if not version.is_dir():raise ValueError('Pinned Chromium version directory missing from archive')
        for path in application.rglob('*'):
            if path.is_symlink() or not path.resolve().is_relative_to(runtime):
                raise ValueError('Installer extraction contains a linked/outside path')
        for source in version.iterdir():
            target=application/source.name
            if target.exists():raise ValueError('Runtime flattening would overwrite a launcher file')
            if source.is_dir():shutil.copytree(source,target)
            else:shutil.copyfile(source,target)
        # A standalone launcher must not also find an installed-version tree.
        # Mixing the two layouts can start a browser whose renderers never reply.
        # Only remove this exact, newly extracted directory after checking that
        # its resolved absolute path remains inside our owned runtime wrapper.
        if version.resolve() != application.resolve() / PRODUCT['chromium_version'] or not version.resolve().is_relative_to(runtime):
            raise ValueError('Version directory is outside the owned runtime')
        shutil.rmtree(version)
        executable=application/'chrome.exe'
        if sha256(executable)!=report.get('files',{}).get('chrome.exe'):
            raise ValueError('Packaged launcher differs from the compiled product')
        for name in ('chrome.dll','resources.pak','tools/ciadpi.exe','tools/LICENSE-byeDPI.txt'):
            if not (application/name).is_file():raise ValueError('Packaged runtime dependency missing: '+name)
        acl_digest = configure_appcontainer(appcontainer_acl_script, application) if os.name == 'nt' else None
        files={path.relative_to(application).as_posix():sha256(path)
               for path in sorted(application.rglob('*')) if path.is_file()}
        result={'kind':'NATIVE_RUNTIME_FROM_EXACT_INSTALLER_ARCHIVE',
                'layout':'standalone_flat',
                'integration_commit':report['integration_commit'],'product':PRODUCT,
                'source_archive_sha256':sha256(archive),'files':files,
                'payload_fingerprint_sha256':hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                'appcontainer_read_execute_configured':os.name == 'nt',
                'appcontainer_acl_helper_sha256':acl_digest,'sandbox_disabled':False,
                'installer_executed':False,'runtime_verified':False,'release_approved':False}
        (runtime/'runtime-provenance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        incomplete.unlink()
    except Exception:
        # Preserve only this newly created copy for diagnostics. Without a
        # completed provenance record no runtime output is returned to CI.
        raise
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as output:
            output.write(f'chrome_exe={runtime / "Chrome-bin/chrome.exe"}\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--extractor',type=Path,required=True)
    parser.add_argument('--appcontainer-acl-script',type=Path)
    args=parser.parse_args()
    result=prepare(args.build,args.runtime,args.extractor,args.appcontainer_acl_script)
    print('Exact installer payload staged for runtime checks. Fingerprint:',result['payload_fingerprint_sha256'])
