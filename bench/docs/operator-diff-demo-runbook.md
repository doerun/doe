# Operator diff demo runbook

Purpose:
- record the currently validated operator-diff proof path
- preserve the architectural meaning of the demo without promoting scratch
  `/tmp` artifacts into governed benchmark catalogs

This runbook documents a validated ad-hoc flow using the existing
`bench/cli.py compare` harness with scratch configs and
workloads under `/tmp`.

## Preconditions

The Doe runtime binary must be current.

Before running the demo flow, rebuild:

```bash
cd runtime/zig
zig build
```

This mattered in practice: a stale `zig-out` binary did not emit semantic
operator artifacts.

## Runtime invocation shape

Each side runs `runtime/zig/zig-out/bin/doe-zig-runtime` with:

- `--execute`
- `--trace`
- `--trace-jsonl`
- `--trace-meta`

The command JSON includes semantic fields:

- `semanticOpId`
- `semanticStage`
- `semanticPhase`
- `semanticTokenIndex`
- `semanticLayerIndex`
- `semanticExecutionPlanHash`

and capture fields:

- `captureBufferHandle`
- `captureOffset`
- `captureSize`

## What the runtime emits

For a traced semantic operator run, the runtime now emits:

- `.operators.json`
- `.capture.bin`
- `.repro.commands.json`
- `.repro.meta.json`

The compare harness reads `operatorRecordManifestPath` from trace meta and
computes `operatorDiff` automatically.

## Validated proof ladder

Three ad-hoc proof states were validated using scratch workloads in `/tmp`.

### 1. Matched structural comparison

Setup:
- same kernel on both sides
- same semantic metadata on both sides

Expected result:
- `operatorDiff.status = "matched"`

What this proves:
- semantic artifacts are emitted
- manifests are discovered by the compare harness
- compare logic can confirm structural match

### 2. Semantic identity mismatch

Setup:
- same kernel on both sides
- different `semanticOpId` / `semanticLayerIndex`

Expected result:
- `firstDivergence.type = "semantic_identity_mismatch"`

What this proves:
- the compare layer diffs semantic operator identity, not just raw command rows

### 3. Capture digest mismatch

Setup:
- same semantic metadata on both sides
- same command shape
- same execution status
- different kernels that write different captured bytes

Validated kernel pair:

- left: `bench/kernels/zero_initialize_workgroup_memory_2048.wgsl`
- right: `bench/kernels/concurrent_execution_runsingle_u32.wgsl`

Expected result:
- `operatorDiff.status = "diverged"`
- `firstDivergence.type = "capture_digest_mismatch"`

What this proves:
- the compare layer can detect byte-level divergence at a semantic operator
  boundary
- the path is now close to a real numerical cross-device drift case

## Architectural significance

### The semantic bridge works

Doppler-side semantic labels flow through command JSON into the Doe runtime,
which attaches them to GPU dispatch results, captures, and repro bundles.

The compare layer then diffs at the semantic operator level rather than the raw
GPU command level.

This is the core "owns both layers" advantage.

### The capture path works

Buffer readback -> SHA-256 -> digest comparison means the system can detect
output divergence without requiring epsilon thresholds just to establish that a
difference exists.

Drift budgets and operator-class tolerances can be layered on top later.

### The repro bundle path works

Each divergent operator produces standalone repro artifacts:

- `.repro.commands.json`
- `.repro.meta.json`

These are the operational basis for the forensic bundle framing in strategy doc
`#9`.

## What this does not yet prove

- governed benchmark-catalog integration
- real cross-backend or cross-device divergence on a buyer-facing workload
- product packaging for `doe-gpu diagnose`

## Gap from this runbook to `doe-gpu diagnose`

What remains is mostly packaging and productization:

- generate configs/commands from model input instead of hand-built scratch JSON
- run left/right across real backend differences (for example Metal vs Vulkan)
- surface the first divergence directly in CLI output rather than only JSON

## Related docs

- `bench/README.md`
- `docs/status.md`
- `../ouroboros/docs/strategy/capabilities/01-operator-diffing.md`
- `../ouroboros/docs/strategy/capabilities/06-doe-gpu-diagnose.md`
