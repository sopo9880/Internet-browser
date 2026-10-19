# Android Chromium + Chrome extensions: v0.2.0 development and post-release acceptance

v0.2.0 combines v0.1.2 DPI/media fixes with **real Chrome extension execution
on Android**. Required Chrome Web Store AdBlock extension:
gighmmpiobklfepjocnamgkkbiglidom.

## Baseline: NOT YET COMPATIBLE

The app currently embeds Android WebView through flutter_inappwebview.
WebView does NOT provide a Chrome extension runtime. Opening the web store,
unpacking CRX, or running an unrelated ad blocker is not genuine compatibility.
The current Dart ChromeExtensionHost interface and Kotlin MethodChannel
return an explicit unsupported capability and fail closed on installation.
The extension screen is a diagnostic UI, not a working extension manager yet.

## Required native Chromium integration

1. Select a maintained, security-patched Chromium Android source baseline.
   Archived Kiwi Browser extension patches are references, not secure
   production engine binaries. Chromium's experimental desktop Android
   extension build flags alone are not enough for ordinary Android phones.
2. Port or implement the Android Chromium extension host, including CRX
   verification, extension sandboxing, permissions, MV3 service workers,
   declarativeNetRequest rule engine, extension toolbar action and popup,
   and verified Chrome Web Store installation/update flow.
3. Replace InAppWebView with an in-app Chromium browsing surface. DO NOT
   open an external browser using an Android intent as a false substitute.
   Maintain responsive tab/back/forward management and Chromium security
   updates.
4. Connect the native engine to the Flutter MethodChannel operations:
   capabilities, installFromChromeWebStore, isInstalledAndEnabled, uninstall.
   Report enabled capabilities only when implemented and tested.
5. Migrate the DPI transport (WebView proxy override is not compatible with
   the new engine), site metadata, page focus events, video downloads,
   tab history, cookies, and existing navigation behavior.
6. Preserve downloaded files, video library metadata, user settings,
   Android signing identity, Windows installer and desktop player. Validate
   an in-place upgrade from v0.1.1.
7. Build the engine on a dedicated runner with enough CPU, RAM and storage
   to compile modern Chromium Android. Do not package untrusted obsolete
   proprietary Chrome APKs or consume external services without consent.

## Post-release physical-device acceptance checklist

- Install the precise AdBlock Chrome extension, not a substitute:
  gighmmpiobklfepjocnamgkkbiglidom
- Run its Manifest V3 background service worker and declarativeNetRequest.
- Verify a real ad/network request was blocked, not merely DOM hiding.
- Verify permission prompt, extension popup/settings, whitelist operation,
  extension update and installation persistence after process restart.
- Test a physical ARM64 Android device, fresh install and in-place upgrade.
- Check existing native ByeDPI, offline media player, PiP, title capture,
  video files and preserved user settings.
- Record tested production APK SHA-256, engine version and device model.
- Verify Windows EXE, production signing, v0.2.0 tag and release checksums.

Tool test: python3 tool/chromium_extension_acceptance.py
The acceptance JSON schema validator is NOT a device test. Run it only AFTER
a signed GitHub Release exists, using trusted evidence from the exact released
APK on a physical Android device. It is NOT required by PR CI, PR merge or the
release workflow. The initial WebView-only app cannot pass this acceptance.
A passing APK compilation alone never proves extension support.
See docs/POST_RELEASE_ANDROID_VALIDATION.md.

## Workflow policy

Reuse PR #3 and branch to avoid duplication, bump the version directly
from v0.1.1 to v0.2.0. Do not publish an intermediate v0.1.2.
Pre-release CI continues to require quality tests, source-pin checks and
both platform builds; the trusted main release workflow verifies signing,
version, installers and checksums. Physical-device acceptance is deferred until
AFTER the official release and does not block PR or release Actions.
Native Chromium integration is separately unfinished; do not claim extension
functionality is working until an actual native runtime is integrated and
verified. Keep versions on 0.x.


## Chromium-first integration changes (v0.2.0 development branch)

Android now routes page rendering to a native Chromium AndroidView adapter,
not to Android WebView. The Windows WebView2 engine is preserved. Until the
actual Chromium provider library is compiled and linked, Android explicitly
shows an unavailable-engine screen. It NEVER silently falls back to WebView.

The native Android class EmbeddedChromiumRuntime registers a platform view
(internet_browser/chromium_view), navigation MethodChannel
(internet_browser/chromium_navigation) and event stream
(internet_browser/chromium_events). A real in-process native Chromium
embedder must provide the following class, constructed with an Activity:

    io.github.sopo9880.internet_browser.chromium.ChromiumEngineProvider

This provider must implement EmbeddedChromiumEngine and support creating
native Chromium pages, navigating, executing JavaScript, and emitting page
events. Page events contain tabId, type and optional url, title, progress
or y. Types: url, title, progress, loadStarted, loadFinished, resource,
pointerDown, scroll. Navigation methods: navigate, back, forward, reload,
canBack, canForward, javascript. The existing extension channel also
requires the real Chromium engine to handle MV3 extensions and exact
AdBlock ID gighmmpiobklfepjocnamgkkbiglidom.

A separately built Chromium engine AAR can be linked into the generated
Android app only when BOTH environment variables are provided:

    BROWSER_ANDROID_CHROMIUM_AAR=/absolute/path/chromium-engine.aar
    BROWSER_ANDROID_CHROMIUM_AAR_SHA256=<exact 64-hex SHA256>

The prepare_platforms.py script verifies the AAR, its contents and
required provider class, then links it through the Android Gradle build.
That structural check alone does NOT demonstrate runtime compatibility.

### Build upstream Chromium Android before porting extensions

A dedicated Linux x64 builder with Chromium depot_tools, at least 100 GB
free disk space and preferably over 16 GB RAM is required. Select a
verified full upstream 40-digit Git commit SHA and run:

    export CHROMIUM_REVISION=<verified Chromium commit SHA>
    bash tool/chromium/build_android.sh

The official Chromium source, GN and autoninja are used to build the
stock chrome_public_apk as a bring-up baseline, and an explicit
NOT-EXTENSIONS manifest is generated. That APK is not an embeddable
Flutter library and does NOT include the Chrome extension port.

An opt-in workflow is included at .github/workflows/chromium-android.yml.
It requires a separately provisioned self-hosted runner with the
chromium-large label. No Chromium build has yet been executed by this
project, and the extension-capable native provider is still missing.

### Migrating ByeDPI and media

The Android WebView proxy override is no longer used in the Chromium
development path. ByeDPI settings are retained but Chromium network
context integration must be implemented before claiming network bypass.
The existing video downloads, metadata and user library remain in place.
Their navigation and resource hooks must be wired to the new Chromium
provider before v0.2.0 can be released.
