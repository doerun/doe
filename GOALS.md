# Doe Goals

## Mission & Thesis

DoeRuntime is the independent, provider-neutral GPU compiler and native runtime in the `doe/` repository: the owned WGSL compiler, GPU runtime, resources, synchronization, lifecycle, and native backends.

**GPU programs should be ordinary software: executable, inspectable, and portable across hardware.**

High-performance GPU compute is historically trapped in proprietary vendor ecosystems and brittle platform-specific toolchains. Doe delivers an open, portable runtime where developers substitute an owned GPU provider beneath supported workloads, preserving exact numerical results without becoming low-level GPU systems engineers.

## Intended Beneficiaries

1. **Numerical & Systems Developers**: Engineers seeking reproducible, portable GPU execution across disparate vendors (Apple Silicon, NVIDIA, AMD, Intel) through unified WGSL.
2. **AI Runtime Implementers (Doppler)**: Machine learning frameworks requiring high-throughput, low-latency kernel dispatch and memory management without proprietary driver lock-in.
3. **Research & Scientific Teams**: Developers needing verifiable, hardware-attested execution receipts (DoeProof) to prove simulation and benchmark correctness.

## Desired Outcomes

1. **Governed Local Execution**: Support a strictly bounded matrix of real application workloads on declared runtimes, platforms, adapters, drivers, and backends.
2. **Program-Identity Preservation**: Cryptographically bind source WGSL, pipeline layout, command graphs, and lowering policies into immutable execution receipts.
3. **Fail-Closed Control**: Provider selection, unsupported hardware capabilities, synchronization faults, and fallback paths fail closed immediately with inspectable error envelopes.
4. **Independent Correctness**: Mandate a semantic oracle and declared exactness class before promoting any kernel optimization or execution schedule.
5. **Application-Earned Ownership**: Maintain DoeRuntime only where matched controls prove measurable speed or reliability advantages over pinned incumbent drivers.

## Operating Loops

1. **Ordinary Execution Loop**:
   ```text
   Compile WGSL -> Lower to Native Backend -> Bind GPU Resources -> Dispatch Commands -> Verify Exactness & Return Receipt
   ```
2. **Hardware Qualification Loop (DoeProof)**:
   ```text
   Ingest Workload -> Run Against Semantic Oracle -> Benchmark Incumbent Baseline -> Verify Tolerance & Energy -> Qualify Provider
   ```

## Strategic Constraints

- Hardware impartiality: Doe operates across standard WebGPU and WGSL specifications; collaborating products receive no private provider preference.
- Non-interference: Supporting feature value (such as DoeProof) cannot be counted as runtime adoption.
- Safe revert: Any provider substitution must permit immediate, clean reversion to standard drivers.

## Explicit Exclusions

Doe does not build browser user interfaces, Flutter engine replacements, peer-to-peer compute protocols, or distributed cloud training clusters.

---

Links:
- Strategic intent links to local invariants in [INTENT.md](INTENT.md).
- Technical boundaries and owned authority are chartered in [CATSCAN.md](CATSCAN.md).
