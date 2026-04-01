# AMD Vulkan Full Comparison Run Plan

## Hardware requirements

- AMD GPU with Vulkan support (tested: Radeon GFX1151, RADV, Mesa 25.0.7)
- Chromium with WebGPU + Vulkan ANGLE
- Zig 0.15.2 (for doe-zig-runtime)
- Doppler repo at `../doppler` with models in `models/local/`

## Prerequisites

```bash
# 1. Build doe-zig-runtime
cd runtime/zig && zig build doe-runtime && cd ../..

# 2. Verify Vulkan
python3 bench/runners/preflight_vulkan_host.py

# 3. Verify models exist
ls ../doppler/models/local/gemma-3-270m-it-q4k-ehf16-af32/manifest.json
ls ../doppler/models/local/gemma-3-1b-it-q4k-ehf16-af32/manifest.json
```

## Phase 1: Operator-level counterexamples (no model needed, ~2 min)

These use synthetic weights baked into commands.json files.
Tests whether accumulation order flips exist on AMD Vulkan hardware.

```bash
# Dot product (forward/reverse/pairwise)
python3 bench/runners/run_reduction_order_counterexample.py \
  --fixture bench/fixtures/determinism/amd-vulkan-reduction-order-dot-product.json \
  --output-root bench/out/amd-vulkan-reduction-order-dot-product

# Matmul logit flip (forward/reverse/pairwise)
python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/amd-vulkan-reduction-order-logit-flip.json \
  --output-root bench/out/amd-vulkan-reduction-order-logit-flip

# Attention slice (forward/pairwise)
python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/amd-vulkan-attention-slice-logit-flip.json \
  --output-root bench/out/amd-vulkan-attention-slice-logit-flip

# RMSNorm slice (tree/serial)
python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/amd-vulkan-rmsnorm-slice-logit-flip.json \
  --output-root bench/out/amd-vulkan-rmsnorm-slice-logit-flip
```

## Phase 2: Full greedy logit hunts (needs Doppler + models)

### 270M, 10-step decode, 206 prompts (~15 min)

```bash
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/amd-vulkan-full-greedy-10step.gemma270m.json \
  --output-root bench/out/amd-vulkan-full-greedy-10step \
  --persist-logits
```

### 1B, 10-step decode, 206 prompts (~25 min)

```bash
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/amd-vulkan-full-greedy-10step.gemma1b.json \
  --output-root bench/out/amd-vulkan-full-greedy-10step \
  --persist-logits
```

### 270M, 32-step decode, 206 prompts (~40 min)

```bash
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/amd-vulkan-full-greedy-32step.gemma270m.json \
  --output-root bench/out/amd-vulkan-full-greedy-32step \
  --persist-logits
```

## Phase 3: Offline analysis (Python-only, uses Phase 2 output)

Replace `$HARVEST` with the Phase 2 output JSON path (the `.real-logit-hunt.json` file).
For scan/cascade, extract the harvest portion first:

```bash
python3 -c "
import json
d = json.load(open('$HARVEST'))
json.dump(d['harvest'], open('harvest-only.json','w'))
"
```

### Exhaustive f16 flip scan

```bash
python3 bench/runners/scan_f16_flip_exhaustive.py \
  --harvest harvest-only.json \
  --model-root ../doppler/models/local/gemma-3-270m-it-q4k-ehf16-af32 \
  --answer-set-registry config/determinism-answer-set-registry.json \
  --top-k 64 --pairwise --cross-answer-set \
  > bench/out/amd-vulkan-f16-flip-exhaustive-scan.json
```

### Cascade divergence (32-step simulated)

```bash
python3 bench/runners/run_cascade_divergence_tracker.py \
  --harvest harvest-only.json \
  --model-root ../doppler/models/local/gemma-3-270m-it-q4k-ehf16-af32 \
  --steps 32 --top-k 64 \
  --answer-set-registry config/determinism-answer-set-registry.json \
  --output-root bench/out/amd-vulkan-cascade-divergence
```

## Phase 4: LM-head slice hunt + frontier sweep

### LM-head slice hunt (extracts weight slices, tests accumulation variants)

```bash
python3 bench/runners/run_real_lm_head_slice_hunt.py \
  --fixture bench/fixtures/determinism/amd-vulkan-full-lm-head-slice-hunt.gemma270m.json \
  --output-root bench/out/amd-vulkan-full-lm-head-slice-hunt \
  --top-candidates 20
```

### Frontier sweep (mutations of tightest candidates)

```bash
SEED_REPORT=$(ls -t bench/out/amd-vulkan-full-lm-head-slice-hunt/*/*.real-lm-head-slice-hunt.json | head -1)

python3 bench/runners/run_real_lm_head_slice_frontier_sweep.py \
  --seed-report "$SEED_REPORT" \
  --source-logit-fixture bench/fixtures/determinism/amd-vulkan-full-greedy-10step.gemma270m.json \
  --lm-head-scenario-fixture bench/fixtures/determinism/amd-vulkan-full-lm-head-slice-hunt.gemma270m.json \
  --frontier-limit 20 --mutations-per-seed 4 --runs 3 \
  --output-root bench/out/amd-vulkan-full-lm-head-slice-frontier-sweep
```

## What to compare

After running, compare these numbers against Apple Metal results:

| Metric | Where to find it |
|--------|-----------------|
| Run-to-run determinism | logit hunt: `byteDriftObserved`, `greedyTokenFlipObserved` per candidate |
| Greedy margin distribution | logit hunt: `minTop2Gap` per candidate, sorted ascending |
| F16 flip count | f16-flip-exhaustive-scan: `totalFlips`, `flipsByType` |
| Cascade divergence rate | cascade report: `divergenceRate`, `permanentDivergenceRate` |
| Operator-level flips | reduction-order reports: `tokenFlipObserved`, raw logit values per variant |
| LM-head variant flips | lm-head hunt: `promotedCaseCount`, `tokenFlipObserved` per group |

## Backend matrix (5 backends)

This plan covers **AMD Vulkan Doe** only. The full comparison needs:

| Backend | Machine | Status |
|---------|---------|--------|
| Doe on Apple Metal | Apple machine | Mostly done |
| Dawn on Apple Metal | Apple machine | Partial (cross-backend-32tok-decode exists) |
| WebKit on Apple Metal | Apple machine | Partial (cross-backend-32tok-decode exists) |
| Doe on AMD Vulkan | This machine | This plan |
| Dawn on AMD Vulkan | This machine | Needs Dawn Vulkan build |
