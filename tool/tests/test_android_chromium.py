"""Brand text must preserve translations, markup and upstream attribution."""
import unittest

from tool.chromium.prepare_android_product import brand
from tool.chromium.titanium_product import prepare_source, PRODUCT_PACKAGE, RESEARCH_PACKAGE
from tool.tests.test_titanium_product import ARGS, BUILD, METADATA


class AndroidProductOverlayTests(unittest.TestCase):
    def test_branding_preserves_license_and_placeholder_identity(self):
        original = ('<grit><message name="A">Titanium 설정 <ph name="N">$1</ph></message>'
                    '<message name="C">Copyright The Chromium Authors</message></grit>')
        result = brand(original)
        self.assertIn('Internet Browser 설정 <ph name="N">$1</ph>', result)
        self.assertIn('Copyright The Chromium Authors', result)
        self.assertIn('Internet Browser에서는', brand(
            '<translationbundle><translation id="1">Titanium에서는</translation></translationbundle>', xtb=True))

    def test_overlay_is_fatal_and_runs_after_upstream_patches_before_gn(self):
        before = BUILD + 'source $SCRIPT_DIR/patch.sh\ngn gen out/Default\n'
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
