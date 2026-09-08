# Doe strategy: make GPU programs ordinary software

Build the independent GPU compiler and runtime that makes useful computation
easy to create, cheap to repeat, and portable across supported hardware.

Agents and human developers should be able to create a simulation or image
analysis, accelerate it, inspect failures, and publish the working computation
without becoming GPU systems engineers. DoeRuntime supplies execution. DoeProof
supplies impartial evaluation. Neither Doppler adoption nor a new browser is a
prerequisite. This document owns strategy; component charters constrain
implementation and artifacts establish current results.

Run this as one execution-ownership program. First prove ordinary provider
replacement in an unchanged Node application using a retained `doe-gpu` package,
fixed tests, explicit identities, complete-operation accounting, and immediate
rollback. Then demonstrate interactive reuse and agent-assisted acceleration.
Bun, Electron, native embedding, and additional hardware earn their own host
evidence; qualifying every host is not a prerequisite to the first Node result.
Promote transferable corrections and expand embedding channels only after
application wins. Resource allocation and portfolio bounds live in
[`doe-product-strategy.json`](../config/doe-product-strategy.json).

## Own the executable program

The proposed primitive is a reusable GPU program: shaders, dependencies,
resource requirements, permitted input variations, and executable plans.
Optimize allocations, pipeline preparation, transfers, command construction,
synchronization, and repeated submission as well as kernels. Retain useful
state and rebuild only affected assumptions.

Safe reuse is the central invention to earn. Shape, binding, shader, driver, or
device changes must invalidate affected state. Removing a check without proving
its precondition is a correctness bug. After the ordinary-execution demonstration,
begin reuse with explicitly declared fixed-shape compute, retain deterministic
Zig guards, and eliminate work through Lean only
when current proof artifacts discharge the actual preconditions. Keep ordinary
execution available where reuse is unsuitable.

The WGSL compiler, native backends, resource contracts, and declarative plan
executor are foundations. Their existence does not establish a complete program
compiler. The initial additive API and its limits live in
[reusable compute programs](reusable-compute-programs.md).

## Enter through compatibility and earn reuse

Make `doe-gpu` straightforward to try in controlled Node, Bun, Electron, and
native applications. Preserve familiar WebGPU operations and existing WGSL.
Offer repeated computation through an optional declared-program interface.
Replacing a provider cannot eliminate arbitrary JavaScript orchestration that
an application continues to execute.

Each external application compares the strongest incumbent, ordinary Doe, and
prepared DoePlan. Complete useful-operation latency owns the application result;
kernel timing helps diagnose it. Retain cold initialization, preparation, first
execution, repeated tails, CPU and GPU work, memory, allocations, submissions,
teardown, and recovery. Missing measurements remain missing acceptance evidence.

The promise is the same useful computation with less repeated work, smaller
resource demands, and clearer failures. Compatibility substitution and explicit
program integration are different treatments: freeze and disclose each one,
and give incumbent controls equivalent persistent pipelines, bindings, batching,
and caches. An interface alone is not an ownership win if the same optimization
works equally well above an incumbent.

Prepared workflows already exist in
[CUDA Graphs](https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/cuda-graphs.html),
and IREE combines scheduling with execution compilation. Doe must differentiate
through WebGPU integration, deployment simplicity, safe reuse, and measured
application outcomes; graph execution is not a Doe invention.

Ordinary browser imports still use browser-owned WebGPU. Browser replacement
requires its own integration, artifact, and acceptance evidence.

## Make corrections transferable

Preserve relationships from original WGSL through IR and backend programs to
execution. Make failures reproducible and effects inspectable. A contributor
should supply a small reproduction and comparison without understanding the
entire runtime.

```text
application failure or measured repeated work
-> minimized source and frozen independent oracle
-> general compiler transformation, resource policy, or backend correction
-> permanent regression and physical evaluation
-> transfer to an unrelated program
-> maintained release gate
```

DoeLab owns this failure-to-correction process. Its next product-level test is
whether accumulated corrections make subsequent applications easier to support,
not whether the regression archive grows. Keep source, interfaces, and
reproduction tools open. Compound development momentum, maintained integrations,
and implementation knowledge through useful results.

## Demonstrate a newly practical application

Start with unchanged ordinary WebGPU in a non-Doppler application on physical
AMD Vulkan. Prepared image-processing and scientific computations follow as
separate treatments. Reproduce useful mechanisms on another application and
qualify Apple Metal independently rather than transferring support claims.

Before tuning, freeze source, inputs, independent numerical requirements,
hardware and driver, fallback policy, lifecycle obligations, timing scopes,
memory accounting, and a meaningful application outcome. Identity hashes bind
bytes; numerical comparisons establish acceptable results.

Compare against competently configured Dawn and wgpu with persistent pipelines,
batching, and caches. Report preparation, cold startup, repeated latency and CPU
cost, peak memory, cancellation, recovery, and when preparation is recovered.
Keep raw samples, tails, failures, and structural work. Distinguish process RSS
and requested buffer bytes from peak GPU memory. Disclose host and effective
readback differences rather than presenting them as runtime speed.

Cross a predeclared useful boundary: a missed interactive deadline, an analysis
memory limit, or unacceptable repeated CPU cost. Numerical parity alone does
not establish that crossing. A transferred correctness fix does not establish
a transferred performance breakthrough. Preserve losses and audit implausibly
large wins before accepting them.

Repository-owned applications can prove a mechanism. External voluntary
adoption and retention require separate evidence from the application's owner.
Receipts, internal benchmarks, sibling integrations, and paid qualification do
not establish adoption. Revenue is not required for the first proof.

## Ownership and independent controls

DoeRuntime is primary. DoeProof remains useful around the strongest eligible
incumbent and cannot select a favorable execution provider. Doppler may supply
a workload or become a user; it receives no qualification preference.

Preserve I0, I1, W0, D0, and credible eligible P0 under the governed
[runtime ownership decision](runtime-ownership-decision.md). An unchanged
application measures provider substitution. An explicit program integration
measures the disclosed application/runtime treatment under identical useful
work. Each freezes the strongest control; neither inherits the other's result.

Priorities remain correctness, operational reliability, compatibility, material
end-to-end value, simple installation, and useful diagnostics and replay.
Receipts cannot compensate for incorrect, unstable, incompatible, or slower work.

## Focus and founder responsibilities

The immediate engineering focus is a smaller, clearer, cheaper Zig core. Give
each semantic decision one owner, make resource acquisition and release
complete, and remove unnecessary allocation, repeated analysis, and command
preparation. Qualification verifies these improvements. Use compile-time
programming for facts known at build time; resolve physical device and driver
facts at initialization when their lifetime permits. Shared algorithms must
reduce real work without hiding backend-specific responsibilities. Preserve
characterizing tests and check execution cost, generated code size, and build
cost before accepting a structural optimization.

Compiler/runtime ownership covers transformations, reusable plans, invalidation,
resource lifecycle, and backend execution. Application/evaluation ownership
covers integration, packaging, independent controls, diagnostics, and reproducible
tests. Both own the frozen application outcome and transfer test.

Exclude browser construction, Flutter replacement, peer networks, distributed
training, and universal accelerator support from the first demonstration. Dynamic
shapes follow explicit fixed-shape assumptions and verified invalidation.

Later, embedding partners may distribute the same runtime through frameworks,
applications, or browser distributions. Fawn remains separately gated. Existing
A/B/C/D and K0 browser laws retain their meaning; browser construction is not a
dependency. Accelerator work retains separate hardware admission and cannot
broaden the initial matrix through simulator evidence.

## Prioritized target journeys

These are target outcomes, not completed support, release commitments, or existing
customers. Build the first three as direct demonstrations; the remaining four
distribute and improve the same compiler/runtime. AMD and Qualcomm are prospective
technical users only. Each additional hardware/operating-system tuple requires
its own qualification.

### 1. Independent developer: improve an application without rewriting it

Replace a Node application's current WebGPU provider with pinned `doe-gpu`,
retaining WGSL, inputs, tests, and application logic. Compare complete operation
latency, startup, CPU overhead, memory, and slow executions without weakening
validation or changing accepted results. Unsupported operations produce useful
errors; rollback is immediate. Reuse in a subsequent application establishes
repeat value. Ordinary execution must earn this result before a special
interface or application-specific optimization is required.

### 2. Small application team: keep editing and simulation interactive

An Electron editing or simulation application prepares repeated computation,
retains compatible state, and updates parameters during use. Check shader edits
before activation; incompatible state changes require explicit approval, and
failed edits preserve the working program. Measure preview responsiveness,
bounded memory, cancellation, reopening, preparation, and final cleanup during
prolonged use. Transfer corrections into the shared runtime, not a product fork.
Electron renderer and main-process evidence remain separate.

### 3. Research laboratory: accelerate unfamiliar numerical work

A researcher supplies a slow routine, representative inputs, and frozen
independent reference tests. An agent proposes WGSL and evaluates candidates
using Doe diagnostics under explicit process and memory budgets. Retain the
accepted program, supported-device record, and a reproducible collaborator
package. Numerical requirements never change to admit a candidate. New
algorithms and changed drivers require fresh checks; this is bounded application
development, not a general agent framework.

### 4. AI framework maintainer: improve execution beneath applications

Evaluate the same runtime beneath an existing WebGPU path or a separately
implemented provider integration. Preserve model interfaces and supported
semantics; include loading, small dispatches, concurrency, and output transfers
in inference comparisons across models. Framework distribution must demonstrate
dependable upgrades and explicit unsupported operations. Doe does not acquire
conversion, tokenization, or application-policy ownership.
[ONNX Runtime's provider interface](https://onnxruntime.ai/docs/execution-providers/)
is an integration reference, not evidence of a Doe provider.

### 5. Equipment manufacturer: ship dependable offline inspection

Embed the pinned runtime in an inspection workstation with fixed camera and
measurement workloads, independent numerical checks, resource budgets, and a
qualified hardware matrix. Installation requires no technician-managed shader
toolchain or cloud image transfer. Include camera transfer and synchronization,
processing deadlines, prolonged memory behavior, fault reports, and recoverable
updates. Reuse the integration in another product. Machinery control and safety
remain separately designed and validated application responsibilities.

### 6. AMD: improve real applications on Radeon

A prospective compiler or developer-tools evaluation runs unchanged application
corpora through Doe and strong incumbent implementations, inspects generated
programs and submissions, and contributes transferable compiler/runtime fixes.
Require reproducible complete-application benefit across workloads and separately
qualified GPU generations. Driver workarounds remain precisely scoped and
removable; vendor-specific work stays beneath independently usable interfaces.
[AMD's graphics developer resources](https://www.amd.com/en/developer/browse-by-product-type/graphics-resources.html)
provide technical context, not evidence of a relationship or accepted result.

### 7. Qualcomm: sustain GPU features within power limits

A prospective platform/application integration targets Adreno through a
separately qualified Vulkan or D3D12 configuration. Exercise camera processing,
effects, and inference over prolonged sessions; measure energy per accepted
result, temperature, responsiveness, and memory against the strongest practical
alternative. Portable WGSL remains above architecture-specific optimization.
ARM packaging and each operating system/device integration require work.
GPU capability does not imply Hexagon NPU support.
[Qualcomm's Vulkan memory discussion](https://www.qualcomm.com/developer/blog/2026/05/high-performance-memory-extension-optimize-memory)
is technical context, not Doe qualification.

## Acquisition hypothesis

An acquirer would buy an execution advantage, its engineering team, development
momentum, and an ecosystem that depends on it. Open code can be licensed;
ownership must add difficult implementation knowledge and maintained integration
capacity that licensing or sponsorship does not supply.

AMD's Nod.ai acquisition is a precedent for interest in compiler expertise and
optimized deployment, not evidence of Doe's valuation. Buyer interest and
valuation remain hypotheses requiring independent evidence.

## Strategy execution map

- [GOALS.md](../GOALS.md) owns mission and durable goals.
- [CATSCAN.md](../CATSCAN.md) and child charters own component authority.
- [Reusable compute programs](reusable-compute-programs.md) owns initial API,
  invalidation, reproduction, and limitations.
- [Developer wedge](node-bun-developer-wedge.md) owns package integration and
  downstream promotion.
- [Product strategy contract](product-strategy-contract.md) maps strategy into
  `config/doe-product-strategy.json`.
- [Performance](performance-strategy.md), [workloads](workload-system.md), and
  [process](process.md) own measurement, evidence, and stage law.
- [Ecosystem](ecosystem.md), `config/ecosystem-registry.json`, and
  `reports/ecosystem/` own external evaluation and adoption state.
- [Support matrix](doe-support-matrix.md) and `reports/claim-index.json` own
  promoted support and public claim eligibility.
- [Browser lane](browser-lane.md) owns the separate browser evidence path.

Artifacts own current outcomes. Strategy prose does not promote an
implementation, benchmark, package, browser, or adoption claim.
