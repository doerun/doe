# Gemma 4 E2B WebGPU / CSL simulator demo

This is the interactive demo for the Doppler -> Doe -> CSL proof path.
The claimable default is the L1 synthetic layer-block plus the
BF16-derived real-weight smoke receipt. Deeper selector depths are
diagnostic until the depth-coverage matrix marks them evidence-eligible.

It runs the Gemma 4 E2B layer-block WGSL kernel in the browser through
WebGPU, runs or loads the matching Doe-emitted CSL simfabric result, and
compares the `activation_out` vectors in the page. The third lane runs a
CSL semantic emulator on WebGPU by binding to the CSL trace's
`layerBlockSmoke.hostIoLayout` stream contract and reusing the same
browser GPU execution path.

Start the API-capable local server from the repo root:

```bash
python3 demos/gemma4-e2b-csl-sim/server.py --port 8001
```

Then open:

```text
http://127.0.0.1:8001/demos/gemma4-e2b-csl-sim/
```

The CSL button invokes diagnostic local runs:

```bash
/home/x/cerebras-sdk/cs_python \
  bench/runners/csl-runners/e2b_layer_block_smoke.py \
  --num-layers <1|2|4|8|35>
```

and writes scratch artifacts under
`bench/out/scratch/gemma4-e2b-csl-sim/`.

Use `bench/out/doe-run/depth-coverage-matrix.json`,
`bench/out/doe-run/all-lanes-summary-L1.json`, and
`bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json` as the claim
boundary. Today that boundary is L1 synthetic parity plus a real-weight
smoke layer-block only. The model receipt also exposes BF16 and RDRR L35
smoke-chain diagnostics in `sdkLayoutDepthDiagnosticEvidence`, but that
block is explicitly non-claimable: no manifest-shape Doe/CSL runtime
execution, no full E2B runtime execution, and no Cerebras hardware
receipt.

The cockpit also reads
`config/generated/doppler-vs-tjs-20260421-digest.json`.
That digest hash-links sibling Doppler vendor benchmark artifacts: Qwen
rows are claimable Doppler-vs-TJS WebGPU wins when exact-match correctness
and comparable metrics are present; Gemma 4 E2B rows remain blocked because
Transformers.js / ONNX Runtime WebGPU did not load the external-data ONNX
artifact on this host.

LAN note: browser WebGPU requires a secure context. Loading this page
from `http://192.168.x.x:8001` may show the page but block the live
browser WebGPU run. Use localhost, an SSH tunnel, or a browser trusted
insecure-origin override for the LAN URL.
