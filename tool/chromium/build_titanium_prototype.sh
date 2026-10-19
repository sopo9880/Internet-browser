#!/usr/bin/env bash
# Actual source build of Chromium with Titanium's Chrome extensions.
# Second arg: research (isolated ID) or product-candidate (real app ID).
# Both use disposable signing keys; NEVER install product-candidate over v0.2.0.
# This is NOT an AAR, and NEVER a signed release.
# Run ONLY on an isolated disposable dedicated Linux x86_64 large runner.
set -euo pipefail
umask 077

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: build_titanium_prototype.sh /empty/large/workspace [research|product-candidate]" >&2
  exit 2
fi
WORKSPACE="$(realpath -m "$1")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_SHA="e59e03dc83bc940d73cf29a7683286fca390b393"
VANADIUM_SHA="20526e052e304b62cf3e80114b423934e2d1c540"
FLAVOR="${2:-research}"
case "$FLAVOR" in
  research)
    APP_PACKAGE="io.github.sopo9880.internet_browser.chromiumtest"
    OUTPUT_NAME="Chromium-155-EXTENSIONS-RESEARCH-ONLY.apk"
    ;;
  product-candidate)
    APP_PACKAGE="io.github.sopo9880.internet_browser"
    OUTPUT_NAME="Internet-browser-Titanium-ARM64-PRODUCT-CANDIDATE-NOT-INSTALLABLE-UPGRADE.apk"
    : "${BROWSER_NATIVE_VERSION_CODE:?Set native versionCode computed from pubspec}"
    : "${BROWSER_NATIVE_VERSION:?Set native 0.x versionName computed from pubspec}"
    ;;
  *)
    echo "Unsupported Chromium build flavor: $FLAVOR" >&2; exit 2 ;;
esac

if [ "$(uname -s)" != "Linux" ] || [ "$(uname -m)" != "x86_64" ]; then
  echo "Chromium source builder requires Linux x86_64" >&2
  exit 2
fi
for cmd in git python3 java keytool openssl base64 sudo; do
  command -v "$cmd" >/dev/null || {
    echo "Missing required Linux build command: $cmd" >&2
    exit 2
  }
done
if [ -e "$WORKSPACE" ]; then
  echo "Refusing to reuse or delete an existing build workspace: $WORKSPACE" >&2
  exit 2
fi

python3 "$SCRIPT_DIR/titanium_pin.py"
mkdir -p "$WORKSPACE"
AVAILABLE="$(df -Pk "$WORKSPACE" | awk 'END {print $4}')"
if [ "$AVAILABLE" -lt 120000000 ]; then
  echo "Chromium engine source build requires ~120 GB free disk" >&2
  exit 2
fi
RAM_KIB="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
if [ "$RAM_KIB" -lt 30000000 ]; then
  echo "Chromium engine builder needs at least 32 GB RAM" >&2
  exit 2
fi

git clone --no-checkout https://github.com/jqssun/android-titanium-browser.git "$WORKSPACE/titanium"
git -C "$WORKSPACE/titanium" fetch --depth=1 origin "$SOURCE_SHA"
git -C "$WORKSPACE/titanium" checkout --detach "$SOURCE_SHA"
git -C "$WORKSPACE/titanium" submodule update --init --recursive vanadium
HEAD="$(git -C "$WORKSPACE/titanium" rev-parse HEAD)"
SUBMODULE="$(git -C "$WORKSPACE/titanium/vanadium" rev-parse HEAD)"
python3 "$SCRIPT_DIR/titanium_pin.py" --checkout "$WORKSPACE/titanium" \
  --head-sha "$HEAD" --vanadium-sha "$SUBMODULE"

# Stage a signed, first-install MV3 welcome card inside the Chromium runtime.
# This installs only OUR welcome helper; AdBlock is an explicit opt-in link.
# Research keys are deliberately ephemeral and MUST be pinned before release.
python3 "$SCRIPT_DIR/pack_welcome_crx.py" \
  --source "$SCRIPT_DIR/welcome_extension" \
  --template "$WORKSPACE/titanium/extensions/BUILD.gn" \
  --dist "$WORKSPACE/titanium/extensions/dist" \
  --key "$WORKSPACE/welcome-crx-research-private.pem"


# Build a *real* native Chrome APK with the desired product package ID.
# A compiled Chrome application is NOT an embeddable Flutter AndroidView AAR.
VERSION_FLAGS=()
if [ "$FLAVOR" = "product-candidate" ]; then
  VERSION_FLAGS=(--version-code "$BROWSER_NATIVE_VERSION_CODE" --version-name "$BROWSER_NATIVE_VERSION")
fi
python3 "$SCRIPT_DIR/titanium_product.py" configure \
  --args "$WORKSPACE/titanium/args.gn" \
  --build "$WORKSPACE/titanium/build.sh" \
  --package "$APP_PACKAGE" "${VERSION_FLAGS[@]}"

# Ephemeral signing keys. This is NOT the Internet-browser production key.
# Avoid loading any repository signing secret into third-party Chromium builds.
PASSWORD="$(openssl rand -hex 18)"
keytool -genkeypair -noprompt -alias prototype \
  -keyalg RSA -keysize 3072 -validity 7 \
  -dname "CN=Internet-browser Chromium research, O=Unreleased" \
  -keystore "$WORKSPACE/prototype.jks" \
  -storepass "$PASSWORD" -keypass "$PASSWORD" >/dev/null 2>&1
printf 'keyAlias=prototype\nkeyPassword=%s\nstorePassword=%s\n' \
  "$PASSWORD" "$PASSWORD" > "$WORKSPACE/local.properties"
export LOCAL_TEST_JKS="$(base64 -w0 "$WORKSPACE/local.properties")"
export STORE_TEST_JKS="$(base64 -w0 "$WORKSPACE/prototype.jks")"
unset PASSWORD

# The source-pinned upstream build requires system dependencies and runs apt.
# Do not execute on a shared or developer workstation.
cd "$WORKSPACE/titanium"
bash build.sh
unset LOCAL_TEST_JKS STORE_TEST_JKS
APK="$(find "$WORKSPACE/titanium/chromium/src/out/release" -maxdepth 1 -type f -name '*-arm64-v8a.apk' -print -quit)"
if [ -z "$APK" ] || [ ! -s "$APK" ]; then
  echo "Real native Chromium ARM64 extension prototype APK was not produced" >&2
  exit 1
fi
AAPT2="$(find "$WORKSPACE/titanium/chromium/src/third_party/android_sdk/public/build-tools" -type f -name aapt2 | sort -V | tail -n1)"
APKSIGNER="$(find "$WORKSPACE/titanium/chromium/src/third_party/android_sdk/public/build-tools" -type f -name apksigner | sort -V | tail -n1)"
test -n "$AAPT2" && test -n "$APKSIGNER"
python3 "$SCRIPT_DIR/titanium_product.py" verify \
  --apk "$APK" --aapt2 "$AAPT2" --package "$APP_PACKAGE" "${VERSION_FLAGS[@]}"
"$APKSIGNER" verify --verbose "$APK"
mkdir -p "$WORKSPACE/output"
cp "$APK" "$WORKSPACE/output/$OUTPUT_NAME"
python3 "$SCRIPT_DIR/titanium_pin.py" \
  --apk "$WORKSPACE/output/$OUTPUT_NAME" \
  --package "$APP_PACKAGE" \
  --app-version "${BROWSER_NATIVE_VERSION:-}" \
  --version-code "${BROWSER_NATIVE_VERSION_CODE:-0}" \
  --integration-commit "${GITHUB_SHA:-}" \
  --report "$WORKSPACE/output/provenance.json"
echo "Compiled and checked native Chromium $FLAVOR APK, package=$APP_PACKAGE."
echo "Signed with disposable key; NOT compatible as update over existing signed application."
echo "Not a Flutter AAR. ByeDPI/media/data migration and emulator tests remain pending."
