# Fawn Trace Module

Purpose:
- capture deterministic event artifacts
- support crash dump + replay workflows

This module is self-contained and does not depend on external runtime code.

Modes:
- native artifact export
- WASM host-bridge export

## Script

- `replay.py`
  - validates presence and parseability of trace bin/meta artifacts
  - serves as v0 replay contract entrypoint
  - `--trace-jsonl` validates deterministic hash-chain order and sequence continuity
  - compares `trace-meta` fields (`seqMax`, `rowCount`, `hash`) against replay rows when present
  - used as a blocking release gate via `python3 bench/trace_gate.py` against Dawn/Doe comparison artifacts.
- `compare_dispatch_traces.py`
  - compares two NDJSON trace streams by normalized decision envelope
  - fails fast with first mismatch report
  - used by `bench/trace_gate.py` semantic parity mode (`--semantic-parity-mode auto|required`) for runtime-to-runtime parity checks
  - example:
    - `python3 pipeline/trace/compare_dispatch_traces.py --left zig.ndjson --right lean.ndjson`

## Contracts

- `config/trace.schema.json` (row-level trace rows)
- `config/trace-meta.schema.json` (run-level summary artifact)
  - canonical runtime trace row shape
  - includes hash chain fields and decision metadata used by replay parity checks
- semantic operator tracing extends the same trace row/meta contracts with:
  - `semanticOpId`, `semanticStage`, `semanticPhase`
  - semantic token/layer coordinates
  - execution-side backend lane / shader manifest references
  - operator-manifest summary fields on trace-meta
- Doe-native operator debugging artifacts live next to the trace anchor:
  - `<trace-meta-or-jsonl>.operators.json`
  - `<trace-meta-or-jsonl>.opNNNN.capture.bin`
  - `<trace-meta-or-jsonl>.opNNNN.repro.commands.json`
  - `<trace-meta-or-jsonl>.opNNNN.repro.meta.json`
- replay remains structural, not bitwise. Repro bundles are intended for same
  backend / same device debugging with trusted command + artifact provenance.
