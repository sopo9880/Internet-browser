#!/usr/bin/env bash
# Runs every repository check that does not need Flutter, a Chromium checkout
# or a device: Python tooling tests, Java legacy-data codec, standalone C++
# overlay checks and Node video tests. CI runs this same script.
#
#   tool/run_checks.sh             # same flags as CI
#   SANITIZE=1 tool/run_checks.sh  # also build C++ checks with ASan/UBSan
set -euo pipefail
cd "$(dirname "$0")/.."

out="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/internet-browser-checks"
rm -rf "$out"
mkdir -p "$out"

cxx="${CXX:-c++}"
cxxflags=(-std=c++20 -O2 -Wall -Wextra -Werror -I. -Inative/chromium/common/overlay)
if [ "${SANITIZE:-0}" = 1 ]; then
  cxxflags+=(-g -fsanitize=address,undefined -fno-sanitize-recover=all)
fi

step() { printf '\n== %s\n' "$*"; }

step 'Python tooling and release tests'
python3 -m unittest discover -s tool/tests -p 'test_*.py'
python3 tool/release_metadata.py
# The Gradle file only exists after `flutter create` + prepare_platforms.py.
if [ -f android/app/build.gradle.kts ]; then
  python3 tool/configure_android_signing.py
else
  echo 'Skipping Android signing template: run flutter create first (CI always does).'
fi

step 'Legacy Android string-list serialization (Java)'
javac -d "$out/java" native/chromium/android/java/LegacyStringListDecoder.java \
  tool/tests/LegacyStringListDecoderCheck.java
java -cp "$out/java" org.chromium.chrome.browser.LegacyStringListDecoderCheck

# name:extra-source (extra source is compiled together with the check).
for entry in \
    dpi_options: \
    update_validation: \
    video_payload: \
    video_file_types: \
    private_video_access: \
    video_mux: \
    video_playlist:native/chromium/common/overlay/video_playlist.cc; do
  name="${entry%%:*}"
  extra="${entry#*:}"
  step "Native ${name} (C++)"
  # shellcheck disable=SC2086 # $extra is a single path or empty.
  "$cxx" "${cxxflags[@]}" "tool/tests/${name}_check.cc" $extra -o "$out/${name}"
  "$out/${name}"
done

step 'Native video/audio MP4 mux with real H.264/AAC media (ffmpeg)'
# Skips itself when ffmpeg/ffprobe/node are unavailable.
python3 tool/tests/video_mux_media_test.py "$out/video_mux"

step 'Native video discovery, transmuxer and transfer history (Node)'
node --test tool/tests/video_discovery_test.cjs \
  tool/tests/video_transmuxer_tracks_test.cjs \
  tool/tests/video_transfer_history_test.cjs \
  tool/tests/youtube_background_test.cjs

printf '\nAll non-Flutter checks passed.\n'
