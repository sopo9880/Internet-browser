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
readiness. The complete Android product build orchestration is still pending.

The Android overlay now connects the native hub and browser-owned transport to
startup. Its ARM64 ByeDPI executable is built with Chromium's pinned NDK 30,
packaged in nativeLibraryDir, and includes its MIT license. A parent-death signal
limits the child lifetime to the browser. These Android C++ paths still require
compilation and runtime validation.

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

## Required before release

The migration is in progress. Source transformations are not compilation;
a compiled browser is not functional acceptance. Remaining work includes:

- Native Windows compile/startup, first-run/home integration and installer.
- Real AdBlock store install, MV3, DNR, toolbar popup, enable/disable, removal,
  updates, restart persistence and operation with ByeDPI.
- Preserve/import old bookmarks, history, settings and media. Complete media
  download/library/player and updater integration without deleting old profiles.
- Finish English/localized branding and artwork on both platforms. Retain
  Chromium, Titanium and other upstream copyright/licence attribution.
- Bundle the pinned upstream license/exception texts and corresponding source
  reconstruction information with the final native distributions.
- Android branding, permissions/security review, ByeDPI, media and migration.
- Light PR checks, main-branch source build/sign once, then publish those exact
  APK/EXE artifacts with checksums and corresponding source information.

The production version and release workflow have not yet been advanced to
v0.2.2. They must not publish a partial migration as a completed release.
