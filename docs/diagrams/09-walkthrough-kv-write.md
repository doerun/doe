# 09 — Walkthrough: kv_write — "The stateful case"

## Goals

Third per-kernel walkthrough. Pick a kernel whose stateful semantics
(read-write cache binding, position-indexed write) are exactly what
operator-graph IRs struggle to express cleanly. Show that TSIR's
binding-role enum makes the statefulness first-class, not bolted on.

## What it shows

Four panes for kv_write. Note: WGSL + TSIR panes use a placeholder
fixture caption today — see "What it doesn't claim" — because the real
kv_write TSIR fixture under `runtime/zig/tests/tsir/real/kv_write/` is
not yet authored. The CSL emission and PE grid panes are real,
produced by the live `emitCslKvWrite` emitter.

1. **WGSL source** — `kv_write.wgsl`, writing projected key/value
   vectors into the cache at the current decode position.
   *Pane caption: "fixture pending real-pipeline-v0 promotion;
   bootstrap WGSL is the structural reference."*
2. **TSIR semantic function** — one axis (`d` ∈ `[0, head_dim)`),
   five bindings: `key_projection` (read), `value_projection` (read),
   `key_cache` (**read_write**, role `key_cache`),
   `value_cache` (**read_write**, role `value_cache`),
   `position` (read, role `decode_position`). Body op `kv_write`.
   *Pane caption: same "fixture pending" note.*
3. **CSL emission** — actual emitter output from
   `tsir.emit_csl.emitCslKvWrite`. `base = position[0] * head_dim`
   then per-element write into key/value caches at that base. No
   fabric reduce; per-PE local writes only. *Real artifact.*
4. **PE grid mapping** — each PE owns a chunk of `head_dim`. The
   `decode_position` scalar broadcast to all PEs; cache writes are
   PE-local. *Drawn from the emitter's actual axis assignment.*

## What it might look like

### Visual spec (per design tokens)

- **Layout pattern:** `four-pane-walkthrough`, identical structure to
  slide 07.
- **Top-left pane — WGSL source:** code-window frame, title bar
  `kv_write.wgsl`. Caption strip below pane: italic 11 px,
  `red.dim` text *"fixture pending real-pipeline-v0 promotion;
  bootstrap WGSL is the structural reference."* Red caption is
  the only place `red.dim` appears in slides 07-10 — it flags the
  one un-promoted fixture honestly.
- **Top-right pane — TSIR semantic function:** code-window frame,
  title bar `semantic.json`. JSON pretty-printed; the two
  `read_write` binding rows highlighted with a `purple.spatial`
  background tint and bold weight (visual emphasis on stateful
  bindings). Role tags (`role: key_cache`, `role: decode_position`)
  in monospace italic, `purple.spatial`. Caption strip: same
  fixture-pending note.
- **Bottom-left pane — CSL emission:** code-window frame, title bar
  `pe_program.csl`. Real output of `emitCslKvWrite`. No fixture-
  pending caption — this pane is real.
- **Bottom-right pane — PE grid mapping:** PE-grid icon center.
  - Each hexagon labeled with `chunk[d]` showing the head_dim
    distribution (small monospace).
  - Below the grid, a 2-D representation of the cache:
    rows = positions (e.g., `pos 0`, `pos 1`, …), cols = head_dim.
    The current write position highlighted with a `red.opaque`
    outline (the "now-being-written" marker).
  - A `decode_position` scalar shown as a small circle
    (`accent.gold`) above the grid, with thin lines fanning to
    every hexagon — depicting broadcast.
- **Persistent elements reused:** PE grid (slide 04). The
  `accent.gold` decode_position circle is a new ephemeral element
  used only on this slide.

The TSIR pane gets visual emphasis on the
read_write binding rows (e.g., bold or color-coded) and the role tags
(`role: key_cache`, `role: decode_position`). The PE grid pane shows
the cache as a 2-D grid (positions × head_dim) with a red highlight on
the position currently being written. Caption: "Statefulness exposed
as a typed binding role, not hidden in a custom op."

## What it doesn't claim

- kv_write executes in the truncated 31B simfabric receipt; **the
  Cerebras hardware leg (R2-10) is still the outstanding gate** for
  end-to-end hardware-tier evidence on this kernel.
- Operator-graph IRs *can* express stateful kernels. The claim is that
  they require either a custom op or out-of-band state plumbing,
  whereas TSIR carries the state shape in the same surface as the
  rest of the body.
- Not asserting kv_write is the only stateful pattern. kv_read is its
  symmetric partner; the deck collapses both into this slide for
  brevity. Both execute in the same truncated receipt.
- The kv_write real-pipeline-v0 TSIR fixture is not yet authored. The
  WGSL and TSIR panes carry that caveat explicitly. The CSL emission
  and PE grid panes are real (produced by the live emitter), and
  slide 16's evidence ledger carries the truncated 31B receipt as
  the load-bearing execution-side evidence for this kernel.

## Source artifacts to cite

- `runtime/zig/tests/tsir/real/kv_write/` — *fixture directory pending
  real-pipeline-v0 promotion; not present today.* Bootstrap-tier
  source under `runtime/zig/tests/tsir/bootstrap/` is also not present
  for kv_write specifically.
- `runtime/zig/src/tsir/schema.zig` — `SemanticBindingRole` enum
  including `key_cache`, `value_cache`, `decode_position`,
  `key_projection`, `value_projection`.
- `runtime/zig/src/tsir/emit_kernel_body.zig:emitCslKvWrite` — the
  emitter producing the CSL pane (real).
- `runtime/zig/src/doe_wgsl/emit_csl_kv_cache.zig` — the live wrapper
  that delegates to the TSIR emitter with `var_prefix=""` and the
  Config-driven defaults for `head_dim` / `max_seq_len`.
- See slide 16 for the truncated 31B receipt that carries the
  execution-side evidence on kv_write / kv_read.
