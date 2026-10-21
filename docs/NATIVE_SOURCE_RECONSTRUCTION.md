# Native source reconstruction inputs

Use the integration commit and tree in `native-source-inputs.json`, not the
current default branch. The integration repository contains the product's
source overlays, artwork, GN settings, build/packaging scripts and notice texts.
The linked integration archive does not contain the complete upstream Chromium
or Android source trees. This document is reconstruction information, not a
claim that complete corresponding source has been bundled.

## Identify the exact build

The Windows and Android release provenance must identify the same integration
commit/tree as `native-source-inputs.json`. Their artifact hashes are recorded in
`SHA256SUMS.txt`. Windows records the pinned engine and hashes of the applied
product overlay. Android additionally records source preparation, Titanium's
patched source identity, the product overlay, APK payload and signing certificate.
Signing is separate from source compilation; production private keys are not
source inputs and are never distributed.

Start with a fresh checkout of the integration commit named in that manifest.
Review `native/chromium/product.json`, `tool/chromium/titanium_pin.py`, and the
build scripts before executing upstream hooks. Immutable source pins are also
included beside each upstream license in `upstream-notices-manifest.json`.

## Windows

Use Windows x64, Visual Studio 2026 Desktop C++ with ATL/MFC and the Windows
SDK required by the pinned Chromium source. The tested toolchain uses SDK
10.0.28000.2270. The workspace path must have no spaces and at least 120 GiB
free; a clean full build needs substantially more disk and memory than a small
hosted CI runner. See `docs/NATIVE_CHROMIUM_V022.md` for runner requirements.

Install the Python dependencies in `tool/chromium/requirements-windows.txt`.
Run `tool/chromium/build_windows.py --workspace C:\build\internet-browser-chromium
--jobs 3` with Python. That builder checks the Chromium and depot_tools commits,
synchronizes dependencies using Chromium's pinned DEPS, applies the reviewed
product overlay, verifies the bundled transport and builds the actual `chrome`
and `mini_installer` targets. `native-provenance.json` records the resulting
archive/installer hashes and overlay identity.

`tool/chromium/prepare_windows_runtime.py` makes a standalone test copy from that
exact archive. It is not an OS installation. The sandbox remains enabled; its
read/execute ACL setup uses Chromium's own helper from the pinned checkout.
Use the real installer separately when validating installed-browser behavior.

Windows bundles the pinned upstream ByeDPI 0.17.3 Windows distribution;
`tool/chromium/bundle_windows_transport.py` records its archive/executable hashes.
Its source revision and original MIT license are in the notice manifest.

## Android

Use the pinned Titanium and Vanadium revisions from
`tool/chromium/titanium_pin.py`. Source preparation and product application are
explicit phases in `prepare_android_source.py`, `titanium_product.py` and
`prepare_android_product.py`. Preserve their phase records. The builder rejects
an unrelated or incompletely prepared cache rather than silently resetting it.
Provision Chromium's Linux dependencies separately before building as an
ordinary user. No global passwordless sudo is required by this workflow.

The applied Titanium/Vanadium driver and product overlay, generated resources,
source validation records, pinned NDK and GN settings are inputs to
`tool/chromium/build_native_android.py`. Its `--product-objects-only` mode is a
compile check and does not produce an APK. The complete APK phase and exact
commands are defined in `.github/workflows/native-android.yml`; formal main
builds are orchestrated by `.github/workflows/native-android-production.yml`.
The native Android transport is built from the pinned ByeDPI source, rather
than reusing an ordinary Linux executable. Original upstream notices remain
unchanged.

## Distribution work still required

The upstream notice files and immutable reconstruction references accompany the
staged binaries. Review and assemble the complete corresponding-source
distribution for the final patched Android/Chromium build before publication.
Do not treat a green compilation check, these references, or an integration-only
archive as evidence that this remaining distribution step is complete.
