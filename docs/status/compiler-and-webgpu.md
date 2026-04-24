# Doe status: compiler and WebGPU

This is a live topical status shard.

- Add new entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under `docs/status/archive/`.

**Cap notice:** this shard is currently over the 1200-line cap. 2026-04-24
TSIR entries were migrated to [`tsir.md`](./tsir.md) in a later tick;
older TSIR history (2026-04-23 and earlier) remains below pending a
dedicated archive migration. **New TSIR entries go in
[`tsir.md`](./tsir.md).** New non-TSIR entries (shader compiler non-TSIR
paths, WebGPU runtime, robustness) still go here.

## 2026-04-23

- TSIR Step 4 — thirty-ninth increment: `.fused_gemv`
  promotion now uses structural matrix-access evidence instead
  of the temporary same-bound exclusion from increment 37. The
  family classifier moved from `frontend.zig` into
  `runtime/zig/src/tsir/family_hint.zig`; the frontend now
  delegates to that shard. A reduction promotes to
  `.fused_gemv` only when it has exactly 2 axes, one sum
  reduction on axis 1, a non-trivial outer bound, and an
  indexed global load whose expression tree references both
  the outer and inner axis locals (for example `W[i * K + k]`
  or `W[i][k]`). RMSNorm no longer depends on the fragile
  "same upper bound" guard: its split accesses (`input[i]`,
  then `input[d]` / `weight[d]`) do not satisfy the matrix
  access predicate, so it stays on `.reduction` until a real
  `.rms_norm` detector lands. The focused GEMV unit now uses
  the actual matrix access pattern, and `zig build test-wgsl`
  passes.
- TSIR Step 4 — thirty-eighth increment: dispatch-axis bound
  detection now scans past interleaved `let` decls and
  early-return guards for OTHER dispatch axes to find the
  matching guard. New helper `scanForDispatchGuard(allocator,
  module, function, body_range, start_pos, dispatch_local)`
  in `runtime/zig/src/tsir/frontend.zig` walks forward in a
  block starting from the position after a dispatch local's
  decl; skips through subsequent local_decls; at each if it
  tries `extractDispatchBoundFromGuard` and returns on match;
  if the if is a bare early-return (no else, then-body is a
  single-return) for some OTHER local, skips past and keeps
  scanning; anything else stops the scan (arithmetic assigns,
  loops, non-guard ifs) and the caller falls back to the
  placeholder. Why the skip-safe predicate matters: a
  multi-axis dispatch kernel like gather has
  `let t; let h; if (t >= ...) return; if (h >= ...) return;`
  where the first decl's matching guard is TWO positions
  ahead, and the second decl's matching guard is also two
  positions ahead past an unrelated guard. The scan handles
  both. Updated the gather bootstrap integration test to
  assert the real resolved bounds:
  `"uniform:u.num_tokens"` for the `t` axis and
  `"uniform:u.hidden"` for the `h` axis. All three Phase A
  bootstrap kernels now lower to TSIR semantic with real
  bounds — no placeholder strings, no spurious rejections.
  With this, Step 4's frontend is green for Phase A purposes:
  axes, bindings, reductions, collectives, family hints, and
  typed rejections all populate correctly for the bootstrap
  catalog. Remaining Step 4 plan bullets (SSA normalization,
  full access-stride summary analysis) are deferred as
  later-phase hardening; they don't block Step 5 residency
  planning for the bootstrap kernels. `zig build test-wgsl`
  reports 901/901 tests passed.
- TSIR Step 4 — thirty-seventh increment: two-part close-out
  for the frontend pass.
  (1) Tightened the `.fused_gemv` heuristic in
  `runtime/zig/src/tsir/frontend.zig` to require
  `axes[0].upper_bound != axes[1].upper_bound`. The previous
  rule over-matched: any 2-axis kernel with a reduction on
  axis 1 and a non-trivial outer bound got tagged
  `.fused_gemv`. RMSNorm has the same shape but BOTH axes are
  bounded by the same `u.hidden_size`, which the tightened
  rule now rejects as a GEMV candidate — it stays on
  `.reduction`. The catch: when the planner eventually lands
  `.rms_norm` / `.layer_norm` detection, the distinguishing
  signal (same-upper-bound pattern + post-reduction normalize
  step) gets added as a positive refinement; the current
  coarse fallback is the honest intermediate.
  (2) Added three bootstrap integration tests that load
  `runtime/zig/tests/tsir/bootstrap/{fused_gemv,rms_norm,gather}.wgsl`
  via `@embedFile` and lock exactly what the frontend produces
  for each. fused_gemv: 2 axes `[i, k]` with bounds
  `uniform:u.M` / `uniform:u.K`, one sum reduction on axis 1,
  hint `.fused_gemv`, zero rejections. rms_norm: 2 axes `[d,
  i]` with bounds both `uniform:u.hidden_size`, one sum
  reduction on axis 1, hint `.reduction` (coarse fallback
  because both upper bounds match). gather: 2 axes `[t, h]`
  with placeholder upper bounds `dispatch.y` / `dispatch.x`
  (the guards aren't adjacent to each let; a later
  multi-axis-guard-scan increment tightens these to the real
  bounds), zero reductions. The three tests are the
  pre-requisite for declaring Step 4 green-enough for Phase A:
  the canonical inputs lower end-to-end through the frontend
  and produce stable, auditable TSIR. `zig build test-wgsl`
  reports 901/901 tests passed (up from 898).
- TSIR Step 4 — thirty-sixth increment: family hint now
  refines `.reduction` → `.fused_gemv` for the canonical
  two-axis shape: exactly 2 axes, 1 reduction on axis 1
  (inner), and the outer axis's upper bound is non-trivial
  (dispatch / uniform / override / const prefix). New
  predicate `isNontrivialBoundString(s)` in
  `runtime/zig/src/tsir/frontend.zig` matches the leading
  prefix set so `"dispatch.x"`, `"uniform:u.M"`,
  `"override:N"`, `"override@id:5"`, and `"const:K"` all
  qualify, while fixed literals like `"4"` stay coarse.
  Guard rationale: a kernel with fixed literal bounds is
  technically a matmul, but its compile-time-constant outer
  extent doesn't benefit from the GEMV-specific planner
  strategy (streaming weights, row-splitting), so the
  coarse hint is more honest. New tests: "frontend refines
  reduction hint to fused_gemv for canonical 2-axis shape"
  drives the full fused-GEMV WGSL (dispatch-grid outer,
  uniform-bounded inner) and asserts
  `family_hint == .fused_gemv`; "frontend keeps reduction
  hint for fixed-literal outer bound" drives the same
  structural shape with `i < 4u` and asserts the hint stays
  `.reduction`. `zig build test-wgsl` reports 898/898 tests
  passed.
- TSIR Step 4 — thirty-fifth increment: family-hint inference
  now distinguishes `.gather` from `.elementwise`. New helpers
  `hasIndirectBufferAccess(function)` and
  `indexExprContainsBufferIndex(function, expr_id)` in
  `runtime/zig/src/tsir/frontend.zig` walk `function.exprs`
  looking for any `.index` expression whose index-field
  expression tree contains another `.index` node. Matching
  that shape — the canonical data-dependent buffer load
  `input[indices[i]]` — promotes the family hint from
  `.elementwise` to `.gather`. `inferFamilyHint`'s signature
  now also takes the function pointer so the expression walk
  is reachable. Critical no-false-positive property: linear
  index combinations that happen to include uniform scalar
  loads (`W[i * K + k]` where `K` is a uniform) do NOT
  trigger because a uniform load's IR shape is
  `load(member(load(global_ref(...)), field))` — no nested
  `.index`. Fused-GEMV / matmul / strided-access kernels
  therefore stay correctly tagged `.reduction` (or
  `.elementwise` when no reduction exists), never misrouted
  to `.gather`. The helper lists the `.else` fall-through
  cases explicitly so other expression shapes (global_ref,
  param_ref, local_ref, int_lit, etc.) return false without
  ambiguity. Why it matters: residency planning treats
  gather kernels very differently from elementwise — a
  gather's source buffer needs replicated or streamed
  residency because every lane may read any element, while
  an elementwise kernel can slice. The hint is a tiebreaker
  per the plan's rule, but for Phase A's gather bootstrap
  kernel, the planner's correctness-first heuristic benefits
  from the right hint being present. New test "frontend
  infers gather family hint from indirect buffer access"
  drives `output[i] = input[indices[i]]` and asserts
  `family_hint == .gather`. All prior elementwise and
  reduction tests continue to pass. `zig build test-wgsl`
  reports 896/896 tests passed.
- TSIR Step 4 — thirty-fourth increment: `detectReductionOp`'s
  min/max intrinsic-call branch now matches commutative-swapped
  argument order. Iteration 59 only recognized
  `acc = max(acc, x)` with the accumulator at `args[0]`; the
  equally-valid `acc = max(x, acc)` with the accumulator at
  `args[1]` fell through to `null`. Min and max are
  commutative at the semantic level, so either argument
  position should map to the same `.max` / `.min`
  `ReductionOp`. The detector now iterates all of the call's
  args, returns the matching op when any of them is a load of
  the accumulator, and requires `args.len >= 2` so single-arg
  name collisions (`max(x)` would be a user-defined or
  unsupported intrinsic) don't spuriously match. Keeping
  coverage here symmetric matters because real WGSL kernels
  don't canonicalize argument order — some authors write
  `acc = max(acc, ...)` (acc-first), others write
  `acc = max(..., acc)` (value-first, treating acc as the
  "running best"). Without commutative-swap handling the
  frontend silently dropped the value-first shape. New test
  "frontend recovers min and max reductions with
  commutative-swapped arg order" drives both
  `hi = max(input[i], hi)` and `lo = min(input[j], lo)`
  kernels and asserts the same `.max` / `.min` recovery that
  iteration 59's acc-first test produces. `zig build
  test-wgsl` reports 895/895 tests passed.
- TSIR Step 4 — thirty-third increment: `detectReductionOp`
  now recognizes the call-based self-update patterns
  `acc = max(acc, x)` and `acc = min(acc, x)`. Before this
  increment only additive (`.add` / `.sub`) and multiplicative
  (`.mul`) compound and expanded shapes were detected;
  kernels that reduce via WGSL's `max` / `min` intrinsics
  (softmax's numerical-stability max-reduce, clamp
  reductions, streaming-max loops) fell through silently to
  `null` and the for-loop's body scan moved on without
  emitting a `ReductionRegion`. The detector's new branch
  checks for an `.assign` whose rhs is a builtin `.call`
  whose first arg is `load(local_ref(acc_local))` and whose
  name is `"max"` or `"min"`; on match it returns the
  matching `ReductionOp` (`.max` / `.min`). The schema's
  `ReductionOp` enum already had these variants — the
  frontend just wasn't surfacing them. Second-arg structural
  verification is intentionally skipped: a reduction region's
  contract describes WHAT the reduction is, not what per-
  iteration operand shape it consumes; those details belong
  to the realization pass's expression lowering. Why it
  matters: any attention kernel that performs softmax
  renormalization runs an explicit `max` reduction first
  (subtract the max to stabilize exponentiation). Without
  this detection, those reduction regions were invisible —
  the frontend saw the for-loop, emitted an axis, found no
  reduction, and tagged the kernel as `.elementwise`. Now
  it correctly surfaces the max-reduction region, attributes
  the right target binding, and hints the family correctly
  (`.reduction`). New test "frontend recovers min and max
  reductions from builtin call self-updates" drives both
  shapes in one kernel and asserts two reductions with
  `.max` and `.min` ops respectively. `zig build test-wgsl`
  reports 894/894 tests passed.
- TSIR Step 4 — thirty-second increment: decreasing for-loops
  now produce a typed rejection instead of a half-broken axis
  with placeholder upper bound + `"-1"` step. New helper
  `detectStepSign(function, cont, induction_local)` in
  `runtime/zig/src/tsir/frontend.zig` classifies the
  `continuing` clause as `positive` / `negative` / `unknown`
  without allocating. All three walkers (`walkAxesInStmt`,
  `walkReductionsInStmt`, `walkCollectivesInStmt`) now guard
  their for-loop arm with this check: when the sign is
  `.negative`, the walker SKIPS emitting an axis / bumping
  axis_counter / pushing on axis_stack but still descends
  into the body so nested valid for-loops or subgroup calls
  inside a decreasing outer loop still get recovered. The
  three walkers stay in lockstep so axis indices across axes,
  reductions, and collectives always refer to the same slice
  positions. `walkRejectionsInStmt` gets a new branch in the
  `.loop_` case that emits
  `reason = .tsir_source_not_affine` with detail
  `"decreasing for-loop does not fit half-open iteration
  model"` at the loop's node_path. Taxonomy choice:
  `tsir_source_not_affine` fits better than
  `tsir_dependence_unanalyzable` here — the loop IS
  analyzable, it just doesn't fit the forward-affine
  iteration model TSIR's `[lower_bound, upper_bound)` axis
  encodes. A later schema increment could either flip direction
  explicitly via a new axis field or keep rejecting; for now
  this is fail-closed and honest. New test "frontend rejects
  decreasing for-loops instead of emitting a mismatched axis"
  drives `for (var i: u32 = 10u; i > 0u; i = i - 1u)` and
  asserts `axes.len == 0`, one rejection with the exact
  reason / node_path / detail. `zig build test-wgsl` reports
  893/893 tests passed.
- TSIR Step 4 — thirty-first increment: override globals
  carrying an `@id(N)` pipeline-constant attribute now emit
  `"override@id:<N>"` in symbolic bound strings instead of
  `"override:<name>"`. New helper
  `writeOverrideOrConstName(allocator, g)` in
  `runtime/zig/src/tsir/frontend.zig` centralizes the
  prefix-picking logic that was previously inlined at four
  callsites (`extractSymbolicUpperBound`, `extractInitBound`,
  `extractStep`, `extractDispatchBoundFromGuard`). The helper
  prefers the `@id` when present, falls back to
  `"override:<name>"` otherwise, and handles `const_` globals
  as `"const:<name>"` with no id case (WGSL `const` doesn't
  have `@id`). Each callsite simplified to a single helper
  call + concatenation with its own prefix / suffix (sign for
  step, `+1` for `<=` / `>=`). Why it matters: WGSL overrides
  are rebindable at pipeline creation; using the name as
  identity means renaming a semantically-unchanged override
  forks the axis-digest for no real reason, while the `@id`
  is precisely the stable pipeline identity the WGSL spec
  defines. Overrides without `@id` keep using names (there's
  nothing else to hash against them), so existing tests and
  existing kernels in the bootstrap catalog are unaffected.
  New test "frontend resolves override with @id to
  override@id:N form" drives `@id(7) override trip_count` and
  asserts `upper_bound == "override@id:7"`. All prior override
  tests continue to pass because their fixtures don't declare
  `@id`. `zig build test-wgsl` reports 892/892 tests passed.
- TSIR Step 4 — thirtieth increment: `resolveTargetBinding`
  now accepts writebacks whose rhs is an arithmetic expression
  containing an accumulator load, not just a pure `load(alias)`.
  New helper `containsAliasLoad(function, expr_id, aliases)` in
  `runtime/zig/src/tsir/frontend.zig` recursively walks
  `load` / `unary` / `binary` / `index` / `member` / `construct` /
  `call` expression trees; returns true when any `load(local_ref(X))`
  where X is in the alias set appears in the tree. The assign
  case in `resolveTargetBinding` now just calls this predicate
  instead of matching the direct `load(alias)` shape. Attribution
  stays on the final writeback's binding: the reduction produces
  acc, the epilogue shapes it (by `* scale`, `+ bias`, `rsqrt`,
  etc.), and the binding holds the shaped result — downstream
  planning still correctly identifies which binding receives the
  reduction's output. Why it matters: real Phase A kernels have
  canonical post-reduction epilogues. RMSNorm ends with
  `output[i] = input[i] * rsqrt(acc / N)`; fused GEMV with bias
  ends with `output[i] = acc + bias[i]`; attention's scale step
  ends with `output[i] = acc * inv_sqrt_dk`. Before this
  increment, every one of these wrote through a binary rhs and
  produced a spurious `tsir_dependence_unanalyzable` rejection
  despite being the most common real-world shape. Now the
  resolver walks them. All prior writeback tests continue to
  pass because `containsAliasLoad` returns true for pure
  `load(alias)` rhs as well. New test "frontend accepts rhs-
  binary writebacks that contain an accumulator load" drives
  `output[0] = acc * scale` and asserts `target_binding == 1`
  with zero rejections. `zig build test-wgsl` reports 891/891
  tests passed.
- TSIR Step 4 — twenty-ninth increment: dispatch-axis
  `upper_bound` now picks up the real bound from the
  canonical `if (i >= M) return;` early-return guard that
  immediately follows the gid local_decl. New helper
  `extractDispatchBoundFromGuard(allocator, module, function,
  guard_stmt_id, dispatch_local)` in
  `runtime/zig/src/tsir/frontend.zig` checks that the next
  statement is an `if` with no else whose then-body is a
  bare / single-stmt-block return and whose cond is
  `load(local_ref(dispatch_local)) (>|>=) <bound>`. The bound
  expression goes through the same literal / uniform-struct /
  override / const resolution ladder the for-loop bound
  extractors use. Semantic mapping: early-return-if-true
  means the VALID range is the complement of the guard —
  `i >= M` maps to exclusive upper `M` (no suffix), `i > M`
  maps to exclusive upper `M + 1` (suffix `"+1"`), which is
  the opposite suffix convention from the for-loop's
  `i <= M` case where the loop runs WHILE the cond is
  true. The detector is narrow by design: any guard with an
  else branch, multi-statement then body, or non-canonical
  cond shape keeps the `"dispatch.x"` placeholder so the
  frontend never invents a bound it can't see. Emission
  structure: the axis-walker `.local_decl` case moved to
  the block case so it has access to the next sibling
  statement; reduction and collective walkers still detect
  the pattern and bump their `axis_counter` via their own
  `.local_decl` cases. Iteration 54's test updated to
  assert `"uniform:u.M"` instead of `"dispatch.x"` now that
  the guard is detected. New test "frontend keeps
  dispatch.x placeholder when no early-return guard
  follows the gid decl" locks the honest-fallback path for
  kernels without a bound guard. Why it matters: the
  canonical GEMV shape (fused_gemv.wgsl in the bootstrap
  catalog) now produces an axes slice where the outer `i`
  axis has `upper_bound = "uniform:u.M"`, identical in
  shape to the hand-sketched expected TSIR semantic. The
  frontend's raw output now closely matches the Phase A
  bootstrap oracle for at least the outer-axis bounds of
  dispatch-scoped kernels. `zig build test-wgsl` reports
  890/890 tests passed.
- TSIR Step 4 — twenty-eighth increment: the frontend now
  emits a dispatch-grid `IterationAxis` for locals shaped
  `let i = gid.x|.y|.z` when the referenced parameter has
  `@builtin(global_invocation_id)`. New helper
  `tryExtractDispatchAxisLetter(function, init)` in
  `runtime/zig/src/tsir/frontend.zig` walks the initializer
  through any leading `.load` wrapper (single-component
  vector swizzles are ref-category in sema and get wrapped
  by `lower_value_expr`), matches a `.member` expression,
  then walks the member's base through more loads to a
  `.param_ref`; the param's `io.builtin` is checked to
  confirm it's `global_invocation_id`. The member's field
  name (`"x"`, `"y"`, `"z"`) becomes the dispatch-axis
  letter. All three walkers (`walkAxesInStmt`,
  `walkReductionsInStmt`, `walkCollectivesInStmt`) now
  handle the matching `local_decl` pattern — the axis
  walker emits the new axis; the reduction and collective
  walkers only increment their `axis_counter` to stay in
  lockstep with the axes slice. Why this coordination
  matters: if only the axis walker changed, a canonical GEMV
  shape (`let i = gid.x; for k { acc += ... }`) would put
  `[i_dispatch, k_loop]` in axes but the reduction walker
  would attribute the inner reduction to `axis = 0` (the
  dispatch axis) rather than `axis = 1` (the for-loop axis).
  The counter sync keeps attribution honest. Dispatch-axis
  `upper_bound` is a placeholder `"dispatch.x"` /
  `"dispatch.y"` / `"dispatch.z"` — the axis exists but the
  bound isn't yet extracted from the `if (i >= M) return;`
  guard pattern; that's a later increment. New test
  "frontend emits dispatch-grid axis from let i = gid.x with
  axis indices shifted in reductions" drives the canonical
  fused-GEMV shape (minus the bound check) and asserts two
  axes `[i, k]` with the reduction on `axis = 1`. All prior
  tests pass because no existing fixture used `gid`-based
  locals. `zig build test-wgsl` reports 889/889 tests
  passed.
- TSIR Step 4 — twenty-seventh increment: symbolic
  upper-bound resolver now also handles the mirror polarity
  forms `name > i` / `name >= i`, closing the gap the
  previous increment opened for the symbolic path.
  `extractSymbolicUpperBound` in
  `runtime/zig/src/tsir/frontend.zig` now dispatches through
  a polarity-aware switch: canonical (`<`, `<=`) keeps the
  induction on the lhs and the name expression on the rhs;
  mirror (`>`, `>=`) swaps — induction on rhs, name
  expression on lhs. Both paths produce an
  `effective_op` (`.less` or `.less_equal`) plus a
  `name_expr_id` so the subsequent uniform-struct / override /
  const emit logic stays polarity-agnostic. The exclusive-
  bound `+1` suffix for the `>=` / `<=` cases is derived
  from the `effective_op`, not the raw `binary.op`, so the
  canonical and mirror forms produce identical strings for
  identical semantics. Why it matters: Phase A bundles that
  spell out bounds as `count > i` instead of `i < count`
  previously collapsed to the `"upper_bound"` placeholder
  even though the literal-mirror increment caught the
  literal case; this closes the gap for symbolic bounds.
  The canonical and mirror forms now produce bit-identical
  axis digests. New test "frontend resolves override and
  uniform-field mirror-polarity bounds" drives
  `trip_count > i` (→ `"override:trip_count"`) and
  `params.count >= j` (→ `"uniform:params.count+1"`) and
  asserts both mirror-form strings match their canonical
  counterparts exactly. `zig build test-wgsl` reports
  888/888 tests passed.
- TSIR Step 4 — twenty-sixth increment: literal upper-bound
  extractor now also handles the mirror polarity forms
  `N > i` and `N >= i`, closing the last comparison-op gap
  for literal bounds. `extractLiteralUpperBound` in
  `runtime/zig/src/tsir/frontend.zig` now accepts four op
  shapes (`<`, `<=`, `>`, `>=`); the mirror `greater` /
  `greater_equal` cases check that the induction variable is
  on the rhs and the literal on the lhs, then translate to
  the equivalent `<` / `<=` op before returning the exclusive
  upper bound. `N > i` maps to `N`; `N >= i` maps to `N + 1`
  — same convention as the canonical forms. The extractor's
  internal match uses a nested-switch Shape struct so the
  polarity translation is explicit and auditable rather than
  buried in a chain of if-checks. Why it matters: some coding
  styles write `4u > i` or `size >= i` instead of the
  canonical `i < 4u` / `i <= size`; without this mirror
  handling those kernels collapsed to the `"upper_bound"`
  placeholder, producing a digest-wise-distinct kernel from
  the semantically-identical canonical form. They now produce
  the same axis string. Scope discipline: decreasing loops
  (`for (i = 10u; i > 0u; i--)` — real polarity flip with
  iteration running backward) stay on the placeholder path
  for now; handling those properly requires reversing the
  axis direction, not just flipping the comparison, and is
  a later increment that either emits a rejection or a new
  reverse-axis schema field. New test "frontend maps mirror
  polarity > and >= to equivalent upper bound" drives both
  `4u > i` (→ `"4"`) and `3u >= j` (→ `"4"`) and asserts
  both resolve to the same exclusive bound their canonical
  counterparts would. `zig build test-wgsl` reports 887/887
  tests passed.
- TSIR Step 4 — twenty-fifth increment: iteration-axis `step`
  now carries the real update from the for-loop's `continuing`
  clause instead of being hardcoded to `"1"`. New helper
  `extractStep(allocator, module, function, cont, induction_local)`
  in `runtime/zig/src/tsir/frontend.zig` recognizes the same
  two self-update shapes `detectReductionOp` uses for
  reductions, applied to the induction variable:
  compound-assign (`i += N` / `i -= N`) and expanded
  self-update (`i = i + N` / `i = i - N`). The literal `N`
  path emits a decimal (with optional leading `-` for
  subtraction); the symbolic path reuses the uniform-struct-
  field / override / const helpers so `i = i + stride`
  produces `"override:stride"` when `stride` is an override.
  Unanalyzable shapes fall through to `"1"` — the canonical
  `i = i + 1u` kernel routes through the literal path and
  still produces `"1"`, keeping digest-stability for the
  common case. Why it matters: stride-N kernels (tiled
  matmul inner K-loop with an unroll factor; gather
  batched-offset dispatch; sliding-window attention that
  advances by `stride` per outer step) used to share the
  same axis digest as stride-1 kernels. Now they
  disambiguate. Pairs naturally with iteration 50's
  `lower_bound` extractor — the axis slot is now fully
  bound-and-stepped rather than having two of its three
  fields hardcoded. New test "frontend extracts real step
  from for-loop continuing clause" drives three loops
  covering expanded (`i = i + 2u`), compound (`j += 4u`),
  and symbolic override (`k = k + stride`); asserts `"2"`,
  `"4"`, `"override:stride"`. All prior tests still pass
  because every other existing fixture uses `i = i + 1u`,
  which now routes through the literal path and still emits
  `"1"`. `zig build test-wgsl` reports 886/886 tests passed.
- TSIR Step 4 — twenty-fourth increment: iteration-axis
  `lower_bound` is no longer hardcoded to `"0"`. New helper
  `extractInitBound(allocator, module, function, init_expr_opt)`
  in `runtime/zig/src/tsir/frontend.zig` walks the for-loop's
  `local_decl` initializer expression and emits: the literal
  integer (`for (var i: u32 = 4u; ...)` → `"4"`), a
  `uniform:<struct>.<field>` string when the initializer is a
  uniform struct field access, or an `override:<name>` /
  `const:<name>` symbolic string when the initializer is a
  module-scope override or const reference. When the
  initializer is unanalyzable — or the for-loop lacks an
  initializer entirely — the caller falls through to the
  historical `"0"` default so canonical `i = 0u` kernels are
  digest-stable. Mirrors the shape of the upper-bound
  resolvers from iterations 33 / 46 / 47: literal path first,
  uniform-struct next, plain global last. Why it matters: a
  kernel that starts its iteration at a non-zero offset
  (tiled slice dispatch, KV-cache append, sliding-window
  attention prefill) used to collapse to the same axis
  digest as a canonical start-at-zero kernel; the two
  kernels now disambiguate. The all-prior tests continue to
  pass because every other existing fixture uses
  `var i: u32 = 0u;` which flows through the literal path to
  the same `"0"` the hardcoded default produced. New test
  "frontend extracts real lower_bound from the for-loop
  init expression" drives three loops in one kernel — one
  with literal `4u`, one with `override:start_offset`, one
  with `0u` — and asserts the three distinct lower-bound
  strings. `zig build test-wgsl` reports 885/885 tests
  passed.
- TSIR Step 4 — twenty-third increment: rejection `node_path`
  now disambiguates if-then vs if-else branches via explicit
  `.then` / `.else` segments. `walkRejectionsInStmt` in
  `runtime/zig/src/tsir/frontend.zig` previously recursed into
  `node.then_block` and `node.else_block` with the SAME
  `path_prefix`; a non-for loop at the same position in the
  two branches produced identical `node_path` strings, which
  meant downstream consumers comparing rejections
  positionally would see the two rejections as pointing at
  the same node. The fix allocates a per-branch prefix
  (`{parent}.then` / `{parent}.else`) before recursing, then
  frees it with `defer` so the allocation is scope-bounded.
  The existing structured `.body[k]` segment still nests
  naturally inside — a rejection in the then-branch at
  position 1 reads as `functions[0].body[0].then.body[1]`.
  Why it matters: the rejection taxonomy is meant to support
  fail-closed routing (downstream consumers read the
  `node_path` to surface user-visible diagnostics); an
  ambiguous path means two distinct source locations that
  failed for the same reason get reported as one. The
  existing "nested while inside for loop" test continues to
  pass — the outer container is a for_loop, not an if, so
  the path is unchanged. New test "frontend disambiguates
  if-then vs if-else in non-for rejection node paths"
  drives an `if { while ... } else { while ... }` kernel
  and asserts two distinct node_paths — one with `.then`,
  one with `.else`, both at `.body[1]` since the `var` local
  declaration occupies `.body[0]` in each branch. `zig
  build test-wgsl` reports 884/884 tests passed.
- TSIR Step 4 — twenty-second increment: `resolveTargetBinding`
  now follows `let`-alias hops so the common pattern
  `let tmp = acc; output[0] = tmp;` resolves to the right
  `target_binding` instead of falling into the unresolved-
  writeback rejection. The resolver in
  `runtime/zig/src/tsir/frontend.zig` maintains a fixed-size
  alias buffer (8 entries) that starts at `{acc_local}`; each
  post-loop `.local_decl` whose initializer is
  `load(local_ref(x))` for some `x` already in the set grows
  the set by the new local. Writeback detection accepts any
  rhs whose loaded local is in the alias set. Overflow is not
  a correctness issue — if more than 8 aliases chain through
  the region (vanishingly rare in real kernels), only the
  ones that fit stay tracked; the rest would degrade to a
  resolution-failure rejection as before, never a silent
  wrong answer. Small helper `isInAliasSet(aliases, needle)`
  centralizes the membership check so the switch arms read
  cleanly. Why it matters: Phase A's RMSNorm kernels write
  through an intermediate scalar (`let scale = rsqrt(acc /
  N);`) before the final store; similarly the fused GEMV
  epilogue often funnels `acc` through a bias-add and a
  pre-activation copy. Without this hop-following resolver,
  every such kernel produced a rejection AND a silent
  `target_binding = 0` — two failure modes at once.
  (Non-identity hops like the bias-add still reject because
  the rhs is `binary` not `load` — that's correct: the
  accumulator value HAS changed and target_binding analysis
  needs more structure to follow it. The hop-follower is
  scoped narrowly to PURE let-copies.) New test "frontend
  resolves target_binding through a let-alias writeback hop"
  drives `let tmp = acc; output[0] = tmp;` and asserts
  `target_binding == 1` with zero rejections. The existing
  "no writeback" test still rejects because its kernel has
  neither a direct nor alias-chain writeback. `zig build
  test-wgsl` reports 883/883 tests passed (up from 882).
- TSIR Step 4 — twenty-first increment: uniform-struct field
  access now joins the override / const path in the symbolic
  upper-bound resolver. `extractSymbolicUpperBound` in
  `runtime/zig/src/tsir/frontend.zig` now tries a new
  `extractUniformFieldAccess` helper BEFORE the plain
  `findGlobalBase` call — the helper walks outer `load`
  wrappers, matches a `member` expression, then walks the
  member's base chain through more `load` wrappers down to a
  `global_ref`. When the resolved global has
  `class == .var_` and `addr_space == .uniform`, the resolver
  emits `"uniform:<name>.<field>"` (or `"...+1"` for the `<=`
  case). Why the member-first order matters: without it,
  `findGlobalBase` would collapse `params.count` to just
  `params` (the struct's global_index) and lose the field
  name — two distinct fields on the same uniform struct would
  produce identical axis strings. Non-uniform classes
  (storage buffers, workgroup-private structs) return null and
  fall through to the existing override/const lookup so the
  placeholder honest-fallback property is preserved. The
  "non-literal fallback" test was updated to use a
  storage-buffer element read (`i < counts[0]`) since
  `params.count` now resolves; that test still locks the
  placeholder path by exercising a WGSL shape none of the
  resolvers match. New positive test "frontend resolves
  uniform-struct field bound to uniform:name.field" drives
  both `< params.count` (→ `"uniform:params.count"`) and
  `<= params.count` (→ `"uniform:params.count+1"`). Why it
  matters for Phase A: every canonical kernel bundle wraps
  M / K / N dimensions in a `Uniforms` struct; before this
  increment those kernels collapsed to the placeholder; now
  the axis digest separates them by the exact field the bound
  references. `zig build test-wgsl` reports 882/882 tests
  passed.
- TSIR Step 4 — twentieth increment: iteration-axis upper
  bounds shaped `i < override_name` / `i <= override_name` now
  resolve to symbolic bound strings instead of collapsing to
  the `"upper_bound"` placeholder. New helper
  `extractSymbolicUpperBound(allocator, module, function,
  cond, induction_local)` in `runtime/zig/src/tsir/frontend.zig`
  checks for the `load(local_ref(i)) (<|<=) <rhs>` shape, walks
  the rhs through `findGlobalBase` to a `global_ref`, and when
  the resolved global's class is `.override_` or `.const_`
  emits `"override:<name>"` / `"const:<name>"` (with `"+1"`
  suffix for `<=` under the same exclusive-bound convention the
  literal path uses). `var_`-class globals (uniform buffers,
  storage buffers) return `null` so they still fall through to
  the placeholder — honest about what the frontend can actually
  pin today. The axis walker was updated to thread `module`
  through `recoverIterationAxes` and `walkAxesInStmt`; the
  upper-bound resolution chain is now literal → symbolic →
  placeholder, in that order. Why it matters: every Phase A
  bring-up kernel scales its outer loop by a named dimension
  (M, K, N). Before this increment, those kernels all produced
  identical axis strings regardless of which dimension they
  indexed — the semantic digest could not distinguish an
  M-stride GEMV from an N-stride one. Now they do. The
  previous "non-literal fallback" test was updated to reference
  a uniform buffer field (`params.count`) instead of an
  override so it still exercises the placeholder path; the
  new "frontend resolves override-bounded upper to a symbolic
  override:name" test locks both the `<` (→ `"override:trip_count"`)
  and `<=` (→ `"override:trip_count+1"`) resolutions. `zig
  build test-wgsl` reports 881/881 tests passed.
- TSIR Step 4 — nineteenth increment: `CollectiveSemanticNode.axis`
  now reflects the innermost enclosing for-loop instead of
  always being the `-1` whole-workgroup sentinel. `collectCollectives`
  in `runtime/zig/src/tsir/frontend.zig` was rewritten from a flat
  `for (function.exprs.items)` sweep into a statement-aware
  recursive walker: new `CollectiveWalkCtx` carries an
  `axis_counter` and an `axis_stack`; `walkCollectivesInStmt`
  descends through `block`, `local_decl`, `expr`, `assign`,
  `return_`, `if_`, `loop_`, and `switch_` pushing the for_loop
  axis index on entry and popping on exit; `walkCollectivesInExpr`
  recursively visits call / load / unary / binary / construct /
  member / index shapes. When a recognized subgroup builtin call
  is encountered, `emitCollectiveNode` emits the collective with
  `axis = axis_stack.top` or `-1` when the stack is empty. The
  axis counter stays in lockstep with `walkAxesInStmt` and
  `walkReductionsInStmt` so `axis` now indexes into the same
  axes slice the other walkers populate. Honest-fallback
  behavior for non-scalar return types and the `workgroup_barrier`
  dtype exemption carry through unchanged. Why this matters: a
  `subgroupAdd` inside a GEMV-shape outer loop is not the same
  semantic operation as one at the top of the kernel — the inner
  one reduces over the outer loop's iterations and the residency
  pass needs that scope to decide fabric lane mapping. The
  previous `-1` default collapsed both into the same collective
  identity. New test "frontend infers collective axis from
  enclosing for-loop scope" drives a kernel with one top-level
  `subgroupAdd` and one nested inside `for i`, and asserts
  `axis = -1` and `axis = 0` respectively. Both existing
  collective tests continue to pass because their subgroup
  calls sit at the top level. `zig build test-wgsl` reports
  880/880 tests passed.
- TSIR Step 4 — eighteenth increment: non-scalar collective
  return types now rejection-escalate instead of silently
  collapsing to `.u32`. `collectiveDtypeFromReturn` in
  `runtime/zig/src/tsir/frontend.zig` changed signature from
  `ScalarKind` to `?ScalarKind`; vector / matrix / array /
  struct returns now yield `null`. `collectCollectives`
  threads the per-function `rejections` list and emits a
  `RejectionEntry` with
  `reason = .tsir_collective_not_representable`,
  `node_path = "functions[<i>].collectives[<k>]"`, and detail
  `"collective return type is not representable as a
  single-scalar dtype"` when resolution fails, then keeps
  `dtype = .u32` as the shape-preserving default. Taxonomy
  choice: the rejection reason taxonomy already had the exact
  fit — `tsir_collective_not_representable` — so no new enum
  variant. Exemption: `workgroup_barrier` carries no data
  operand, so its `dtype` field is a schema artifact and the
  collector never rejection-escalates for it — the kind-check
  is explicit in the loop. Mirrors the pattern of
  iteration 35 (unresolved writeback →
  `tsir_dependence_unanalyzable`) and iteration 37 (non-scalar
  accumulator → `tsir_dependence_unanalyzable`): silent
  simplification becomes a typed rejection plus a default
  that preserves schema shape, so the collective slot still
  exists for downstream consumers that index by position.
  New test "frontend rejects non-scalar collective dtype with
  u32 shape-preserving fallback" drives a
  `subgroupBallot(true)` call (Doe's sema resolves this to
  `vec4<u32>`) and asserts the rejection fields + default
  dtype. The `workgroupBarrier` in the same kernel stays
  silent, confirming the exemption. All prior collective
  tests continue to pass because their return types were
  scalar. `zig build test-wgsl` reports 879/879 tests passed.
- TSIR Step 4 — seventeenth increment: subgroup canonicalization
  into `CollectiveSemanticNode` now runs in the frontend. New
  `collectCollectives(allocator, module, function)` helper in
  `runtime/zig/src/tsir/frontend.zig` walks
  `function.exprs.items`, keeps `.call` expressions with
  `kind == .builtin`, maps the builtin name to a
  `CollectiveKind` via `builtinNameToCollectiveKind`, and
  emits one node per call site. Coverage: `subgroupAdd`,
  `subgroupMin`, `subgroupMax`, `subgroupMul`,
  `subgroupBroadcast`, `subgroupShuffle`, `subgroupBallot`,
  `subgroupInclusiveAdd` + `subgroupInclusiveMul` (both mapped
  to `.subgroup_inclusive_scan`), `subgroupExclusiveAdd` +
  `subgroupExclusiveMul` (both → `.subgroup_exclusive_scan`),
  and `workgroupBarrier`. Everything else in `.call` space is
  ignored. Why this matters: previously every
  `SemanticFunction.collectives` was `&.{}`, which meant
  downstream lowering had to rediscover subgroup semantics
  per-emitter — exactly the pattern the TSIR plan is trying
  to delete. Now the frontend declares the collectives once
  and downstream passes consume them. Default exactness is
  pessimistic by design: `algorithm_exact` with
  `[reduction_order, associativity_grouping]` invariants, so
  any realization consuming the collective must declare the
  tree shape and associativity grouping rather than assume
  bit-identity. Step 6's collective-synthesis pass refines
  this later — the frontend cannot honestly pin a tighter
  class without knowing the fabric's tree. `axis = -1` is
  the schema's whole-workgroup sentinel; subgroup ops don't
  map to a single TSIR iteration axis. `dtype` resolves from
  the call's return type through `scalarKindFromIr` with
  `ref`-unwrap; non-scalar return types (e.g.
  `subgroupBallot` returning `vec4<u32>`) fall back to `.u32`
  — a future increment either extends `ScalarKind` or
  rejection-escalates that fallback like the non-scalar
  accumulator case. New test "frontend canonicalizes subgroup
  builtins into CollectiveSemanticNode entries" drives a
  WGSL kernel with `subgroupAdd(v)` + `workgroupBarrier()`
  and asserts two collectives in source order with correct
  kind/axis/dtype/exactness. All 877 prior tests continue to
  pass because no fixture previously depended on
  `collectives.len == 0` as a signal — functions without
  subgroup ops still emit an empty slice. `zig build
  test-wgsl` reports 878/878 tests passed.
- TSIR Step 4 — sixteenth increment: rejection emission now
  descends through nested scopes, closing the honesty hole
  iteration 40 left open. `recoverRejections` is now a thin
  entry point that builds an initial `"functions[<i>]"` path
  and hands off to a recursive helper
  `walkRejectionsInStmt(allocator, function, stmt_id,
  path_prefix, rejections)`. The helper mirrors
  `walkAxesInStmt`: it descends into `block` children (each
  child gets path `parent.body[k]`), both branches of `if_`,
  and `loop_` bodies + continuing clauses. At every
  non-for loop it encounters — top-level OR nested — it
  emits one `RejectionEntry` with
  `reason = .tsir_dependence_unanalyzable`, the current
  structured `node_path`, and a short detail string. The
  detail strings changed from `"while loop at top level"` /
  `"unstructured loop at top level"` to just `"while loop"` /
  `"unstructured loop"` since they no longer describe only
  top-level occurrences. The existing top-level while test
  was updated to match; its node_path stays
  `functions[0].body[1]` because the path format for top-level
  is unchanged. New test "frontend rejects a while loop
  nested inside a for loop with a structured node path"
  drives `for i { var k; while (k < 8u) { ... } }`, asserts
  one rejection at `functions[0].body[0].body[1]` with detail
  `"while loop"`, and locks that the outer for_loop still
  contributes an axis so a partially-analyzable kernel
  produces an axis + a rejection rather than an all-or-nothing
  bail. What's still deferred: the walker does not yet emit
  rejections for non-for loops inside `if` branches tagged
  with the `.then`/`.else` path segment; today both branches
  inherit the outer `path_prefix`, so an if-enclosed non-for
  loop would report its path as the enclosing block's. That
  narrower disambiguation can land alongside an extended
  node_path schema when downstream consumers need it. `zig
  build test-wgsl` reports 877/877 tests passed (up from
  876).
- TSIR Step 4 — fifteenth increment: reduction detection now
  descends into nested for loops, mirroring the axis walker
  from the previous increment. `recoverReductions` in
  `runtime/zig/src/tsir/frontend.zig` is now a thin wrapper
  over a recursive walker — new `ReductionWalkCtx`,
  `walkReductionsInStmt(ctx, stmt_id, parent_block, position)`,
  and `scanDirectBodyForReduction(ctx, body, my_axis, parent,
  pos)` helpers replace the old top-level-only loop. The
  walker visits for_loops in pre-order with an axis counter
  that stays in lockstep with `walkAxesInStmt`'s visit order,
  so a reduction inside `for i { for k { acc += ... } }`
  attaches `axis = 1` — the position of `k` in the axes slice
  — not `axis = 0`. Writeback resolution now uses the
  for_loop's PARENT block (not the function root), so a
  canonical GEMV-shape kernel with `output[i] = acc` in the
  outer loop body after the inner for_loop resolves
  `target_binding = 1` correctly. All existing rejection
  behavior carries through unchanged — unresolved writebacks
  still emit `tsir_dependence_unanalyzable` with the
  "no post-loop writeback" detail, non-scalar accumulators
  still emit the "type is not representable as a single-scalar
  accumulation" detail, both at `functions[i].reductions[j]`.
  New test "frontend recovers a nested reduction with axis
  pointing at the inner for loop" drives the canonical
  GEMV-shape kernel and asserts axes `[i, k]`, one reduction
  with `axis = 1` / `op = .sum` / `target_binding = 1`, and
  zero rejections. Scope discipline: reductions detected
  under non-for containers (`while` / bare `loop`) still
  recurse but emit reductions when for_loops are encountered
  inside them — the enclosing non-for loop's rejection is
  still the top-level responsibility of `recoverRejections`
  in a future nested-rejection increment. All prior reduction
  tests continue to pass because flat-loop reductions are
  visited the same way: the top-level for_loop consumes axis
  0, the direct-body scan finds the assign, and the resolver
  looks in the root block just as before. `zig build
  test-wgsl` reports 876/876 tests passed (up from 875).
- TSIR Step 4 — fourteenth increment: axis recovery now
  descends into nested for-loop bodies. `recoverIterationAxes`
  in `runtime/zig/src/tsir/frontend.zig` now delegates to a new
  recursive helper `walkAxesInStmt(allocator, function, stmt_id,
  axes)` that pre-order traverses `block`, `if_` (both branches),
  and `loop_` (body + continuing). When it hits a `for_loop`
  with a `local_decl` init, it appends the `IterationAxis`
  first and recurses into the body after — so an `outer i {
  inner k { ... } }` kernel now produces axes `[i, k]` in that
  order. Why pre-order: downstream planning and reduction
  recovery will use the outer axis to identify the enclosing
  iteration space (rows / M for GEMV, reduction-target rows
  for RMSNorm) and the inner axis as the candidate reduction
  dimension; keeping outer-before-inner in the slice matches
  how kernel-family hints and residency planning read the axis
  list. The walker also descends through non-for `while` /
  `loop` containers so a `for` nested inside them still
  contributes an axis; upgrading non-for containers to typed
  rejections inside nested scopes is a separate future
  increment (today the top-level `recoverRejections` covers
  top-level non-for only). Reduction recovery stays top-level
  this iteration — a nested-reduction kernel like `for i { for
  k { acc += ... } output[i] = acc; }` now reports both axes
  but still recovers zero reductions; that nested-detector
  extension is the natural next pickup. All prior axis tests
  still pass: the side-by-side two-top-level-for-loops fixture
  still produces `[i, j]`, the while-loop fixture still
  rejects at top level with zero axes, and the non-literal
  upper-bound fallback still works. New test "frontend
  recovers nested for loops in pre-order" drives a canonical
  nested shape and asserts `axes[0].name == "i"` with
  `upper_bound == "4"` and `axes[1].name == "k"` with
  `upper_bound == "8"`. `zig build test-wgsl` reports 875/875
  tests passed.
- TSIR Step 4 — thirteenth increment: `SemanticFunction.bindings`
  is now per-function instead of module-wide. Previously every
  function in a module got the same full-module bindings slice,
  which inflated the semantic-digest binding portion and made
  multi-entrypoint modules collide where they shouldn't. New
  helper `extractFunctionBindings(allocator, module, function)`
  in `runtime/zig/src/tsir/frontend.zig` walks
  `function.exprs.items`, collects every `global_ref`, then
  walks `module.globals` keeping only bound globals whose
  index is in that set. Returns a `PerFunctionBindings` struct
  with aligned `bindings: []BufferBinding` and
  `global_indices: []u32`; `bindings[i]` is the encoding of
  the module global at `global_indices[i]`.
  `mapGlobalIndexToBinding` changed to take the per-function
  `binding_global_indices` slice directly, doing a linear
  lookup that returns the aligned per-function position —
  which means `ReductionRegion.target_binding` now also
  indexes into the per-function filtered slice, keeping the
  reduction identity well-defined relative to the function's
  own bindings set. `resolveTargetBinding` signature updated
  to accept the per-function indices instead of the module
  pointer. The old module-wide `extractBindings` helper was
  replaced (not kept as a shim) per the CLAUDE.md rule against
  backwards-compat hacks; if the canonical JSON walker ever
  needs module-wide bindings again it can call
  `extractFunctionBindings` with a synthesized
  always-referenced filter, but no current caller needs that.
  New test "frontend narrows bindings to those the function
  actually references" declares three bindings
  (`input`/`output`/`unused`) but only references two; asserts
  `func.bindings.len == 2` and that `unused` is absent. All
  existing tests continue to pass unchanged because every
  existing fixture already referenced the bindings it
  declared. Why it matters: a multi-entrypoint module where
  entry A uses bindings {0, 1} and entry B uses bindings
  {2, 3} now produces distinct semantic-digest binding
  sections for each entry, which is exactly the per-function
  access summary Step 4's "buffer-binding shape and access
  summary extraction" requirement asks for. `zig build
  test-wgsl` reports 874/874 tests passed.
- TSIR Step 4 — twelfth increment: the literal upper-bound
  extractor now also handles `i <= N` under the exclusive-bound
  convention TSIR uses for `upper_bound`. Extension in
  `extractLiteralUpperBound` (runtime/zig/src/tsir/frontend.zig):
  when the loop condition's binary op is `.less_equal` and the
  rhs is an integer literal, return `N + 1` so `i <= 3u` and
  `i < 4u` both produce `upper_bound = "4"` and both describe
  the same half-open range `[0, 4)`. `.less` keeps returning
  the literal as-is. `+%` is used for the `+1` to stay well-
  defined on the u64 edge case rather than silently trapping in
  Debug. Non-literal rhs stays on the `"upper_bound"`
  placeholder — the non-literal fallback test from iteration 33
  continues to lock that path. New test "frontend maps
  less_equal literal bound to exclusive upper via +1" drives a
  `for (var i: u32 = 0u; i <= 3u; ...)` kernel and asserts
  `upper_bound == "4"`. Scope discipline: `greater` /
  `greater_equal` (loop counts down with induction variable on
  the rhs, requires polarity handling) still stay on the
  placeholder and land in a later increment. `zig build
  test-wgsl` reports 873/873 tests passed.
- TSIR Step 4 — eleventh increment: non-scalar accumulators
  now rejection-escalate instead of silently flattening to
  `.f32`. `resolveAccumulationKind` in
  `runtime/zig/src/tsir/frontend.zig` changed signature from
  `ScalarKind` to `?ScalarKind`; it returns the mapped scalar
  for scalar accumulators (f32 / f16 / bf16 / i32 / u32) and
  `null` for any other shape (vector, matrix, array, struct).
  `recoverReductions` handles the `null` case by emitting a
  `RejectionEntry` with `reason = .tsir_dependence_unanalyzable`,
  `node_path = "functions[<i>].reductions[<j>]"`, and detail
  `"reduction accumulator type is not representable as a
  single-scalar accumulation"`, then keeps
  `contract.accumulation = .f32` as the shape-preserving
  default. This closes the Step-4-plan silent-simplification
  hole the previous increment left open when it noted "a future
  increment either extends the contract or upgrades the
  mismatch to a typed rejection." Taxonomy choice: kept
  `tsir_dependence_unanalyzable` rather than introducing a new
  reason variant, because the underlying issue is the same
  shape of "frontend can't faithfully represent this" as the
  unresolved-writeback case; the `detail` string is the
  disambiguator downstream consumers read when the reason is
  too coarse. A later increment that introduces a more
  specific reason (e.g. `tsir_numerical_contract_unfit`) can
  retarget this rejection; the node_path format stays stable
  in either case. New test "frontend rejects non-scalar
  accumulators and keeps f32 as shape default" drives a
  `vec2<f32>` accumulator reduction kernel and asserts both
  the rejection fields and the default `.f32`. All existing
  scalar-accumulator tests continue to pass unchanged.
  `zig build test-wgsl` reports 872/872 tests passed.
- TSIR Step 4 — tenth increment: reduction
  `contract.accumulation` now carries the accumulator's real
  declared scalar type instead of the hardcoded `.f32` default.
  New helper `resolveAccumulationKind(module, function,
  acc_local)` in `runtime/zig/src/tsir/frontend.zig` looks up
  `function.locals[acc_local].ty`, unwraps a `ref<…>` layer (the
  IR wraps locals declared via `var`), and maps the underlying
  scalar through the existing `scalarKindFromIr` helper.
  Non-scalar accumulator shapes (vectors, matrices, arrays,
  structs) fall back to `.f32` because the current
  `NumericalContract.accumulation` is a single `ScalarKind` and
  can't faithfully represent a vector-typed accumulator; a
  future increment either extends the contract or upgrades the
  mismatch to a typed rejection, but today the fallback
  preserves shape and the common-case correctness path (f32,
  f16, bf16, i32, u32 scalar accumulators) is now honest. All
  existing reduction tests continue to pass unchanged —
  `acc: f32` round-trips through the real resolver to the same
  `.f32` those tests assert. New test "frontend resolves
  accumulation dtype from the accumulator's declared type"
  drives an `acc: i32` reduction kernel and asserts
  `contract.accumulation == .i32`. Why it matters for the
  digest and planner: two otherwise-identical reductions
  differing only by accumulator type (f32 vs f16 vs bf16) used
  to collapse to the same semantic-digest portion of the
  numerical contract; they now distinguish, which is exactly
  the precision discipline Step 6 of the TSIR plan requires
  before collective synthesis can pin the right accumulation
  mode. `zig build test-wgsl` reports 871/871 tests passed.
- TSIR Step 4 — ninth increment: the reduction writeback
  resolver now emits a typed rejection when it cannot find a
  post-loop writeback to a bound global, closing the last
  increment's silent-fallback hole. `resolveTargetBinding` in
  `runtime/zig/src/tsir/frontend.zig` changed signature from
  `u32` to `?u32`; a `null` return now causes `recoverReductions`
  to append a `RejectionEntry` with
  `reason = .tsir_dependence_unanalyzable`, `node_path =
  "functions[<i>].reductions[<j>]"`, and detail
  `"reduction accumulator has no post-loop writeback to a bound
  global"`, then fall back to `target_binding = 0`. The rejection
  is the load-bearing signal downstream consumers must fail
  closed on; the fallback index exists only so the
  `ReductionRegion` slot stays the right shape for the rest of
  the pipeline. `recoverReductions` now takes `func_index` and a
  mutable pointer to the shared rejections list, mirroring how
  `recoverRejections` already threads them. Why it matters:
  previously a kernel that recovered a reduction pattern inside
  a for loop but never wrote the accumulator anywhere produced
  a `ReductionRegion { target_binding = 0 }` indistinguishable
  from a kernel that legitimately reduces into binding 0 — the
  downstream parity oracle and planner had no way to fail
  closed. Now the rejection list carries that signal
  explicitly. Extended the "no writeback visible" test from the
  previous increment: it now also asserts `rejections.len == 1`
  with the exact reason / node_path / detail. All other
  reduction tests continue to pass unchanged because their
  kernels all have `output[0] = acc` writebacks that the
  resolver still finds. Scope discipline: only the "no
  writeback at all" case rejects today; writebacks through
  non-trivial paths (e.g. two-hop `tmp = acc; output[0] = tmp;`
  or conditional writebacks behind an `if`) still silently fall
  back — a later increment extends the detector before
  escalating those to rejections. `zig build test-wgsl` reports
  870/870 tests passed.
- TSIR Step 4 — eighth increment: reductions now carry a real
  `target_binding` instead of the `0` placeholder. New helpers
  `resolveTargetBinding(module, function, body_range, loop_index,
  acc_local)`, `findGlobalBase(function, expr_id)`, and
  `mapGlobalIndexToBinding(module, global_index)` in
  `runtime/zig/src/tsir/frontend.zig` walk the top-level
  statements that come AFTER a reduction loop, look for an
  `assign` whose rhs is `load(local_ref(acc_local))` and whose
  lhs chain (index / member / load / bare) terminates at a
  `global_ref`, and map the resolved module-globals index into a
  position within the `bindings` slice. `recoverReductions` now
  uses that resolver. Honest fallback: a reduction with no
  matching post-loop writeback keeps `target_binding = 0`
  (upgrading that to a typed rejection lands in a later
  increment, per the plan's rule that unresolved lowering
  cannot silently pass). Why it matters: before this increment,
  every reduction claimed to write binding 0, so a kernel that
  reduces into binding 1, 2, or N looked identical in the
  semantic-digest portion covering reduction identity. The
  bootstrap catalog's `fused_gemv` and `rms_norm` fixtures both
  reduce into `@binding(1)`; those semantic JSONs are now
  faithful, and the realization-side planner can key off the
  real binding index rather than an assumed `0`. Two new tests:
  "frontend resolves target_binding from a post-loop writeback"
  drives `output[0] = acc` with `output` at `@binding(1)` and
  asserts `target_binding == 1`; "frontend falls back to
  target_binding 0 when no writeback is visible" locks the
  honest-fallback path. `zig build test-wgsl` reports 870/870
  tests passed (up from 868).
- TSIR Step 4 — seventh increment: iteration-axis `upper_bound`
  now carries the real literal trip count when the loop condition
  is shaped `i < N` with an integer literal `N`. New helper
  `extractLiteralUpperBound(function, cond, induction_local)` in
  `runtime/zig/src/tsir/frontend.zig` pattern-matches the
  canonical `load(local_ref(i)) < int_lit(N)` IR shape and returns
  `N`; `recoverIterationAxes` formats that as a decimal string and
  uses it as the axis's `upper_bound`. Non-matching conditions —
  non-literal rhs, non-`less` op, bare identifier lhs, missing
  cond — fall back to the existing `"upper_bound"` placeholder so
  the frontend never lies about being able to analyze a bound it
  can't. Scope discipline: only `BinaryOp.less` is handled this
  iteration; `less_equal` (needs +1 for exclusive-bound
  convention), `greater`/`greater_equal` (polarity flip), and
  uniform/override rhs (needs a symbolic resolver) land as later
  increments so each change exercises its own test. The earlier
  axis-recovery test locked the `"upper_bound"` string explicitly
  as a "visible contract change" anchor — that's now the anchor
  being moved, and the updated assertion reads `"4"` and `"8"` for
  the two literal-bound for loops in that fixture. New test
  "frontend keeps placeholder upper_bound for non-literal loop
  conditions" drives a WGSL kernel whose condition references a
  module-scope `override` rather than a literal and asserts the
  axis keeps the placeholder, locking the honest-fallback path.
  Why this matters for the digest: previously, two kernels
  differing only by trip count (`for i < 4` vs `for i < 8192`)
  produced identical axis strings and therefore collided in the
  semantic digest's iteration-axis portion; with literal bounds,
  the digest now distinguishes them. `zig build test-wgsl`
  reports 868/868 tests passed (up from 867).
- TSIR Step 4 — sixth increment: the frontend now emits typed
  rejections for top-level loop forms it cannot recover an
  iteration axis from. New `recoverRejections(allocator, function,
  func_index, rejections)` in `runtime/zig/src/tsir/frontend.zig`
  walks the function's root block and, for every `while` or bare
  `loop` at top level, appends one `RejectionEntry` with
  `reason = .tsir_dependence_unanalyzable`, `node_path =
  "functions[<i>].body[<j>]"`, and a short detail string
  (`"while loop at top level"` / `"unstructured loop at top
  level"`). `for_loop` forms are axis-recoverable and do not
  reject. This closes the Step 4 honesty hole the plan calls out
  directly: "Sources that cannot be represented faithfully must
  reject with typed taxonomy reasons instead of having semantics
  dropped or silently simplified." Previously, a `while` loop
  silently produced zero axes and no rejection — the semantics
  were just gone. Now the semantic payload records the rejection
  and downstream consumers can fail closed on it. Tests: the
  existing "frontend ignores non-for-loop iteration forms" test
  now also asserts a one-entry rejection list with the exact
  reason, node path, and detail. New test "frontend emits no
  rejections when all top-level loops are for loops" locks the
  negative case so future increments that broaden the detector
  (nested loops, do-while) do not accidentally reject valid
  for-loop kernels. Scope discipline: only top-level loops are
  walked; nested `while`/`loop` inside a `for_loop` body does NOT
  yet emit a rejection — that lands when the axis pass descends
  into loop bodies. `zig build test-wgsl` reports 867/867 tests
  passed (up from 866).
- TSIR Step 4 — fifth increment: family-hint inference moves off
  the default `.unknown` and onto observable TSIR shape. New helper
  `inferFamilyHint(axes, reductions)` in `runtime/zig/src/tsir/frontend.zig`
  maps recovered function shape to a coarse `KernelFamilyHint`:
  any reduction region → `.reduction`; one or more iteration axes
  with no reduction → `.elementwise`; otherwise `.unknown`. The
  rule is deliberately coarse this iteration. Step 4 of the TSIR
  plan says hints are tiebreakers only and must never change
  feasibility or rejection, so the inference uses only structural
  signals the frontend already recovered — reduction presence and
  axis count — not function names or body-pattern matching. That
  keeps the classifier from sneaking back in through a hint
  side-channel. Refining `.reduction` into `.fused_gemv` /
  `.rms_norm` / `.gather` by inspecting binding shapes and axis
  structure is a later increment; starting from the coarse form
  means that refinement never has to first unwind a name-based
  pre-classifier. Two new tests in
  `runtime/zig/tests/wgsl/tsir_frontend_test.zig`: a WGSL kernel
  whose body contains a classic `acc = acc + input[i]` loop now
  reports `family_hint == .reduction`; a copy loop with one axis
  and no accumulator now reports `family_hint == .elementwise`.
  The minimal empty-function test still asserts `.unknown`, so the
  `unknown` → hint transition is exercised alongside the new
  inference paths. `zig build test-wgsl` reports 866/866 tests
  passed (up from 864).
- Docs alignment — one drift closed in `docs/csl-architecture.md`
  §The abstraction stack. The long-standing "most important design rule is
  that the explicit `HostPlan` is the contract boundary between higher-level
  execution intent and Cerebras-specific emission" line was presented as
  current-truth with no local migration framing. That directly contradicted
  the updated `docs/doppler-ingest.md` §Lowering architecture (HostPlan is
  runtime-orchestration only; kernel meaning, residency, collectives, and
  numerical exactness move into TSIR; HostPlan sits downstream of TSIR
  realization) and the `docs/tsir-lowering-plan.md` §Surrounding context
  framing ("TSIR sits before HostPlan and makes those decisions explicit
  once"). The cross-reference in `doppler-ingest.md` that points readers to
  `csl-architecture.md` for "CSL-specific HostPlan details" made this drift
  load-bearing — a reader following that link landed on uncaveated current
  truth. Rewrote the paragraph to state the rule explicitly as the
  current-path rule, cross-reference the TSIR migration in both sibling
  docs, and name the target-state split (TSIR owns kernel meaning;
  HostPlan owns runtime orchestration). No other drift opened in this
  iteration. After the fix, the three docs tell one migration story
  consistent with "current HostPlan path → TSIR lowering → mechanical
  emitters → manifest-bound receipts"; remaining sections in
  `csl-architecture.md` below the "Planned TSIR generalization" anchor
  still describe current-path behavior, but with the earlier-in-the-doc
  migration framing now locally reinforced at the HostPlan claim.
- TSIR Step 4 — third increment: frontend now recovers iteration
  axes from top-level `for` loops. `recoverIterationAxes` walks the
  function body's root block, picks out `Stmt.loop_` entries with
  `kind == .for_loop` whose init statement is a `local_decl`, and
  emits one `IterationAxis` per recovered loop with `name` taken
  from the induction variable's local name. Bounds/step strings are
  placeholders (`"0"` / `"upper_bound"` / `"1"`) this iteration;
  populating them with the real expression strings is a future
  increment that lands alongside the expression-to-string walker.
  Scope discipline: only top-level loops are walked; nested for
  loops, `while`, and bare `loop` forms do NOT yet produce axes or
  rejections — they simply return empty. Two new tests: a WGSL
  with two top-level for loops produces two axes named `"i"` and
  `"j"`; a WGSL with a `while` loop produces zero axes (no false
  detection). `zig build test-wgsl` reports 861/861 tests passed.
- TSIR Step 4 — second increment: frontend now extracts buffer
  bindings from `module.globals`. Every WGSL global with a
  `@group(n) @binding(m)` annotation is lowered to a
  `BufferBinding` with the right group/binding/read-write polarity
  plus a `(logical_shape, elem: ScalarKind)` pair derived from the
  IR type. Supported today: scalars (empty shape), `array<scalar>`
  (1-D shape, runtime-sized → `[0]`), vectors (1-D, `[vec_len]`),
  matrices (2-D, `[rows, cols]`). Bindings wrapped in `ref<…>` are
  unwrapped first. Structs, textures, samplers, and atomics fall
  through to `(shape=[], elem=.f32)` placeholder so the binding slot
  survives; replacing those placeholders with real encodings is a
  future increment. Each SemanticFunction currently reports the
  full module-scope binding set (WGSL globals are module-scoped); a
  per-function reachability pass comes with the SSA work.
  New integration test `frontend extracts buffer bindings from
  module globals` drives a two-binding WGSL fixture (one
  `read` + one `read_write`) through the full pipeline and verifies
  group/binding/read_write/elem/logical_shape all propagate
  correctly. `zig build test-wgsl` reports 859/859 tests passed.
- TSIR Step 4 — first increment: minimal WGSL → TSIR frontend exists
  end-to-end. New module `runtime/zig/src/tsir/frontend.zig` with
  `lowerIrToTsir(allocator, module, source_digest, frontend_version)`
  that walks a Doe `ir.Module` and produces one `SemanticFunction`
  per WGSL function (name + `family_hint=.unknown` + `source_digest`;
  axes / bindings / reductions / collectives empty). `mod.zig`
  re-exports the frontend.
  Two new integration tests in
  `runtime/zig/tests/wgsl/tsir_frontend_test.zig` run the full
  pipeline (`parseSource → sema.analyze → ir_builder.build →
  frontend.lowerIrToTsir`) on a minimal WGSL compute entrypoint and
  verify: one `SemanticFunction` named `"main"`, correct
  `source_digest` propagation, correct `frontend_version` propagation,
  empty axes/bindings/reductions/collectives (this iteration's scope),
  and that distinct frontend versions produce distinct
  `semanticDigest`s when run through the full digest pipeline. Test
  suite registered in `test_suite_wgsl.zig`. `zig build test-wgsl`
  reports 858/858 tests passed.
  Future Step 4 increments will add, one at a time: buffer-binding
  extraction from `module.globals`, SSA-friendly control-flow
  normalization + induction-variable recovery, affine dependence
  analysis → IterationAxis population, reduction-region
  identification → ReductionRegion population, subgroup
  canonicalization → CollectiveSemanticNode population, and
  kernel-family-hint inference from IR shape. The minimal lowering
  here proves the pipeline exists so each future increment is an
  additive pass over the same function body.
- TSIR Step 3 — `ManifestLoweringEntry` scaffold lands. The 10-field
  tuple the plan's Step 10 enumerates now exists as a first-class
  TSIR type in `runtime/zig/src/tsir/schema.zig` and re-exports via
  `mod.zig`. Fields: `kernel_ref`, `backend`,
  `target_descriptor_correctness_hash` (from the Step 2 correctness
  split, so planner-hint tweaks do NOT invalidate), `frontend_version`
  (the Step 3 pin), `tsir_semantic_digest`, `tsir_realization_digest`,
  `emitter_digest`, `compiler_version`, `exactness` (full Exactness
  struct with invariants), `rejection_reasons` (non-empty means the
  backend refuses this kernel up front). Canonical JSON emission lands
  in `digest.zig` as `canonicalizeManifestLoweringEntry` +
  `manifestLoweringEntryDigest`, with keys in lexicographic order of
  the camelCase field names; matching JSON schema at
  `config/doe-tsir-manifest-lowering.schema.json` is
  `additionalProperties: false` and requires all ten fields.
  Two new tests: full fixture with non-empty exactness invariants
  canonicalizes to exact byte string (lex order verified at every
  nested level); rejected entry has a digest distinct from the
  otherwise-identical pass entry, and per-entry digest is stable
  across repeat canonicalization. `zig build test-wgsl` reports
  856/856 tests passed. Step 3 is now effectively green for the
  plan's stated scope: two-level schema, split digests, canonical
  JSON, frontendVersion pin, algorithm_exact invariants, and the
  manifest-bindable per-entry record.
- TSIR Step 3 — production-grade canonical JSON walker for
  Realization. Mirrors the Semantic walker landed the previous
  iteration: every nested type (`RealizationFunction`, `TileFactors`,
  `PEGridShape`, `ResidencyDecision`, `CollectiveRealizationNode`,
  `ReductionRealizationNode`) now emits with keys in lexicographic
  order of their camelCase JSON field names. Optional fields
  (`axis`, `shards`, `fabricColor`, `chunkBytes`) emit as the literal
  `null` when absent, preserving the split-digest contract that
  absence is part of realization identity. Three new tests: empty
  realization produces the exact byte string; non-trivial realization
  with a single function + residency + reduction + PE-grid + tile
  factors produces the exact lex-sorted byte string; and a
  tree-shape-difference test proves that changing
  `ReductionRealizationNode.tree_shape` from `.linear` to `.binomial`
  changes `realizationDigest` while leaving `semanticDigest` identical
  — the split-digest promise landing as bit-level evidence.
  `zig build test-wgsl` reports 854/854 tests passed.
  Step 3's canonicalization work is now complete for both layers;
  the remaining Step 3 surface is `ManifestLoweringEntry` (the 10-
  field tuple the plan's Step 10 enumerates; still stub-absent in
  schema).
- TSIR Step 3 — production-grade canonical JSON walker for Semantic.
  `digest.zig` now emits real lex-ordered JSON instead of the scaffold
  byte string. Walks every nested TSIR type (`SemanticFunction`,
  `IterationAxis`, `BufferBinding`, `ReductionRegion`,
  `NumericalContract`, `CollectiveSemanticNode`, `Exactness`,
  `RejectionEntry`) with keys in lexicographic order per the schema's
  camelCase field names. Enums emit their tag names as quoted strings;
  `[32]u8` digests emit as 64-char lowercase hex. String escaping
  covers the canonical reserved set (`\"`, `\\`, `\n`, `\r`, `\t`,
  `\uXXXX` for control codes). Float canonicalization rejects NaN/Inf
  explicitly (TSIR forbids them in canonical form). Realization
  canonicalization remains scaffold-shaped pending its own walker.
  Three new tests: empty semantic canonicalizes to the exact byte
  string `{"contractVersion":1,"frontendVersion":"","functions":[],"rejections":[]}`,
  a non-trivial semantic produces the exact lex-sorted byte string
  (all keys verified in alphabetical order at every nesting level),
  and string escaping covers the canonical-form-reserved characters.
  `zig build test-wgsl` reports 851/851 tests passed.
- TSIR Step 3 — `frontendVersion` pin wired into Semantic. The revised
  plan's Step 3 caveat says `semanticDigest` is stable ONLY under a
  pinned frontend version; a frontend upgrade (richer loop recovery,
  subgroup canonicalization, affine-analysis coverage) changes semantic
  identity. `Semantic.frontend_version: []const u8` (defaults empty)
  now carries the pinned identity; `canonicalizeSemantic` in
  `digest.zig` includes it so changing frontend version changes
  `semanticDigest`. `config/doe-tsir-semantic.schema.json` adds
  `frontendVersion` as a required top-level string. The three bootstrap
  catalog entries (`fused_gemv`, `rms_norm`, `gather`) gained an empty
  `frontendVersion: ""` field to stay schema-valid after the
  requirement; catalog tests still pass.
  One new test locks three invariants: same frontendVersion →
  identical digest; different frontendVersion → distinct digests;
  empty default is distinct from any declared version. `zig build
  test-wgsl` reports 848/848 tests passed. Full production-grade
  canonical JSON walker (lex-ordered keys, per-field emitters for all
  TSIR types) remains future Step 3 work; the digest is still
  scaffold-shaped but now participates every identity-affecting input.
- TSIR Step 3 — `algorithm_exact` invariants now load-bearing. The
  revised plan requires `algorithm_exact` to carry a declared list of
  bit-affecting properties (reduction order, tree shape, accumulation
  dtype, associativity grouping); a bare class tag cannot distinguish
  realizations that produce different float bits under the same
  semantic. Schema work:
  - `runtime/zig/src/tsir/schema.zig` adds `AlgorithmExactInvariant`
    enum (four variants) and an `Exactness` struct wrapping class +
    invariants + optional tolerance metric/epsilon. `Exactness` is the
    per-node contract; the bare `ExactnessClass` enum stays for cases
    where only the class tag is needed.
  - `CollectiveSemanticNode.exactness` now declares `Exactness` rather
    than the bare enum, so a lowering's invariant list is machine-
    checkable at schema validation time.
  - `config/doe-tsir-semantic.schema.json` adds a `$def` for
    `algorithmExactInvariant` (enum of four values) and `exactness`
    (object with `class` + optional invariants array + optional
    tolerance fields).
  - `runtime/zig/src/tsir/mod.zig` re-exports `AlgorithmExactInvariant`
    and `Exactness` on the public surface.
  Three new tests lock the invariant enum coverage, the four cases
  of Exactness construction (bit_exact_solo defaults, algorithm_exact
  with invariants, tolerance_bounded with metric+epsilon). The
  pre-existing "exactness classes match RDRR taxonomy verbatim" test
  continues to hold since the bare enum is unchanged. `zig build
  test-wgsl` reports 847/847 tests passed.
  This closes the second scaffolding-to-plan gap I flagged earlier:
  before this iteration, `algorithm_exact` was a bare tag with no
  machine-checkable invariants.
- TSIR Step 2 — descriptor correctness/planner split landed. The
  revised plan requires partitioning target-descriptor fields into
  `correctness` (participates in lowering identity) and `planner`
  (search quality only; must not invalidate manifests on tuning).
  `runtime/zig/src/targets/mod.zig` now defines `CorrectnessFields`
  and `PlannerFields`, `TargetDescriptor` wraps both, and
  `descriptorHash` hashes only the correctness fields so a
  `fabric_per_hop_latency_ns` tuning does not force re-emission of
  existing lowerings. `wse3.zig` and `webgpu_generic.zig` updated to
  the nested-initializer shape. Two new tests lock the invariant:
  planner-field-change produces same hash, correctness-field-change
  produces different hash. Existing "distinct descriptors have
  distinct hashes" and "descriptor hash is stable" tests continue to
  hold. `zig build test-wgsl` reports 845/845 tests passed.
  This closes a scaffolding-to-plan gap that had been open since the
  TSIR scaffolding first landed: the original unified descriptor
  struct did not distinguish correctness from planner fields, which
  meant any hint tweak would have invalidated every lowering.
- TSIR Step 1.5 — bootstrap catalog entry 3 of 3: gather. Completes
  the plan-required trio. New trio in
  `runtime/zig/tests/tsir/bootstrap/`: `gather.wgsl` (minimal embedding
  lookup `output[t,h] = table[indices[t], h]`),
  `gather.tsir-semantic.json` (schema-valid shape + dtypes), and
  `gather.notes.md`. The notes surface a category error orthogonal to
  GEMV/RMSNorm: indexed indirect addressing — one binding's values
  used as offsets into another binding's axis. Current `BufferBinding`
  has no way to express this relationship. Implied Step 3 extensions
  specific to gather: a first-class `GatherNode` operation with
  (source binding, source axis, index binding, bounds policy), an
  explicit index-binding attribute, and a declared `BoundsPolicy` enum
  (`assume_valid` / `clamp_to_zero` / `trap`) because different
  choices produce different output bytes on out-of-range inputs — the
  parity contract must pin one.
  Step 1.5's three-entry catalog is now complete. Three distinct
  category-error classes have been discovered by hand-sketching real
  kernels against the current schema, driving a documented Step 3
  extension surface: (a) elementwise/arithmetic op-body AST (GEMV +
  RMSNorm), (b) multi-stage composition / scalar tail / scalar binding
  kind (RMSNorm), (c) gather node + index-binding attribute + bounds
  policy (gather). Realization sketches for all three families remain
  deferred pending those schema extensions.
  `test_tsir_bootstrap_catalog.py` picks up the new files
  automatically; 4 tests pass.
- TSIR Step 1.5 — bootstrap catalog entry 2 of 3: RMSNorm. New trio in
  `runtime/zig/tests/tsir/bootstrap/`: `rms_norm.wgsl` (minimal
  single-token RMSNorm exercising elementwise-square + scalar-tail
  arithmetic + elementwise-multiply-chain), `rms_norm.tsir-semantic.json`
  (schema-valid, represents only the reduction shape), and
  `rms_norm.notes.md` (schema-fit report). The notes surface four
  category errors the GEMV entry didn't: pre-op square, scalar-tail
  arithmetic (div/add/sqrt/recip), elementwise multiply chain after
  reduction, and post-reduction dependency from reduction output into
  a later elementwise stage. Implied Step 3 extensions beyond GEMV's:
  scalar-operand binding kind for `eps`, multi-stage function
  composition (ordered `reduce → elementwise` within one
  SemanticFunction), and a Phase B determinism commitment for `sqrt`.
  The existing `test_tsir_bootstrap_catalog.py` picks up the new files
  automatically; 4 tests still pass. Gather entry remains for next
  iteration.
- TSIR Step 1.5 — bootstrap kernel catalog, first entry (fused GEMV).
  `runtime/zig/tests/tsir/bootstrap/` now holds a pinned WGSL snapshot
  (`fused_gemv.wgsl`), a hand-sketched TSIR semantic JSON
  (`fused_gemv.tsir-semantic.json`), and a schema-fit report
  (`fused_gemv.notes.md`). The semantic JSON validates against
  `config/doe-tsir-semantic.schema.json`, but the notes explicitly
  document what the current schema CANNOT express: the elementwise
  multiply `W[i,k] * x[k]` before the sum has no TSIR node. This is
  exactly the category-error discovery Step 1.5 exists for — the
  schema accepts a structurally valid reduction shape while the kernel
  body it must encode is not yet representable. Implied Step 3 schema
  extensions (fused pre-op on `ReductionRegion`, or elementwise
  operation AST as a first-class TSIR node, plus symbolic buffer-shape
  dims) are documented for the next schema iteration.
  `bench/tests/test_tsir_bootstrap_catalog.py` locks the invariants:
  directory and README exist, every WGSL has a paired semantic sketch
  and notes file, every JSON in the catalog validates against the
  current schema. Four Python tests pass. RMSNorm and gather entries
  follow in subsequent iterations.
- TSIR Step 1 — rank-3 binomial fold. Rank-3 reduction branch now
  honors `.binomial` alongside `.linear`/`.ring` using the same
  scratch-buffer-per-output pattern as rank-2. Scratch of size
  `reduce_len` is allocated once before the `out_i` loop and reused
  across positions; empty reduce lengths short-circuit to identity
  without allocating. Linear and ring paths continue to stream.
  Rank-4+ binomial still falls through (odometer path requires an
  analogous scratch extension; future increment).
  One new test: rank-3 binomial sum over `[2, 2, 4]` with values 1..16
  along axis 2 (inner) produces `[[10, 26], [42, 58]]`, where each row's
  four values pairwise-fold to `(v0+v1)+(v2+v3)`. The "rank-3 binomial
  still falls through" test was retired (now a pass path). `zig build
  test-wgsl` reports 843/843 tests passed.
- TSIR Step 1 — rank-2 binomial fold. The rank-2 reduction branch now
  honors `effective_tree_shape == .binomial` with per-output-position
  pairwise folding. Scratch buffer of size `reduce_len` is allocated
  once (before the `out_i` loop) and reused across output positions so
  the hot loop is alloc-free. Per `out_i`: gather `reduce_len` values
  into `scratch[0..reduce_len]`, then pairwise-fold at `⌈count/2⌉` per
  level, passing any odd leftover through. Empty reduce (`reduce_len
  == 0`) returns identity without allocating scratch. Linear / ring
  paths remain the streaming left-fold. Rank-3 and rank-4+ binomial
  still fall through (scope discipline).
  Two new tests: rank-2 binomial sum `[[1,2,3,4],[5,6,7,8]] → [10, 26]`
  (`(1+2)+(3+4)=10`, `(5+6)+(7+8)=26`); rank-3 binomial still-falls-
  through. One stale "rank-2 binomial still falls through" test was
  retired (now a pass path). `zig build test-wgsl` reports 843/843
  tests passed.
- TSIR Step 1 — `.ring` tree shape accepted. On a single-PE reference
  interpreter, ring and linear fold orders are bit-for-bit identical
  (the distinction is fabric topology, not fold order, and a single-PE
  oracle cannot exercise fabric topology). The dispatch in
  `run_doe_csl_int4ple_transcript.py`-adjacent wording: rank-1/2/3/4+
  paths all treat `.ring` as `.linear`; `.binomial` remains rank-1-only.
  Rank gating simplified from "only linear" to "not binomial" so ring
  now flows through every rank path. An `else` arm in the rank-1
  switch was removed as unreachable after `linear`/`ring` were
  collapsed into a single prong. Two new tests replace the old ring-
  unimplemented test: rank-1 ring sum `[1,2,3,4]f32 → 10.0`, and
  rank-2 ring per-row sum `[[1,2,3],[4,5,6]] → [6,15]`. Non-linear
  binomial on rank ≥ 2 still falls through (unchanged). `zig build
  test-wgsl` reports 842/842 tests passed.
- TSIR Step 1 — first non-linear tree fold: `binomial` for rank-1
  associative_allowed reductions. The algorithm gathers all N input
  values, then pairwise-folds to `ceil(N/2)` values each level, passing
  any odd leftover through to the next level, until one value remains.
  On non-associative floating-point this can differ bit-for-bit from
  the linear left-fold, which is exactly the property
  `algorithm_exact` pins as a declared invariant — two kernels with
  identical `semanticDigest` but different `realizationDigest` can
  legitimately produce different output bits when the declared tree
  shapes differ. Scope is rank-1 for this iteration; rank-2/3/4+ with
  non-linear tree shapes still fall through to `NotImplemented` (the
  generic odometer path guards on `effective_tree_shape == .linear`).
  Two new tests: parametric pass path for sum/product/min/max on
  `[1,2,3,4]f32` under binomial (result matches linear on exact
  integers: 10 / 24 / 1 / 4), and rank-2 binomial still-falls-through.
  One stale rank-1 "binomial remains unimplemented" test was retired;
  a ring-tree version replaces it since ring is still unsupported.
  `zig build test-wgsl` reports 841/841 tests passed.
- TSIR Step 1 — Realization now participates in interpreter dispatch
  for the first time. `associative_allowed` reductions require a
  matching `ReductionRealizationNode` (new struct in `schema.zig`,
  new field on `RealizationFunction.reductions`, new entry in
  `config/doe-tsir-realization.schema.json`). The interpreter dispatches
  on `reduction.contract.associativity`: `strict_ordered` proceeds to
  left-fold as before; `associative_allowed` looks up the realization's
  declared `tree_shape` — only `.linear` is currently interpreted
  (equivalent to left-fold), with `.binomial` and `.ring` falling
  through to `NotImplemented` until the tree-fold path lands. The plan's
  "algorithm_exact invariants include tree_shape" clause is now
  enforceable: a lowering that declares `associative_allowed` without a
  realization tree shape is refused precisely rather than silently
  assumed. Three new tests: pass path with linear tree, refusal when no
  realization tree shape is declared, refusal when tree shape is
  binomial. `zig build test-wgsl` reports 839/839 tests passed.
- TSIR Step 1 — rank-4+ generic N-D reduction fallback. The rank-4+
  case uses an odometer over the output coord tuple instead of explicit
  nested loops, so any rank ≥ 4 works from a single code path. Row-major
  input strides are computed from the input logical_shape; the input
  base offset for each output position is
  `sum(coord[out_pos] * stride[in_dim_map(out_pos)])` where
  `in_dim_map` skips the reduced axis. Output shape validation enforces
  the per-dimension contract (output rank is input rank minus one,
  matching all non-reduced dims). Rank-1/2/3 explicit paths are left
  untouched (they are tested and fast); the generic fallback handles
  rank 4+ without duplicated per-rank code. Two new tests lock rank-4
  reductions: axis 3 (innermost, contiguous) over `[2,2,2,2]` with
  values 1..16 → `[3,7,11,15,19,23,27,31]`; axis 1 (non-innermost,
  strided) over `[2,3,1,2]` with values 1..12 → `[9,12,27,30]`.
  `zig build test-wgsl` reports 836/836 tests passed. This shape class
  covers attention-prep reductions like `[batch, head, seq, hidden]`
  along any axis, which is where real MHA Phase B work will land.
- TSIR Step 1 — rank-3 reduction. `trySimpleReduction` now handles 3-D
  input shapes along any of the three axes, dropping the reduced axis
  and preserving row-major order for the surviving two. Flat-index
  math uses `a*B*C + b*C + c` with the reduced dim substituted by `r`
  per axis case. Non-reduced dim product becomes the output element
  count; output shape rank is the input rank minus one (rank-2). One
  parametric test locks all three axes on `[[[1,2],[3,4]],[[5,6],[7,8]]]`
  producing `[[6,8],[10,12]]` (axis 0), `[[4,6],[12,14]]` (axis 1),
  `[[3,7],[11,15]]` (axis 2). The dtype matrix and op table
  (sum/product/min/max, f32/f16/bf16 in, f32/f16/bf16 out) is
  inherited from the shared helpers without duplication. `zig build
  test-wgsl` reports 834/834 tests passed. Rank 4+ still falls through
  to `NotImplemented`; attention shapes commonly use rank 4
  (batch, head, seq, hidden) so that is the next natural extension.
- TSIR Step 1 — bf16 output completes the narrow dtype matrix. The
  downcast uses round-to-nearest-even on the u32 bit pattern via the
  bias trick (`bits + 0x7fff + lsb` then `>> 16`), with explicit NaN
  preservation: a NaN input takes the high 16 bits of its f32 bit
  pattern and forces the quiet-NaN mantissa bit on, so rounding
  overflow cannot silently turn a NaN into an Inf. Three new tests
  lock the end-to-end pass path (`[1,2,3,4]f32 → bf16(10.0) = 0x4120`,
  exact), NaN preservation (f32 NaN → bf16 NaN, not Inf), and the RTNE
  ties-to-even behavior on exact half values (`0x3F808000 → 0x3F80`
  down, `0x3F818000 → 0x3F82` up). `zig build test-wgsl` reports
  833/833 tests passed. Phase A scalar dtype matrix is now
  `{f32, f16, bf16} → {f32, f16, bf16}` for reductions with f32
  accumulation. Integer dtypes and `associative_allowed` remain the
  next open surfaces within Step 1.
- TSIR Step 1 — first non-f32 output dtype. `trySimpleReduction` can now
  downcast the f32 accumulator to an `f16` output binding. New helpers
  `writeF32AsElem` (dispatches on wb.elem) and `emitScalarFromF32`
  (parameterized version of the old `emitScalarF32`) centralize the
  downcast; both rank-1 and rank-2 paths route through them. bf16
  output remains explicitly unsupported — caught by the entry check
  that now accepts `{f32, f16}` for `wb.elem`. One stale test that
  asserted "f16 output rejects" was retired (now a pass path); two new
  tests replace it: f16 scalar downcast case (`[1,2,3,4]f32 → 10.0 f16`
  — exact because 10.0 is representable in both), and the bf16-output
  fail-closed refusal. `zig build test-wgsl` reports 831/831 tests
  passed.
- TSIR Step 1 — second non-f32 input dtype. `trySimpleReduction` now
  accepts `bf16` input alongside `f16` and `f32`. bf16 is f32 truncated
  to its high 16 bits; the upcast path reads 2 LE bytes, splices them
  into the high 16 bits of a u32, and `@bitCast`s to f32. No native Zig
  bf16 type is required — the bit manipulation is direct and loss-free
  per the bf16 spec. One new test locks the pass path on `[1,2,3,4]bf16`
  → `10.0 f32`; because 1/2/3/4 have zero mantissa low bits as f32,
  truncating to bf16 and back is exact so the scalar is bit-identical.
  `zig build test-wgsl` reports 830/830 tests passed.
- TSIR Step 1 — first non-f32 input dtype. `trySimpleReduction` now
  accepts `f16` input with `f32` accumulation per the declared
  `NumericalContract.accumulation = .f32` rule in the module header.
  The new `readF32FromBytes` helper upcasts per element: `f32` reads
  4 LE bytes and `@bitCast` to f32; `f16` reads 2 LE bytes, `@bitCast`
  to f16, then `@floatCast` to f32. Both rank-1 and rank-2 branches
  route through the helper so there is one dtype-widening code path.
  Output is still f32 so the reference hash lives in a fixed byte
  layout. Two new tests: `[1,2,3,4]f16 → 10.0 f32` (f16 representations
  of 1/2/3/4 are exact so the scalar is bit-identical), and fail-closed
  refusal when the output binding is `.f16`. `zig build test-wgsl`
  reports 829/829 tests passed.
- TSIR Step 1 — `trySimpleReduction` now handles 2-D input shapes along
  any axis. `[M, N] f32` input reduces to `[N] f32` along axis 0 and to
  `[M] f32` along axis 1, using row-major offset math (`input[i,j]` at
  byte offset `(i*n + j)*4`). The four-op identity/combine table
  (`sum`/`product`/`min`/`max`) is reused for the inner fold; per-axis
  traversal is a single branch around the offset calc. Two new tests
  lock the 2-D sum cases: per-column sums `[[1,2,3],[4,5,6]]` along
  axis 0 → `[5,7,9]`, and per-row sums along axis 1 → `[6,15]`. A
  pre-rank axis check was removed so per-rank branches own axis
  validation. Rank 3+ still falls through to `NotImplemented`.
  `zig build test-wgsl` reports 827/827 tests passed. This shape class
  is exactly what RMSNorm's sum-of-squares pre-step needs.
- TSIR Step 1 — `trySimpleReduction` now covers all four ReductionOps
  (`sum`, `product`, `min`, `max`) over 1-D `strict_ordered f32`.
  Refactored into `reductionIdentityF32()` and `combineF32()` helpers so
  adding the remaining three ops was a one-line dispatch extension per
  op, not a new code path. Product uses identity 1.0, min uses
  `+inf`, max uses `-inf`; each identity is what a zero-length fold
  returns. `@min`/`@max` honor IEEE-754 min/max under the declared
  `nan_inf=propagate` contract. Two parametric tests replace the old
  single-op case: one locks product/min/max over `[1,2,3,4]` producing
  `24.0 / 1.0 / 4.0`, the other locks the empty-input identity for each
  of the four ops. `zig build test-wgsl` reports 825/825 tests passed.
- TSIR Step 1 — first real arithmetic. The reference interpreter now
  dispatches `strict_ordered f32` sum reductions over a 1-D input: a
  function with one `[N]f32` read binding, one `[1]f32` write binding,
  one reduction region (`axis=0`, `op=sum`, `accumulation=f32`,
  `strict_ordered`, `nan_inf=propagate`), and no collectives is folded
  left-to-right with explicit IEEE-754 byte-layout in/out. The output
  scalar is emitted as little-endian 4 bytes, and `reference_hash =
  SHA-256(output_bytes)`. Non-sum ops, non-strict associativity, non-f32
  dtypes, non-1D shapes, and wrong target bindings fall through to
  `NotImplemented` — the oracle never silently honors a reduction class
  it cannot yet handle. This is the first increment where the oracle
  performs arithmetic rather than copying or returning empty. Four new
  tests lock the pass case (`sum [1,2,3,4] = 10`), the associativity
  refusal, the non-sum-op refusal, and the empty-input identity (0.0).
  `zig build test-wgsl` reports 824/824 tests passed.
- TSIR Step 1 schema prerequisite: `ReductionRegion` now declares the
  arithmetic operation it computes via a new `ReductionOp` enum (`sum`,
  `product`, `min`, `max`). The Zig struct defaults to `.sum` so existing
  reduction fixtures continue to compile; the JSON schema at
  `config/doe-tsir-semantic.schema.json` now requires the `op` field on
  every reduction, closing the ambiguity where a reduction declared an
  axis and a target buffer but not what to compute across that axis.
  The public module surface at `runtime/zig/src/tsir/mod.zig` re-exports
  `ReductionOp`. Three new tests lock the enum coverage, the default
  value, and explicit override. `zig build test-wgsl` reports 820/820
  tests passed. The interpreter itself does not yet dispatch reductions;
  that lands as the next increment, now unblocked by this schema work.
- TSIR Step 1 again: the reference interpreter now dispatches the
  zero-binding nop case. A `SemanticFunction` with zero bindings, zero
  reductions, and zero collectives returns a `Result` with no output
  buffers and `reference_hash = SHA-256("")`. The dispatch is wired
  ahead of `tryIdentity` in `run()`, proving the multi-case dispatch
  pattern the interpreter needs as it grows. Two new tests lock the
  nop pass path and the fail-closed refusal when a caller supplies
  inputs that the nop kernel doesn't consume. `zig build test-wgsl`
  reports 817/817 tests passed.
- TSIR Step 1 again: the identity path now validates input buffer size
  against declared `logical_shape × elem.byteSize()` and rejects
  wrong-sized inputs as `NotImplemented` rather than silently hashing a
  truncated or oversized tensor. `ScalarKind.byteSize()` added to
  `runtime/zig/src/tsir/schema.zig` as the single source of truth for
  per-element byte sizes (f32/i32/u32 = 4; f16/bf16 = 2). A new
  `computeExpectedBytes()` helper in `reference_interpreter.zig` walks
  logical shape with overflow-safe u64 arithmetic. Two new inline tests
  lock the under-sized + over-sized rejection and the ScalarKind byte
  table. `zig build test-wgsl` reports 815/815 tests passed.
- TSIR Step 1 moved one notch forward again: the Zig reference interpreter now
  distinguishes explicit TSIR rejection from the generic `NotImplemented`
  oracle scaffold, and `bench/tools/doe_parity.py` now surfaces
  `rejectionReasons[]` as a first-class fail-closed state when semantic or
  realization TSIR inputs declare a rejected lowering. This keeps rejected
  lowerings from collapsing into the same bucket as "oracle not wired yet".
- TSIR reference interpreter (`runtime/zig/src/tsir/reference_interpreter.zig`)
  now has its first real dispatch path: the identity case. A SemanticFunction
  with exactly one read-only binding and one writable binding of matching
  shape, zero reductions, and zero collectives is interpreted as a
  byte-for-byte copy from input to output, with `reference_hash = SHA-256(output_bytes)`.
  Every other semantic still returns `NotImplemented`. This is a scaffolding
  step: it proves the Result struct, allocator ownership, and hash pipeline
  are sound end-to-end before the first real kernel dispatch lands.
- New `freeResult` helper owns output-buffer lifecycle so the caller contract
  is explicit.
- Two new unit tests in `runtime/zig/tests/wgsl/tsir_scaffold_test.zig` lock
  the identity-copy pass path and the `NotImplemented` refusal when a
  reduction is present. The zero-oracle default test still holds for the
  empty semantic. `zig build test-wgsl` exit 0.
- This increment closes one committable unit of TSIR plan Step 1. Real
  dispatch on non-identity kernels still requires a schema extension to
  carry op bodies (Step 3) and/or a frontend that produces TSIR with enough
  information to interpret (Step 4). Both remain open.

## Current state

- The forward compiler plan for one-program/many-realizations lowering is now
  documented in `docs/tsir-lowering-plan.md`. The in-tree
  `runtime/zig/src/tsir/` scaffold exists, but it is not wired into the real
  frontend/emitter path yet.
- The TSIR scaffold now locks the full vocabulary: `schema.zig` declares the
  two-level `Semantic`/`Realization` types with `contract_version = 1`,
  `digest.zig` produces split `semanticDigest`/`realizationDigest`/
  `emitterDigest`, `reference_interpreter.zig` declares the numerical contract
  (IEEE-754 round-to-nearest-even, fp32 accumulation, left-fold reduction
  order, sollya-bounded transcendentals), supports the identity bootstrap
  case, and now distinguishes explicit TSIR rejection from generic
  `NotImplemented`. Target descriptors live under
  `runtime/zig/src/targets/` — `wse3.zig` and `webgpu_generic.zig` — and
  their SHA-256 `descriptorHash` participates in the realization digest.
- A manual parity CLI lives at `bench/tools/doe_parity.py` with receipts
  validated by `config/doe-parity-receipt.schema.json`. The CLI runs today
  but comparisons still fail closed: non-rejected lanes return
  `not_implemented` / `deferred`, rejected TSIR inputs now surface explicit
  `rejectionReasons[]`, and the process exit code remains non-zero while the
  frontend and backend lanes are still to land.
- TSIR and realization contracts live at
  `config/doe-tsir-semantic.schema.json` and
  `config/doe-tsir-realization.schema.json`. Scaffolding invariants are
  locked by `runtime/zig/tests/wgsl/tsir_scaffold_test.zig` and
  `bench/tests/test_doe_parity.py`.
- Postfix `++` / `--` statements are now supported in the WGSL compiler
  (tokens, lexer, AST `inc_stmt`/`dec_stmt`, parser, sema, IR lowering).
  `ir_transform` / `emit_spirv` errors are surfaced with specific kinds
  instead of silently becoming empty `OOM` strings, and the failing-kernel
  log carries the first 120 chars of the WGSL so failures are identifiable
  without re-running.
- The Doe WebGPU shared-contract lane has real transcript and parity plumbing,
  but it is not green end to end.
- The current blocker is in `runtime/zig/src/doe_wgsl/`, not Vulkan feature
  discovery.
- Vulkan-side capability bring-up has improved: the adapter now advertises
  `shader-f16` correctly, and the shared-contract runner can force subgroup
  removal with `DOE_DISABLE_SUBGROUPS=1`.

## Active blockers

- WGSL semantic-analysis and/or SPIR-V emission gaps still block some real
  Doppler kernels in the shared-contract lane.
- Mixed subgroup and non-subgroup entrypoints remain a real compiler surface.
- Real KV/cache evidence is still not emitted in the WebGPU transcript path.

## Landed infrastructure

- Shared-contract WebGPU transcript receipt
- Pairwise parity binder
- Generic transcript parity report surface
- Vulkan API-version and feature-capability fixes that expose `shader-f16`
  correctly
- Shared-contract runner defaults that force the declared subgroup workaround
  instead of silently relying on unsupported subgroup lowering

## Ground truth

- The WebGPU lane is blocked by WGSL compiler work, not by contract design.
- The current failures are concrete compiler/runtime gaps with named files and
  reproducible signatures.

## Use this shard for

- `doe_wgsl` compiler status
- WebGPU shared-contract transcript status
- WebGPU parity blockers
- Vulkan capability / adapter issues that affect the WebGPU lane
