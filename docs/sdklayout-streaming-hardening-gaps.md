# SdkLayout streaming runtime hardening gaps

## Purpose

The current layer-block runner
(`bench/runners/csl-runners/e2b_layer_block_smoke.py`) proves the
4-stage transformer layer kernel executes bit-exact under simfabric.
Scaling to **full** E2B / 31B model execution under SdkLayout streaming
needs six concrete gaps closed. Each gap below is named, detected, and
scoped so the implementation path is explicit.

This document is scoped to in-flight CSL streaming work. Apple Metal
runtime design lives in `docs/apple-metal-runtime-release.md`; cross-
kernel numeric-stability in `docs/numeric-stability-runtime-roadmap.md`.

## Gap 1: compile-artifact reuse

**Current state.** Every `cs_python e2b_layer_block_smoke.py` call
invokes `layout.compile(out_prefix=...)` which recompiles the kernel
from source (~500 ms). Multi-invocation chains recompile per call.

**Why this blocks full-model execution.** A full E2B forward pass
dispatches ~35 transformer-block kernels, 2 norm kernels, embed /
unembed, and sampling. Recompiling each per-dispatch multiplies
compile time to minutes on every invocation. Release-grade streaming
needs compile-once / dispatch-many.

**Detection signal.** Runner trace's `executedCompile.elapsedMs` non-
zero on every layer. Today it's emitted once per process but the
underlying `layout.compile()` still runs unconditionally.

**Implementation direction.** Content-address the compile result by
`(kernelSourceSha256, cslc_params_string, target_arch)`. Cache under
`bench/out/compile-cache/<key>/`. On runner invocation, check
`<compile-out>/.kernel_meta.json` vs the cache; reuse when match.
SDK support required: confirm `SdkRuntime(artifacts, ...)` accepts
pre-existing artifact directories without a fresh `layout.compile()`.

## Gap 2: weight staging

**Current state.** Each layer re-sends `ple_projection` and
`layer_weights` from the host via `runtime.send(proj_stream, ...)`
and `runtime.send(wts_stream, ...)` at chain-loop iteration time.
Total host→PE transfer over a 35-layer chain at smoke size 1024 is
`3 × 1024 × 4 × 35 = 430 KB/PE`. At manifest size the number grows
linearly with shape.

**Why this blocks full-model execution.** For real Gemma-4 weights
each layer's K/V/gate/up/proj tensors are MBs. Streaming the full
weight set per layer per dispatch wastes host bandwidth and hides
the underlying stream contract the plan already names (`weights`
payload bytes are fixed per layer at plan-emit time).

**Detection signal.** `observedBytesTransferredPerPe` in the runner
trace scales linearly with `num_layers`. It should scale with
`num_layers` only for rows (residual stream) — weights should cost
`1 × per_layer_footprint` when staged.

**Implementation direction.** Stage all per-layer weights into PE
memory once via an init-phase stream, reuse the stage for each
forward pass. Requires SdkLayout streaming primitives that support
persistent weight residency + an index-stream for per-layer offset
selection.

## Gap 3: KV cache movement

**Current state.** The layer-block smoke has no KV cache. The MHA
kernel today uses `kv_len=4` as a literal constant in the smoke
shape; per-iteration K/V are read from the `layer_weights` stream at
fixed offsets, not from a persistent KV cache.

**Why this blocks full-model execution.** Real inference writes new
K/V entries per token into a rolling cache, reads the full cache
on each decode step. The kernel needs KV-write / KV-read primitives
separate from the layer-block compute.

**Detection signal.** `streamingMigration.kvPolicy` field on the
model receipt: currently absent; should name the policy (ring buffer,
sharded, etc.) once wired.

**Implementation direction.** The host-plan already carries
`kv_write` / `kv_read` patterns with governed fixtures at
`bench/out/dual-compile-evidence/kv-*/`. Wire the fixture kernels
into the streaming dispatch chain; validate parity against a numpy
KV-cache model at matching token positions.

## Gap 4: stream buffer sizing

**Current state.** Generated layer-block runners derive per-stream
`io_buffer_size` from the execution plan with
`next_power_of_two(max(1024, payloadBytes))`. The small control
streams still use the 1024-byte floor; the larger weights stream is
plan-sized.

**Why this blocks full-model execution.** Per-stream optimal buffer
sizes depend on per-layer payload bytes and producer/consumer rates.
The plan's `layer.streams[*].payloadBytes` already differs per
stream: rows=2, proj=23, weights=2166. A single 1024 buffer either
over-allocates small streams or under-feeds big ones.

**Detection signal.** Runner trace `hostIoLayout[*].planPayloadBytes`
vs `ioBufferSizes.*`. `bench/gates/sdklayout_streaming_hardening_gate.py`
fails on undersized buffers and warns on `> 4x` over-allocation.

**Remaining work.** Replace the 1024-byte floor for tiny control
streams with a measured per-stream minimum once the executor exposes
backpressure and queue-depth telemetry.

## Gap 5: backpressure handling

**Current state.** Runner uses `runtime.send(..., nonblock=True)`
for inputs and `runtime.receive(..., nonblock=False)` for output.
Nonblocking sends can queue indefinitely; there's no instrumentation
on queue depth or dropped messages.

**Why this blocks full-model execution.** At manifest-shape scale
with full weight staging and KV movement, stream queue depth
matters. Silent buffer overflow would manifest as an unexplained
mismatch or a hang; a graceful backpressure signal is needed.

**Detection signal.** Absent. No counter today. Runner trace would
need `perStream.maxQueueDepth` and `droppedSendCount` fields.

**Implementation direction.** Add per-stream counters + periodic
sampling in the runner. Surface them in the trace's
`executedRun.streams` array as `maxQueueDepth` and
`droppedSendCount` per stream.

## Gap 6: traceable failure modes

**Current state.** On failure, the runner's exception path emits
`run_status = "failed:<type>:<msg>"` and `output_digest = None`.
The trace records the top-line error but not where in the 4-stage
chain the failure occurred, what CSL task was last active, or what
the PE fabric state was.

**Why this blocks full-model execution.** A full E2B / 31B forward
pass has hundreds of stream events per token. Without a failure
timeline, root-cause analysis requires rerunning under
`sdk_debug_shell` by hand. Streaming-grade debuggability needs
structured failure receipts.

**Detection signal.** Runner trace on failure has `executedRun.
status` and the elapsed ms only. Missing: `failedAtStage`,
`failedAtDispatchIndex`, `lastCompletedStreamSendReceive`,
`simulatorLogTailPath`.

**Implementation direction.** Add structured error handling: on
any exception, capture the current stage name, the per-stream
send/receive counter states, and the last N lines of simfabric
stderr. Emit those as `executedRun.failure` on the trace.

## Status

None of the six gaps are blocking `simulator_success` at the layer-
block scope (that already landed for E2B L=35 and 31B L=61). All six
are blockers for `simulator_success` at **full-model scope** (item #5
/ #6 in the Gemma-4-on-Cerebras roadmap) and for a meaningful
`hardware_success` receipt (item #8).

Prioritize in the order above: gap 1 unlocks fast iteration on the
others, gap 2 cuts host bandwidth, gap 3 is required for decode,
gap 4 is a simple validator-driven fix, gap 5 is instrumentation,
gap 6 is debuggability.
