# Determinism Run Plan

Blog-focused plan for measuring GPU numerical drift in WebGPU LLM inference.

```bash
export B=apple-metal   # or amd-vulkan
```

Backend-specific setup:
- [APPLE-METAL-RUN-PLAN.md](APPLE-METAL-RUN-PLAN.md)
- [AMD-VULKAN-RUN-PLAN.md](AMD-VULKAN-RUN-PLAN.md)

---

## Run matrix

12 runs across 3 models, 2 GPUs, and 3 WebGPU runtimes.

| ID | Model | GPU | Runtime | Fixture suffix |
|----|-------|-----|---------|----------------|
| 2a | Gemma 270M | Apple Metal | Doe | `.gemma270m` |
| 2b | Gemma 270M | AMD Vulkan | Doe | `.gemma270m` |
| 2c | Gemma 1B | Apple Metal | Doe | `.gemma1b` |
| 2d | Gemma 1B | AMD Vulkan | Doe | `.gemma1b` |
| 2e | Qwen 3.5 0.8B | Apple Metal | Doe | `.qwen08b` |
| 2f | Qwen 3.5 0.8B | AMD Vulkan | Doe | `.qwen08b` |
| 6a | Gemma 270M | Apple Metal | Dawn | `.gemma270m.dawn` |
| 6b | Gemma 270M | Apple Metal | WebKit | `.gemma270m.webkit` |
| 6c | Gemma 270M | AMD Vulkan | Dawn | `.gemma270m.dawn-vulkan` |
| 6d | Qwen 3.5 0.8B | Apple Metal | Dawn | `.qwen08b.dawn` |
| 6e | Qwen 3.5 0.8B | Apple Metal | WebKit | `.qwen08b.webkit` |
| 6f | Qwen 3.5 0.8B | AMD Vulkan | Dawn | `.qwen08b.dawn-vulkan` |

All runs: 256 prompts, 16 decode steps, top-64 logits captured, 3 repeats, `--persist-logits`.

Comparison axes:
- **Hardware**: Metal vs Vulkan (2a vs 2b, 2c vs 2d, 2e vs 2f)
- **Model family**: Gemma vs Qwen (2a vs 2e, 2b vs 2f)
- **Model size**: 270M vs 1B vs 0.8B (2a vs 2c, 2b vs 2d)
- **Runtime on Metal**: Doe vs Dawn vs WebKit (2a vs 6a vs 6b, 2e vs 6d vs 6e)
- **Runtime on Vulkan**: Doe vs Dawn (2b vs 6c, 2f vs 6f)

---

## Layer 0: Operator counterexamples (~2 min, no model needed)

Synthetic inputs proving GPU floating-point non-associativity at the operator level. Same computation, different accumulation order, different result.

```bash
# Attention slice (forward vs pairwise) — diverges on both backends
python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/$B-attention-slice-logit-flip.json \
  --output-root bench/out/$B-attention-slice-logit-flip

# RMSNorm slice (tree vs serial) — diverges on both backends
python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/$B-rmsnorm-slice-logit-flip.json \
  --output-root bench/out/$B-rmsnorm-slice-logit-flip

# Dot product (forward/reverse/pairwise) — diverges on Metal only
python3 bench/runners/run_reduction_order_counterexample.py \
  --fixture bench/fixtures/determinism/$B-reduction-order-dot-product.json \
  --output-root bench/out/$B-reduction-order-dot-product

# Matmul logit flip (forward/reverse/pairwise)
python3 bench/runners/run_reduction_order_logit_flip.py \
  --fixture bench/fixtures/determinism/$B-reduction-order-logit-flip.json \
  --output-root bench/out/$B-reduction-order-logit-flip
```

---

## Layer 2: Full greedy 16-step sweeps

Runner: `run_real_logit_hunt.py`

### Single-run (full 256 prompts)

```bash
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/$B-full-greedy-16step.MODEL.json \
  --output-root bench/out/$B-full-greedy-16step \
  --persist-logits
```

Replace `MODEL` with `gemma270m`, `gemma1b`, or `qwen08b`.

### Batch splits (for resumability)

Each Doe fixture has 6 batch splits (44 prompts × 5 + 36 × 1 = 256):

```bash
for i in 0 1 2 3 4 5; do
  python3 bench/runners/run_real_logit_hunt.py \
    --fixture bench/fixtures/determinism/$B-full-greedy-16step.MODEL.batch$i.json \
    --output-root bench/out/$B-full-greedy-16step \
    --persist-logits
done
```

### Cross-backend runs (Layer 6)

These use the same runner but point to fixtures with a `backendLane` override:

```bash
# Dawn on Metal
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/apple-metal-full-greedy-16step.gemma270m.dawn.json \
  --output-root bench/out/apple-metal-dawn-full-greedy-16step \
  --persist-logits

# WebKit on Metal
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/apple-metal-full-greedy-16step.gemma270m.webkit.json \
  --output-root bench/out/apple-metal-webkit-full-greedy-16step \
  --persist-logits

# Dawn on Vulkan
python3 bench/runners/run_real_logit_hunt.py \
  --fixture bench/fixtures/determinism/amd-vulkan-full-greedy-16step.gemma270m.dawn-vulkan.json \
  --output-root bench/out/amd-vulkan-dawn-full-greedy-16step \
  --persist-logits
```

Same pattern for `qwen08b.dawn`, `qwen08b.webkit`, `qwen08b.dawn-vulkan`.

---

## Layer 3: Offline analysis (Python-only, consumes Layer 2)

Set `$HARVEST` to the Layer 2 output path (the `.real-logit-hunt.json` file).

```bash
# Extract harvest portion
python3 -c "
import json
d = json.load(open('$HARVEST'))
json.dump(d['harvest'], open('harvest-only.json','w'))
"
```

### 3a. Exhaustive f16 flip scan

```bash
python3 bench/runners/scan_f16_flip_exhaustive.py \
  --harvest harvest-only.json \
  --model-root ../doppler/models/local/MODEL_DIR \
  --answer-set-registry config/determinism-answer-set-registry.json \
  --top-k 64 --pairwise --cross-answer-set \
  > bench/out/$B-f16-flip-exhaustive-scan.json
```

### 3b. Cascade divergence (16-step)

```bash
python3 bench/runners/run_cascade_divergence_tracker.py \
  --harvest harvest-only.json \
  --model-root ../doppler/models/local/MODEL_DIR \
  --steps 16 --top-k 64 \
  --answer-set-registry config/determinism-answer-set-registry.json \
  --output-root bench/out/$B-cascade-divergence
```

### 3c. Sampled decode sensitivity (NEW)

Simulates what happens under sampled decoding (temp=0.7, top-k=4) using the persisted logits from Layer 2. No GPU needed.

```bash
python3 bench/runners/simulate_sampled_sensitivity.py \
  --harvest $HARVEST \
  --temperatures 0.0 0.3 0.5 0.7 1.0 1.5 \
  --top-k 4 \
  --output bench/out/$B-sampled-sensitivity.MODEL.json
```

Produces per-prompt, per-step, per-temperature:
- `tokenFlip`: did the most-probable sampled token change between repeats?
- `pDisagreement`: probability that two independent samples from different repeats would disagree
- `flipRateByStep`: flip rate broken down by decode step (step 0 = prefill)

---

## Output structure

```
bench/out/$B-full-greedy-16step/
  <timestamp>/
    <scenario_id>.real-logit-hunt.json    # main result
    embeddings/                            # prefill embedding hashes
    logits/                                # persisted logit tensors (if --persist-logits)

bench/out/$B-f16-flip-exhaustive-scan.json
bench/out/$B-cascade-divergence/
bench/out/$B-sampled-sensitivity.MODEL.json
```

## Key output fields

| Field | Source | Meaning |
|-------|--------|---------|
| `byteDriftObserved` | Layer 2 | Any byte-level logit difference between repeats |
| `greedyTokenFlipObserved` | Layer 2 | Greedy winner changed between repeats |
| `minTop2Gap` | Layer 2 | Smallest margin between #1 and #2 token |
| `totalFlips` | Layer 3a | Count of f16-induced token flips |
| `divergenceRate` | Layer 3b | Fraction of sequences that diverge by step N |
| `flipRate` | Layer 3c | Fraction of steps where sampled token flips |
| `pDisagreement` | Layer 3c | P(different token) under sampling at temp T |

## Backend matrix

| Backend | Machine | Plan |
|---------|---------|------|
| Doe on Apple Metal | Apple Silicon Mac | [APPLE-METAL-RUN-PLAN.md](APPLE-METAL-RUN-PLAN.md) |
| Doe on AMD Vulkan | AMD Radeon (GFX1151) | [AMD-VULKAN-RUN-PLAN.md](AMD-VULKAN-RUN-PLAN.md) |
| Dawn on Apple Metal | Apple Silicon Mac | Layer 6 above |
| WebKit on Apple Metal | Apple Silicon Mac | Layer 6 above |
| Dawn on AMD Vulkan | AMD Radeon | Layer 6 above |
