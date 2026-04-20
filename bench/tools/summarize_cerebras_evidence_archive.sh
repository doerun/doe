#!/usr/bin/env bash
# Summarize a packed Cerebras evidence archive WITHOUT extracting it.
# Operates on the tarball via `tar -xzO | jq`, prints human-readable
# status for E2B, 31B, 26B/A4B MoE, and the bundle-level gate verdict.
#
# Usage:
#   bench/tools/summarize_cerebras_evidence_archive.sh <archive.tar.gz>
#
# Exits 0 on clean summary, 1 if the archive is unreadable or a
# required file is missing (most likely a malformed bundle).

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <doe-cerebras-evidence-*.tar.gz>" >&2
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

echo "--- emulator verdicts ---"
for f in \
    "bench/out/doppler-reference/csl-emulator-speed-verdict-L1.json" \
    "bench/out/doppler-reference/csl-emulator-speed-verdict-L35.json" \
    "bench/out/doppler-reference/csl-emulator-accuracy-verdict-L2.json"
do
    label="$(basename "$f" .json)"
    extract_json "$f" "\"$label: \" + (.verdict // \"?\")" 2>/dev/null || echo "$label: not present"
done
