# Release updates (Windows and Android)

## Current integration

The app checks public GitHub Releases/latest after startup (at most once
per 12 hours) or from Settings > Check for updates.

- Only newer stable versions are offered. The app version is taken from
  package_info_plus and compared numerically, including four-part 0.x tags.
- Users may choose Later or Hide for 7 days. Hiding applies only to that tag.
  Manual checks ignore the snooze.
- No release/404, offline failures and rate limits are handled without
  preventing normal browsing; manual checks display useful feedback.
- Only an exact same-repository asset URL is accepted.
- If the official release contains the right installer plus a SHA-256 digest,
  the app downloads it into private temp storage, validates its length and
  SHA-256, and asks the user again before launching the system installer.
- If there is no trusted installer asset, the app offers the official
  GitHub release page. No unverified EXE/APK is auto-opened.

## Release asset names (strict)

For version 0.1.1 using release tag v0.1.1, attach:

    Internet-browser-Windows-Setup-v0.1.1.exe
    Internet-browser-Android-v0.1.1.apk

The version in pubspec.yaml must be increased and match the GitHub release
tag. The installer asset must be a GitHub Release asset (not a bare EXE
from another website). GitHub's release asset API should expose its
digest field as sha256:<64 hexadecimal characters>.

The Windows CI job builds the EXE folder and an Inno Setup installer;
the latter can install over an existing installation without removing
bookmarks or app storage. No app-level silent install or elevation.

## Android signing requirement

The Android PR CI APK is only a test build. Production APK updates are
signed by the main-branch release workflow using one persistent PKCS12
keystore from GitHub Actions Secrets. PR CI does not access release secrets.
The release workflow also verifies the APK signature. Never commit a keystore
or ship a debug-signed APK as an official auto-update release.

Android will prompt users to permit installs from this app/source if their
device policy allows it; the app neither bypasses nor disables Android
security settings. When an app comes from Google Play, use Play-managed
update APIs instead of side-loading a different certificate.

## Pre-release automated gate and post-release device QA

1. Validate Flutter analysis, widget/unit tests, Android build, Windows
   installer build and the source-pin checks at the PR head SHA.
2. After verified PR merge, the trusted main workflow reruns quality checks
   and builds the Android APK using the persistent release signing key.
   Verify signing and preserve the existing application ID.
3. Build Windows Setup from the same main SHA; keep the Inno Setup AppId.
4. Verify both published asset names and SHA-256 checksums, then create the
   official GitHub Release with a 0.x tag.
5. AFTER publication, install the exact signed APK/EXE and test the real
   device upgrade and Chromium/AdBlock, ByeDPI and offline video behavior.
   Record failed features and ship a corrective 0.x patch if needed.

Physical-device acceptance no longer blocks PR CI, PR merge, or release
Actions. The strict validator in tool/chromium_extension_acceptance.py is
retained for post-release trusted evidence, not as proof that the existing
native Chromium engine is integrated. The current engine implementation is
still incomplete and a successful APK build does not imply working Chrome
extensions. See docs/POST_RELEASE_ANDROID_VALIDATION.md.

The updater stays quiet until an official stable release exists. Android
signing, platform builds and checksum generation remain required by Actions.


## GitHub Actions release secrets (set up once)

| Secret | Purpose |
| --- | --- |
| ANDROID_KEYSTORE_BASE64 | Base64 of the same persistent PKCS12 .p12 keystore |
| ANDROID_KEYSTORE_PASSWORD | PKCS12 store password |
| ANDROID_KEY_ALIAS | Key alias (e.g. internet_browser_release) |
| ANDROID_KEY_PASSWORD | Private key password |

These secrets are only passed to the trusted main-branch Android release job.
They are never used by pull request builds. GitHub Secrets cannot be recovered
after storage; securely back up the original keystore and its password. Never
commit the .p12 to source control.

## Release automation

The project has two independent GitHub Actions workflows:

- .github/workflows/ci.yml: PR analysis/tests and test build artifacts.
  It has no access to Android release secrets.
- .github/workflows/release.yml: triggers on push to main after the
  maintainer explicitly verifies and merges a PR, or via manual dispatch
  from main. It validates versions and reruns tests, builds Windows setup,
  builds and signs the production APK, verifies the APK signing certificate,
  creates checksums and publishes both files to GitHub Releases.
- If a release with the same tag already exists, it does not overwrite it.
  If either platform build or secret validation fails, no release is posted.
  Non-0.x versions are intentionally not supported by the metadata script.
- Both artifacts are built from the SAME main-branch commit. The installer
  and APK are tagged v0.x.y. SHA256SUMS.txt is included in the release.
- No release code is executed for pull_request events. Release credentials
  are decoded into a temporary runner directory, not stored in source.
- The four Secrets above have not been verified through this conversation:
  a real production Actions run will test whether they are valid.

## Android versionCode policy

The pubspec.yaml version format is 0.MINOR.PATCH+BUILD (e.g. 0.1.0+1).
tool/release_metadata.py derives a monotonically increasing versionCode:

    versionCode = MINOR * 1000000 + PATCH * 1000 + BUILD

Use PATCH <= 999, BUILD from 1 to 999 and a MINOR value keeping the code
within Android's supported range. Release version codes increase whenever
the semantic app version increases. The application ID stays unchanged.

Production APKs are signed with the persisted release keystore; CI APKs
are test-only and may use a different certificate. Android may require
uninstalling an earlier test APK before installing the first production
release. In-place updates between production releases require using the
SAME original signing key each time.

## Windows setup and user data

The production workflow uses the existing Inno Setup config with a stable
AppId. It installs over the previous version without deliberately deleting
user data. Windows SmartScreen may warn about the EXE because certificate-
based Windows code signing is not implemented yet; SHA-256 checks verify the
GitHub-downloaded asset bytes, not publisher identity.

## Final verification

After the release job is triggered, verify successful Actions results,
release version/tag, actual GitHub Release publication, expected Windows
installer and signed Android APK, and SHA256SUMS. Then perform a separate
post-release physical-device update and feature-acceptance check.
A successful CI build alone is not proof of working Chromium extensions.
