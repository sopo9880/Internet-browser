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
