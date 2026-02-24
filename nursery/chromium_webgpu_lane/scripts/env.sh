#!/usr/bin/env bash
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "Source this file from your shell: source ./scripts/env.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LANE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

prepend_path() {
  local dir="$1"
  if [[ -d "${dir}" ]]; then
    PATH="${dir}:${PATH}"
  fi
}

prepend_path "${LANE_DIR}/depot_tools"
prepend_path "${LANE_DIR}/cache/tools/gperf_pkg/usr/bin"

HOST_TOOLS_DIR="${LANE_DIR}/cache/tools/host_tools"
if [[ -d "${HOST_TOOLS_DIR}" ]]; then
  while IFS= read -r -d '' bin_dir; do
    prepend_path "${bin_dir}"
  done < <(find "${HOST_TOOLS_DIR}" -type d -path "*/usr/bin" -print0 | sort -z)
fi

export CHROMIUM_WEBGPU_LANE_ROOT="${LANE_DIR}"
export PATH

if [[ "${FAWN_CHROMIUM_LANE_QUIET:-0}" != "1" ]]; then
  echo "Chromium lane env enabled: ${CHROMIUM_WEBGPU_LANE_ROOT}"
fi
