# v0.2.0: real Android Chromium extension engine research build

This is the **real extension-capable Chromium source build** milestone,
not a WebView fallback, a JavaScript-only extension substitute or a claimed
release. The exact required extension remains Chrome Web Store AdBlock
ID: gighmmpiobklfepjocnamgkkbiglidom.

## Verified upstream source choice (October 2026)

Research engine: Titanium Browser for Android
https://github.com/jqssun/android-titanium-browser

- Source revision: e59e03dc83bc940d73cf29a7683286fca390b393
- Vanadium submodule revision: 20526e052e304b62cf3e80114b423934e2d1c540
- Reference Chromium version: 155.0.8059.84
- Chromium build mode: is_desktop_android = true, ARM64
- Upstream documentation: Android Chrome Web Store extension installation
- Upstream source and patches are GPL-2.0. Review license and the full
  combined application's source-distribution obligations BEFORE
  incorporating any of that code into a public Internet-browser release.

These commits are immutable in tool/chromium/titanium_pin.py and the
actual research builder verifies source and Vanadium hashes.
**The extension ID has NOT been installed or verified in this app.**

## What the builder actually does

On a disposable Linux x86_64 runner with at least ~32 GB RAM and 120 GB
free disk, run:

    bash tool/chromium/build_titanium_prototype.sh /large/empty/workspace

The script clones exact upstream source and submodule revisions,
checks the source tree, modifies the research copy to build ARM64
only, and invokes the upstream real Chromium GN / autoninja build.

Safety properties:

- Output is a **standalone Chromium APK**, built from a genuinely
  extensions-capable source fork. It is NOT a Flutter AAR.
- The prototype has a separate app ID:
  io.github.sopo9880.internet_browser.chromiumtest
- The original installed v0.1.1 app and production signing key are never
  overwritten or used in this prototype build.
- A short-lived test keystore is generated locally on the build runner.
- It creates provenance.json with exact Git SHA, version and APK SHA-256.
- The report explicitly says AdBlock was NOT installed/tested and
  embedded Flutter engine was NOT completed.
- The builder executes a pinned upstream build script that runs
  sudo apt-get; use an isolated ephemeral runner, never a shared
  workstation. Never pass release signing secrets into this build.
- A successful research APK is a prerequisite to developing the
  production Android Chromium host, **not** authorization to ship v0.2.0.

## How to run through GitHub Actions

A prototype workflow is in:
.github/workflows/chromium-extension-prototype.yml

The self-hosted runner must be labeled:
self-hosted, linux, x64, chromium-large

After registering a suitable isolated runner, apply the
chromium-build label to existing PR #3. The labeled event starts the
large source build. The workflow is otherwise skipped on ordinary PRs
so it does not queue forever without a real runner.
This workflow only uploads a short-lived R&D APK artifact (1-day
retention), never a GitHub Release.

The usual Browser v0.x CI independently checks the pinned source
metadata and does not need 120 GB just to analyze Dart/Python.

## Important architecture decision: Chromium-first Android

The existing Flutter browser and its media library stay available as
source, and Windows continues using Flutter/WebView2. However, a full
Chromium-based Android browser build is a native Chrome app, not an
embedded AAR exposed by the ordinary Chrome build target.

The earlier EmbeddedChromiumEngine / AndroidView / AAR interface is a
prototype seam and has NO working native provider. Passing a stock
Chromium build, or obtaining this R&D APK, does not magically provide
the provider class.

For production, prioritize a Chromium-native Android app host and
port/reconnect the existing Flutter features or embed Flutter tooling
into that host. Before replacing the live app, prove:

1. Native Chromium Android UI and tabs launched **inside our app ID**.
2. The exact Chrome Web Store AdBlock extension installed and enabled.
3. MV3 service worker runs; declarativeNetRequest blocks controlled
   real network requests, plus site allowlists and popup work.
4. Downloads/video metadata/media playback/PiP are migrated and tested.
5. The Chromium network context routes through the app's ByeDPI SOCKS5.
6. Cookies, bookmarks, settings, existing downloaded files and library
   metadata migrate safely from v0.1.1.
7. Android production signing uses the original release key and the
   correct monotonically increasing versionCode.
8. Windows builds still pass. Retain the 0.x version policy.

The complete PR CI and release workflow remain blocked until the
physical-device AdBlock acceptance gate is satisfied. No manual
acceptance.json may stand in for actual trusted device test results.

## Remaining infrastructure dependency

A large isolated Linux Chromium runner is necessary for this source
build. Standard GitHub-hosted Ubuntu runners are too small for the
expected workspace. Having workflow YAML does not mean a runner
exists, a Chromium engine has been compiled, or the APK is available.


## First-run welcome and recommended AdBlock (added in this PR)

The Flutter Android development shell now displays a first-run welcome page
before browsing on a fresh install. It presents the exact AdBlock
gighmmpiobklfepjocnamgkkbiglidom, with user-initiated install and
installed/enabled verification through the real Chromium extension host.
It does not silently install third-party extensions, and it disables
installation when the native Chromium host is missing. A settings marker
welcome_v0200_completed prevents repeat display; existing v0.1.x
bookmarks, browsing history and DPI preferences are retained without
forcing the migration welcome. The user can reopen the welcome via
the Android browser's menu.

For the standalone Titanium-based Chromium research APK, the native
first-run equivalent is an Internet-browser-owned MV3 welcome extension
(tool/chromium/welcome_extension/). Its service worker listens only
for a genuine runtime.onInstalled(reason=install) event and opens the
bundled local welcome HTML once. The HTML shows the exact AdBlock
Chrome Web Store link and a continue button. AdBlock itself is not
bundled or installed; the user must choose to install/approve it.

The prototype builder uses tool/chromium/pack_welcome_crx.py to create
a real, signed CRX3, and stages it via Titanium's existing
extensions/dist/bundled.json and BUILD.gn extension bundling path.
CI verifies the CRX3 signature, archive and fixed AdBlock ID, but has
not executed this extension in a real Chromium APK.

Production blocker: Research builds generate an ephemeral welcome
signing key. This gives a new welcome extension ID on every build, so
the native extension could show the page again across APK upgrades.
A stable, securely stored signing key and proven first-run-only behavior
on device are necessary before release. The key must never be checked
into Git or bundled with an APK. A native first-run UI or retained
Chromium profile marker may be preferable for the final app host.

This workflow does not overcome the lack of a full compiled Chromium
engine, Chromium-to-Flutter integration, ByeDPI transport, or real-device
testing of the exact requested AdBlock. The v0.2.0 acceptance gate
remains mandatory.
