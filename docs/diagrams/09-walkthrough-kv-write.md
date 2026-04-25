# 09 - Kernel walkthrough: `kv_write`

## Purpose

Show why state matters. KV cache updates must be visible in the contract, not
hidden inside an opaque op.

## Slide content

- Doppler decode step provides key/value projections and current position.
- TSIR shape: `key_cache` and `value_cache` are `read_write` bindings;
  `position` is a decode-position binding.
- Doe CSL writes key/value chunks at `position * head_dim + d`.
- Cerebras mapping: each PE owns a head-dim chunk; position is broadcast.

## Visual spec

- Four panes: WGSL/source contract (`doppler.red`), TSIR (`doe.blue`), CSL
  (`doe.blue`), PE/cache grid (`cerebras.orange`).
- Cache grid is rows = positions, columns = head dimension. Highlight the
  current position.

## Scope guard

- If the deck is sent before a receipt executes `kv_write`/`kv_read`, mark this
  slide as structurally enabled rather than executed.
- Do not claim operator graphs cannot model state; claim they usually need
  custom ops or side-channel state.
- If the real TSIR fixture is still missing, label the WGSL/TSIR panes as
  fixture-pending.

## Evidence sources

- `runtime/zig/src/doe_wgsl/emit_csl_kv_cache.zig`
- `runtime/zig/src/tsir/schema.zig`
- `docs/diagrams/16-evidence-ledger.md`
