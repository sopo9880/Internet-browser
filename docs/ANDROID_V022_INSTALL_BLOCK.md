# Android v0.2.2 installation block investigation

On 2026-10-22 a user reported an installation failure on Samsung One UI 8.5.
The device dialog reads `악성 앱 설치 차단됨` and
`악성 앱으로 의심되어 설치할 수 없습니다.` The device model and the
security engine's detailed classification are not yet known. This is a failed
device-installation observation, not successful Android acceptance.

The published APK remains unchanged:

- Package: `io.github.sopo9880.internet_browser`
- Version: `0.2.2` / `2002001`
- SHA-256: `e8b8e92566fbdb4532a3f4c0fb12a76aa18827ac97b86d499103d9be565803d9`
- Original production certificate SHA-256:
  `08116054e3a1de465da9357649c045fbb06e6d06f2c6108cda5e6dfd81d82e4a`

The exact APK's compiled manifest was examined using the pinned Android SDK's
`aapt2`. Its manifest bytes match the native source APK that was subsequently
signed by the successful formal workflow. The package/version and signing
evidence establish origin, not a malware-safety verdict or installability.

The compiled default application label is still `Titanium`. The branding overlay
changed GRIT messages and launcher artwork but omitted
`res_titanium_base/values/channel_constants.xml`, which both APK resource targets
include. The patch brands the four explicit launcher/widget names while keeping
XML comments and upstream notices. APK verification now rejects a product package
whose compiled application label is not `Internet Browser`, even when its package
and version otherwise match. The new verifier rejects the actual v0.2.2 source
APK, and the string transformation was checked against the real pinned resource.
This branding defect is verified; its relationship to the security block is not.

The manifest declares browser capabilities including `QUERY_ALL_PACKAGES`,
`REQUEST_INSTALL_PACKAGES` and `READ_CONTACTS` (limited to SDK 36). These are
declarations, not proof of granted permissions, malicious activity or the reason
for the device verdict. Each requires a feature/call-site review before removing
it; arbitrary permission removal would not establish safety. The APK's manifest
targets SDK 37, has minimum SDK 29 and `allowBackup=false`; no `debuggable` or
`testOnly` attribute was present in the inspected manifest.

The investigation must still identify the device's actual blocking component and
classification, review the declared capabilities and native transport, and test a
new, separately versioned signed candidate on the affected device. No device
protection setting was changed, no APK was uploaded to an external scanner, and
the branding patch does not claim the installation block is resolved. Do not
overwrite the published APK, existing tag or checksums to replace it silently.
