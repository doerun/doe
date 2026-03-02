const std = @import("std");
const backend_ids = @import("backend_ids.zig");

pub const BackendLane = enum {
    vulkan_dawn_release,
    vulkan_doe_app,
    d3d12_doe_app,
    metal_doe_directional,
    metal_doe_comparable,
    metal_doe_release,
    metal_dawn_release,
    d3d12_doe_directional,
    d3d12_doe_comparable,
    d3d12_doe_release,
    d3d12_dawn_release,
    vulkan_dawn_directional,
    vulkan_doe_comparable,
    vulkan_doe_release,
    metal_doe_app,
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
        .vulkan_dawn_release => "vulkan_dawn_release",
        .vulkan_doe_app => "vulkan_doe_app",
        .d3d12_doe_app => "d3d12_doe_app",
        .metal_doe_directional => "metal_doe_directional",
        .metal_doe_comparable => "metal_doe_comparable",
        .metal_doe_release => "metal_doe_release",
        .metal_dawn_release => "metal_dawn_release",
        .d3d12_doe_directional => "d3d12_doe_directional",
        .d3d12_doe_comparable => "d3d12_doe_comparable",
        .d3d12_doe_release => "d3d12_doe_release",
        .d3d12_dawn_release => "d3d12_dawn_release",
        .vulkan_dawn_directional => "vulkan_dawn_directional",
        .vulkan_doe_comparable => "vulkan_doe_comparable",
        .vulkan_doe_release => "vulkan_doe_release",
        .metal_doe_app => "metal_doe_app",
    };
}

pub fn parse_lane(raw: []const u8) ?BackendLane {
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_dawn_release") or std.ascii.eqlIgnoreCase(raw, "vulkan_dawn_release")) return .vulkan_dawn_release;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_doe_app") or std.ascii.eqlIgnoreCase(raw, "vulkan_doe_app")) return .vulkan_doe_app;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12_doe_app") or std.ascii.eqlIgnoreCase(raw, "d3d12_doe_app")) return .d3d12_doe_app;
    if (std.ascii.eqlIgnoreCase(raw, "metal_doe_directional") or std.ascii.eqlIgnoreCase(raw, "metal_doe_directional")) return .metal_doe_directional;
    if (std.ascii.eqlIgnoreCase(raw, "metal_doe_comparable") or std.ascii.eqlIgnoreCase(raw, "metal_doe_comparable")) return .metal_doe_comparable;
    if (std.ascii.eqlIgnoreCase(raw, "metal_doe_release") or std.ascii.eqlIgnoreCase(raw, "metal_doe_release")) return .metal_doe_release;
    if (std.ascii.eqlIgnoreCase(raw, "metal_dawn_release")) return .metal_dawn_release;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12_doe_directional") or std.ascii.eqlIgnoreCase(raw, "d3d12_doe_directional")) return .d3d12_doe_directional;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12_doe_comparable") or std.ascii.eqlIgnoreCase(raw, "d3d12_doe_comparable")) return .d3d12_doe_comparable;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12_doe_release") or std.ascii.eqlIgnoreCase(raw, "d3d12_doe_release")) return .d3d12_doe_release;
    if (std.ascii.eqlIgnoreCase(raw, "d3d12_dawn_release")) return .d3d12_dawn_release;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_dawn_directional") or std.ascii.eqlIgnoreCase(raw, "vulkan_dawn_directional")) return .vulkan_dawn_directional;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_doe_comparable") or std.ascii.eqlIgnoreCase(raw, "vulkan_doe_comparable")) return .vulkan_doe_comparable;
    if (std.ascii.eqlIgnoreCase(raw, "vulkan_doe_release") or std.ascii.eqlIgnoreCase(raw, "vulkan_doe_release")) return .vulkan_doe_release;
    if (std.ascii.eqlIgnoreCase(raw, "metal_doe_app") or std.ascii.eqlIgnoreCase(raw, "metal_doe_app")) return .metal_doe_app;
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
        .vulkan_dawn_release => .{
            .lane = lane,
            .default_backend = .dawn_delegate,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .vulkan_doe_app, .vulkan_doe_comparable, .vulkan_doe_release => .{
            .lane = lane,
            .default_backend = .doe_vulkan,
            .allow_fallback = false,
            .strict_no_fallback = true,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .d3d12_doe_app, .d3d12_doe_comparable, .d3d12_doe_release => .{
            .lane = lane,
            .default_backend = .doe_d3d12,
            .allow_fallback = false,
            .strict_no_fallback = true,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .metal_doe_directional => .{
            .lane = lane,
            .default_backend = .doe_metal,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .metal_dawn_release => .{
            .lane = lane,
            .default_backend = .dawn_delegate,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .metal_doe_comparable, .metal_doe_release, .metal_doe_app => .{
            .lane = lane,
            .default_backend = .doe_metal,
            .allow_fallback = false,
            .strict_no_fallback = true,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .vulkan_dawn_directional => .{
            .lane = lane,
            .default_backend = .dawn_delegate,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .d3d12_doe_directional => .{
            .lane = lane,
            .default_backend = .doe_d3d12,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
        .d3d12_dawn_release => .{
            .lane = lane,
            .default_backend = .dawn_delegate,
            .allow_fallback = true,
            .strict_no_fallback = false,
            .policy_hash = "backend-runtime-policy-v1",
        },
    };
}
