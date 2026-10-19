# v0.1.1 checked third-party DPI engine (Windows)

Windows uses the upstream MIT-licensed ByeDPI `ciadpi.exe` binary from
[hufrea/byedpi](https://github.com/hufrea/byedpi/releases/tag/v0.17.3).
The install script pins the release archive's SHA-256 checksum, verifies
it before unpacking and copies the executable (and LICENSE, if present)
into the installed app's `tools/` directory.

The user must explicitly enable DPI mode. Windows starts a local SOCKS5
proxy bound to `127.0.0.1:1080` before creating WebView2 with an explicit
SOCKS5 proxy argument. The app checks the SOCKS5 handshake; it never
reports a successful bypass merely because the toggle is enabled. A new
app launch is needed to change the Windows WebView2 proxy configuration.

Android v0.1.1 supports an already-running local ByeDPI-compatible SOCKS5
proxy on `127.0.0.1:1080` through WebView's proxy override API. It does
NOT ship a standalone Android VPN service or a native Android ByeDPI engine;
installing/starting one separately is required for this mode. Do not
confuse the local proxy test with a successful DPI bypass for every site.

Changing proxy settings does not modify the OS-wide network connection.
No private keys or privileged system modifications are needed. A SOCKS
proxy routes browser HTTP(S) traffic but not all external app traffic.

YouTube: v0.1.1 adds a best-effort DOM skip/overlay cleanup script for
advertisements, not guaranteed full blocking of server-inserted ads, and
a user-confirmed downloader for permitted muxed streams (typically <=360p).
DRM and separate high-resolution video/audio merging are not supported.

## v0.2.0 combined release (work in progress)

- Android fixes system status-bar collision with a SafeArea; page pointer and scroll events release address-field focus.
- ByeDPI preferences support balanced/split/disorder/aggressive/custom presets, with only allowlisted CLI arguments and validated parameters. Windows changes apply on restart; Android restarts the internal proxy when changing settings.
- Android ByeDPI binaries are cross-compiled from pinned upstream v0.17.3 commit 7efde1b1296eaaa187b70e951894dde17527489c using the Android NDK for arm64-v8a, armeabi-v7a and x86_64. The binary is installed in APK nativeLibraryDir and runs as an app-scoped localhost SOCKS5 process. **No VPN service, root, or another ByeDPI application is required**. Device compatibility and site-by-site bypass effectiveness are not guaranteed; after detecting SOCKS5 we still show "connectivity verification needed".
- Downloaded video titles come from YouTube metadata when available and the embedding page's video / Open Graph / Twitter / document metadata for generic video downloads, with a safe fallback and editable title. A sidecar library.json preserves source page, filename, title, thumbnail, quality and playback position; v0.1.1 files remain in place and are found on startup.
- New media_kit-based offline player supports Android and Windows, ±10s double tap, held 2× playback, speeds from .25× to 2×, volume, subtitles (auto-detected SRT/VTT/ASS next to video), internal video/audio tracks, fitted/cropped aspect, playlists, repeat, seek and Windows-style shortcuts.
- Android uses an in-app MediaSession foreground playback notification and system picture-in-picture support (Android 8.0+); video background pause is disabled for this screen. Playback/service/device behavior still needs real-device validation.
- Selecting another quality **does not upsample a saved file**: only source tracks exist in a downloaded media file. Quality selection is only offered when the file contains multiple video tracks. YouTube downloads continue to use permitted available audio+video muxed streams; high-resolution separate tracks, service-account features and DRM are not cloned.
- Video metadata is derived from the page/site and saved locally. It never attempts to read protected credentials from sites.


## Chrome extension compatibility gate (v0.2.0)

Android Chrome Web Store extension compatibility is not supplied by Flutter
WebView, Android WebView Chromium libraries, embedded scripts, or an external
browser intent. The native Chromium browser engine and extension system need
real integration. Android's current MethodChannel honestly returns
"android-webview" with all Chrome extension capabilities disabled. The UI
also reports unsupported until the proper engine exists.

The required extension is AdBlock ID
gighmmpiobklfepjocnamgkkbiglidom. Release proof includes actual MV3 service
worker activation, declarativeNetRequest page-request blocking, Chrome Web
Store install, permission prompts, extension action/popup, persistence, and
validation of existing ByeDPI, library and player features. CI intentionally
fails its Android AdBlock acceptance job until this evidence is provided by a
real physical-device test. Do not manually override it.


### Chromium network transport (v0.2.0 in progress)

Android now uses a native Chromium engine interface rather than a WebView
browsing surface. Saved ByeDPI preferences remain, but the old Android
WebView proxy override is not used. The Chromium network context must
be adapted to the local SOCKS5 proxy before claiming DPI bypass.
The offline video library and files retain their existing storage path.
