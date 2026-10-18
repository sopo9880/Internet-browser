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
