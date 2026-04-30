#!/usr/bin/env bash
# Doe-local cs_python wrapper that forces singularity-mode invocation,
# bypassing the SDK's default --direct-rootfs path.
#
# Why this exists: the canonical SDK cs_python wrapper at
# `$SDK_ROOT/cs_python` checks for `.direct-rootfs/host-bin/python3` first
# and uses it when present. Direct-rootfs mode does NOT bind `/cbcore`
# for cslc subprocesses, so the SDK paint flow fails with a
# `Could not find source code for "/cbcore/...csl"` cslc error.
# Singularity-mode binds `/cbcore` correctly because it executes inside
# the SIF namespace.
#
# This script picks the singularity path unconditionally when both
# singularity and the SIF are available. Falls back to the SDK's
# default cs_python when not.
#
# Usage: same as cs_python — pass the runner script + args.
#   cs_python_singularity.sh path/to/runner.py --num-layers 1 ...

set -euo pipefail

SDK_ROOT_CANDIDATES=(
    "${DOE_CSL_SDK_ROOT:-}"
    "${CEREBRAS_SDK_ROOT:-}"
    "${CSL_SDK_ROOT:-}"
    "/home/x/cerebras-sdk-2.10.0"
    "/home/x/cerebras-sdk"
)

SDK_ROOT=""
for candidate in "${SDK_ROOT_CANDIDATES[@]}"; do
    if [[ -n "$candidate" && -f "$candidate/cs_python" ]]; then
        SDK_ROOT="$candidate"
        break
    fi
done

if [[ -z "$SDK_ROOT" ]]; then
    echo "cs_python_singularity: no Cerebras SDK root with cs_python found" >&2
    exit 2
fi

# Find the SIF adjacent to the SDK install.
shopt -s nullglob
SIFS=("$SDK_ROOT"/*.sif)
shopt -u nullglob

SINGULARITY_BIN=""
for cmd in singularity apptainer; do
    if command -v "$cmd" &>/dev/null; then
        SINGULARITY_BIN="$cmd"
        break
    fi
done

# Fall back to the SDK default if singularity or SIF missing.
if [[ -z "$SINGULARITY_BIN" || ${#SIFS[@]} -eq 0 ]]; then
    exec "$SDK_ROOT/cs_python" "$@"
fi

PWD_REAL=$(realpath "$(pwd)")
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DOE_REPO_REAL=$(realpath "$SCRIPT_DIR/../../..")
WORKSPACE_REAL=$(realpath "$DOE_REPO_REAL/..")
CONTAINER_SCRATCH_ROOT="${DOE_CSL_CONTAINER_SCRATCH:-$DOE_REPO_REAL/bench/out/scratch/csl-container}"
CONTAINER_TMP="${DOE_CSL_TMPDIR:-${DOE_CSL_CONTAINER_TMP:-$CONTAINER_SCRATCH_ROOT/tmp}}"
CONTAINER_CACHE="${DOE_CSL_CONTAINER_CACHE:-$CONTAINER_SCRATCH_ROOT/cache}"
if [[ "$CONTAINER_TMP" != /* ]]; then
    CONTAINER_TMP="$DOE_REPO_REAL/$CONTAINER_TMP"
fi
if [[ "$CONTAINER_CACHE" != /* ]]; then
    CONTAINER_CACHE="$DOE_REPO_REAL/$CONTAINER_CACHE"
fi
mkdir -p "$CONTAINER_TMP" "$CONTAINER_CACHE"
CONTAINER_TMP=$(realpath "$CONTAINER_TMP")
CONTAINER_CACHE=$(realpath "$CONTAINER_CACHE")
if [[ -z "${TMPDIR:-}" || "${TMPDIR:-}" == "/tmp" ]]; then
    export TMPDIR="$CONTAINER_TMP"
fi
if [[ -z "${APPTAINER_TMPDIR:-}" || "${APPTAINER_TMPDIR:-}" == "/tmp" ]]; then
    export APPTAINER_TMPDIR="$CONTAINER_TMP"
fi
if [[ -z "${SINGULARITY_TMPDIR:-}" || "${SINGULARITY_TMPDIR:-}" == "/tmp" ]]; then
    export SINGULARITY_TMPDIR="$CONTAINER_TMP"
fi
export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-$CONTAINER_CACHE}"
export SINGULARITY_CACHEDIR="${SINGULARITY_CACHEDIR:-$CONTAINER_CACHE}"
TMP_BIND="${TMPDIR:-$CONTAINER_TMP}"
export CSL_SUPPRESS_SIMFAB_TRACE="${CSL_SUPPRESS_SIMFAB_TRACE:-1}"

# Optional scratch-cwd redirect: cslc, sim runners, and the SDK paint
# flow all create scratch in the cwd (executables/, sim_stats.json,
# wio_flows_tmpdir*). When DOE_CSL_SCRATCH_CWD is set the wrapper cd's
# there before exec, so scratch lands inside the named workspace dir
# instead of the repo root. Unset behavior is unchanged for legacy
# callers; new callers should set this to a path under
# `bench/out/scratch/` (gitignored).
if [[ -n "${DOE_CSL_SCRATCH_CWD:-}" ]]; then
    mkdir -p "$DOE_CSL_SCRATCH_CWD"
    SCRATCH_REAL=$(realpath "$DOE_CSL_SCRATCH_CWD")
    cd "$SCRATCH_REAL"
    PWD_REAL="$SCRATCH_REAL"
fi

# Singularity's `-C` (containall) flag strips parent env vars from the
# container. Doe-side runtime helpers (e.g.,
# `int4ple_compile_target_sim_runner.cs_python_executable()`) read
# `DOE_CSL_*` vars to discover the right SDK invocation. Forward them
# via singularity's `SINGULARITYENV_<NAME>` convention so the prefix is
# stripped inside the container and the var lands as `<NAME>`.
for var in \
    DOE_CSL_CS_PYTHON \
    DOE_CSL_SDK_ROOT \
    DOE_CSLC_EXECUTABLE \
    DOE_CSL_SIM_RUNNER_EXECUTABLE \
    DOE_CSL_RUNTIME_TIMEOUT_SECONDS \
    DOE_CSL_CMADDR \
    CSL_SUPPRESS_SIMFAB_TRACE
do
    val="${!var:-}"
    if [[ -n "$val" ]]; then
        export "SINGULARITYENV_$var=$val"
    fi
done

# Override DOE_CSL_RUNTIME_EXECUTABLE to the in-container python path
# regardless of host value. If the host caller set it to this very
# wrapper (a common case when the SDK driver chains the call), then
# propagating the host value into the container would tell the
# in-container int4ple runner to invoke this wrapper again, which
# would attempt to spawn a nested `singularity exec` — and singularity
# inside singularity is not supported. The in-container python sits at
# `/python/python-x86_64/bin/python` (per the SDK rootfs's PATH), so
# point the in-container helpers at that directly. Inner subprocesses
# then bypass the wrapper and run python natively under the active
# container.
export SINGULARITYENV_DOE_CSL_RUNTIME_EXECUTABLE=/python/python-x86_64/bin/python

exec "$SINGULARITY_BIN" exec \
    "--bind=${WORKSPACE_REAL}" \
    "--bind=${DOE_REPO_REAL}" \
    "--bind=${PWD_REAL}" \
    "--pwd=${PWD_REAL}" \
    -C \
    "--bind=${TMP_BIND}:/tmp" \
    -- "${SIFS[0]}" \
    python "$@"
