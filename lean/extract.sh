#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLCHAIN_VERSION="$(jq -r '.toolchains.lean.version // empty' "$ROOT_DIR/config/toolchains.json" 2>/dev/null || true)"

if [[ -z "${TOOLCHAIN_VERSION}" ]]; then
  TOOLCHAIN_VERSION="4.16.0"
fi

if [[ "${TOOLCHAIN_VERSION}" == v* ]]; then
  TOOLCHAIN_REF="leanprover/lean4:${TOOLCHAIN_VERSION}"
else
  TOOLCHAIN_REF="leanprover/lean4:v${TOOLCHAIN_VERSION}"
fi

if [[ -x "${HOME}/.elan/bin/lean" ]]; then
  LEAN_BIN="${HOME}/.elan/bin/lean"
elif command -v lean >/dev/null 2>&1; then
  LEAN_BIN="$(command -v lean)"
else
  echo "lean binary not found. Install Lean with elan first." >&2
  exit 1
fi

BUILD_DIR="$(mktemp -d /tmp/fawn-lean-extract.XXXXXX)"
trap 'rm -rf "${BUILD_DIR}"' EXIT
mkdir -p "${BUILD_DIR}/Fawn/Core"
mkdir -p "${BUILD_DIR}/Fawn/Full"

ARTIFACT_DIR="${ROOT_DIR}/lean/artifacts"
ARTIFACT_PATH="${ARTIFACT_DIR}/proven-conditions.json"
mkdir -p "${ARTIFACT_DIR}"

# Core layer (canonical sources, same order as check.sh).
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Core/Model.olean" "${ROOT_DIR}/lean/Fawn/Core/Model.lean"
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Core/Runtime.olean" "${ROOT_DIR}/lean/Fawn/Core/Runtime.lean"
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Core/Dispatch.olean" "${ROOT_DIR}/lean/Fawn/Core/Dispatch.lean"
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Core/Bridge.olean" "${ROOT_DIR}/lean/Fawn/Core/Bridge.lean"

# Full layer (canonical sources).
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Full/Comparability.olean" "${ROOT_DIR}/lean/Fawn/Full/Comparability.lean"
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Full/ComparabilityFixtures.olean" "${ROOT_DIR}/lean/Fawn/Full/ComparabilityFixtures.lean"

# Re-export shims (backward compatibility).
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Model.olean" "${ROOT_DIR}/lean/Fawn/Model.lean"
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Runtime.olean" "${ROOT_DIR}/lean/Fawn/Runtime.lean"
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Dispatch.olean" "${ROOT_DIR}/lean/Fawn/Dispatch.lean"
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Comparability.olean" "${ROOT_DIR}/lean/Fawn/Comparability.lean"
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/ComparabilityFixtures.olean" "${ROOT_DIR}/lean/Fawn/ComparabilityFixtures.lean"
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" -o "${BUILD_DIR}/Fawn/Bridge.olean" "${ROOT_DIR}/lean/Fawn/Bridge.lean"

# Run extraction: compile Extract.lean and execute its main to produce the artifact.
LEAN_PATH="${BUILD_DIR}:${ROOT_DIR}/lean" \
  "${LEAN_BIN}" "+${TOOLCHAIN_REF}" --run "${ROOT_DIR}/lean/Fawn/Extract.lean" > "${ARTIFACT_PATH}"

echo "lean-extract: artifact written to ${ARTIFACT_PATH} (${TOOLCHAIN_REF})"
