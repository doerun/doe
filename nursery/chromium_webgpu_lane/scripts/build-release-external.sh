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

MACOS_APP="${SCRIPT_DIR}/../src/out/fawn_release/Chromium.app"
if [[ "$(uname -s)" == "Darwin" && -x "${MACOS_APP}/Contents/MacOS/Chromium" ]]; then
  "${SCRIPT_DIR}/patch-chromium-app-doe.sh" --app "${MACOS_APP}" || \
    echo "warning: unable to patch app default runtime flags" >&2
fi

"${SCRIPT_DIR}/sync-release-artifacts-local.sh" "out/fawn_release"

if [[ "$(uname -s)" == "Darwin" ]]; then
  LOCAL_OUT="${FAWN_CHROMIUM_RELEASE_LOCAL_OUT:-${LANE_DIR}/out/fawn_release_local}"
  LOCAL_APP_NAME="${FAWN_CHROMIUM_LOCAL_APP_NAME:-Fawn.app}"
  LOCAL_APP_PATH="${LOCAL_OUT}/${LOCAL_APP_NAME}"
  HOST_APP_PATH="${FAWN_CHROMIUM_HOST_APP_PATH:-${HOME}/Applications/Fawn.app}"

  if [[ -d "${LOCAL_APP_PATH}" ]]; then
    mkdir -p "$(dirname "${HOST_APP_PATH}")"
    rsync -a --delete "${LOCAL_APP_PATH}/" "${HOST_APP_PATH}/"
    echo "copied app bundle to host path: ${HOST_APP_PATH}"
  else
    echo "local app copy skipped; missing: ${LOCAL_APP_PATH}" >&2
  fi
fi
