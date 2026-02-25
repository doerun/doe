#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LANE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
EXTERNAL_ENV_FILE="${LANE_DIR}/.external-macos.env"

if [[ -f "${EXTERNAL_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${EXTERNAL_ENV_FILE}"
fi

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/env.sh"

if [[ ! -d "${LANE_DIR}/src" ]]; then
  echo "missing lane src checkout: ${LANE_DIR}/src" >&2
  echo "run fetch/gclient sync first." >&2
  exit 1
fi

cd "${LANE_DIR}/src"

if [[ ! -f "out/fawn_release/args.gn" ]]; then
  gn gen out/fawn_release --args='is_debug=false'
fi

autoninja -C out/fawn_release chrome "$@"
"${SCRIPT_DIR}/sync-release-artifacts-local.sh" "out/fawn_release"
