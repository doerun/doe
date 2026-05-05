# Gemma 4 31B AF16 simfabric-cell drivers

Tracked source for bounded simfabric cells for the Gemma 4 31B AF16
manifest lane. The cell source names use the production kernel stem from the
HostPlan compile inventory.

## Current cells

- `lm_head_prefill` — dense GEMV lm-head canary using f16
  activation and weight buffers with f32 sink output. The cell exercises the
  collectives_2d reduction path at a bounded shape that completes locally.

## Regenerating receipts

From the repo root:

```sh
python3 bench/tools/run_gemma4_31b_af16_simfabric_cells.py
```

The runner copies the tracked CSL triple into `bench/out/`, compiles with
`cslc`, runs the cell with `cs_python`, and writes:

- `bench/out/r3-1-31b-gemma-af16-lm-head-prefill-simfabric-cell/receipt.json`
- `bench/out/r3-1-31b-gemma-af16-simfabric-cells/summary-receipt.json`

For hardware endpoint validation, pass the endpoint through:

```sh
python3 bench/tools/run_gemma4_31b_af16_simfabric_cells.py \
  --cmaddr <operator-supplied>
```

## What this validates

- The production-named `lm_head_prefill` CSL triple compiles under the
  WSE-3 SDK at bounded shape.
- f16 activation and f16 weights are staged through SDK 32-bit memcpy words.
- The PE program converts f16 operands to f32, computes a dense GEMV partial,
  and reduces across the row chain.
- The sink PE output matches the host f32 reference within the receipt's
  tolerance.

## What this does not validate

- Full 31B manifest-shape execution.
- Full-vocabulary lm-head coverage.
- End-to-end token output.
- Hardware execution unless `--cmaddr` is provided and the returned receipt
  records `executionTarget=hardware`.
- Other Gemma kernels. Those remain separate cell work.
