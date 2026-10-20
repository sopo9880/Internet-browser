"""Brand text must preserve translations, markup and upstream attribution."""
import unittest

from tool.chromium.prepare_android_product import brand
from tool.chromium.titanium_product import prepare_source, PRODUCT_PACKAGE, RESEARCH_PACKAGE
from tool.tests.test_titanium_product import ARGS, BUILD, METADATA
from tool.chromium.prepare_android_hooks import configuration, HOOK_ACTION


class AndroidProductOverlayTests(unittest.TestCase):
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

    def test_overlay_is_fatal_and_runs_after_upstream_patches_before_gn(self):
        before = BUILD + 'gclient runhooks\nsource $SCRIPT_DIR/patch.sh\ngn gen out/Default\n'
        _, configured = prepare_source(ARGS, before, PRODUCT_PACKAGE,
                                       product_overlay=True, **METADATA)
        self.assertLess(configured.index('source $SCRIPT_DIR/patch.sh'),
                        configured.index('prepare_android_product.py'))
        self.assertLess(configured.index('prepare_android_product.py'),
                        configured.index('gn gen out/Default'))
        self.assertIn('set -e\n', configured)
        with self.assertRaises(ValueError):
            prepare_source(ARGS, before, RESEARCH_PACKAGE, product_overlay=True)


if __name__ == '__main__':
    unittest.main()
