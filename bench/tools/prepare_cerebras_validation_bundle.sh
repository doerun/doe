#!/usr/bin/env bash
# End-to-end Cerebras validation bundle preparation.
#
#   gates (run_cerebras_evidence_bundle.py)
#     -> pack (pack_cerebras_validation_archive.py)
#       -> verify (verify_cerebras_validation_archive.py)
#
# Intended as the single command a bundler runs before attaching an
# archive to an external email. Exits 0 iff every step passes; exits
# non-zero on any failure. Prints the final archive path + git sha
# for downstream copy-paste.
#
# Usage:
#   bench/tools/prepare_cerebras_validation_bundle.sh
#
# The three underlying scripts each exit 0 on success. This wrapper
# runs them in sequence so an operator does not have to remember the
# order.

set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
prepare_cerebras_validation_bundle.sh — one-command Cerebras bundle prep

Chains in sequence:
  1. run_cerebras_evidence_bundle.py   (local evidence gates)
  2. pack_cerebras_validation_archive.py   (builds dated tarball)
  3. verify_cerebras_validation_archive.py   (manifest + claim-role + claim-discipline scan)

Output: bench/out/doe-cerebras-evidence-YYYYMMDD-HHMM-<shortSha>[-dirty].tar.gz

Usage:
  bench/tools/prepare_cerebras_validation_bundle.sh        run the full chain
  bench/tools/prepare_cerebras_validation_bundle.sh --help show this message

Exits 0 iff every step passes; non-zero on first failure.
Run from any directory; the script cd's to the repo root.
EOF
    exit 0
fi

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

SIM_STATS_WAS_CLEAN=0
if [[ -f sim_stats.json && -z "$(git status --porcelain -- sim_stats.json 2>/dev/null)" ]]; then
    SIM_STATS_WAS_CLEAN=1
fi

step() {
    local name="$1"; shift
    echo
    echo "=== $name ==="
    "$@"
}

step "1/3  gates: run_cerebras_evidence_bundle.py" \
    python3 bench/tools/run_cerebras_evidence_bundle.py

if [[ "$SIM_STATS_WAS_CLEAN" -eq 1 && -n "$(git status --porcelain -- sim_stats.json 2>/dev/null)" ]]; then
    git restore -- sim_stats.json
fi

step "2/3  pack: pack_cerebras_validation_archive.py" \
    python3 bench/tools/pack_cerebras_validation_archive.py

# Find the newest archive for step 3 — the packer prints the filename
# it wrote, but we rediscover it from disk to avoid parsing stdout.
ARCHIVE="$(ls -t bench/out/doe-cerebras-evidence-*.tar.gz 2>/dev/null | head -1)"
if [[ -z "${ARCHIVE}" ]]; then
    echo "FAIL: no archive found at bench/out/doe-cerebras-evidence-*.tar.gz" >&2
    exit 1
fi

step "3/3  verify: verify_cerebras_validation_archive.py --archive $ARCHIVE" \
    python3 bench/tools/verify_cerebras_validation_archive.py --archive "$ARCHIVE"

# Refresh docs/cerebras-evidence-bundle-pointer.md with the current
# archive's pinned values so the appendix stays stable while the
# pointer tracks the latest build. Written AFTER verify passes, so
# the pointer is never stamped with unverified bytes.
POINTER="docs/cerebras-evidence-bundle-pointer.md"
ARCHIVE_SHA="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
MANIFEST_SHA="$(tar -xzOf "$ARCHIVE" MANIFEST.txt | sha256sum | awk '{print $1}')"
META_SHA="$(tar -xzOf "$ARCHIVE" BUNDLE_META.json | sha256sum | awk '{print $1}')"
ARCHIVE_SIZE="$(stat --printf=%s "$ARCHIVE" 2>/dev/null || stat -f%z "$ARCHIVE")"
GIT_COMMIT="$(git rev-parse HEAD)"
GIT_STATE="clean"
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    GIT_STATE="dirty"
fi
# Bundle verdict from the inner summary, for at-a-glance trust signal.
BUNDLE_VERDICT="$(tar -xzOf "$ARCHIVE" bench/out/cerebras-evidence-bundle/summary.json | jq -r '.verdict // "unknown"' 2>/dev/null)"
BUNDLE_PASSED="$(tar -xzOf "$ARCHIVE" bench/out/cerebras-evidence-bundle/summary.json | jq -r '.passedSteps // "?"' 2>/dev/null)"
BUNDLE_TOTAL="$(tar -xzOf "$ARCHIVE" bench/out/cerebras-evidence-bundle/summary.json | jq -r '.totalSteps // "?"' 2>/dev/null)"
cat > "$POINTER" <<EOF
# Cerebras evidence bundle — current pointer

**Auto-generated** by
\`bench/tools/prepare_cerebras_validation_bundle.sh\` on each clean
run. Do not hand-edit; the prep script overwrites this file so it
always reflects the last successful pack.

## Latest archive

| Field | Value |
| --- | --- |
| archive | \`$ARCHIVE\` |
| archive sha256 | \`$ARCHIVE_SHA\` |
| MANIFEST.txt sha256 | \`$MANIFEST_SHA\` |
| BUNDLE_META.json sha256 | \`$META_SHA\` |
| archive size (bytes) | \`$ARCHIVE_SIZE\` |
| git commit | \`$GIT_COMMIT\` |
| git dirty | \`$GIT_STATE\` |
| evidence bundle verdict | \`$BUNDLE_VERDICT\` ($BUNDLE_PASSED/$BUNDLE_TOTAL steps) |

## Verify the bytes you received

\`\`\`bash
python3 bench/tools/verify_cerebras_validation_archive.py \\
    --archive <path-to-received-archive>
\`\`\`

Expected: \`PASS ... manifest sha integrity OK, claim-role taxonomy
clean, BUNDLE_META complete, claim-discipline scan clean\`.

## Summarize without unpacking

\`\`\`bash
bench/tools/summarize_cerebras_evidence_archive.sh <path-to-archive>
\`\`\`

## Reproducibility note

If \`git dirty\` is \`dirty\`, the bundle was built from an uncommitted
working tree; rebuild from a clean tree before external circulation.
The archive's own \`BUNDLE_META.json\` is the authoritative source of
truth for any bundle in hand — this file just mirrors the values
from the last prep-script run on the repo.
EOF
echo
echo "refreshed $POINTER"

echo
echo "=== PREP DONE ==="
echo "archive:     $ARCHIVE"
echo "size:        $(stat --printf=%s "$ARCHIVE" 2>/dev/null || stat -f%z "$ARCHIVE") bytes"
echo "git commit:  $(git rev-parse HEAD)"
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    echo "git tree:    DIRTY — prefer a clean rebuild before external circulation"
else
    echo "git tree:    clean"
fi
echo
echo "Next step: attach $ARCHIVE and the unpacked README.md to the external ask."
