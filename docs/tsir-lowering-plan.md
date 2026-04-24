# TSIR lowering plan

## Purpose

The goal is one program and many faithful realizations. Doppler already treats
WGSL as the source program and WebGPU as one realization of that program.
Doe's job is to extend that discipline across backends without turning each new
backend into a separate hand-authored runtime.

The current CSL path does not meet that bar. It has one real direct-lowering
success case in matmul, but the broader non-GEMM path still depends on
classifier-selected template emitters. Those emitters rediscover placement,
residency, collectives, and numerical behavior locally. That is why the current
CSL blockers look like hardware fit failures when the deeper problem is
compiler structure.

This document defines the forward architecture for fixing that: a Tiled Spatial
IR (TSIR) between WGSL IR and backend emitters, with a parity oracle defined
before backend-specific lowering decisions.

This is a plan document, not a landed-claim document. Current code still uses
the classifier/template path for CSL. The in-tree `runtime/zig/src/tsir/`
surface is scaffolding for this plan, not a completed pipeline.

## What TSIR means

TSIR means **Tiled Spatial IR**.

Each word matters:

- **Tiled**
  - TSIR represents loop nests, iteration axes, and tile factors explicitly.
  - Tensor work is expressed as bounded tiles and declared reduction regions,
    not as "one PE materializes the full logical buffer" unless that is an
    explicit legal residency choice.
  - This is what lets the compiler reason about fit, streaming, recompute, and
    collective boundaries instead of inheriting those choices from a template.

- **Spatial**
  - TSIR makes placement on a PE fabric first-class.
  - It represents PE-grid topology, residency class per buffer, collective
    nodes, reduction-tree shape, and the target descriptor that says what the
    hardware can actually do.
  - That matters for Cerebras WSE-3 because placement, routing, and per-PE
    memory are part of the execution contract, not backend-private details the
    emitter can guess differently per kernel.

- **IR**
  - TSIR is a schema-backed, hashable compiler contract.
  - It splits stable source meaning from target-specific realization:
    - `tsir.semantic`
    - `tsir.realization`
  - Those structures produce distinct digests so manifests, receipts, and
    replay can pin the exact lowering unit, not only the original WGSL.

In short:

```text
WGSL -> TSIR -> mechanical backend emitters
```

instead of:

```text
WGSL -> classify -> per-kernel template logic
```

For Cerebras, the backend emitter is CSL plus the surrounding runtime-facing
artifacts. For WebGPU-shaped lanes, TSIR can drive a validated WebGPU lowering
surface such as WGSL re-emission or an equivalent backend-facing realization.
The key point is the same in both cases: backend codegen becomes mechanical
with respect to an explicit lowering contract.

## Surrounding context

TSIR is not a replacement for Doppler's program bundle and it is not a
replacement for Doe IR.

The surrounding boundary is:

1. **Doppler owns the source program contract**
   - manifest identity
   - execution graph
   - WGSL modules and digests
   - weights and runtime profile
   - reference transcript

2. **Doe's existing WGSL frontend owns semantic recovery**
   - lexer
   - parser
   - sema
   - Doe IR

3. **TSIR is the lowering contract after WGSL IR and before backend emission**
   - it is where tiling, residency, collectives, and exactness become explicit
   - it is where rejection becomes typed and replayable

4. **Backend-specific artifacts consume TSIR**
   - CSL emitter and HostPlan-facing artifacts for Cerebras
   - WebGPU/backend lowering artifacts for WebGPU-shaped lanes

5. **Parity compares each backend against the oracle defined over TSIR**
   - never backend-versus-backend only

For the CSL lane, this means HostPlan stays important, but it moves to the
right place in the stack. HostPlan is the runtime orchestration contract for
launches, tensors, and receipts. It should not also be the place where kernel
meaning, residency strategy, or numerical semantics are rediscovered. TSIR sits
before HostPlan and makes those decisions explicit once.

For the Doppler/RDRR lane, this means lowering becomes part of artifact
identity. The manifest still owns source identity. TSIR adds lowering identity:
what semantic kernel was lowered, what realization was chosen, what target
descriptor it was lowered for, and what exactness class or rejection reason
applies.

## Why TSIR is needed

TSIR is needed because the current classifier/template path does not scale as a
proof-bearing compiler boundary.

Today, each non-GEMM CSL emitter tends to rediscover its own answers to
questions that should have one compiler-level answer:

- what part of the loop nest belongs on each PE
- whether a buffer is replicated, sliced, streamed, or recomputed
- what the reduction or collective structure really is
- what numerical order is declared versus accidental
- when to reject because the kernel cannot fit or cannot lower faithfully

That local rediscovery causes three concrete problems.

First, **fit failures look like hardware facts when they are often emitter
facts**. If a template allocates `[num_tokens * hidden_size]` per PE, the
result looks like "Cerebras cannot run this kernel." The more accurate
statement is "this emitter materialized the wrong thing locally." TSIR is the
place where the compiler chooses a bounded residency strategy before emission.

Second, **auditability collapses**. A per-kernel template can be locally
correct and still impossible to compare across kernels because each one carries
different hidden placement assumptions. A schema-backed TSIR makes those
choices explicit and hashable.

Third, **parity has no stable lowering unit**. Without TSIR, the manifest pins
the source program but not the compiler's realization of that program on a
spatial backend. That makes replay weaker than it should be, because a
compiler-policy change can silently alter the lowered kernel without changing
the source program identity.

TSIR fixes these three problems by moving the load-bearing decisions into a
shared compiler layer:

- the frontend recovers structure once
- the planner chooses residency and collectives once
- the emitter stops making semantic decisions
- the parity oracle judges the declared lowering, not template accidents

## Current scaffold already in tree

Phase A compiler surface has landed for the bootstrap catalog
(`fused_gemv`, `rms_norm`, `gather`). For live TSIR status refer to
[`docs/status/tsir.md`](status/tsir.md); the plan doc gives the shape
of what exists, not counts or dates. Archive of 2026-04-23 TSIR Step 4
incremental history lives in
[`docs/status/archive/2026-04.md`](status/archive/2026-04.md).

TSIR core under `runtime/zig/src/tsir/`:

- `schema.zig` — two-level TSIR shape (`Semantic`, `Realization`), exactness
  classes aligned to RDRR, rejection taxonomy, and `SemanticBody` contract
  (body ops for `fused_gemv` / `rms_norm` / `gather`, RMSNorm epsilon source
  + binding/offset plumbing).
- `digest.zig` — canonical serialization and SHA-256 digests for semantic,
  realization, and emitter-code identity.
- `family_hint.zig` — structural classifier that infers coarse family hints
  from IR shape; hints are tiebreakers only, never change feasibility or
  rejection.
- `frontend.zig` — WGSL IR to TSIR semantic lowering for bindings, axes,
  reductions, collectives, typed rejections, family hints, and
  kernel-specific semantic body recovery (fused_gemv, rms_norm, gather).
- `planner.zig` — correctness-first TSIR realization planning for
  residency, tile factors, PE grid, reduction tree choices,
  descriptor-checked collectives, target hashes, and typed rejections.
- `collective_synthesis.zig` — dedicated Step 6 pass for descriptor-backed
  collective lowering: native-capability + exactness checks, fabric-color
  assignment under the descriptor's budget, and typed rejections when a
  target cannot host the declared collective. Consumed by the planner.
- `reference_interpreter.zig` — scalar reference oracle covering the three
  bootstrap families across `{f32, f16, bf16}` with `strict_ordered` and
  `associative_allowed` reductions plus RMSNorm `literal_f32` and
  `uniform_field` epsilon. Unsupported shapes fail closed with
  `NotImplemented`.
- `emit_csl.zig` — mechanical TSIR-to-CSL skeleton emitter (contract
  serialization; does not yet produce executable kernel bodies).
- `emit_webgpu.zig` — mechanical TSIR-to-WebGPU skeleton emitter
  (contract serialization only).
- `emit_msl.zig` / `emit_dxil.zig` / `emit_spir_v.zig` — portable backend
  skeleton emitters consuming a shared text skeleton helper.
- `emit_text_skeleton.zig` — shared contract-text serialization helpers
  used by the five backend skeleton emitters.
- `mod.zig` — public module surface.

Each of the five backend emitters exposes an `emitterCodeDigest()` that
SHA-256s its own source text plus the shared skeleton helper source.
Pairwise distinctness across all five is locked by test so
manifest-lowering entries cannot silently ambiguate which backend
produced an artifact.

Target descriptors under `runtime/zig/src/targets/`:

- `webgpu_generic.zig` and `wse3.zig` — conservative portable WebGPU
  profile and Cerebras WSE-3 profile. Descriptor fields split into
  `correctness` (hashed, participates in realization identity) and
  `planner` (search-quality hints only). Includes
  `runtime_sized_binding_policy` so runtime-sized storage bindings
  resolve to `host_copied` (WebGPU) or `fabric_streamed_with_loader`
  (WSE-3) rather than an implicit choice.
- `mod.zig` — descriptor hash helpers that participate in realization
  identity.

Schema + contract surfaces under `config/`:

- `doe-tsir-semantic.schema.json` — canonical JSON shape for TSIR
  semantic artifacts including RMSNorm body contract.
- `doe-tsir-realization.schema.json` — canonical JSON shape for TSIR
  realization artifacts including residency decisions, tile factors,
  and reduction tree nodes.
- `doe-tsir-manifest-lowering.schema.json` — manifest binding entry
  shape: `(kernelRef, backend, targetDescriptorCorrectnessHash,
  tsirSemanticDigest, tsirRealizationDigest, emitterDigest,
  exactness, rejectionReasons)`.
- `doe-parity-receipt.schema.json` — parity CLI receipt shape.

Bench tooling + fixtures:

- `bench/tools/doe_parity.py` — manual parity CLI gate. Reference
  interpreter and backend lanes remain stub-only (`not_implemented`)
  until a subprocess harness to the Zig oracle and executable backend
  emission land.
- `bench/tools/tsir_manifest_lowering.py` — schema-backed builder for
  `integrityExtensions.lowerings[]` entries.
- `bench/fixtures/tsir-manifest-entries/` — bootstrap manifest-lowering
  fixtures pairing the three bootstrap families against both
  `webgpu-generic` and `wse3` target descriptors.
- `bench/gates/nightly_tsir_parity_canary.py` — advisory nightly canary
  that drives the bootstrap fixture set through the parity CLI without
  promoting stub backend lanes to a claim.
- `runtime/zig/tests/tsir/bootstrap/` — pinned `.wgsl`, hand-sketched
  `.tsir-semantic.json`, and per-target `.tsir-realization.*.json`
  plus `.notes.md` for each bootstrap family.
- `runtime/zig/src/tsir_bootstrap_manifest_inputs.zig` — build-step
  entrypoint invoked by `bench/tools/generate_tsir_manifest_fixtures.py`
  via `zig build tsir-bootstrap-manifest-inputs` to materialize the
  canonical digest inputs the Python builder pairs with target descriptor
  hashes and emitter-code digests.

Rejection taxonomy is locked across five surfaces — the Zig canonical
enum, the Python CLI's `REJECTION_REASONS`, and the three JSON schemas
that carry rejection enums — by a cross-schema lockstep test; the Zig
enum is additionally locked by a scaffold test for exhaustiveness.

The missing work is executable kernel-body emission in the backend
skeleton emitters, the parity CLI subprocess harness that shells into a
Zig oracle binary, AOT convert-time lowering with a correctness-input
cache key, Loop 3 per-family parity receipts under `reports/parity/`,
manifest-binding of those receipts into Doppler's
`integrityExtensions.lowerings[]`, and the attention phase (Phase B)
with its sollya transcendental determinism.

## Design rules

The plan keeps five rules fixed:

1. The parity oracle is the definition of correctness. Backends compare against
   the oracle, never against each other.
2. Exactness classes reuse RDRR vocabulary verbatim. No parallel taxonomy.
3. Lowering is manifest-bound and hashable. Compiler policy is not allowed to
   drift silently.
4. Unsupported kernels fail closed with typed rejection reasons.
5. The manual parity CLI is the gate. This is not a CI-first design. A nightly
   canary parity run on a fixed kernel set is allowed as low-cost regression
   insurance; PR-gating CI is still out.

## Scope and phasing

Realistic floor for this work is **12–18 months on one compiler engineer**,
more if attention parity includes flash semantics. The plan is four phases,
each with a concrete exit criterion:

- **Phase A — pipeline proof (4–6 months).** Steps 1 through 9 for the first
  three kernel families: fused GEMV, RMSNorm, gather. Oracle, descriptors,
  TSIR schema, frontend, residency, collective synthesis, mechanical emitter,
  parity CLI, three kernel rewrites with receipts. End state: one program can
  cross the TSIR path on WSE-3 and WebGPU generic, with parity receipts for
  non-attention kernels.

- **Phase B — attention (4–6 months).** Its own phase, not an extension.
  Flash-style streaming attention, tiled prefill, paged KV residency class,
  sliding-window dependence analysis, streaming softmax reductions, and the
  cross-platform transcendental determinism (step 1 sollya polynomials) that
  attention's softmax needs at scale. Parity class includes flash semantics.

- **Phase C — remaining kernel families (2–4 months).** Rope, dequant,
  elementwise, linear attention, sample. These are mostly mechanical once
  Phase A and B have exercised the pipeline; their novelty is narrow and they
  inherit residency, collective, and parity machinery.

- **Phase D — autotuning (post-C).** Replaces the Phase A first-fit tile
  search with search guided by measured throughput. Phase A's planner is
  correctness-only by design; perf claims need Phase D.

Claims tightened from the previous draft:

- "3–6 months" reads 12–18 months. Named above.
- "zero local decisions" becomes "no kernel-family pattern-matching; conflict
  resolution enumerated and hashed". Named in step 7.
- "stable semanticDigest" becomes "stable under pinned frontendVersion".
  Named in step 3.
- "no CI" becomes "no PR-gating CI; nightly canary parity on a fixed kernel
  set". Named in step 8.
- "kernel-family hints bias heuristics" becomes "hints are tiebreakers only;
  never change feasibility or rejection". Named in step 4.

## Step 1: parity oracle before any compiler work

The first load-bearing surface is the scalar reference interpreter. It consumes
WGSL-derived TSIR, not backend code, and defines what counts as correct before
any emitter gets a vote. The interpreter executes with declared IEEE-754
semantics, left-fold reduction order unless a reduction explicitly permits a
declared tree, and fp32 accumulation for reductions unless the source overrides
it. The current `runtime/zig/src/tsir/reference_interpreter.zig` file states
this contract; it still returns `NotImplemented`.

**Determinism requirement, named:** the project requires cross-platform
bit-identity because Doppler WebGPU runs on heterogeneous browser GPUs. The
end-state interpreter uses sollya-bounded minimax polynomials for
transcendentals (exp, log, sin, cos, tan, tanh, rsqrt, recip) with declared
worst-case ULP bounds. Shipping sollya polynomials is a several-month
sub-project of its own and is therefore scheduled as Phase B work, not
Phase A.

**Phase A bootstrap:** Phase A ships with pinned-libc determinism — the caller
pins the glibc version used to compute reference results, and the nightly
canary (step 8) runs on that same pinned libc. Any kernel whose correctness
depends on a transcendental is declared `tolerance_bounded` with a named
metric and epsilon; no kernel silently uses libm-adjacent math under
`bit_exact_solo` or `algorithm_exact`.

**Phase B upgrade:** sollya polynomials land as part of Phase B when attention's
softmax needs cross-platform exp determinism at scale. Kernels that were
`tolerance_bounded` in Phase A for transcendental-only reasons can then be
re-declared `algorithm_exact` with the sollya tree shape recorded in the
`algorithm_exact` invariants (see step 6). Existing Phase A parity receipts
remain valid for their declared class; the upgrade is a new receipt, not a
retrofit of old ones.

Every later compiler step depends on this oracle existing as a real program,
not a comment. Without it, "faithful lowering" is undefined and backend drift
can only be measured relative to another backend. That is not good enough for
proof-bound runtime claims.

## Step 1.5: bootstrap kernel catalog before the full frontend

Before the full WGSL -> TSIR frontend is written, Doe should pin a deliberately
small bootstrap catalog of WGSL kernels and their expected TSIR shapes:

- one fused-GEMV variant
- one RMSNorm variant
- one gather variant

The point is not performance. The point is validating that the TSIR schema, the
parity oracle, and the target-descriptor shape can actually represent the first
three nontrivial kernel families the project intends to lower. This catches
category errors early, before the frontend locks in assumptions that force
schema churn later.

These bootstrap kernels should live as explicit test fixtures with hand-sketched
expected TSIR summaries so the first frontend work is judged against concrete
representability rather than prose alone.

## Step 2: target descriptors as data, not backend code

Target properties must be explicit descriptors consumed by planning passes, not
hidden emitter assumptions. The first descriptor should cover WSE-3 and expose
the fields the planner actually needs: per-PE working and persistent memory,
fabric colors, collective limits, lane/sub-tile width, native collective set,
supported numerical modes, dequant helpers, streaming primitives, and latency
or cost hints the planner may consult. A second descriptor should capture a
generic WebGPU target surface with subgroup bounds, workgroup memory, and
storage/buffer limits.

The point is not to abstract all hardware differences away. The point is to
make them explicit, versioned, hashable inputs to realization. New hardware
should add a new descriptor, not force hidden compiler rewrites.

Descriptor fields should be split into two classes:

- `descriptor.correctness`
  - correctness-affecting fields that participate in lowering identity
  - examples: supported collectives, lane width, supported dtypes, memory
    budgets, exactness-relevant collective properties
- `descriptor.planner`
  - planner-affecting fields that influence search quality but should not, by
    themselves, invalidate manifests
  - examples: latency hints, bandwidth estimates, cost priors, autotuning hints

Only correctness-affecting descriptor fields should flow into the realization
identity. Planner hints are inputs to search quality, not semantic identity.

## Step 3: TSIR schema with semantic and realization digests

TSIR needs two stable layers with two different digests.

`tsir.semantic` is the backend-independent meaning of the kernel:

- loop nests and iteration axes
- affine bounds where analyzable
- buffer bindings and logical shapes
- reduction regions and numerical contract
- collective nodes
- source hash back to WGSL IR
- family hints that bias heuristics but do not select emitters

`tsir.realization` is the backend/target-specific plan:

- tile factors
- residency choices
- PE-grid shape
- reduction tree shape
- collective mapping details
- target descriptor hash
- emitter parameters
- emitter digest

The in-tree scaffold already models this split. The real work is making the
canonical JSON and digests production-grade and then binding them into the
manifest/lowering receipts.

One caveat needs to be explicit: `semanticDigest` is not "stable forever." It
is stable under a pinned frontend version and semantics-preserving frontend
evolution. If loop recovery, subgroup canonicalization, or dependence analysis
changes semantic TSIR, then semantic identity changes and the manifest must pin
that through an explicit `frontendVersion` input. That turns frontend
improvements into declared migrations instead of silent semantic drift.

## Step 4: WGSL frontend to TSIR lowering

The current CSL route collapses too early from IR into classifier tags and
template parameters. The replacement path is WGSL IR to TSIR.

That means a real frontend pipeline:

- SSA-friendly control-flow normalization
- induction-variable recovery
- affine/dependence analysis where possible
- reduction-region identification
- buffer-binding shape and access summary extraction
- subgroup canonicalization into collective nodes

Classifier logic does not disappear entirely. It shrinks into a kernel-family
hint on the TSIR function so planning heuristics can bias search without
hard-selecting an emitter. Sources that cannot be represented faithfully must
reject with typed taxonomy reasons instead of having semantics dropped or
silently simplified.

The bound on hints should be strict: hints may act as tie-breakers between
already-feasible plans, but they must never change feasibility or rejection.
If a kernel does not fit without a hint, the hint is not allowed to "rescue"
it. That keeps TSIR planning honest and prevents hidden special-casing from
re-entering through heuristic backdoors.

## Step 5: residency and allocation planning

This is where the current non-GEMM failures actually get fixed. The issue is
not that WSE-3 is incompatible with these kernels. The issue is that current
emitters materialize buffers per PE that should instead be sliced, streamed, or
recomputed.

The residency pass consumes `tsir.semantic`, a target descriptor, and loader
capabilities. It computes liveness, interference, and fit. For each binding and
intermediate, it chooses one of a small declared set:

- `pe_replicated`
- `pe_sliced`
- `fabric_streamed`
- `host_copied`
- `recomputed`

Tile search should stay bounded and deterministic. It does not need a full
polyhedral framework. It does need explicit fit decisions and explicit failure
reasons. If no fitting plan exists, the compiler rejects with
`tsir_pe_budget_exhausted` and records the specific overflow source.

This first planner should be documented honestly as a correctness-first
planner. A bounded first-fit search over a small tile space is enough to prove
representability and fit, but it is not enough to promise good non-GEMM
throughput. Autotuning and broader cost search belong later, after the kernel
families are actually lowered through TSIR.

This pass also has an external dependency boundary: some streaming decisions are
not only compiler questions. They depend on RDRR packaging. A tensor cannot be
planned as `fabric_streamed` if the bundle packaging does not expose the needed
Merkle or shard granularity. That means some kernel families will require both:

- TSIR/compiler work in Doe
- packaging policy work in Doppler/RDRR

Examples of that coupling:

| Kernel family | Packaging dependency |
| --- | --- |
| fused GEMV with streamed weights | tensor isolation and sufficiently fine Merkle/block granularity |
| gather with streamed embedding | embedding tensor isolated from unrelated co-packed tensors |
| attention with paged KV | explicit KV packaging contract compatible with paged or streamed residency |

## Step 6: collective synthesis and numerical contract

Subgroup and barrier behavior needs a first-class lowering pass rather than
template-local interpretation. `workgroupBarrier` becomes an explicit sync
point. Subgroup reductions and scans become explicit collectives over a declared
lane or sub-tile mapping. Broadcasts, ballots, shuffles, and reductions each
need declared semantics, not inferred "best effort" behavior.

This is also where numerical exactness gets pinned:

- accumulation dtype
- reduction order or declared tree
- reduction-tree shape
- NaN and Inf propagation
- exactness class

If a collective cannot be represented on a target without violating the
declared contract, the pass rejects it. That keeps fail-closed behavior intact
while making subgroup-to-fabric lowering a compiler responsibility instead of an
unsupported gray area.

For `algorithm_exact`, the declared invariants must include more than "same
operation family." They need to include the properties that actually affect
floating-point bits:

- reduction order
- tree shape
- accumulation dtype
- allowed associativity grouping

Two lowerings can share one semantic TSIR and still produce different bits if
their realization chooses different reduction trees. That is valid only when
the exactness contract declares it.

## Step 7: one mechanical TSIR-to-CSL emitter

Once planning is explicit, the emitter should stop making decisions. It should
be mechanical.

The emitter consumes `tsir.realization` and a target descriptor and emits:

- declarations based on residency class
- loop structure from tile factors
- PE program scaffolding from grid shape
- collectives from collective nodes
- parameter blocks from resolved emitter parameters

The key constraint is not "zero local decisions" in the absolute sense. The
real constraint is:

- no kernel-family pattern matching in the emitter
- no hidden semantic rescue logic in the emitter
- any conflict-resolution behavior that remains local to emission must be named,
  enumerable, and hashed into emission identity

That leaves room for emitter-local conflict handling where the hardware requires
it, such as DSD layout details, fabric-color conflicts, or bank-conflict
workarounds, without turning the emitter back into a semantic planner. If the
emitter has to decide whether something is replicated, sliced, streamed, or
reduced, the earlier passes have already failed architecturally.

The current per-kernel CSL emitters can remain as migration shims while kernels
move over one family at a time, but the end state is a shared lowering
pipeline feeding a small number of mechanical backend emitters.

## Step 8: manual parity CLI as the gate

Parity is a manual CLI gate, not a PR-gating CI policy. The CLI runs the reference
interpreter first and then compares each backend result against it under a
declared exactness class. The output is a parity receipt with hashes, exactness
class, pass/fail status, and explicit rejection reasons.

The important property is asymmetry: a backend is never validated by comparing
it only to a different backend. Both compare to the oracle. If the oracle does
not exist for a kernel family yet, that family is not eligible for proof-grade
promotion.

This gate is what keeps compiler migration honest. Every rewrite should land
with a parity receipt or with an explicit rejection, not with a vague "looks
reasonable on the simulator" claim.

The reason for avoiding PR-gating CI here is practical rather than ideological:

- full reference interpretation is expensive on large kernels
- simfabric-backed runs require provisioned infrastructure
- most repo changes do not touch lowering
- existing promoted non-TSIR artifacts already have their own parity gates;
  TSIR convert-time parity is introduced by this plan, not assumed as current
  state

That still leaves room for lightweight automation. A fixed nightly canary set
is compatible with this plan and should be preferred over broad PR gating:

- one fused-GEMV kernel
- one RMSNorm kernel
- one gather kernel
- later, one attention-decode kernel

That gives cheap regression coverage without turning every routine change into a
full lowering/parity farm run.

## Step 9: rewrite kernel families in impact order

Migration should follow throughput and architectural leverage, not only surface
simplicity.

The first targets should be the families that currently force the biggest
planning and residency decisions:

- fused GEMV
- normalization
- gather and embedding
- attention decode
- attention prefill/tiled

Elementwise, rope, dequant, and sampling families become easier once residency,
collectives, and parity machinery are already real. Each migrated family should
cross the full bar in one move: TSIR lowering, mechanical emission, parity
receipt, then deletion of the old path for that family. Half-migrated kernel
families create audit holes and should be avoided.

Attention needs to be treated as its own phase, not as a routine extension of
the first non-GEMM migration wave. Streaming attention, paged KV, sliding
window policies, and streaming softmax reductions are distinct compiler
problems. The non-attention phase proves the TSIR pipeline on GEMV, RMSNorm,
and gather. Attention then becomes the next architecture phase built on top of
that proven pipeline rather than a hidden assumption inside the first rewrite
sequence.

## Step 10: manifest-bound lowering receipts

Lowerings need to be part of the portable-program artifact boundary. The
manifest should bind:

- kernel reference
- backend
- target descriptor hash
- frontend version identity
- TSIR semantic digest
- TSIR realization digest
- emitter digest
- compiler version identity
- exactness class
- rejection reasons when a backend cannot honor the kernel

That keeps compiler policy from becoming a hidden runtime behavior. Replay
should be able to say not only "these weights and this graph ran" but also
"this exact lowering of this exact kernel ran." Compiler upgrades then become
explicit migrations and refreshed lowerings, not silent semantic drift.

## Step 11: AOT lowering at convert time

Lowering should run ahead of time during conversion or refresh, not at load.
The bundle should ship with emitted backend artifacts and the receipts that
justify them. A backend that cannot honor a kernel should record the rejection
reason in the manifest-side lowering metadata, so runtime refusal is immediate
and explicit.

This keeps the runtime boundary small. The runtime becomes a loader and
executor of predeclared lowerings rather than a place where planning and policy
quietly happen on first token. It also keeps proof and replay discipline
aligned with the existing Doppler manifest-first model.

Per-backend AOT emission does increase convert cost, especially for large model
families and multiple backend variants. That should be handled explicitly with
per-kernel lowering cache keys derived from correctness-relevant inputs such as:

- WGSL/kernel identity
- target correctness descriptor
- frontend version
- compiler version
- emitter version

That keeps repeated variants from paying the full lowering cost when the kernel
and lowering identity have not changed.

## Step 12: rollout and steady state

The rollout order should be:

1. parity oracle (Phase A bootstrap: pinned-libc determinism; sollya in Phase B)
2. bootstrap kernel catalog (step 1.5) — one fused-GEMV, one RMSNorm, one gather
3. target descriptors (correctness + planner field split)
4. TSIR schema hardening and canonical digests
5. WGSL frontend lowering
6. residency/allocation (correctness-only planner; autotuning is Phase D)
7. collective synthesis
8. mechanical emitter (no kernel-family pattern-matching; conflict rules
   enumerable and hashed)
9. manual parity CLI (plus nightly canary on the fixed bootstrap set)
10. kernel family rewrites (Phase A: GEMV, RMSNorm, gather; Phase B: attention;
    Phase C: remaining families)
11. manifest binding (includes frontendVersion, descriptor correctness hash)
12. convert-time lowering (per-kernel lowering cache keyed on correctness
    inputs)

### Loop 2 subloops

The Loop 2 subloops below are scheduling labels for the rollout order above.
They do not change the ordering, and they do not permit an iteration to skip
the lowest-numbered unfinished rollout item. Each Loop 2 iteration still lands
one committable compiler-only increment, with tests, schema or contract updates
where required, and a dated status entry.

- **Loop 2A: oracle, catalog, and descriptors.** Owns rollout items 1-3:
  parity oracle, bootstrap kernel catalog, and `webgpu-generic` / `wse3`
  target descriptors.
- **Loop 2B: TSIR contract hardening.** Owns rollout item 4: schema
  hardening, canonical JSON, semantic digest, realization digest, exactness
  vocabulary, and rejection taxonomy.
- **Loop 2C: WGSL frontend lowering.** Owns rollout item 5: WGSL IR to TSIR
  semantic lowering, including binding/shape extraction, axis recovery,
  reduction detection, family hints, and typed rejection for unanalyzable
  kernels.
- **Loop 2D: residency and allocation planning.** Owns rollout item 6:
  correctness-first residency, allocation, liveness, and bounded tile search.
- **Loop 2E: collective synthesis and numerical contract.** Owns rollout item
  7: collective nodes, reduction tree shape, accumulation dtype, and exactness
  invariants.
- **Loop 2F: mechanical backend emission.** Owns rollout item 8: backend
  emission from `tsir.realization`, with no hidden kernel-family semantic
  rescue logic.
- **Loop 2G: parity CLI plumbing.** Owns rollout item 9 as infrastructure
  only. Real parity closure remains Loop 3; legacy classifier receipts do not
  satisfy Loop 3.
- **Loop 2H: Phase A kernel rewrites.** Owns rollout item 10 for fused GEMV,
  RMSNorm, and gather, with old paths deleted or fenced as legacy-only.
- **Loop 2I: manifest metadata and AOT plumbing.** Owns rollout items 11-12
  as Doe-side infrastructure: lowering metadata shape, rejection
  serialization, cache keys, and convert-time lowering. Production Doppler
  manifest binding remains Loop 3.
- **Loop 2J: steady-state cleanup.** Deletes migrated per-kernel CSL emitters
  and reduces classifier logic to kernel-family hint extraction for migrated
  families.

Loop 2 has no production Doppler manifest mutation and no live Cerebras SDK
dependency in its inner loop. It may define `wse3` target descriptors, but
simulator execution belongs to Loop 3 or evidence work.

Steady state is simple:

- a new kernel family means WGSL plus parity-backed lowering support
- a new backend means a descriptor and emitter support, not a new compiler
  architecture
- a compiler change means a new lowering digest and refreshed receipts

That is the difference between "one program, many faithful realizations" and
"one source language with many backend-specific template piles."

## Relationship to current Doe docs

This plan extends, but does not replace, the current architecture docs:

- `docs/shader-compiler-architecture.md`
  - current WGSL compiler pipeline
- `docs/csl-architecture.md`
  - current CSL classifier/HostPlan/emitter path
- `docs/doppler-ingest.md`
  - Doppler-owned program boundary and Doe-owned lowering boundary
- [`docs/loop-protocol.md`](loop-protocol.md)
  - Loop 2 / Loop 3 iteration discipline that drives how this plan
    lands incrementally
- [`docs/status/tsir.md`](status/tsir.md)
  - live status for this plan's implementation — what's landed per
    step and what the remaining proof-1 wedges are

The operative current state remains:

- WGSL -> Doe IR -> backend emission for Metal/Vulkan/D3D12
- WGSL/Doppler capture -> classifier -> HostPlan -> CSL emitter for Cerebras

The target state defined here is:

- WGSL IR -> TSIR semantic -> TSIR realization -> backend emitters
- reference-interpreter parity against the same TSIR contract

Until that target path is wired end to end, current classifier/template
limitations remain real blockers rather than documentation-only issues.
