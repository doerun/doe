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
  - used as a blocking release gate via `python3 fawn/bench/trace_gate.py` against Dawn/Fawn comparison artifacts.
- `compare_dispatch_traces.py`
  - compares two NDJSON trace streams by normalized decision envelope
  - fails fast with first mismatch report
  - useful when a Lean oracle trace is available (manual/prototype path in v0)
  - example:
    - `python3 fawn/trace/compare_dispatch_traces.py --left zig.ndjson --right lean.ndjson`

## Contracts

- `fawn/config/trace.schema.json` (row-level trace rows)
- `fawn/config/trace-meta.schema.json` (run-level summary artifact)
  - canonical runtime trace row shape
  - includes hash chain fields and decision metadata used by replay parity checks
