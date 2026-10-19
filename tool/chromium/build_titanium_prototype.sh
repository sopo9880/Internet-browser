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

# Private research install identity; NEVER replace the signed v0.1.1 app.
python3 - "$WORKSPACE/titanium/args.gn" "$WORKSPACE/titanium/build.sh" "$APP_PACKAGE" <<'PY'
from pathlib import Path
import sys
gn_path, build_path, package = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
args = gn_path.read_text(encoding="utf-8")
old_package = 'chrome_public_manifest_package = "io.github.jqssun.helium"'
old_cpu = 'target_cpu = "arm"'
if args.count(old_package) != 1 or args.count(old_cpu) != 1:
    raise SystemExit("Titanium Android GN build template changed; review upstream")
args = args.replace(old_package, f'chrome_public_manifest_package = "{package}"')
args = args.replace(old_cpu, 'target_cpu = "arm64"')
gn_path.write_text(args, encoding="utf-8")

build = build_path.read_text(encoding="utf-8")
arm_block = (
    "autoninja -C out/Default chrome_public_apk\n"
    "mv $(find out/Default/apks -name 'Chrome*.apk') out/tmp/$VERSION-armeabi-v7a.apk\n"
    "sed -i 's/target_cpu = \"arm\"/target_cpu = \"arm64\"/' out/Default/args.gn\n"
)
arm_sign = "sign_apk out/tmp/$VERSION-armeabi-v7a.apk out/release/$VERSION-armeabi-v7a.apk\n"
if build.count(arm_block) != 1 or build.count(arm_sign) != 1:
    raise SystemExit("Titanium build.sh layout changed; cannot safely isolate ARM64")
build = build.replace(arm_block, "# ARM64-only isolated research build\n")
build = build.replace(arm_sign, "")
build_path.write_text(build, encoding="utf-8")
PY

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
mkdir -p "$WORKSPACE/output"
cp "$APK" "$WORKSPACE/output/Chromium-155-EXTENSIONS-RESEARCH-ONLY.apk"
python3 "$SCRIPT_DIR/titanium_pin.py" \
  --apk "$WORKSPACE/output/Chromium-155-EXTENSIONS-RESEARCH-ONLY.apk" \
  --report "$WORKSPACE/output/provenance.json"
echo "Native Chromium extension-source APK compiled. IN-APP EMBEDDING AND ADBLOCK NOT TESTED."
