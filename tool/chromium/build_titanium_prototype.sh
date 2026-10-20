#!/usr/bin/env bash
# ACTUAL extension-capable Android Chromium research source build.
# Pinned Titanium Chromium 155. Not a Flutter AAR or product release.
# Run ONLY on an isolated, disposable, dedicated x86_64 Linux runner.
set -euo pipefail
umask 077

if [ "$#" -ne 1 ]; then
  echo "Usage: bash build_titanium_prototype.sh /isolated/large/workspace" >&2
  exit 2
fi
WORKSPACE="$(realpath -m "$1")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_SHA="e59e03dc83bc940d73cf29a7683286fca390b393"
VANADIUM_SHA="20526e052e304b62cf3e80114b423934e2d1c540"
APP_PACKAGE="io.github.sopo9880.internet_browser.chromiumtest"

if [ "$(uname -s)" != "Linux" ] || [ "$(uname -m)" != "x86_64" ]; then
  echo "Chromium source builder requires Linux x86_64" >&2
  exit 2
fi
for cmd in git python3 java keytool openssl base64; do
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
CHROMIUM_NINJA_JOBS="${CHROMIUM_NINJA_JOBS:-3}"
CHROMIUM_SYNC_JOBS="${CHROMIUM_SYNC_JOBS:-2}"
python3 "$SCRIPT_DIR/build_resources.py" --workspace "$WORKSPACE" \
  --ninja-jobs "$CHROMIUM_NINJA_JOBS" --sync-jobs "$CHROMIUM_SYNC_JOBS"

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


# Keep the research identity isolated while using the same checked source
# transformation and constrained resource limits as native product candidates.
python3 "$SCRIPT_DIR/titanium_product.py" configure \
  --args "$WORKSPACE/titanium/args.gn" \
  --build "$WORKSPACE/titanium/build.sh" --package "$APP_PACKAGE" \
  --ninja-jobs "$CHROMIUM_NINJA_JOBS" --sync-jobs "$CHROMIUM_SYNC_JOBS" \
  --preprovisioned-deps

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

# git am runs only in the dedicated checkout. Keep identity scoped to this job.
export GIT_COMMITTER_NAME="Internet-browser Chromium Build"
export GIT_COMMITTER_EMAIL="internet-browser-ci@users.noreply.github.com"
cd "$WORKSPACE/titanium"
bash build.sh
unset LOCAL_TEST_JKS STORE_TEST_JKS
APK="$(find "$WORKSPACE/titanium/chromium/src/out/release" -maxdepth 1 -type f -name '*-arm64-v8a.apk' -print -quit)"
if [ -z "$APK" ] || [ ! -s "$APK" ]; then
  echo "Real native Chromium ARM64 extension prototype APK was not produced" >&2
  exit 1
fi
mkdir -p "$WORKSPACE/output"
cp "$APK" "$WORKSPACE/output/Chromium-155-EXTENSIONS-RESEARCH-ONLY.apk"
python3 "$SCRIPT_DIR/titanium_pin.py" \
  --apk "$WORKSPACE/output/Chromium-155-EXTENSIONS-RESEARCH-ONLY.apk" \
  --report "$WORKSPACE/output/provenance.json"
echo "Native Chromium extension-source APK compiled. IN-APP EMBEDDING AND ADBLOCK NOT TESTED."
