"""Identity/source safeguards for the native Windows Chromium migration."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tool.chromium.prepare_windows import (
    PRODUCT, brand_install_modes, brand_messages, brand_metadata, replace_once,
    overlay_path,
)


class NativeWindowsIdentityTests(unittest.TestCase):
    def test_product_names_change_without_claiming_chromium_copyright(self):
        original = ('PRODUCT_FULLNAME=Chromium\nPRODUCT_SHORTNAME=Chromium\n'
                    'PRODUCT_INSTALLER_FULLNAME=Chromium Installer\n'
                    'PRODUCT_INSTALLER_SHORTNAME=Chromium Installer\n'
                    'COPYRIGHT=The Chromium Authors\n')
        result = brand_metadata(original)
        self.assertIn('PRODUCT_FULLNAME=Internet Browser\n', result)
        self.assertIn('COPYRIGHT=The Chromium Authors\n', result)

    def test_unknown_or_ambiguous_upstream_anchor_fails_before_modification(self):
        for original in ('no known source', 'anchor anchor'):
            with self.assertRaises(ValueError):
                replace_once(original, 'anchor', 'replacement')

    def test_grd_fingerprints_and_placeholders_stay_valid(self):
        original = ('<grit><message name="IDS_PRODUCT_NAME" translateable="false">'
                    'Chromium</message><message name="IDS_NOTE">'
                    'Open Chromium <ph name="N">$1</ph></message></grit>')
        result = brand_messages(original)
        self.assertIn('>Internet Browser</message>', result)
        self.assertIn('Open Chromium <ph name="N">$1</ph>', result)

    def test_xtb_keeps_translation_ids_and_substitutions(self):
        original = ('<translationbundle><translation id="123">Chromium 설정 '
                    '<ph name="NAME"/></translation></translationbundle>')
        result = brand_messages(original, xtb=True)
        self.assertIn('id="123">Internet Browser 설정 <ph name="NAME"/>', result)

    def test_malformed_resources_are_rejected(self):
        with self.assertRaises(Exception):
            brand_messages('<grit><message>Chromium</message>')

    def test_runner_labels_do_not_consume_legacy_native_jobs(self):
        self.assertEqual(PRODUCT['android_runner_label'], 'chromium-wsl2')
        self.assertEqual(PRODUCT['windows_runner_label'], 'chromium-windows-v022')
        self.assertEqual(len(PRODUCT['chromium_revision']), 40)
        self.assertEqual(PRODUCT['required_adblock_id'],
                         'gighmmpiobklfepjocnamgkkbiglidom')

    def test_overlay_cleanup_cannot_escape_workspace_or_touch_unowned_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for relative in ('../important.txt', '/etc/passwd',
                             'chrome/browser/passwords.cc',
                             'chrome/browser/internet_browser/../../important.cc'):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    overlay_path(root, relative)
            self.assertEqual(overlay_path(root, 'chrome/browser/internet_browser/BUILD.gn'),
                             root / 'chrome/browser/internet_browser/BUILD.gn')


if __name__ == '__main__':
    unittest.main()
