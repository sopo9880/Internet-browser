# Internet-browser

Windows + Android Flutter browser — v0.1.1 in development.

Latest released version: [v0.1.0](https://github.com/sopo9880/Internet-browser/releases/tag/v0.1.0).

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
