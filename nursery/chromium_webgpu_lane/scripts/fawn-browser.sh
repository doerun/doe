#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/x/deco/fawn"
CHROME_BIN="$ROOT/nursery/chromium_webgpu_lane/src/out/fawn_debug/chrome"
FAWN_LIB="$ROOT/zig/zig-out/lib/libfawn_webgpu.so"

if [[ ! -x "$CHROME_BIN" ]]; then
  echo "missing chrome binary: $CHROME_BIN" >&2
  exit 1
fi

if [[ ! -f "$FAWN_LIB" ]]; then
  echo "missing fawn runtime library: $FAWN_LIB" >&2
  exit 1
fi

exec "$CHROME_BIN" \
  --no-sandbox \
  --use-webgpu-runtime=fawn \
  --fawn-webgpu-library-path="$FAWN_LIB" \
  "$@"
