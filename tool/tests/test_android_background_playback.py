"""Source patches that let YouTube keep playing with the Android app backgrounded."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'chromium'))
import prepare_android_product as product  # noqa: E402

# Verbatim anchors from Chromium 155.0.8059.84 (5869fe31).
RENDERER = '''#include "content/public/renderer/render_frame.h"

void ChromeContentRendererClient::RunScriptsAtDocumentStart(
    content::RenderFrame* render_frame) {
#if BUILDFLAG(ENABLE_EXTENSIONS_CORE)
  extensions::ExtensionsRendererClient::Get()->RunScriptsAtDocumentStart(
      render_frame);
  // |render_frame| might be dead by now.
#endif
}
'''
MAIN = '''#include "base/android/jni_android.h"
#include "content/public/common/main_function_params.h"

int ChromeBrowserMainPartsAndroid::PreEarlyInitialization() {
  content::Compositor::Initialize();
  return ChromeBrowserMainParts::PreEarlyInitialization();
}
'''


class BackgroundPlaybackPatchTest(unittest.TestCase):
    def test_renderer_injects_script_for_top_level_youtube_before_extensions(self):
        patched = product.youtube_background_renderer_source(RENDERER)
        injected = patched.index('render_frame->ExecuteJavaScript(uR"JS(')
        self.assertLess(injected, patched.index('ExtensionsRendererClient::Get()'))
        self.assertIn('render_frame->IsMainFrame()', patched)
        self.assertIn('url.SchemeIs("https")', patched)
        for host in ('www.youtube.com', 'm.youtube.com', 'youtube.com', 'music.youtube.com'):
            self.assertIn(f'url.host() == "{host}"', patched)
        script = (product.ROOT / 'native/chromium/android/resources/youtube_background.js').read_text()
        self.assertIn(script, patched)
        self.assertNotIn('evil', patched)

    def test_background_media_suspend_disabled_before_compositor_and_renderers(self):
        patched = product.background_media_main_source(MAIN)
        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('#include "media/base/media_switches.h"', patched)
        switch = patched.index('AppendSwitch(\n      switches::kDisableBackgroundMediaSuspend);')
        self.assertLess(switch, patched.index('content::Compositor::Initialize();'))

    def test_anchor_drift_fails_closed(self):
        with self.assertRaises(Exception):
            product.youtube_background_renderer_source(RENDERER.replace('RunScriptsAtDocumentStart(\n', 'Other(\n'))
        with self.assertRaises(Exception):
            product.background_media_main_source(MAIN.replace('Compositor::Initialize', 'Compositor::Start'))


if __name__ == '__main__':
    unittest.main()
