#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <matrix_report_json> [windows]"
  exit 2
fi

report="$1"
windows="${2:-3}"
dropin_artifact="zig/zig-out/lib/libwebgpu_doe.so"

echo "[1/5] validating matrix readiness report: $report"
python3 bench/check_full39_claim_readiness.py --report "$report"

echo "[2/5] running blocking gates + claim + drop-in"
python3 bench/run_blocking_gates.py \
  --report "$report" \
  --trace-semantic-parity-mode auto \
  --with-dropin-gate \
  --dropin-artifact "$dropin_artifact" \
  --with-claim-gate \
  --claim-require-comparison-status comparable \
  --claim-require-claim-status claimable \
  --claim-require-claimability-mode release \
  --claim-require-min-timed-samples 15 \
  --claim-expected-workload-contract bench/workloads.amd.vulkan.extended.json \
  --claim-require-workload-contract-hash \
  --claim-require-workload-id-set-match

echo "[3/5] running repeated release windows + substantiation gate"
python3 bench/run_release_claim_windows.py \
  --config bench/compare_dawn_vs_doe.config.amd.vulkan.release.json \
  --windows "$windows" \
  --strict-amd-vulkan \
  --with-dropin-gate \
  --dropin-artifact "$dropin_artifact" \
  --with-substantiation-gate

echo "[4/5] refreshing test inventory dashboard"
python3 bench/build_test_inventory_dashboard.py --report-glob "bench/out/**/dawn-vs-doe*.json"

echo "[5/5] refreshing baseline dataset package"
python3 bench/build_baseline_dataset.py --report-glob "bench/out/**/dawn-vs-doe*.json"

echo "PASS: matrix evidence bundle complete"
