// Injected into the main world of top-level YouTube documents at document
// start (chrome_content_renderer_client.cc, patched by
// tool/chromium/prepare_android_product.py). YouTube pauses its player when the
// page reports itself hidden; keep reporting "visible" so playback continues
// with the app in the background or the screen off, like the YouTube app.
// Chromium's own background-media suspend is disabled separately with
// --disable-background-media-suspend. Nothing else on the page is changed.
(() => {
  const define = (name, value) => {
    try {
      Object.defineProperty(Document.prototype, name, {configurable: true, enumerable: true, get: () => value});
    } catch {}
  };
  define('hidden', false);
  define('webkitHidden', false);
  define('visibilityState', 'visible');
  define('webkitVisibilityState', 'visible');
  const swallow = event => event.stopImmediatePropagation();
  for (const type of ['visibilitychange', 'webkitvisibilitychange']) {
    window.addEventListener(type, swallow, true);
  }
})();
