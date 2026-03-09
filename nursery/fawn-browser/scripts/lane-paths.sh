#!/usr/bin/env bash
set -euo pipefail

FAWN_LANE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAWN_CHROMIUM_LANE_DIR="$(cd "${FAWN_LANE_SCRIPT_DIR}/.." && pwd)"
FAWN_REPO_ROOT="$(cd "${FAWN_CHROMIUM_LANE_DIR}/../.." && pwd)"

fawn_host_os() {
  uname -s | tr '[:upper:]' '[:lower:]'
}

fawn_doe_lib_extension() {
  local os_name
  os_name="$(fawn_host_os)"
  case "${os_name}" in
    darwin*) echo "dylib" ;;
    msys*|mingw*|cygwin*|windows*) echo "dll" ;;
    *) echo "so" ;;
  esac
}

fawn_default_doe_lib_candidates() {
  local extension
  extension="$(fawn_doe_lib_extension)"
  printf "%s\n" \
    "${FAWN_REPO_ROOT}/zig/zig-out/lib/libwebgpu_doe.${extension}" \
    "${FAWN_REPO_ROOT}/zig/zig-out/lib/libwebgpu_doe.so" \
    "${FAWN_REPO_ROOT}/zig/zig-out/lib/libwebgpu_doe.dylib" \
    "${FAWN_REPO_ROOT}/zig/zig-out/lib/libwebgpu_doe.dll"
}

fawn_default_chrome_candidates() {
  local release_local_out
  local chromium_lane_out
  local home_fawn_app
  release_local_out="${FAWN_CHROMIUM_RELEASE_LOCAL_OUT:-${FAWN_CHROMIUM_LANE_DIR}/out/fawn_release_local}"
  chromium_lane_out="${FAWN_REPO_ROOT}/nursery/chromium_webgpu_lane/out/fawn_release_local"
  home_fawn_app="${HOME}/Applications/Fawn.app/Contents/MacOS/Chromium"
  printf "%s\n" \
    "${release_local_out}/chrome" \
    "${release_local_out}/Fawn.app/Contents/MacOS/Chromium" \
    "${release_local_out}/Chromium.app/Contents/MacOS/Chromium" \
    "${chromium_lane_out}/chrome" \
    "${chromium_lane_out}/Fawn.app/Contents/MacOS/Chromium" \
    "${chromium_lane_out}/Chromium.app/Contents/MacOS/Chromium" \
    "${home_fawn_app}" \
    "${FAWN_CHROMIUM_LANE_DIR}/src/out/fawn_release/chrome" \
    "${FAWN_CHROMIUM_LANE_DIR}/src/out/fawn_release/Fawn.app/Contents/MacOS/Chromium" \
    "${FAWN_CHROMIUM_LANE_DIR}/src/out/fawn_release/Chromium.app/Contents/MacOS/Chromium" \
    "${FAWN_REPO_ROOT}/nursery/chromium_webgpu_lane/src/out/fawn_release/chrome" \
    "${FAWN_REPO_ROOT}/nursery/chromium_webgpu_lane/src/out/fawn_release/Fawn.app/Contents/MacOS/Chromium" \
    "${FAWN_REPO_ROOT}/nursery/chromium_webgpu_lane/src/out/fawn_release/Chromium.app/Contents/MacOS/Chromium" \
    "${FAWN_CHROMIUM_LANE_DIR}/src/out/fawn_debug/chrome" \
    "${FAWN_CHROMIUM_LANE_DIR}/src/out/fawn_debug/Fawn.app/Contents/MacOS/Chromium" \
    "${FAWN_CHROMIUM_LANE_DIR}/src/out/fawn_debug/Chromium.app/Contents/MacOS/Chromium" \
    "${FAWN_REPO_ROOT}/nursery/chromium_webgpu_lane/src/out/fawn_debug/chrome" \
    "${FAWN_REPO_ROOT}/nursery/chromium_webgpu_lane/src/out/fawn_debug/Fawn.app/Contents/MacOS/Chromium" \
    "${FAWN_REPO_ROOT}/nursery/chromium_webgpu_lane/src/out/fawn_debug/Chromium.app/Contents/MacOS/Chromium"
}

fawn_resolve_doe_lib() {
  local override
  override="${1:-${FAWN_DOE_LIB:-}}"
  if [[ -n "${override}" ]]; then
    echo "${override}"
    return 0
  fi

  local candidates=()
  while IFS= read -r candidate; do
    candidates+=("${candidate}")
  done < <(fawn_default_doe_lib_candidates)

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  echo "${candidates[0]}"
}

fawn_resolve_chrome_binary() {
  local override
  override="${1:-${FAWN_CHROME_BIN:-}}"
  if [[ -n "${override}" ]]; then
    echo "${override}"
    return 0
  fi

  local candidates=()
  while IFS= read -r candidate; do
    candidates+=("${candidate}")
  done < <(fawn_default_chrome_candidates)

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "${candidate}" ]]; then
      echo "${candidate}"
      return 0
    fi
  done

  echo "${candidates[0]}"
}
