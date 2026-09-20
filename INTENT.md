# INTENT: Doe

Parent: none

## Need

Engineers need portable GPU compilation and execution, understandable failures,
and safe reuse of repeated work across qualified hardware without hidden fallbacks.

## Target

Deliver one independent compiler/runtime through ordinary WebGPU and optional
reusable programs. Preserve supported application semantics and declared numerical
requirements; earn adoption through measured application advantage. Qualification
receipts evaluate this product without becoming mandatory application machinery.

## Invariants

- Identity-bearing artifacts cryptographically bind source, lowering policy,
  command graphs, and outputs; mandatory qualification evidence remains mandatory.
- Unsupported device features, memory overflows, or backend mismatches fail closed; silent fallback to unverified CPU execution is prohibited.
- DoeProof evaluates providers objectively; candidate optimizations receive no promotion without passing against a frozen semantic oracle.
- Runtime provider substitution preserves application logic and permits clean
  rollback without abandoning live GPU ownership.
- Execution evidence is bound to physical adapter and driver identity; simulator runs cannot qualify hardware claims.
- The compiler owns shader meaning; the runtime owns physical execution and
  lifetime. Host adapters never substitute shader behavior from source patterns.
- Immutable descriptions, device-specific prepared resources, and invocation
  state have separate owners. Exact bytes, entrypoint, layout, effective compiler
  options, device identity, and native allocation generations govern reuse.
- Compatible parameter changes may reuse resources. Structural replacements
  prepare before activation; failed preparation preserves the working program.
  Incompatible resident-state changes require explicit approval.
- Submission carries resource obligations until established terminal completion.
  Timeout stops waiting, not GPU use; unknown completion forbids unsafe reuse
  or destruction. Terminal failure permits cleanup but never successful output.
- Ordinary WebGPU, command execution, and prepared programs share semantic rules
  without requiring a universal interpreter. The runtime remains usable without
  development tools, detailed tracing, or artifact publication.
- Agents propose changes offline. Frozen tests and independent comparisons govern
  promotion; application requests cannot silently rewrite the selected runtime.

## Evidence

- Passing CATSCAN gate via `python3 bench/gates/catscan_gate.py`.
- Passing execution contract tests and compiler parity benchmarks in `bench/`.
- Deterministic verification receipts matching the declared DoeProof schema.

## Non-goals

- General-purpose application framework or agent orchestration platform.
- Universal WebGPU browser implementation or full Dawn replacement without dedicated evidence gates.
- Distributed cluster scheduling or multi-node training fabric.

## Truth

Physical execution traces and reproducible output receipts govern all performance and correctness claims. Passing compiler syntax checks does not prove hardware suitability.

---

Links:
- Root strategy: [GOALS.md](GOALS.md)
- Technical charter: [CATSCAN.md](CATSCAN.md)
