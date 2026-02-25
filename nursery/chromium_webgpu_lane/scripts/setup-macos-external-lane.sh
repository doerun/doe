#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LANE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_VOLUME="/Volumes/fawn"
VOLUME_PATH="${1:-${FAWN_EXTERNAL_VOLUME:-${DEFAULT_VOLUME}}}"
EXTERNAL_ROOT="${FAWN_EXTERNAL_LANE_ROOT:-${VOLUME_PATH}/chromium_webgpu_lane}"
EXTERNAL_DEPOT_TOOLS="${EXTERNAL_ROOT}/depot_tools"
EXTERNAL_SRC="${EXTERNAL_ROOT}/src"
EXTERNAL_CACHE="${EXTERNAL_ROOT}/cache"
LOCAL_RELEASE_OUT="${LANE_DIR}/out/fawn_release_local"
EXTERNAL_ENV_FILE="${LANE_DIR}/.external-macos.env"

if [[ ! -d "${VOLUME_PATH}" ]]; then
  echo "missing external volume path: ${VOLUME_PATH}" >&2
  echo "finish formatting/mounting, then re-run this script." >&2
  exit 1
fi

if [[ ! -w "${VOLUME_PATH}" ]]; then
  echo "external volume is not writable: ${VOLUME_PATH}" >&2
  exit 1
fi

mkdir -p "${EXTERNAL_ROOT}" "${EXTERNAL_SRC}" "${EXTERNAL_CACHE}" "${LOCAL_RELEASE_OUT}"

link_lane_path() {
  local lane_path="$1"
  local target_path="$2"

  if [[ -L "${lane_path}" ]]; then
    local current_target
    current_target="$(readlink "${lane_path}")"
    if [[ "${current_target}" == "${target_path}" ]]; then
      return
    fi
    ln -sfn "${target_path}" "${lane_path}"
    return
  fi

  if [[ -e "${lane_path}" ]]; then
    echo "refusing to replace non-symlink path: ${lane_path}" >&2
    echo "move it aside manually, then re-run." >&2
    exit 1
  fi

  ln -s "${target_path}" "${lane_path}"
}

link_lane_path "${LANE_DIR}/src" "${EXTERNAL_SRC}"
link_lane_path "${LANE_DIR}/depot_tools" "${EXTERNAL_DEPOT_TOOLS}"
link_lane_path "${LANE_DIR}/cache" "${EXTERNAL_CACHE}"

cat > "${EXTERNAL_ENV_FILE}" <<EOF
export FAWN_CHROMIUM_EXTERNAL_VOLUME="${VOLUME_PATH}"
export FAWN_CHROMIUM_EXTERNAL_ROOT="${EXTERNAL_ROOT}"
export FAWN_CHROMIUM_EXTERNAL_SRC="${EXTERNAL_SRC}"
export FAWN_CHROMIUM_EXTERNAL_CACHE="${EXTERNAL_CACHE}"
export FAWN_CHROMIUM_RELEASE_LOCAL_OUT="${LOCAL_RELEASE_OUT}"
EOF

echo "external lane configured:"
echo "  volume: ${VOLUME_PATH}"
echo "  external root: ${EXTERNAL_ROOT}"
echo "  lane src -> ${EXTERNAL_SRC}"
echo "  lane depot_tools -> ${EXTERNAL_DEPOT_TOOLS}"
echo "  lane cache -> ${EXTERNAL_CACHE}"
echo "  local release artifacts: ${LOCAL_RELEASE_OUT}"
echo "  env file: ${EXTERNAL_ENV_FILE}"

if [[ ! -d "${EXTERNAL_DEPOT_TOOLS}/.git" ]]; then
  echo
  echo "next: clone depot_tools into external storage:"
  echo "  git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git \"${EXTERNAL_DEPOT_TOOLS}\""
fi
