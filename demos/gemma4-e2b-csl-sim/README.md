# Gemma 4 E2B WebGPU / CSL simulator demo

This is the interactive demo for the Doppler -> Doe -> CSL proof path.

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

The CSL button invokes:

```bash
/home/x/cerebras-sdk/cs_python \
  bench/runners/csl-runners/e2b_layer_block_smoke.py \
  --num-layers <1|2|4|8|35>
```

and writes scratch artifacts under
`bench/out/scratch/gemma4-e2b-csl-sim/`.

LAN note: browser WebGPU requires a secure context. Loading this page
from `http://192.168.x.x:8001` may show the page but block the live
browser WebGPU run. Use localhost, an SSH tunnel, or a browser trusted
insecure-origin override for the LAN URL.
