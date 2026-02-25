#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lane-paths.sh"

mode="general"
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
    --help|-h)
      cat <<'EOF'
Usage:
  ./scripts/preflight.sh [--mode general|bench|build]

Checks host dependencies, resolved Chromium binary path, and Doe runtime library path.
EOF
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "${mode}" != "general" && "${mode}" != "bench" && "${mode}" != "build" ]]; then
  echo "invalid --mode: ${mode} (expected general|bench|build)" >&2
  exit 2
fi

failure_count=0

check_cmd() {
  local cmd="$1"
  local required="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    printf "[ok]   %s -> %s\n" "${cmd}" "$(command -v "${cmd}")"
    return 0
  fi
  if [[ "${required}" == "required" ]]; then
    printf "[fail] %s missing (required)\n" "${cmd}" >&2
    failure_count=$((failure_count + 1))
  else
    printf "[warn] %s missing (optional)\n" "${cmd}" >&2
  fi
}

check_path() {
  local label="$1"
  local path="$2"
  local kind="$3"
  if [[ "${kind}" == "exec" ]]; then
    if [[ -x "${path}" ]]; then
      printf "[ok]   %s -> %s\n" "${label}" "${path}"
    else
      printf "[warn] %s missing executable: %s\n" "${label}" "${path}" >&2
    fi
    return 0
  fi
  if [[ -f "${path}" ]]; then
    printf "[ok]   %s -> %s\n" "${label}" "${path}"
  else
    printf "[warn] %s missing file: %s\n" "${label}" "${path}" >&2
  fi
}

echo "lane: ${FAWN_CHROMIUM_LANE_DIR}"
echo "repo: ${FAWN_REPO_ROOT}"
echo "host: $(uname -s) $(uname -m)"
echo "mode: ${mode}"
echo

check_cmd "git" "required"
check_cmd "python3" "required"
check_cmd "node" "required"
check_cmd "zig" "optional"
check_cmd "rg" "optional"
check_cmd "jq" "optional"

if [[ "${mode}" == "build" || "${mode}" == "general" ]]; then
  check_cmd "fetch" "optional"
  check_cmd "gclient" "optional"
  check_cmd "gn" "optional"
  check_cmd "autoninja" "optional"
fi

if [[ "$(fawn_host_os)" == linux* ]]; then
  check_cmd "apt-get" "optional"
  check_cmd "dpkg-deb" "optional"
fi

if [[ "${mode}" == "bench" || "${mode}" == "general" ]]; then
  check_cmd "npm" "optional"
fi

echo
chrome_bin="$(fawn_resolve_chrome_binary)"
doe_lib="$(fawn_resolve_doe_lib)"
check_path "chrome-bin" "${chrome_bin}" "exec"
check_path "doe-lib" "${doe_lib}" "file"

echo
if [[ "${failure_count}" -gt 0 ]]; then
  echo "preflight failed with ${failure_count} required dependency errors" >&2
  exit 1
fi
echo "preflight passed"
