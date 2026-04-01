# Apple Metal Full Comparison Run Plan

## Hardware requirements

- Apple Silicon Mac (tested: M-series)
- Chromium with WebGPU
- Doppler repo at `../doppler` with models in `models/local/`

## Prerequisites

```bash
# 1. Verify models exist
ls ../doppler/models/local/gemma-3-270m-it-q4k-ehf16-af32/manifest.json
ls ../doppler/models/local/gemma-3-1b-it-q4k-ehf16-af32/manifest.json
```

## Phase 1: Operator-level counterexamples (no model needed, ~2 min)

Synthetic weights baked into commands.json. Tests accumulation-order sensitivity on Apple Metal.

```bash
# Dot product (forward/reverse/pairwise)
python3 bench/runners/run_reduction_order_counterexample.py \
  --fixture bench/fixtures/determinism/apple-metal-reduction-order-dot-product.json \
  --output-root bench/out/apple-metal-reduction-order-dot-product

# Matmul logit flip (forward/reverse/pairwise)
python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/apple-metal-reduction-order-logit-flip.json \
  --output-root bench/out/apple-metal-reduction-order-logit-flip

# Attention slice (forward/pairwise)
python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/apple-metal-attention-slice-logit-flip.json \
  --output-root bench/out/apple-metal-attention-slice-logit-flip

# RMSNorm slice (tree/serial)
python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/apple-metal-rmsnorm-slice-logit-flip.json \
  --output-root bench/out/apple-metal-rmsnorm-slice-logit-flip
```

## Phase 2: Full greedy logit hunts (needs Doppler + models)

### 270M, 10-step decode, 206 prompts (~15 min)

```bash
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/apple-metal-full-greedy-10step.gemma270m.json \
  --output-root bench/out/apple-metal-full-greedy-10step \
  --persist-logits
```

### 1B, 10-step decode, 20 prompts (~10 min)

```bash
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/apple-metal-full-greedy-10step.gemma1b.json \
  --output-root bench/out/apple-metal-full-greedy-10step \
  --persist-logits
```

### 270M, 32-step decode, 206 prompts (~40 min)

```bash
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/apple-metal-full-greedy-32step.gemma270m.json \
  --output-root bench/out/apple-metal-full-greedy-32step \
  --persist-logits
```

## Phase 3: Offline analysis (Python-only, uses Phase 2 output)

Replace `$HARVEST` with the Phase 2 output JSON path.

```bash
# Extract harvest portion
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
  > bench/out/apple-metal-f16-flip-exhaustive-scan.json
```

### Cascade divergence (32-step simulated)

```bash
python3 bench/runners/run_cascade_divergence_tracker.py \
  --harvest harvest-only.json \
  --model-root ../doppler/models/local/gemma-3-270m-it-q4k-ehf16-af32 \
  --steps 32 --top-k 64 \
  --answer-set-registry config/determinism-answer-set-registry.json \
  --output-root bench/out/apple-metal-cascade-divergence
```

### Cross-domain f16 flip exercise

```bash
python3 bench/runners/exercise_cross_domain_flips.py \
  --output-dir bench/out/apple-metal-cross-domain-f16-flip-exercise
```

## Phase 4: LM-head slice hunt + frontier sweep

### LM-head slice hunt

```bash
python3 bench/runners/run_real_lm_head_slice_hunt.py \
  --fixture bench/fixtures/determinism/apple-metal-full-lm-head-slice-hunt.gemma270m.json \
  --output-root bench/out/apple-metal-full-lm-head-slice-hunt \
  --top-candidates 20
```

### Frontier sweep

```bash
SEED_REPORT=$(ls -t bench/out/apple-metal-full-lm-head-slice-hunt/*/*.real-lm-head-slice-hunt.json | head -1)

python3 bench/runners/run_real_lm_head_slice_frontier_sweep.py \
  --seed-report "$SEED_REPORT" \
  --source-logit-fixture bench/fixtures/determinism/apple-metal-full-greedy-10step.gemma270m.json \
  --lm-head-scenario-fixture bench/fixtures/determinism/apple-metal-full-lm-head-slice-hunt.gemma270m.json \
  --frontier-limit 20 --mutations-per-seed 4 --runs 3 \
  --output-root bench/out/apple-metal-full-lm-head-slice-frontier-sweep
```

## Phase 5: Cross-backend comparison (Doe vs Dawn vs WebKit)

Requires Dawn and WebKit builds. Run each Phase 2 fixture through all three backends.

```bash
# Dawn backend (uses dawn_delegate)
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/apple-metal-full-greedy-10step.gemma270m.json \
  --output-root bench/out/apple-metal-dawn-full-greedy-10step \
  --backend-lane metal_dawn_release \
  --persist-logits

# WebKit backend (uses webkit_delegate)
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/apple-metal-full-greedy-10step.gemma270m.json \
  --output-root bench/out/apple-metal-webkit-full-greedy-10step \
  --backend-lane metal_webkit_release \
  --persist-logits
```

## Backend matrix (5 backends)

| Backend | Machine | Fixture | Status |
|---------|---------|---------|--------|
| Doe on Apple Metal | This machine | `apple-metal-full-greedy-*.json` | This plan |
| Dawn on Apple Metal | This machine | Same fixtures, `--backend-lane metal_dawn_release` | Needs Dawn build |
| WebKit on Apple Metal | This machine | Same fixtures, `--backend-lane metal_webkit_release` | Needs WebKit shim |
| Doe on AMD Vulkan | AMD machine | `amd-vulkan-full-greedy-*.json` | See AMD-VULKAN-RUN-PLAN.md |
| Dawn on AMD Vulkan | AMD machine | Same AMD fixtures | Needs Dawn Vulkan build |
