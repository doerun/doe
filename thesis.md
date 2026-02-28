# Fawn Thesis

## Abstract

Fawn is a Chromium fork that replaces Dawn with Doe as its WebGPU implementation.

Doe is a Zig WebGPU runtime for WebGPU-class execution with:

- Zig for explicit low-overhead systems paths
- Lean 4 for high-value invariant formalization
- deterministic boundary decisions (`accept(receipt)` or `reject(trace)`)

The intent is defense-in-depth and performance improvement, not sandbox replacement.

## Process Goals (Priority Order)

1. Development speed
2. p95 latency reduction
3. Correctness in runtime behavior (non-proof correctness)
4. Deterministic replay/debuggability
5. Formal proof coverage

This ordering governs scope decisions and tradeoffs.

## Delivery Mode

- Commit-only workflow (no PR gate model).
- Committers are responsible for keeping `main` healthy before and after commit.
- Automation provides immediate signal, not committee process.

## Problem Statement

Industrial WebGPU stacks carry recurring CPU-side costs from:

- repeated runtime validation
- abstraction layering overhead
- IPC/serialization overhead in sandboxed modes

These costs often dominate high-frequency small-dispatch workloads.

## Core Thesis

Split validation into:

1. hoistable checks (compile/init-time candidates)
2. inherently dynamic checks (must stay runtime)

Then use Lean where it has highest leverage and keep Zig hot paths explicit and minimal.

## Security Position

Formal methods complement isolation, they do not replace it. Doe supports two distinct security modes depending on the trust profile of the workload:

### 1. Ahead-of-Time Verification (Lean + Zig)
- Intended for trusted, pre-verified workloads (e.g., verified WASM games, known-safe assets).
- Lean mathematically proves invariants and bounds-checks offline.
- Zig executes the provably-safe workload with zero runtime validation overhead for maximum performance.

### 2. Runtime Verification (Full Zig)
- Intended for untrusted, dynamic web content (Chromium-style drop-in).
- Zig forcefully handles dynamic bounds-checking and sandbox enforcement at runtime.
- Formal proofs reduce the logic defect surface of the runtime itself, while deterministic boundaries enforce input admissibility.

In both modes, sandbox/process boundaries remain required where deployment topologies demand them.

## Standalone Execution Model

Doe is self-contained.

- Doe owns its own runtime, verification boundary, benchmark harness, and replay tooling.
- Dawn and wgpu are external incumbents used as comparison baselines only.
- Doe does not depend on incumbent internals at runtime.

## Zero-Tape Operating System

### A) Agent Miner (Nightly Drift Ingest)

- automated miner scans Dawn/wgpu quirk logic nightly
- emits structured quirk candidates into machine-readable data
- committers review and merge data updates quickly

No manual source archaeology as a recurring process.

### B) Lean Guard (Invariant Gate)

- consumes quirk data and contract inputs
- checks core invariants and admissibility properties
- emits validator artifacts or fails fast for quirks requiring Lean

No meeting-based safety review loop.

### C) Zig Muscle (Specialized Execution)

- build reads quirk/profile data at comptime
- generates specialized backend paths
- avoids runtime toggle branching in hot loops when static specialization is possible

## Debug-First Determinism

### Flight Recorder

- fixed-size ring buffer for structured events
- zero-allocation write path
- crash/device-loss dumps as replay artifacts

### Replay Tooling

- binary artifact replay reproduces command/event sequence
- used for deterministic root-cause isolation
- replay consistency is treated as a core product property

## Performance Ratchet (Commit Mode)

- benchmarking runs continuously on commit
- regressions are surfaced immediately as machine signals
- committers must fix, revert, or explicitly annotate baseline movement

No delayed “perf sprint” process.

## Incumbent Comparison Policy

“Beat incumbents” means measured deltas, not narrative claims.

- Baselines: Dawn (C++) and wgpu (Rust)
- Metrics: encode overhead, validation overhead, submit latency (p50/p95/p99), allocation churn
- Evidence: reproducible run metadata + published benchmark reports
- Claim states:
  - `scaffold`: placeholder outputs, no incumbent claim allowed
  - `directional`: measured deltas exist but sample depth is below confidence target
  - `substantiated`: measured deltas + stable trend window + reproducible metadata

Attribution method for "why Zig + Lean":
1. Zig attribution: compare specialized vs non-specialized Doe paths with same policy/proof posture.
2. Lean attribution: compare defect/reject/replay outcomes with and without Lean-required quirk sets.
3. Incumbent attribution: compare Doe against Dawn/wgpu on identical metric IDs and workload IDs.
4. Any claim missing this decomposition is reported as "unattributed".

## Runtime Architecture

### Lean Contract Layer

- formalize selected state machine invariants
- prove admissibility-critical properties
- keep proof scope aligned to leverage and maintenance cost
- apply Lean proof requirements by per-quirk policy, not universally

### Zig Execution Layer

- explicit allocators and bounded memory behavior
- specialized backend paths via comptime
- deterministic trace emission and low-overhead submission paths

### Boundary Decision Layer

- input: state/policy/profile/hashes
- output: `accept(receipt)` or `reject(trace)`
- rule: no side effects before `accept`

## Backend Strategy

- target both native and WASM-compatible deployment modes with minimal overhead
- primary lane first: Vulkan
- secondary lane next: Metal
- expand only after baseline stability and conformance trend are healthy

## Validation Split (Hoisted vs Dynamic)

### Hoisted First

- static compatibility checks
- structural command validity
- profile and limit compatibility derivable from known state

### Always Dynamic

- device-loss and async lifecycle behavior
- queue/timeline synchronization
- residency and transient runtime pressure

## Success Criteria (Trend-Based)

- latency trend improves on representative workloads
- correctness incidents trend down
- replay success and determinism trend up
- conformance trend improves on selected CTS subsets
- proof coverage grows only where it yields clear correctness/perf value
- benchmark deltas against Dawn/wgpu trend in Doe's favor on targeted workloads

No hard numeric threshold is required for v0 acceptance.

Minimum acceptance contract for incumbent claims:
1. use metric IDs defined in `fawn/config/benchmarks.json`
2. include matching workload IDs and backend IDs in run metadata
3. include baseline deltas for Dawn and wgpu from measured runs
4. mark report `comparisonStatus=substantiated` before using "beats incumbents" language

## v0 Delivery Reality

v0 is process and data-contract heavy by design, but implementation-light:

- module scaffolds + worked examples first
- binding gates + hard thresholds later as empirical baselines stabilize

## Risks

1. Conformance sink from backend-specific divergence
2. ABI compatibility drag (`webgpu.h` parity costs)
3. proof maintenance burden under spec churn

## Mitigations

1. lane-first rollout (Vulkan first, then Metal)
2. isolate compatibility layer from internal fast paths
3. maintain explicit “proof ROI” policy so proof scope stays high leverage
4. automate drift detection from upstream stacks

## Immediate Next Steps

1. implement the agent miner prototype and structured quirk dataset
2. define the first Lean invariant bundle for admissibility-critical checks
3. build commit-time benchmark + replay harness
4. publish first baseline trend report for Dawn/wgpu comparisons
