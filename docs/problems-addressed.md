# Problems Doe addresses

## Purpose

This document describes specific practitioner pain points in current WebGPU
stacks and how Doe addresses them. Each section names the problem, explains
what incumbent stacks (Dawn, browser WebGPU) do, and describes Doe's approach.

The important framing is competitive, not rhetorical: Dawn is the incumbent.
Doe is the challenger runtime. The immediate target is not "replace Chromium."
The immediate target is to win the native, embedded, and package/runtime lanes
where browser process overhead and general-purpose incumbent layering are most
expensive.

See also:

- [`thesis.md`](./thesis.md) for project rationale
- [`architecture.md`](./architecture.md) for system surfaces
- [`performance-strategy.md`](./performance-strategy.md) for Dawn comparison methodology

---

## 1. Per-call validation overhead

**Problem.**
Dawn validates every API call at runtime — every `writeBuffer`, every
`setBindGroup`, every pipeline creation. This is correct for untrusted browser
content but adds recurring CPU cost for embedded/native workloads where the
caller is trusted.

**Doe's approach.**
Doe separates validation into two modes:

1. **Ahead-of-time verified execution.** Lean proofs discharge selected
   invariants offline. The Zig runtime executes the resulting specialized path
   with those branches removed.
2. **Runtime-checked execution.** Zig keeps dynamic checks for untrusted or
   late-bound inputs.

The design rule is: implement in Zig first, measure, then move conditions into
proof/config only when that lets Doe delete runtime branches safely.

The result is less CPU work per command on hot paths — the kind of overhead
that dominates small, frequent GPU workloads (point cloud node uploads,
per-frame compute dispatches, repeated inference steps).

## 2. Process and bridge overhead

**Problem.**
Dawn in Chrome runs in a separate GPU process. Every WebGPU API call crosses a
Mojo IPC boundary with serialization/deserialization overhead. This is
architecturally necessary for browser sandboxing but unnecessary when the
runtime is embedded in a native application or server-side JS runtime.

**Doe's approach.**
Doe loads `libwebgpu_doe.so` in-process via N-API (Node.js) or FFI (Bun/Deno)
and calls the WebGPU proc table directly. No IPC, no serialization, no process
boundary per call.

## 3. Staging buffer complexity

**Problem.**
WebGPU requires explicit staging buffers for GPU uploads. The API surface makes
this manual and error-prone: allocate staging buffer, map it, copy CPU data in,
unmap, encode a copy command, submit. Unified-memory hardware (Apple Silicon)
still pays this ceremony even though the underlying memory is shared.

**Doe's approach.**
The Zig runtime selects the upload path automatically per backend:

| Path | Condition | What it avoids |
|------|-----------|---------------|
| `fast_mapped` | Small buffers (<1 MB), Vulkan | No staging alloc; persistent CPU mapping |
| `direct_mapped` | Up to 4 GB, Vulkan | Persistent mapped; no map/unmap per upload |
| `staged_copy` | Large or non-mappable, Vulkan | Explicit staging + command buffer when needed |
| Deferred copy | Metal (unified memory) | CPU memcpy after shared-event wait; no GPU-side staging |

Upload cadence is config-driven (`upload_submit_every`) rather than hardcoded.

The JS API adds a further layer: buffer creation uses semantic tokens
(`'upload'`, `'readback'`, `'storageReadWrite'`) that resolve to the correct
WebGPU usage flags. Readback auto-selects direct mapping vs cached staging
buffer per source buffer.

## 4. Bind group proliferation

**Problem.**
WebGPU's static bind group model requires creating separate bind group objects
for each unique resource binding. Point cloud renderers, LOD systems, and
inference pipelines can accumulate thousands of bind groups for per-node or
per-layer parameter sets.

**Doe's approach.**

- **Dynamic offsets.** Doe supports dynamic bind group offsets (256-byte
  aligned stride), so a single bind group can address different slices of a
  large buffer — reducing bind group count for workloads with uniform structure.
- **Render draw loop modes.** Explicit `static` vs `redundant` modes for
  pipeline and bind-group state management. The caller opts into how much state
  resetting happens rather than the runtime guessing.
- **JS-side tracking.** The batch compute API tracks last-bound bind group and
  skips redundant `setBindGroup()` calls automatically.

## 5. Render pass ceremony

**Problem.**
WebGPU requires render passes even for simple draw calls. Render pass objects
add setup cost and conceptual overhead, especially for workloads that are
primarily compute-driven with occasional visualization.

**Doe's approach.**

- **Compute-first surface.** `doe-gpu/compute` is a first-class package export.
  Compute-only workloads never touch render passes.
- **Render bundles.** For render workloads, Doe supports render bundle
  pre-encoding — record draw state once, replay cheaply.
- **One-shot compute.** The JS API provides `gpu.compute()` which handles
  buffer creation, upload, dispatch, readback, and cleanup in a single call.

## 6. Hidden runtime behavior and silent fallback

**Problem.**
Incumbent WebGPU stacks sometimes silently fall back to slower paths when a
feature is unavailable, or hide policy decisions in undocumented runtime
branches. This makes performance debugging difficult — you don't know what
path you're actually on.

**Doe's approach.**

- Unsupported capabilities fail with explicit, actionable errors — never
  auto-switch to hidden behavior.
- All runtime policy (upload cadence, sync mode, queue wait strategy, timestamp
  collection) lives in config, not in undocumented code branches.
- Backend selection is config/policy-driven with typed backend identities
  (`doe_metal`, `doe_vulkan`, `doe_d3d12`, `dawn_delegate`).
- Queue synchronization is configurable: `process_events` vs `wait_any` wait
  mode, `per_command` vs `deferred` sync mode.

## 7. Non-deterministic GPU compute results

**Problem.**
Floating-point reduction order varies across GPU runs. For inference workloads,
this means token selection can differ between runs on identical inputs —
making debugging, testing, and compliance auditing difficult. Neither Dawn nor
browser WebGPU provides determinism guarantees.

**Doe's approach.**
The JS API provides three determinism policy levels:

1. **`gpu.determinism.stableToken(logits)`** — greedy token selection with a
   Lean-proven tie-break rule. Returns `{ token, receipt }` with SHA-256 of
   logits, top-k candidates, and proof artifact links.
2. **`gpu.determinism.stableChoice(logits, candidateSet)`** — bounded
   candidate evaluation with configurable ambiguity trigger.
3. **`gpu.determinism.reviewedChoice(logits, reviewedToken)`** — explicit
   reviewed decision with ambiguity gate.

Every call returns an auditable receipt with policy IDs and registry versions.

## 8. Numeric stability opacity

**Problem.**
GPU fast paths (f16 accumulation, fused operations) can produce results that
diverge from CPU reference values. Most stacks provide no way to detect or
quantify this divergence at runtime.

**Doe's approach.**
`gpu.numericStability.matmulLogitsSlice()` compares fast (f16 GPU), stable
(f64 serial), and reference (CPU f64) paths for the same computation. Returns
a route decision (`'accept-fast'`, `'prefer-stable'`, `'abstain'`) so the
caller knows whether the GPU fast path is trustworthy for a given input.

`gpu.ordinaryExecution()` runs entire command streams through the native
runtime with automatic sensitive-operator detection and structured trace
output.

## 9. WebGPU feature ceiling

**Problem.**
Browser WebGPU targets a feature set constrained by the lowest common
denominator (primarily Android Vulkan 1.0 drivers). Features like `shader-f16`,
subgroups, and advanced texture formats are unavailable or optional.

**Doe's approach.**
Since Doe targets native embedding (not browsers), it can expose hardware
capabilities when present: `shader-f16`, `subgroups`, `timestamp-query`,
`indirect-first-instance`, texture format tiers, and others. The capabilities
system probes the backend at startup and publishes what is actually available.
Unsupported features fail explicitly rather than silently degrading.

## 10. Correctness vs performance tradeoff

**Problem.**
Removing validation or changing execution paths to improve performance raises
the question of whether the faster runtime is still correct.

**Doe's approach.**
Doe maintains byte-identical compute output parity with Dawn and WebKit Metal
on reference workloads. The 49-command Gemma3-270M inference pipeline produces
bitwise-matching results across all three backends. Performance claims require
explicit comparability and claimability status — see
[`performance-strategy.md`](./performance-strategy.md) for the full contract.
