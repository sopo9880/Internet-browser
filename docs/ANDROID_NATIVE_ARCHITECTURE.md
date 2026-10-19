# Android native Chromium + Windows Flutter: v0.2.1 pipeline

## Single production pipeline per stage

PR development runs ONE required CI workflow:

    PR #4 / feature branch
       |
       +-- quality: Windows Flutter widget/static tests, Python tests
       +-- chromium_extension_source_pin: pinned Titanium+Vanadium checks
       +-- windows: Flutter Windows + ByeDPI + Inno EXE artifact
       +-- android: REAL Titanium Chromium ARM64 source compilation
       |      self-hosted, linux, x64, chromium-large (isolated runner)
       |      package io.github.sopo9880.internet_browser
       |      versionCode derived from pubspec (v0.2.1 = 2,001,001)
       |      disposable test signing key; NO production secrets
       |      artifact native-chromium.apk plus pinned provenance.json
       +-- android_chromium_runtime_gate:
              downloaded exact native APK + automated integration proof;
              must test navigation, MV3 AdBlock, ByeDPI, media, user migration

No Flutter APK is built in the required PR workflow. The separate Chromium
research PR workflow was removed to prevent duplicate builds. The optional
upstream Chromium stock-baseline workflow is manual-only and NOT releasable.

After all required PR CI passes and a user explicitly says "확인해", merge
PR #4. Push to main then triggers ONE signed release workflow:

    main push / v0.2.1
       |
       +-- prepare: strict 0.x metadata, tag uniqueness
       +-- quality: tests (Windows Flutter + Python native tests)
       +-- android: native Chromium source build, same release commit
       +-- android_gate: required automated real APK smoke validation
       +-- android_sign: GitHub-hosted runner only, existing v0.2.0 private key
       |      package/versionCode verified, cert SHA256 pinned to v0.2.0
       +-- windows: signed-build installer, Flutter Windows/WebView2
       +-- publish: ONLY after every dependency succeeds;
              Internet-browser-Android-v0.2.1.apk (native Chromium)
              Internet-browser-Windows-Setup-v0.2.1.exe
              SHA256SUMS.txt

### Version and upgrade safety

- Native Chromium Android is a full application, not a Flutter AAR or an
  externally launched Titanium APK. `chrome_public_manifest_package` is
  forced to the already released `io.github.sopo9880.internet_browser`.
- Chromium's default native versionCode would not respect the Flutter 0.x
  scheme. GN `android_override_version_code` and
  `android_override_version_name` are set from the exact pubspec metadata.
- The CI native product APK has a short-lived key and must NEVER be installed
  over production v0.2.0 (different signer).
- The GitHub-hosted release signing job uses the existing keystore ONLY after
  automated integration is green, and rejects any signer whose certificate
  digest differs from the v0.2.0 release:
  `08116054e3a1de465da9357649c045fbb06e6d06f2c6108cda5e6dfd81d82e4a`.
- Same package + signer + increasing versionCode are NECESSARY but not
  sufficient. The previous Flutter user's app-private files, settings,
  videos/bookmarks/history require a genuine non-destructive migration into
  native Chromium. NEVER advise uninstall/clear-data to fix migration.
- Native product-build artifacts are not release artifacts until successful
  CI smoke evidence and production signing.

### Blockers before v0.2.1 release

1. **Runner:** register an isolated Linux x86_64 runner labeled
   `self-hosted`, `linux`, `x64`, `chromium-large` with >=32 GB RAM
   and >=120 GB free disk. Native Chromium source build remains queued
   without hardware, not a "completed Chromium integration".
2. **Android features:** migrate existing Flutter features to native
   Titanium UI/network layer. Android ByeDPI proxy configuration currently
   exists in Flutter, NOT in Titanium; same for DPI dropdown, Samsung
   security flow, video download/library/offline playback.
3. **AdBlock:** verify exact Chrome Web Store ID
   `gighmmpiobklfepjocnamgkkbiglidom` installs, MV3 service worker runs
   and network requests really are blocked. Source support alone isn't proof.
4. **Automated acceptance:** instrument an actual Android emulator/device
   with the exact compiled APK and generate `android-ci-smoke.json` only
   from genuine test results. The required gate rejects its absence. Do not
   hand-author a fake passing report. Physical user-device tests remain
   AFTER release under the project's explicit policy.
5. **License:** Titanium/Vanadium patches are GPL-2.0. Prepare and publish
   complete corresponding source, changes, build instructions and notices
   before distributing binaries.

The runtime gate is deliberately RED until the remaining implementation is
real. Never weaken this gate to turn CI green. Do not merge the Draft PR
or release v0.2.1 while the native pipeline has not passed.
