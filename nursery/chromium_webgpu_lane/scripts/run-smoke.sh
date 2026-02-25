#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lane-paths.sh"

chrome_bin="$(fawn_resolve_chrome_binary)"
doe_lib="$(fawn_resolve_doe_lib)"
mode="both"
forward_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --chrome)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --chrome" >&2
        exit 2
      fi
      chrome_bin="$2"
      forward_args+=("$1" "$2")
      shift 2
      ;;
    --doe-lib)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --doe-lib" >&2
        exit 2
      fi
      doe_lib="$2"
      forward_args+=("$1" "$2")
      shift 2
      ;;
    --mode)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --mode" >&2
        exit 2
      fi
      mode="$2"
      forward_args+=("$1" "$2")
      shift 2
      ;;
    --help|-h)
      cat <<'EOF'
Usage:
  ./scripts/run-smoke.sh [webgpu-playwright-smoke args...]

Runs webgpu-playwright-smoke.mjs with host-resolved default --chrome and --doe-lib.
All unrecognized args are forwarded to the Node runner.
EOF
      exit 0
      ;;
    *)
      forward_args+=("$1")
      shift
      ;;
  esac
done

if [[ ! -x "${chrome_bin}" ]]; then
  echo "missing chrome binary: ${chrome_bin}" >&2
  exit 1
fi
if [[ "${mode}" != "dawn" && ! -f "${doe_lib}" ]]; then
  echo "missing doe runtime library: ${doe_lib}" >&2
  exit 1
fi

exec node "${SCRIPT_DIR}/webgpu-playwright-smoke.mjs" \
  --chrome "${chrome_bin}" \
  --doe-lib "${doe_lib}" \
  "${forward_args[@]}"
