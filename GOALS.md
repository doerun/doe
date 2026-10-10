# Doe goals

## Mission and thesis

Doe develops an independently usable WGSL compiler and native WebGPU runtime.
Either may earn adoption without requiring the other. Their contributions require
separate evidence. DoeRuntime owns resources, synchronization, lifecycle, and
native execution; the compiler owns shader meaning and target lowering.

**GPU programs should be ordinary software: executable, inspectable, and portable across hardware.**

Make existing local applications materially faster, less memory intensive, and
cheaper in CPU overhead through replacement of their WebGPU implementation. Developers should be able to substitute Doe beneath
supported WebGPU workloads while preserving shaders, application logic, and
declared numerical requirements. Exact outputs are required where justified;
other workloads use frozen, independently evaluated tolerances. Universal bit
identity is not a product promise.

## Independent compiler and runtime adoption

Compiler outcomes include compilation latency, diagnostics, supported shader
semantics, and generated-program performance. Runtime outcomes include resource
management, submission, completion, memory, and application integration. A compiler
result does not establish runtime adoption, or conversely. A new compiler campaign
needs a concrete opportunity; closed browser optimizer experiments remain closed.

## Runtime entrypoints

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
- Acceptance sequence: Ordinary execution, independent framework integration, and binding transfer establish native value. Browser replacement is an optional, separately selected adoption route. The ordered acceptance milestones live in [the strategy contract](config/doe-product-strategy.json), projected from [the thesis](docs/thesis.md); they do not block correctness repairs or independent installation work.
- Backend focus: Vulkan is the current engineering focus. Work proceeds in bounded batches. Switching to Metal requires an explicit prioritization decision and handoff; D3D12 remains deferred. Existing regression checks do not constitute parallel optimization campaigns.

## Execution milestones

Retain accepted improvements and correctness repairs. Close a bounded ordinary
execution optimization with a material complete-application advantage under
predeclared regression limits; simultaneous latency, CPU, and memory victory is
not required. Reject ineffective candidates without extending one reranker
indefinitely or declaring the advantage achieved.

The pinned ONNX Runtime integration already executes existing WebGPU operators
through Doe on the qualified Vulkan host. The [campaign](docs/onnx-vulkan-campaign-contract.md),
[lifecycle qualification](docs/native-device-lifecycle-contract.md), and
[evaluation installation](docs/onnx-vulkan-installation.md) retain that bounded
evidence. The versioned package has local isolated-installation acceptance.
Material replacement advantage, broader compatibility, another operator's
reproduction, and retained adoption remain unestablished.

Next make that package available for independent installation, obtain one real
consumer requirement, and select further engineering against agreed acceptance.
Do not repeat initial substitution discovery or expand the experimental plugin's
operator stack by default. Discovery and technical release are distinct gates;
correctness, packaging, and useful engineering do not require a paying customer.
Supported embedding, binaries, and maintained releases remain commercial
hypotheses until repeated voluntary use demonstrates demand.

Make inference, general computation, and interactive rendering binding transfer
evidence through unchanged applications, independent correctness references, and
complete-operation measurements. Doppler owns models and inference and remains a
demanding customer; another framework must establish independent adoption.
Expand hardware coverage around demonstrated advantages.

After explicit selection, independent native wins, and transfer evidence, attempt
bounded Chromium integration preserving ordinary WebGPU behavior through validation and process
boundaries. Broader browser adoption depends on compatibility, security,
maintainability, and application benefits. Native or compiler adoption does not
require browser replacement.

Measure development by reproduction-to-verified-improvement time using existing
work records. Keep compiler, backend, and host boundaries independently testable.
Reuse, refactoring, and agent assistance serve these milestones without adding
unnecessary execution overhead.

Exceptional execution and exceptional implementation are independent standards.
Deliberate compiler and backend engineering is an active workstream: a change
that materially clarifies ownership, dependencies, diagnostics, or extension
points can be worthwhile without a speedup. Preserve behavior and check execution,
build cost, and binary size through the existing style guide and review ledger.

## Explicit exclusions

Doe does not build browser user interfaces, Flutter engine replacements, peer-to-peer compute protocols, or distributed cloud training clusters.

---

Links:
- Strategic intent links to local invariants in [INTENT.md](INTENT.md).
- Technical boundaries and owned authority are chartered in [CATSCAN.md](CATSCAN.md).
