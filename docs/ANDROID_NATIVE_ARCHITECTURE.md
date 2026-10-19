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
   `self-hosted`, `linux`, `x64`, `chromium-large` with >=20 GiB RAM,
   >=16 GiB swap, >=40 GiB combined memory/swap, >=120 GB free Linux
   disk, and >=12 GiB available RAM. On the personal Windows 11 WSL2
   Ubuntu-24.04 builder: 23 GiB RAM, 24 GiB swap, 12 visible logical CPUs,
   954 GiB disk free; Chromium ninja -j3, gclient sync -j2. A clean
   Chromium build is NOT yet confirmed. Native Chromium source build remains queued
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


### Ubuntu 24.04 WSL2 runner preparation (personal PC, not connected yet)

- WSL2 memory: 24GB, swap: 24GB, processors: 12 in Windows
  .wslconfig; verify from Ubuntu with free -h, nproc, df -h /.
- Ubuntu-24.04 /etc/wsl.conf keeps systemd enabled and disables
  Windows drive automount and Windows process interop. WSL2 is NOT a
  security boundary; avoid sensitive host credentials on this build OS.
- The source builder checks /proc/meminfo and *real free Linux* storage,
  then patches the pinned Titanium build.sh with gclient sync -j 2
  and autoninja -j 3. On low physical RAM, it refuses insufficient swap
  or unsafe parallelism; success still depends on real compiler demands.
- For the **first build**, the GitHub Android CI job has 24-hour timeout.
  Keep Windows powered and avoid WSL shutdown while it runs.
- Install the official Linux x64 GitHub Actions runner only from the exact
  repository Settings > Actions > Runners > New self-hosted runner instructions.
  The runner must register labels [self-hosted, linux, x64, chromium-large].
  Registration tokens are short-lived SECRET credentials; never paste them
  into ChatGPT, logs or repository code. Do not run the runner as Windows
  administrator or put production Android signing secrets on WSL.
- Only same-repository PRs can invoke this build job (not forks).
  Nonetheless, runner uses public-repo source and pinned third-party
  build.sh, which executes sudo apt-get and build/install-build-deps.sh.
  Configure privileged build prerequisites only inside this dedicated
  disposable development environment; do NOT grant system-wide
  passwordless sudo on your main Windows workstation. If unattended
  sudo is not available, the upstream script may fail until a safe
  dedicated provisioning plan is established.
- There is an older queued "Android Chromium Titanium native source build"
  run from the previously removed workflow. Cancel the obsolete run in
  GitHub Actions before connecting a scarce runner, so it will not consume
  hours of compile time ahead of the current PR CI.
