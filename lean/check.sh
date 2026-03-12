#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR="$(mktemp -d /tmp/fawn-lean-check.XXXXXX)"
trap 'rm -rf "${BUILD_DIR}"' EXIT
mkdir -p "${BUILD_DIR}/Fawn/Core"
mkdir -p "${BUILD_DIR}/Fawn/Full"

# shellcheck source=lean_build_common.sh
. "$(dirname "${BASH_SOURCE[0]}")/lean_build_common.sh"

echo "lean-check: ok (${TOOLCHAIN_REF})"
