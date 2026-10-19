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

Physical-device AdBlock acceptance is performed AFTER publishing a signed
release. It no longer blocks PR CI or the release workflow. The strict
acceptance script remains available for trusted device evidence; a manually
fabricated acceptance.json is not proof of physical-device testing.
Passing source-pin and Android/Windows builds does NOT prove that the native
Chromium engine is embedded or that AdBlock works.

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
A stable, securely stored extension signing key is still required for
consistent production upgrades. First-run-only behavior on a real device is
checked AFTER publication; the private key must never be checked into Git or
bundled with an APK. A native first-run UI or retained
Chromium profile marker may be preferable for the final app host.

This research workflow does not overcome the lack of a full compiled
in-app Chromium engine, Chromium-to-Flutter integration or ByeDPI transport.
Real-device AdBlock verification is now a post-release activity. See
docs/POST_RELEASE_ANDROID_VALIDATION.md. Do not advertise native extension
support based only on the successful Flutter/WebView package build.

## v0.2.1: compile the REAL Titanium-based Android product candidate

The old Chromium/Flutter AAR contract is not a working Chromium engine.
The shorter real native Android route is to **build Titanium as the Android
browser application itself**, preserving Windows Flutter separately.

We now provide an explicit second variant of the pinned Titanium ARM64
builder. On a dedicated isolated `chromium-large` Linux runner, run:

    bash tool/chromium/build_titanium_prototype.sh /empty/large/workspace product-candidate

This configures the actual Chromium `chrome_public_apk` target with
`chrome_public_manifest_package = "io.github.sopo9880.internet_browser"`
instead of constructing a stub AAR. The produced APK must pass an aapt2
package-name check and Android apksigner verification.

- The product candidate is **signed with a short-lived research key**, NOT
  the key used by v0.2.0. Never install this over existing user data:
  Android will reject the mismatched signing certificate.
- This is a full Chromium browser candidate, not an embedded engine inside
  Flutter. A genuinely usable browser still needs integration of ByeDPI,
  video, user settings, versionCode, Chrome extension workflows, and a
  non-destructive migration of previous Flutter user data.
- The same Chromium source with a production signing path will be needed
  for an installable 0.2.1 upgrade. Never use the production key in a
  PR/self-hosted builder or third-party build script.
- Titanium/Vanadium are GPL-2.0. Release requires complete corresponding
  source and license notices, not just a modified binary.
- The strict release gate remains RED; no claim of successful embedded AAR
  or validated Android integration is made by this change.

To request the expensive source build, apply `chromium-build` to the
existing development PR #4. Workflow:
`.github/workflows/chromium-extension-prototype.yml`.
The job needs a connected `[self-hosted, linux, x64, chromium-large]`
runner and can queue if none is available. A passing lightweight Flutter
CI run is NOT proof that this real Chromium compilation succeeded.


## 2026-10-19: 23 GiB RAM + 24 GiB swap WSL2 source-build mode

This repository's one required PR CI (ci.yml) now owns the genuine
Titanium-native Android compile. The older separate research PR workflow
was removed. In v0.2.1, do NOT follow earlier instructions in this
document about PR #3 or the now-deleted chromium-extension-prototype.yml.

On the user's dedicated Ubuntu 24.04 WSL2 distribution, memory visible
inside Linux is ~23 GiB, swap is 24 GiB, CPUs visible are 12 and the
Ubuntu ext4 filesystem has ~954 GiB free. A new
tool/chromium/build_resources.py preflight admits this configuration
only when enough physical available RAM, swap, combined capacity and
disk are present; the earlier unconditional 30,000,000 KiB RAM gate
is removed. A default 3-worker autoninja / 2-worker gclient sync
configuration is patched into the exact, source-pinned upstream
build.sh; if upstream commands change, patching fails closed.
These limits trade compilation throughput for reduced OOM risk.
A verified source-build success is still pending.

Set CHROMIUM_NINJA_JOBS=2 to reduce memory pressure further if needed,
or CHROMIUM_SYNC_JOBS=1 to reduce source download concurrency.
Low-RAM preflight deliberately rejects values over 3 (ninja) / 2 (sync).
The dedicated GitHub self-hosted Android build job has a 24-hour limit.
NEVER change the Android runtime smoke gate merely to make CI green.

This pinned upstream builder installs Debian/Ubuntu packages via sudo.
A normal GitHub runner is noninteractive; password-protected sudo may
block compilation. Plan privileged dependency installation inside the
dedicated WSL distribution before connecting the runner, and use only
trusted code. WSL2 and disabled Windows drive mounts are not a complete
security boundary. Do NOT place production signing keys in this runner.
