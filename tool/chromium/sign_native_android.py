"""Validate and sign the exact native Android build once on a trusted hosted job.

No build command is invoked here. Production secrets are read only by `sign`,
after source identity, package/version, payload and disposable signer checks.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from tool.configure_android_signing import decode_key
from tool.release_metadata import parse_pubspec, ReleaseMetadata
from tool.chromium.build_native_android import verify_payload, sha256
from tool.chromium.prepare_windows import PRODUCT, ROOT, resource_header
from tool.chromium.sign_candidate import PRODUCTION_CERT_SHA256, parse_verified_certificate_sha256
from tool.chromium.titanium_product import PRODUCT_PACKAGE, verify_native_apk
from tool.chromium.build_android_transport import REVISION, NDK_VERSION, LLVM_VERSION


def product_hashes(transport_sha256: str) -> dict[str, str]:
    expected = {'resources.h': hashlib.sha256(resource_header(android=True)).hexdigest(),
                'libciadpi.so': transport_sha256,
                'LICENSE-byeDPI.txt': sha256(ROOT / 'third_party/byedpi/LICENSE')}
    for name in ('internet_browser_ui.cc', 'internet_browser_ui.h', 'transport.h', 'legacy_data.h'):
        expected[name] = sha256(ROOT / 'native/chromium/windows/overlay' / name)
    for directory in ('common', 'android'):
        for path in (ROOT / f'native/chromium/{directory}/overlay').iterdir():
            if path.is_file(): expected[path.name] = sha256(path)
    return expected


def validate_report(report: dict, transport: dict, *, commit: str, tree: str,
                    version: str, version_code: int) -> None:
    if (report.get('kind') != 'NATIVE_ANDROID_SOURCE_BUILD_NOT_RUNTIME_ACCEPTANCE' or
        report.get('compiled') is not True or report.get('product_objects_compiled') is not True or
        report.get('source_validated') is not True or report.get('production_signed') is not False or
        report.get('integration_commit') != commit or report.get('integration_tree') != tree or
        report.get('product') != PRODUCT or version != PRODUCT['app_version'] or
        report.get('version_code') != version_code or report.get('package') != PRODUCT_PACKAGE):
        raise ValueError('Native Android source build identity/version does not match the release checkout')
    upstream = report.get('upstream', {})
    overlay = report.get('overlay', {})
    if (not upstream.get('upstream_driver_applied') or
        upstream.get('chromium_base') != PRODUCT['chromium_revision'] or
        report.get('source_revision') != upstream.get('root_after_driver') or
        overlay.get('source_revision') != report.get('source_revision') or overlay.get('product') != PRODUCT):
        raise ValueError('Native Android source/overlay provenance differs')
    if (transport.get('compiled') is not True or transport.get('source_revision') != REVISION or
        transport.get('ndk_version') != NDK_VERSION or transport.get('llvm_revision') != LLVM_VERSION or
        not re.fullmatch(r'[a-f0-9]{64}', transport.get('sha256', ''))):
        raise ValueError('Native Android transport build identity differs')
    expected = product_hashes(transport['sha256'])
    actual = overlay.get('files', {})
    for name, digest in expected.items():
        if actual.get('chrome/browser/internet_browser/' + name) != digest:
            raise ValueError('Compiled native Android product source differs: ' + name)


def signing_entries(apk: Path) -> dict[str, str]:
    result = {}
    seen = set()
    with zipfile.ZipFile(apk) as archive:
        for entry in archive.infolist():
            name = entry.filename
            if name in seen: raise ValueError('Duplicate APK ZIP entry')
            seen.add(name)
            if entry.is_dir(): continue
            if name.upper() == 'META-INF/MANIFEST.MF' or re.fullmatch(r'META-INF/[^/]+\.(?:SF|RSA|DSA|EC)', name, re.I):
                continue
            digest = hashlib.sha256()
            with archive.open(entry) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):digest.update(block)
            result[name] = digest.hexdigest()
    return result


def command(program: Path | str, *args: str, env: dict | None = None) -> str:
    completed = subprocess.run([str(program), *map(str, args)], env=env,
                               capture_output=True, text=True)
    if completed.returncode:
        # Key aliases, passwords and certificate subject names must not be
        # included in exception logs or command echoes.
        raise RuntimeError(Path(program).name + ' failed; check the tool, input file and signing configuration')
    return completed.stdout


def verify_source(source: Path, aapt2: Path, apksigner: Path) -> tuple[dict, ReleaseMetadata]:
    metadata = parse_pubspec((ROOT / 'pubspec.yaml').read_text(encoding='utf-8'))
    report = json.loads((source / 'native-provenance.json').read_text(encoding='utf-8'))
    transport = json.loads((source / 'transport-provenance.json').read_text(encoding='utf-8'))
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    tree = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    validate_report(report, transport, commit=commit, tree=tree,
                    version=metadata.version, version_code=metadata.version_code)
    apk = source / 'native-chromium.apk'
    payload = source / 'libciadpi.so'
    if sha256(apk) != report.get('apk_sha256') or sha256(payload) != transport['sha256']:
        raise ValueError('Native Android artifact bytes differ from build provenance')
    verify_native_apk(apk, aapt2, PRODUCT_PACKAGE,
                      version_code=metadata.version_code, version_name=metadata.version)
    verify_payload(apk, payload, ROOT / 'third_party/byedpi/LICENSE')
    certificate = parse_verified_certificate_sha256(command(apksigner, 'verify', '--verbose', '--print-certs', str(apk)))
    if certificate == PRODUCTION_CERT_SHA256 or certificate != report.get('development_certificate_sha256'):
        raise ValueError('Source must retain its recorded disposable certificate before production signing')
    return report, metadata


def require_hosted_main(env: dict[str, str], commit: str) -> None:
    if (env.get('GITHUB_ACTIONS') != 'true' or env.get('GITHUB_REF') != 'refs/heads/main' or
        env.get('GITHUB_EVENT_NAME') not in ('push', 'workflow_dispatch') or
        env.get('RUNNER_ENVIRONMENT') != 'github-hosted' or env.get('GITHUB_SHA') != commit):
        raise ValueError('Production signing requires the matching main-branch commit on a trusted GitHub-hosted job')


def sign(source: Path, output: Path, aapt2: Path, apksigner: Path, zipalign: Path,
         env: dict[str, str]) -> dict:
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    require_hosted_main(env, commit)
    report, metadata = verify_source(source, aapt2, apksigner)
    required = ('ANDROID_KEYSTORE_BASE64', 'ANDROID_KEYSTORE_PASSWORD', 'ANDROID_KEY_ALIAS', 'ANDROID_KEY_PASSWORD', 'RUNNER_TEMP')
    if any(not env.get(name) for name in required):
        raise ValueError('Existing production signing secrets and RUNNER_TEMP are required')
    target = output / f'Internet-browser-Android-v{metadata.version}.apk'
    if target.exists(): raise ValueError('Refusing to sign over an existing release APK')
    original_entries = signing_entries(source / 'native-chromium.apk')
    # Nothing above this line decodes or writes private key material.
    key_bytes = decode_key(env['ANDROID_KEYSTORE_BASE64'])
    child_env = dict(env)
    child_env.pop('ANDROID_KEYSTORE_BASE64', None)
    with tempfile.TemporaryDirectory(prefix='internet-browser-sign-', dir=env['RUNNER_TEMP']) as temporary:
        temporary = Path(temporary)
        key = temporary / 'release.p12'
        descriptor = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:stream.write(key_bytes)
        del key_bytes
        aligned = temporary / 'aligned.apk'
        signed = temporary / 'signed.apk'
        listing = command('keytool', '-list', '-storetype', 'PKCS12', '-keystore', str(key),
                          '-storepass:env', 'ANDROID_KEYSTORE_PASSWORD', '-alias', env['ANDROID_KEY_ALIAS'], env=child_env)
        if 'PrivateKeyEntry' not in listing: raise ValueError('The configured alias has no private signing key')
        command(zipalign, '-f', '-P', '16', '4', str(source / 'native-chromium.apk'), str(aligned), env=child_env)
        command(apksigner, 'sign', '--ks', str(key), '--ks-type', 'PKCS12',
                '--ks-key-alias', env['ANDROID_KEY_ALIAS'], '--ks-pass', 'env:ANDROID_KEYSTORE_PASSWORD',
                '--key-pass', 'env:ANDROID_KEY_PASSWORD', '--out', str(signed), str(aligned), env=child_env)
        command(zipalign, '-c', '-P', '16', '4', str(signed), env=child_env)
        certificate = parse_verified_certificate_sha256(command(apksigner, 'verify', '--verbose', '--print-certs', str(signed), env=child_env))
        if certificate != PRODUCTION_CERT_SHA256:
            raise ValueError('Production APK certificate does not match the original published application')
        verify_native_apk(signed, aapt2, PRODUCT_PACKAGE,
                          version_code=metadata.version_code, version_name=metadata.version)
        if signing_entries(signed) != original_entries:
            raise ValueError('Signing modified compiled APK payload entries')
        signed_digest = sha256(signed)
        final = {'kind': 'PRODUCTION_SIGNED_NATIVE_ANDROID_BUILD', 'version': metadata.version,
                 'version_code': metadata.version_code, 'package': PRODUCT_PACKAGE,
                 'integration_commit': commit, 'integration_tree': report['integration_tree'],
                 'source_apk_sha256': report['apk_sha256'], 'signed_apk_sha256': signed_digest,
                 'release_certificate_sha256': certificate, 'github_run_id': env.get('GITHUB_RUN_ID'),
                 'compiled': True, 'production_signed': True, 'runtime_verified': False,
                 'device_verified': False, 'release_approved': False}
        output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(signed, target)
        (output / 'android-release-provenance.json').write_text(json.dumps(final, indent=2) + '\n', encoding='utf-8')
    return final

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('check-source', 'sign'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--aapt2', type=Path, required=True)
    parser.add_argument('--apksigner', type=Path, required=True)
    parser.add_argument('--zipalign', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'check-source':
        report, metadata = verify_source(args.source, args.aapt2, args.apksigner)
        print('Native APK source verified for', metadata.tag, '; production keys were not accessed.')
    else:
        if not args.zipalign or not args.output:parser.error('sign requires --zipalign and --output')
        result = sign(args.source, args.output, args.aapt2, args.apksigner, args.zipalign, dict(os.environ))
        print('Native APK signed and verified; temporary keystore removed. SHA-256:', result['signed_apk_sha256'])
