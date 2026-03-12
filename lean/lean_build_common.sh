#!/usr/bin/env bash
# Shared toolchain resolution and Lean compilation block.
# Source this file after BUILD_DIR is set by the caller.
# Sets: ROOT_DIR, TOOLCHAIN_VERSION, TOOLCHAIN_REF, LEAN_BIN

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

# Core layer (canonical sources).
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
