const std = @import("std");
const backend_ids = @import("backend_ids.zig");

pub const BackendLane = enum {
    amd_vulkan_release,
    amd_vulkan_app,
    local_metal_directional,
    local_metal_comparable,
    local_metal_release,
    metal_oracle,
    local_vulkan_directional,
    local_vulkan_comparable,
    local_vulkan_release,
    macos_app,
};

pub const SelectionPolicy = struct {
    lane: BackendLane,
    default_backend: backend_ids.BackendId,
    allow_fallback: bool,
    strict_no_fallback: bool,
    policy_hash: []const u8,
};

pub const LoadedSelectionPolicy = struct {
    policy: SelectionPolicy,
    owned_policy_hash: []u8,
};

pub const DEFAULT_RUNTIME_POLICY_PATH = "config/backend-runtime-policy.json";
const MAX_RUNTIME_POLICY_BYTES: usize = 64 * 1024;
const EXPECTED_SCHEMA_VERSION: i64 = 1;

pub const PolicyLoadError = error{
    InvalidRuntimePolicy,
};

pub fn lane_name(lane: BackendLane) []const u8 {
    return switch (lane) {
        .amd_vulkan_release => "vulkan_oracle",
        .amd_vulkan_app => "vulkan_app",
        .local_metal_directional => "metal_local_directional",
        .local_metal_comparable => "metal_local_comparable",
        .local_metal_release => "metal_local_release",
        .metal_oracle => "metal_oracle",
        .local_vulkan_directional => "vulkan_local_directional",
        .local_vulkan_comparable => "vulkan_local_comparable",
        .local_vulkan_release => "vulkan_local_release",
        .macos_app => "metal_app",
    };
}

pub fn parse_lane(raw: []const u8) ?BackendLane {
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_oracle") or std.ascii.eqlIgnoreCase(raw, "amd_vulkan_release")) return .amd_vulkan_release;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_app") or std.ascii.eqlIgnoreCase(raw, "amd_vulkan_app")) return .amd_vulkan_app;
    if (std.ascii.eqlIgnoreCase(raw, "metal_local_directional") or std.ascii.eqlIgnoreCase(raw, "local_metal_directional")) return .local_metal_directional;
    if (std.ascii.eqlIgnoreCase(raw, "metal_local_comparable") or std.ascii.eqlIgnoreCase(raw, "local_metal_comparable")) return .local_metal_comparable;
    if (std.ascii.eqlIgnoreCase(raw, "metal_local_release") or std.ascii.eqlIgnoreCase(raw, "local_metal_release")) return .local_metal_release;
    if (std.ascii.eqlIgnoreCase(raw, "metal_oracle")) return .metal_oracle;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_local_directional") or std.ascii.eqlIgnoreCase(raw, "local_vulkan_directional")) return .local_vulkan_directional;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_local_comparable") or std.ascii.eqlIgnoreCase(raw, "local_vulkan_comparable")) return .local_vulkan_comparable;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_local_release") or std.ascii.eqlIgnoreCase(raw, "local_vulkan_release")) return .local_vulkan_release;
    if (std.ascii.eqlIgnoreCase(raw, "metal_app") or std.ascii.eqlIgnoreCase(raw, "macos_app")) return .macos_app;
    return null;
}

pub fn load_policy_for_lane(
    allocator: std.mem.Allocator,
    policy_path: []const u8,
    lane: BackendLane,
) !LoadedSelectionPolicy {
    const bytes = try std.fs.cwd().readFileAlloc(allocator, policy_path, MAX_RUNTIME_POLICY_BYTES);
    defer allocator.free(bytes);

    var arena = std.heap.ArenaAllocator.init(allocator);
    defer arena.deinit();

    const parsed = try std.json.parseFromSlice(std.json.Value, arena.allocator(), bytes, .{
        .ignore_unknown_fields = false,
    });
    defer parsed.deinit();

    const root_obj = switch (parsed.value) {
        .object => |obj| obj,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };

    const schema_value = root_obj.get("schemaVersion") orelse return PolicyLoadError.InvalidRuntimePolicy;
    const schema_version = switch (schema_value) {
        .integer => |value| value,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };
    if (schema_version != EXPECTED_SCHEMA_VERSION) {
        return PolicyLoadError.InvalidRuntimePolicy;
    }

    const policy_hash_value = root_obj.get("selectionPolicyHashSeed") orelse return PolicyLoadError.InvalidRuntimePolicy;
    const policy_hash = switch (policy_hash_value) {
        .string => |value| value,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };
    const owned_policy_hash = try allocator.dupe(u8, policy_hash);
    errdefer allocator.free(owned_policy_hash);

    const lanes_value = root_obj.get("lanes") orelse return PolicyLoadError.InvalidRuntimePolicy;
    const lanes_obj = switch (lanes_value) {
        .object => |obj| obj,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };

    const lane_value = lanes_obj.get(lane_name(lane)) orelse return PolicyLoadError.InvalidRuntimePolicy;
    const lane_obj = switch (lane_value) {
        .object => |obj| obj,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };

    const rollback_value = root_obj.get("rollbackSwitch") orelse return PolicyLoadError.InvalidRuntimePolicy;
    const rollback_obj = switch (rollback_value) {
        .object => |obj| obj,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };
    const rollback_name_value = rollback_obj.get("name") orelse return PolicyLoadError.InvalidRuntimePolicy;
    const rollback_name = switch (rollback_name_value) {
        .string => |value| value,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };
    const rollback_backend_value = rollback_obj.get("forceBackend") orelse return PolicyLoadError.InvalidRuntimePolicy;
    const rollback_backend_name = switch (rollback_backend_value) {
        .string => |value| value,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };
    const rollback_backend = backend_ids.parse_backend_id(rollback_backend_name) orelse return PolicyLoadError.InvalidRuntimePolicy;

    var force_backend: ?backend_ids.BackendId = null;
    const active_switch = std.process.getEnvVarOwned(allocator, "FAWN_BACKEND_SWITCH") catch |err| switch (err) {
        error.EnvironmentVariableNotFound => null,
        else => return err,
    };
    defer if (active_switch) |value| allocator.free(value);
    if (active_switch) |switch_name| {
        if (std.mem.eql(u8, switch_name, rollback_name)) {
            force_backend = rollback_backend;
        }
    }

    const backend_value = lane_obj.get("defaultBackend") orelse return PolicyLoadError.InvalidRuntimePolicy;
    const backend_name = switch (backend_value) {
        .string => |value| value,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };
    const lane_backend = backend_ids.parse_backend_id(backend_name) orelse return PolicyLoadError.InvalidRuntimePolicy;
    const backend_id = force_backend orelse lane_backend;

    const allow_fallback_value = lane_obj.get("allowFallback") orelse return PolicyLoadError.InvalidRuntimePolicy;
    var allow_fallback = switch (allow_fallback_value) {
        .bool => |value| value,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };

    const strict_no_fallback_value = lane_obj.get("strictNoFallback") orelse return PolicyLoadError.InvalidRuntimePolicy;
    var strict_no_fallback = switch (strict_no_fallback_value) {
        .bool => |value| value,
        else => return PolicyLoadError.InvalidRuntimePolicy,
    };

    if (force_backend != null) {
        allow_fallback = false;
        strict_no_fallback = true;
    }

    return .{
        .policy = .{
            .lane = lane,
            .default_backend = backend_id,
            .allow_fallback = allow_fallback,
            .strict_no_fallback = strict_no_fallback,
            .policy_hash = owned_policy_hash,
        },
        .owned_policy_hash = owned_policy_hash,
    };
}

pub fn default_policy_for_lane(lane: BackendLane) SelectionPolicy {
    return switch (lane) {
        .amd_vulkan_release => .{
            .lane = lane,
            .default_backend = .dawn_oracle,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .amd_vulkan_app, .local_vulkan_comparable, .local_vulkan_release => .{
            .lane = lane,
            .default_backend = .zig_vulkan,
            .allow_fallback = false,
            .strict_no_fallback = true,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .local_metal_directional => .{
            .lane = lane,
            .default_backend = .zig_metal,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .metal_oracle => .{
            .lane = lane,
            .default_backend = .dawn_oracle,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .local_metal_comparable, .local_metal_release, .macos_app => .{
            .lane = lane,
            .default_backend = .zig_metal,
            .allow_fallback = false,
            .strict_no_fallback = true,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .local_vulkan_directional => .{
            .lane = lane,
            .default_backend = .dawn_oracle,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
    };
}
