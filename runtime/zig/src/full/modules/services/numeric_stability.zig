const std = @import("std");
const common = @import("../common.zig");
const numeric_stability_policy = @import("../../../numeric_stability_policy.zig");
const trace_numeric_stability = @import("../../../trace_numeric_stability.zig");

pub const MODULE_ID = "doe_numeric_stability";
pub const MATMUL_LOGITS_SLICE_SERVICE_ID = "matmul_logits_slice";
pub const SUPPORTED_OPERATOR_FAMILY = "lm-head-slice";
pub const SUPPORTED_SEMANTIC_OP_ID = "matmul.logits";
pub const SUPPORTED_FAST_POLICY_ID = "lm-head-slice/forward-f16accum-v1";
pub const SUPPORTED_STABLE_POLICY_ID = "lm-head-slice/forward-serial-v1";
pub const REFERENCE_POLICY_ID = "lm-head-slice/cpu-f64-serial-v1";
const ZERO_HASH = "sha256:0000000000000000000000000000000000000000000000000000000000000000";

pub const CandidateInput = struct {
    tokenId: u32,
    label: ?[]const u8 = null,
    weights: []const f64,
    bias: ?f64 = null,
};

pub const Request = struct {
    schemaVersion: u32,
    moduleId: []const u8,
    artifactKind: []const u8,
    serviceId: []const u8,
    operatorFamily: []const u8,
    semanticOpId: []const u8,
    semanticStage: []const u8,
    semanticPhase: []const u8,
    triggerPolicyId: []const u8,
    routingPolicyId: []const u8,
    fastPolicyId: []const u8,
    stablePolicyId: []const u8,
    candidates: []const CandidateInput,
    hiddenState: []const f64,
    receiptPath: ?[]const u8 = null,
    traceMetaPath: ?[]const u8 = null,
};

pub const Policy = struct {
    policyRegistryPath: []const u8,
    registry: numeric_stability_policy.Registry,
};

pub const ParsedPolicy = struct {
    parsed: std.json.Parsed(numeric_stability_policy.Registry),
    policyRegistryPath: []u8,
    value: Policy,

    pub fn deinit(self: *ParsedPolicy, allocator: std.mem.Allocator) void {
        self.parsed.deinit();
        allocator.free(self.policyRegistryPath);
    }
};

pub const ServiceResult = struct {
    status: []const u8,
};

pub const ExecutionStats = struct {
    dispatchCount: u64,
    bytesMoved: u64,
    candidateCount: u64,
};

pub const TimingStats = struct {
    setupNs: u64,
    encodeNs: u64,
    submitNs: u64,
    dispatchNs: u64,
};

pub const FailureDetails = struct {
    code: []const u8,
};

pub const ReceiptCandidate = struct {
    tokenId: u32,
    label: ?[]const u8 = null,
    fastLogit: f64,
    stableLogit: f64,
    referenceLogit: f64,
};

pub const FirstDivergence = struct {
    semanticOpId: []const u8,
    semanticStage: []const u8,
    semanticPhase: []const u8,
    fastDigest: []const u8,
    stableDigest: []const u8,
};

pub const SelectedTokenReceipt = struct {
    fast: u32,
    stable: u32,
    reference: u32,
    fastMatchesReference: bool,
    stableMatchesReference: bool,
};

pub const TriggerChecks = struct {
    firstDivergencePresent: bool,
    sensitiveOperatorMatched: bool,
    selectedTokenDisagreement: bool,
    stableMatchesExactReference: bool,
    fastMissesExactReference: bool,
};

pub const TriggerReceipt = struct {
    fired: bool,
    checks: TriggerChecks,
    proofLinks: []const numeric_stability_policy.ProofLink,
};

pub const RouteReceipt = struct {
    decision: []const u8,
    selectionMode: []const u8,
    selectedPolicyId: ?[]const u8 = null,
    selectedToken: ?u32 = null,
    proofLinks: []const numeric_stability_policy.ProofLink,
    selectionProofLinks: []const numeric_stability_policy.ProofLink,
};

pub const Receipt = struct {
    schemaVersion: u32,
    mode: []const u8,
    operatorFamily: []const u8,
    semanticOpId: []const u8,
    semanticStage: []const u8,
    semanticPhase: []const u8,
    policyRegistryPath: []const u8,
    policyRegistryVersion: []const u8,
    routeTaxonomyVersion: []const u8,
    proofArtifactPath: []const u8,
    triggerPolicyId: []const u8,
    routingPolicyId: []const u8,
    fastPolicyId: []const u8,
    stablePolicyId: []const u8,
    referencePolicyId: []const u8,
    candidates: []const ReceiptCandidate,
    firstDivergence: ?FirstDivergence = null,
    selectedToken: SelectedTokenReceipt,
    trigger: TriggerReceipt,
    route: RouteReceipt,
};

pub const ResultNoTrace = struct {
    schemaVersion: u32,
    moduleId: []const u8,
    artifactKind: []const u8,
    serviceId: []const u8,
    serviceResult: ServiceResult,
    executionStats: ExecutionStats,
    timingStats: TimingStats,
    failureDetails: FailureDetails,
    routeDecision: []const u8,
    selectedToken: ?u32,
    receiptPath: ?[]const u8 = null,
    traceMetaPath: ?[]const u8 = null,
    receipt: Receipt,
};

pub const Result = struct {
    schemaVersion: u32,
    moduleId: []const u8,
    artifactKind: []const u8,
    serviceId: []const u8,
    serviceResult: ServiceResult,
    executionStats: ExecutionStats,
    timingStats: TimingStats,
    failureDetails: FailureDetails,
    routeDecision: []const u8,
    selectedToken: ?u32,
    receiptPath: ?[]const u8 = null,
    traceMetaPath: ?[]const u8 = null,
    receipt: Receipt,
    traceLink: common.TraceLink,
};

const HashlessTraceMeta = struct {
    traceVersion: u32,
    module: []const u8,
    seqMax: u32,
    rowCount: u32,
    numericStability: trace_numeric_stability.TraceNumericStabilitySummary,
};

const TraceMetaFile = struct {
    traceVersion: u32,
    module: []const u8,
    seqMax: u32,
    rowCount: u32,
    hash: []const u8,
    previousHash: []const u8,
    numericStability: trace_numeric_stability.TraceNumericStabilitySummary,
};

pub fn parseRequest(allocator: std.mem.Allocator, bytes: []const u8) !std.json.Parsed(Request) {
    return try std.json.parseFromSlice(Request, allocator, bytes, .{
        .ignore_unknown_fields = false,
        .allocate = .alloc_always,
    });
}

pub fn parsePolicy(
    allocator: std.mem.Allocator,
    policy_registry_path: []const u8,
    bytes: []const u8,
) !ParsedPolicy {
    var parsed = try numeric_stability_policy.parseRegistry(allocator, bytes);
    errdefer parsed.deinit();
    const owned_path = try allocator.dupe(u8, policy_registry_path);
    errdefer allocator.free(owned_path);
    return .{
        .parsed = parsed,
        .policyRegistryPath = owned_path,
        .value = .{
            .policyRegistryPath = owned_path,
            .registry = parsed.value,
        },
    };
}

fn ensureValidRequest(request: Request) !void {
    if (!std.mem.eql(u8, request.moduleId, MODULE_ID)) return error.InvalidModuleId;
    if (!std.mem.eql(u8, request.artifactKind, "request")) return error.InvalidArtifactKind;
    if (!std.mem.eql(u8, request.serviceId, MATMUL_LOGITS_SLICE_SERVICE_ID)) return error.UnsupportedServiceId;
    if (!std.mem.eql(u8, request.operatorFamily, SUPPORTED_OPERATOR_FAMILY)) return error.UnsupportedOperatorFamily;
    if (!std.mem.eql(u8, request.semanticOpId, SUPPORTED_SEMANTIC_OP_ID)) return error.UnsupportedSemanticOpId;
    if (!std.mem.eql(u8, request.fastPolicyId, SUPPORTED_FAST_POLICY_ID)) return error.UnsupportedFastPolicy;
    if (!std.mem.eql(u8, request.stablePolicyId, SUPPORTED_STABLE_POLICY_ID)) return error.UnsupportedStablePolicy;
    if (request.hiddenState.len == 0) return error.HiddenStateEmpty;
    if (request.candidates.len < 2) return error.CandidateCountInvalid;
    for (request.candidates) |candidate| {
        if (candidate.weights.len != request.hiddenState.len) return error.CandidateLengthMismatch;
    }
}

fn ensureValidPolicy(policy: Policy) !void {
    try numeric_stability_policy.ensureValidRegistry(policy.registry);
}

fn containsString(values: []const []const u8, needle: []const u8) bool {
    for (values) |value| {
        if (std.mem.eql(u8, value, needle)) return true;
    }
    return false;
}

fn ensureParentPath(path: []const u8) !void {
    if (std.fs.path.dirname(path)) |dir_name| {
        if (dir_name.len == 0) return;
        try std.fs.cwd().makePath(dir_name);
    }
}

fn totalBytesMoved(request: Request) u64 {
    var total: u64 = @as(u64, @intCast(request.hiddenState.len)) * @sizeOf(f64);
    for (request.candidates) |candidate| {
        total += @as(u64, @intCast(candidate.weights.len)) * @sizeOf(f64);
        if (candidate.bias != null) total += @sizeOf(f64);
    }
    return total;
}

fn evaluateForwardF16(hidden_state: []const f64, weights: []const f64, bias: ?f64) f64 {
    var acc: f16 = 0;
    for (hidden_state, weights) |hidden_value, weight_value| {
        const lhs: f16 = @floatCast(hidden_value);
        const rhs: f16 = @floatCast(weight_value);
        acc = acc + lhs * rhs;
    }
    var out: f64 = @floatCast(acc);
    if (bias) |value| out += value;
    return out;
}

fn evaluateForwardF32(hidden_state: []const f64, weights: []const f64, bias: ?f64) f64 {
    var acc: f32 = 0;
    for (hidden_state, weights) |hidden_value, weight_value| {
        const lhs: f32 = @floatCast(hidden_value);
        const rhs: f32 = @floatCast(weight_value);
        acc = acc + lhs * rhs;
    }
    var out: f64 = @floatCast(acc);
    if (bias) |value| out += value;
    return out;
}

fn evaluateForwardF64(hidden_state: []const f64, weights: []const f64, bias: ?f64) f64 {
    var acc: f64 = 0;
    for (hidden_state, weights) |hidden_value, weight_value| {
        acc += hidden_value * weight_value;
    }
    if (bias) |value| acc += value;
    return acc;
}

fn selectedIndex(logits: []const f64) usize {
    var best_index: usize = 0;
    var best_value = logits[0];
    for (logits[1..], 1..) |value, index| {
        if (value > best_value) {
            best_value = value;
            best_index = index;
        }
    }
    return best_index;
}

fn appendReceiptCandidates(
    allocator: std.mem.Allocator,
    request: Request,
    fast_logits: []const f64,
    stable_logits: []const f64,
    reference_logits: []const f64,
) ![]ReceiptCandidate {
    var candidates = std.ArrayList(ReceiptCandidate).empty;
    defer candidates.deinit(allocator);
    for (request.candidates, 0..) |candidate, index| {
        try candidates.append(allocator, .{
            .tokenId = candidate.tokenId,
            .label = candidate.label,
            .fastLogit = fast_logits[index],
            .stableLogit = stable_logits[index],
            .referenceLogit = reference_logits[index],
        });
    }
    return try candidates.toOwnedSlice(allocator);
}

fn buildDecisionCounts(route_decision: []const u8) trace_numeric_stability.TraceNumericStabilityDecisionCounts {
    var counts = trace_numeric_stability.TraceNumericStabilityDecisionCounts{};
    if (std.mem.eql(u8, route_decision, "accept-fast")) {
        counts.accept_fast = 1;
    } else if (std.mem.eql(u8, route_decision, "prefer-stable")) {
        counts.prefer_stable = 1;
    } else if (std.mem.eql(u8, route_decision, "abstain")) {
        counts.abstain = 1;
    }
    return counts;
}

fn writeReceiptJsonl(allocator: std.mem.Allocator, receipt_path: []const u8, receipt: Receipt) !void {
    try ensureParentPath(receipt_path);
    const payload = try common.jsonStringifyAlloc(allocator, receipt);
    defer allocator.free(payload);
    const file = try std.fs.cwd().createFile(receipt_path, .{ .truncate = true });
    defer file.close();
    try file.writeAll(payload);
    try file.writeAll("\n");
}

fn writeTraceMetaJson(
    allocator: std.mem.Allocator,
    trace_meta_path: []const u8,
    summary: trace_numeric_stability.TraceNumericStabilitySummary,
) !void {
    const hashless = HashlessTraceMeta{
        .traceVersion = 1,
        .module = MODULE_ID,
        .seqMax = 0,
        .rowCount = 0,
        .numericStability = summary,
    };
    const hash_hex = try common.stableHashJsonAlloc(allocator, hashless);
    defer allocator.free(hash_hex);
    const hash_value = try std.fmt.allocPrint(allocator, "sha256:{s}", .{hash_hex});
    defer allocator.free(hash_value);
    const meta = TraceMetaFile{
        .traceVersion = hashless.traceVersion,
        .module = hashless.module,
        .seqMax = hashless.seqMax,
        .rowCount = hashless.rowCount,
        .hash = hash_value,
        .previousHash = ZERO_HASH,
        .numericStability = hashless.numericStability,
    };
    try ensureParentPath(trace_meta_path);
    const payload = try common.jsonStringifyAlloc(allocator, meta);
    defer allocator.free(payload);
    const file = try std.fs.cwd().createFile(trace_meta_path, .{ .truncate = true });
    defer file.close();
    try file.writeAll(payload);
    try file.writeAll("\n");
}

pub fn execute(allocator: std.mem.Allocator, request: Request, policy: Policy) !Result {
    try ensureValidRequest(request);
    try ensureValidPolicy(policy);

    const trigger_policy = try numeric_stability_policy.resolveTriggerPolicy(policy.registry, request.triggerPolicyId);
    const routing_policy = try numeric_stability_policy.resolveRoutingPolicy(policy.registry, request.routingPolicyId, request.triggerPolicyId);
    if (!containsString(policy.registry.routeDecisions, routing_policy.triggeredDecision)) {
        return error.UnsupportedRouteDecision;
    }
    if (!containsString(policy.registry.routeDecisions, routing_policy.fallbackDecision)) {
        return error.UnsupportedRouteDecision;
    }

    const start_ns = std.time.nanoTimestamp();
    var fast_logits = try allocator.alloc(f64, request.candidates.len);
    defer allocator.free(fast_logits);
    var stable_logits = try allocator.alloc(f64, request.candidates.len);
    defer allocator.free(stable_logits);
    var reference_logits = try allocator.alloc(f64, request.candidates.len);
    defer allocator.free(reference_logits);

    for (request.candidates, 0..) |candidate, index| {
        fast_logits[index] = evaluateForwardF16(request.hiddenState, candidate.weights, candidate.bias);
        stable_logits[index] = evaluateForwardF32(request.hiddenState, candidate.weights, candidate.bias);
        reference_logits[index] = evaluateForwardF64(request.hiddenState, candidate.weights, candidate.bias);
    }
    const end_ns = std.time.nanoTimestamp();
    const elapsed_ns = @as(u64, @intCast(end_ns - start_ns));

    const fast_digest = try common.stableHashJsonAlloc(allocator, fast_logits);
    var free_fast_digest = true;
    defer if (free_fast_digest) allocator.free(fast_digest);
    const stable_digest = try common.stableHashJsonAlloc(allocator, stable_logits);
    var free_stable_digest = true;
    defer if (free_stable_digest) allocator.free(stable_digest);

    const fast_index = selectedIndex(fast_logits);
    const stable_index = selectedIndex(stable_logits);
    const reference_index = selectedIndex(reference_logits);
    const fast_token = request.candidates[fast_index].tokenId;
    const stable_token = request.candidates[stable_index].tokenId;
    const reference_token = request.candidates[reference_index].tokenId;

    const first_divergence = if (std.mem.eql(u8, fast_digest, stable_digest))
        null
    else blk: {
        free_fast_digest = false;
        free_stable_digest = false;
        break :blk FirstDivergence{
            .semanticOpId = request.semanticOpId,
            .semanticStage = request.semanticStage,
            .semanticPhase = request.semanticPhase,
            .fastDigest = fast_digest,
            .stableDigest = stable_digest,
        };
    };

    const trigger_checks = TriggerChecks{
        .firstDivergencePresent = first_divergence != null,
        .sensitiveOperatorMatched = first_divergence != null and containsString(trigger_policy.allowedSensitiveOperators, request.semanticOpId),
        .selectedTokenDisagreement = fast_token != stable_token,
        .stableMatchesExactReference = stable_token == reference_token,
        .fastMissesExactReference = fast_token != reference_token,
    };

    const trigger_fired =
        (!trigger_policy.requireFirstDivergence or trigger_checks.firstDivergencePresent) and
        trigger_checks.sensitiveOperatorMatched and
        (!trigger_policy.requireSelectedTokenDisagreement or trigger_checks.selectedTokenDisagreement) and
        (!trigger_policy.requireStableMatchesExactReference or trigger_checks.stableMatchesExactReference) and
        (!trigger_policy.requireFastMissesExactReference or trigger_checks.fastMissesExactReference);

    const route_decision = if (trigger_fired) routing_policy.triggeredDecision else routing_policy.fallbackDecision;
    const route_metadata = try numeric_stability_policy.resolveRouteDecisionMetadata(policy.registry, route_decision);
    const selected_policy_id: ?[]const u8 = if (std.mem.eql(u8, route_metadata.selectionMode, numeric_stability_policy.SELECTION_MODE_STABLE))
        request.stablePolicyId
    else if (std.mem.eql(u8, route_metadata.selectionMode, numeric_stability_policy.SELECTION_MODE_FAST))
        request.fastPolicyId
    else
        null;
    const selected_token: ?u32 = if (std.mem.eql(u8, route_metadata.selectionMode, numeric_stability_policy.SELECTION_MODE_STABLE))
        stable_token
    else if (std.mem.eql(u8, route_metadata.selectionMode, numeric_stability_policy.SELECTION_MODE_FAST))
        fast_token
    else
        null;

    const receipt_candidates = try appendReceiptCandidates(allocator, request, fast_logits, stable_logits, reference_logits);
    errdefer allocator.free(receipt_candidates);

    const receipt = Receipt{
        .schemaVersion = 1,
        .mode = "numeric-stability",
        .operatorFamily = request.operatorFamily,
        .semanticOpId = request.semanticOpId,
        .semanticStage = request.semanticStage,
        .semanticPhase = request.semanticPhase,
        .policyRegistryPath = policy.policyRegistryPath,
        .policyRegistryVersion = policy.registry.registryVersion,
        .routeTaxonomyVersion = policy.registry.routeTaxonomyVersion,
        .proofArtifactPath = policy.registry.proofArtifactPath,
        .triggerPolicyId = request.triggerPolicyId,
        .routingPolicyId = request.routingPolicyId,
        .fastPolicyId = request.fastPolicyId,
        .stablePolicyId = request.stablePolicyId,
        .referencePolicyId = REFERENCE_POLICY_ID,
        .candidates = receipt_candidates,
        .firstDivergence = first_divergence,
        .selectedToken = .{
            .fast = fast_token,
            .stable = stable_token,
            .reference = reference_token,
            .fastMatchesReference = fast_token == reference_token,
            .stableMatchesReference = stable_token == reference_token,
        },
        .trigger = .{
            .fired = trigger_fired,
            .checks = trigger_checks,
            .proofLinks = trigger_policy.proofLinks,
        },
        .route = .{
            .decision = route_decision,
            .selectionMode = route_metadata.selectionMode,
            .selectedPolicyId = selected_policy_id,
            .selectedToken = selected_token,
            .proofLinks = routing_policy.proofLinks,
            .selectionProofLinks = route_metadata.proofLinks,
        },
    };

    if (request.receiptPath) |receipt_path| {
        try writeReceiptJsonl(allocator, receipt_path, receipt);
    }

    if (request.traceMetaPath) |trace_meta_path| {
        const summary = trace_numeric_stability.TraceNumericStabilitySummary{
            .policy_registry_path = policy.policyRegistryPath,
            .policy_registry_version = policy.registry.registryVersion,
            .route_taxonomy_version = policy.registry.routeTaxonomyVersion,
            .receipt_path = request.receiptPath orelse "",
            .receipt_count = if (request.receiptPath != null) 1 else 0,
            .decision_counts = buildDecisionCounts(route_decision),
            .first_divergence_present_count = if (first_divergence != null) 1 else 0,
        };
        try writeTraceMetaJson(allocator, trace_meta_path, summary);
    }

    const payload = ResultNoTrace{
        .schemaVersion = 1,
        .moduleId = MODULE_ID,
        .artifactKind = "result",
        .serviceId = request.serviceId,
        .serviceResult = .{ .status = "ok" },
        .executionStats = .{
            .dispatchCount = 0,
            .bytesMoved = totalBytesMoved(request),
            .candidateCount = request.candidates.len,
        },
        .timingStats = .{
            .setupNs = 0,
            .encodeNs = 0,
            .submitNs = 0,
            .dispatchNs = elapsed_ns,
        },
        .failureDetails = .{ .code = "none" },
        .routeDecision = route_decision,
        .selectedToken = selected_token,
        .receiptPath = request.receiptPath,
        .traceMetaPath = request.traceMetaPath,
        .receipt = receipt,
    };

    const request_hash = try common.stableHashJsonAlloc(allocator, request);
    errdefer allocator.free(request_hash);
    const policy_hash = try common.stableHashJsonAlloc(allocator, policy);
    errdefer allocator.free(policy_hash);
    const result_hash = try common.stableHashJsonAlloc(allocator, payload);

    return .{
        .schemaVersion = payload.schemaVersion,
        .moduleId = payload.moduleId,
        .artifactKind = payload.artifactKind,
        .serviceId = payload.serviceId,
        .serviceResult = payload.serviceResult,
        .executionStats = payload.executionStats,
        .timingStats = payload.timingStats,
        .failureDetails = payload.failureDetails,
        .routeDecision = payload.routeDecision,
        .selectedToken = payload.selectedToken,
        .receiptPath = payload.receiptPath,
        .traceMetaPath = payload.traceMetaPath,
        .receipt = payload.receipt,
        .traceLink = .{
            .moduleIdentity = MODULE_ID,
            .requestHash = request_hash,
            .policyHash = policy_hash,
            .resultHash = result_hash,
        },
    };
}

test "prefer-stable fires when stable matches reference and fast misses" {
    const allocator = std.testing.allocator;
    const request = Request{
        .schemaVersion = 1,
        .moduleId = MODULE_ID,
        .artifactKind = "request",
        .serviceId = MATMUL_LOGITS_SLICE_SERVICE_ID,
        .operatorFamily = SUPPORTED_OPERATOR_FAMILY,
        .semanticOpId = SUPPORTED_SEMANTIC_OP_ID,
        .semanticStage = "lm_head_slice",
        .semanticPhase = "logits",
        .triggerPolicyId = "numeric-instability/selected-token-disagreement-with-reference-improvement-v1",
        .routingPolicyId = "numeric-stability/prefer-stable-on-selected-token-disagreement-v1",
        .fastPolicyId = SUPPORTED_FAST_POLICY_ID,
        .stablePolicyId = SUPPORTED_STABLE_POLICY_ID,
        .hiddenState = &.{ 1.0, 1.0, 1.0 },
        .candidates = &.{
            .{
                .tokenId = 11,
                .label = "keep",
                .weights = &.{ 10000.0, 0.01, -10000.0 },
            },
            .{
                .tokenId = 22,
                .label = "flip",
                .weights = &.{ 0.0, 0.001, 0.0 },
            },
        },
    };
    const policy = Policy{
        .policyRegistryPath = "config/numeric-stability-policy.json",
        .registry = .{
            .schemaVersion = 2,
            .registryVersion = "2026-03-29-route-taxonomy-v2",
            .routeTaxonomyVersion = "numeric-stability-routes-v1",
            .proofArtifactPath = "pipeline/lean/artifacts/proven-conditions.json",
            .routeDecisions = &.{ "accept-fast", "prefer-stable", "abstain" },
            .routeDecisionMetadata = &.{
                .{ .decision = "accept-fast", .selectionMode = "fast", .proofLinks = &.{} },
                .{ .decision = "prefer-stable", .selectionMode = "stable", .proofLinks = &.{} },
                .{ .decision = "abstain", .selectionMode = "none", .proofLinks = &.{} },
            },
            .triggerPolicies = &.{
                .{
                    .triggerPolicyId = request.triggerPolicyId,
                    .requireFirstDivergence = true,
                    .requireSelectedTokenDisagreement = true,
                    .requireStableMatchesExactReference = true,
                    .requireFastMissesExactReference = true,
                    .allowedSensitiveOperators = &.{SUPPORTED_SEMANTIC_OP_ID},
                    .proofLinks = &.{},
                },
            },
            .routingPolicies = &.{
                .{
                    .policyId = request.routingPolicyId,
                    .triggerPolicyId = request.triggerPolicyId,
                    .triggeredDecision = "prefer-stable",
                    .fallbackDecision = "accept-fast",
                    .proofLinks = &.{},
                },
            },
        },
    };

    const result = try execute(allocator, request, policy);
    try std.testing.expectEqualStrings("prefer-stable", result.routeDecision);
    try std.testing.expectEqual(@as(?u32, 11), result.selectedToken);
    try std.testing.expectEqualStrings("numeric-stability-routes-v1", result.receipt.routeTaxonomyVersion);
    try std.testing.expectEqualStrings(numeric_stability_policy.SELECTION_MODE_STABLE, result.receipt.route.selectionMode);
}

test "accept-fast falls back when no divergence is present" {
    const allocator = std.testing.allocator;
    const request = Request{
        .schemaVersion = 1,
        .moduleId = MODULE_ID,
        .artifactKind = "request",
        .serviceId = MATMUL_LOGITS_SLICE_SERVICE_ID,
        .operatorFamily = SUPPORTED_OPERATOR_FAMILY,
        .semanticOpId = SUPPORTED_SEMANTIC_OP_ID,
        .semanticStage = "lm_head_slice",
        .semanticPhase = "logits",
        .triggerPolicyId = "numeric-instability/selected-token-disagreement-with-reference-improvement-v1",
        .routingPolicyId = "numeric-stability/prefer-stable-on-selected-token-disagreement-v1",
        .fastPolicyId = SUPPORTED_FAST_POLICY_ID,
        .stablePolicyId = SUPPORTED_STABLE_POLICY_ID,
        .hiddenState = &.{ 1.0, 2.0 },
        .candidates = &.{
            .{
                .tokenId = 1,
                .label = "fast",
                .weights = &.{ 0.25, 0.75 },
            },
            .{
                .tokenId = 2,
                .label = "slow",
                .weights = &.{ 0.1, 0.2 },
            },
        },
    };
    const policy = Policy{
        .policyRegistryPath = "config/numeric-stability-policy.json",
        .registry = .{
            .schemaVersion = 2,
            .registryVersion = "2026-03-29-route-taxonomy-v2",
            .routeTaxonomyVersion = "numeric-stability-routes-v1",
            .proofArtifactPath = "pipeline/lean/artifacts/proven-conditions.json",
            .routeDecisions = &.{ "accept-fast", "prefer-stable", "abstain" },
            .routeDecisionMetadata = &.{
                .{ .decision = "accept-fast", .selectionMode = "fast", .proofLinks = &.{} },
                .{ .decision = "prefer-stable", .selectionMode = "stable", .proofLinks = &.{} },
                .{ .decision = "abstain", .selectionMode = "none", .proofLinks = &.{} },
            },
            .triggerPolicies = &.{
                .{
                    .triggerPolicyId = request.triggerPolicyId,
                    .requireFirstDivergence = true,
                    .requireSelectedTokenDisagreement = true,
                    .requireStableMatchesExactReference = true,
                    .requireFastMissesExactReference = true,
                    .allowedSensitiveOperators = &.{SUPPORTED_SEMANTIC_OP_ID},
                    .proofLinks = &.{},
                },
            },
            .routingPolicies = &.{
                .{
                    .policyId = request.routingPolicyId,
                    .triggerPolicyId = request.triggerPolicyId,
                    .triggeredDecision = "prefer-stable",
                    .fallbackDecision = "accept-fast",
                    .proofLinks = &.{},
                },
            },
        },
    };

    const result = try execute(allocator, request, policy);
    try std.testing.expectEqualStrings("accept-fast", result.routeDecision);
    try std.testing.expectEqual(@as(?u32, 1), result.selectedToken);
    try std.testing.expectEqualStrings(numeric_stability_policy.SELECTION_MODE_FAST, result.receipt.route.selectionMode);
}
