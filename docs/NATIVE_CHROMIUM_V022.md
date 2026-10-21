# v0.2.2 native Chromium migration

The user selected a source-built native Chromium Windows browser, including
the product name, icon and native extension toolbar/popup. WebView2 is not the
v0.2.2 Windows browsing architecture. Android retains its Titanium/Chromium
source fork. v0.2.1 was published on 2026-10-20; it is not v0.2.2 acceptance.

## Source and build

`native/chromium/product.json` pins Chromium 155.0.8059.84 at
`5869fe313571d75152b77813cf0a4ee26a4e6df0` and depot_tools at an immutable SHA.
`tool/chromium/build_windows.py` obtains that source, synchronizes dependencies,
applies the version-controlled overlay, and builds Chromium's real `chrome` and
`mini_installer` targets. No prebuilt browser is renamed or wrapped in WebView2.
The engine version is retained separately from the product's 0.x release version.

The overlay adds `chrome://internet-browser/` and a browser-owned ByeDPI process.
Only allowlisted presets are accepted. Configuration is saved atomically in
the dedicated product user-data directory and applies at browser restart.
SOCKS5 status is distinct from site-level bypass verification. The engine runs
in a kill-on-close Windows job and does not change the system proxy. Missing
transport fails closed when DPI is enabled. Native WebUI messages are async.

The page links Chromium's native extension manager, store, bookmarks, history,
downloads and settings. AdBlock is an explicit store link for
`gighmmpiobklfepjocnamgkkbiglidom`; a link is not installation/compatibility proof.

```text
python -m pip install -r tool/chromium/requirements-windows.txt
python tool/chromium/build_windows.py --workspace C:\build\internet-browser-chromium --jobs 3
```

At least 120 GiB of free disk and VS 2026 C++ with ATL/MFC are required.
The pinned Chromium documentation requires Windows SDK 10.0.28000.2270 and
suitable SDK debugging tools. `--prepare-only` obtains source/dependencies
without compiling. GN's actual toolchain checks remain authoritative.

## Runners and CI

- Android: `[self-hosted, Linux, X64, chromium-wsl2]`.
- Windows: `[self-hosted, Windows, X64, chromium-windows-v022]`.
- The existing CI has an opt-in `native_windows` dispatch input. PRs run
  quality/source checks; legacy Flutter product builds are manual regressions.
- The native builder uses Python/CMD and needs no PowerShell policy changes.
- `CHROMIUM_WINDOWS_WORKSPACE` can select a persistent source cache on the
  dedicated runner. The source SHA and overlay are still verified.
- Artifacts are development candidates named `not-release`. Provenance records
  actual output hashes while leaving runtime/release status false.
- A headless controlled fixture checks the native page, MV3 worker, real DNR
  request blocking and an extension popup document. Its report explicitly
  does not certify the real AdBlock, store installation or toolbar popup UI.
- Provision Android dependencies separately as administrator, then build as
  the ordinary runner user. Do not enable global passwordless sudo.
- Local Windows and Android compile jobs share one concurrency group so they
  cannot exhaust the same PC's memory together. Source download alone may run
  alongside compilation.

## Android product preparation

`prepare_android_source.py` obtains pinned Titanium, Vanadium, Chromium and
depot_tools in a dedicated Linux cache. It executes no upstream hooks or sudo.
`titanium_product.py configure --product-overlay --preprovisioned-deps` prepares
the product package/version and inserts the product overlay before GN.

The product hook configuration excludes the unrelated Titanium helper's
unversioned `latest` CRX download. AdBlock remains an explicit store installation.
The source overlay restores external-extension safety checking, applies the
existing parcel icon and Internet Browser resource text, and remaps translation
fingerprints using the pinned Chromium GRIT implementation. Actual Chromium
resource checks produced identical full-file and wrapped-message mappings for
484 changed Android message fingerprints.

These are source checks. They do not establish successful Android compilation,
ByeDPI/media/data integration, a physical device's security verdict, or release
readiness. Full APK orchestration is implemented below; the APK phase has not
yet run.

The Android overlay now connects the native hub and browser-owned transport to
startup. Its ARM64 ByeDPI executable is built with Chromium's pinned NDK 30,
packaged in nativeLibraryDir, and includes its MIT license. A parent-death signal
limits the child lifetime to the browser. All seven Android product objects,
including transport and the updated player, compiled at 356948f. Android runtime
and device validation remain outstanding.

Original Flutter preferences are read into an atomic snapshot without editing
the original XML. Legacy ArrayList and Arrays-backed string lists are decoded
with a bounded format reader that never instantiates serialized classes. Real
Java serialization interoperability/rejection checks passed, and the snapshot
helpers compiled against the pinned Android SDK 37 jar. Lightweight PR CI runs
the plain Java codec checks. Native bookmarks import is opt-in; history keeps
its original URL-only representation without invented visit times.

The Android video listing reads the original app_flutter/Videos directory.
The shared native DPI option grammar and argument builder now preserve all four
presets and the old custom controls, including platform-specific disorder values.
Native configuration takes precedence; absent native settings read through the
original DPI preferences without changing the original files. C++ compatibility
and input-rejection checks passed, and Windows product source syntax checks passed.
Runtime verification of these paths, mapping other legacy settings, full media
player/library parity and updater integration remain required. Source wiring and
Java checks do not establish an integrated or release-ready Android APK.

The dedicated Linux cache has now completed source synchronization and hooks,
291 Vanadium patches, and Titanium's pinned driver (88 changed root files).
The source overlay applied 1,249 product files and remapped 1,273 translation
fingerprints. Actual Android GN generation succeeded with 98,385 targets from
4,981 build files. None of this is an Android browser compilation result.

The ARM64 ByeDPI PIE compiled using Chromium LLVM and its NDK 30 sysroot subset.
ELF inspection confirmed `/system/bin/linker64`, Android libc/libdl, 16 KiB load
alignment, RELRO and a non-executable stack. Device execution remains unverified.
The exact product overlay can be removed only after every owned file hash and
source revision matches, allowing controlled incremental source updates.

The native hub now embeds the exact pinned Chromium and ByeDPI notices on
Windows, plus Titanium and Vanadium license/exception texts on Android.
The notice manifest records revisions and byte hashes, which are checked while
generating the native resource header. Git preserves the notice bytes across
platforms. Both versions retain access to `chrome://credits/`. Windows source
syntax checks and Android GN generation passed with these pages included;
the runtime smoke check must still verify that the built page is served.
Corresponding source distribution/reconstruction remains a separate release task.

The Windows overlay now generates 25 product resources from the existing parcel
artwork: executable/app-list icons, square/scaled logos, monochrome variants,
Windows tiles, SVG logos and light/dark product-name images. Generation preserves
PNG dimensions and checks every pinned path before writing. A visual contact-sheet
review and deterministic output/dimension checks passed against the real source
checkout. These source changes require the next rebuild and runtime inspection;
they have not modified the source cache used by the active full build. Search and
provider artwork, distinct incognito/security icons and attribution remain intact.

The shared local player is now wired to validated library-file navigation.
A WebContents observer injects controls only into the selected primary-frame
file in Chromium's existing internal isolated world. Position reports and
next/previous commands are restricted to that library, with profile-local atomic
state writes; original videos and `library.json` stay untouched. Legacy positions
are read through until a native position exists. Controls include resume,
playlist continuation, rate, volume, loop, fit, lock, keyboard seek, temporary
2x playback, media-session actions, fullscreen and a capability-gated PiP button.

The seven current Windows product translation units pass pinned compiler syntax checks.
`check_video_player.py` exercised a real WebM media document in Chrome
155.0.8059.85 using a temporary profile: playback, resume, percent seeking, lock,
rate, loop/fit, position reporting, playlist choices, literal metadata text and
control layout passed. Visual review found and fixed MediaDocument's inline
absolute-video positioning. These checks cover the renderer script; native
observer navigation/state persistence, final product codecs, PiP, Android
background playback, external subtitles/tracks, download integration and full
library parity still require implementation or product-runtime acceptance.

The native update service now uses the profile's browser network context to query
this repository's stable release without credentials/cookies. It validates
numeric three/four-component versions, exact official asset paths and names,
size limits and GitHub SHA-256 digests. Downloads are streamed to a private
staging directory, then size/hash checked and renamed. Installation rechecks the
file and requires a separate confirmation. The Android bridge checks this
application's package name and uses a narrowly scoped cache FileProvider path
plus the OS installer; the OS retains its permission/signature checks.

The hub preserves legacy automatic-check and snooze choices, checks no more than
every 12 hours when opened, supports a seven-day tag-specific snooze, and retains
manual checks. It does not claim a background notification service when the hub
is never opened. Windows compiler syntax checks and actual C++ validator tests
passed. Eight renderer-flow checks passed with a stub native service, including
literal release notes, confirmation cancellation and rejected hash results.
Installed Windows native checks subsequently queried the actual stable GitHub
release successfully, preserved legacy automatic-check false, and also ran the
automatic hub check with legacy automatic-check true in a separate owned profile.
Native installer download/hash/cancellation and updater-launched execution,
Android JNI build and OS behavior remain unverified; these require product
acceptance. This check did not download or execute an update installer.
No installer was downloaded/executed by the renderer-flow tests.

`build_native_android.py` now connects the prepared source to compilation.
It validates the source/driver/nested repository pins, reviewed patch bytes,
owned overlay hashes and unknown tracked edits before replacing only the recorded
product overlay. It rebuilds the pinned transport, regenerates GN, compiles the
seven product translation units first, then builds `chrome_public_apk`. Final APK
checks cover package/version, the exact transport/license payload, ARM64 engine
ELF and disposable signature. Provenance and source-phase records accompany the
staged APK; they explicitly retain false runtime/release/production-signing flags.
The builder never accesses production signing keys. A prepare-only phase and a
product-objects-only phase support validation without creating a misleading APK.
Its prepare-only execution now passed on the real Linux cache, including source
validation, transport rebuilding, product overlay and GN generation. No APK was
created. `native-android.yml` schedules source-object checks on `chromium-wsl2`,
sharing the Windows compile queue. Its APK phase requires main and matching
product/release versions. Production signing is defined below; public release
qualification and publication remain required.
The old Flutter release path now permits only v0.2.1, so a v0.2.2 version change
cannot accidentally publish the previous implementation.

The formal native pipeline is defined in `native-android-production.yml`.
It is manual and main-only. It first requires matching native/release versions,
then calls the Windows CI builder and packaged native fixture/media smoke before
calling the native APK source builder once. It reuses
that run's artifact on a GitHub-hosted signing job. Source jobs receive no
production signing secrets. The signer checks the exact integration commit/tree,
package/version, product-source hashes, transport payload and disposable signer
before decoding the existing key. It checks the published application's original
certificate and all non-signature ZIP file contents after signing, with 16 KiB
ZIP alignment. The temporary private key is held outside the checkout and removed
on success or ordinary failure; output provenance does not claim runtime/release
acceptance. No publication or rebuild occurs in the signing step.

Six signing policy/orchestration tests pass using synthetic ZIP/key fixtures and
mocked signing tools, including wrong-certificate/tampered-payload rejection,
key cleanup and refusal to overwrite an existing release APK. These do not prove
a real APK is signed. The production workflow remains unexecuted: the migration
is not merged and native/release version metadata does not yet match.

`native-release-stage.yml` selects the exact Windows and signed Android artifact
IDs from one successful formal run on the current main commit. The selector
rejects PR/fork/other-commit runs, missing/duplicate/expired artifacts and missing
archive digests. It rechecks the Windows source tree/product hashes, packaged
archive/runtime identity and required native smoke results. It verifies the
Android package/version, original production certificate and APK hash with the
actual SDK tools, then copies the unchanged APK/EXE under their update asset
names and emits provenance plus SHA256SUMS. Native overlay files use LF on both
platforms so their source hashes agree across compilation and hosted staging.

Eight synthetic staging tests cover incorrect origins, modified payloads,
runtime/source mismatches, failed or empty smoke reports, wrong APK signatures,
unchanged copies, checksums and overwrite refusal. This workflow has read-only
permissions and uploads a review artifact; it does not build, sign, tag or
publish. The manifest explicitly leaves real Windows extension/installer,
remaining native features and corresponding-source distribution unaccepted.
No formal or staging run has executed yet. The old Flutter publisher still
cannot publish v0.2.2.

The Windows build provenance records the verified root source revision directly.
Its overlay marker stores the source pin inside `product`, unlike Android's
separate marker field; staging checks the actual producer format. A regression
test covers this distinction so a valid Windows build is not rejected merely
because its marker lacks an Android-specific field.

The library now supports editing displayed titles through a browser-side lookup
of an existing library URL. Native title and playback updates merge under the
same state-file lock, so playback cannot overwrite an edited title and a
title-only edit preserves the legacy resume fallback. Names are normalized and
bounded without modifying the original media file or `library.json`. Filename
fallback titles omit the extension. Compiler syntax checks and renderer checks
for cancellation/literal title display passed; native file-state behavior is
still pending product runtime validation.

The Windows native smoke harness now seeds temporary preferences, bookmark and
video-library fixtures instead of reading personal legacy directories. Directory
overrides require Chromium's explicit `--test-type` and cannot come from renderer
messages. Planned executable checks cover actual bookmark import/deduplication,
title writes, legacy resume, saved-position reopen, and unchanged original
preference/library bytes. This extended native smoke has not yet run against the
newly built product. The real AdBlock acceptance flags remain separately false.

The library now merges only this profile's completed video downloads with the
legacy folder. It waits for DownloadManager initialization, excludes blocked or
removed items, validates local file/content-URI access on a worker, deduplicates
URLs and retains default titles/source pages under stable download GUIDs. Android
content URIs use Chromium's existing ContentURLLoader; renderer requests still
select only entries returned by the browser's own library lookup. Refresh and
window-focus updates expose newly completed downloads without copying/moving them.
All ten legacy filename extensions remain listed; this is not proof that every
container/codec plays in Chromium.

Incognito library views can read existing metadata but do not persist new catalog
entries, edited titles or playback positions to the normal profile. Seven current
Windows product translation units pass pinned-compiler syntax checks. Twelve
renderer-flow checks pass with the native service stubbed, including refresh and
content-URI forwarding. The native smoke now includes a real loopback video
download and lookup/playback checks; those new executable checks have not run.
Android scoped-storage access, history/restart behavior, codecs and privacy state
writes still require native runtime/device acceptance.

`adblock_probe.py` reverified the real 6.50.0 CRX developer/Web Store publisher
signatures and selected enabled vendor ruleset
`8C13E995-8F06-4927-BEA7-6C845FB7EEBF`, block rule 779252 (`/ads/!rotator/`).
Its loopback server serves both a control script and a matching request; it adds
no filtering rules or substitute extension. Server/selection tests passed, but
these preparation tests do not establish runtime behavior. Subsequent real
Windows extension results are recorded below. Extension-manager enable/disable,
update/removal and error recovery still require separate acceptance.

Windows CI now prepares its test runtime from the exact `chrome.7z` whose hash
matches native build provenance. The helper rejects escaping/linked/colliding
archive paths, creates a coherent standalone layout from version-directory
files, verifies the packaged launcher, checks required resources/transport,
and fingerprints every copied file. Keeping a duplicate installed-version
directory beside the flattened launcher stalled renderer replies in the real
Windows package; removing that duplicate restored normal rendering. The helper
checks the pinned upstream AppContainer ACL helper before granting sandboxed
processes read/execute access to this owned copy. The sandbox stays enabled.
Preparation uses a unique final wrapper and completion marker, avoiding a
directory rename that failed with access denied in the OneDrive CI checkout.

The Windows browser and mini-installer compiled successfully at 9e878393.
Local packaged-runtime checks now pass startup, product WebUI, video title
editing, legacy bookmark import/deduplication, upstream notices, fixture MV3/DNR,
controlled navigation/download and fixture popup document. The saved-video
player initially failed: the media document reached readyState 4 but the
custom player was absent. At b678e101 the player attaches when the media document
is parsed, without waiting for the media resource's delayed window-load event.
Run 39524456961 successfully exercised all 22 controlled runtime checks,
including saved external Korean subtitles, legacy resume, position saving,
reopening, completed-download listing/playback and unchanged original files.
Separately, the exact 0f10c4f packaged app with ByeDPI enabled loaded
https://example.com/; its network log records the example.com:443 HTTP/2 session
through the app-owned loopback SOCKS5 endpoint. The bundled transport hash matches
build provenance and no transport child remained after browser exit. This proves
that tested HTTPS route, not restricted-site bypass. Android's seven ARM64
product objects compiled again at 356948f, including the DOM-ready player fix,
after the earlier Windows-only process-status API was replaced with POSIX
termination-status handling. This
does not constitute a complete APK build or device validation.

On 2026-10-21 the user installed the real AdBlock 6.50.0 into the owned native
test profile through the Chrome Web Store. The profile recorded `from_webstore`
and the expected ID, and the real MV3 worker executed. Read-only diagnostics
observed the vendor's enabled ruleset 2708BCB7-2E45-41BC-B517-1730CF532F89, rule
369368 (`/ads/!rotator/`). Its installed rule-file bytes matched the authentic
developer/publisher-verified CRX; no custom rules were added. The control script
reached the loopback server while the matching ad request did not. The user
opened the toolbar popup and `chrome.runtime.getContexts` reported its actual
`POPUP` context, rather than merely loading a popup HTML document in a tab.

Human-driven site pause/re-enable produced ad-loaded true, then false, with
matching server request counts. After the user closed the app, the same profile
was restarted headlessly using the b678e101 packaged runtime with ByeDPI enabled.
The normally installed extension remained enabled and blocked the controlled
request. The same browser loaded example.com over an HTTP/2 session through the
app-owned SOCKS endpoint. This proves the observed coexistence and restart case;
it does not prove a restricted site's bypass or Android behavior.

The user also ran the b678e101 Windows mini-installer. The installed application
ran from LocalAppData/Internet Browser/Application and registered as Internet
Browser. All 258 installed payload files matched the exact tested archive;
none were missing or different. Windows installation metadata retains the
Chromium engine version 155.0.8059.84, separate from product version 0.2.2.
Native first-run visual review was stopped when the computer-use helper could
not confidently identify the current URL. No safety barrier was bypassed.

The local player now reads the legacy `subtitlePath` first, then adjacent
same-basename SRT/VTT/ASS files, on a worker. Reads are limited to 2 MiB local
regular files; network/device paths are excluded. UTF-8, BOM-marked UTF-16 and
strict Windows-949 decoding are supported. The asynchronous injection checks
the original document's lifetime before adding the player. Original subtitles
and library metadata are never rewritten. Android content-URI videos cannot
automatically enumerate adjacent subtitle documents by this local-file path.

The renderer converts SRT and basic ASS dialogue timing/text to WebVTT, loads
an actual browser TextTrack and offers one-track selection/off and the C shortcut.
ASS fonts, positioning and effects are not reproduced. Twenty real Chrome 155
renderer checks pass, including Korean text, literal markup, cue timing,
SRT/VTT/ASS loading and track toggling; the screenshot was visually inspected.
All seven current Windows translation units pass the pinned compiler's syntax
check. The packaged native smoke additionally passed the saved UTF-16 subtitle
path priority over a neighboring SRT and unchanged-original-bytes checks.
Android device acceptance is separate.

## Native video discovery and saving (additional work after PR #10)

The hub now has a unified Video Save section. An explicit scan inspects HTTP(S)
tabs and frames in the exact same profile, including media elements, video
metadata, bounded resource history and embedded JSON. It recognizes direct files,
available unciphered YouTube muxed formats and Instagram/JSON-LD video addresses.
Only discovered opaque candidate IDs can start downloads; arbitrary hub-supplied
addresses are not accepted. Source document lifetime, active state and URL are
rechecked, including same-document navigation and back-forward cached pages.

File downloads use the source frame's ordinary Chromium download path, with
safety checks required. The hub shows progress, pause/resume/cancel controls and
links to the complete download manager. Completed video files enter the existing
library and player. Extensionless loaded media retain the server's container
filename inference rather than being silently labeled MP4.

HLS inspection offers the manifest's actual variants. Supported VOD playlists
contain an MP4 initialization segment and unencrypted MP4 media fragments. Every
manifest/part uses the standard frame-bound downloader; no safety verdict is
overridden. A profile-owned job survives leaving the hub. Parts are assembled on
a sequenced worker, and a completion marker registers only finished files in the
library. Pause takes effect at a part boundary; cancellation removes partials.
Keep the source tab open. Limits are 4 active jobs, 20,000 parts, 256 MiB per part,
8 GiB total and bounded manifest/address data. Interrupted parts can be retried;
in-progress stream jobs do not resume across a complete browser restart.

The controlled native browser test passed 21 checks: the actual save screen and
quality choices, byte-identical file download, generic/YouTube/Instagram data
discovery, profile separation, encrypted HLS refusal, HLS variant selection,
pause/resume/cancel, hub-navigation survival, exact MP4 assembly, cleanup, library
registration, offline playback and rejection of stale documents/SPA URLs. This
is controlled-page evidence, **not live YouTube/Instagram compatibility evidence**.
The JavaScript discovery suite has 8 checks; release staging additionally requires
the full native video smoke and its exact engine DLL hash.
The updated Windows source browser also passed all 22 existing native smoke
checks, retaining bookmark import, extension fixture behavior, subtitles,
playback/resume and unchanged legacy data. The 115 Python tests passed with 3
environment-specific skips; HLS C++ parser checks and workflow lint passed.

Still required for the requested broader downloader: live site acceptance,
YouTube signature-dependent/adaptive formats, DASH and separate audio/video
muxing, MPEG-TS remuxing, additional playlist features and live streams. These
cases display explicit reasons instead of pretending a playlist or video-only
track is a completed offline movie. DRM decryption is not implemented. The
installed development app and previous installer do not contain these changes.

## Required before release

The migration is in progress. Source transformations are not compilation;
a compiled browser is not functional acceptance. Remaining work includes:

- Installed Windows first-run/home visual review and old-to-native update flow.
- Real AdBlock extension-manager enable/disable, removal/update and error recovery.
- Preserve/import old bookmarks, history, settings and media. Complete media
  download/library/player and updater integration without deleting old profiles.
- Finish English/localized branding and artwork on both platforms. Retain
  Chromium, Titanium and other upstream copyright/licence attribution.
- Bundle the pinned upstream license/exception texts and corresponding source
  reconstruction information with the final native distributions.
- Android branding, permissions/security review, ByeDPI, media and migration.
- Light PR checks, main-branch source build/sign once, then publish those exact
  APK/EXE artifacts with checksums and corresponding source information.

The product and release metadata now both name v0.2.2 (Android code 2002001),
preparing the main-only formal build. No v0.2.2 tag or public release has been
created. Matching versions do not qualify the remaining work or authorize the
staging tool to publish; it retains false release-approval/publication flags.
