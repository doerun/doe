// emit_csl_validate.zig — Pattern-specific CSL output validation and opt-in
// cslc toolchain checks.
//
// The structural validator stays deterministic and fake-tool-friendly. The
// opt-in toolchain lane mirrors the DXIL config flow: explicit config,
// environment-backed discovery, and a PATH sentinel for explicit lookup.

const builtin = @import("builtin");
const std = @import("std");
const spec = @import("csl_spec.zig");

pub const Error = error{
    OutputTooLarge,
    InvalidIr,
    OutOfMemory,
    ShaderToolchainUnavailable,
};

pub const CSLC_ENV_VAR: []const u8 = "DOE_WGSL_CSLC";
pub const CSLC_PATH_SENTINEL: []const u8 = "PATH";

const MAX_ERRORS: usize = 16;
const LAST_ERROR_CAP: usize = 1024;
const MAX_CSLC_OUTPUT_BYTES: usize = 64 * 1024;

pub const ToolchainDiscovery = enum {
    explicit_config,
    env_path,
    env_path_lookup,
    implicit_path_lookup,
};

pub const ToolchainConfig = struct {
    executable: []const u8,
    discovery: ToolchainDiscovery = .explicit_config,
    owned_value: ?[]u8 = null,

    pub fn deinit(self: *ToolchainConfig, alloc: std.mem.Allocator) void {
        if (self.owned_value) |value| {
            alloc.free(value);
            self.owned_value = null;
        }
    }
};

pub const ValidationResult = struct {
    valid: bool,
    errors: [MAX_ERRORS][]const u8,
    error_count: u32,

    pub fn ok() ValidationResult {
        return .{ .valid = true, .errors = undefined, .error_count = 0 };
    }

    pub fn firstError(self: ValidationResult) ?[]const u8 {
        if (self.error_count == 0) return null;
        return self.errors[0];
    }
};

var last_error_buf: [LAST_ERROR_CAP]u8 = undefined;
var last_error_len: usize = 0;

pub fn lastErrorMessage() []const u8 {
    return last_error_buf[0..last_error_len];
}

pub fn loadToolchainConfig(alloc: std.mem.Allocator) Error!ToolchainConfig {
    clearLastError();
    const env_value = std.process.getEnvVarOwned(alloc, CSLC_ENV_VAR) catch |err| switch (err) {
        error.EnvironmentVariableNotFound => return .{
            .executable = defaultCslcExecutable(),
            .discovery = .implicit_path_lookup,
        },
        else => {
            setLastErrorFmt("failed to read {s}: {s}", .{ CSLC_ENV_VAR, @errorName(err) });
            return error.ShaderToolchainUnavailable;
        },
    };
    errdefer alloc.free(env_value);
    return toolchainConfigFromEnvValue(alloc, env_value);
}

pub fn toolchainConfigFromEnvValue(alloc: std.mem.Allocator, raw_value: []const u8) Error!ToolchainConfig {
    clearLastError();
    const owned = try alloc.dupe(u8, raw_value);
    errdefer alloc.free(owned);

    const trimmed = std.mem.trim(u8, owned, " \t\r\n");
    if (trimmed.len == 0) {
        setLastErrorFmt(
            "{s} is set but empty; set it to a cslc path or `{s}` to opt into PATH lookup explicitly",
            .{ CSLC_ENV_VAR, CSLC_PATH_SENTINEL },
        );
        return error.ShaderToolchainUnavailable;
    }

    if (std.ascii.eqlIgnoreCase(trimmed, CSLC_PATH_SENTINEL)) {
        return .{
            .executable = defaultCslcExecutable(),
            .discovery = .env_path_lookup,
            .owned_value = owned,
        };
    }

    return .{
        .executable = trimmed,
        .discovery = .env_path,
        .owned_value = owned,
    };
}

pub fn validatePattern(csl: []const u8, pattern: PatternKind) ValidationResult {
    clearLastError();
    var result = ValidationResult.ok();

    if (spec.validateOutput(csl)) |base_err| {
        addError(&result, base_err.message);
        return result;
    }

    switch (pattern) {
        .element_wise => validateElementWise(csl, &result),
        .reduction => validateReduction(csl, &result),
        .gather => validateGather(csl, &result),
        .attention_decode => validateAttention(csl, &result),
        .attention_tiled => validateAttention(csl, &result),
        .attention_linear => validateAttention(csl, &result),
        .attention_streaming => validateAttention(csl, &result),
        .tiled_matmul => validateTiledMatmul(csl, &result),
        .fused_gemv_dequant => validateFusedGemvDequant(csl, &result),
        .dequant => validateDequant(csl, &result),
        .rope => validateRope(csl, &result),
        .sample => validateSample(csl, &result),
        .kv_write => validateKvWrite(csl, &result),
        .kv_read => validateKvRead(csl, &result),
        .fused_ffn => validateFusedFfn(csl, &result),
    }

    result.valid = result.error_count == 0;
    return result;
}

pub fn validatePatternWithToolchainConfig(
    csl: []const u8,
    pattern: PatternKind,
    config: ToolchainConfig,
) Error!ValidationResult {
    const result = validatePattern(csl, pattern);
    if (!result.valid) return result;
    try validateToolchainConfig(config);
    return result;
}

pub fn validateToolchainConfig(config: ToolchainConfig) Error!void {
    clearLastError();
    if (config.executable.len == 0) {
        setLastErrorFmt(
            "cslc executable path is empty; pass ToolchainConfig{{ .executable = ... }} or set {s} to a cslc path or {s}",
            .{ CSLC_ENV_VAR, CSLC_PATH_SENTINEL },
        );
        return error.ShaderToolchainUnavailable;
    }

    const alloc = std.heap.page_allocator;
    const argv = [_][]const u8{ config.executable, "--version" };
    const result = std.process.Child.run(.{
        .allocator = alloc,
        .argv = &argv,
        .max_output_bytes = MAX_CSLC_OUTPUT_BYTES,
    }) catch |err| switch (err) {
        error.FileNotFound => {
            setMissingToolchainError(config);
            return error.ShaderToolchainUnavailable;
        },
        else => {
            setLastErrorFmt(
                "failed to start cslc via {s} `{s}`: {s}",
                .{ discoveryLabel(config.discovery), config.executable, @errorName(err) },
            );
            return error.ShaderToolchainUnavailable;
        },
    };
    defer alloc.free(result.stdout);
    defer alloc.free(result.stderr);

    switch (result.term) {
        .Exited => |code| {
            if (code != 0) {
                const detail = trimmedDiagnostic(result.stderr, result.stdout);
                if (detail.len == 0) {
                    setLastErrorFmt(
                        "cslc failed via {s} `{s}` with exit code {d}",
                        .{ discoveryLabel(config.discovery), config.executable, code },
                    );
                } else {
                    setLastErrorFmt(
                        "cslc failed via {s} `{s}` with exit code {d}: {s}",
                        .{ discoveryLabel(config.discovery), config.executable, code, detail },
                    );
                }
                return error.InvalidIr;
            }
        },
        else => {
            setLastErrorFmt(
                "cslc terminated unexpectedly via {s} `{s}`",
                .{ discoveryLabel(config.discovery), config.executable },
            );
            return error.InvalidIr;
        },
    }
}

pub const PatternKind = enum {
    element_wise,
    reduction,
    gather,
    attention_decode,
    attention_tiled,
    attention_linear,
    attention_streaming,
    tiled_matmul,
    fused_gemv_dequant,
    dequant,
    rope,
    sample,
    kv_write,
    kv_read,
    fused_ffn,
};

fn validateElementWise(csl: []const u8, result: *ValidationResult) void {
    if (std.mem.indexOf(u8, csl, "fabin_dsd") != null) {
        addError(result, "element_wise pattern should not use fabric input DSDs");
    }
    if (std.mem.indexOf(u8, csl, "fabout_dsd") != null) {
        addError(result, "element_wise pattern should not use fabric output DSDs");
    }
    requireContains(csl, result, "@range", "element_wise missing compute loop (@range)");
}

fn validateReduction(csl: []const u8, result: *ValidationResult) void {
    requireContains(csl, result, "fabout_dsd", "reduction missing fabric output DSD");
    requireContains(csl, result, "fabin_dsd", "reduction missing fabric input DSD");
}

fn validateGather(csl: []const u8, result: *ValidationResult) void {
    requireContains(csl, result, "indices", "gather missing indices reference");
}

fn validateAttention(csl: []const u8, result: *ValidationResult) void {
    const has_qkv = std.mem.indexOf(u8, csl, "q_") != null or
        std.mem.indexOf(u8, csl, "query") != null or
        std.mem.indexOf(u8, csl, "key") != null;
    if (!has_qkv) {
        addError(result, "attention pattern missing Q/K/V buffer references");
    }
}

fn validateTiledMatmul(csl: []const u8, result: *ValidationResult) void {
    requireContains(csl, result, "accum", "tiled_matmul missing accumulator");
}

fn validateFusedGemvDequant(csl: []const u8, result: *ValidationResult) void {
    requireContains(csl, result, "dequant", "fused_gemv_dequant missing dequantization");
}

fn validateDequant(csl: []const u8, result: *ValidationResult) void {
    const has_q4k = std.mem.indexOf(u8, csl, "QK_K") != null or
        std.mem.indexOf(u8, csl, "Q4K") != null;
    if (!has_q4k) {
        addError(result, "dequant missing Q4K format constants");
    }
}

fn validateRope(csl: []const u8, result: *ValidationResult) void {
    const has_rotation = std.mem.indexOf(u8, csl, "cos") != null or
        std.mem.indexOf(u8, csl, "sin") != null;
    if (!has_rotation) {
        addError(result, "rope missing cos/sin rotation references");
    }
}

fn validateSample(csl: []const u8, result: *ValidationResult) void {
    requireContains(csl, result, "logit", "sample missing logits reference");
}

fn validateKvWrite(csl: []const u8, result: *ValidationResult) void {
    const has_cache = std.mem.indexOf(u8, csl, "cache") != null or
        std.mem.indexOf(u8, csl, "kv_") != null;
    if (!has_cache) {
        addError(result, "kv_write missing cache buffer reference");
    }
}

fn validateKvRead(csl: []const u8, result: *ValidationResult) void {
    const has_cache = std.mem.indexOf(u8, csl, "cache") != null or
        std.mem.indexOf(u8, csl, "kv_") != null;
    if (!has_cache) {
        addError(result, "kv_read missing cache buffer reference");
    }
}

fn validateFusedFfn(csl: []const u8, result: *ValidationResult) void {
    const has_activation = std.mem.indexOf(u8, csl, "silu") != null or
        std.mem.indexOf(u8, csl, "gelu") != null;
    if (!has_activation) {
        addError(result, "fused_ffn missing activation function (silu/gelu)");
    }
}

fn requireContains(csl: []const u8, result: *ValidationResult, needle: []const u8, msg: []const u8) void {
    if (std.mem.indexOf(u8, csl, needle) == null) {
        addError(result, msg);
    }
}

fn addError(result: *ValidationResult, msg: []const u8) void {
    if (result.error_count < MAX_ERRORS) {
        result.errors[result.error_count] = msg;
        result.error_count += 1;
        result.valid = false;
    }
}

fn clearLastError() void {
    last_error_len = 0;
}

fn setMissingToolchainError(config: ToolchainConfig) void {
    switch (config.discovery) {
        .explicit_config => setLastErrorFmt(
            "cslc executable from explicit CSL toolchain config was not found at `{s}`; pass a valid ToolchainConfig path or set {s} to a valid cslc path",
            .{ config.executable, CSLC_ENV_VAR },
        ),
        .env_path => setLastErrorFmt(
            "{s} points to `{s}`, but that cslc executable was not found; fix {s} or use `{s}` to opt into PATH lookup",
            .{ CSLC_ENV_VAR, config.executable, CSLC_ENV_VAR, CSLC_PATH_SENTINEL },
        ),
        .env_path_lookup => setLastErrorFmt(
            "{s}={s} requested explicit PATH lookup, but `{s}` was not found on PATH",
            .{ CSLC_ENV_VAR, CSLC_PATH_SENTINEL, config.executable },
        ),
        .implicit_path_lookup => setLastErrorFmt(
            "cslc was not found on PATH (`{s}`); set {s} to an absolute/workspace-relative cslc path or `{s}` to make PATH lookup explicit",
            .{ config.executable, CSLC_ENV_VAR, CSLC_PATH_SENTINEL },
        ),
    }
}

fn setLastErrorFmt(comptime fmt: []const u8, args: anytype) void {
    const text = std.fmt.bufPrint(last_error_buf[0..], fmt, args) catch {
        last_error_len = 0;
        return;
    };
    last_error_len = text.len;
}

fn defaultCslcExecutable() []const u8 {
    return if (builtin.os.tag == .windows) "cslc.exe" else "cslc";
}

fn discoveryLabel(discovery: ToolchainDiscovery) []const u8 {
    return switch (discovery) {
        .explicit_config => "explicit-config",
        .env_path => "environment-path",
        .env_path_lookup => "environment-PATH",
        .implicit_path_lookup => "implicit-PATH",
    };
}

fn trimmedDiagnostic(stderr: []const u8, stdout: []const u8) []const u8 {
    const trimmed_stderr = std.mem.trim(u8, stderr, " \t\r\n");
    if (trimmed_stderr.len != 0) return trimmed_stderr;
    return std.mem.trim(u8, stdout, " \t\r\n");
}

test "element_wise pattern rejects fabric usage" {
    const csl =
        \\//--- layout.csl ---
        \\@set_rectangle(16, 1)
        \\//--- pe_program.csl ---
        \\const sys = @import_module("<memcpy/memcpy>", .{});
        \\fn compute() void { for (@range(u32, 64)) |i| { buf[i] += 1; } sys.unblock_cmd_stream(); }
        \\comptime { @export_symbol(compute); }
    ;
    const result = validatePattern(csl, .element_wise);
    try std.testing.expect(result.valid);
}

test "element_wise pattern catches fabric DSD" {
    const csl =
        \\//--- layout.csl ---
        \\@set_rectangle(16, 1)
        \\//--- pe_program.csl ---
        \\const sys = @import_module("<memcpy/memcpy>", .{});
        \\var fab = @get_dsd(fabin_dsd, .{});
        \\fn compute() void { for (@range(u32, 64)) |i| { buf[i] += 1; } sys.unblock_cmd_stream(); }
        \\comptime { @export_symbol(compute); }
    ;
    const result = validatePattern(csl, .element_wise);
    try std.testing.expect(!result.valid);
    try std.testing.expect(result.error_count == 1);
}

test "reduction pattern requires fabric DSDs" {
    const csl_no_fabric =
        \\//--- layout.csl ---
        \\@set_rectangle(16, 1)
        \\//--- pe_program.csl ---
        \\const sys = @import_module("<memcpy/memcpy>", .{});
        \\fn compute() void { sys.unblock_cmd_stream(); }
        \\comptime { @export_symbol(compute); }
    ;
    const result = validatePattern(csl_no_fabric, .reduction);
    try std.testing.expect(!result.valid);
    try std.testing.expect(result.error_count >= 1);
}

test "dequant pattern requires Q4K constants" {
    const csl_with_q4k =
        \\//--- layout.csl ---
        \\@set_rectangle(16, 1)
        \\//--- pe_program.csl ---
        \\const sys = @import_module("<memcpy/memcpy>", .{});
        \\const QK_K: u32 = 256;
        \\fn compute() void { sys.unblock_cmd_stream(); }
        \\comptime { @export_symbol(compute); }
    ;
    const result = validatePattern(csl_with_q4k, .dequant);
    try std.testing.expect(result.valid);
}

test "base validation catches missing sections" {
    const bad_csl = "just some random text";
    const result = validatePattern(bad_csl, .element_wise);
    try std.testing.expect(!result.valid);
    try std.testing.expect(result.error_count == 1);
}
