#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LANE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

bootstrap_host_tools=1
skip_fetch=0
skip_sync=0
skip_hooks=0
mode="debug"
jobs=""
gn_args=""
autoninja_extra=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --mode" >&2
        exit 2
      fi
      mode="$2"
      shift 2
      ;;
    --jobs)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --jobs" >&2
        exit 2
      fi
      jobs="$2"
      shift 2
      ;;
    --gn-args)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --gn-args" >&2
        exit 2
      fi
      gn_args="$2"
      shift 2
      ;;
    --skip-fetch)
      skip_fetch=1
      shift
      ;;
    --skip-sync)
      skip_sync=1
      shift
      ;;
    --skip-hooks)
      skip_hooks=1
      shift
      ;;
    --no-bootstrap-host-tools)
      bootstrap_host_tools=0
      shift
      ;;
    --)
      shift
      autoninja_extra+=("$@")
      break
      ;;
    --help|-h)
      cat <<'EOF'
Usage:
  ./scripts/bringup-linux.sh [options] [-- autoninja args]

Options:
  --mode debug|release         Build directory lane (default: debug)
  --jobs N                     gclient sync jobs count
  --gn-args "..."              Override gn args
  --skip-fetch                 Skip fetch --nohooks chromium when src is absent
  --skip-sync                  Skip gclient sync
  --skip-hooks                 Skip gclient runhooks
  --no-bootstrap-host-tools    Skip ./scripts/bootstrap-host-tools.sh
EOF
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "${mode}" != "debug" && "${mode}" != "release" ]]; then
  echo "invalid --mode: ${mode} (expected debug|release)" >&2
  exit 2
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "bringup-linux.sh is for Linux hosts. Use setup-macos-external-lane.sh on macOS." >&2
  exit 1
fi

if [[ -z "${gn_args}" ]]; then
  if [[ "${mode}" == "debug" ]]; then
    gn_args="is_debug=true is_chrome_for_testing=false is_chrome_for_testing_branded=false is_chrome_branded=false"
  else
    gn_args="is_debug=false is_chrome_for_testing=false is_chrome_for_testing_branded=false is_chrome_branded=false"
  fi
fi

run_cmd() {
  echo "+ $*"
  "$@"
}

if [[ "${bootstrap_host_tools}" -eq 1 ]]; then
  run_cmd "${SCRIPT_DIR}/bootstrap-host-tools.sh"
fi

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env.sh"

if [[ ! -d "${LANE_DIR}/src/.git" ]]; then
  if [[ "${skip_fetch}" -eq 1 ]]; then
    echo "src checkout is missing and --skip-fetch was set" >&2
    exit 1
  fi
  run_cmd fetch --nohooks chromium
fi

cd "${LANE_DIR}/src"

if [[ "${skip_sync}" -eq 0 ]]; then
  sync_cmd=(gclient sync)
  if [[ -n "${jobs}" ]]; then
    sync_cmd+=(--jobs "${jobs}")
  fi
  run_cmd "${sync_cmd[@]}"
fi

if [[ "${skip_hooks}" -eq 0 ]]; then
  run_cmd gclient runhooks
fi

out_dir="out/fawn_debug"
if [[ "${mode}" == "release" ]]; then
  out_dir="out/fawn_release"
fi

run_cmd gn gen "${out_dir}" "--args=${gn_args}"
run_cmd autoninja -C "${out_dir}" chrome "${autoninja_extra[@]}"

echo "linux bring-up complete: ${LANE_DIR}/src/${out_dir}"
