#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/x/deco/fawn"
CHROME_BIN="$ROOT/nursery/chromium_webgpu_lane/src/out/fawn_debug/chrome"
DOE_LIB="$ROOT/zig/zig-out/lib/libdoe_webgpu.so"

if [[ ! -x "$CHROME_BIN" ]]; then
  echo "missing chrome binary: $CHROME_BIN" >&2
  exit 1
fi

if [[ ! -f "$DOE_LIB" ]]; then
  echo "missing doe runtime library: $DOE_LIB" >&2
  exit 1
fi

export CHROME_DESKTOP="fawn.desktop"

exec -a fawn "$CHROME_BIN" \
  --no-sandbox \
  --class=fawn \
  --use-webgpu-runtime=doe \
  --doe-webgpu-library-path="$DOE_LIB" \
  "$@"
