"""Identity/source safeguards for the native Windows Chromium migration."""
import unittest
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from tool.chromium.prepare_windows import (
    PRODUCT, brand_install_modes, brand_messages, brand_metadata, replace_once,
    overlay_path,
    remap_translation_ids,
    native_source_bytes,
)


class NativeWindowsIdentityTests(unittest.TestCase):
    def test_per_user_shell_progids_fit_windows_39_character_limit(self):
        upstream = '\n'.join((
            'kProductPathName[] = L"Chromium"',
            '.base_app_name = L"Chromium"',
            '.base_app_id = L"Chromium"',
            '.browser_prog_id_prefix = L"ChromiumHTM"',
            'L"Chromium HTML Document"',
            '.direct_launch_url_scheme = "chromium"',
            '.pdf_prog_id_prefix = L"ChromiumPDF"',
            'L"Chromium PDF Document"',
            'L"{7D2B3E1D-D096-4594-9D8F-A6667F12E0AC}"',
        ))
        branded = brand_install_modes(upstream)
        prefixes = re.findall(r'\.(?:browser|pdf)_prog_id_prefix = L"([^"]+)"', branded)
        self.assertEqual(len(prefixes), 2)
        # Chromium appends a dot and the 26-character Base32 MD5 user suffix.
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                self.assertLessEqual(len(prefix + '.' + 'A' * 26), 39)
                self.assertNotIn(prefix, ('ChromeHTML', 'ChromePDF', 'ChromiumHTM', 'ChromiumPDF'))
        self.assertIn('kProductPathName[] = L"Internet Browser"', branded)
        self.assertIn('.base_app_id = L"InternetBrowser"', branded)

    def test_overlay_source_bytes_match_in_cached_crlf_and_fresh_lf_checkouts(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'source.cc'
            path.write_bytes('// 한글\r\nint main() {}\r\n'.encode())
            canonical = native_source_bytes(path)
            self.assertEqual(canonical, '// 한글\nint main() {}\n'.encode())
            path.write_bytes(canonical)
            self.assertEqual(native_source_bytes(path), canonical)

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

    def test_english_branding_keeps_placeholders_valid(self):
        original = ('<grit><message name="IDS_PRODUCT_NAME" translateable="false">'
                    'Chromium</message><message name="IDS_NOTE">'
                    'Open Chromium <ph name="N">$1</ph></message></grit>')
        result = brand_messages(original)
        self.assertIn('>Internet Browser</message>', result)
        self.assertIn('Open Internet Browser <ph name="N">$1</ph>', result)

    def test_xtb_keeps_translation_ids_and_substitutions(self):
        original = ('<translationbundle><translation id="123">Chromium 설정 '
                    '<ph name="NAME"/></translation></translationbundle>')
        result = brand_messages(original, xtb=True)
        self.assertIn('id="123">Internet Browser 설정 <ph name="NAME"/>', result)

    def test_korean_suffixes_do_not_hide_old_branding(self):
        original = '<translationbundle><translation id="123">Chromium의 Chromium에서</translation></translationbundle>'
        result = brand_messages(original, xtb=True)
        self.assertIn('Internet Browser의 Internet Browser에서', result)

    def test_translation_fingerprints_are_remapped_without_touching_other_ids(self):
        original = '<translationbundle><translation id="123">Chromium</translation><translation id="456">Other</translation></translationbundle>'
        result = remap_translation_ids(original, {'123': '789'})
        self.assertIn('id="789">Chromium', result)
        self.assertIn('id="456">Other', result)

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
