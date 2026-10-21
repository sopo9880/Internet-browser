"""Release staging contracts with synthetic files; no binaries execute or publish."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tool.release_metadata import parse_pubspec
from tool.chromium import stage_native_release as staging

COMMIT = 'c' * 40
TREE = 'b' * 40
RUN_ID = 44
METADATA = parse_pubspec('version: 0.2.2+1\n')


class NativeReleaseStageTests(unittest.TestCase):
    def origin(self):
        run = {'id': RUN_ID, 'head_sha': COMMIT, 'head_branch': 'main',
               'event': 'workflow_dispatch', 'status': 'completed', 'conclusion': 'success',
               'path': staging.WORKFLOW, 'repository': {'id': staging.REPO_ID},
               'head_repository': {'id': staging.REPO_ID}}
        artifacts = [{'id': index, 'name': name, 'expired': False, 'size_in_bytes': 123,
                      'digest': 'sha256:' + str(index) * 64,
                      'workflow_run': {'id': RUN_ID, 'head_sha': COMMIT, 'head_branch': 'main',
                                       'repository_id': staging.REPO_ID, 'head_repository_id': staging.REPO_ID}}
                     for index, name in enumerate(staging.ARTIFACTS.values(), 1)]
        return run, {'total_count': len(artifacts), 'artifacts': artifacts}

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def windows(self, directory):
        directory.mkdir()
        (directory / 'mini_installer.exe').write_bytes(b'synthetic installer; never executed')
        (directory / 'chrome.7z').write_bytes(b'synthetic archive; never extracted')
        files = {name: staging.sha256(directory / name) for name in ('mini_installer.exe', 'chrome.7z')}
        files['chrome.exe'] = 'e' * 64
        report = {'native_source_compiled': True, 'product': staging.PRODUCT,
                  'source_revision': staging.PRODUCT['chromium_revision'],
                  'integration_commit': COMMIT, 'integration_tree': TREE, 'files': files,
                  'overlay': {'product': staging.PRODUCT,
                              'files': {'chrome/browser/internet_browser/' + name: value
                                        for name, value in staging.windows_product_hashes().items()}}}
        self.write(directory / 'native-provenance.json', report)
        payload = {'chrome.exe': files['chrome.exe'], 'chrome.dll': 'd' * 64}
        runtime = {'kind': 'NATIVE_RUNTIME_FROM_EXACT_INSTALLER_ARCHIVE', 'product': staging.PRODUCT,
                   'layout': 'standalone_flat',
                   'appcontainer_read_execute_configured': True, 'sandbox_disabled': False,
                   'appcontainer_acl_helper_sha256': 'a' * 64,
                   'integration_commit': COMMIT, 'source_archive_sha256': files['chrome.7z'],
                   'files': payload, 'payload_fingerprint_sha256': hashlib.sha256(
                       json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}
        self.write(directory / 'runtime-provenance.json', runtime)
        smoke = {'kind': 'NATIVE_WINDOWS_CONTROLLED_FIXTURE_SMOKE', 'chrome_exe_sha256': files['chrome.exe'],
                 'checks': dict.fromkeys(staging.SMOKE_CHECKS, True),
                 'real_adblock_id_verified': False, 'release_approved': False}
        self.write(directory / 'windows-smoke.json', smoke)
        return report, runtime, smoke

    def android(self, directory):
        directory.mkdir()
        apk = directory / f'Internet-browser-Android-v{METADATA.version}.apk'
        apk.write_bytes(b'synthetic apk; never installed')
        report = {'kind': 'PRODUCTION_SIGNED_NATIVE_ANDROID_BUILD', 'version': METADATA.version,
                  'version_code': METADATA.version_code, 'package': staging.PRODUCT_PACKAGE,
                  'integration_commit': COMMIT, 'integration_tree': TREE,
                  'compiled': True, 'production_signed': True, 'release_approved': False,
                  'release_certificate_sha256': staging.PRODUCTION_CERT_SHA256,
                  'github_run_id': str(RUN_ID), 'source_apk_sha256': 'a' * 64,
                  'signed_apk_sha256': staging.sha256(apk)}
        self.write(directory / 'android-release-provenance.json', report)
        return report

    def signer(self, certificate=None):
        return 'Number of signers: 1\nSigner #1 certificate SHA-256 digest: ' + (certificate or staging.PRODUCTION_CERT_SHA256) + '\n'

    def test_selects_exact_distinct_immutable_artifact_ids(self):
        selection = staging.select_artifacts(*self.origin(), COMMIT, RUN_ID)
        self.assertEqual(selection['artifacts']['windows']['id'], 1)
        self.assertEqual(selection['artifacts']['android']['id'], 2)

    def test_rejects_wrong_run_branch_commit_workflow_and_repository(self):
        for field, value in [('id', 45), ('head_sha', 'a' * 40), ('head_branch', 'feature'),
                             ('event', 'pull_request'), ('status', 'in_progress'),
                             ('conclusion', 'failure'), ('path', '.github/workflows/ci.yml'),
                             ('repository', {'id': 1}), ('head_repository', {'id': 1})]:
            run, artifacts = self.origin(); run[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                staging.select_artifacts(run, artifacts, COMMIT, RUN_ID)

    def test_rejects_expired_unhashed_foreign_duplicate_or_incomplete_artifacts(self):
        for case in ('expired', 'digest', 'foreign', 'duplicate', 'missing', 'pagination'):
            run, listing = self.origin()
            artifact = listing['artifacts'][0]
            if case == 'expired': artifact['expired'] = True
            if case == 'digest': artifact['digest'] = ''
            if case == 'foreign': artifact['workflow_run']['head_sha'] = 'f' * 40
            if case == 'duplicate': listing['artifacts'].append(deepcopy(artifact)); listing['total_count'] += 1
            if case == 'missing': listing['artifacts'].pop(); listing['total_count'] -= 1
            if case == 'pagination': listing['total_count'] += 1
            with self.subTest(case=case), self.assertRaises(ValueError):
                staging.select_artifacts(run, listing, COMMIT, RUN_ID)

    def test_windows_rejects_changed_bytes_source_overlay_runtime_or_failed_smoke(self):
        for case in ('bytes', 'tree', 'source', 'overlay', 'runtime', 'sandbox', 'acl', 'smoke', 'empty-smoke', 'other-exe'):
            with self.subTest(case=case), TemporaryDirectory() as temporary:
                directory = Path(temporary) / 'windows'
                report, runtime, smoke = self.windows(directory)
                if case == 'bytes': (directory / 'mini_installer.exe').write_bytes(b'changed')
                if case == 'tree': report['integration_tree'] = 'f' * 40
                if case == 'source': report['source_revision'] = 'f' * 40
                if case == 'overlay': report['overlay']['files'].clear()
                if case == 'runtime': runtime['source_archive_sha256'] = 'f' * 64
                if case == 'sandbox': runtime['sandbox_disabled'] = True
                if case == 'acl': runtime['appcontainer_read_execute_configured'] = False
                if case == 'smoke': smoke['checks']['native_browser_started'] = False
                if case == 'empty-smoke': smoke['checks'].clear()
                if case == 'other-exe': smoke['chrome_exe_sha256'] = 'f' * 64
                self.write(directory / 'native-provenance.json', report)
                self.write(directory / 'runtime-provenance.json', runtime)
                self.write(directory / 'windows-smoke.json', smoke)
                with self.assertRaises(ValueError): staging.validate_windows(directory, COMMIT, TREE)

    def test_windows_accepts_actual_overlay_marker_shape(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'windows'
            report, _, _ = self.windows(directory)
            # prepare_windows records its pin inside product, unlike the Android marker.
            self.assertNotIn('source_revision', report['overlay'])
            self.assertEqual(staging.validate_windows(directory, COMMIT, TREE), report)

    @patch.object(staging, 'verify_native_apk')
    def test_android_rechecks_actual_signature_after_payload_hash(self, verify):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'android'
            self.android(directory)
            with patch.object(staging, 'command', return_value=self.signer('f' * 64)):
                with self.assertRaisesRegex(ValueError, 'signature'):
                    staging.validate_android(directory, METADATA, COMMIT, TREE, RUN_ID, Path('aapt2'), Path('apksigner'))
            verify.assert_called_once()

    @patch.object(staging, 'verify_native_apk')
    def test_android_rejects_modified_apk_before_running_tools(self, verify):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'android'
            self.android(directory)
            (directory / f'Internet-browser-Android-v{METADATA.version}.apk').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'bytes'):
                staging.validate_android(directory, METADATA, COMMIT, TREE, RUN_ID, Path('aapt2'), Path('apksigner'))
            verify.assert_not_called()

    @patch.object(staging, 'verify_native_apk')
    def test_stages_unchanged_files_with_checksums_without_claiming_release_acceptance(self, verify):
        with TemporaryDirectory() as temporary, patch.object(staging, 'command', return_value=self.signer()):
            root = Path(temporary); windows = root / 'windows'; android = root / 'android'; output = root / 'dist'
            self.windows(windows); self.android(android)
            selection = staging.select_artifacts(*self.origin(), COMMIT, RUN_ID)
            manifest = staging.stage(windows, android, output, selection, METADATA, COMMIT, TREE, Path('aapt2'), Path('apksigner'))
            self.assertFalse(manifest['release_approved']); self.assertFalse(manifest['published'])
            source_inputs = json.loads((output / 'native-source-inputs.json').read_text())
            self.assertEqual(source_inputs['integration_commit'], COMMIT)
            self.assertFalse(source_inputs['complete_corresponding_source_included'])
            for notice in source_inputs['upstream_notices']:
                self.assertEqual(staging.sha256(output / ('upstream-' + notice['file'])), notice['sha256'])
            self.assertEqual((windows / 'mini_installer.exe').read_bytes(), (output / 'Internet-browser-Windows-Setup-v0.2.2.exe').read_bytes())
            for line in (output / 'SHA256SUMS.txt').read_text().splitlines():
                digest, name = line.split('  ', 1)
                self.assertEqual(digest, staging.sha256(output / name))
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                staging.stage(windows, android, output, selection, METADATA, COMMIT, TREE, Path('aapt2'), Path('apksigner'))
            self.assertTrue((windows / 'mini_installer.exe').exists())
            verify.assert_called_once()


if __name__ == '__main__': unittest.main()
