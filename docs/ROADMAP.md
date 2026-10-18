# Development roadmap

## v0.1.0: browser foundation
Tabbed browsing, history/bookmarks, Android and Windows builds, basic ad-host rules, permitted direct-media downloads.

## Next: DPI transport
Embed a maintained and license-compliant proxy engine separately on Windows and Android. Validate DNS, QUIC and WebView proxy behavior; never display enabled status without running traffic checks.

## Next: comprehensive ad filtering
Add rule-list parsing, signed/updateable lists, cosmetic rule handling, per-site configuration and regression tests.

## Next: advanced media library
Support permitted HLS/DASH downloads, pause/resume, offline in-app playback and Android background notifications. Do not attempt to defeat DRM.

## Release gates
Build both EXE bundle and APK against the same SHA, verify on real devices, and require explicit confirmation before PR merge or release.
