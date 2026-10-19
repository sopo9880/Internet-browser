# Post-release Android and Windows validation (v0.2.0)

Physical-device testing is deliberately scheduled AFTER a signed GitHub Release.
This checklist never runs in required PR CI or main-branch release Actions.
Release automation still needs successful static tests, Android APK build,
Windows installer build, production APK signing and SHA-256 checksum generation.

## 1. Obtain and verify the exact release

Download these release assets from the official GitHub release page
(replace v0.2.0 with the exact published tag):

    gh release download v0.2.0 --repo sopo9880/Internet-browser \
      --pattern 'Internet-browser-Android-v0.2.0.apk' \
      --pattern 'SHA256SUMS.txt' --dir dist
    cd dist
    grep 'Internet-browser-Android-v0.2.0.apk' SHA256SUMS.txt | sha256sum -c -

Also download the exact Windows installer and validate its SHA-256 against
SHA256SUMS.txt before installing it on Windows.
Do not treat PR CI artifacts as signed production APKs.

## 2. Test installation and previous user data

- On a physical ARM64 Android device, install the official release APK.
- Upgrade from the previously installed signed v0.1.1 version without
  deleting bookmarks, saved video files, history or DPI preferences.
- Confirm the signing identity and Android versionCode support an update.
- Test the original Windows application upgrade and saved configuration.
- If Android displays 'Chromium engine not connected', record a FAIL.
  The current source tree does not contain a compiled native Chromium
  integration; a successful Flutter APK build does not make browsing work.

## 3. Exercise actual Android Chromium and requested AdBlock

- Confirm browsing and navigation run inside this app (not an external app).
- Install the exact Chrome Web Store AdBlock ID:
  gighmmpiobklfepjocnamgkkbiglidom (user approval required).
- Verify MV3 service worker, declarativeNetRequest network blocking,
  permission prompts, action popup, site allowlist and persistence on restart.
- Test ByeDPI proxy routing with configured presets and advanced arguments.
- Test videos, downloads, offline playback, media controls, PiP and data
  preservation across app restarts; note any missing features explicitly.
- Mark unsupported functions as NOT IMPLEMENTED or FAIL, never as PASS.

## 4. Record trustworthy evidence

Record release tag, official APK SHA-256, device model, Android version,
results and relevant device logs. The optional validator is:

    python3 tool/chromium_extension_acceptance.py \
      --report build/reports/android_adblock_v0200.json

The JSON file must be produced from actual instrumented device evidence.
This command validates its schema; it does NOT itself install AdBlock, test
network filtering or establish the authenticity of the claimed results.
Never manufacture a passing JSON report to change a CI/release status.

## 5. Decide what to fix

Keep the released version and its checksums immutable. If the device test
finds defects, fix them in a new PR and publish a new 0.x patch release.
Do not announce Chromium/AdBlock compatibility as proven until device
validation and actual native-engine implementation are complete.


## v0.2.1 native Chromium upgrade-specific checks

When (and ONLY when) the new Titanium-native Android APK is functionally
complete and officially released, verify Android upgrade from the existing
v0.2.0 Flutter-signed installation IN PLACE without uninstalling. The
production Android signing certificate SHA256 must match v0.2.0 and
Android versionCode must increase (expected 2,001,001 for v0.2.1+1).
Ensure the old private Flutter settings and user library persist or are
migrated correctly into Titanium native storage. Test Chromium navigation,
Chrome Web Store AdBlock, MV3 request filtering, ByeDPI and offline media.
Never treat normal APK compilation as proof of these features.

The native CI product candidate is signed with a disposable key, so it is
NOT a supported in-place update over v0.2.0. Use it only for isolated test
installations, not production devices. See ANDROID_NATIVE_ARCHITECTURE.md.
