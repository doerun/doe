# Gemma 4 E2B model access handoff

This is the model/cache side of the Cerebras evidence handoff. It pins the
local artifact identities and the environment variables that make the raw
SafeTensors, Doppler RDRR, and hardware-run commands resolve consistently.

## Cache roots

The current Linux host should not use `/media/x/models` for Hugging Face auth
or cache state unless its permissions are fixed. A failed `hf auth login` that
tries to create `/media/x/models/huggingface_cache` is an environment problem,
not a model problem.

Use the home-backed cache and explicit model roots:

```bash
export HF_HOME=/home/x/.cache/huggingface
export HUGGINGFACE_HUB_CACHE=/home/x/.cache/huggingface/hub
export HF_HUB_CACHE=/home/x/.cache/huggingface/hub
export DOE_MODELS_ROOT=/home/x/model-downloads
export DOE_GEMMA4_E2B_SAFETENSORS_DIR=/home/x/model-downloads/gemma4-e2b-it
export DOE_GEMMA4_E2B_RDRR_ROOT=/home/x/deco/doppler/models/local/gemma-4-e2b-it-q4k-ehf16-af32-int4ple
```

Run the preflight after changing any of those paths:

```bash
python3 bench/tools/prepare_gemma4_e2b_access.py --print-shell
```

Add `--create` to create the selected cache directories. Add
`--require-assets` when a CI/operator step must fail if the raw SafeTensors or
Doppler RDRR artifact is missing.

## Canonical artifacts

The canonical raw checkpoint source for the BF16/text oracle lane is
`google/gemma-4-E2B-it` from Hugging Face:

- upstream model id: `google/gemma-4-E2B-it`
- upstream page: <https://huggingface.co/google/gemma-4-E2B-it>
- local raw snapshot: `$DOE_GEMMA4_E2B_SAFETENSORS_DIR`
- expected local files: `config.json`, one or more `.safetensors` files,
  `tokenizer.json`, and `tokenizer_config.json`
- active Doe use: manifest-shape CPU oracle and BF16-derived smoke-contract
  layer-block slices

The canonical Doppler production-artifact lane is the local RDRR/Q4_K_M
fixture:

- fixture: `config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json`
- local root: `$DOE_GEMMA4_E2B_RDRR_ROOT`
- expected local files: `manifest.json`, `origin.json`, `tokenizer.json`, and
  shard files
- quantization: `Q4_K_M`
- active Doe use: RDRR structural probe, Q4_K_M smoke-slice extraction, and
  smoke-contract parity

Raw BF16 and RDRR/Q4_K_M are both active lanes. They prove different things:
the BF16 lane verifies the upstream text checkpoint and smoke-contract slice
extraction; the RDRR lane verifies that Doe can consume Doppler's converted
artifact shape and dequantized smoke slices. Neither lane is full Doppler
production inference parity yet.

## Download and validation commands

Authenticate without writing credentials into the model root:

```bash
hf auth login --token <token> --add-to-git-credential false
```

Download the raw BF16 snapshot:

```bash
hf download google/gemma-4-E2B-it \
  --local-dir "$DOE_GEMMA4_E2B_SAFETENSORS_DIR"
```

Validate the raw BF16 lane:

```bash
python3 bench/tools/probe_gemma4_e2b_manifest_shape.py \
  --source-dir "$DOE_GEMMA4_E2B_SAFETENSORS_DIR"

python3 bench/tools/run_gemma4_e2b_manifest_shape_execution.py \
  --source-dir "$DOE_GEMMA4_E2B_SAFETENSORS_DIR"

python3 bench/tools/extract_gemma4_e2b_weight_slices.py \
  --source-dir "$DOE_GEMMA4_E2B_SAFETENSORS_DIR" \
  --out-json bench/out/gemma-4-e2b-real-weight-extraction.json
```

Validate the Doppler RDRR/Q4_K_M lane:

```bash
python3 bench/tools/probe_doppler_rdrr_artifact.py \
  --artifact-root "$DOE_GEMMA4_E2B_RDRR_ROOT"

python3 bench/tools/run_doppler_rdrr_q4k_parity.py \
  --artifact-root "$DOE_GEMMA4_E2B_RDRR_ROOT"
```

Those commands are path-resilient: if the environment variables above are set,
the tools use them as defaults. Explicit flags still win for one-off runs.

## Cerebras access commands

Direct endpoint:

```bash
cs_python bench/runners/csl-runners/e2b_layer_block_smoke.py \
  --num-layers 35 \
  --compile-out bench/out/hardware-run/compile \
  --trace-out bench/out/hardware-run/trace.json \
  --weights-dir bench/out/gemma-4-e2b-real-weights \
  --cmaddr "$DOE_CSL_CMADDR"
```

WSC appliance:

```bash
python3 runtime/zig/tools/csl_appliance_driver.py \
  --code-dir bench/out/streaming-executor/e2b-layer-block-source \
  --layout layout.csl \
  --compiler-args "<operator-supplied cslc args>" \
  --compile-output bench/out/hardware-run/compile \
  --runner-command "cs_python bench/runners/csl-runners/e2b_layer_block_smoke.py --num-layers 35 --compile-out bench/out/hardware-run/compile --trace-out bench/out/hardware-run/trace.json --weights-dir bench/out/gemma-4-e2b-real-weights --cmaddr %CMADDR%" \
  --download "bench/out/hardware-run/trace.json:bench/out/hardware-run/trace.json" \
  --receipt-out bench/out/hardware-run/appliance-receipt.json \
  --system
```

The WSC command uses `%CMADDR%` so `SdkLauncher` resolves the endpoint at run
time. Receipts redact that to `$DOE_CSL_CMADDR`; raw endpoints and credentials
must not be checked into repo artifacts.

## First demo scope

The first demo should show:

- E2B slice proof as the primary live row: Doppler/RDRR identity, BF16/RDRR
  slice provenance, SdkLayout smoke status, parity, and blockers
- 31B dense as a structural/blocked row: stream graph and model receipt
  present, execution/hardware absent
- Cerebras hardware as absent until a `hardware_success` receipt exists

Do not show full E2B, 31B execution, MoE, or performance claims as green until
the corresponding model-level and hardware receipts exist.
