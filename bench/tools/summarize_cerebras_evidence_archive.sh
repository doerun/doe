#!/usr/bin/env bash
# Summarize a packed Cerebras evidence archive WITHOUT extracting it.
# Operates on the tarball via `tar -xzO | jq`, prints human-readable
# status for E2B, 31B, 26B/A4B MoE, the bundle-level gate verdict,
# RDRR Q4_K_M smoke parity, and claimable-depth coverage.
#
# Usage:
#   bench/tools/summarize_cerebras_evidence_archive.sh <archive.tar.gz>
#
# Exits 0 on clean summary, 1 if the archive is unreadable or a
# required file is missing (most likely a malformed bundle).

set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
summarize_cerebras_evidence_archive.sh — quick status from inside an archive

Prints E2B, 31B, 26B/A4B MoE status + bundle gate verdict +
RDRR Q4_K_M parity + claimable-depth coverage, entirely from the
tarball via `tar -xzO | jq`.
No extraction to disk.

Usage:
  bench/tools/summarize_cerebras_evidence_archive.sh <archive.tar.gz>

Exits 0 on clean summary; 1 if the archive is unreadable or
missing a required file (likely a malformed bundle).
EOF
    exit 0
fi

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <doe-cerebras-evidence-*.tar.gz>" >&2
    echo "run with --help for details" >&2
    exit 2
fi

ARCHIVE="$1"

if [[ ! -f "$ARCHIVE" ]]; then
    echo "FAIL: archive not found: $ARCHIVE" >&2
    exit 1
fi

extract_json() {
    # $1: path inside the archive
    # $2: jq filter
    if ! tar -xzO -f "$ARCHIVE" "$1" 2>/dev/null | jq -r "$2"; then
        echo "(error reading $1)"
        return 1
    fi
}

echo "=== archive: $(basename "$ARCHIVE") ==="
echo

echo "--- BUNDLE META ---"
extract_json "BUNDLE_META.json" '
    "builtUtc:       \(.builtUtc)",
    "gitShortSha:    \(.gitShortSha)",
    "gitDirtyTree:   \(.gitDirtyTree)",
    "archiveFilename:\(.archiveFilename)",
    "csPythonAvailableOnBundler: \(.csPython.csPythonAvailableOnBundler)"
'
echo

echo "--- E2B (primary_correctness_target) ---"
extract_json "bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json" '
    "executionStatus:   \(.executionStatus)",
    "executionBlocker:  \(.executionBlocker)",
    "laneStatus:        \(.laneStatus)",
    (if (.realWeightEvidence // empty) then
        "realWeight criteria met: " +
        ([.realWeightEvidence.promotionCriteriaMet | to_entries[] | select(.value) | .key] | length | tostring) +
        "/" + (.realWeightEvidence.promotionCriteriaMet | length | tostring)
    else "realWeightEvidence: absent" end)
'
echo

echo "--- 31B (dense_scale_target) ---"
extract_json "bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json" '
    "executionStatus:   \(.executionStatus)",
    "executionBlocker:  \(.executionBlocker)",
    "laneStatus:        \(.laneStatus)",
    (if (.realWeightEvidence // empty) then
        "realWeight criteria met: " +
        ([.realWeightEvidence.promotionCriteriaMet | to_entries[] | select(.value) | .key] | length | tostring) +
        "/" + (.realWeightEvidence.promotionCriteriaMet | length | tostring)
    else "realWeightEvidence: absent" end)
'
echo

echo "--- 26B/A4B MoE (blocked_efficiency_lane) ---"
extract_json "bench/out/26b-moe-lane/lane-status.json" '
    "laneLabel:         \(.laneLabel)",
    "laneStatus:        \(.laneStatus)",
    "laneBlocker:       \(.laneBlocker)",
    "missingReceipts:   \(.missingReceipts | length) of \(.todoReceipts | length) TODOs"
'
echo

echo "--- evidence bundle gate verdict ---"
extract_json "bench/out/cerebras-evidence-bundle/summary.json" '
    "verdict:           \(.verdict)",
    "passedSteps:       \(.passedSteps)/\(.totalSteps)",
    "skippedSteps:      \(.skippedSteps)"
'
echo

echo "--- Doppler RDRR Q4_K_M smoke parity ---"
extract_json "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json" '
    "verdict:           \(.verdict // "?")",
    "status:            \(.status // "?")",
    "weightSetSha256:   \((.weightSetSha256 // "")[0:16])..."
' 2>/dev/null || echo "rdrr-q4k-parity: not present"
echo

echo "--- E2B L2 diagnostic parity ---"
extract_json "bench/out/gemma-4-e2b-real-weight-parity-L2.json" '
    "bf16 verdict:      \(.verdict // "?")",
    "bf16 layers:       \(.parity.layersCompared // "?")",
    "bf16 tolerance:    \(.parity.tolerancePassed // "?")"
' 2>/dev/null || echo "bf16-l2-parity: not present"
extract_json "bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity-L2.json" '
    "rdrr verdict:      \(.verdict // "?")",
    "rdrr layers:       \(.paritySummary.layersCompared // "?")",
    "rdrr tolerance:    \(.paritySummary.tolerancePassed // "?")"
' 2>/dev/null || echo "rdrr-q4k-l2-parity: not present"
echo

echo "--- claimable depth coverage ---"
extract_json "bench/out/doe-run/depth-coverage-matrix.json" '
    "claimableAny:      \(.rollup.anyEligibleReceiptCount)/\(.rollup.declaredCount)",
    "claimableFull:     \(.rollup.fullEligibleCoverageCount)/\(.rollup.declaredCount)",
    "claimableTol:      \(.rollup.claimableWithinToleranceCount)/\(.rollup.declaredCount)",
    "depths:            \(.rollup.depthsClaimableWithinTolerance | map("L=" + tostring) | join(", "))"
'
echo

echo "--- emulator local-debug verdict ---"
extract_json "bench/out/doppler-reference/csl-emulator-speed-verdict-L1.json" '
    "csl-emulator-speed-verdict-L1: \(.verdict // "?")"
' 2>/dev/null || echo "csl-emulator-speed-verdict-L1: not present"
