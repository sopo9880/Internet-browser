"""Brand text must preserve translations, markup and upstream attribution."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tool.chromium.prepare_android_product import brand, brand_launcher_names, product_path
from tool.chromium.titanium_product import prepare_source, PRODUCT_PACKAGE, RESEARCH_PACKAGE
from tool.tests.test_titanium_product import ARGS, BUILD, METADATA
from tool.chromium.prepare_android_hooks import configuration, HOOK_ACTION
from tool.chromium.prepare_titanium_patches import branded_patch, selected


class AndroidProductOverlayTests(unittest.TestCase):
    def test_product_cleanup_cannot_escape_or_touch_unrelated_sources(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for path in ('../outside.cc', '/etc/passwd', 'chrome/browser/passwords.cc',
                         'chrome/../../outside.grd', 'chrome\\app\\outside.grd'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    product_path(root, path)
            self.assertEqual(product_path(root, 'chrome/browser/internet_browser/transport.cc'),
                             root / 'chrome/browser/internet_browser/transport.cc')

    def test_patch_branding_preserves_original_attribution(self):
        data = b'+// Copyright The Vanadium Authors\n+class VanadiumConfig {}\n'
        result = branded_patch(data)
        self.assertIn(b'Copyright The Vanadium Authors', result)
        self.assertIn(b'class TitaniumConfig', result)
        self.assertFalse(selected('0010-trichrome-apk-build-targets.patch'))
        self.assertFalse(selected('0020-add-config-app-parsing.patch'))
        self.assertTrue(selected('0004-Vanadium-branding.patch'))

    def test_product_hooks_cannot_execute_configuration_code_or_fetch_latest_crx(self):
        config = {'solutions': [], 'target_os': ['android'], 'hooks': [
            {'name': 'fetch_titanium_extension', 'action': HOOK_ACTION},
            {'name': 'apply_subprojects_patches', 'action': ['python3', 'pinned.py']}]}
        text = '\n'.join(f'{name} = {value!r}' for name, value in config.items())
        result = configuration(text)
        self.assertEqual([h['name'] for h in result['hooks']], ['apply_subprojects_patches'])
        with self.assertRaises(ValueError):
            configuration(text + '\nprint("unexpected execution")')
        with self.assertRaises(ValueError):
            configuration(text.replace('titanium.crx', 'different.crx'))

    def test_branding_preserves_license_and_placeholder_identity(self):
        original = ('<grit><message name="A">Titanium 설정 <ph name="N">$1</ph></message>'
                    '<message name="C">Copyright The Chromium Authors</message></grit>')
        result = brand(original)
        self.assertIn('Internet Browser 설정 <ph name="N">$1</ph>', result)
        self.assertIn('Copyright The Chromium Authors', result)
        self.assertIn('Internet Browser에서는', brand(
            '<translationbundle><translation id="1">Titanium에서는</translation></translationbundle>', xtb=True))

    def test_launcher_strings_preserve_notices_and_reject_upstream_drift(self):
        original = ('<resources><!-- Copyright The Titanium Authors -->'
                    '<string name="app_name" translatable="false">Titanium</string>'
                    '<string name="bookmark_widget_title">Titanium bookmarks</string>'
                    '<string name="search_widget_title">Titanium search</string>'
                    '<string name="quick_action_search_widget_title">Titanium quick action search</string>'
                    '</resources>')
        result = brand_launcher_names(original)
        self.assertIn('Copyright The Titanium Authors', result)
        self.assertIn('translatable="false">Internet Browser</string>', result)
        self.assertIn('Internet Browser quick action search</string>', result)
        for changed in (original.replace('>Titanium</string>', '>Changed</string>'),
                        original.replace('name="app_name"', 'name="other"')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                brand_launcher_names(changed)

    def test_overlay_is_fatal_and_runs_after_upstream_patches_before_gn(self):
        before = (BUILD + '# https://grapheneos.org/build#browser-and-webview\n'
                  'rm unsafe-upstream-patch-directory\n'
                  'git am --whitespace=nowarn --keep-non-patch $SCRIPT_DIR/vanadium/patches/*.patch\n'
                  'gclient runhooks\nsource $SCRIPT_DIR/patch.sh\ngn gen out/Default\n')
        _, configured = prepare_source(ARGS, before, PRODUCT_PACKAGE,
                                       product_overlay=True, **METADATA)
        self.assertLess(configured.index('source $SCRIPT_DIR/patch.sh'),
                        configured.index('prepare_android_product.py'))
        self.assertLess(configured.index('prepare_android_product.py'),
                        configured.index('gn gen out/Default'))
        self.assertIn('set -e\n', configured)
        self.assertNotIn('rm unsafe-upstream-patch-directory', configured)
        self.assertIn('prepare_titanium_patches.py', configured)
        with self.assertRaises(ValueError):
            prepare_source(ARGS, before, RESEARCH_PACKAGE, product_overlay=True)


if __name__ == '__main__':
    unittest.main()
