# v0.2.1 native Chromium: signing-only, NOT a release

## Scope

This isolated workflow signs the EXISTING native Chromium APK already compiled in
Actions run 39225095884, Android job 117970070549, uploaded artifact 12204054700.
It deliberately does not rebuild Chromium, merge the Chromium feature PR, or
publish a GitHub Release/tag. Windows and v0.2.0 release workflows are untouched.

The original overall Actions run FAILED its independent Android runtime
integration gate, even though native source compilation succeeded. Navigation,
Chrome extension MV3 AdBlock behavior, ByeDPI, media, and migration from the
existing Flutter Android app have not passed automated functional checks.

The signed candidate retains the v0.2.1 manifest and original Android package
identity, but that DOES NOT prove upgrade safety. Do not install it as an update
over existing v0.2.0 user data or distribute it as a stable release.

## Provenance, trust, secrets and reproducibility

- Pin source workflow run, successful Android job, artifact ID, archive SHA-256,
  exact source SHA, package name, versionName and versionCode.
- Before accessing secrets, validate GitHub API metadata, original APK file
  digest in provenance, manifest identity and disposable signing certificate.
- ONLY a manual workflow_dispatch on the default main branch with explicit
  acknowledgement SIGN_UNVERIFIED_NO_RELEASE can access signing credentials.
  A PR receives no signing credentials and runs only no-secret safety tests.
- Use the stored ANDROID_KEYSTORE_BASE64, ANDROID_KEYSTORE_PASSWORD,
  ANDROID_KEY_ALIAS and ANDROID_KEY_PASSWORD secrets on a GitHub-hosted Ubuntu
  runner. Never place the private keystore on the WSL2 self-hosted Chromium
  build runner.
- The final APK's signature must match the existing v0.2.0 certificate
  fingerprint. Secrets are removed from runner temporary storage immediately
  after signing.
- Upload only a short-lived Actions artifact: an explicitly named UNVERIFIED
  signed APK, SHA256SUMS.txt, status notice, and immutable provenance report.
  No release tags or GitHub Releases are created.

## Operation

1. Review and merge this isolated signing-only PR after its no-secret CI checks
   pass. Do not merge the separate unfinished v0.2.1 Chromium feature PR.
2. Open Actions > Sign pinned Chromium candidate (UNVERIFIED, no release)
   on the default main branch, then Run workflow.
3. Enter SIGN_UNVERIFIED_NO_RELEASE when prompted.
4. Download the signed candidate artifact from the workflow run, if it passes.
   It is NOT the app's production release.

The original artifact expires on 2026-10-26 (UTC). If it expires, STOP and
review a new source artifact as a separate explicit change; do not silently
fall back to a different APK or rerun the multi-hour Chromium build.
Physical-device validation remains post-release for the actual completed
product; this signing-only workflow does not claim that testing happened.
