# Internet-browser

Windows + Android browser — v0.2.0 development (single DPI + media + Chromium extensions milestone).

Latest published release: [v0.1.1](https://github.com/sopo9880/Internet-browser/releases/tag/v0.1.1).

## v0.1.1 changes

- New black-and-white parcel icon on Android and Windows (including Windows installer).
- Address field focus fix, compact chrome, optional tab strip, tab chooser and scroll-to-hide address bar.
- Windows includes a SHA-256-verified ByeDPI v0.17.3 executable, started on demand as a local SOCKS5 proxy. WebView2 uses this proxy on next app launch after enabling it; a SOCKS handshake is checked before showing a connected status.
- Android optionally connects its WebView to a separately installed/running local ByeDPI-compatible SOCKS5 server. Android does not yet include a native VPN or DPI engine. It must never claim the toggle alone proves bypass.
- Best-effort YouTube skip-button support. A server-inserted/unskippable advertisement may still play. The basic host-based ad filter remains limited.
- User-confirmed saving of supported YouTube audio+video *muxed* streams, normally up to 360p. This is not high-resolution transcoding/merging or DRM circumvention. Save only material you have permission to download.
- Android updater: opens the official per-app unknown-source installation settings for user approval. Samsung Auto Blocker requires manual navigation; nothing changes OS security switches automatically.

## Build

Use Flutter 3.35.7 with the appropriate Windows/Android native SDK:

    flutter create --project-name=internet_browser --org=io.github.sopo9880 --platforms=android,windows .
    python tool/prepare_platforms.py
    flutter pub get
    dart run flutter_launcher_icons
    dart format lib test
    flutter analyze
    flutter test

On Windows, CI obtains the pinned upstream ByeDPI archive using tool/install_byedpi.ps1 and checks SHA-256 before putting ciadpi.exe and its MIT license alongside the app. Android uses an optional local proxy supplied by a separate app; no root permission is needed for the browser itself.

Pull requests perform tests and build test APK/EXE artifacts, never using production release signing secrets. An authorized PR merge triggers the separate production release workflow (signed APK + Windows installer, checksums), retaining v0.x versions. See docs/DPI_AND_MEDIA.md and docs/UPDATES.md.


## v0.2.0 combined release milestone (under development)

This version replaces the previously planned v0.1.2 release. The open
v0.1.2 development PR is reused rather than rebased into a second PR.

- Preserve the Android-native ByeDPI, Windows DPI presets, safe area, address
  focus fix, generic video metadata, offline video library and Android PiP.
- Android must actually run the **Chrome Web Store AdBlock extension**
  gighmmpiobklfepjocnamgkkbiglidom, not an imitation ad filter.
- The v0.2.0 Android Chromium extension host contract and diagnostic UI are
  currently integrated, but Android still uses WebView as its underlying
  browsing engine. Real Chrome extension installation is NOT implemented yet.
- The CI and release gates deliberately reject publishing v0.2.0 without
  physical-device acceptance for real Chromium/MV3/DNR, Chrome Web Store
  install, AdBlock startup, network request blocking, preferences and
  persistence. A green Android APK build is NOT extension support.
- See docs/ANDROID_CHROMIUM_EXTENSIONS.md for the engine migration and proof
  required. Never mark this release complete without that evidence.


### Android Chromium-first migration

The v0.2.0 Android development branch now routes the browser surface to a
native Chromium embedder interface instead of Android WebView. Until the
extension-capable native engine is supplied, Android shows an unavailable
engine message. Windows remains on WebView2.

Build instructions and native engine integration requirements are in
docs/ANDROID_CHROMIUM_EXTENSIONS.md. The upstream build script
tool/chromium/build_android.sh produces only a STOCK Chromium baseline,
not a Chrome Web Store extension-capable browser. AdBlock is not working
until actual native engine integration and physical-device verification.


### Real Chromium extension-source build phase (not yet completed)

Research pin: Chromium 155 Titanium/Vanadium Android fork, rather than
the old Kiwi 105 engine. This supplies a reproducible Android browser
source tree with real extension runtime patches. Its full build needs
an isolated Linux runner (32+ GB RAM, 120+ GB storage); it produces a
standalone research APK, NOT an embeddable Flutter AAR and NOT v0.2.0.
See docs/CHROMIUM_NATIVE_BUILD.md. Chrome Web Store AdBlock execution,
Flutter/media/ByeDPI integration and license review remain required.


### First-run AdBlock recommendation (v0.2.0 development)

A new Android install opens a welcome screen featuring the exact
Chrome Web Store AdBlock gighmmpiobklfepjocnamgkkbiglidom.
The user may install it (only once a real in-app Chromium extension
host exists), or continue without installing. No external browser is
used as a workaround and an unavailable engine cannot claim success.
Existing v0.1.x user data is preserved and the onboarding can be
revisited through the menu. Windows startup is unchanged.

The native Chromium research build also bundles a signed MV3 welcome
helper which can offer the official AdBlock store link on initial
installation. See docs/CHROMIUM_NATIVE_BUILD.md for the limitations:
this path has NOT been compiled or device-verified yet, and the
research signing identity must be stabilized before production.

## v0.2.1 development status (not a released Android fix)

**Android v0.2.0 cannot browse pages.** It was published without a
compiled embedded Chromium engine. Do not clear existing user data.

The v0.2.1 development branch adds a readable ByeDPI preset dropdown,
Samsung/Android security Settings navigation and an explicit native
Chromium CI/release readiness gate. The engine and actual AdBlock support
are NOT implemented yet. The required gate stays failing until real
engine integration and automatic Android navigation/extension tests exist.
Do not publish v0.2.1 solely because the Flutter APK compiles.


### Updated v0.2.1 architecture

Android release builds now target the full Titanium/Chromium native ARM64
APK; Windows stays Flutter/WebView2. The old non-functional Flutter Android
APK is no longer an output of the required CI or release workflow.
Both targets are controlled by one required PR CI pipeline and one
signed release workflow. Android source compilation needs an isolated
`chromium-large` Linux self-hosted runner; it is not confirmed online.

**This code change alone does NOT implement the Titanium port of ByeDPI,
video/offline library, Samsung security UX, or existing Flutter user-data
migration.** The Android functional smoke gate intentionally rejects
unverified binaries until genuine automated integration tests exist.
See [docs/ANDROID_NATIVE_ARCHITECTURE.md](docs/ANDROID_NATIVE_ARCHITECTURE.md).
