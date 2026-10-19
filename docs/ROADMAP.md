# Development roadmap

## v0.1.0: browser foundation
Tabbed browsing, history/bookmarks, Android and Windows builds, basic ad-host rules, permitted direct-media downloads.

## v0.1.1: partial DPI transport integration
Windows: pinned verified ByeDPI native proxy and WebView2 startup configuration. Android: connect WebView to an external local SOCKS5 proxy, not a bundled VPN service. Verify real website access, DNS/QUIC and device behavior before calling DPI fully supported.

## Next: comprehensive ad filtering
v0.1.1 adds best-effort visible YouTube skip button handling. Continue toward rule-list parsing, signed/updateable lists, cosmetic rule handling, per-site configuration and regression tests; YouTube server-inserted ads are not guaranteed.

## v0.1.1: permitted media streams, next: advanced library
The browser saves allowed YouTube muxed audio+video streams with a user confirmation. Future work: high-quality audio/video muxing, permitted HLS/DASH, pause/resume, background notifications and offline in-app playback. Never defeat DRM.

## Release gates
Build both EXE bundle and APK against the same SHA, verify on real devices, and require explicit confirmation before PR merge or release.


## v0.2.0 (combined): in-app video library, native DPI and Chrome extensions

- User-configurable Windows and Android DPI argument presets with allowlisted flags.
- Android NDK-builds bundled ByeDPI engine for app-scoped SOCKS5; real-device verification and WebView compatibility remain required.
- Preserve all existing downloads while adding video page metadata, original title, thumbnails, playback position and local player.
- MediaKit offline player on Windows/Android: shortcuts, ±10s, hold 2×, subtitles, media tracks, background playback and Android system PiP. Some YouTube-specific online behaviors and protected streams are deliberately unavailable.


### Android Chromium and required Chrome AdBlock (release blocker)

- Reuse v0.1.2 code and existing PR; do not publish an intermediate v0.1.2.
- Replace Android WebView with an extension-capable, maintained Chromium
  engine. Kiwi Browser's archived source is reference material only.
- Required extension ID: gighmmpiobklfepjocnamgkkbiglidom.
- Must load that extension's Manifest V3 service worker and
  declarativeNetRequest rules, prompt for permissions and show the action
  popup; installation/updates must survive restarts.
- Test genuine ad blocking on a physical Android device, not just an icon,
  built-in filter or Chromium feature flag; verify original DPI/media
  functionality after migration.
- CI and release must remain blocked until this gate passes. The initially
  integrated Flutter WebView interface is a clearly labeled placeholder.


## Chromium-first priority order

1. Build a modern upstream Android Chromium baseline on a dedicated runner,
   then port an in-app native embedder with Chrome MV3 extensions.
2. Verify actual installation and network blocking by Chrome Web Store
   AdBlock gighmmpiobklfepjocnamgkkbiglidom.
3. Reconnect native Chromium to ByeDPI, navigation, downloads and offline
   video metadata; protect existing app data, Android signing and Windows.
4. Run the integrated device test suite and only then release v0.2.0.

The Android development app now deliberately blocks WebView fallback while
Chromium is not linked. A stock Chromium APK or build script does not pass
the mandatory AdBlock device test.


## Real Chromium Android extension source (October 2026 research phase)

The source/build path now pins Chromium 155-based Titanium and its
Vanadium revision for an actual extension-capable Android prototype.
Unlike stock ChromePublic.apk, the pinned fork documents Chrome Web
Store extension installation. However its build still produces a
standalone APK, not an embedded Flutter engine. See
docs/CHROMIUM_NATIVE_BUILD.md for runner requirements and limitations.
The prototype APK never replaces signed v0.1.1 and cannot satisfy
v0.2.0's AdBlock device acceptance gate on its own.

## v0.2.1 recovery development — HOLD RELEASE UNTIL NATIVE BROWSER WORKS

The published v0.2.0 Android app is NOT a usable Chromium browser. The
native Chromium engine never shipped: a successful Flutter APK build
was incorrectly treated as a completed product.

- ByeDPI settings now expose a readable dropdown with descriptions and
  actual safe ciadpi flags. The pictured GoodbyeDPI blacklist profile
  strings are NOT valid ByeDPI/ciadpi arguments.
- Android settings, welcome and APK update UI can open Android security
  settings, with fallback. Samsung users can inspect Auto Blocker there;
  the app never switches off security protections.
- Preserve package IDs, Android signing, bookmarks, downloads, history
  and existing settings; never erase data to mask an upgrade bug.
- Actual embedded Chromium navigation, Chrome extensions, in-app ByeDPI
  routing and media migration are NOT complete.
- The mandatory v0.2.1 CI check in
  tool/chromium/require_native_engine.py REJECTS absent AAR and missing
  native emulator smoke evidence. Main-branch release preparation has
  the same blocker. A claimed JSON report without real test provenance is
  not proof of working features; build and wire the native CI executor.
- The standalone Titanium research build does NOT produce an AAR, and
  needs a separate large isolated runner (32+ GB RAM, 120+ GB free disk).
- Only after feature implementation plus automatic integration checks pass
  can a verified PR be merged and v0.2.1 released. Actual phone testing
  remains after release, as requested.


## v0.2.1 native pipeline integration (October 19, 2026)

The correct product architecture is now **Windows Flutter/WebView2** plus
**Android Titanium Chromium native application**. Both are jobs inside
one PR CI and one release workflow; Android Flutter APKs are no longer built
as CI/release products. This is a source/build routing change, NOT a claim
that the resulting native Android experience is functionally complete.

See [ANDROID_NATIVE_ARCHITECTURE.md](ANDROID_NATIVE_ARCHITECTURE.md) for
exact job dependencies, production-signing isolation, update metadata
and pending feature migration. No production Android release before
native integration, AdBlock/ByeDPI/media/data-migration smoke and licensing
are complete. A dedicated Chromium build runner is not yet confirmed.
