"""Runtime setup contracts with synthetic files; no program is executed."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from tool.chromium import prepare_windows_runtime as runtime


class RuntimePreparationTests(unittest.TestCase):
    def source(self, root):
        source = root / 'build'; source.mkdir()
        (source / 'chrome.7z').write_bytes(b'synthetic archive')
        report = {'native_source_compiled': True, 'product': runtime.PRODUCT,
                  'integration_commit': 'c' * 40,
                  'files': {'chrome.7z': runtime.sha256(source / 'chrome.7z'),
                            'chrome.exe': hashlib.sha256(b'synthetic launcher').hexdigest()}}
        (source / 'native-provenance.json').write_text(json.dumps(report))
        return source

    def extract(self, command, **kwargs):
        destination = Path(next(arg[2:] for arg in command if arg.startswith('-o')))
        application = destination / 'Chrome-bin'; application.mkdir()
        (application / 'chrome.exe').write_bytes(b'synthetic launcher')
        version = application / runtime.PRODUCT['chromium_version']; version.mkdir()
        for name in ('chrome.dll', 'resources.pak', 'tools/ciadpi.exe', 'tools/LICENSE-byeDPI.txt'):
            path = version / name; path.parent.mkdir(exist_ok=True)
            path.write_bytes(('synthetic ' + name).encode())

    def listing(self):
        return 'Path = Chrome-bin/chrome.exe\nPath = Chrome-bin/' + runtime.PRODUCT['chromium_version'] + '/chrome.dll\n'

    def test_runtime_wrapper_is_complete_without_directory_rename(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source = self.source(root); output = root / 'runtime'
            with patch.object(runtime.subprocess, 'check_output', return_value=self.listing()), \
                 patch.object(runtime.subprocess, 'run', side_effect=self.extract), \
                 patch.object(runtime, 'configure_appcontainer', return_value='a' * 64) as acl, \
                 patch.object(runtime.os, 'replace', side_effect=AssertionError('Directory rename is not allowed')):
                report = runtime.prepare(source, output, Path('fixture-extractor'), Path('fixture-acl-helper'))
            self.assertTrue((output / 'Chrome-bin/chrome.exe').is_file())
            self.assertTrue((output / 'Chrome-bin/tools/ciadpi.exe').is_file())
            self.assertFalse((output / 'Chrome-bin' / runtime.PRODUCT['chromium_version']).exists())
            self.assertEqual(report['layout'], 'standalone_flat')
            self.assertTrue((output / 'runtime-provenance.json').is_file())
            self.assertFalse((output / '.preparing').exists())
            self.assertFalse(report['sandbox_disabled'])
            self.assertEqual(report['files']['chrome.exe'], hashlib.sha256(b'synthetic launcher').hexdigest())
            if os.name == 'nt': acl.assert_called_once_with(Path('fixture-acl-helper'), output / 'Chrome-bin')
            else: acl.assert_not_called()

    def test_modified_archive_rejected_before_creating_runtime(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source = self.source(root); output = root / 'runtime'
            (source / 'chrome.7z').write_bytes(b'changed')
            with self.assertRaises(ValueError): runtime.prepare(source, output, Path('unused'))
            self.assertFalse(output.exists())

    def test_failed_extraction_cannot_emit_completed_provenance_or_overwrite(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); source = self.source(root); output = root / 'runtime'
            with patch.object(runtime.subprocess, 'check_output', return_value=self.listing()), \
                 patch.object(runtime.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'fixture')):
                with self.assertRaises(subprocess.CalledProcessError):
                    runtime.prepare(source, output, Path('fixture'), Path('fixture-helper'))
            self.assertTrue((output / '.preparing').exists())
            self.assertFalse((output / 'runtime-provenance.json').exists())
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                runtime.prepare(source, output, Path('unused'))

    def helpers(self, root):
        script = root / 'build/win/set_appcontainer_acls.py'
        common = root / 'testing/scripts/common.py'
        for path in (script, common): path.parent.mkdir(parents=True, exist_ok=True)
        script.write_bytes(b'synthetic helper'); common.write_bytes(b'synthetic common')
        return script, common

    def test_wrong_helper_revision_cannot_execute(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); script, _ = self.helpers(root)
            with patch.object(runtime.subprocess, 'check_output', return_value='f' * 40), \
                 patch.object(runtime.subprocess, 'run') as execute:
                with self.assertRaisesRegex(ValueError, 'revision'):
                    runtime.configure_appcontainer(script, root / 'owned-program')
                execute.assert_not_called()

    def test_changed_helper_cannot_execute(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); script, _ = self.helpers(root)
            with patch.object(runtime.subprocess, 'check_output', side_effect=[runtime.PRODUCT['chromium_revision'], b'original']), \
                 patch.object(runtime.subprocess, 'run') as execute:
                with self.assertRaisesRegex(ValueError, 'changed'):
                    runtime.configure_appcontainer(script, root / 'owned-program')
                execute.assert_not_called()

    def test_exact_pinned_helper_targets_only_the_owned_program_directory(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary); script, common = self.helpers(root); application = root / 'owned-program'
            with patch.object(runtime.subprocess, 'check_output', side_effect=[runtime.PRODUCT['chromium_revision'], script.read_bytes(), common.read_bytes()]), \
                 patch.object(runtime.subprocess, 'run') as execute:
                digest = runtime.configure_appcontainer(script, application)
            self.assertEqual(digest, runtime.sha256(script))
            execute.assert_called_once_with([sys.executable, str(script), '--dir', str(application)], check=True)


if __name__ == '__main__': unittest.main()
