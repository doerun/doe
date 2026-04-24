// TSIR schema — Two-level Semantic IR for Doe's WGSL → backend compiler.
//
// TSIR sits between WGSL IR and backend emitters. It is two layered
// structures with two digests:
//
//   tsir.Semantic       — stable across compiler policy iteration
//   tsir.Realization    — varies with target and planner version
//
// Both serialize to canonical JSON; their hashes become the
// `semanticDigest` and `realizationDigest` bound into RDRR manifest
// `integrityExtensions.lowerings[]`.
//
// Vocabulary: exactness classes match RDRR verbatim, rejection codes
// are enumerated up front. No ad-hoc tolerance, no implicit defaults.

const std = @import("std");

pub const CONTRACT_VERSION: u32 = 1;

// ============================================================
// Exactness classes (match RDRR taxonomy verbatim)
// ============================================================

pub const ExactnessClass = enum {
    /// Hex-identical bytes versus reference in a single, declared order.
    bit_exact_solo,
    /// Hex-identical bytes versus reference re-run in the declared
    /// reduction-tree order. Commutativity allowed, associativity declared.
    algorithm_exact,
    /// Declared metric within declared epsilon; both metric and epsilon
    /// are fields on the node, never harness defaults.
    tolerance_bounded,
};

/// Invariants that make an `algorithm_exact` contract meaningful.
///
/// Per the plan, `algorithm_exact` cannot be a bare enum: two
/// realizations of the same semantic can produce different float bits
/// if they differ on these properties, so the list of invariants a
/// realization must honor is part of the exactness contract.
pub const AlgorithmExactInvariant = enum {
    /// Left-fold vs tree; relevant on non-associative floating-point.
    reduction_order,
    /// Tree shape declared in `ReductionRealizationNode` or the
    /// analogous realization-side node; includes binomial / ring /
    /// linear plus any future shape that affects output bits.
    tree_shape,
    /// Accumulation dtype pinned independently of input/output dtypes;
    /// e.g. fp32 accumulation under f16 inputs.
    accum_dtype,
    /// Explicit associativity grouping for reductions where the order
    /// of pair-wise combining is declared (rather than merely the
    /// high-level tree shape).
    associativity_grouping,
};

/// Full exactness contract attached to a reduction or collective
/// node. `class` is always declared; the other fields are populated
/// only for the class that needs them and must be empty/zero
/// otherwise.
pub const Exactness = struct {
    class: ExactnessClass,
    /// Required when `class == .algorithm_exact`; must be empty for
    /// `bit_exact_solo` and `tolerance_bounded`.
    algorithm_exact_invariants: []const AlgorithmExactInvariant = &.{},
    /// Required when `class == .tolerance_bounded`; must be empty for
    /// the other two classes. The metric string names the declared
    /// distance function (e.g. `"ulp"`, `"relative"`, `"max_abs"`).
    tolerance_metric: []const u8 = "",
    /// Required when `class == .tolerance_bounded`; zero for other
    /// classes. The epsilon is interpreted under the declared metric.
    tolerance_epsilon: f64 = 0.0,
};

// ============================================================
// Rejection taxonomy (enumerated up front; fail-closed)
// ============================================================

pub const RejectionReason = enum {
    tsir_subgroup_unlowerable,
    tsir_pe_budget_exhausted,
    tsir_collective_not_representable,
    tsir_dependence_unanalyzable,
    tsir_source_not_affine,
    tsir_target_unfit,
};

pub const RejectionEntry = struct {
    reason: RejectionReason,
    /// Dot-delimited path into the TSIR structure where the rejection
    /// applies, e.g. `functions[0].reductions[2]`.
    node_path: []const u8,
    /// Short actionable detail string; never free-form prose — short
    /// noun phrase tied to the specific node.
    detail: []const u8,
};

// ============================================================
// Kernel family hints (hints only — never selects an emitter)
// ============================================================

pub const KernelFamilyHint = enum {
    unknown,
    elementwise,
    reduction,
    gather,
    rms_norm,
    fused_gemv,
    tiled_matmul,
    attention_decode,
    attention_tiled,
    rope,
    dequant,
    sample,
    embed,
};

// ============================================================
// Numerical contract
// ============================================================

pub const ScalarKind = enum {
    f32,
    f16,
    bf16,
    i32,
    u32,

    /// Number of bytes occupied by a single element of this scalar kind.
    /// Used by the reference interpreter to validate input buffer sizes
    /// against declared `BufferBinding.logical_shape`.
    pub fn byteSize(self: ScalarKind) u8 {
        return switch (self) {
            .f32, .i32, .u32 => 4,
            .f16, .bf16 => 2,
        };
    }
};

pub const ReductionAssociativity = enum {
    /// Strict left-fold; reduction order is part of the observable
    /// semantics.
    strict_ordered,
    /// Associativity permitted; reduction tree shape lives in
    /// Realization, not Semantic.
    associative_allowed,
};

pub const NanInfPolicy = enum { propagate, quiet_mask };

/// Which arithmetic operation defines a reduction region.
///
/// The reference interpreter dispatches on this enum to determine what
/// to compute over the declared reduction axis. `sum` and `product` are
/// the floating-point-sensitive ops where associativity matters;
/// `min` and `max` are order-insensitive under IEEE-754 (excluding NaN
/// handling which is covered by `NanInfPolicy`).
pub const ReductionOp = enum {
    sum,
    product,
    min,
    max,
    /// Numerically-stable softmax normalizer over the declared axis:
    /// `exp(x - max(x)) / sum(exp(x - max(x)))`. A single ReductionOp
    /// because the max pass and the sum-exp pass are load-bearing
    /// together — splitting them into two ReductionRegion entries
    /// would require the second to reference the first's output, a
    /// cross-region dependency the schema does not yet express.
    /// Consumed by attention body lowering; see `AttentionScoresBody`.
    softmax_stable,
};

pub const NumericalContract = struct {
    accumulation: ScalarKind,
    associativity: ReductionAssociativity,
    nan_inf: NanInfPolicy,
};

// ============================================================
// Collective nodes (subgroup → fabric lowering surface)
// ============================================================

pub const CollectiveKind = enum {
    subgroup_add,
    subgroup_min,
    subgroup_max,
    subgroup_mul,
    subgroup_broadcast,
    subgroup_ballot,
    subgroup_shuffle,
    subgroup_exclusive_scan,
    subgroup_inclusive_scan,
    workgroup_barrier,
    fabric_reduce,
    fabric_broadcast,
    fabric_allreduce,
};

pub const ReductionTreeShape = enum { binomial, ring, linear };

pub const CollectiveSemanticNode = struct {
    kind: CollectiveKind,
    /// Which iteration axis the collective operates over, by index into
    /// the enclosing loop nest. -1 for whole-workgroup.
    axis: i32,
    exactness: Exactness,
    dtype: ScalarKind,
};

pub const CollectiveRealizationNode = struct {
    /// Parallel index into Semantic.collectives.
    semantic_index: u32,
    tree_shape: ReductionTreeShape,
    fabric_color: ?u32,
    group_size: u32,
};

/// Realization-side pairing for a `ReductionRegion`. When a reduction
/// declares `associative_allowed` on the semantic side, the
/// interpreter uses this node to pick a fold order. For
/// `strict_ordered` reductions, this node is informational (left-fold
/// is the only legal order regardless).
pub const ReductionRealizationNode = struct {
    /// Parallel index into `SemanticFunction.reductions`.
    semantic_index: u32,
    tree_shape: ReductionTreeShape,
};

// ============================================================
// Buffers and loop nests
// ============================================================

pub const BufferBinding = struct {
    name: []const u8,
    group: u32,
    binding: u32,
    logical_shape: []const u64,
    elem: ScalarKind,
    read_write: bool,
};

pub const IterationAxis = struct {
    /// Loop induction variable name recovered by SSA phi analysis.
    name: []const u8,
    /// Lower bound must be an affine expression over outer axes;
    /// represented here as a simple integer or the literal `"dynamic"`
    /// placeholder when dependence is not analyzable (will be rejected
    /// by the residency pass with TSIR_DEPENDENCE_UNANALYZABLE).
    lower_bound: []const u8,
    upper_bound: []const u8,
    step: []const u8,
};

pub const ReductionRegion = struct {
    /// Axis this reduction collapses, indexed into the surrounding
    /// loop nest.
    axis: u32,
    /// Which arithmetic operation the reduction computes. Defaults to
    /// `sum` so existing fixtures that predate this field keep their
    /// meaning, but the frontend should always set this explicitly.
    op: ReductionOp = .sum,
    contract: NumericalContract,
    /// Reference into the output buffer where the reduced value lands.
    target_binding: u32,
};

// ============================================================
// Semantic body roles
// ============================================================

pub const SemanticBodyOp = enum {
    unknown,
    fused_gemv,
    rms_norm,
    gather,
    /// Fused attention-scores body:
    /// `output = softmax_stable((Q · Kᵀ) · scale [+ softcap] [+ mask]) · V`.
    /// Represents the prefill / decode attention kernel family as a
    /// single semantic body so TSIR can emit one lowering instead of
    /// the current per-variant template pile. See `AttentionScoresBody`.
    attention_scores,
};

pub const SemanticBindingRole = enum {
    matrix,
    vector,
    input,
    scale,
    indices,
    table,
    output,
    // Attention-scores bindings (added for SemanticBodyOp.attention_scores):
    query,
    key,
    value,
    /// Optional runtime KV-length buffer when the host streams KV in
    /// chunks whose cumulative length is observed at dispatch time
    /// instead of baked into a uniform. Maps to Doppler's
    /// `kv_len_buffer` binding.
    kv_len_buffer,
    /// Optional page-table binding for paged-KV layouts. Maps to
    /// Doppler's `page_table` binding.
    page_table,
};

pub const SemanticAxisRole = enum {
    output,
    reduction,
    hidden,
    token,
    // Attention-scores axes (added for SemanticBodyOp.attention_scores):
    head,
    query_sequence,
    key_sequence,
};

pub const SemanticBodyBinding = struct {
    binding_index: u32,
    role: SemanticBindingRole,
};

pub const SemanticBodyAxis = struct {
    axis_index: u32,
    role: SemanticAxisRole,
};

pub const RmsNormFormula = enum {
    sum_squares_mean_epsilon_rsqrt_scale,
};

pub const RmsNormReductionTarget = enum {
    intermediate_scalar,
};

pub const RmsNormEpsilonSource = enum {
    uniform_field,
    literal_f32,
};

pub const RmsNormEpsilon = struct {
    source: RmsNormEpsilonSource,
    /// Canonical symbolic source for uniform-backed epsilon values, for
    /// example `uniform:u.eps`. Empty when `source == .literal_f32`.
    path: []const u8 = "",
    /// Binding index carrying the uniform bytes when
    /// `source == .uniform_field`; null for literal epsilon values.
    binding_index: ?u32 = null,
    /// Byte offset within the uniform binding where the f32 epsilon
    /// value starts when `source == .uniform_field`; null for literals.
    byte_offset: ?u32 = null,
    /// Literal epsilon value when `source == .literal_f32`; null for
    /// uniform-backed epsilon values.
    literal_f32: ?f64 = null,
};

pub const RmsNormBody = struct {
    formula: RmsNormFormula,
    epsilon: RmsNormEpsilon,
    /// Axis carrying the normalized hidden extent. The reduction axis
    /// is still declared by `ReductionRegion.axis`; this field states
    /// which body axis the per-element output shares with the reduction
    /// extent.
    hidden_extent_axis: u32,
    reduction_target: RmsNormReductionTarget,
};

/// Softmax algorithm selector. Both modes end up at the same stable
/// result; the distinction is load-bearing because it constrains
/// emitter choices (streaming cannot be naively flash-decomposed
/// across PEs without a reconciliation pass).
pub const SoftmaxMode = enum {
    /// Traditional two-pass numerically-stable softmax:
    ///   pass 1: max over the reduction axis
    ///   pass 2: sum(exp(x - max)), then divide
    /// Cheapest to reason about; requires two full passes over scores.
    two_pass_stable,
    /// Online / streaming softmax (flash-attention inner loop):
    /// updates `(m, l, acc)` per block so K/V can stream in tiles.
    /// Single pass over scores but carries running state across
    /// iterations of the reduction axis.
    streaming_online,
};

/// Causal/windowing mode for attention score masking.
pub const CausalMode = enum {
    /// Full attention; no masking beyond the declared kv-length.
    none,
    /// Standard causal mask: key positions after the query position
    /// are masked out (score = -inf).
    causal,
    /// Sliding-window causal: key positions outside
    /// `[query_pos - window + 1, query_pos]` are masked out.
    sliding_window,
};

/// Fused attention-scores kernel body. Represents:
/// `output[h, q] = softmax_stable((Q[h,q] · Kᵀ[h]) · scale [+ softcap] [+ mask]) · V[h]`
///
/// The reduction declared at the enclosing `SemanticFunction.reductions`
/// must reduce over the key_sequence axis with
/// `ReductionOp.softmax_stable` and produce the per-(head, query_pos)
/// normalizer. This body carries the constants (head_dim, scale source,
/// softcap, causal window) that drive emitter choices.
pub const AttentionScoresBody = struct {
    softmax_mode: SoftmaxMode,
    /// Dimension of each attention head; also the reduction extent for
    /// the Q·Kᵀ dot product at each (head, q_pos, k_pos) triple.
    head_dim: u32,
    /// Axis index of the kv_sequence axis in the enclosing loop nest;
    /// this is where `ReductionOp.softmax_stable` collapses.
    key_sequence_axis: u32,
    /// Scale factor applied to raw scores before softmax. Typically
    /// `1/sqrt(head_dim)` but the source is declared here so the
    /// emitter doesn't have to guess.
    scale_source: AttentionScaleSource,
    scale_binding_index: ?u32 = null,
    scale_byte_offset: ?u32 = null,
    /// Literal scalar scale when `scale_source == .literal_f32`.
    scale_literal_f32: ?f64 = null,
    /// Whether an `attn_softcap` (Gemma-style `tanh(s / cap) * cap`)
    /// is applied to scores before softmax.
    has_softcap: bool = false,
    causal_mode: CausalMode = .none,
    /// Required when `causal_mode == .sliding_window`; bounds the
    /// visible key range.
    sliding_window_size: ?u32 = null,
};

pub const AttentionScaleSource = enum {
    /// Scale is stored in a uniform field. Path/binding/offset declared
    /// on the containing `AttentionScoresBody`.
    uniform_field,
    /// Scale is a compile-time literal, declared on the containing body.
    literal_f32,
};

/// Declares the kernel body family in semantic, digestable form. Family hints
/// are planner tie-breakers; this body contract is the semantic claim that
/// parity and backend emitters consume.
pub const SemanticBody = struct {
    op: SemanticBodyOp = .unknown,
    binding_roles: []const SemanticBodyBinding = &.{},
    axis_roles: []const SemanticBodyAxis = &.{},
    rms_norm: ?RmsNormBody = null,
    attention_scores: ?AttentionScoresBody = null,
};

// ============================================================
// Semantic (stable)
// ============================================================

pub const SemanticFunction = struct {
    name: []const u8,
    family_hint: KernelFamilyHint,
    axes: []const IterationAxis,
    bindings: []const BufferBinding,
    reductions: []const ReductionRegion,
    collectives: []const CollectiveSemanticNode,
    body: SemanticBody = .{},
    /// Hash of the owning WGSL IR module (pre-TSIR). Lets replay verify
    /// semantic identity without re-running the whole frontend.
    source_digest: [32]u8,
};

pub const Semantic = struct {
    contract_version: u32 = CONTRACT_VERSION,
    /// Pinned frontend version. `semanticDigest` is stable only under
    /// a fixed frontend version; a frontend upgrade that adds loop
    /// recovery, richer subgroup canonicalization, or different
    /// affine-analysis coverage changes semantic identity. Manifests
    /// pin `frontendVersion` alongside `semanticDigest` so a future
    /// compiler bump cannot silently invalidate existing lowerings.
    /// The empty string is the pre-versioning default; real uses must
    /// set this to a concrete value.
    frontend_version: []const u8 = "",
    functions: []const SemanticFunction,
    rejections: []const RejectionEntry,
};

// ============================================================
// Residency (realization)
// ============================================================

pub const ResidencyClass = enum {
    /// Every PE holds the whole tensor. Only legal when the tensor fits
    /// the target's per-PE working memory budget.
    pe_replicated,
    /// Tensor sliced along `axis` into `shards` per-PE pieces.
    pe_sliced,
    /// Streamed across fabric on a declared color in chunks.
    fabric_streamed,
    /// Copied from host per-launch; no persistence.
    host_copied,
    /// Recomputed from inputs; persisted bytes reclaimed under a cost
    /// bound declared by the residency pass.
    recomputed,
};

pub const ResidencyDecision = struct {
    binding_index: u32,
    class: ResidencyClass,
    /// Populated for pe_sliced: which axis, how many shards.
    axis: ?u32 = null,
    shards: ?u32 = null,
    /// Populated for fabric_streamed: fabric color and chunk bytes.
    fabric_color: ?u32 = null,
    chunk_bytes: ?u64 = null,
};

pub const TileFactors = struct {
    /// Power-of-two tile factor per axis, in order of the enclosing nest.
    per_axis: []const u32,
};

pub const PEGridShape = struct {
    width: u32,
    height: u32,
};

// ============================================================
// Realization (varies)
// ============================================================

pub const RealizationFunction = struct {
    /// Parallel index into Semantic.functions.
    semantic_index: u32,
    tiles: TileFactors,
    pe_grid: PEGridShape,
    residency: []const ResidencyDecision,
    collectives: []const CollectiveRealizationNode,
    /// Per-reduction tree shape, paired by `semantic_index` into the
    /// owning `SemanticFunction.reductions`. Empty when no reductions
    /// are declared or when all reductions are `strict_ordered`.
    reductions: []const ReductionRealizationNode = &.{},
    /// Emitter-specific parameters kept as a canonicalized JSON blob so
    /// the emitter version alone decides parameter interpretation.
    emitter_params_json: []const u8,
    /// Hash of the target descriptor used to build this realization.
    target_descriptor_hash: [32]u8,
};

pub const Realization = struct {
    contract_version: u32 = CONTRACT_VERSION,
    functions: []const RealizationFunction,
    /// Hash of the emitter module version used. Future emitter changes
    /// force realization re-emission.
    emitter_digest: [32]u8,
    rejections: []const RejectionEntry,
};

// ============================================================
// Split digests
// ============================================================

pub const Digests = struct {
    semantic: [32]u8,
    realization: [32]u8,
    emitter: [32]u8,
};

/// One entry in the manifest's `integrityExtensions.lowerings[]`
/// array. Carries the 10-field tuple that binds a kernel's TSIR
/// identity to the target and compiler versions under which it was
/// lowered. Replay consults this to pick the right lowering for the
/// detected adapter/fabric, and rejects if `rejection_reasons` is
/// non-empty.
pub const ManifestLoweringEntry = struct {
    /// Stable reference to the kernel in the source program (e.g.
    /// `"gemma-4-e2b.rmsnorm"`); callers pair this with the
    /// source-program manifest for full identity.
    kernel_ref: []const u8,
    /// Backend tag — `"wse3"`, `"webgpu-generic"`, `"metal"`, etc.
    backend: []const u8,
    /// Hash of the target descriptor's correctness fields only (per
    /// the Step 2 correctness/planner split). Planner-hint tuning
    /// does NOT invalidate this entry.
    target_descriptor_correctness_hash: [32]u8,
    /// Frontend version pin; must match the value embedded in the
    /// TSIR semantic at lowering time.
    frontend_version: []const u8,
    tsir_semantic_digest: [32]u8,
    tsir_realization_digest: [32]u8,
    emitter_digest: [32]u8,
    /// Doe compiler version identity (e.g. `"doe-0.3.2"`); a compiler
    /// bump forces refreshed lowerings rather than silently reusing
    /// old ones.
    compiler_version: []const u8,
    /// Declared exactness contract, including invariants for
    /// `algorithm_exact` and metric/epsilon for `tolerance_bounded`.
    exactness: Exactness,
    /// Populated when the backend cannot honor the kernel. Non-empty
    /// means "runtime refuses this backend for this kernel up front."
    rejection_reasons: []const RejectionReason,
};
