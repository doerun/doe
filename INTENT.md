# INTENT: Doe

Parent: none

## Need

Engineers need portable, deterministic GPU compilation and execution across diverse hardware platforms without proprietary vendor lock-in or unpredictable driver fallbacks.

## Target

Deliver an independent WGSL compiler and native GPU runtime that executes declared numerical workloads with hardware-bound identity, fail-closed synchronization, and impartial qualification receipts.

## Invariants

- Program source, lowering policy, command graphs, and execution outputs remain cryptographically bound to immutable hashes.
- Unsupported device features, memory overflows, or backend mismatches fail closed; silent fallback to unverified CPU execution is prohibited.
- DoeProof evaluates providers objectively; candidate optimizations receive no promotion without passing against a frozen semantic oracle.
- Runtime provider substitution in host applications preserves existing application logic and remains immediately reversible.
- Execution evidence is bound to physical adapter and driver identity; simulator runs cannot qualify hardware claims.

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
