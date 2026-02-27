#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lane-paths.sh"

CHROME_BIN="$(fawn_resolve_chrome_binary)"
DOE_LIB="$(fawn_resolve_doe_lib)"

CHROME_TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --chrome)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --chrome" >&2
        exit 2
      fi
      CHROME_BIN="$2"
      shift 2
      ;;
    --doe-lib)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --doe-lib" >&2
        exit 2
      fi
      DOE_LIB="$2"
      shift 2
      ;;
    --help|-h)
      cat <<'EOF'
Usage:
  ./scripts/fawn-browser.sh [--chrome PATH] [--doe-lib PATH] [-- ...chrome args]

Launch the Fawn browser binary (or app bundle) with Doe runtime enabled
using lane-resolved defaults.
EOF
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

if [[ -d "${CHROME_BIN}" ]]; then
  if [[ "${CHROME_BIN}" == *.app && -x "${CHROME_BIN}/Contents/MacOS/Chromium" ]]; then
    CHROME_TARGET="${CHROME_BIN}"
    CHROME_BIN="${CHROME_BIN}/Contents/MacOS/Chromium"
  else
    echo "missing chrome binary: ${CHROME_BIN}" >&2
    exit 1
  fi
elif [[ ! -x "${CHROME_BIN}" ]]; then
  echo "missing chrome binary: ${CHROME_BIN}" >&2
  exit 1
fi

if [[ ! -f "${DOE_LIB}" ]]; then
  echo "missing doe runtime library: ${DOE_LIB}" >&2
  exit 1
fi

extra_args=()
if [[ "$(fawn_host_os)" == linux* ]]; then
  export CHROME_DESKTOP="fawn.desktop"
  extra_args+=(
    "--no-sandbox"
    "--class=fawn"
  )
fi
if [[ -n "${CHROME_TARGET}" ]]; then
  if [[ "$(fawn_host_os)" != "darwin" ]]; then
    echo "chrome app bundles require macOS launch path support" >&2
    exit 1
  fi

  exec open "${CHROME_TARGET}" --args \
    "${extra_args[@]}" \
    --use-webgpu-runtime=doe \
    --doe-webgpu-library-path="${DOE_LIB}" \
    "$@"
else
  exec -a fawn "${CHROME_BIN}" \
    "${extra_args[@]}" \
    --use-webgpu-runtime=doe \
    --doe-webgpu-library-path="${DOE_LIB}" \
    "$@"
fi
