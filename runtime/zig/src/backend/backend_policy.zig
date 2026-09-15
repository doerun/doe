//! Config-backed backend selection for build defaults and explicit file loads.

const std = @import("std");
const backend_contract = @import("../contracts/backend.zig");
const runtime_types = @import("../contracts/runtime_types.zig");

pub const BackendLane = backend_contract.BackendLane;
pub const UploadPathPolicy = backend_contract.UploadPathPolicy;
pub const VulkanSubgroupSizePolicy = backend_contract.VulkanSubgroupSizePolicy;
pub const SelectionPolicy = backend_contract.SelectionPolicy;
pub const PolicyTable = std.enums.EnumFieldStruct(BackendLane, SelectionPolicy, null);
pub const lane_name = backend_contract.laneName;
pub const parse_lane = backend_contract.parseLane;

/// The caller frees owned_policy_hash after all users of policy have finished.
pub const LoadedSelectionPolicy = struct {
    policy: SelectionPolicy,
    owned_policy_hash: []u8,
};

pub const DEFAULT_RUNTIME_POLICY_PATH = "config/backend-runtime-policy.json";
pub const MAX_RUNTIME_POLICY_BYTES: usize = 64 * 1024;
const MAX_RUNTIME_POLICY_SEARCH_DEPTH: usize = 4;
const EXPECTED_SCHEMA_VERSION: i64 = 6;

pub const PolicyLoadError = error{InvalidRuntimePolicy};

/// Owns parsed JSON storage; returned policies borrow its hash until deinit.
pub const ParsedPolicyFile = struct {
    parsed: std.json.Parsed(std.json.Value),
    policy_hash: []const u8,
    lanes: std.json.ObjectMap,

    pub fn deinit(self: *const ParsedPolicyFile) void {
        self.parsed.deinit();
    }

    pub fn policy_for_lane(self: *const ParsedPolicyFile, lane: BackendLane) !SelectionPolicy {
        const lane_obj = try require_object(self.lanes.get(lane_name(lane)) orelse return error.InvalidRuntimePolicy);
        const Field = enum { defaultBackend, allowFallback, strictNoFallback, uploadPathPolicy, queueFamilyPolicy, deferredSubmissionSyncPolicy, vulkanSubgroupSizePolicy, notes };
        for (lane_obj.keys()) |key| {
            if (std.meta.stringToEnum(Field, key) == null) return error.InvalidRuntimePolicy;
        }
        if (lane_obj.get("notes")) |notes| _ = try require_string(notes);
        const backend_id = std.meta.stringToEnum(backend_contract.BackendId, try field_string(lane_obj, "defaultBackend")) orelse return error.InvalidRuntimePolicy;
        const allow_fallback = try field_bool(lane_obj, "allowFallback");
        const strict_no_fallback = try field_bool(lane_obj, "strictNoFallback");
        if (allow_fallback or !strict_no_fallback) return error.InvalidRuntimePolicy;
        const upload_path_policy = if (lane_obj.get("uploadPathPolicy")) |value|
            parse_upload_path_policy(try require_string(value)) orelse return error.InvalidRuntimePolicy
        else
            UploadPathPolicy.allow_mapped_shortcuts;
        if (strict_staged_upload_policy_required(lane) and upload_path_policy != .staged_copy_only) return error.InvalidRuntimePolicy;
        return .{
            .lane = lane,
            .default_backend = backend_id,
            .allow_fallback = allow_fallback,
            .strict_no_fallback = strict_no_fallback,
            .policy_hash = self.policy_hash,
            .upload_path_policy = upload_path_policy,
            .queue_family_policy = parse_queue_family_policy(try field_string(lane_obj, "queueFamilyPolicy")) orelse return error.InvalidRuntimePolicy,
            .deferred_submission_sync_policy = parse_deferred_submission_sync_policy(try field_string(lane_obj, "deferredSubmissionSyncPolicy")) orelse return error.InvalidRuntimePolicy,
            .vulkan_subgroup_size_policy = if (lane_obj.get("vulkanSubgroupSizePolicy")) |value|
                parse_vulkan_subgroup_size_policy(try require_string(value)) orelse return error.InvalidRuntimePolicy
            else
                default_vulkan_subgroup_size_policy(lane),
        };
    }

    pub fn complete_table(self: *const ParsedPolicyFile) !PolicyTable {
        var result: PolicyTable = undefined;
        inline for (@typeInfo(BackendLane).@"enum".fields) |field| {
            @field(result, field.name) = try self.policy_for_lane(@enumFromInt(field.value));
        }
        return result;
    }
};

pub fn parse_policy(allocator: std.mem.Allocator, bytes: []const u8) !ParsedPolicyFile {
    const parsed = try std.json.parseFromSlice(std.json.Value, allocator, bytes, .{});
    errdefer parsed.deinit();
    const root = try require_object(parsed.value);
    const Field = enum { schemaVersion, defaultLane, selectionPolicyHashSeed, cutoverPolicyPath, lanes };
    for (root.keys()) |key| {
        if (std.meta.stringToEnum(Field, key) == null) return error.InvalidRuntimePolicy;
    }
    const version = root.get("schemaVersion") orelse return error.InvalidRuntimePolicy;
    if (version != .integer or version.integer != EXPECTED_SCHEMA_VERSION) return error.InvalidRuntimePolicy;
    const policy_hash = try field_string(root, "selectionPolicyHashSeed");
    if (policy_hash.len == 0) return error.InvalidRuntimePolicy;
    if (root.get("cutoverPolicyPath")) |path| {
        if ((try require_string(path)).len == 0) return error.InvalidRuntimePolicy;
    }
    const lanes = try require_object(root.get("lanes") orelse return error.InvalidRuntimePolicy);
    const default_lane = try field_string(root, "defaultLane");
    if (std.meta.stringToEnum(BackendLane, default_lane) == null or !lanes.contains(default_lane)) return error.InvalidRuntimePolicy;
    const result: ParsedPolicyFile = .{ .parsed = parsed, .policy_hash = policy_hash, .lanes = lanes };
    for (lanes.keys()) |name| {
        const lane = std.meta.stringToEnum(BackendLane, name) orelse return error.InvalidRuntimePolicy;
        _ = try result.policy_for_lane(lane);
    }
    return result;
}

fn require_object(value: std.json.Value) !std.json.ObjectMap {
    return switch (value) {
        .object => |object| object,
        else => error.InvalidRuntimePolicy,
    };
}

fn require_string(value: std.json.Value) ![]const u8 {
    return switch (value) {
        .string => |string| string,
        else => error.InvalidRuntimePolicy,
    };
}

fn field_string(object: std.json.ObjectMap, name: []const u8) ![]const u8 {
    return require_string(object.get(name) orelse return error.InvalidRuntimePolicy);
}

fn field_bool(object: std.json.ObjectMap, name: []const u8) !bool {
    return switch (object.get(name) orelse return error.InvalidRuntimePolicy) {
        .bool => |value| value,
        else => error.InvalidRuntimePolicy,
    };
}

pub fn load_policy_for_lane(allocator: std.mem.Allocator, policy_path: []const u8, lane: BackendLane) !LoadedSelectionPolicy {
    const bytes = try read_policy_file_alloc(allocator, policy_path);
    defer allocator.free(bytes);
    const parsed = try parse_policy(allocator, bytes);
    defer parsed.deinit();
    var policy = try parsed.policy_for_lane(lane);
    const owned_policy_hash = try allocator.dupe(u8, policy.policy_hash);
    policy.policy_hash = owned_policy_hash;
    return .{ .policy = policy, .owned_policy_hash = owned_policy_hash };
}

fn read_policy_file_alloc(allocator: std.mem.Allocator, policy_path: []const u8) ![]u8 {
    if (std.fs.path.isAbsolute(policy_path)) {
        return std.fs.cwd().readFileAlloc(allocator, policy_path, MAX_RUNTIME_POLICY_BYTES);
    }
    var candidate_buffer: [std.fs.max_path_bytes]u8 = undefined;
    var depth: usize = 0;
    while (depth <= MAX_RUNTIME_POLICY_SEARCH_DEPTH) : (depth += 1) {
        const candidate = if (depth == 0) policy_path else blk: {
            const prefix_len = depth * "../".len;
            if (policy_path.len > candidate_buffer.len - prefix_len) return error.NameTooLong;
            var index: usize = 0;
            while (index < depth) : (index += 1) {
                const start = index * "../".len;
                @memcpy(candidate_buffer[start .. start + "../".len], "../");
            }
            @memcpy(candidate_buffer[prefix_len .. prefix_len + policy_path.len], policy_path);
            break :blk candidate_buffer[0 .. prefix_len + policy_path.len];
        };
        return std.fs.cwd().readFileAlloc(allocator, candidate, MAX_RUNTIME_POLICY_BYTES) catch |err| switch (err) {
            error.FileNotFound => continue,
            else => return err,
        };
    }
    return error.FileNotFound;
}

pub fn default_policy_for_lane(lane: BackendLane) SelectionPolicy {
    const compiled = @import("build_options").backend_runtime_policy;
    return switch (lane) {
        inline else => |selected| blk: {
            const entry = @field(compiled, @tagName(selected));
            var policy: SelectionPolicy = undefined;
            inline for (@typeInfo(SelectionPolicy).@"struct".fields) |field| {
                const value = @field(entry, field.name);
                @field(policy, field.name) = switch (@typeInfo(field.type)) {
                    .@"enum" => @field(field.type, @tagName(value)),
                    else => value,
                };
            }
            break :blk policy;
        },
    };
}

fn parse_upload_path_policy(raw: []const u8) ?UploadPathPolicy {
    return std.meta.stringToEnum(UploadPathPolicy, raw);
}

fn parse_queue_family_policy(raw: []const u8) ?runtime_types.QueueFamilyPolicy {
    return std.meta.stringToEnum(runtime_types.QueueFamilyPolicy, raw);
}

fn parse_deferred_submission_sync_policy(raw: []const u8) ?runtime_types.DeferredSubmissionSyncPolicy {
    return std.meta.stringToEnum(runtime_types.DeferredSubmissionSyncPolicy, raw);
}

fn parse_vulkan_subgroup_size_policy(raw: []const u8) ?VulkanSubgroupSizePolicy {
    return std.meta.stringToEnum(VulkanSubgroupSizePolicy, raw);
}

fn default_vulkan_subgroup_size_policy(lane: BackendLane) VulkanSubgroupSizePolicy {
    return switch (lane) {
        .vulkan_doe_app,
        .vulkan_doe_comparable,
        .vulkan_doe_compute_only_diagnostic,
        .vulkan_doe_compute_only_fence_diagnostic,
        .vulkan_doe_release,
        => .suppress_for_workgroup_memory_256_or_single_invocation,
        else => .fixed_32_when_supported,
    };
}

fn strict_staged_upload_policy_required(lane: BackendLane) bool {
    return switch (lane) {
        .metal_doe_comparable,
        .metal_doe_release,
        .metal_webkit_comparable,
        .vulkan_doe_comparable,
        .vulkan_doe_compute_only_diagnostic,
        .vulkan_doe_compute_only_fence_diagnostic,
        .vulkan_doe_release,
        .d3d12_doe_comparable,
        .d3d12_doe_release,
        => true,
        else => false,
    };
}

const testing = std.testing;

test "lane table round-trips canonical and alias names" {
    try testing.expectEqualStrings("metal_webkit_comparable", lane_name(.metal_webkit_comparable));
    try testing.expectEqual(@as(?BackendLane, .metal_webkit_comparable), parse_lane("metal_webkit_comparable"));
    try testing.expectEqual(@as(?BackendLane, .metal_webkit_comparable), parse_lane("metal-webkit-comparable"));
    try testing.expectEqual(@as(?BackendLane, .vulkan_dawn_release), parse_lane("vulkan_dawn_directional"));
    try testing.expectEqual(@as(?BackendLane, .vulkan_doe_compute_only_fence_diagnostic), parse_lane("vulkan-doe-compute-only-fence-diagnostic"));
}

test "default Vulkan comparable policy declares graphics compute queue preference" {
    const policy = default_policy_for_lane(.vulkan_doe_comparable);
    try testing.expectEqual(runtime_types.QueueFamilyPolicy.prefer_graphics_compute, policy.queue_family_policy);
    try testing.expectEqual(UploadPathPolicy.staged_copy_only, policy.upload_path_policy);
    try testing.expectEqual(runtime_types.DeferredSubmissionSyncPolicy.prefer_timeline_semaphore, policy.deferred_submission_sync_policy);
}

test "default Vulkan compute-only diagnostic policy requires compute queue and staged uploads" {
    const policy = default_policy_for_lane(.vulkan_doe_compute_only_diagnostic);
    try testing.expectEqual(runtime_types.QueueFamilyPolicy.require_compute_only, policy.queue_family_policy);
    try testing.expectEqual(UploadPathPolicy.staged_copy_only, policy.upload_path_policy);
    try testing.expectEqual(runtime_types.DeferredSubmissionSyncPolicy.prefer_timeline_semaphore, policy.deferred_submission_sync_policy);
}

test "default Vulkan compute-only fence diagnostic policy requires fence pool" {
    const policy = default_policy_for_lane(.vulkan_doe_compute_only_fence_diagnostic);
    try testing.expectEqual(runtime_types.QueueFamilyPolicy.require_compute_only, policy.queue_family_policy);
    try testing.expectEqual(UploadPathPolicy.staged_copy_only, policy.upload_path_policy);
    try testing.expectEqual(runtime_types.DeferredSubmissionSyncPolicy.require_fence_pool, policy.deferred_submission_sync_policy);
}

test "backend runtime policy: compiled defaults match the config for every lane" {
    inline for (@typeInfo(BackendLane).@"enum".fields) |field| {
        const lane: BackendLane = @enumFromInt(field.value);
        const loaded = try load_policy_for_lane(testing.allocator, DEFAULT_RUNTIME_POLICY_PATH, lane);
        defer testing.allocator.free(loaded.owned_policy_hash);
        try testing.expectEqualDeep(loaded.policy, default_policy_for_lane(lane));
    }
}

const TEST_POLICY =
    \\{"schemaVersion":6,"defaultLane":"vulkan_doe_app","selectionPolicyHashSeed":"policy-\u0061","lanes":{"vulkan_doe_app":{"defaultBackend":"doe_vulkan","allowFallback":false,"strictNoFallback":true,"queueFamilyPolicy":"prefer_graphics_compute","deferredSubmissionSyncPolicy":"require_fence_pool"}}}
;

fn check_parsed_policy_allocations(allocator: std.mem.Allocator) !void {
    const parsed = try parse_policy(allocator, TEST_POLICY);
    defer parsed.deinit();
    const policy = try parsed.policy_for_lane(.vulkan_doe_app);
    try testing.expectEqualStrings("policy-a", policy.policy_hash);
    try testing.expectEqual(runtime_types.DeferredSubmissionSyncPolicy.require_fence_pool, policy.deferred_submission_sync_policy);
    try testing.expectError(error.InvalidRuntimePolicy, parsed.complete_table());
}

test "backend runtime policy: parser ownership and incomplete build table survive allocation failures" {
    try testing.checkAllAllocationFailures(testing.allocator, check_parsed_policy_allocations, .{});
}

fn check_loaded_policy_allocations(allocator: std.mem.Allocator, path: []const u8) !void {
    const loaded = try load_policy_for_lane(allocator, path, .vulkan_doe_app);
    defer allocator.free(loaded.owned_policy_hash);
    try testing.expectEqualStrings("policy-a", loaded.policy.policy_hash);
    try testing.expectEqual(loaded.owned_policy_hash.ptr, loaded.policy.policy_hash.ptr);
}

test "backend runtime policy: file loading owns the surviving hash and preserves allocation failures" {
    var temp = testing.tmpDir(.{});
    defer temp.cleanup();
    try temp.dir.writeFile(.{ .sub_path = "policy.json", .data = TEST_POLICY });
    const path = try temp.dir.realpathAlloc(testing.allocator, "policy.json");
    defer testing.allocator.free(path);
    try testing.checkAllAllocationFailures(testing.allocator, check_loaded_policy_allocations, .{path});
    try temp.dir.deleteFile("policy.json");
    try testing.expectError(error.FileNotFound, load_policy_for_lane(testing.allocator, path, .vulkan_doe_app));
}

test "backend runtime policy: rejects malformed fields and undeclared choices" {
    const replacements = .{
        .{ "\"schemaVersion\":6", "\"schemaVersion\":7" },
        .{ "\"schemaVersion\":6", "\"schemaVersion\":\"6\"" },
        .{ "\"schemaVersion\":6", "\"schemaVersion\":6,\"typo\":true" },
        .{ "\"defaultBackend\":\"doe_vulkan\"", "\"defaultBackend\":\"DOE_VULKAN\"" },
        .{ "\"defaultBackend\":\"doe_vulkan\"", "\"defaultBackend\":0" },
        .{ "\"allowFallback\":false", "\"allowFallback\":true" },
        .{ "\"strictNoFallback\":true", "\"strictNoFallback\":false" },
        .{ "\"allowFallback\":false", "\"allowFallback\":false,\"typo\":true" },
        .{ "\"allowFallback\":false", "\"allowFallback\":false,\"notes\":null" },
        .{ "\"allowFallback\":false", "\"allowFallback\":false,\"uploadPathPolicy\":null" },
        .{ "\"queueFamilyPolicy\":\"prefer_graphics_compute\"", "\"queueFamilyPolicy\":\"unrecognized\"" },
        .{ "\"deferredSubmissionSyncPolicy\":\"require_fence_pool\"", "\"deferredSubmissionSyncPolicy\":\"unrecognized\"" },
        .{ "\"vulkan_doe_app\"", "\"unknown_lane\"" },
    };
    inline for (replacements) |replacement| {
        const bytes = try std.mem.replaceOwned(u8, testing.allocator, TEST_POLICY, replacement[0], replacement[1]);
        defer testing.allocator.free(bytes);
        try testing.expectError(error.InvalidRuntimePolicy, parse_policy(testing.allocator, bytes));
    }
}
