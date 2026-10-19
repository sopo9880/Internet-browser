#!/usr/bin/env bash
# Build stock upstream Android Chromium on a dedicated Linux builder.
# This is NOT a Chrome-extensions-compatible Android application.
set -euo pipefail
REVISION="${CHROMIUM_REVISION:?Set a verified full Chromium commit SHA}"
WORKSPACE="${CHROMIUM_WORKSPACE:-$HOME/internet-browser-chromium}"
CPU="${CHROMIUM_CPU:-arm64}"
OUT="out/InternetBrowser"

if [[ ! "$REVISION" =~ ^[a-f0-9]{40}$ ]]; then
  echo "Expected a pinned 40-character Chromium revision" >&2
  exit 2
fi
if [[ "$CPU" != "arm64" && "$CPU" != "x64" ]]; then
  echo "Unsupported Android CPU: $CPU" >&2
  exit 2
fi
for program in git python3 fetch gclient gn autoninja; do
  command -v "$program" >/dev/null || {
    echo "Missing $program. Install Chromium depot_tools." >&2
    exit 2
  }
done
if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "A Linux x86_64 Chromium builder is required" >&2
  exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"
if [[ ! -d src/.git ]]; then
  if [[ -e src ]]; then
    echo "Existing src is not a Chromium checkout" >&2
    exit 2
  fi
  fetch --nohooks android
fi
if [[ -n "$(git -C src status --porcelain --untracked-files=no)" ]]; then
  echo "Refusing to overwrite modified Chromium source" >&2
  exit 2
fi
git -C src fetch origin "$REVISION"
git -C src checkout --detach "$REVISION"
gclient sync --with_branch_heads --with_tags
ACTUAL="$(git -C src rev-parse HEAD)"
if [[ "$ACTUAL" != "$REVISION" ]]; then
  echo "Chromium revision mismatch" >&2
  exit 2
fi
gclient runhooks

python3 "$SCRIPT_DIR/prepare_android.py" \
  --source "$WORKSPACE/src" --out "$OUT" \
  --revision "$REVISION" --checkout-sha "$ACTUAL" --cpu "$CPU"
cd "$WORKSPACE/src"
gn gen "$OUT"
autoninja -C "$OUT" chrome_public_apk

APK="$OUT/apks/ChromePublic.apk"
if [[ ! -s "$APK" ]]; then
  echo "Missing upstream Chromium APK" >&2
  exit 1
fi
BASELINE="$WORKSPACE/chromium-baseline"
mkdir -p "$BASELINE"
cp "$APK" "$BASELINE/ChromePublic-stock-NOT-EXTENSIONS.apk"
DIGEST="$(sha256sum "$APK" | awk '{print $1}')"
python3 - "$SCRIPT_DIR" "$BASELINE/baseline.json" "$REVISION" "$DIGEST" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from prepare_android import save_baseline_metadata
save_baseline_metadata(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
PY
echo "Built a stock Chromium baseline. Extensions and Flutter embedding NOT implemented."
