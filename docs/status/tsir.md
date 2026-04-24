# Doe status: TSIR

This is a live topical status shard for the Tiled Spatial IR (TSIR) work
defined in [`docs/tsir-lowering-plan.md`](../tsir-lowering-plan.md) and
sequenced by [`docs/loop-protocol.md`](../loop-protocol.md).

- Add new TSIR entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under [`archive/`](archive/).
- Parity receipts themselves land under `reports/parity/` and are bound
  into Doppler manifests at `integrityExtensions.lowerings[]`; this shard
  is narrative status, not the receipt surface.

This shard exists because `compiler-and-webgpu.md` exceeded its 1200-line
cap once the TSIR Phase A wedges started landing. 2026-04-24 TSIR entries
live here; older TSIR history (2026-04-23 TSIR Step 4 increments) was
moved to [`archive/2026-04.md`](archive/2026-04.md) in a subsequent
tick. New TSIR entries go here going forward.

## Phase A status at a glance

Compiler surface by plan step (see
[`docs/tsir-lowering-plan.md`](../tsir-lowering-plan.md) for the full
plan). This is a shape summary — file paths name what exists, not
how much. For iteration cadence see
[`docs/loop-protocol.md`](../loop-protocol.md).

| Step | Artifact | State |
| --- | --- | --- |
| Step 1 oracle | `runtime/zig/src/tsir/reference_interpreter.zig` | Recognizes fused_gemv / gather / rms_norm across {f32, f16, bf16} with strict_ordered + associative_allowed reductions + literal/uniform epsilon. Unsupported shapes fail closed with `NotImplemented`. |
| Step 1.5 bootstrap | `runtime/zig/tests/tsir/bootstrap/` | Pinned WGSL + hand-sketched `.tsir-semantic.json` + per-target realization sketches for fused_gemv, rms_norm, gather. |
| Step 2 descriptors | `runtime/zig/src/targets/{webgpu_generic,wse3,mod}.zig` | Correctness/planner field split; `RuntimeSizedBindingPolicy`; pairwise-distinct descriptor hashes. |
| Step 3 schema | `runtime/zig/src/tsir/schema.zig` + `config/doe-tsir-*.schema.json` | Semantic/realization split with canonical digests; RMSNorm body contract + uniform-field epsilon with binding/offset plumbing. |
| Step 4 frontend | `runtime/zig/src/tsir/frontend.zig` | Lowers all three bootstrap families to their declared body ops; axis recovery + reduction recovery + body inference (per family) + epsilon resolution. |
| Step 5 planner | `runtime/zig/src/tsir/planner.zig` | `planRealization` produces deterministic `RealizationFunction` records for both descriptors; residency / tile factors / PE grid / reduction tree / typed rejection. |
| Step 6 collectives | `runtime/zig/src/tsir/collective_synthesis.zig` (planner calls in); frontend walker still owns semantic collection | Dedicated pass file isolates descriptor-backed native-capability / exactness / fabric-color-budget logic with typed rejections. Bootstrap families still have no collectives to exercise it; attention (Phase B) consumes this pass. |
| Step 7 emitter | `runtime/zig/src/tsir/emit_{kernel_body,csl,webgpu,msl,dxil,spir_v,text_skeleton}.zig` | Realization-only skeleton entry points remain for contract inspection; semantic-aware entry points emit executable fused_gemv / rms_norm / gather bodies across WebGPU, CSL, MSL, DXIL/HLSL, and SPIR-V/GLSL surfaces. Source-backed `emitterCodeDigest()` includes shared body source and remains pairwise-distinct by test. |
| Step 8 parity CLI | `bench/tools/doe_parity.py` + `bench/gates/nightly_tsir_parity_canary.py` | Narrow bootstrap oracle executes fused_gemv / rms_norm / gather input JSONs and writes real reference hashes. Backend execution lanes still return `not_implemented` / `deferred`; Zig subprocess oracle + WebGPU/CSL execution wiring remain unlanded. |
| Step 9 family rewrites | — | **0/3 Loop 3 parity receipts.** Directory `reports/parity/` does not yet exist. Gated on Step 7 executable bodies + Step 8 subprocess harness. |
| Step 10 manifest binding | `bench/tools/tsir_manifest_lowering.py` + `bench/fixtures/tsir-manifest-entries/*.json` | Schema, builder, six bootstrap fixtures; receipt ↔ fixture identity lockstep + fixture version + descriptor uniformity locked by test. |
| Step 11 AOT convert | — | Unlanded; cache-key design pending. |
| Step 12 rollout | — | Unlanded. |

Gates protecting Phase A artifacts:

*Repo-wide hygiene:*

- `bench/gates/doe_private_strategy_leak_gate.py` — private-strategy
  leak guard (Doe docs must not contain upstream-repo path or
  competitive-framing patterns).
- `runtime/zig/tools/check_line_limits.py` — 999-line Zig source cap;
  three TSIR modules allowlisted with tracked sharding follow-ups.
- `bench/tests/test_doc_link_coverage.py` — in-repo markdown link
  integrity across `docs/**` + root-level markdown.

*Rejection / exactness taxonomy:*

- `test_rejection_taxonomy_is_consistent_across_schemas` — rejection
  taxonomy lockstep across the four JSON schemas + Python CLI.
- Zig `test "rejection taxonomy is exhaustive and enumerable"` —
  Zig canonical enum.

*Bootstrap catalog ↔ manifest fixture chain:*

- `test_every_wgsl_has_semantic_sketch` + `test_every_wgsl_has_realization_per_target` —
  catalog forward invariant (every WGSL has semantic/notes + both
  target realizations).
- `test_no_orphan_artifacts_without_wgsl_pair` — catalog reverse
  invariant (no orphan semantic/realization/notes files without a
  matching WGSL).
- `test_every_bootstrap_wgsl_has_manifest_fixture` — catalog →
  fixture cross-layer (every bootstrap WGSL has fixtures for both
  targets).
- `test_manifest_fixture_kernelrefs_map_to_bootstrap_wgsl` — fixture
  → catalog cross-layer (every fixture's kernelRef names a real WGSL).
- `test_bootstrap_fixtures_validate_and_bind_distinct_targets` —
  fixture schema + pairwise uniqueness + per-kernel semantic-digest
  coherence + per-kernel realization distinctness across backends.
- `test_bootstrap_fixtures_share_version_and_descriptor_identity` —
  fixture set agreement on `frontendVersion` + `compilerVersion` +
  per-backend `targetDescriptorCorrectnessHash`.

*Receipt ↔ fixture identity:*

- `test_canary_receipts_carry_fixture_lowering_identity` — every
  nightly canary receipt's `loweringIdentity` matches the source
  fixture's digests byte-for-byte.
- `test_loads_exact_bootstrap_fixture_set` — canary enumerates the
  expected six (kernel, backend) pairs.

*Emitter identity:*

- Zig `test "tsir emitter code digests are pairwise distinct across
  all five backends"` — manifest-binding disambiguation.
- `test_canary_runs_fixture_receipts_without_claiming_pass` — backend
  lanes return `not_implemented` / `deferred` and do not silently
  promote before execution harnesses exist.

The missing path to proof 1 — in priority order: backend execution
wiring for the parity CLI (Step 8), first Loop 3 receipt for fused_gemv
against both `webgpu-generic` and `wse3` (Step 9 iter 1), manifest
binding of that receipt into a Doppler manifest (Step 10), and AOT
convert-time lowering (Step 11). Each is a multi-day wedge; the Loop 2
hygiene work through today has made every one of them safer to attempt.

## 2026-04-24

- TSIR Loop 2 — current-state prose refresh after Step 7 bodies landed:
  five prose docs still described the TSIR backend emitters as
  skeleton-only (`emit_*.zig` produce contract text, not executable
  kernel bodies). Step 7 executable bodies for fused_gemv / rms_norm /
  gather landed across all five emitters in `97c06859d`, so that framing
  is now stale. Refreshed:
  `docs/csl-architecture.md`,
  `docs/shader-compiler-architecture.md`,
  `docs/doppler-ingest.md`,
  `runtime/zig/README.md` (also adds `collective_synthesis.zig` +
  `emit_kernel_body.zig` to the enumerated file lists), and
  `docs/status/compiler-and-webgpu.md §Current state` to describe five
  backend emitters whose realization-only entry points still serialize
  contract skeletons while their semantic-aware entry points emit
  executable bodies for the Phase A bootstrap families. The
  classifier/template CSL lane still lives (Step 12 unlanded) and that
  caveat is preserved; what changed is the accurate current-state
  description of the TSIR emitter surface itself. Strategy-leak gate
  PASS, doc-link coverage PASS, 938/938 `test-wgsl` tests still pass.
  Per `docs/loop-protocol.md` Loop 2 protocol: documentation
  drift-prevention per CLAUDE.md §Documentation drift prevention; no
  code change, no phase boundary crossed. Cites
  `docs/tsir-lowering-plan.md` Step 7.
- TSIR Loop 2 — Step 6 collective-synthesis edge-case test coverage:
  `runtime/zig/tests/wgsl/tsir_planner_test.zig` gains two tests that
  exercise branches of `runtime/zig/src/tsir/collective_synthesis.zig`
  not reached by the prior three planner tests — (1) fabric-color
  budget exhaustion: submits `fabric_color_count + 1` native
  `fabric_reduce` nodes against the wse3 descriptor and locks the
  budget-many accepted entries (distinct `fabric_color` values), the
  single `tsir_collective_not_representable` rejection on the overflow
  index, and its exact detail string; (2) the
  `bit_exact_solo → tolerance_bounded` satisfiability branch of
  `collectiveExactnessSatisfies` via a `fabric_broadcast` semantic
  node (the existing workgroup-barrier test only reaches
  `bit_exact_solo → algorithm_exact`). 938/938 `test-wgsl` tests pass.
  Strategy-leak gate PASS. Per `docs/loop-protocol.md` Loop 2 protocol:
  within-step hardening of Step 6, no phase boundary crossed. Cites
  `docs/tsir-lowering-plan.md` Step 6.
- TSIR Step 8 — bootstrap parity oracle execution in the CLI:
  `bench/tools/doe_parity.py` now accepts dedicated bootstrap input
  JSON and computes real reference hashes for fused_gemv, rms_norm,
  and gather using deterministic f32/f16/bf16/u32 byte handling plus
  the existing manifest-lowering identity binding. Backend lanes remain
  honest `not_implemented` / `deferred` until WebGPU and CSL simfabric
  execution are wired, so no Loop 3 receipt is promoted by this step.
- TSIR Step 7 — semantic-aware executable bootstrap bodies: added
  `runtime/zig/src/tsir/emit_kernel_body.zig` and wired
  `emitSemantic` / `emitSemanticFunction` through all five TSIR backend
  emitters. The old realization-only skeleton entry points remain for
  contract inspection, but the supported semantic path now emits
  fused_gemv, rms_norm, and gather bodies for WebGPU, CSL, MSL,
  DXIL/HLSL, and SPIR-V/GLSL surfaces. Emitter digests now bind the
  shared body source, and `tsir_emit_kernel_body_test.zig` locks the
  three bootstrap families across the five emitters.
- TSIR Loop 2 — Step 6 collective-synthesis extraction:
  `runtime/zig/src/tsir/collective_synthesis.zig` carries the pass
  (`synthesize` plus `supportsCollective`,
  `collectiveExactnessSatisfies`, `needsFabricColor`,
  `chooseCollectiveGroupSize`) previously embedded in `planner.zig`.
  Behavior is preserved — 933/933 `test-wgsl` tests pass unchanged,
  including the three existing planner tests that exercise
  descriptor-supported collectives, absent-native rejection, and
  fabric-color budget exhaustion. Shared helpers `supportsNumericalMode`
  and `appendRejection` are now `pub fn` in `planner.zig` so the new
  file can call them; the planner in turn calls
  `collective_synthesis.synthesize(...)` from `planRealization`. Plan
  doc scaffold list and Phase A status-at-a-glance row for Step 6
  refreshed in the same change. This makes the dedicated Phase B prerequisite
  (`docs/tsir-lowering-plan.md §Step 6`) a named, isolated surface ready
  for the numerical-contract extensions (accumulation dtype, declared
  reduction tree, NaN/Inf policy) rather than code embedded inside the
  residency planner. Per `docs/loop-protocol.md` Loop 2 protocol: lowest-
  numbered unlanded step, one committable increment, no phase boundary
  crossed. Strategy-leak gate PASS, doc-link coverage PASS. Cites
  `docs/tsir-lowering-plan.md` Step 6.
- TSIR Loop 2 — manifest fixture generator build-step alignment:
  `bench/tools/generate_tsir_manifest_fixtures.py` now invokes
  `zig build tsir-bootstrap-manifest-inputs` and then runs the installed
  `doe-tsir-bootstrap-manifest-inputs` binary, instead of shelling through
  `zig run` on the source file. This makes the plan doc's build-step
  contract true in code and keeps fixture regeneration on the same
  type-checked build surface as the rest of TSIR.
- Plan: add `runtime/zig/src/tsir_bootstrap_manifest_inputs.zig` to
  `docs/tsir-lowering-plan.md §Current scaffold already in tree`.
  The `tsir/` subdir enumeration covered all thirteen core compiler
  files but missed the sibling build-step entrypoint added in tick 18
  that the Python fixture generator shells into via
  `zig build tsir-bootstrap-manifest-inputs`. Without it the scaffold
  list implied fixture digests appeared by magic; the real chain is
  Zig-computed inputs → Python pairing with descriptor/emitter
  hashes. Discoverability-only — no code change. Per
  `docs/loop-protocol.md` Loop 2 scope, within Step 3/5/10 supporting
  surfaces (no phase boundary crossed).
- Docs: add TSIR parity tooling entry to
  `docs/internal-tooling.md §Internal operator tooling`. That
  list enumerated bench/cli, release pipeline runner, blocking
  gates runner, workload generator, runtime README, and browser
  scripts — but no pointer to the TSIR parity surface added in
  bench/ today. One entry pointing at the three main TSIR tools
  (doe_parity, tsir_manifest_lowering, nightly_tsir_parity_canary)
  with a deeper pointer to `bench/README.md §TSIR parity tooling`
  (tick 59) for the full enumeration. Closes a similar
  discoverability gap to the tick 58/59 README fixes. Strategy
  leak gate PASS, doc-link coverage PASS. Cites
  `docs/loop-protocol.md` Loop 2 protocol.
- Docs: add TSIR row to `docs/doppler-ingest.md §Artifact
  ownership` table. The table enumerated five Doe-owned /
  Doppler-owned / Ouroboros-owned artifact classes (Doppler
  Program Bundle, WebGPU capture graph, HostPlan, CSL bundle and
  receipts, cross-repo CUJ narrative) but omitted TSIR semantic +
  realization artifacts — post-Phase-A, a distinct Doe-owned
  artifact class with schema-backed JSON contracts and
  `integrityExtensions.lowerings[]` bindings. Added a TSIR row
  between "WebGPU capture graph" and "HostPlan" naming what each
  level is (target-independent semantic + target-pinned
  realization), how it's digested, and where it binds. Strategy
  leak gate PASS, doc-link coverage PASS. Cites
  `docs/tsir-lowering-plan.md` Step 3 (schema + digests) + Step 10
  (manifest binding) and `docs/loop-protocol.md` Loop 2 protocol.
- Docs: add `## TSIR parity tooling` section to `bench/README.md`.
  The 2204-line bench README had zero TSIR mentions despite
  hosting the parity CLI, manifest-lowering builder, fixture
  generator, six bootstrap manifest fixtures, nightly canary, and
  five TSIR-related test files. A contributor scanning the bench
  README for TSIR tooling would have found nothing and had to
  hunt by filesystem. Added a short section (between §Proof-backed
  shader metric front door and §Terminology) enumerating the
  TSIR tools + fixtures + canary + tests, with pointers to plan,
  status shard, and loop protocol. Strategy-leak gate PASS,
  doc-link coverage PASS. Cites `docs/loop-protocol.md` Loop 2
  protocol.
- Docs: add TSIR entry to top-level `README.md` §Start here. The
  §Start here list enumerated entry points for package consumers,
  runtime, benchmarks, current status, Doppler ingest, project
  rationale, and proof/trace pipelines — but had no pointer for
  contributors interested in TSIR compiler work. Added one bullet
  naming plan + loop protocol + status shard. First-time visitors
  who'd be landing on the top-level README can now find TSIR
  entry points without navigating to `docs/architecture.md` first.
  Strategy-leak gate PASS, doc-link coverage PASS. Cites
  `docs/loop-protocol.md` Loop 2 protocol.
- Docs: add TSIR compiler surface section to
  `runtime/zig/README.md` §Source modules. The README had zero
  TSIR mentions despite Phase A landing substantial source
  surface (13 Zig files under `src/tsir/` + `src/targets/`). A
  reader scanning §Source modules for the TSIR surface would find
  nothing. Added a grouped entry between the WebGPU/render source
  modules and the §Public surface section, naming the three
  file groups (TSIR core, skeleton emitters, target descriptors)
  with pointers to the plan and status docs for detail. Strategy
  leak gate PASS, doc-link coverage PASS. Cites
  `docs/tsir-lowering-plan.md` §Current scaffold and
  `docs/loop-protocol.md` Loop 2 protocol.
- Docs: extend `docs/shader-compiler-architecture.md` §Related
  docs. The section had a single entry (TSIR plan doc). Added
  pointers to the overall architecture doc, the sibling compiler
  doc (csl-architecture), and the loop-protocol iteration
  discipline. Same discoverability pattern as ticks 54/55:
  architecture-level docs should enumerate their companions so a
  reader landing on one doc can find the others. Strategy-leak
  gate PASS, doc-link coverage PASS. Cites `docs/loop-protocol.md`
  Loop 2 protocol.
- Docs: extend `docs/csl-architecture.md` §Source of truth
  "Related user-facing entrypoints" list with pointers to the
  two live-status shards that cover this doc's subject matter:
  `docs/status/cerebras-csl.md` (CSL lane live status) and
  `docs/status/tsir.md` (TSIR generalization path live status).
  Same discoverability pattern as tick 54's plan-doc extension.
  A reader arriving at csl-architecture.md and looking for
  current reality would otherwise miss both shards.
  Strategy-leak gate PASS, doc-link coverage PASS. Cites
  `docs/loop-protocol.md` Loop 2 protocol.
- Docs: extend `docs/tsir-lowering-plan.md` §Relationship to
  current Doe docs with pointers to the two load-bearing docs
  added today: `docs/loop-protocol.md` (restored in tick 19 —
  defines Loop 2 / Loop 3 iteration discipline) and
  `docs/status/tsir.md` (split off in tick 8 — live status per
  plan step). The section previously listed only the three
  pre-existing architecture docs and omitted these newer
  dependencies. Strategy-leak gate PASS, doc-link coverage PASS.
  Cites `docs/tsir-lowering-plan.md` §Relationship to current Doe
  docs and `docs/loop-protocol.md` Loop 2 protocol.
- Docs: finish `docs/doppler-ingest.md` TSIR framing refresh. Tick 41
  updated item 1 of §Lowering architecture, but the "operative path
  vs planned migration" framing further down (lines 146–160) still
  used "planned migration path" / "planned lowering architecture"
  language. Rewrote to "in-flight migration path" and named the
  Phase A compiler surface + pointer to `docs/status/tsir.md` in
  the plan-doc reference line. Ninth doc in the post-Phase-A
  landed-state drift class. Strategy-leak gate PASS, doc-link
  coverage PASS. Cites `docs/tsir-lowering-plan.md` §Current
  scaffold and `docs/loop-protocol.md` Loop 2 protocol.
- Code: refresh stale header comment in
  `runtime/zig/tests/wgsl/tsir_frontend_test.zig`. Said "Step 4
  scaffold tests" and "The lowering itself is minimal (names only
  for now) so this test locks the 'pipeline exists' milestone;
  richer coverage (bindings, axes, reductions, collectives) lands
  with future increments." Stale — the frontend now recovers full
  TSIR semantic including bindings, axes, reduction regions,
  collective nodes, typed rejections, family hints, and per-family
  `SemanticBody` payloads. Rewrote to describe what the tests
  actually lock. 933/933 Zig tests still pass; strategy-leak gate
  PASS. Cites `docs/tsir-lowering-plan.md` Step 4 (frontend) and
  `docs/loop-protocol.md` Loop 2 protocol.
- Code: refresh module docstring of
  `bench/tests/test_tsir_bootstrap_catalog.py`. Described only
  schema validation ("This test fails closed if any catalog entry
  stops validating against the current schema"), but ticks 29/30
  added `test_every_wgsl_has_realization_per_target` and
  `test_no_orphan_artifacts_without_wgsl_pair` — the module now
  locks four distinct internal-integrity contracts, not one.
  Rewrote to enumerate all four (schema validation, WGSL+
  semantic+notes pairing, per-target realization completeness,
  orphan check). 6/6 catalog tests still pass; strategy-leak gate
  PASS. Cites `docs/tsir-lowering-plan.md` Step 1.5 (bootstrap
  catalog) and `docs/loop-protocol.md` Loop 2 protocol.
- Code: refresh docstring of `bench/tests/test_doe_parity.py`. Said
  the tests "lock the fail-closed scaffolding contract until the
  TSIR reference interpreter and backend lanes land in future
  sessions" — overclaims what's pending. The reference interpreter
  landed in ticks 1–3 with all three Phase A bootstrap families on
  all dtypes; the actual outstanding wedge is the CLI subprocess
  harness to the Zig oracle (the interpreter runs in-process, just
  not from the Python CLI yet). Rewrote to name both real remaining
  gaps accurately: CLI subprocess harness + backend executable
  kernel bodies. 19/19 parity CLI tests still pass; strategy-leak
  gate PASS. Cites `docs/tsir-lowering-plan.md` Step 1 (oracle) +
  Step 7 (mechanical emitter executable bodies) + Step 8 (parity
  CLI subprocess harness), and `docs/loop-protocol.md` Loop 2
  protocol.
- Code: refresh two stale comments in
  `runtime/zig/src/tsir/reference_interpreter.zig`:
  (a) `trySimpleReduction` docstring said "Detect the simplest
  reduction case the oracle can honor in Phase A: a 1-D
  `strict_ordered` sum over `f32` …" — stale; the function now
  handles ranks 1–4+, all four reduction ops, both associativity
  modes, and all three Phase A dtypes with upcast/downcast. Wrote
  a precise Phase A envelope listing what's inside vs. what falls
  through. (b) Inline associativity-dispatch comment said "`.binomial`
  pairwise fold is rank-1-only this phase" — rank-2 and rank-3 both
  support binomial now; only rank-4+ rejects it. Updated.
  933/933 Zig tests still pass. Strategy-leak gate PASS. Cites
  `docs/tsir-lowering-plan.md` Step 1 (oracle scope) and
  `docs/loop-protocol.md` Loop 2 protocol.
- Code: refresh stale module-header comment in
  `runtime/zig/src/tsir/digest.zig`. Said "Realization
  canonicalization is still scaffolding (byte-string summary)
  pending its own walker in a future iteration." — factually wrong.
  `canonicalizeRealization` and `emitRealization` (lines 513+) are
  full walkers that emit every field of every nested TSIR type in
  declared order, matching what the semantic walker does. Rewrote
  the header to describe the actual state: both semantic and
  realization canonicalization are walker-based and produce stable
  digests under content-equivalent inputs. `zig build test-wgsl`
  still passes 933/933. Strategy-leak gate PASS. Cites
  `docs/tsir-lowering-plan.md` Step 3 (TSIR schema + canonical
  digests) and `docs/loop-protocol.md` Loop 2 protocol.
- Code: refresh misleading detail string in
  `bench/tools/doe_parity.py::run_reference_interpreter`. Said
  "tsir.reference_interpreter returns NotImplemented; scaffolding
  only" — accurate when the CLI landed (pre-ticks-1-3 oracle), but
  the oracle now recognizes all three Phase A bootstrap families
  across `{f32, f16, bf16}`. The scaffolding-only aspect is that
  the CLI doesn't shell into the Zig oracle, not that the oracle
  is stubbed. Rewrote detail to name the real integration gap
  (CLI subprocess harness). 19/19 parity CLI tests still pass;
  strategy-leak gate PASS. Cites `docs/tsir-lowering-plan.md`
  Step 8 (parity CLI) and `docs/loop-protocol.md` Loop 2 protocol.
- Docs: refresh `docs/status/cerebras-csl.md` §Current state first
  bullet. Line said "The TSIR scaffold is in tree, but the live CSL
  lane still uses the existing classifier/template route." Same
  "scaffold" understatement as tick 42's fix in
  compiler-and-webgpu.md. Rewrote to name Phase A landed surface
  explicitly (with pointer to tsir.md) while preserving the
  honest statement that the CSL-specific skeleton emitter produces
  contract text rather than executable kernels. Non-refreshed text:
  the dated 2026-04-23 entry at the top of the shard stays
  untouched — dated entries are historical observations and
  refreshing them destroys that history. Strategy-leak gate PASS,
  doc-link coverage PASS. Cites `docs/loop-protocol.md` Loop 2
  protocol.
- Docs: finish the tick-39 refresh in `docs/csl-architecture.md` —
  tick 39 refreshed the body of §Planned TSIR generalization but
  left the section header ("Planned TSIR generalization") and
  opening sentence ("The planned direction is a Tiled Spatial IR")
  stale. Updated header to "TSIR generalization path" and reworded
  the opening to name the general-lowering direction without
  "planned" framing. Preserves the accurate "not yet a completed
  replacement for the classifier/template path" framing from
  tick 39. Strategy-leak gate PASS, doc-link coverage PASS. Cites
  `docs/tsir-lowering-plan.md` §Current scaffold + §Relationship
  to current Doe docs, and `docs/loop-protocol.md` Loop 2 protocol.
- Docs: remove four TSIR-specific bullets from
  `docs/status/compiler-and-webgpu.md` §Current state. Left over
  from when that shard owned TSIR before the tick-8 split. Per
  tick 26's scope notice ("this shard stays focused on non-TSIR
  compiler work"), TSIR current state should live in tsir.md — and
  does, in the Phase A status-at-a-glance section from tick 22.
  The four bullets were also materially outdated ("TSIR scaffold
  exists, but it is not wired into the real frontend/emitter path
  yet" — Phase A compiler surface is now wired for the bootstrap
  pipeline test). Replaced with a one-line pointer to tsir.md.
  Shard drops from 86 to 66 lines. Strategy-leak gate PASS,
  doc-link coverage PASS. Cites `docs/loop-protocol.md` Loop 2
  protocol.
- Docs: refresh TSIR framing in `docs/doppler-ingest.md` §Lowering
  architecture, item 1 (Kernel-level lowering — the TSIR contract).
  Same "scaffolding for that plan, not a completed pipeline"
  language as csl-architecture.md had pre-tick-39. Rewrote to name
  the Phase A compiler surface explicitly (schema, digests,
  frontend, planner, reference interpreter, five skeleton emitters)
  while preserving the honest framing that the pipeline is not yet
  a completed replacement for the classifier/template CSL path.
  Added pointer to `docs/status/tsir.md`. Eighth doc in the
  post-Phase-A landed-state drift class (ticks 27/28/34/35/37/38/39
  and now this one). Strategy-leak gate PASS, doc-link coverage
  PASS. Cites `docs/tsir-lowering-plan.md` §Current scaffold and
  `docs/loop-protocol.md` Loop 2 protocol.
- Docs: refresh `runtime/zig/STYLE.md` file-size section. Bullet at
  line 94 said "a small number of test-only WGSL files currently
  exceed this cap" — factually wrong (no WGSL files exist in
  `runtime/zig/src/`; the over-cap files are the three TSIR Phase A
  Zig modules allowlisted in tick 15). Rewrote to name the actual
  allowlist mechanism (`ALLOWLIST` in `check_line_limits.py` with
  sharding follow-ups tracked in `docs/status/tsir.md`), name the
  three specific TSIR modules currently on the allowlist
  (reference_interpreter.zig, frontend.zig, digest.zig), and flag
  allowlist entries as tracked debt rather than precedent.
  Strategy-leak gate PASS, doc-link coverage PASS. Cites
  `docs/tsir-lowering-plan.md` Step 7 (the TSIR modules currently
  over cap) + `docs/loop-protocol.md` Loop 2 protocol.
- Docs: refresh TSIR framing in `docs/csl-architecture.md`
  §Planned TSIR generalization. Paragraph said "The current in-tree
  `runtime/zig/src/tsir/` surface is scaffolding for that plan" —
  "scaffolding" understated the Phase A compiler surface that
  landed (full schema, digests, frontend, planner, reference
  interpreter, and mechanical skeleton emitters for five backends
  including the CSL skeleton). Rewrote to name the landed
  capability while preserving accurate framing that TSIR is not
  yet a completed replacement for the classifier/template CSL
  lane (skeleton emitters produce contract text, classifier
  remains the live CSL path). Added pointer to
  `docs/status/tsir.md` for live status. Same drift class as
  ticks 27/28/34/35/37/38; this is now the seventh doc updated in
  this class. Strategy-leak gate PASS, doc-link coverage PASS.
  Cites `docs/tsir-lowering-plan.md` §Current scaffold + §Related
  to current Doe docs, and `docs/loop-protocol.md` Loop 2 protocol.
- Docs: refresh TSIR framing in `docs/architecture.md` and
  `docs/shader-compiler-architecture.md`. Both had "planned" TSIR
  language — accurate when written (pre-Phase-A), but stale after
  the compiler surface landed. Updated both to say the architecture
  is landed (while being precise that TSIR is not yet the wired
  executable compiler path for CSL or WebGPU — skeleton emitters
  produce contract text, not executable kernel bodies, and the
  classifier/template CSL lane + Doe IR → MSL/SPIR-V/HLSL WebGPU
  lanes remain live). Each also gains a pointer to
  `docs/status/tsir.md` so readers of the architecture docs land
  on live status. Same post-migration doc-drift class as ticks
  27/28/34/35, just in architecture-level docs rather than status
  shards. Strategy-leak gate PASS, doc-link coverage PASS. Cites
  `docs/tsir-lowering-plan.md` §Current scaffold and
  `docs/loop-protocol.md` Loop 2 protocol.
- Docs: refresh `fused_gemv.notes.md` and `gather.notes.md` Status
  paragraphs in the bootstrap catalog. Both described their semantic
  JSONs as "semantically incomplete" / "unrepresentable" — accurate
  when the notes were written (pre-`SemanticBody` schema), but stale
  after the body-op contract + oracle recognizers landed for both
  families. Refreshed status entries now name the landed state
  explicitly (body-op contract present, oracle recognizes the shape
  across `{f32, f16, bf16}`) and preserve the "pre-`SemanticBody`"
  framing for historical context. `rms_norm.notes.md` was already
  refreshed in commit 9b6f6d117 (schema extension landing).
  Bootstrap catalog tests pass. Strategy-leak gate PASS. Cites
  `docs/tsir-lowering-plan.md` Step 1.5 (bootstrap catalog) and
  `docs/loop-protocol.md` Loop 2 protocol.
- Docs: add `tsir.md` to the bottom-of-front-door "Live topical
  shards" list. The top-of-file "How to use the status log" section
  lists four shards including tsir.md, but the `## Live topical
  shards` section near the bottom was an inconsistent three-item
  list that omitted tsir.md. Readers navigating to the bottom
  would miss the TSIR shard entirely. Doc-only one-line addition.
  Strategy-leak gate PASS, doc-link coverage PASS. Cites
  `docs/loop-protocol.md` Loop 2 protocol.
- Docs: refresh the `docs/status.md` front-door TSIR bullet. Tick-6
  version was stale on three axes: (a) only named `emit_csl.zig` as
  the mechanical emitter — five backends now have skeleton emitters
  (csl, webgpu, msl, dxil, spir_v + shared text helper); (b) omitted
  `family_hint.zig` from the TSIR core file list; (c) pointed
  readers at both `docs/status/tsir.md` and
  `docs/status/compiler-and-webgpu.md` for TSIR status — post
  migrations (ticks 24/26), compiler-and-webgpu.md no longer holds
  TSIR status. Same class of post-migration drift as ticks 27/28
  (loop-protocol.md + tsir-lowering-plan.md). Strategy-leak gate
  PASS, doc-link coverage PASS. Cites
  `docs/tsir-lowering-plan.md` §Current scaffold and
  `docs/loop-protocol.md` Loop 2 protocol.
- Docs: refresh the Phase A status-at-a-glance "Gates" list to
  reflect the four bootstrap-catalog ↔ manifest-fixture invariant
  tests added in ticks 29–32. Reorganized the list into four
  categories (repo-wide hygiene, rejection/exactness taxonomy,
  bootstrap-catalog ↔ manifest-fixture chain, receipt ↔ fixture
  identity, emitter identity) so a reader can locate the layer
  they're editing. Added the Zig canonical-enum taxonomy test
  and the canary's pair-enumeration test that were live but
  previously uncatalogued. Doc-only; all tests still pass.
  Cites `docs/tsir-lowering-plan.md` Step 1.5 + Step 10 and
  `docs/loop-protocol.md` Loop 2 protocol.
- Tests: add reverse-direction catalog → manifest-fixture check
  `test_every_bootstrap_wgsl_has_manifest_fixture`. Complements tick
  31's manifest → catalog check. Catches "new kernel landed in the
  bootstrap catalog but manifest fixtures weren't regenerated" —
  the catalog test passes (new kernel has semantic + realization +
  notes), and existing fixture tests hard-code `len(paths) == 6`
  which only fires if a fixture shrinks, not if the catalog grows.
  Downstream consumers (nightly canary, receipt producers) assume
  every kernel has fixtures; this makes the assumption testable.
  Error message includes the regeneration command. Closes the
  bidirectional bootstrap-catalog ↔ manifest-fixture invariant.
  11/11 manifest-lowering tests pass. Strategy-leak gate PASS.
  Cites `docs/tsir-lowering-plan.md` Step 1.5 (bootstrap catalog)
  + Step 10 (manifest binding) + `docs/loop-protocol.md` Loop 2
  protocol.
- Tests: add cross-layer kernelRef → bootstrap-WGSL integrity check
  `test_manifest_fixture_kernelrefs_map_to_bootstrap_wgsl` in
  `bench/tests/test_tsir_manifest_lowering.py`. Manifest fixtures
  use `kernelRef: "doe.tsir.bootstrap.<name>"` where `<name>` must
  correspond to an actual WGSL file in the bootstrap catalog.
  Existing fixture tests enforced set-internal coherence but never
  cross-referenced `<name>` back to the catalog — a kernel rename
  or deletion in the catalog would otherwise leave a dangling
  reference in the fixture set, and downstream receipts would
  attribute artifacts to a kernel that no longer exists. Pairs
  with tick 30's reverse-direction orphan check in the catalog:
  together they enforce "every `<name>` appears in both places or
  neither." 10/10 manifest-lowering tests pass; strategy-leak
  gate PASS. Cites `docs/tsir-lowering-plan.md` Step 10 (manifest
  binding) + `docs/loop-protocol.md` Loop 2 protocol.
- Tests: add reverse-direction orphan check
  `test_no_orphan_artifacts_without_wgsl_pair` to
  `bench/tests/test_tsir_bootstrap_catalog.py`. Existing tests
  enforced the forward direction (every WGSL has a semantic + notes
  + per-target realization). Reverse direction was uncovered — a
  leftover `*.tsir-semantic.json` / `*.tsir-realization.*.json` /
  `*.notes.md` after a kernel rename or deletion would sit in the
  bootstrap dir with no matching WGSL, and downstream consumers
  (catalog validators, nightly canary) would silently pick up the
  orphan. Test iterates each artifact kind, derives the stem, and
  asserts there's a matching WGSL. 6/6 catalog tests pass.
  Strategy-leak gate PASS. Cites `docs/tsir-lowering-plan.md`
  Step 1.5 (bootstrap catalog — the artifact set this locks) and
  `docs/loop-protocol.md` Loop 2 protocol.
- Tests: add `test_every_wgsl_has_realization_per_target` to
  `bench/tests/test_tsir_bootstrap_catalog.py`. Existing tests
  verified each WGSL has a matching semantic JSON and notes, and
  that whatever realization files exist validate against the
  schema — but neither enforced that every `(kernel, target)` pair
  exists. A new bootstrap WGSL could land with only one target's
  realization and both tests would pass. Downstream consumers
  (`bench/fixtures/tsir-manifest-entries/`, nightly canary) assume
  the set is complete. Test asserts both `webgpu-generic` and
  `wse3` realization files exist for every bootstrap WGSL. 5/5
  catalog tests pass; strategy-leak gate PASS. Cites
  `docs/tsir-lowering-plan.md` Step 1.5 (bootstrap catalog) and
  `docs/loop-protocol.md` Loop 2 protocol.
- Docs: update `docs/tsir-lowering-plan.md` to reflect the
  post-migration TSIR shard. Plan doc's "Current scaffold already
  in tree" section pointed readers at both `docs/status/tsir.md`
  and `docs/status/compiler-and-webgpu.md` for live TSIR status.
  After ticks 8/24/26 made tsir.md the TSIR shard and moved all
  TSIR content out of compiler-and-webgpu.md, the second
  reference was stale. Updated to point at tsir.md only for live
  status, with a pointer to `archive/2026-04.md` for the
  2026-04-23 TSIR Step 4 incremental history. Same class of
  post-migration drift as tick 27's loop-protocol.md fix — both
  docs predated the shard split and both had content references
  that outlived the migration. Both gates PASS. Cites
  `docs/tsir-lowering-plan.md` §Current scaffold (the file this
  updates) and `docs/loop-protocol.md` Loop 2 protocol.
- Docs: update `docs/loop-protocol.md` to reflect the post-migration
  shard scopes. The protocol doc (restored in tick 19 from tick-0
  content that predates the tsir.md split) still said "Loop 2 doc
  output: status entry in `docs/status/compiler-and-webgpu.md` /
  `docs/status/cerebras-csl.md`" and "Phase A is closed in
  `docs/status/compiler-and-webgpu.md`". After ticks 8/24/26 made
  tsir.md the TSIR shard, both references were stale. Updated: Loop
  2 doc output for TSIR now routes to `docs/status/tsir.md`; Phase A
  closure also lands there. Both gates PASS. Cites
  `docs/loop-protocol.md` itself (the file this updates) and
  `docs/tsir-lowering-plan.md` §Step 12 (Phase A exit criteria).
- Docs: migrate 2026-04-23 TSIR Step 4 incremental history from
  `compiler-and-webgpu.md` to `archive/2026-04.md`. Tick 25
  deferred this under a design concern (archive file used a
  different header convention); reconsidered and resolved by
  wrapping the migrated block with a provenance paragraph that
  explains the convention mix and preserves the original
  `## 2026-04-23` section header. Impact: `compiler-and-webgpu.md`
  drops from 1701 to 86 lines — well under the 1200 cap, cap
  notice replaced with a scope notice. The archive grows to
  ~11.7k lines (archives have no cap). Both sibling shards'
  intro paragraphs updated to reflect new location.
  Strategy-leak gate PASS, doc-link coverage PASS. Cites
  `docs/loop-protocol.md` Loop 2 protocol (outstanding tick-8
  migration follow-up now fully closed; the live shards are
  coherent with their stated scopes).
- Docs: refresh the cap-notice paragraphs on both shards to match
  post-migration state. `tsir.md` intro said "historical TSIR
  entries remain in compiler-and-webgpu.md until a deliberate
  migration sweep"; after tick 24 the 2026-04-24 entries were
  migrated, so the sentence now distinguishes migrated-24 from
  pending-23. `compiler-and-webgpu.md` cap notice correspondingly
  says what migrated and what still sits pending. Names the
  specific blocker on the 2026-04-23 archive migration (entries
  there follow the `## Push:` archive convention rather than the
  `## YYYY-MM-DD` + bullet convention used in the live shards —
  needs a separate tick to either convert inline or create a
  dedicated archive file). Doc-only; no test or runtime change.
  Cites `docs/loop-protocol.md` Loop 2 protocol.
- Docs: migrate 2026-04-24 TSIR entries from
  `compiler-and-webgpu.md` to `tsir.md`. Tick 8 created the shard
  split but deferred the historical migration — the 2026-04-24
  TSIR content had accumulated in `compiler-and-webgpu.md` before
  `tsir.md` existed and had been sitting in the wrong shard ever
  since. Moved all ~260 lines under the existing 2026-04-24
  section in `tsir.md` with an HTML-comment migration marker.
  `compiler-and-webgpu.md` drops from 1965 to 1701 lines — still
  over the 1200 cap but materially closer (older pre-2026-04-24
  TSIR history remains for a later migration pass). `tsir.md`
  grows to 586 lines, well under cap. Strategy-leak gate PASS,
  doc-link coverage test PASS, no content changes — only
  relocation. Cites `docs/loop-protocol.md` Loop 2 protocol
  (deferred follow-up from tick 8 closed).
- Tests: extend `test_doc_link_coverage` to scan root-level markdown
  files (`AGENTS.md`, `README.md`, `CLAUDE.md`, `SKILLS.md`) in
  addition to `docs/**/*.md`. Those root-level files carry
  load-bearing in-repo links (AGENTS.md lists the per-language style
  guides; CLAUDE.md lists mandatory-reading paths) that were outside
  the test's coverage. The extension is additive — existing links
  still pass, plus the five style-guide links from AGENTS.md now
  verify. Test still completes in ~10ms. Strategy-leak gate PASS.
  Cites `docs/loop-protocol.md` Loop 2 protocol (generalization of
  the tick 20 regression guard).
- Docs: add a Phase A status-at-a-glance section at the top of this
  shard. Readers coming fresh were landing on the dated entries
  immediately, which meant scanning 20+ tick entries to orient on
  current Phase A state. The new section names what exists by file
  path for each plan step (per CLAUDE.md doc-drift discipline —
  shape not counts), lists the gates that protect Phase A artifacts
  (strategy-leak, line-limit, doc-link, canary-receipt-identity,
  fixture uniformity, rejection-taxonomy lockstep, emitter-digest
  distinctness), and closes with the remaining proof-1 work in
  priority order (executable kernel bodies, parity CLI subprocess
  harness, Loop 3 fused_gemv receipt, manifest binding). Strategy
  leak gate and doc-link coverage test both PASS. Cites
  `docs/tsir-lowering-plan.md` step structure and
  `docs/loop-protocol.md` Loop 2 / Loop 3 discipline.
- Gate: fix the third self-referential leak-gate trip of the day.
  The test landed in tick 20 (`bench/tests/test_doc_link_coverage.py`)
  had a code comment quoting the forbidden upstream-path pattern in
  backticks while describing what the test skips. Same mistake shape
  as tick 10 and tick 19 — describe the rule, don't quote the
  literal token. Reworded. Both gates PASS. No behavior change; test
  still passes on the fixed tree. Cites `docs/loop-protocol.md`
  Loop 2 protocol (the recurring discipline this wedge repairs).
- Tests: add `bench/tests/test_doc_link_coverage.py` — walks
  `docs/**/*.md` (excluding `docs/status/archive/`), extracts every
  markdown link that resolves to a local in-repo path, and asserts
  the target exists on disk. External URLs, cross-repo paths, and
  same-doc anchors are skipped. Generalizes tick 19's fix (a
  load-bearing doc had disappeared, and references to it stayed
  broken for 18 ticks because nothing was checking). First run
  found four existing broken links in `docs/status.md` — all from
  tick 6's own TSIR bullet which used repo-root-prefixed paths
  instead of doc-relative. Fixed those; added a link to the new
  `docs/status/tsir.md` shard while cleaning up. Test passes on
  the fixed tree. Also fixed a tick-19 self-referential
  leak-gate trigger (same mistake pattern as tick 10/11 —
  quoting a forbidden token in backticks triggers the gate). Both
  gates now PASS. Cites `docs/loop-protocol.md` Loop 2 protocol
  (the file the new test primarily protects) and
  `docs/tsir-lowering-plan.md` §Documentation drift prevention.
- Docs: restore `docs/loop-protocol.md`. The file was in the working
  tree at the start of today's Loop 2 push (I read it in tick 0 and
  based every subsequent tick's discipline on it), but had never been
  committed and somewhere in today's churn was removed from disk.
  Every tick commit message since tick 0 cited it, `docs/status.md`
  lists it, `docs/tsir-lowering-plan.md` references it, the user's
  cron prompt names it — all pointing at a missing file. Restored
  from the content captured in tick 0 Read output. File is now
  tracked so this cannot recur through untracked-file cleanup.
  Strategy-leak gate PASS after add (the restored doc mentions
  "Ouroboros" as a proper-noun repo name in the cross-repo
  handoffs section, not as an upstream-path pattern, so the gate
  stays clean). No runtime, test, or contract
  change. Cites `docs/tsir-lowering-plan.md` §Step 12 (rollout
  ordering — the protocol sits on top of) and `docs/loop-protocol.md`
  itself (the file whose restoration this entry describes).
- Build: add `tsir-bootstrap-manifest-inputs` build step.
  `runtime/zig/src/tsir_bootstrap_manifest_inputs.zig` is invoked by
  the Python fixture generator (`bench/tools/generate_tsir_manifest_fixtures.py`)
  via `zig run` on the source, so the file was not otherwise
  type-checked by standard `zig build`. A schema, target-descriptor,
  frontend, or planner change that broke the generator source would
  only surface at next fixture regen — potentially days after the
  breaking change. Added the tool as a build step matching the
  pattern used for `csl_host_plan_tool` so compile errors surface
  immediately. Binary installs at
  `zig-out/bin/doe-tsir-bootstrap-manifest-inputs`. `zig build
  test-wgsl` still passes 933/933. Cites
  `docs/tsir-lowering-plan.md` Step 10 (manifest binding — the
  generator produces these fixtures) + `docs/loop-protocol.md`
  Loop 2 protocol (harness tightening follows the tick 15/16
  pattern of wiring gate checks into per-tick build signals).
- Docs: refresh `bench/fixtures/tsir-manifest-entries/README.md`. The
  existing README named only the regeneration command — not the
  fixture purpose, the downstream consumers that depend on this set
  as a coherent snapshot (manifest binder, nightly canary, parity
  CLI's `--manifest-lowering-entry` path), or the uniformity
  invariants the tests enforce. Rewrote it to name all of those,
  enumerate the six per-(kernel, backend) entries, and explicitly
  warn that fixtures must always regenerate together — partial
  regeneration is exactly what `test_bootstrap_fixtures_share_version_and_descriptor_identity`
  from tick 14 catches, and a contributor running the generator
  against one file after a descriptor change would otherwise not
  know the set now needs full regen. Strategy-leak gate PASS after
  edit. Doc-only; no runtime or test change. Cites
  `docs/tsir-lowering-plan.md` Step 10 (manifest binding) and
  `docs/loop-protocol.md` Loop 2 protocol.
- Build: wire `test-wgsl` to `line_limit_check`. The tick-15 follow-up
  is landed: `runtime/zig/build.zig` now makes `wgsl_test_step`
  depend on `line_limit_check.step`, matching what `test`,
  `test-core`, `test-full`, and `test-d3d12` already do. Future
  Zig source-cap breaches surface on `zig build test-wgsl` rather
  than hiding until a full `test` run. `zig build test-wgsl` passes
  with advisory allowlist warnings (same three TSIR files tracked
  in the tick-15 allowlist). Clears the sharding-pending follow-up
  for this specific build wiring; the three source-file sharding
  splits themselves remain pending per the entries below.
- TSIR Loop 2 — Zig line-limit cap breach acknowledged + tracked:
  `zig build test` was failing because three TSIR modules are over
  the 999-line Zig source cap (`tsir/reference_interpreter.zig` at
  4103, `tsir/frontend.zig` at 2059, `tsir/digest.zig` at 1227).
  The `test-wgsl` subset does not depend on the line-limit check
  so the breach was hiding during per-tick test runs; the full
  `test` step caught it. Added all three to
  `runtime/zig/tools/check_line_limits.py` allowlist with explicit
  sharding follow-ups (reference_interpreter: split by family
  dispatch; frontend: split by pass; digest: split by tier).
  `zig build test` now passes with advisory warnings.
  **Sharding follow-ups pending (owner: next Loop 2 breadth wedge):**
  - `tsir/reference_interpreter.zig`: split into per-family dispatch
    modules — `ref_interp_fused_gemv.zig`, `ref_interp_rms_norm.zig`,
    `ref_interp_gather.zig`, `ref_interp_reduction.zig`, plus a
    dispatcher in `reference_interpreter.zig`.
  - `tsir/frontend.zig`: split by pass — axis recovery, reduction
    recovery, body inference (per family), epsilon resolution.
  - `tsir/digest.zig`: split by tier — semantic, realization,
    emitter-code, each with its own canonical serializer.
  Each split must follow CLAUDE.md discipline: "group by feature,
  keep related code together; splitting a file must not scatter a
  single concern." Cites `docs/tsir-lowering-plan.md` Step 7 and
  `docs/loop-protocol.md` Loop 2 protocol. Also logs a follow-up
  to wire `test-wgsl` to the line-limit check so future breaches
  surface during per-tick test runs rather than only on full
  `test`.
- TSIR Loop 2 — bootstrap fixture version + descriptor uniformity lock:
  new `test_bootstrap_fixtures_share_version_and_descriptor_identity`
  in `bench/tests/test_tsir_manifest_lowering.py` asserts every one
  of the six manifest-lowering fixtures shares the same
  `frontendVersion` and `compilerVersion`, and every fixture for a
  given backend (`webgpu-generic` or `wse3`) shares the same
  `targetDescriptorCorrectnessHash`. The existing
  `test_bootstrap_fixtures_validate_and_bind_distinct_targets` covered
  kernel/pair uniqueness and per-kernel semantic-digest coherence, but
  not version or per-backend descriptor drift. Partial regeneration —
  bumping the frontend or a descriptor and running
  `bench/tools/generate_tsir_manifest_fixtures.py` against only a subset
  — would leave the set internally inconsistent, and downstream
  consumers (canary, manifest binder, parity CLI) assume the set is a
  coherent snapshot. 9/9 manifest-lowering tests pass.
  Cites `docs/tsir-lowering-plan.md` Step 10 (manifest binding) and
  `docs/loop-protocol.md` Loop 2 protocol.
- TSIR Loop 2 — canary receipt ↔ fixture identity lockstep: new
  `test_canary_receipts_carry_fixture_lowering_identity` in
  `bench/tests/test_nightly_tsir_parity_canary.py` asserts that every
  receipt the nightly canary emits carries the exact same
  `loweringIdentity` digests (`tsirSemanticDigest`,
  `tsirRealizationDigest`, `emitterDigest`,
  `targetDescriptorCorrectnessHash`) as the source manifest-lowering
  fixture at `bench/fixtures/tsir-manifest-entries/`. Catches drift
  where the parity CLI or canary recomputes a digest on its own
  path and silently produces a receipt bound to a different
  `(semantic, realization, emitter, target)` tuple than the
  manifest entry declared — if that drift ever reaches Loop 3
  promotion, the receipt would attribute artifacts to a lowering
  that doesn't exist. Strategy-leak gate verified PASS after edit.
  Cites `docs/tsir-lowering-plan.md` Step 10 (manifest binding) and
  `docs/loop-protocol.md` Loop 2 protocol.
- Plan doc refresh: `docs/tsir-lowering-plan.md` "Current scaffold
  already in tree" section was drafted before Phase A landed and
  didn't mention `family_hint.zig`, the five backend skeleton
  emitters (`emit_csl`, `emit_webgpu`, `emit_msl`, `emit_dxil`,
  `emit_spir_v`) plus `emit_text_skeleton`, the target descriptors
  under `runtime/zig/src/targets/`, the four JSON schemas under
  `config/`, the bench tooling (parity CLI, manifest-lowering
  builder, nightly canary), the bootstrap manifest fixtures, or the
  bootstrap test fixture set. Future Loop 2 readers were getting a
  stale starting picture. Rewrote the section to describe what
  exists in shape (not counts) with artifact-path references per
  CLAUDE.md documentation-drift discipline. Also refreshed the
  "missing work" paragraph to name executable kernel bodies, parity
  CLI subprocess harness, AOT convert-time cache, Loop 3 per-family
  parity receipts, manifest binding into Doppler RDRR, and
  Phase B attention + sollya. Strategy-leak gate verified PASS
  post-edit. Cites `docs/tsir-lowering-plan.md` §Current scaffold
  and `docs/loop-protocol.md` Loop 2 protocol (doc-only
  in-step increment).
- Private-strategy leak gate: fixed two cross-repo path references to
  the upstream planning repo in `docs/doppler-ingest.md:11` that were
  failing `bench/gates/doe_private_strategy_leak_gate.py` (a hard
  blocking gate per CLAUDE.md). The line had a markdown link pointing
  at an upstream planning repo path. Replaced with Doe-local prose
  describing only the Doe-local side of the Doppler-Doe boundary;
  motivation and composition context are intentionally not named.
  Gate now passes. Not a TSIR wedge strictly, but logged here because
  the status shard has been the main Loop 2 activity surface today
  and the leak was discovered while confirming no TSIR doc drift
  during this tick's
  scope search.
- TSIR Loop 2 — cross-backend emitter digest distinctness lock: new
  test "tsir emitter code digests are pairwise distinct across all five
  backends" in `runtime/zig/tests/wgsl/tsir_emit_backend_skeleton_test.zig`.
  Computes `emitterCodeDigest()` for each of the five backend emitters
  (`emit_csl`, `emit_webgpu`, `emit_msl`, `emit_dxil`, `emit_spir_v`)
  and asserts all pairs are distinct. The manifest-lowering contract
  binds `(kernelRef, backend)` pairs to an emitter digest so replay
  identifies which backend produced an artifact; silent digest
  collision (e.g. a refactor leaving two emitter sources identical)
  would make that binding ambiguous and attribute artifacts to the
  wrong backend. Per-emitter digest formation (emitter source +
  shared `emit_text_skeleton.zig`) is still covered by the existing
  "expose source-backed code digests" test. `zig build test-wgsl`:
  933/933 pass. Cites `docs/tsir-lowering-plan.md` Step 7 (mechanical
  emitter identity) and Step 10 (manifest binding); `docs/loop-protocol.md`
  Loop 2 protocol.
- TSIR Loop 2 — nightly parity canary increment:
  `bench/gates/nightly_tsir_parity_canary.py` now runs all six bootstrap
  manifest lowering fixtures through the parity CLI, validates the emitted v2
  receipts, checks that each receipt carries the expected lowering identity,
  and writes an advisory JSON report. The canary accepts today's honest
  `not_implemented` / `deferred` statuses and fails only on fixture coverage,
  schema, identity, or explicit parity-fail regressions; it does not promote
  the stub backend lanes to a green claim.
- TSIR Loop 2 — shard created by splitting `compiler-and-webgpu.md` on
  subdomain after it exceeded the 1200-line cap. Historical TSIR
  entries remain in `compiler-and-webgpu.md` until a deliberate
  migration sweep; new TSIR entries route here. Updated
  `docs/status.md` front door to list the new shard and left a cap
  notice at the top of `compiler-and-webgpu.md` pointing new TSIR
  traffic here. Cites `docs/loop-protocol.md` Loop 2 protocol
  (no-code subdomain-split increment). No runtime, test, or contract
  change.

<!-- entries below here were migrated from docs/status/compiler-and-webgpu.md on 2026-04-24. -->
<!-- They predate the tsir.md shard split (tick 8) and were written into compiler-and-webgpu.md before tsir.md existed. -->
<!-- Ordering within this block reflects their original top-to-bottom layout; commit log is authoritative for strict chronology. -->

- TSIR Loop 2 - portable backend skeleton increment: added deterministic
  source-hashed TSIR skeleton emitters for SPIR-V, MSL, and DXIL, backed by a
  shared contract-text serializer that includes the common serializer source in
  each backend emitter digest. The emitters serialize realization headers,
  residency, tiles, collectives, and reductions, and fail closed on realization
  rejections or target descriptor hash mismatches. They are non-executable
  backend contract emitters; real backend codegen remains deferred.
- TSIR Loop 2 — parity receipt lowering-identity increment:
  `bench/tools/doe_parity.py` now accepts a schema-validated
  `--manifest-lowering-entry` fixture and copies only the TSIR lowering
  identity digests into the parity receipt:
  `tsirSemanticDigest`, `tsirRealizationDigest`, `emitterDigest`, and
  `targetDescriptorCorrectnessHash`. The receipt schema is versioned to
  `schemaVersion=2` with an optional `loweringIdentity` object. This is still
  receipt metadata only: the reference and backend lanes remain
  `not_implemented`/`deferred`, and the CLI still exits nonzero unless real
  comparisons pass in a future increment.
- TSIR Loop 2 — rejection taxonomy cross-schema lockstep test: new
  `test_rejection_taxonomy_is_consistent_across_schemas` in
  `bench/tests/test_doe_parity.py` walks the four JSON schemas that carry
  the TSIR rejection enum (`doe-parity-receipt.schema.json`,
  `doe-tsir-semantic.schema.json`, `doe-tsir-realization.schema.json`,
  `doe-tsir-manifest-lowering.schema.json`) and asserts each one's enum
  set equals `doe_parity.REJECTION_REASONS`. Catches drift where someone
  renames or adds a reason in one schema and forgets another — the
  taxonomy is a single wire contract shared across all four artifacts
  plus the Python CLI. The Zig canonical enum at
  `runtime/zig/src/tsir/schema.zig::RejectionReason` is verified
  separately by the existing scaffold test "rejection taxonomy is
  exhaustive and enumerable". 16/16 parity CLI tests pass. Cites
  `docs/tsir-lowering-plan.md` Step 1 (rejection taxonomy) and
  `docs/loop-protocol.md` Loop 2 protocol. No runtime, schema, or
  fixture change.
- TSIR Loop 2 — bootstrap manifest fixture increment: added a source-hashed
  WebGPU-generic TSIR skeleton emitter so WebGPU and WSE-3 lowerings no longer
  share an emitter identity, added a Zig bootstrap manifest-input tool that
  lowers the pinned `fused_gemv`, `rms_norm`, and `gather` WGSL kernels through
  frontend + planner for both targets, and added
  `bench/tools/generate_tsir_manifest_fixtures.py` to pass those digests through
  the schema-backed manifest lowering builder. The committed
  `bench/fixtures/tsir-manifest-entries/*.json` fixtures cover the six Phase A
  kernel/target pairs and validate as `integrityExtensions.lowerings[]` rows.
  This is still compiler-contract evidence only; executable backend parity
  remains Loop 3.
- TSIR Loop 2 — emitter code digest increment: `emit_csl.zig` now exposes
  `emitterCodeDigest()` as SHA-256 over the mechanical CSL emitter source, and
  `digest.zig` has `computeWithEmitterDigest()` for callers that already hold
  a content-addressed emitter identity instead of a version string. The Phase A
  bootstrap pipeline test now feeds that source-backed digest into WebGPU and
  WSE-3 realizations and asserts the returned split digest preserves it
  verbatim. This removes the zero/placeholder emitter identity from the
  compiler-only bootstrap lowering path. Verified with
  `zig test test_suite_wgsl.zig --test-filter tsir`,
  `zig build test-wgsl`, and `git diff --check`.
- TSIR Loop 2 — Step 8 parity CLI scaffolding comment refresh:
  `bench/tools/doe_parity.py` scaffolding comments on
  `run_reference_interpreter` and `run_backend` were stale — they claimed
  the Zig oracle returns `NotImplemented` for every kernel, but the
  oracle now recognizes the three Phase A bootstrap families
  (`fused_gemv`, `gather`, `rms_norm`) across `{f32, f16, bf16}` with
  `strict_ordered` + `associative_allowed` reductions plus
  `literal_f32` / `uniform_field` epsilon. Updated comments to name
  what the oracle covers, name the remaining CLI subprocess harness
  that is the real gap, and name the backend-lane gaps (TSIR-to-WGSL
  re-emission for WebGPU; TSIR-to-CSL executable kernel bodies for
  simfabric, since `runtime/zig/src/tsir/emit_csl.zig` is a skeleton
  contract emitter only). Doc-only; all 15 `bench/tests/test_doe_parity.py`
  cases still pass. The CLI's `not_implemented` stub contract is
  intentionally preserved — wiring real subprocess calls is a distinct
  Loop 2 wedge that has not landed. Cites
  `docs/tsir-lowering-plan.md` Step 8 and `docs/loop-protocol.md`
  Loop 2 protocol.
- TSIR Loop 2 — Phase A bootstrap pipeline identity increment:
  added a compiler-only pipeline test that lowers the pinned
  `fused_gemv`, `rms_norm`, and `gather` WGSL bootstrap kernels through
  Doe IR → TSIR semantic → WebGPU-generic and WSE-3 realization planning →
  semantic/realization digest computation. The test requires clean semantic
  and realization rejection lists, stable repeated digests, shared semantic
  digest across targets, and target-distinct realization digests. To make that
  honest, the frontend now traces reduction accumulator dependencies through
  scalar-tail aliases, so RMSNorm's `sum_sq -> mean_sq -> inv_rms -> output`
  path no longer emits an unresolved-writeback rejection, and gather hinting
  follows bounded local aliases initialized from indexed buffer reads. Target
  descriptors now declare a correctness-affecting runtime-sized binding policy:
  `webgpu-generic` uses `host_copied`, while `wse3` requires loader-backed
  `fabric_streamed` residency. Verified with
  `zig test test_suite_wgsl.zig --test-filter tsir`,
  `zig build test-wgsl`, and `git diff --check`.
- TSIR Loop 2 — Step 1 oracle / RMSNorm uniform-epsilon increment:
  `body.rmsNorm.epsilon` now carries `bindingIndex` and `byteOffset` in
  both Zig and JSON schema, canonical semantic digests include those fields,
  and the WGSL frontend derives binding `3` / byte offset `4` for the
  bootstrap `uniform:u.eps` struct field. The reference interpreter now
  consumes read-only inputs by semantic binding order and executes RMSNorm
  with explicit uniform epsilon bytes; missing uniform input, mismatched
  path/binding, NaN/Inf, or malformed offsets still fall through to
  `NotImplemented`, so there is no hidden epsilon default. The bootstrap
  RMSNorm semantic fixture and notes now include the `u` binding. This same
  increment also extends the fused GEMV oracle to honor
  `associative_allowed` reductions only when the realization declares a
  matching reduction tree shape, with focused coverage for binomial fold
  behavior. Verified with
  `zig test test_suite_wgsl.zig --test-filter tsir`,
  `zig build test-wgsl`,
  `env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest bench.tests.test_config_schemas`,
  and `git diff --check`.
- TSIR Loop 2 — Step 1 oracle dtype coverage for `rms_norm`: two
  focused tests in `runtime/zig/src/tsir/reference_interpreter.zig`
  exercise the f16 and bf16 upcast/downcast paths for the
  literal-epsilon recognizer committed in `39707259e`. Test values use
  input=[2,2] and scale=[3,4] so `mean_sq=4.0` and `inv_rms=0.5` are
  exactly representable and the f32 accumulator + dtype downcast
  produces bit-exact output={3,4} — this validates the dtype plumbing,
  not `@sqrt` rounding. `uniform_field` epsilon still falls through
  until TSIR input plumbing lands for uniform scalars. Mirrors the
  dtype-closure wedge landed for `fused_gemv`/`gather` earlier today.
  `zig build test-wgsl` passes. No recognizer or schema change. Cites
  `docs/tsir-lowering-plan.md` Step 1 and `docs/loop-protocol.md`
  Loop 2 protocol (stop-until-green; same step, same wedge shape).
  After this tick all three Phase A bootstrap families (fused_gemv,
  gather, rms_norm) have positive oracle coverage on every declared
  Phase A dtype {f32, f16, bf16}.
- TSIR Loop 2 — Step 1 oracle increment for literal-epsilon `rms_norm`:
  new `tryRmsNorm` dispatch path in
  `runtime/zig/src/tsir/reference_interpreter.zig` consumes the
  `SemanticBody.rms_norm` contract, validates input/scale/output roles,
  hidden/reduction axes, strict f32 sum-of-squares reduction semantics,
  and equal {f32, f16, bf16} dtypes, then computes
  `output[d] = input[d] * rsqrt(mean(input^2) + epsilon) * scale[d]`.
  The executable wedge is deliberately limited to `literal_f32` epsilon;
  `uniform_field` epsilon still falls through to `NotImplemented` until
  scalar/uniform value plumbing is represented in TSIR inputs. Focused
  tests cover the positive f32 literal-epsilon path plus the uniform-eps
  fail-closed path. Verified with
  `zig test test_suite_wgsl.zig --test-filter tsir` and
  `zig build test-wgsl`.
- TSIR Loop 2 — RMSNorm semantic-body contract: `SemanticBody` now carries
  an optional `rms_norm` payload, mirrored in
  `config/doe-tsir-semantic.schema.json` as `body.rmsNorm` and required
  when `body.op == "rms_norm"`. The contract names the Phase A formula
  (`sum_squares_mean_epsilon_rsqrt_scale`), epsilon source
  (`uniform:u.eps` or a future literal), hidden extent axis, and
  `intermediate_scalar` reduction target so RMSNorm execution is no longer
  inferred from operand roles alone. `digest.zig` includes the payload in
  canonical semantic bytes only when present, preserving non-RMS body
  digests. The WGSL frontend attaches the payload to the bootstrap
  RMSNorm shape while keeping the coarse family hint at `.reduction`;
  `runtime/zig/tests/tsir/bootstrap/rms_norm.tsir-semantic.json` and notes
  were updated to record the contract. This is not an RMSNorm oracle pass:
  executable node-level square / scalar-tail / rsqrt / post-scale dataflow
  is still rejected until a later increment. Verified with
  `zig test test_suite_wgsl.zig --test-filter tsir`,
  `zig build test-wgsl`, and
  `python3 -m unittest bench.tests.test_config_schemas`.
- TSIR Loop 2 — Step 1 oracle dtype coverage for `fused_gemv` +
  `gather`: four focused tests added in
  `runtime/zig/src/tsir/reference_interpreter.zig` exercising the
  f16 and bf16 upcast/downcast paths through `readF32FromBytes` /
  `writeF32AsElem`. fused_gemv f16/bf16 cases use `[1,2]×[2,2]` with
  exactly-representable small integers so the f32 accumulator plus
  declared-output-dtype downcast produces a bit-exact expected value.
  gather f16/bf16 cases confirm row-copy preserves byte-level identity
  through the declared element dtype. Tick 1 already wired the
  recognizers to admit all three Phase A dtypes; this tick closes the
  declared contract by covering the two dtypes tick 1 left untested.
  `zig build test-wgsl` passes. No recognizer or schema change. Cites
  `docs/tsir-lowering-plan.md` Step 1 and `docs/loop-protocol.md`
  Loop 2 protocol (stop-until-green wedge on the existing step). The
  `rms_norm` bootstrap family remains blocked on Step 3 schema
  extensions per its own `notes.md`; oracle correctly returns
  `NotImplemented` for it under the current semantic, which is the
  fail-closed behavior plan §5 rule 4 requires.
- TSIR Loop 2 — Step 1 oracle increment for `gather`: new
  `tryGather` dispatch path in
  `runtime/zig/src/tsir/reference_interpreter.zig`. Recognizer matches
  `SemanticBody{op=gather}` with indices/table/output binding roles and
  token/hidden axis roles. It requires `u32` indices shaped `[T]`, a
  table shaped `[V, H]`, output shaped `[T, H]`, table/output dtype
  equality over {f32, f16, bf16}, row-major axes `[token, hidden]`, no
  reductions, and no collectives. Computation copies
  `table[indices[t], h]` into `output[t, h]`; out-of-range indices fall
  through to `NotImplemented` rather than clamping or wrapping. Focused
  tests cover a positive f32 row-copy case with SHA-256 reference hash
  validation and a negative out-of-range rejection case. `zig test
  test_suite_wgsl.zig --test-filter tsir` passes. RMSNorm remains
  intentionally unexecuted until TSIR body semantics declare epsilon,
  sum-of-squares formula, and intermediate reduction target semantics.
- TSIR Loop 2 — Step 1 oracle increment for `fused_gemv`: new
  `tryFusedGemv` dispatch path in
  `runtime/zig/src/tsir/reference_interpreter.zig`. Recognizer matches
  the `SemanticBody{op=fused_gemv}` shape declared by the bootstrap
  catalog fixture at
  `runtime/zig/tests/tsir/bootstrap/fused_gemv.tsir-semantic.json` —
  three bindings with matrix/vector/output roles, two axes with
  output/reduction roles, one sum reduction with f32 accumulation and
  `strict_ordered` associativity, equal dtype across {f32, f16, bf16}
  on all three bindings, `[M, K]` matrix + `[K]` vector + `[M]` output,
  row-major axes `[output, reduction]`. Computation is the left-fold
  `y[i] = Σ_k W[i, k] · x[k]` in an f32 accumulator, written through
  the declared output dtype. `associative_allowed` with a declared
  tree shape falls through (future wedge). Two focused tests in
  `reference_interpreter.zig`: positive 2×3 f32 case validating the
  exact dot-product values and the SHA-256 reference hash, plus a
  negative fall-through test that leaves `SemanticBody.op` at
  `.unknown` and confirms `NotImplemented`. `zig build test-wgsl`
  passes. Cites `docs/tsir-lowering-plan.md` Step 1 + Step 1.5 and
  `docs/loop-protocol.md` Loop 2 protocol. No schema change; the
  recognizer consumes the already-landed `SemanticBody`.
- TSIR Loop 2 — mechanical CSL skeleton emitter: new
  `runtime/zig/src/tsir/emit_csl.zig` exposes
  `tsir.emit_csl.emit(...)` for checked realization artifacts and
  `tsir.emit_csl.emitFunction(...)` for a direct `RealizationFunction`
  plus target descriptor. The emitter validates the descriptor hash,
  refuses realization-level rejections, and writes deterministic
  `layout.csl` / `pe_program.csl` skeleton contract text that records
  PE grid, tile factors, residency decisions, collectives, reductions,
  target descriptor hash, and emitter params. This is contract
  serialization only: it does not inspect kernel-family hints and does
  not emit executable kernel bodies yet. Focused coverage lives in
  `runtime/zig/tests/wgsl/tsir_emit_csl_test.zig`; `zig build
  test-wgsl` passes.
- TSIR manifest/AOT binding helper: `bench/tools/tsir_manifest_lowering.py`
  now builds and validates a schema-backed manifest lowering entry from
  `tsirSemanticDigest`, `tsirRealizationDigest`, `emitterDigest`,
  `targetDescriptorCorrectnessHash`, frontend/compiler pins, backend,
  kernel ref, exactness, and rejection taxonomy inputs. The helper rejects
  malformed lowercase-hex digests, duplicate rejection reasons, unsupported
  exactness/taxonomy values, and schema-invalid entries before emitting
  canonical JSON or a `manifestLoweringEntryDigest`. The
  `config/doe-tsir-manifest-lowering.schema.json` exactness contract now
  fail-closes per class and requires unique algorithm invariants and rejection
  reasons. Focused coverage lives in
  `bench/tests/test_tsir_manifest_lowering.py`. This is a bench-tool binding
  increment only: no runtime Zig, backend execution, or manifest loader path
  changed.
- TSIR Step 5/6 — first executable planner increment: new
  `runtime/zig/src/tsir/planner.zig` exports
  `tsir.planner.planRealization(allocator, semantic, descriptor, options)`.
  The pass emits deterministic `RealizationFunction` records from TSIR
  semantic plus a target descriptor: first-fit tile factors, WebGPU/WSE-3
  PE-grid choice, per-binding residency decisions, target descriptor hashes,
  reduction tree choices for `associative_allowed` reductions, native
  collective realization nodes, and typed rejection entries for PE-budget,
  target-dtype, and missing-collective failures. Loader-owned streaming is an
  explicit option (`LoaderCapabilities.fabric_streaming` /
  `max_stream_chunk_bytes`), so `fabric_streamed` is never selected as a hidden
  fallback when packaging has not declared it. Focused coverage lives in
  `runtime/zig/tests/wgsl/tsir_planner_test.zig`; `zig build test-wgsl`
  passes.
- TSIR parity CLI schema gate: `bench/tools/doe_parity.py` now validates the
  generated receipt dictionary against
  `config/doe-parity-receipt.schema.json` before writing it. Invalid receipt
  state (for example an unknown comparison status) fails closed with a schema
  path, and `bench/tests/test_doe_parity.py` now locks both a valid generated
  receipt and the invalid-status rejection. This does not add backend
  execution, oracle execution, manifest binding, or a parity pass claim.
- Loop 2 plan doc-only update: `docs/tsir-lowering-plan.md` now splits Loop 2
  TSIR machinery into explicit compiler-only subloops while preserving the
  one-committable-increment rule, rollout order, and Loop 2 / Loop 3 boundary.
  This is process documentation only: no TSIR schema, compiler output, parity
  receipt, Cerebras SDK run, or Doppler manifest binding changed.

## Scope

Use this shard for:

- TSIR schema + digest contract changes
- TSIR reference interpreter (oracle) coverage
- TSIR frontend lowering (WGSL IR → TSIR semantic)
- TSIR planner (residency, tile factors, PE grid, realization)
- TSIR mechanical backend emitters (CSL, WebGPU, MSL, HLSL/DXIL, SPIR-V)
- TSIR manifest-lowering identity contract + fixtures
- Loop 2 stop-until-green iteration status
- Loop 3 per-kernel-family parity closure status

Use `compiler-and-webgpu.md` for:

- Doe WGSL shader compiler (non-TSIR paths: Metal, Vulkan, D3D12)
- WebGPU runtime behavior outside TSIR lowering
- Robustness / validator / conformance work
