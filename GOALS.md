# Doe goals

## Mission and thesis

DoeRuntime is the independent, provider-neutral GPU compiler and native runtime in the `doe/` repository: the owned WGSL compiler, GPU runtime, resources, synchronization, lifecycle, and native backends.

**GPU programs should be ordinary software: executable, inspectable, and portable across hardware.**

Make existing applications easier to accelerate, and repeated computations
cheaper to execute safely. Developers should be able to substitute Doe beneath
supported WebGPU workloads while preserving shaders, application logic, and
declared numerical requirements. Exact outputs are required where justified;
other workloads use frozen, independently evaluated tolerances. Universal bit
identity is not a product promise.

## One product, two entrypoints

Ordinary WebGPU through `doe-gpu` or native embedding is the first experience.
Installation, startup, complete-operation latency, memory, and understandable
failures determine its value. Optional `doe-gpu/compute-program` lets applications
declare repeated work and retain compatible resources incrementally; it is not
a prerequisite for ordinary execution.

Independent developers, Electron teams, framework maintainers, researchers, and
hardware vendors use the same compiler/runtime. Prioritize compute while
preserving shared graphics semantics. Do not create application- or vendor-specific
runtimes. [Reusable compute programs](docs/reusable-compute-programs.md) owns the
current fixed-shape buffer-compute interface and its execution-mode limits;
textures, dynamic dimensions, and arbitrary graphics capture require separate
extensions and qualification.

## Desired outcomes

1. **Governed Local Execution**: Support a strictly bounded matrix of real application workloads on declared runtimes, platforms, adapters, drivers, and backends.
2. **Program-Identity Preservation**: Cryptographically bind source WGSL, pipeline layout, command graphs, and lowering policies into immutable execution receipts.
3. **Fail-Closed Control**: Provider selection, unsupported hardware capabilities, synchronization faults, and fallback paths fail closed immediately with inspectable error envelopes.
4. **Independent Correctness**: Mandate a semantic oracle and declared exactness class before promoting any kernel optimization or execution schedule.
5. **Application-earned ownership**: Earn adoption where matched controls prove measurable application advantages over pinned incumbent implementations.
6. **Safe reuse**: Separate immutable program descriptions, device-specific prepared resources, and invocation inputs/completion. Exact identity and resource lifetime authorize reuse; hashes only locate candidates. Prepare structural replacements before activation, preserve the working program on preparation failure, and require explicit approval for incompatible resident-state changes.
7. **Enforced decisions**: Use Zig's compile-time checks for structural completeness, with independent behavioral and lifetime tests. Explicit allocators, checked arithmetic, acquisition rollback, bounded caches, and backend-private state remain implementation obligations, not automatic language guarantees.

## Operating loops

1. **Ordinary Execution Loop**:
   ```text
   Compile shader meaning -> Prepare resources and bindings -> Submit -> Observe completion -> Return result or failure
   ```
2. **Hardware Qualification Loop (DoeProof)**:
   ```text
   Freeze workload and numerical requirements -> Run independent oracle checks -> Compare matched controls -> Apply qualification gates
   ```
3. **Offline improvement loop**:
   ```text
   Retain a failure or measured cost -> Propose a bounded candidate -> Test against frozen criteria -> Independently confirm -> Promote or reject
   ```

Ordinary execution remains useful without DoeProof, development agents, or
artifact publication. Detailed tracing is optional; runtime requests execute a
selected version without rewriting their compiler or runtime. Qualification
requires its declared evidence independently of what ordinary applications enable.

## Strategic constraints

- Hardware impartiality: Doe operates across standard WebGPU and WGSL specifications; collaborating products receive no private provider preference.
- Non-interference: Supporting feature value (such as DoeProof) cannot be counted as runtime adoption.
- Safe revert: Provider substitution must permit clean reversion to the prior provider; rollback never abandons live GPU ownership.
- Deployment: No mandatory browser or cloud service. Platform drivers and frameworks remain dependencies; there is no universal zero-dependency or zero-allocation claim.
- Support: Metal, Vulkan, D3D12, and additional operating systems earn support separately. iOS and Android require implemented paths and physical tests before support is promised.
- Diagnostics: Report the best established source, validation, resource, submission, or native failure location. Do not invent a shader location for an unattributed hardware fault.
- Acceptance sequence: Demonstrate a dependable ordinary-provider application advantage, then demonstrate safe reuse benefiting another application. Measure allocation reductions and latency on named paths, not through universal promises.

## Explicit exclusions

Doe does not build browser user interfaces, Flutter engine replacements, peer-to-peer compute protocols, or distributed cloud training clusters.

---

Links:
- Strategic intent links to local invariants in [INTENT.md](INTENT.md).
- Technical boundaries and owned authority are chartered in [CATSCAN.md](CATSCAN.md).
