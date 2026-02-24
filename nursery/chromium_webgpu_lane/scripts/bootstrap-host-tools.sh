#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LANE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEBS_DIR="${LANE_DIR}/cache/tools/debs"
TOOLS_DIR="${LANE_DIR}/cache/tools/host_tools"

PACKAGES=(
  gperf
  bison
  flex
  m4
)

mkdir -p "${DEBS_DIR}" "${TOOLS_DIR}"

download_pkg() {
  local pkg="$1"
  (
    cd "${DEBS_DIR}"
    apt-get download "${pkg}" >/dev/null
  )
}

extract_deb() {
  local deb="$1"
  local out_dir="${TOOLS_DIR}/$(basename "${deb}" .deb)"
  rm -rf "${out_dir}"
  mkdir -p "${out_dir}"
  dpkg-deb -x "${deb}" "${out_dir}"
}

for pkg in "${PACKAGES[@]}"; do
  download_pkg "${pkg}"
done

for deb in "${DEBS_DIR}"/*.deb; do
  extract_deb "${deb}"
done

echo "Host tools staged under: ${TOOLS_DIR}"
find "${TOOLS_DIR}" -type f -path "*/usr/bin/*" | rg -e "/(gperf|bison|flex|m4)$" || true
