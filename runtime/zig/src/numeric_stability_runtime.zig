const std = @import("std");
const execution = @import("execution.zig");
const numeric_stability_annotation = @import("numeric_stability_annotation.zig");
const numeric_stability_policy = @import("numeric_stability_policy.zig");
const semantic_trace = @import("semantic_trace.zig");
const trace_numeric_stability = @import("trace_numeric_stability.zig");
const common = @import("full/modules/common.zig");
const numeric_stability_service = @import("full/modules/services/numeric_stability.zig");

const RECEIPT_PATH_SUFFIX = ".numeric-stability.jsonl";
const F32_BYTE_WIDTH: u64 = @sizeOf(f32);

pub const Recorder = struct {
    allocator: std.mem.Allocator,
    loaded_registry: ?numeric_stability_policy.LoadedRegistry = null,
    receipt_path: ?[]u8 = null,
    receipt_file: ?std.fs.File = null,
    receipt_count: u32 = 0,
    first_divergence_present_count: u32 = 0,
    decision_counts: trace_numeric_stability.TraceNumericStabilityDecisionCounts = .{},

    pub fn init(allocator: std.mem.Allocator, anchor: ?[]const u8) !Recorder {
        if (anchor == null) {
            return .{ .allocator = allocator };
        }
        var loaded_registry = try numeric_stability_policy.loadRegistry(
            allocator,
            numeric_stability_annotation.DEFAULT_POLICY_PATH,
        );
        errdefer loaded_registry.deinit(allocator);
        return .{
            .allocator = allocator,
            .loaded_registry = loaded_registry,
            .receipt_path = try std.mem.concat(allocator, u8, &.{ anchor.?, RECEIPT_PATH_SUFFIX }),
        };
    }

    pub fn deinit(self: *Recorder) void {
        if (self.receipt_file) |file| {
            file.close();
            self.receipt_file = null;
        }
        if (self.receipt_path) |path| self.allocator.free(path);
        if (self.loaded_registry) |*loaded_registry| {
            loaded_registry.deinit(self.allocator);
        }
        self.receipt_path = null;
        self.loaded_registry = null;
    }

    pub fn enabled(self: *const Recorder) bool {
        return self.loaded_registry != null and self.receipt_path != null;
    }

    pub fn hasEvents(self: *const Recorder) bool {
        return self.receipt_count > 0;
    }

    pub fn record(
        self: *Recorder,
        execution_context: *execution.ExecutionContext,
        semantic: semantic_trace.SemanticContext,
        annotation: numeric_stability_annotation.Annotation,
    ) !void {
        if (!self.enabled()) return error.NumericStabilityRecorderDisabled;
        if (semantic.op_id == null or semantic.stage == null or semantic.phase == null) {
            return error.NumericStabilityMissingSemanticContext;
        }
        try ensureValidAnnotation(annotation, semantic);

        var arena = std.heap.ArenaAllocator.init(self.allocator);
        defer arena.deinit();
        const allocator = arena.allocator();

        const hidden_state = try captureVector(
            allocator,
            execution_context,
            annotation.hidden_state.buffer_handle,
            annotation.hidden_state.offset,
            annotation.hidden_state.element_count,
        );
        const fast_logits = try captureVector(
            allocator,
            execution_context,
            annotation.logits.buffer_handle,
            annotation.logits.offset,
            annotation.logits.element_count,
        );
        if (fast_logits.len != annotation.candidates.len) {
            return error.NumericStabilityLogitCountMismatch;
        }

        var stable_logits = try allocator.alloc(f64, annotation.candidates.len);
        var reference_logits = try allocator.alloc(f64, annotation.candidates.len);
        for (annotation.candidates, 0..) |candidate, index| {
            const weights = try captureWeightsRow(allocator, execution_context, annotation, candidate, hidden_state.len);
            stable_logits[index] = evaluateForwardF32(hidden_state, weights, candidate.bias);
            reference_logits[index] = evaluateForwardF64(hidden_state, weights, candidate.bias);
        }

        const fast_digest = try common.stableHashJsonAlloc(allocator, fast_logits);
        const stable_digest = try common.stableHashJsonAlloc(allocator, stable_logits);

        const fast_index = selectedIndex(fast_logits);
        const stable_index = selectedIndex(stable_logits);
        const reference_index = selectedIndex(reference_logits);
        const fast_token = annotation.candidates[fast_index].token_id;
        const stable_token = annotation.candidates[stable_index].token_id;
        const reference_token = annotation.candidates[reference_index].token_id;

        const first_divergence = if (std.mem.eql(u8, fast_digest, stable_digest))
            null
        else
            numeric_stability_service.FirstDivergence{
                .semanticOpId = semantic.op_id.?,
                .semanticStage = semantic.stage.?,
                .semanticPhase = semantic.phase.?,
                .fastDigest = fast_digest,
                .stableDigest = stable_digest,
            };

        const registry = self.loaded_registry.?.parsed.value;
        const trigger_policy = try numeric_stability_policy.resolveTriggerPolicy(
            registry,
            annotation.trigger_policy_id,
        );
        const routing_policy = try numeric_stability_policy.resolveRoutingPolicy(
            registry,
            annotation.routing_policy_id,
            annotation.trigger_policy_id,
        );
        const trigger_checks = numeric_stability_service.TriggerChecks{
            .firstDivergencePresent = first_divergence != null,
            .sensitiveOperatorMatched = first_divergence != null and
                containsString(trigger_policy.allowedSensitiveOperators, semantic.op_id.?),
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

        const route_decision = if (trigger_fired)
            routing_policy.triggeredDecision
        else
            routing_policy.fallbackDecision;
        const route_metadata = try numeric_stability_policy.resolveRouteDecisionMetadata(registry, route_decision);
        const selected_policy_id: ?[]const u8 = if (std.mem.eql(u8, route_metadata.selectionMode, numeric_stability_policy.SELECTION_MODE_STABLE))
            annotation.stable_policy_id
        else if (std.mem.eql(u8, route_metadata.selectionMode, numeric_stability_policy.SELECTION_MODE_FAST))
            annotation.fast_policy_id
        else
            null;
        const selected_token: ?u32 = if (std.mem.eql(u8, route_metadata.selectionMode, numeric_stability_policy.SELECTION_MODE_STABLE))
            stable_token
        else if (std.mem.eql(u8, route_metadata.selectionMode, numeric_stability_policy.SELECTION_MODE_FAST))
            fast_token
        else
            null;

        const receipt = numeric_stability_service.Receipt{
            .schemaVersion = 1,
            .mode = "numeric-stability",
            .operatorFamily = annotation.operator_family,
            .semanticOpId = semantic.op_id.?,
            .semanticStage = semantic.stage.?,
            .semanticPhase = semantic.phase.?,
            .policyRegistryPath = self.loaded_registry.?.policyRegistryPath,
            .policyRegistryVersion = registry.registryVersion,
            .routeTaxonomyVersion = registry.routeTaxonomyVersion,
            .proofArtifactPath = registry.proofArtifactPath,
            .triggerPolicyId = annotation.trigger_policy_id,
            .routingPolicyId = annotation.routing_policy_id,
            .fastPolicyId = annotation.fast_policy_id,
            .stablePolicyId = annotation.stable_policy_id,
            .referencePolicyId = numeric_stability_service.REFERENCE_POLICY_ID,
            .candidates = try buildReceiptCandidates(allocator, annotation, fast_logits, stable_logits, reference_logits),
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

        try self.ensureReceiptFile();
        const payload = try common.jsonStringifyAlloc(allocator, receipt);
        defer allocator.free(payload);
        try self.receipt_file.?.writeAll(payload);
        try self.receipt_file.?.writeAll("\n");

        self.receipt_count += 1;
        if (first_divergence != null) self.first_divergence_present_count += 1;
        updateDecisionCounts(&self.decision_counts, route_decision);
    }

    pub fn summary(self: *const Recorder) ?trace_numeric_stability.TraceNumericStabilitySummary {
        if (!self.enabled() or self.receipt_count == 0) return null;
        return .{
            .policy_registry_path = self.loaded_registry.?.policyRegistryPath,
            .policy_registry_version = self.loaded_registry.?.parsed.value.registryVersion,
            .route_taxonomy_version = self.loaded_registry.?.parsed.value.routeTaxonomyVersion,
            .receipt_path = self.receipt_path.?,
            .receipt_count = self.receipt_count,
            .decision_counts = self.decision_counts,
            .first_divergence_present_count = self.first_divergence_present_count,
        };
    }

    fn ensureReceiptFile(self: *Recorder) !void {
        if (self.receipt_file != null) return;
        const receipt_path = self.receipt_path orelse return error.NumericStabilityRecorderDisabled;
        if (std.fs.path.dirname(receipt_path)) |dir_name| {
            if (dir_name.len != 0) try std.fs.cwd().makePath(dir_name);
        }
        self.receipt_file = try std.fs.cwd().createFile(receipt_path, .{ .truncate = true });
    }
};

fn ensureValidAnnotation(
    annotation: numeric_stability_annotation.Annotation,
    semantic: semantic_trace.SemanticContext,
) !void {
    if (annotation.candidates.len < 2) return error.NumericStabilityCandidateCountInvalid;
    if (annotation.hidden_state.element_count == 0) return error.NumericStabilityHiddenStateInvalid;
    if (annotation.logits.element_count != annotation.candidates.len) return error.NumericStabilityLogitCountMismatch;
    if (annotation.weights.row_stride_elements < annotation.hidden_state.element_count) {
        return error.NumericStabilityWeightsStrideInvalid;
    }
    if (!std.mem.eql(u8, annotation.operator_family, numeric_stability_annotation.DEFAULT_OPERATOR_FAMILY)) {
        return error.NumericStabilityUnsupportedOperatorFamily;
    }
    if (!std.mem.eql(u8, semantic.op_id.?, "matmul.logits")) return error.NumericStabilityUnsupportedSemanticOpId;
}

fn captureVector(
    allocator: std.mem.Allocator,
    execution_context: *execution.ExecutionContext,
    buffer_handle: u64,
    offset: u64,
    element_count: u32,
) ![]f64 {
    const byte_size = @as(u64, element_count) * F32_BYTE_WIDTH;
    const bytes = try execution_context.captureBuffer(allocator, buffer_handle, offset, byte_size);
    defer allocator.free(bytes);
    return try decodeF32Vector(allocator, bytes, element_count);
}

fn captureWeightsRow(
    allocator: std.mem.Allocator,
    execution_context: *execution.ExecutionContext,
    annotation: numeric_stability_annotation.Annotation,
    candidate: numeric_stability_annotation.Candidate,
    hidden_len: usize,
) ![]f64 {
    const row_offset = annotation.weights.offset +
        (@as(u64, candidate.row_index) * @as(u64, annotation.weights.row_stride_elements) * F32_BYTE_WIDTH);
    const byte_size = @as(u64, @intCast(hidden_len)) * F32_BYTE_WIDTH;
    const bytes = try execution_context.captureBuffer(
        allocator,
        annotation.weights.buffer_handle,
        row_offset,
        byte_size,
    );
    defer allocator.free(bytes);
    return try decodeF32Vector(allocator, bytes, @intCast(hidden_len));
}

fn decodeF32Vector(
    allocator: std.mem.Allocator,
    bytes: []const u8,
    element_count: u32,
) ![]f64 {
    if (bytes.len != @as(usize, element_count) * @sizeOf(f32)) return error.NumericStabilityCaptureSizeMismatch;
    var values = try allocator.alloc(f64, element_count);
    var index: usize = 0;
    while (index < element_count) : (index += 1) {
        const start = index * @sizeOf(f32);
        const chunk: *const [4]u8 = @ptrCast(bytes[start .. start + @sizeOf(f32)].ptr);
        const bits = std.mem.readInt(u32, chunk, .little);
        const value: f32 = @bitCast(bits);
        values[index] = @as(f64, @floatCast(value));
    }
    return values;
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

fn buildReceiptCandidates(
    allocator: std.mem.Allocator,
    annotation: numeric_stability_annotation.Annotation,
    fast_logits: []const f64,
    stable_logits: []const f64,
    reference_logits: []const f64,
) ![]numeric_stability_service.ReceiptCandidate {
    var candidates = try allocator.alloc(numeric_stability_service.ReceiptCandidate, annotation.candidates.len);
    for (annotation.candidates, 0..) |candidate, index| {
        candidates[index] = .{
            .tokenId = candidate.token_id,
            .label = candidate.label,
            .fastLogit = fast_logits[index],
            .stableLogit = stable_logits[index],
            .referenceLogit = reference_logits[index],
        };
    }
    return candidates;
}

fn updateDecisionCounts(
    counts: *trace_numeric_stability.TraceNumericStabilityDecisionCounts,
    route_decision: []const u8,
) void {
    if (std.mem.eql(u8, route_decision, "accept-fast")) {
        counts.accept_fast += 1;
    } else if (std.mem.eql(u8, route_decision, "prefer-stable")) {
        counts.prefer_stable += 1;
    } else if (std.mem.eql(u8, route_decision, "abstain")) {
        counts.abstain += 1;
    }
}

fn containsString(values: []const []const u8, needle: []const u8) bool {
    for (values) |value| {
        if (std.mem.eql(u8, value, needle)) return true;
    }
    return false;
}
