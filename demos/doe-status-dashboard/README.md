# doe-status-dashboard

Single-page static demo that binds to Doe's artifact schemas and renders the
current state of WGSL → multi-backend compile + CSL runtime readiness.

## View

Serve from the repo root (the page fetches artifacts from `../../bench/out/`):

```bash
cd /path/to/doe
python3 -m http.server 8000
```

Then open <http://localhost:8000/demos/doe-status-dashboard/>.

## What it binds to

Each row is re-derived from a JSON artifact at view time. No labels are
hardcoded; "Aspirational" rows in particular lift their `executionStatus` and
`executionBlocker` text verbatim from the receipt so the dashboard and the
artifact cannot drift.

| row | source |
| --- | --- |
| WGSL → multi-backend compile | `bench/out/cross-backend-matrix/wgsl-backend-matrix.json` |
| WGSL backend equivalence crosswalk | `bench/out/wgsl-backend-equivalence/index.json` |
| SdkLayout streaming executor primitives | `bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json` → `streamingExecutorPrimitivesEvidence` |
| Full-grid cslc feasibility | `bench/out/cslc-grid-probe/grid-probe-aggregate.json` |
| E2B / 31B structural readiness | `bench/out/e2b-full-graph/*-runtime-receipt.json`, `bench/out/31b-full-graph/*-runtime-receipt.json` |
| CSL full execution (simulator) | `executionStatus` + `executionBlocker` from each model receipt |
| CSL hardware execution | gated on the simulator blocker clearing; dashboard shows the blocker chain |

## What it does not do

This is a static page. It doesn't re-run any gate, regenerate any artifact,
or validate against schemas at view time — it trusts that the sweep has
already done that. Schema validation lives in `bench/gates/schema_gate.py`.

## Intentional distinction

The `bench/out/streaming-executor/` traces prove stream primitives run on
simfabric (stream I/O, compute transform, region-to-region chain, multi-PE
SPMD, compile cache, 4-stage layer-block chain). The E2B receipt still
carries `executionStatus=not_attempted` because no generated layer-block
runner exists yet. The dashboard renders these as separate rows so "streaming
executor primitives: pass" doesn't get conflated with "full-model CSL
execution: blocked".

The schema's `executionBlocker` enum was widened with
`streaming_executor_not_bound_to_execution_plan` to name this gap precisely;
the legacy `sdk_layout_streaming_executor_missing` remains in the enum for
backward compatibility but is no longer emitted by `build_model_runtime_receipt.py`.
