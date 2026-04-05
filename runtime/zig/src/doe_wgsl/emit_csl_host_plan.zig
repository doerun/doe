// emit_csl_host_plan.zig — Schema-backed HostPlan artifact emission.
//
// This module serializes and validates the explicit host-plan artifact used by
// the CSL toolchain emitter. It keeps the schema deterministic and checks the
// emitted JSON shape before it leaves the Zig runtime path.

const std = @import("std");
const host = @import("emit_csl_host.zig");
const spec = @import("csl_spec.zig");

pub const EmitError = error{
    OutputTooLarge,
    InvalidIr,
    InvalidSchema,
    UnsupportedSchemaVersion,
};

pub const CompileTarget = struct {
    kernel_name: []const u8,
    layout_path: []const u8,
    pe_program_path: []const u8,
};

pub const DiscoveryMode = enum {
    explicit_config,
    implicit_path_lookup,
};

pub const CslcPlan = struct {
    executable: []const u8,
    discovery: DiscoveryMode,
    minimum_version: []const u8 = spec.CSLC_SDK_MIN_VERSION,
};

pub fn makeCslcPlan(executable: ?[]const u8) EmitError!CslcPlan {
    if (executable) |path| {
        if (path.len == 0) return error.InvalidIr;
        return .{
            .executable = path,
            .discovery = .explicit_config,
        };
    }

    return .{
        .executable = "cslc",
        .discovery = .implicit_path_lookup,
    };
}

pub fn discoveryLabel(discovery: DiscoveryMode) []const u8 {
    return switch (discovery) {
        .explicit_config => spec.HOST_PLAN_DISCOVERY_EXPLICIT_CONFIG,
        .implicit_path_lookup => spec.HOST_PLAN_DISCOVERY_IMPLICIT_PATH_LOOKUP,
    };
}

/// Emits the explicit HostPlan artifact schema used by the CSL toolchain.
pub fn emitHostPlanArtifactJson(
    buf: []u8,
    pos: *usize,
    plan: host.HostPlan,
    targets: []const CompileTarget,
    cslc_plan: ?CslcPlan,
) EmitError!void {
    try validateHostPlan(plan, targets, cslc_plan);

    try write(buf, pos, "{\n");
    try write(buf, pos, "  \"schemaVersion\": ");
    try writeInt(buf, pos, spec.HOST_PLAN_SCHEMA_VERSION);
    try write(buf, pos, ",\n  \"artifactKind\": ");
    try writeJsonString(buf, pos, spec.HOST_PLAN_ARTIFACT_KIND);
    try write(buf, pos, ",\n  \"target\": ");
    try writeJsonString(buf, pos, spec.HOST_PLAN_TARGET);
    try write(buf, pos, ",\n  \"contract\": ");
    try writeJsonString(buf, pos, spec.HOST_PLAN_CONTRACT);
    try write(buf, pos, ",\n");

    try write(buf, pos, "  \"hostPlan\": {\n");
    try write(buf, pos, "    \"peGrid\": { \"width\": ");
    try writeInt(buf, pos, plan.pe_grid_width);
    try write(buf, pos, ", \"height\": ");
    try writeInt(buf, pos, plan.pe_grid_height);
    try write(buf, pos, " },\n");

    try write(buf, pos, "    \"kernels\": [\n");
    for (plan.kernels, 0..) |kernel, idx| {
        try write(buf, pos, "      { \"name\": ");
        try writeJsonString(buf, pos, kernel.name);
        try write(buf, pos, ", \"pattern\": ");
        try writeJsonString(buf, pos, kernel.pattern);
        try write(buf, pos, ", \"count\": ");
        try writeInt(buf, pos, kernel.count);
        if (kernel.kv_cache_alias) |alias| {
            try write(buf, pos, ", \"kvCacheAlias\": ");
            try writeJsonString(buf, pos, alias);
        }
        try write(buf, pos, " }");
        if (idx + 1 < plan.kernels.len) try write(buf, pos, ",");
        try write(buf, pos, "\n");
    }
    try write(buf, pos, "    ],\n");

    try write(buf, pos, "    \"phases\": {\n");
    try write(buf, pos, "      \"prefill\": [\n");
    try emitLaunchSpecsJson(buf, pos, plan.prefill_launches);
    try write(buf, pos, "      ],\n");
    try write(buf, pos, "      \"decode\": [\n");
    try emitLaunchSpecsJson(buf, pos, plan.decode_launches);
    try write(buf, pos, "      ]\n");
    try write(buf, pos, "    },\n");

    try write(buf, pos, "    \"eosTokenId\": ");
    if (plan.eos_token_id) |eos_token_id| {
        try writeInt(buf, pos, eos_token_id);
    } else {
        try write(buf, pos, "null");
    }
    try write(buf, pos, "\n  },\n");

    try write(buf, pos, "  \"compileTargets\": [\n");
    for (targets, 0..) |target, idx| {
        try write(buf, pos, "    { \"name\": ");
        try writeJsonString(buf, pos, target.kernel_name);
        try write(buf, pos, ", \"layout\": ");
        try writeJsonString(buf, pos, target.layout_path);
        try write(buf, pos, ", \"peProgram\": ");
        try writeJsonString(buf, pos, target.pe_program_path);
        try write(buf, pos, " }");
        if (idx + 1 < targets.len) try write(buf, pos, ",");
        try write(buf, pos, "\n");
    }
    try write(buf, pos, "  ]");

    if (cslc_plan) |plan_cslc| {
        try write(buf, pos, ",\n  \"cslc\": {\n");
        try write(buf, pos, "    \"executable\": ");
        try writeJsonString(buf, pos, plan_cslc.executable);
        try write(buf, pos, ",\n    \"discovery\": ");
        try writeJsonString(buf, pos, discoveryLabel(plan_cslc.discovery));
        try write(buf, pos, ",\n    \"validation\": {\n");
        try write(buf, pos, "      \"command\": [");
        try writeJsonString(buf, pos, plan_cslc.executable);
        try write(buf, pos, ", ");
        try writeJsonString(buf, pos, spec.CSLC_VERSION_ARG);
        try write(buf, pos, "],\n      \"minimumVersion\": ");
        try writeJsonString(buf, pos, plan_cslc.minimum_version);
        try write(buf, pos, "\n    }\n  }");
    }

    try write(buf, pos, "\n}\n");
}

pub fn validateHostPlanArtifactJson(
    allocator: std.mem.Allocator,
    bytes: []const u8,
) EmitError!void {
    const parsed = std.json.parseFromSlice(std.json.Value, allocator, bytes, .{
        .ignore_unknown_fields = false,
    }) catch return error.InvalidSchema;
    defer parsed.deinit();

    try validateArtifactValue(parsed.value);
}

fn validateArtifactValue(root: std.json.Value) EmitError!void {
    const root_obj = expectObject(root, "root") orelse return error.InvalidSchema;

    const schema_version = jsonToU32(root_obj.get("schemaVersion")) orelse return error.InvalidSchema;
    if (schema_version != spec.HOST_PLAN_SCHEMA_VERSION) return error.UnsupportedSchemaVersion;

    const artifact_kind = expectString(root_obj.get("artifactKind"), "artifactKind") orelse return error.InvalidSchema;
    if (!std.mem.eql(u8, artifact_kind, spec.HOST_PLAN_ARTIFACT_KIND)) return error.InvalidSchema;

    const target = expectString(root_obj.get("target"), "target") orelse return error.InvalidSchema;
    if (!std.mem.eql(u8, target, spec.HOST_PLAN_TARGET)) return error.InvalidSchema;
    const contract = expectString(root_obj.get("contract"), "contract") orelse return error.InvalidSchema;
    if (!std.mem.eql(u8, contract, spec.HOST_PLAN_CONTRACT)) return error.InvalidSchema;

    try validateHostPlanValue(root_obj.get("hostPlan") orelse return error.InvalidSchema);
    try validateCompileTargetsValue(root_obj.get("compileTargets") orelse return error.InvalidSchema);

    if (root_obj.get("cslc")) |raw_cslc| {
        try validateCslcValue(raw_cslc);
    }
}

fn validateHostPlanValue(raw: std.json.Value) EmitError!void {
    const obj = expectObject(raw, "hostPlan") orelse return error.InvalidSchema;

    const pe_grid = expectObject(obj.get("peGrid") orelse return error.InvalidSchema, "peGrid") orelse return error.InvalidSchema;
    const width = jsonToU32(pe_grid.get("width")) orelse return error.InvalidSchema;
    const height = jsonToU32(pe_grid.get("height")) orelse return error.InvalidSchema;
    if (width == 0 or height == 0) return error.InvalidSchema;

    try validateKernelArray(obj.get("kernels") orelse return error.InvalidSchema);

    const phases = expectObject(obj.get("phases") orelse return error.InvalidSchema, "phases") orelse return error.InvalidSchema;
    try validateLaunchArray(phases.get("prefill") orelse return error.InvalidSchema);
    try validateLaunchArray(phases.get("decode") orelse return error.InvalidSchema);

    if (obj.get("eosTokenId")) |raw_eos| {
        if (raw_eos != .null and jsonToU32(raw_eos) == null) return error.InvalidSchema;
    } else {
        return error.InvalidSchema;
    }
}

fn validateKernelArray(raw: std.json.Value) EmitError!void {
    switch (raw) {
        .array => |arr| {
            for (arr.items) |item| {
                const obj = expectObject(item, "kernel") orelse return error.InvalidSchema;
                const name = expectString(obj.get("name"), "kernel.name") orelse return error.InvalidSchema;
                const pattern = expectString(obj.get("pattern"), "kernel.pattern") orelse return error.InvalidSchema;
                const count = jsonToU32(obj.get("count")) orelse return error.InvalidSchema;
                if (name.len == 0 or pattern.len == 0 or count == 0) return error.InvalidSchema;
            }
        },
        else => return error.InvalidSchema,
    }
}

fn validateLaunchArray(raw: std.json.Value) EmitError!void {
    switch (raw) {
        .array => |arr| {
            for (arr.items) |item| {
                const obj = expectObject(item, "launch") orelse return error.InvalidSchema;
                const kernel_name = expectString(obj.get("kernelName"), "launch.kernelName") orelse return error.InvalidSchema;
                const repeat = jsonToU32(obj.get("repeat")) orelse return error.InvalidSchema;
                if (kernel_name.len == 0 or repeat == 0) return error.InvalidSchema;
            }
        },
        else => return error.InvalidSchema,
    }
}

fn validateCompileTargetsValue(raw: std.json.Value) EmitError!void {
    switch (raw) {
        .array => |arr| {
            for (arr.items) |item| {
                const obj = expectObject(item, "compileTarget") orelse return error.InvalidSchema;
                const name = expectString(obj.get("name"), "compileTarget.name") orelse return error.InvalidSchema;
                const layout = expectString(obj.get("layout"), "compileTarget.layout") orelse return error.InvalidSchema;
                const pe_program = expectString(obj.get("peProgram"), "compileTarget.peProgram") orelse return error.InvalidSchema;
                if (name.len == 0 or layout.len == 0 or pe_program.len == 0) return error.InvalidSchema;
            }
        },
        else => return error.InvalidSchema,
    }
}

fn validateCslcValue(raw: std.json.Value) EmitError!void {
    const obj = expectObject(raw, "cslc") orelse return error.InvalidSchema;
    const executable = expectString(obj.get("executable"), "cslc.executable") orelse return error.InvalidSchema;
    if (executable.len == 0) return error.InvalidSchema;

    const discovery = expectString(obj.get("discovery"), "cslc.discovery") orelse return error.InvalidSchema;
    if (!std.mem.eql(u8, discovery, spec.HOST_PLAN_DISCOVERY_EXPLICIT_CONFIG) and
        !std.mem.eql(u8, discovery, spec.HOST_PLAN_DISCOVERY_IMPLICIT_PATH_LOOKUP))
    {
        return error.InvalidSchema;
    }

    const validation = expectObject(obj.get("validation") orelse return error.InvalidSchema, "validation") orelse return error.InvalidSchema;
    switch (validation.get("command") orelse return error.InvalidSchema) {
        .array => |command| {
            if (command.items.len != 2) return error.InvalidSchema;
            const first = expectString(command.items[0], "validation.command[0]") orelse return error.InvalidSchema;
            const second = expectString(command.items[1], "validation.command[1]") orelse return error.InvalidSchema;
            if (!std.mem.eql(u8, first, executable) or !std.mem.eql(u8, second, spec.CSLC_VERSION_ARG)) return error.InvalidSchema;
        },
        else => return error.InvalidSchema,
    }

    const minimum_version = expectString(validation.get("minimumVersion"), "validation.minimumVersion") orelse return error.InvalidSchema;
    if (minimum_version.len == 0) return error.InvalidSchema;
}

fn validateHostPlan(
    plan: host.HostPlan,
    targets: []const CompileTarget,
    cslc_plan: ?CslcPlan,
) EmitError!void {
    if (plan.pe_grid_width == 0 or plan.pe_grid_height == 0) return error.InvalidIr;

    for (plan.kernels) |kernel| {
        if (kernel.name.len == 0 or kernel.pattern.len == 0 or kernel.count == 0) return error.InvalidIr;
    }
    for (plan.prefill_launches) |launch| {
        if (launch.kernel_name.len == 0 or launch.repeat == 0) return error.InvalidIr;
        if (!hasKernel(plan.kernels, launch.kernel_name)) return error.InvalidIr;
    }
    for (plan.decode_launches) |launch| {
        if (launch.kernel_name.len == 0 or launch.repeat == 0) return error.InvalidIr;
        if (!hasKernel(plan.kernels, launch.kernel_name)) return error.InvalidIr;
    }

    for (targets) |target| {
        if (target.kernel_name.len == 0 or target.layout_path.len == 0 or target.pe_program_path.len == 0) {
            return error.InvalidIr;
        }
        if (!hasKernel(plan.kernels, target.kernel_name)) return error.InvalidIr;
    }

    if (cslc_plan) |plan_cslc| {
        if (plan_cslc.executable.len == 0 or plan_cslc.minimum_version.len == 0) return error.InvalidIr;
    }
}

fn hasKernel(kernels: []const host.KernelSpec, kernel_name: []const u8) bool {
    for (kernels) |kernel| {
        if (std.mem.eql(u8, kernel.name, kernel_name)) return true;
    }
    return false;
}

fn emitLaunchSpecsJson(buf: []u8, pos: *usize, launches: []const host.LaunchSpec) EmitError!void {
    for (launches, 0..) |launch, idx| {
        try write(buf, pos, "        { \"kernelName\": ");
        try writeJsonString(buf, pos, launch.kernel_name);
        try write(buf, pos, ", \"repeat\": ");
        try writeInt(buf, pos, launch.repeat);
        try write(buf, pos, " }");
        if (idx + 1 < launches.len) try write(buf, pos, ",");
        try write(buf, pos, "\n");
    }
}

fn expectObject(raw: ?std.json.Value, label: []const u8) ?std.json.ObjectMap {
    const value = raw orelse return null;
    return switch (value) {
        .object => |obj| obj,
        else => {
            _ = label;
            return null;
        },
    };
}

fn expectString(raw: ?std.json.Value, label: []const u8) ?[]const u8 {
    const value = raw orelse return null;
    return switch (value) {
        .string => |text| text,
        else => {
            _ = label;
            return null;
        },
    };
}

fn jsonToU32(raw: ?std.json.Value) ?u32 {
    const value = raw orelse return null;
    return switch (value) {
        .integer => |int_value| if (int_value < 0 or int_value > std.math.maxInt(u32))
            null
        else
            @as(u32, @intCast(int_value)),
        .float => |float_value| blk: {
            if (float_value < 0 or !std.math.isFinite(float_value)) break :blk null;
            const max_value = @as(f64, @floatFromInt(std.math.maxInt(u32)));
            if (float_value > max_value) break :blk null;
            if (float_value != @floor(float_value)) break :blk null;
            break :blk @as(u32, @intFromFloat(float_value));
        },
        else => null,
    };
}

fn writeJsonString(buf: []u8, pos: *usize, value: []const u8) EmitError!void {
    try write(buf, pos, "\"");
    for (value) |ch| {
        switch (ch) {
            '"' => try write(buf, pos, "\\\""),
            '\\' => try write(buf, pos, "\\\\"),
            '\n' => try write(buf, pos, "\\n"),
            '\r' => try write(buf, pos, "\\r"),
            '\t' => try write(buf, pos, "\\t"),
            else => {
                if (pos.* + 1 > buf.len) return error.OutputTooLarge;
                buf[pos.*] = ch;
                pos.* += 1;
            },
        }
    }
    try write(buf, pos, "\"");
}

fn write(buf: []u8, pos: *usize, text: []const u8) EmitError!void {
    if (pos.* + text.len > buf.len) return error.OutputTooLarge;
    @memcpy(buf[pos.*..][0..text.len], text);
    pos.* += text.len;
}

fn writeInt(buf: []u8, pos: *usize, value: anytype) EmitError!void {
    var tmp: [20]u8 = undefined;
    const slice = std.fmt.bufPrint(&tmp, "{d}", .{value}) catch return error.OutputTooLarge;
    try write(buf, pos, slice);
}

test "host plan artifact emits schema and cslc plan" {
    const targets = [_]CompileTarget{
        .{ .kernel_name = "gelu", .layout_path = "gelu/layout.csl", .pe_program_path = "gelu/pe_program.csl" },
    };
    const plan = host.HostPlan{
        .pe_grid_width = 16,
        .pe_grid_height = 1,
        .kernels = &[_]host.KernelSpec{
            .{ .name = "gelu", .pattern = "element_wise", .count = 1 },
        },
        .prefill_launches = &[_]host.LaunchSpec{
            .{ .kernel_name = "gelu", .repeat = 1 },
        },
        .decode_launches = &[_]host.LaunchSpec{
            .{ .kernel_name = "gelu", .repeat = 1 },
        },
    };
    var buf: [8192]u8 = undefined;
    var pos: usize = 0;
    const cslc_plan = try makeCslcPlan(null);
    try emitHostPlanArtifactJson(&buf, &pos, plan, &targets, cslc_plan);
    const text = buf[0..pos];
    try std.testing.expect(std.mem.indexOf(u8, text, "\"schemaVersion\": 1") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "\"artifactKind\": \"csl_host_plan\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, text, "\"discovery\": \"implicit_path_lookup\"") != null);
}
