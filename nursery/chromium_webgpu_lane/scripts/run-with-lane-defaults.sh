#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lane-paths.sh"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <smoke|bench> [args...]" >&2
  exit 2
fi

runner="$1"
shift

chrome_bin="$(fawn_resolve_chrome_binary)"
doe_lib="$(fawn_resolve_doe_lib)"
mode="both"
skip_run=0
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
    --skip-run)
      if [[ "${runner}" != "bench" ]]; then
        echo "--skip-run is only supported for bench mode" >&2
        exit 2
      fi
      skip_run=1
      forward_args+=("$1")
      shift
      ;;
    --help|-h)
      if [[ "${runner}" == "smoke" ]]; then
        cat <<'EOF'
Usage:
  ./scripts/run-smoke.sh [webgpu-playwright-smoke args...]

Runs webgpu-playwright-smoke.mjs with host-resolved default --chrome and --doe-lib.
All unrecognized args are forwarded to the Node runner.
EOF
      elif [[ "${runner}" == "bench" ]]; then
        cat <<'EOF'
Usage:
  ./scripts/run-bench.sh [run-browser-benchmark-superset args...]

Runs run-browser-benchmark-superset.py with host-resolved default --chrome and --doe-lib.
All unrecognized args are forwarded to the Python runner.
EOF
      else
        echo "unknown runner: ${runner} (expected smoke|bench)" >&2
        exit 2
      fi
      exit 0
      ;;
    *)
      forward_args+=("$1")
      shift
      ;;
  esac
done

if [[ "${skip_run}" -eq 0 && ! -x "${chrome_bin}" ]]; then
  echo "missing chrome binary: ${chrome_bin}" >&2
  exit 1
fi
if [[ "${skip_run}" -eq 0 && "${mode}" != "dawn" && ! -f "${doe_lib}" ]]; then
  echo "missing doe runtime library: ${doe_lib}" >&2
  exit 1
fi

if [[ "${runner}" == "smoke" ]]; then
  exec node "${SCRIPT_DIR}/webgpu-playwright-smoke.mjs" \
    --chrome "${chrome_bin}" \
    --doe-lib "${doe_lib}" \
    "${forward_args[@]}"
fi

if [[ "${runner}" == "bench" ]]; then
  exec python3 "${SCRIPT_DIR}/run-browser-benchmark-superset.py" \
    --chrome "${chrome_bin}" \
    --doe-lib "${doe_lib}" \
    "${forward_args[@]}"
fi

echo "unknown runner: ${runner} (expected smoke|bench)" >&2
exit 2
