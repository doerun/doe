# Doe Zig style guide

This guide is the style contract for owned code under `runtime/zig/`. Use the
Zig version pinned in [`../../config/toolchains.json`](../../config/toolchains.json).
Component intent comes from the applicable `CATSCAN.md` chain; source ownership
and size policy come from [`source-layout.json`](source-layout.json).

Readable code makes its inputs, decisions, ownership, and failure paths visible.
Shorter code is useful when it removes repetition or indirection; line count
alone does not establish quality.

## Core principles

- Prefer explicit typed contracts over inferred behavior.
- Keep runtime decisions deterministic and traceable.
- Fail fast on invalid/unsupported inputs with actionable errors.
- Keep hot-path execution allocation-light after initialization.
- Give every semantic fact one authoritative owner and every subsystem one
  narrow public surface.
- Eliminate duplicate registries, policy maps, profile unions, errors, artifact
  fields, and conversion taxonomies before optimizing file count.

## Invariant registry

These identifiers are normative and should be named by reviews, regression
tests, and receipts when a change touches the corresponding boundary.

| ID | Invariant | Enforcement surface |
| --- | --- | --- |
| `INV-OWNER-001` | Shared behavior lives with the narrowest subsystem that owns its semantics; dependency direction remains one-way. | `tools/check_source_layout.py`, `tools/check_core_import_fence.py`, import tests |
| `INV-PLAN-002` | Command-oriented immediate, recorded, replayed, direct, and indirect execution share the prepared-operation contract; ordinary WebGPU and package programs share applicable semantics without a universal interpreter. | affected executor parity tests, trace/replay gates |
| `INV-RESOURCE-003` | Every resource has one explicit owner and every ownership transition has one cleanup path. | allocator-backed tests, lifecycle and failure-path tests |
| `INV-RECEIPT-004` | Structural refactors preserve the canonical behavior receipt and first failure boundary. | trace determinism, replay, semantic digest, and workload-oracle tests |
| `INV-FACADE-005` | Module roots and compatibility facades aggregate, normalize, delegate, or translate errors; they do not own independent domain behavior. | `source-layout.json`, `tools/check_source_layout.py`, exercised facade tests |
| `INV-REGISTRY-006` | Each command, capability, error class, artifact identity, and timing field has one authoritative registry or contract. | compile-time coverage, schema gates, duplicate-declaration inventory |
| `INV-CONTEXT-007` | Promoted execution boundaries use explicit context, request, and report types rather than `anytype` dependency hiding. | affected-path compile and parity tests |
| `INV-ARCH-008` | Every production module has one declared owner, layer, and special role, with zero forbidden dependency edges or cycles. | versioned `source-layout.json`, architecture graph gate |
| `INV-PROVIDER-009` | Provider selection has one ordinary runtime construction root; FFI provider integrations are explicitly enumerated, and provider configuration/state is instance-owned. | `tools/check_core_import_fence.py`, provider construction and concurrent-session tests |
| `INV-BORROW-010` | A borrowed prepared operation is valid only for synchronous execution/callback scope; queued or retained work owns a deep immutable snapshot. | `OwnedPreparedOperation` tests, observer and executor lifetime tests |
| `INV-PORT-011` | Capability ports and provider drivers expose domain-specific operations; no broad command escape hatch survives in the adapter contract. | `tools/check_core_import_fence.py`, provider adapter compilation tests |
| `INV-LIVE-012` | Re-export reachability is not evidence of use. Incubation modules require a real consumer or are removed from production roots. | architecture reachability reports, consumer search, affected package tests |

No prose-only waiver satisfies an invariant. If the named global gate cannot
observe a changed behavior, the affected subsystem must add a focused
characterization or parity test in the same change.

## Build decisions and observed costs

- Build decisions produce immutable typed values from versioned policy. Reject
  unsupported versions, missing fields, and incompatible selections before
  compiling consumers. Device facts resolve once per device; changing invocation
  inputs retain explicit validation. Algorithm constants stay with the algorithm.
- Derive diagnostic identity and coverage metadata from the owning contract.
  Compile-time completeness is structural evidence; validators, executors, and
  resource lifetimes still require independent behavioral tests.
- Declare allocation sites in steady execution and distinguish reserved capacity
  from allocator calls. Every cache specifies identity, owner, capacity,
  invalidation, and full-capacity behavior. Owning structs cannot be freely copied;
  Zig supplies no general ownership checker.
- Keep pointers, casts, native handles, and foreign callbacks at narrow adapters.
  Required metadata and allocation failures remain errors. API admission and
  checked arithmetic must work in every supported optimization mode.
- Instrument the real execution path. Optional observation has bounded storage,
  explicit unavailable values, and overflow reporting. Export outside the measured
  operation and confirm benefit in the ordinary configuration. Specialization,
  forced inlining, and vector variants require application, binary-size, and build
  evidence before adoption.

- Telemetry snapshots read existing state. File output and configuration reads
  belong to an explicit fallible collection boundary outside the measured
  operation. Deferred capture owns its inputs until publication or cleanup.
- Content hashes require actual artifact bytes. Derived identifiers, observed
  source hashes, and unobserved compiler stages must remain distinguishable in
  versioned evidence; a configured tool is not evidence that it executed.
- Elapsed-time measurements use a suitable elapsed clock rather than calendar
  time. Preserve unavailable timing explicitly; legacy zero sentinels must never
  become a duration measured from the clock's epoch.
- Filesystem lookup may continue on absence. Permission, allocation, and other
  access failures retain their causes instead of selecting another candidate.

## Repository conventions

- Shared command/profile contracts belong to `contracts/`; parsing belongs to
  the subsystem that owns the input language.
- Quirk selection belongs to `quirk/`; execution orchestration, trace, and
  replay belong to `runtime/`; WebGPU ABI contracts belong to `core/abi/`.
- The current ownership directories and compatibility facades are generated in
  `src/README.md` from `source-layout.json`. Do not duplicate that changing
  module inventory in this guide.

`source-layout.json` is the architecture manifest, not merely a directory
inventory. Its architecture-aware version must own layers, import permissions,
special roles, compatibility-facade lifecycle, generated sources, and any
cohesive-module size justification. Do not create a second policy file for
those facts.

## Architectural decoupling

- Treat directories as subsystem boundaries, not just file buckets.
- Prefer dependency direction: contracts -> helpers -> subsystem
  implementation -> facade/orchestration.
- `src/mod.zig` is the only production Zig file allowed directly under `src/`.
  `source-layout.json` assigns every implementation to an ownership directory,
  and `tools/check_source_layout.py` enforces that boundary.
- `core` must remain one-way with respect to `full`. If shared behavior is
  needed, extract it into `core`, `backend/common`, or a new contract module
  rather than importing upward.
- Backend-specific code must not import sibling backends directly. Cross-backend
  sharing belongs in `backend/common`.
- `composition/backend_factory.zig` is the ordinary runtime provider
  construction root. Drop-in FFI modules that must translate provider-native
  objects are an explicit, source-enforced integration-root set; adding one is
  an architecture change, not an automatic privilege of living in `backend/`.
- Provider configuration is passed at construction. Mutable cache paths,
  enablement flags, handles, telemetry, and device identity belong to the
  selected provider instance, never a process-global configuration shim.
- Non-backend implementation files must reach backend-specific behavior through
  backend-owned seam modules such as `backend/dropin_*.zig`, not by importing
  `backend/metal/*`, `backend/vulkan/*`, or `backend/d3d12/*` directly. The
  import fence enforces this boundary.
- Keep `compiler/wgsl` self-contained except for explicit shared
  proof/contracts.
- Keep `quirk` limited to quirk logic plus shared contracts/proof inputs; it
  should not depend on backend execution modules.
- Prefer narrow context/state types over monolithic runtime structs when
  crossing subsystem boundaries.
- Avoid introducing new import cycles. If an import would create one, extract a
  smaller contract/state module and depend on that instead.
- When splitting a high-fan-in file, move definitions first and retain a
  compatibility facade only when an exercised compatibility contract requires
  it. Every retained facade must be declared in `source-layout.json`.
- Shared types should live with the subsystem that owns their semantics, not in
  whichever orchestration file currently imports them most often.
- New implementation code must not import `compat/`; the compatibility surface
  is for compatibility tests and declared consumers only.
- Native implementation code should import the narrowest support, contract,
  value-type, or ABI shard that owns the required symbols. Broad aggregation
  modules are compatibility/facade surfaces, not default implementation
  dependencies.

## Module roots and facades

- Module roots may re-export contracts, normalize public inputs, delegate to
  feature owners, and translate errors at the public boundary.
- A package-root re-export does not prove a module has a production consumer.
  Modules used only by their own characterization tests remain incubation
  scaffolding and must not be described as a completed production route.
- Module roots must not own mutable diagnostic state, semantic transforms,
  backend realization, resource state machines, or substantive feature tests.
- Compatibility facades may contain aliases and delegation required by a
  declared consumer. They must not introduce independent policy or execution
  semantics.
- Every compatibility facade must be declared in `source-layout.json` and
  name its external consumer, reason, owner, consumer-facing test, and removal
  condition.
- When moving implementation out of a root or facade, definitions move first;
  the facade remains only until its declared consumers migrate.

## File size

The active `architecture.linePolicy` in `source-layout.json` sets the advisory
review threshold, justification threshold, and hard maximum for handwritten
production source under `src/`. Generated specification or table files require
a declared, reproducible generation contract. Build tooling and test files are
outside that production line gate; they still require cohesive responsibilities.

The thresholds are not targets. A file that owns multiple state machines,
artifact kinds, input languages, or execution phases must split even below the
advisory signal. Split by cohesive functionality, keep related code together,
and do not create a module whose only identity is satisfying a line limit.

File-count reduction and size distribution are campaign observations. Report
production, generated, test, and build/tooling code separately, and exclude
retained benchmark source snapshots from active-tree totals.

## Semantic inventory decisions

Architecture analysis assigns every production file one decision:

- **Keep**: executable or package root, ABI/FFI boundary, generated
  specification, stable shared contract, or independently meaningful
  algorithm.
- **Merge**: one production importer, no independent contract or test identity,
  same owner as its consumer, and only forwarding declarations, private
  constants, or a tiny private record.
- **Elevate**: a semantic fact used across layers currently lives inside one
  implementation; move it to the neutral owner.
- **Recompose**: one file owns multiple state machines, policies, contexts,
  artifact kinds, or pipeline phases; reorganize by those responsibilities.
- **Delete**: unreachable, superseded, duplicated, or an unconsumed
  compatibility facade.

Physical size, fan-in, fan-out, and co-change frequency are diagnostic evidence
for these decisions. None decides the outcome alone.

## Canonical contract families

Resolve duplicate sources of truth in this order:

1. command kinds, payloads, scope, parser names, trace names, and operation accounting;
2. capabilities and feature identities;
3. error and unsupported classifications;
4. artifact identity and hash fields;
5. timing and dispatch-result semantics;
6. texture-format and binding mappings;
7. backend selection and fallback policy.

Each family has one neutral typed owner. Backend-specific conversion and native
control flow remain local to the backend. Prefer an explicit tagged union plus
complete metadata table before considering type generation.

Command accounting rules are required metadata, not catch-all defaults. Payload
counts must name an existing `u32` field; dynamic capability policies must bind
the command they inspect. Keep independent tests for count normalization and
required capabilities because structural completeness cannot establish either
rule's semantic correctness.

## Formatting

Run these commands from `runtime/zig/`:

```bash
zig build fmt-check
zig build fmt
```

`fmt-check` checks without writing; `fmt` applies Zig's formatter. Both cover the
runtime tree, including tests, generated suite roots, and build/tooling code,
excluding `vendor/`, `.zig-cache/`, and `zig-out/`. Format generated source through
its generator when a generator check would otherwise reject the result.

Formatting is blocking in the default install step and every canonical test
suite. The WGSL CI workflow also runs it explicitly before compilation. A named
artifact-only build step is not a substitute for these checks.

## Imports

- `std` and `builtin` first.
- Then local modules, with shared contracts before domain-specific imports.
- Group domain imports by subsystem (e.g. backend modules together).
- Prefer small feature-scoped modules over catch-all utility files.
- Prefer importing feature-local contract/state modules over whole runtime
  orchestrators.
- Before importing a broad hub such as a facade or backend runtime, check
  whether a narrower contract module is the real dependency.

## Naming

- Types, including type-returning factory functions: `PascalCase`.
- Ordinary functions and methods: `camelCase`.
- Local values, parameters, fields, enum tags, and module import bindings:
  `snake_case`. A local `const` is still a local value.
- Named domain, ABI, and policy constants: `UPPER_SNAKE_CASE`.
- File names: `snake_case.zig`.
- Doe runtime files stay `snake_case.zig` even when a file is centered on one
  primary type; do not introduce `PascalCase.zig` files in `runtime/zig/src/`.

Preserve spellings imposed by foreign symbols, generated bindings, serialized
schemas, and external interfaces. Those contracts take precedence over a local
naming preference. Rename private implementation symbols with their consumers
when touching the responsibility they belong to; do not silently rename a
public declaration, error, or serialized field for style. Existing mixed naming
is review debt, not evidence that an automated naming gate exists.

Choose names for the represented fact: `retained_bytes` distinguishes capacity
from a live allocation count. Avoid `data`, `state`, and `result` when several
different concepts share the scope. Use short names where their meaning is
unambiguous, such as a loop index.

## Constants and magic numbers

- Inline `0`, `1`, simple index arithmetic, and language-level sentinels when
  they are the clearest expression of local mechanics.
- Name domain, ABI, policy, threshold, size, retry, and timing values.
- Use named `UPPER_SNAKE_CASE` comptime constants or config values.
- Place module constants after imports; keep type-owned constants with the type.
- Domain-shared constants belong in the narrow contract module that owns their
  semantics, such as `model_texture_value_types.zig`,
  `model_binding_value_types.zig`, `wgpu_core_base_types.zig`, or
  `wgpu_texture_base_types.zig`.
- Module-specific constants stay in the module that uses them.
- If a value appears in more than one file, it must have a single source of truth.

## Canonical serialization

- Each schema-owned artifact kind owns its canonical field walk and validation.
- Shared byte, number, string, and key emission belongs in one narrow canonical
  writer module.
- Do not combine unrelated artifact walkers in a catch-all digest module only
  because they share SHA-256 or JSON emission.
- Canonicalization refactors must preserve exact bytes, semantic digests, error
  classification, and allocation cleanup through characterization tests.

## Control flow

- Prefer `switch` on enums over long `if` ladders.
- Exhaust meaningful alternatives. Use `else` only for a deliberate shared
  policy; do not let a new enum tag silently acquire success behavior.
- Use early returns for invalid states.
- Keep fallback behavior explicit and auditable.
- Do not introduce silent capability switching.
- Prefer immutable locals and the smallest useful scope. Represent mutually
  exclusive states with a tagged union when independent flags permit invalid
  combinations.
- Extract a helper when it names a responsibility or removes duplicated
  semantics. A forwarding wrapper, generic callback, or new module must earn
  its indirection through an actual contract or consumer.

## Prepared operation parity

These rules govern the command-oriented executor. Ordinary native WebGPU and
package compute programs retain their own submission interfaces while consuming
the same applicable shader, resource, ownership, and error contracts.

- Resolve policy, bindings, work shape, entry point, specialization, and
  fallback eligibility before selecting an executor.
- Immediate, recorded, replayed, direct, indirect, and backend-specific paths
  consume the same read-only prepared-operation contract.
- `PreparedOperation` is a borrowed view for one synchronous execution and its
  observer callbacks. Anything that queues, retries asynchronously, records
  payloads for later replay, or otherwise retains the operation must own an
  `OwnedPreparedOperation` snapshot and release it explicitly.
- Snapshot cloning must reject pointer forms without a declared ownership rule,
  preserve slice alignment and sentinels, and release partial allocations on
  failure. Opaque handles and callbacks remain identities whose external owners
  must outlive their use; copying an address does not retain the resource.
- Canonical command-to-operation conversion is owned by `app/prepare.zig`.
  Inbound adapters may not call the lower-level conversion directly.
- Executor adapters may differ only in submission, resource retention,
  completion, readback scheduling, and evidence capture.
- An executor must not reinterpret bindings, invent defaults, change dispatch
  shape, or select a different shader or pipeline.
- Every executor split or merge requires a parity test that changes one plan
  field and proves all applicable adapters observe the same change.

Promoted execution interfaces use named types such as `ComputeContext`,
`DispatchRequest`, and `DispatchReport`. `anytype` remains acceptable for
private, local, compile-time-generic helpers; it is forbidden where it hides
the dependencies or output contract of a subsystem or promoted execution path.

## Errors and diagnostics

- Compiler lowering must emit either a valid typed semantic value or a typed
  rejection with source/node location and reason. Placeholder scalar types,
  shapes, or handles are forbidden in promotable semantic artifacts.
- Artifacts carrying semantic rejections are diagnostic-only and cannot enter
  code generation, parity promotion, or claim-bearing workloads.
- Return explicit error unions (`!T`) for recoverable failures.
- Keep unsupported behavior explicit (`unsupported` taxonomy), never silent no-op.
- Include actionable context: what was expected, what was received.
- Route runtime observability through pipeline/trace/trace-meta contracts.
- No ad-hoc `std.debug.print` in runtime paths; use structured trace output.
- Investigation-only debug output must be removed before committing runtime
  code; retained diagnostics use the owned trace contract.
- When a parameter is required by an interface or callback but intentionally
  unused, suppress it explicitly with `_ = param;` rather than relying on broad
  placeholder naming.

## Comments

- Comments explain why, not what.
- Do not add comments that restate the code.
- Use `///` to explain public intent, ownership, lifetimes, and failure conditions
  that a caller cannot infer from the signature. Do not repeat the identifier.
- Inline comments are for preconditions, control-flow rationale, or non-obvious constraints.
- Do not add TODO/FIXME inline; track follow-ups in the status log (`docs/status.md`, with dated entries in the current `docs/status/*.md` shard).

## Memory

- Functions that allocate must take an explicit allocator parameter unless the
  allocator is already owned by the receiving struct/context.
- Use explicit allocator ownership.
- Structs that own heap-backed state should store the allocator needed to
  release that state and provide an explicit `deinit` path.
- Scope temporary allocations with `defer` cleanup.
- Use `errdefer` for partial initialization rollback and multi-step allocation
  or acquisition paths that can fail after earlier resources are acquired.
- Place `defer`/`errdefer` immediately after the acquisition they clean up when
  the pairing is not obvious from a tighter local scope.
- Keep long-lived caches explicit in owning structs.
- Do not use process-global mutable state to transmit per-session provider
  configuration or telemetry. A global registry is acceptable only when the
  process itself is the declared resource owner and concurrency semantics are
  explicit and tested.
- Prefer arena allocators only for clearly bounded lifetimes such as one parse,
  one request, or one artifact build; do not use arenas to hide long-lived
  ownership.
- Resource contracts should make ownership state explicit where a value crosses
  a subsystem boundary: `borrowed`, `scope_owned`, `submit_owned`,
  `transferred`, or `retained`.
- Ownership transitions belong to the resource owner, not to convenience
  callers. Each transition must have one success cleanup path and one tested
  failure cleanup path.
- Submission retains resources until established terminal completion. Timeout
  or unknown completion cannot authorize reuse or destruction. Terminal failure
  allows retirement but must remain an error to consumers.

## FFI and C interop

- Define C function pointer types as `pub const Fn<Name> = *const fn (...) callconv(.c) <ReturnType>`.
- Collect function pointers into a `Procs` struct in `wgpu_types.zig`.
- Required procs are non-optional fields. Optional/conditional procs use `?` wrapper.
- Load required procs with `loadProc()` (error on missing symbol). Load optional procs with `loadOptionalProc()` (returns null on missing symbol).
- Check optional proc availability before call:
  `if (procs.someFn) |proc| proc(...) else return error.Unsupported`.
- C callbacks use `callconv(.c)` and cast `?*anyopaque` userdata to known state
  structs via `@ptrCast(@alignCast(...))` only under the adapter's alignment,
  nullability, and lifetime contract. Completion status must survive delivery;
  setting a done flag alone does not establish success.
- Suppress unused callback parameters with `_ = param;`.
- Keep `@cImport` isolated to support or backend-boundary modules when
  unavoidable; do not spread ad-hoc C imports through general runtime logic
  when an existing typed seam or ABI module already owns that contract.

## Determinism and trace

- Identical inputs/config must produce stable decision and trace sequences.
- Preserve hash-chain invariants in trace rows/meta.
- Include enough metadata to reproduce selection and execution outcomes.

## Structural refactor receipts

Before moving runtime or compiler behavior, capture the observable contract for
the affected path. The retained evidence must cover every applicable field:

- resolved policy and runtime identity;
- semantic or prepared-operation plan;
- operation and submission order;
- shader, pipeline, and specialization identity;
- resource acquisition, transfer, retention, and release events;
- output identity or oracle verdict;
- diagnostic classification and first failure boundary.

After the move, compare the receipt, semantic digest, trace chain, output
oracle, and performance class. Remove a compatibility facade only after its
declared consumers use the new owner and the parity evidence remains green.

Before a recomposition campaign begins, bind the baseline to one commit and
retain:

- public Zig modules and declarations reachable through `@import("doe")`;
- exported C ABI symbols;
- command parsing and normalized command representations;
- compiler semantic and target-output digests;
- traces, terminal hashes, replay results, and receipt identities;
- backend capabilities and unsupported classifications;
- representative backend outputs;
- clean and incremental compilation measurements, promoted hot-path medians,
  and binary sizes.

Every structural change is classified as exact equivalence, an explicitly
approved contract change, or failure. Public API changes require a manifest
diff; no rename, move, or split may silently change an error name, import path,
shader output, fallback decision, synchronization behavior, or receipt field.

## Testing

- Use inline `test` blocks for private, pure, module-local behavior.
- Use dedicated external tests for integration, ABI, backend execution, golden
  artifacts, cross-module characterization, and cross-backend parity.
- Shared fixtures belong in one domain-local fixture module when multiple tests
  genuinely share setup.
- Generate suite imports from the owned test inventory instead of maintaining
  parallel manual aggregator lists.
- Test names are descriptive behavior strings: `test "vendor comparison ignores case"`.
- Use `std.testing.expect` and `std.testing.expectEqual` for assertions.
- Prefer `std.testing.allocator` for tests that exercise allocation-owning code
  unless the allocator choice itself is part of the behavior under test.
- Run `zig build test` for affected runtime modules.
- Verify replay/trace gate compatibility for runtime-visible changes.
- For WebGPU API-surface changes, update config coverage + benchmark contracts in the same change.

## Consistency checks and review

| Concern | Enforced mechanically | Still requires review or behavioral evidence |
| --- | --- | --- |
| Formatting | `zig build fmt-check` | Clear names and useful documentation |
| Ownership boundaries | `zig build import-fence source-layout` | Correct semantic owner and a necessary abstraction |
| Production file size | `zig build line-limits` | Cohesion, even below the configured thresholds |
| Generated contracts and suites | `zig build webgpu-abi test-inventory` | Independent oracle and meaningful failure coverage |
| Types and command coverage | Compilation of the affected consumers | Correct validation, execution, and complete exercised paths |
| Resource lifetime and allocation | Focused lifetime and allocation-failure tests | Complete ownership reasoning across asynchronous and foreign calls |

Record systematic coverage in the [hierarchical review ledger](reviews/README.md).
File, directory, internal relationships, cross-directory relationships, and
whole-runtime reviews are distinct. A partial cleanup does not establish that
the entire file has been reviewed. Append new findings and evidence; let the
generated queue determine whether earlier reviews remain current.

For each cleanup, work through one named responsibility:

1. Read its charter, consumers, and existing tests. Use the generated
   `reports/architecture/` inventory to investigate duplicate declarations,
   dependency edges, and reachability; inspect the code before accepting a
   suggested merge or deletion.
2. Name the concrete ambiguity or duplication being removed. Define what must
   remain identical, including public names, errors, serialized bytes, and
   resource lifetime where applicable.
3. Make the smallest coherent change, migrate its consumers, and remove the
   obsolete path. Prefer an existing typed contract or standard-library
   operation over another registry, wrapper, or generic utility.
4. Format, run the relevant structural gates and behavioral tests, and retain
   the applicable equivalence receipt. Style-only edits do not need tests that
   merely repeat the implementation. New enforcement must demonstrate that it
   rejects the condition it claims to detect.
5. Record remaining debt with the semantic owner and next concrete target in
   the live status shard. Update this guide only when the rule generalizes;
   keep policy values and module inventories with their existing owners.

Measure execution changes with the frozen application procedure. A cleaner
diff, fewer allocations, or a successful compile is not performance evidence.
