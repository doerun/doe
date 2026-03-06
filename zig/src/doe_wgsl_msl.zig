// doe_wgsl_msl.zig — Minimal WGSL → MSL translator for compute shaders.
// Handles the subset needed by WebGPU compute: storage buffers, builtins, basic types.

const std = @import("std");

pub const TranslateError = error{
    InvalidWgsl,
    OutputTooLarge,
    OutOfMemory,
};

const Binding = struct {
    group: u32,
    binding: u32,
    name: []const u8,
    is_read_only: bool,
    elem_type: []const u8, // MSL element type (e.g. "float", "uint")
};

const Builtin = struct {
    name: []const u8,
    wgsl_type: []const u8,
    msl_attr: []const u8,
    msl_type: []const u8,
};

const BUILTINS = [_]Builtin{
    .{ .name = "global_invocation_id", .wgsl_type = "vec3u", .msl_attr = "thread_position_in_grid", .msl_type = "uint3" },
    .{ .name = "local_invocation_id", .wgsl_type = "vec3u", .msl_attr = "thread_position_in_threadgroup", .msl_type = "uint3" },
    .{ .name = "workgroup_id", .wgsl_type = "vec3u", .msl_attr = "threadgroup_position_in_grid", .msl_type = "uint3" },
    .{ .name = "num_workgroups", .wgsl_type = "vec3u", .msl_attr = "threadgroups_per_grid", .msl_type = "uint3" },
    .{ .name = "local_invocation_index", .wgsl_type = "u32", .msl_attr = "thread_index_in_threadgroup", .msl_type = "uint" },
};

pub const MAX_OUTPUT: usize = 64 * 1024;
pub const MAX_BINDINGS: usize = 16;

/// Translate a WGSL compute shader to MSL. Returns the MSL source length written.
pub fn translate(wgsl: []const u8, out: []u8) TranslateError!usize {
    var bindings: [MAX_BINDINGS]Binding = undefined;
    var binding_count: usize = 0;

    var entry_name: []const u8 = "main";
    var body_start: usize = 0;
    var body_end: usize = 0;
    var builtin_params: [8]BuiltinParam = undefined;
    var builtin_count: usize = 0;

    // Parse bindings and entry point from WGSL source.
    const line_iter = std.mem.splitScalar(u8, wgsl, '\n');
    var in_fn = false;
    var brace_depth: i32 = 0;
    var pos: usize = 0;

    // First pass: find bindings and entry point structure.
    var lines = std.mem.splitScalar(u8, wgsl, '\n');
    while (lines.next()) |line| {
        const trimmed = std.mem.trim(u8, line, " \t\r");

        if (parseBinding(trimmed)) |b| {
            if (binding_count < MAX_BINDINGS) {
                bindings[binding_count] = b;
                binding_count += 1;
            }
        }

        if (std.mem.startsWith(u8, trimmed, "fn ")) {
            entry_name = parseFnName(trimmed) orelse "main";
            builtin_count = parseFnBuiltins(trimmed, &builtin_params);
        }
    }
    _ = line_iter;

    // Find function body (everything between outermost braces of fn).
    pos = 0;
    in_fn = false;
    var body_brace_start: usize = 0;
    for (wgsl, 0..) |ch, i| {
        if (!in_fn) {
            if (i + 3 <= wgsl.len and std.mem.eql(u8, wgsl[i .. i + 3], "fn ")) {
                in_fn = true;
            }
        }
        if (in_fn) {
            if (ch == '{') {
                if (brace_depth == 0) body_brace_start = i + 1;
                brace_depth += 1;
            } else if (ch == '}') {
                brace_depth -= 1;
                if (brace_depth == 0) {
                    body_start = body_brace_start;
                    body_end = i;
                    break;
                }
            }
        }
    }

    if (body_end == 0) return TranslateError.InvalidWgsl;

    // Generate MSL.
    var w = Writer{ .buf = out, .pos = 0 };
    try w.write("#include <metal_stdlib>\nusing namespace metal;\n\n");
    try w.write("kernel void main_kernel(\n");

    // Buffer parameters.
    var param_idx: usize = 0;
    for (bindings[0..binding_count]) |b| {
        if (param_idx > 0) try w.write(",\n");
        try w.write("    ");
        if (b.is_read_only) try w.write("const ");
        try w.write("device ");
        try w.write(b.elem_type);
        try w.write("* ");
        try w.write(b.name);
        try w.write(" [[buffer(");
        try w.writeInt(b.binding);
        try w.write(")]]");
        param_idx += 1;
    }

    // Builtin parameters.
    for (builtin_params[0..builtin_count]) |bp| {
        if (param_idx > 0) try w.write(",\n");
        try w.write("    ");
        try w.write(bp.msl_type);
        try w.write(" ");
        try w.write(bp.param_name);
        try w.write(" [[");
        try w.write(bp.msl_attr);
        try w.write("]]");
        param_idx += 1;
    }

    try w.write("\n) {\n");

    // Function body — pass through with type replacements.
    const body = wgsl[body_start..body_end];
    try writeTransformedBody(&w, body);

    try w.write("}\n");
    return w.pos;
}

const BuiltinParam = struct {
    param_name: []const u8,
    msl_type: []const u8,
    msl_attr: []const u8,
};

fn parseBinding(line: []const u8) ?Binding {
    // Match: @group(G) @binding(B) var<storage, read_write|read> NAME : TYPE;
    const group_prefix = "@group(";
    const gi = std.mem.indexOf(u8, line, group_prefix) orelse return null;
    const g_start = gi + group_prefix.len;
    const g_end = std.mem.indexOfPos(u8, line, g_start, ")") orelse return null;
    const group = std.fmt.parseInt(u32, line[g_start..g_end], 10) catch return null;

    const bind_prefix = "@binding(";
    const bi = std.mem.indexOf(u8, line, bind_prefix) orelse return null;
    const b_start = bi + bind_prefix.len;
    const b_end = std.mem.indexOfPos(u8, line, b_start, ")") orelse return null;
    const binding = std.fmt.parseInt(u32, line[b_start..b_end], 10) catch return null;

    const is_read_only = std.mem.indexOf(u8, line, "read>") != null and
        std.mem.indexOf(u8, line, "read_write>") == null;

    // Find variable name: var<...> NAME
    const var_idx = std.mem.indexOf(u8, line, "var<") orelse return null;
    const gt_idx = std.mem.indexOfPos(u8, line, var_idx, ">") orelse return null;
    const after_gt = std.mem.trim(u8, line[gt_idx + 1 ..], " \t");
    const name_end = std.mem.indexOfAny(u8, after_gt, " :\t;") orelse after_gt.len;
    const name = after_gt[0..name_end];
    if (name.len == 0) return null;

    // Parse element type from array<T> or array<T, N>.
    const elem_type = parseElemType(line) orelse "float";

    return Binding{
        .group = group,
        .binding = binding,
        .name = name,
        .is_read_only = is_read_only,
        .elem_type = elem_type,
    };
}

fn parseElemType(line: []const u8) ?[]const u8 {
    const arr_idx = std.mem.indexOf(u8, line, "array<") orelse return null;
    const start = arr_idx + 6;
    const end = std.mem.indexOfPos(u8, line, start, ">") orelse return null;
    // Handle array<T, N> by taking up to comma.
    const inner = line[start..end];
    const comma = std.mem.indexOf(u8, inner, ",");
    const type_str = std.mem.trim(u8, if (comma) |c| inner[0..c] else inner, " \t");
    return wgslTypeToMsl(type_str);
}

fn wgslTypeToMsl(t: []const u8) []const u8 {
    if (std.mem.eql(u8, t, "f32")) return "float";
    if (std.mem.eql(u8, t, "u32")) return "uint";
    if (std.mem.eql(u8, t, "i32")) return "int";
    if (std.mem.eql(u8, t, "f16")) return "half";
    if (std.mem.eql(u8, t, "vec2f") or std.mem.eql(u8, t, "vec2<f32>")) return "float2";
    if (std.mem.eql(u8, t, "vec3f") or std.mem.eql(u8, t, "vec3<f32>")) return "float3";
    if (std.mem.eql(u8, t, "vec4f") or std.mem.eql(u8, t, "vec4<f32>")) return "float4";
    if (std.mem.eql(u8, t, "vec2u") or std.mem.eql(u8, t, "vec2<u32>")) return "uint2";
    if (std.mem.eql(u8, t, "vec3u") or std.mem.eql(u8, t, "vec3<u32>")) return "uint3";
    if (std.mem.eql(u8, t, "vec4u") or std.mem.eql(u8, t, "vec4<u32>")) return "uint4";
    if (std.mem.eql(u8, t, "vec2i") or std.mem.eql(u8, t, "vec2<i32>")) return "int2";
    if (std.mem.eql(u8, t, "vec3i") or std.mem.eql(u8, t, "vec3<i32>")) return "int3";
    if (std.mem.eql(u8, t, "vec4i") or std.mem.eql(u8, t, "vec4<i32>")) return "int4";
    return "float";
}

fn parseFnName(line: []const u8) ?[]const u8 {
    const fn_idx = std.mem.indexOf(u8, line, "fn ") orelse return null;
    const start = fn_idx + 3;
    const rest = std.mem.trim(u8, line[start..], " \t");
    const end = std.mem.indexOfAny(u8, rest, " (\t") orelse rest.len;
    const name = rest[0..end];
    return if (name.len > 0) name else null;
}

fn parseFnBuiltins(line: []const u8, out: []BuiltinParam) usize {
    // Find parameters between ( and )
    const paren_start = std.mem.indexOf(u8, line, "(") orelse return 0;
    const paren_end = std.mem.lastIndexOf(u8, line, ")") orelse return 0;
    if (paren_start >= paren_end) return 0;
    const params = line[paren_start + 1 .. paren_end];

    var count: usize = 0;
    var iter = std.mem.splitScalar(u8, params, ',');
    while (iter.next()) |param| {
        const trimmed = std.mem.trim(u8, param, " \t");
        if (std.mem.indexOf(u8, trimmed, "@builtin(")) |bi| {
            const b_start = bi + 9;
            const b_end = std.mem.indexOfPos(u8, trimmed, b_start, ")") orelse continue;
            const builtin_name = trimmed[b_start..b_end];

            // Find param name after ") NAME: TYPE"
            const after_close = std.mem.trim(u8, trimmed[b_end + 1 ..], " \t");
            const name_end = std.mem.indexOfAny(u8, after_close, " :\t") orelse after_close.len;
            const param_name = after_close[0..name_end];

            for (BUILTINS) |b| {
                if (std.mem.eql(u8, builtin_name, b.name)) {
                    if (count < out.len) {
                        out[count] = .{
                            .param_name = param_name,
                            .msl_type = b.msl_type,
                            .msl_attr = b.msl_attr,
                        };
                        count += 1;
                    }
                    break;
                }
            }
        }
    }
    return count;
}

fn writeTransformedBody(w: *Writer, body: []const u8) TranslateError!void {
    // Line-by-line pass-through with WGSL→MSL keyword replacements.
    var lines = std.mem.splitScalar(u8, body, '\n');
    while (lines.next()) |line| {
        const trimmed = std.mem.trim(u8, line, " \t\r");
        // Skip WGSL-only declarations that were already handled.
        if (trimmed.len == 0) {
            try w.write("\n");
            continue;
        }
        // Replace WGSL type keywords in the line.
        try writeLineWithReplacements(w, line);
        try w.write("\n");
    }
}

fn writeLineWithReplacements(w: *Writer, line: []const u8) TranslateError!void {
    // Simple token-level replacement for WGSL→MSL types in function body.
    // For the compute subset, most syntax is identical. Key differences:
    // - `let` → `const auto` is not needed (MSL auto works, but let's use types)
    // - `var x: f32` → `float x` would require full parsing
    // For now, pass through as-is — MSL and WGSL share C-like expression syntax.
    // The function body (arithmetic, indexing, assignments) is compatible.
    try w.write(line);
}

const Writer = struct {
    buf: []u8,
    pos: usize,

    fn write(self: *Writer, data: []const u8) TranslateError!void {
        if (self.pos + data.len > self.buf.len) return TranslateError.OutputTooLarge;
        @memcpy(self.buf[self.pos..][0..data.len], data);
        self.pos += data.len;
    }

    fn writeInt(self: *Writer, val: u32) TranslateError!void {
        var tmp: [16]u8 = undefined;
        const s = std.fmt.bufPrint(&tmp, "{d}", .{val}) catch return TranslateError.OutputTooLarge;
        try self.write(s);
    }
};
