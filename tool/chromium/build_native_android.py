"""Compile the prepared native Android product; never accesses production keys.

Source synchronization/hooks/patching are explicit earlier phases. This builder
will not repeat them over a staged product tree or reset unknown source edits.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import zipfile

try:
    from .prepare_windows import PRODUCT, ROOT
    from .prepare_android_product import product_path
    from .titanium_pin import SOURCE_SHA, VANADIUM_SHA
    from .titanium_product import PRODUCT_PACKAGE, verify_native_apk
    from .sign_candidate import parse_verified_certificate_sha256
except ImportError:
    from prepare_windows import PRODUCT, ROOT
    from prepare_android_product import product_path
    from titanium_pin import SOURCE_SHA, VANADIUM_SHA
    from titanium_product import PRODUCT_PACKAGE, verify_native_apk
    sys.path.insert(0, str(ROOT))
    from tool.chromium.sign_candidate import parse_verified_certificate_sha256

PHASE_RECORDS = ('source-preparation.json', 'titanium-patches.json',
                 'titanium-dependencies.json', 'titanium-hooks.json', 'titanium-upstream.json')
PRODUCT_OBJECTS = tuple('obj/chrome/browser/internet_browser/' + target + '/' + source + '.o'
    for target, source in (('transport', 'transport'), ('legacy_data', 'legacy_data'),
                          ('ui', 'internet_browser_ui'), ('video_player', 'video_player'),
                          ('video_player', 'video_subtitles'),
                          ('updater', 'updater'), ('video_library', 'video_downloads')))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def git(path: Path, *arguments: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(path), *arguments])


def head(path: Path) -> str:
    return git(path, 'rev-parse', 'HEAD').decode().strip()


def validate_source(workspace: Path, *, require_overlay: bool = True) -> dict:
    titanium = workspace / 'titanium'
    source = titanium / 'chromium/src'
    records = {name: json.loads((workspace / name).read_text(encoding='utf-8')) for name in PHASE_RECORDS}
    upstream = records['titanium-upstream.json']
    if (head(titanium) != SOURCE_SHA or head(titanium / 'vanadium') != VANADIUM_SHA or
        head(titanium / 'depot_tools') != PRODUCT['depot_tools_revision'] or
        head(source) != upstream['root_after_driver'] or
        upstream.get('chromium_base') != PRODUCT['chromium_revision'] or
        not upstream.get('hooks_run') or not upstream.get('upstream_driver_applied')):
        raise ValueError('Native Android prepared source pins/state differ')
    subprocess.run(['git', '-C', str(source), 'merge-base', '--is-ancestor',
                    PRODUCT['chromium_revision'], upstream['root_after_driver']], check=True)
    if git(titanium, 'diff', '--name-only').strip() or git(titanium, 'diff', '--cached', '--name-only').strip():
        raise ValueError('Titanium driver checkout contains tracked edits')
    for relative, record in upstream['driver_commits'].items():
        if relative == '.': continue
        repository = source / relative
        if head(repository) != record['head'] or git(repository, 'status', '--porcelain', '-uno').strip():
            raise ValueError('Prepared Android nested driver repository differs: ' + relative)
    for relative in ('v8', 'third_party/search_engines_data/resources'):
        repository = source / relative
        if head(repository) != upstream['subproject_inputs'][relative] or git(repository, 'status', '--porcelain', '-uno').strip():
            raise ValueError('Prepared Android hook repository differs: ' + relative)
    if sha256(titanium / 'patch.sh') != upstream['driver_sha256']:
        raise ValueError('Pinned Titanium patch driver changed')
    for name, digest in upstream['patches'].items():
        if Path(name).name != name or sha256(workspace / 'reviewed-vanadium-patches' / name) != digest:
            raise ValueError('Reviewed Vanadium patch bytes changed')
    stamp = source / '.internet-browser-android-overlay.json'
    overlay = json.loads(stamp.read_text(encoding='utf-8')) if stamp.exists() else None
    if require_overlay and not overlay:
        raise ValueError('Android product overlay has not been prepared')
    owned = set()
    if overlay:
        if overlay['source_revision'] != head(source) or overlay['product'] != PRODUCT:
            raise ValueError('Android overlay revision/product differs')
        for relative, digest in overlay['files'].items():
            if sha256(product_path(source, relative)) != digest:
                raise ValueError('Android product file changed: ' + relative)
            owned.add(relative)
    changed = {p.decode() for p in git(source, 'diff', '--name-only', '-z', 'HEAD').split(b'\0') if p}
    if changed - owned - {'v8', 'third_party/search_engines_data/resources'}:
        raise ValueError('Unknown tracked source edits; refusing to reset or compile them')
    return {'upstream': upstream, 'overlay': overlay, 'records': records}


def verify_payload(apk: Path, transport: Path, license_file: Path) -> None:
    with zipfile.ZipFile(apk) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate APK ZIP entry')
        payload = 'lib/arm64-v8a/libciadpi.so'
        if archive.getinfo(payload).file_size > 16 * 1024 * 1024 or archive.read(payload) != transport.read_bytes():
            raise ValueError('Packaged Android transport differs from the compiled payload')
        if archive.read('assets/licenses/ByeDPI.txt') != license_file.read_bytes():
            raise ValueError('Packaged Android transport license differs')
        engines = [name for name in names if name in ('lib/arm64-v8a/libchrome.so', 'lib/arm64-v8a/libmonochrome.so')]
        if len(engines) != 1:
            raise ValueError('Expected one actual ARM64 Chromium engine library')
        with archive.open(engines[0]) as stream:
            header = stream.read(20)
        if header[:6] != b'\x7fELF\x02\x01' or len(header) != 20 or struct.unpack_from('<HH', header, 16) != (3, 183):
            raise ValueError('APK Chromium library is not an ARM64 ELF shared object')


def build(workspace: Path, stage: Path, version_code: int, jobs: int,
          prepare_only: bool = False, product_objects_only: bool = False) -> dict:
    import fcntl
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
        raise ValueError('Native Android compilation requires Linux x64')
    if not 1 <= jobs <= 3 or not 1 <= version_code <= 2_100_000_000:
        raise ValueError('Expected jobs 1..3 and a valid release versionCode')
    workspace = workspace.resolve(strict=True)
    stage = stage.resolve()
    source = workspace / 'titanium/chromium/src'
    depot = workspace / 'titanium/depot_tools'
    if stage.is_relative_to(source):
        raise ValueError('Stage outputs must stay outside the Chromium source checkout')
    if (prepare_only or product_objects_only) and (stage / 'native-chromium.apk').exists():
        raise ValueError('A non-APK phase cannot reuse a stage containing a previous APK')
    with (workspace / '.native-android-build.lock').open('a+b') as build_lock:
        fcntl.flock(build_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        validate_source(workspace, require_overlay=False)
        if git(ROOT, 'status', '--porcelain').strip():
            raise ValueError('Integration checkout must be clean so provenance identifies the compiled source')
        env = os.environ.copy()
        env.update({'DEPOT_TOOLS_UPDATE': '0', 'DEPOT_TOOLS_METRICS': '0', 'DEPOT_TOOLS_BUILD_TELEMETRY': '0'})
        env['JAVA_HOME'] = str(source / 'third_party/jdk/current')
        env['PATH'] = str(depot) + os.pathsep + str(source / 'third_party/jdk/current/bin') + os.pathsep + env.get('PATH', '')
        def run(*arguments):
            subprocess.run([str(a) for a in arguments], env=env, cwd=source, check=True)
        # Only the exact recorded product overlay may be replaced. Source
        # synchronization/hooks are deliberately excluded from this phase.
        run(sys.executable, ROOT / 'tool/chromium/prepare_android_product.py', '--checkout', source, '--remove')
        run(sys.executable, ROOT / 'tool/chromium/build_android_transport.py', '--checkout', source,
            '--workspace', workspace / 'transport')
        run(sys.executable, ROOT / 'tool/chromium/prepare_android_product.py', '--checkout', source,
            '--transport', workspace / 'transport/libciadpi.so')
        run(sys.executable, ROOT / 'tool/chromium/generate_android.py', '--workspace', workspace,
            '--version-code', str(version_code))
        with (workspace / '.native-android-source.lock').open('a+b') as source_lock:
            fcntl.flock(source_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = validate_source(workspace)
            report = {'kind': 'NATIVE_ANDROID_SOURCE_BUILD_NOT_RUNTIME_ACCEPTANCE', 'product': PRODUCT,
                'integration_commit': head(ROOT), 'integration_tree': git(ROOT, 'rev-parse', 'HEAD^{tree}').decode().strip(),
                'source_revision': head(source), 'package': PRODUCT_PACKAGE, 'version_code': version_code,
                'source_validated': True, 'product_objects_compiled': False, 'compiled': False,
                'runtime_verified': False, 'device_verified': False, 'release_approved': False,
                'overlay': state['overlay'], 'upstream': state['upstream']}
            if not prepare_only:
                vpython = depot / '.cipd_bin/vpython3'
                run(vpython, depot / 'autoninja.py', '-C', 'out/InternetBrowserAndroid', '-j', str(jobs), *PRODUCT_OBJECTS)
                report['product_objects_compiled'] = True
                if not product_objects_only:
                    run(vpython, depot / 'autoninja.py', '-C', 'out/InternetBrowserAndroid', '-j', str(jobs), 'chrome_public_apk')
                    apk = source / 'out/InternetBrowserAndroid/apks/ChromePublic.apk'
                    tools = source / 'third_party/android_sdk/public/build-tools/37.0.0'
                    verify_native_apk(apk, tools / 'aapt2', PRODUCT_PACKAGE,
                                      version_code=version_code, version_name=PRODUCT['app_version'])
                    verify_payload(apk, workspace / 'transport/libciadpi.so', ROOT / 'third_party/byedpi/LICENSE')
                    signature = subprocess.check_output([str(tools / 'apksigner'), 'verify', '--verbose', '--print-certs', str(apk)], env=env, text=True)
                    report.update({'compiled': True, 'apk_sha256': sha256(apk),
                                   'development_certificate_sha256': parse_verified_certificate_sha256(signature),
                                   'production_signed': False})
                    stage.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(apk, stage / 'native-chromium.apk')
            stage.mkdir(parents=True, exist_ok=True)
            (stage / 'native-provenance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            for name in PHASE_RECORDS:
                (stage / 'source-records').mkdir(exist_ok=True)
                shutil.copyfile(workspace / name, stage / 'source-records' / name)
            shutil.copyfile(workspace / 'transport/transport-provenance.json', stage / 'transport-provenance.json')
            shutil.copyfile(workspace / 'transport/libciadpi.so', stage / 'libciadpi.so')
            print('Native Android phase complete. APK compilation:', report['compiled'], '; runtime/release acceptance remains required.', flush=True)
            return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--version-code', type=int, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument('--prepare-only', action='store_true')
    phase.add_argument('--product-objects-only', action='store_true')
    args = parser.parse_args()
    build(args.workspace, args.stage, args.version_code, args.jobs, args.prepare_only, args.product_objects_only)
