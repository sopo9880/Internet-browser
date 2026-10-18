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
