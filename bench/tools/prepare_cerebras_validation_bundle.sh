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
  1. run_cerebras_evidence_bundle.py   (5 local gates)
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

step() {
    local name="$1"; shift
    echo
    echo "=== $name ==="
    "$@"
}

step "1/3  gates: run_cerebras_evidence_bundle.py" \
    python3 bench/tools/run_cerebras_evidence_bundle.py

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
