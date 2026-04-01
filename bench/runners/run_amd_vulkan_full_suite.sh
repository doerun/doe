#!/usr/bin/env bash
# AMD Vulkan full comparison suite runner.
# Run from the doe repo root: bash bench/runners/run_amd_vulkan_full_suite.sh
#
# Runs all batched greedy logit hunts sequentially (one browser session at a time
# to avoid GPU contention on integrated AMD GPUs).
#
# Total estimated time on AMD Radeon iGPU:
#   270M 10-step: ~50 min (5 batches × ~10 min)
#   1B 10-step:   ~80 min (5 batches × ~16 min)
#   270M 32-step: ~120 min (9 batches × ~13 min)
#   Total:        ~4 hours
#
# Output goes to bench/out/amd-vulkan-full-greedy-{10step,32step}/

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

echo "=== AMD Vulkan Full Greedy Suite ==="
echo "Started: $(date -u +%Y%m%dT%H%M%SZ)"
echo

# Phase 1: Operator counterexamples (~2 min)
echo "--- Phase 1: Operator counterexamples ---"
python3 bench/runners/run_reduction_order_counterexample.py \
  --fixture bench/fixtures/determinism/amd-vulkan-reduction-order-dot-product.json \
  --output-root bench/out/amd-vulkan-reduction-order-dot-product 2>&1 | tail -1

python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/amd-vulkan-reduction-order-logit-flip.json \
  --output-root bench/out/amd-vulkan-reduction-order-logit-flip 2>&1 | tail -1

python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/amd-vulkan-attention-slice-logit-flip.json \
  --output-root bench/out/amd-vulkan-attention-slice-logit-flip 2>&1 | tail -1

python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/amd-vulkan-rmsnorm-slice-logit-flip.json \
  --output-root bench/out/amd-vulkan-rmsnorm-slice-logit-flip 2>&1 | tail -1

echo

# Phase 2a: 270M greedy 10-step
echo "--- Phase 2a: 270M greedy 10-step (206 prompts in 5 batches) ---"
for i in 0 1 2 3 4; do
  echo "  Batch $i: $(date +%H:%M:%S)"
  python3 bench/runners/run_real_logit_hunt.py \
    --fixture "bench/fixtures/determinism/amd-vulkan-full-greedy-10step.gemma270m.batch${i}.json" \
    --output-root bench/out/amd-vulkan-full-greedy-10step \
    --persist-logits 2>&1 | tail -1
done
echo

# Phase 2b: 1B greedy 10-step
echo "--- Phase 2b: 1B greedy 10-step (206 prompts in 5 batches) ---"
for i in 0 1 2 3 4; do
  echo "  Batch $i: $(date +%H:%M:%S)"
  python3 bench/runners/run_real_logit_hunt.py \
    --fixture "bench/fixtures/determinism/amd-vulkan-full-greedy-10step.gemma1b.batch${i}.json" \
    --output-root bench/out/amd-vulkan-full-greedy-10step \
    --persist-logits 2>&1 | tail -1
done
echo

# Phase 2c: 270M greedy 32-step
echo "--- Phase 2c: 270M greedy 32-step (206 prompts in 9 batches) ---"
for i in 0 1 2 3 4 5 6 7 8; do
  echo "  Batch $i: $(date +%H:%M:%S)"
  python3 bench/runners/run_real_logit_hunt.py \
    --fixture "bench/fixtures/determinism/amd-vulkan-full-greedy-32step.gemma270m.batch${i}.json" \
    --output-root bench/out/amd-vulkan-full-greedy-32step \
    --persist-logits 2>&1 | tail -1
done
echo

echo "=== Suite complete ==="
echo "Finished: $(date -u +%Y%m%dT%H%M%SZ)"
echo
echo "Next steps:"
echo "  1. Run Phase 3 analysis (see AMD-VULKAN-RUN-PLAN.md)"
echo "  2. Run Phase 4 LM-head hunt + frontier sweep"
