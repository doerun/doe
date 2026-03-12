#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR="$(mktemp -d /tmp/fawn-lean-extract.XXXXXX)"
trap 'rm -rf "${BUILD_DIR}"' EXIT
mkdir -p "${BUILD_DIR}/Fawn/Core"
mkdir -p "${BUILD_DIR}/Fawn/Full"

# shellcheck source=lean_build_common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lean_build_common.sh"

ARTIFACT_DIR="${ROOT_DIR}/lean/artifacts"
ARTIFACT_PATH="${ARTIFACT_DIR}/proven-conditions.json"
mkdir -p "${ARTIFACT_DIR}"

# Run extraction: compile Extract.lean and execute its main to produce the artifact.
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" --run "${ROOT_DIR}/lean/Fawn/Extract.lean" > "${ARTIFACT_PATH}"

echo "lean-extract: artifact written to ${ARTIFACT_PATH} (${TOOLCHAIN_REF})"
