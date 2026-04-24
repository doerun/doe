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
