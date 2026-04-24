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
cap once the TSIR Phase A wedges started landing. Historical TSIR entries
remain in `compiler-and-webgpu.md` until a deliberate migration sweep
moves them here; new TSIR entries go here going forward.

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
| Step 6 collectives | (embedded in planner + frontend) | Bootstrap families have no collectives; no dedicated pass file yet. Required before attention (Phase B). |
| Step 7 emitter | `runtime/zig/src/tsir/emit_{csl,webgpu,msl,dxil,spir_v,text_skeleton}.zig` | Skeleton emitters for five backends with source-hashed `emitterCodeDigest()` pairwise-distinct by test. **Executable kernel bodies not yet emitted** — skeleton contracts only. |
| Step 8 parity CLI | `bench/tools/doe_parity.py` + `bench/gates/nightly_tsir_parity_canary.py` | Stub contract with lowering-identity binding. Reference interpreter and backend lanes return `not_implemented` / `deferred`; **subprocess harness to the Zig oracle unlanded**. |
| Step 9 family rewrites | — | **0/3 Loop 3 parity receipts.** Directory `reports/parity/` does not yet exist. Gated on Step 7 executable bodies + Step 8 subprocess harness. |
| Step 10 manifest binding | `bench/tools/tsir_manifest_lowering.py` + `bench/fixtures/tsir-manifest-entries/*.json` | Schema, builder, six bootstrap fixtures; receipt ↔ fixture identity lockstep + fixture version + descriptor uniformity locked by test. |
| Step 11 AOT convert | — | Unlanded; cache-key design pending. |
| Step 12 rollout | — | Unlanded. |

Gates protecting Phase A artifacts:

- `bench/gates/doe_private_strategy_leak_gate.py` — private-strategy
  leak guard (Doe docs must not contain upstream-repo path or
  competitive-framing patterns).
- `runtime/zig/tools/check_line_limits.py` — 999-line Zig source cap;
  three TSIR modules allowlisted with tracked sharding follow-ups.
- `bench/tests/test_doc_link_coverage.py` — in-repo markdown link
  integrity.
- `test_canary_receipts_carry_fixture_lowering_identity` — receipt ↔
  fixture identity.
- `test_bootstrap_fixtures_share_version_and_descriptor_identity` —
  fixture set coherence.
- `test_rejection_taxonomy_is_consistent_across_schemas` — rejection
  taxonomy lockstep across the four JSON schemas + Python CLI.
- Zig `test "tsir emitter code digests are pairwise distinct across
  all five backends"` — manifest-binding disambiguation.

The missing path to proof 1 — in priority order: executable kernel
bodies in a backend emitter (Step 7), parity CLI subprocess harness to
the Zig oracle (Step 8), first Loop 3 receipt for fused_gemv against
both `webgpu-generic` and `wse3` (Step 9 iter 1), manifest binding of
that receipt into a Doppler manifest (Step 10). Each is a multi-day
wedge; the Loop 2 hygiene work through today has made every one of
them safer to attempt.

## 2026-04-24

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
