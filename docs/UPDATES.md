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

The Android CI APK in pull-request artifacts is only a test build.
Production APK updates MUST be signed with one persistent release keystore
and a versionCode greater than the installed versionCode. The signing key
must be configured as a GitHub Actions secret in a separate release
workflow or in a secure external signing process. Never commit a keystore
or ship a debug-signed APK as an official auto-update release.

Android will prompt users to permit installs from this app/source if their
device policy allows it; the app neither bypasses nor disables Android
security settings. When an app comes from Google Play, use Play-managed
update APIs instead of side-loading a different certificate.

## Production release gate

1. Validate Android tests and Windows CI (same SHA).
2. Build and sign the Android APK with the stable keystore. Verify signing
   certificate fingerprint matches previous releases.
3. Build Windows setup from the same source SHA and keep AppId unchanged.
4. Upload both named files to a public GitHub Release tagged v0.x.y.
5. Verify asset digests, installation and upgrade on real devices.
6. Release only after the explicit verification/approval workflow.

At the moment no official Releases exist. The updater can be tested with
an authorized staged release but won't announce anything until a newer
stable release is published.
