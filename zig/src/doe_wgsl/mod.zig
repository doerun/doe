// doe_wgsl/mod.zig — WGSL compiler module entry point.
//
// Public API for parsing WGSL source, validating it through semantic analysis,
// lowering it to typed IR, and then invoking legacy backend emitters.

pub const token = @import("token.zig");
pub const lexer = @import("lexer.zig");
pub const ast = @import("ast.zig");
pub const parser = @import("parser.zig");
pub const sema = @import("sema.zig");
pub const ir = @import("ir.zig");
pub const ir_builder = @import("ir_builder.zig");
pub const ir_validate = @import("ir_validate.zig");
pub const emit_msl = @import("emit_msl.zig");
pub const emit_hlsl = @import("emit_hlsl.zig");
pub const emit_spirv = @import("emit_spirv.zig");
pub const emit_spirv_fn = @import("emit_spirv_fn.zig");
pub const emit_spirv_stages = @import("emit_spirv_stages.zig");
pub const emit_dxil = @import("emit_dxil.zig");
const legacy_msl = @import("doe_wgsl_msl.zig");

const std = @import("std");

pub const TranslateError = error{
    InvalidWgsl,
    InvalidIr,
    DuplicateSymbol,
    InvalidAttribute,
    InvalidType,
    OutputTooLarge,
    OutOfMemory,
    ShaderToolchainUnavailable,
    UnexpectedToken,
    TypeMismatch,
    UnknownIdentifier,
    UnknownType,
    UnsupportedBuiltin,
    UnsupportedConstruct,
    UnsupportedWgsl,
};

pub const MAX_OUTPUT: usize = emit_msl.MAX_OUTPUT;
pub const MAX_HLSL_OUTPUT: usize = emit_hlsl.MAX_OUTPUT;
pub const MAX_SPIRV_OUTPUT: usize = emit_spirv.MAX_OUTPUT;
pub const MAX_DXIL_OUTPUT: usize = emit_dxil.MAX_OUTPUT;
pub const DXIL_DXC_ENV_VAR: []const u8 = emit_dxil.DXC_ENV_VAR;
pub const DXIL_DXC_PATH_SENTINEL: []const u8 = emit_dxil.DXC_PATH_SENTINEL;
pub const DxilToolchainConfig = emit_dxil.ToolchainConfig;
pub const DxilToolchainDiscovery = emit_dxil.ToolchainDiscovery;
pub const MAX_BINDINGS: usize = 16;

pub const BindingKind = enum(u32) {
    buffer,
    sampler,
    texture,
    storage_texture,
};

pub const BindingMeta = struct {
    group: u32,
    binding: u32,
    kind: BindingKind,
    addr_space: ir.AddressSpace,
    access: ir.AccessMode,
};

pub const CompilationStage = enum {
    none,
    parser,
    sema,
    ir_builder,
    ir_validate,
    msl_emit,
    hlsl_emit,
    spirv_emit,
    dxil_emit,
};

const LAST_ERROR_CAP: usize = 256;
const LAST_CONTEXT_CAP: usize = 96;
var last_error_buf: [LAST_ERROR_CAP]u8 = undefined;
var last_error_len: usize = 0;
var last_error_stage: CompilationStage = .none;
var last_error_kind: ?TranslateError = null;
var last_error_line: u32 = 0;
var last_error_column: u32 = 0;
var last_error_context_buf: [LAST_CONTEXT_CAP]u8 = undefined;
var last_error_context_len: usize = 0;

pub const SourceLocation = struct {
    line: u32,
    column: u32,
};

pub const LastErrorInfo = struct {
    stage: CompilationStage,
    kind: ?TranslateError,
    location: ?SourceLocation,
    context: []const u8,
};

fn clearLastError() void {
    last_error_stage = .none;
    last_error_kind = null;
    last_error_len = 0;
    last_error_line = 0;
    last_error_column = 0;
    last_error_context_len = 0;
}

fn setLastError(stage: CompilationStage, kind: TranslateError, source: ?[]const u8, loc: ?token.Token.Loc) void {
    last_error_stage = stage;
    last_error_kind = kind;
    recordSourceContext(source, loc);
    const text = (if (last_error_line != 0 and last_error_context_len != 0)
        std.fmt.bufPrint(&last_error_buf, "{s}: {s} at {d}:{d} near `{s}`", .{
            @tagName(stage),
            @errorName(kind),
            last_error_line,
            last_error_column,
            last_error_context_buf[0..last_error_context_len],
        })
    else
        std.fmt.bufPrint(&last_error_buf, "{s}: {s}", .{
            @tagName(stage),
            @errorName(kind),
        })) catch {
        last_error_len = 0;
        return;
    };
    last_error_len = text.len;
}

fn setLastErrorDetail(stage: CompilationStage, kind: TranslateError, detail: []const u8) void {
    last_error_stage = stage;
    last_error_kind = kind;
    last_error_line = 0;
    last_error_column = 0;
    last_error_context_len = 0;
    const text = std.fmt.bufPrint(&last_error_buf, "{s}: {s}: {s}", .{
        @tagName(stage),
        @errorName(kind),
        detail,
    }) catch {
        last_error_len = 0;
        return;
    };
    last_error_len = text.len;
}

fn recordSourceContext(source: ?[]const u8, loc: ?token.Token.Loc) void {
    last_error_line = 0;
    last_error_column = 0;
    last_error_context_len = 0;

    const src = source orelse return;
    const span = loc orelse return;
    if (span.start > src.len or span.end > src.len or span.start > span.end) return;

    var line: u32 = 1;
    var column: u32 = 1;
    var line_start: usize = 0;
    var i: usize = 0;
    while (i < span.start) : (i += 1) {
        if (src[i] == '\n') {
            line += 1;
            column = 1;
            line_start = i + 1;
        } else {
            column += 1;
        }
    }

    var line_end = span.end;
    while (line_end < src.len and src[line_end] != '\n' and src[line_end] != '\r') : (line_end += 1) {}
    const full_line = src[line_start..line_end];
    const token_rel = span.start - line_start;

    var snippet_start: usize = 0;
    if (full_line.len > LAST_CONTEXT_CAP and token_rel > LAST_CONTEXT_CAP / 2) {
        snippet_start = token_rel - LAST_CONTEXT_CAP / 2;
        if (snippet_start + LAST_CONTEXT_CAP > full_line.len) {
            snippet_start = full_line.len - LAST_CONTEXT_CAP;
        }
    }
    const snippet = full_line[snippet_start..@min(full_line.len, snippet_start + LAST_CONTEXT_CAP)];
    @memcpy(last_error_context_buf[0..snippet.len], snippet);
    last_error_context_len = snippet.len;
    last_error_line = line;
    last_error_column = column;
}

fn tokenLoc(tree: *const ast.Ast, token_idx: ?u32) ?token.Token.Loc {
    const idx = token_idx orelse return null;
    if (idx >= tree.tokens.items.len) return null;
    return tree.tokens.items[idx].loc;
}

pub fn lastErrorKind() ?TranslateError {
    return last_error_kind;
}

pub fn lastErrorContext() []const u8 {
    return last_error_context_buf[0..last_error_context_len];
}

pub fn lastErrorInfo() LastErrorInfo {
    return .{
        .stage = last_error_stage,
        .kind = last_error_kind,
        .location = if (last_error_line == 0) null else .{
            .line = last_error_line,
            .column = last_error_column,
        },
        .context = last_error_context_buf[0..last_error_context_len],
    };
}

pub fn lastErrorStage() CompilationStage {
    return last_error_stage;
}

pub fn lastErrorMessage() []const u8 {
    return last_error_buf[0..last_error_len];
}

pub fn lastErrorLine() u32 {
    return last_error_line;
}

pub fn lastErrorColumn() u32 {
    return last_error_column;
}

pub fn analyzeToIr(allocator: std.mem.Allocator, wgsl: []const u8) TranslateError!ir.Module {
    clearLastError();
    var tree = parser.parseSource(allocator, wgsl) catch |err| {
        const kind = switch (err) {
            error.OutOfMemory => TranslateError.OutOfMemory,
            error.UnexpectedToken => TranslateError.UnexpectedToken,
        };
        // Recover the byte-offset span saved by the parser before the Ast was freed.
        const fail_loc = parser.lastFailureContext().loc;
        setLastError(.parser, kind, wgsl, fail_loc);
        return kind;
    };
    defer tree.deinit();

    var semantic = sema.analyze(allocator, &tree) catch |err| {
        const kind = mapSemanticError(err);
        setLastError(.sema, kind, tree.source, tokenLoc(&tree, sema.lastFailureContext().token_idx));
        return kind;
    };
    defer semantic.deinit();

    var module = ir_builder.build(allocator, &tree, &semantic) catch |err| {
        const kind = mapIrBuildError(err);
        setLastError(.ir_builder, kind, tree.source, tokenLoc(&tree, ir_builder.lastFailureContext().token_idx));
        return kind;
    };
    errdefer module.deinit();
    ir_validate.validate(&module) catch {
        setLastError(.ir_validate, TranslateError.InvalidIr, null, null);
        return TranslateError.InvalidIr;
    };
    return module;
}

pub fn extractBindings(allocator: std.mem.Allocator, wgsl: []const u8, out: []BindingMeta) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    var count: usize = 0;
    for (module_ir.globals.items) |global| {
        if (global.binding == null) continue;
        const binding_type, const binding_access = switch (module_ir.types.get(global.ty)) {
            .sampler => .{ BindingKind.sampler, ir.AccessMode.read },
            .texture_2d => .{ BindingKind.texture, ir.AccessMode.read },
            .storage_texture_2d => |storage_tex| .{ BindingKind.storage_texture, storage_tex.access },
            else => .{ BindingKind.buffer, global.access orelse switch (global.addr_space orelse .private) {
                .uniform => ir.AccessMode.read,
                .storage => ir.AccessMode.read_write,
                else => ir.AccessMode.read,
            } },
        };
        if (count >= out.len) break;
        out[count] = .{
            .group = global.binding.?.group,
            .binding = global.binding.?.binding,
            .kind = binding_type,
            .addr_space = global.addr_space orelse .handle,
            .access = binding_access,
        };
        count += 1;
    }
    return count;
}

pub fn translateToMsl(allocator: std.mem.Allocator, wgsl: []const u8, out: []u8) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    return emit_msl.emit(&module_ir, out) catch |err| {
        const kind = switch (err) {
            error.OutputTooLarge => TranslateError.OutputTooLarge,
            error.InvalidIr => TranslateError.InvalidIr,
        };
        setLastError(.msl_emit, kind, null, null);
        return kind;
    };
}

pub fn translateToHlsl(allocator: std.mem.Allocator, wgsl: []const u8, out: []u8) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    return emit_hlsl.emit(&module_ir, out) catch |err| {
        const kind = switch (err) {
            error.OutputTooLarge => TranslateError.OutputTooLarge,
            error.InvalidIr => TranslateError.InvalidIr,
        };
        setLastError(.hlsl_emit, kind, null, null);
        return kind;
    };
}

pub fn translateToSpirv(allocator: std.mem.Allocator, wgsl: []const u8, out: []u8) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    return emit_spirv.emit(&module_ir, out) catch |err| {
        const kind = switch (err) {
            error.OutputTooLarge => TranslateError.OutputTooLarge,
            error.UnsupportedConstruct => TranslateError.UnsupportedConstruct,
            error.InvalidIr => TranslateError.InvalidIr,
            error.OutOfMemory => TranslateError.OutOfMemory,
        };
        setLastError(.spirv_emit, kind, null, null);
        return kind;
    };
}

pub fn translateToDxil(allocator: std.mem.Allocator, wgsl: []const u8, out: []u8) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    return emit_dxil.emit(&module_ir, out) catch |err| {
        const detail = emit_dxil.lastErrorMessage();
        const kind = switch (err) {
            error.OutputTooLarge => TranslateError.OutputTooLarge,
            error.UnsupportedConstruct => TranslateError.UnsupportedConstruct,
            error.InvalidIr => TranslateError.InvalidIr,
            error.OutOfMemory => TranslateError.OutOfMemory,
            error.ShaderToolchainUnavailable => TranslateError.ShaderToolchainUnavailable,
        };
        if (detail.len != 0)
            setLastErrorDetail(.dxil_emit, kind, detail)
        else
            setLastError(.dxil_emit, kind, null, null);
        return kind;
    };
}

pub fn translateToDxilWithToolchainConfig(
    allocator: std.mem.Allocator,
    wgsl: []const u8,
    out: []u8,
    config: emit_dxil.ToolchainConfig,
) TranslateError!usize {
    var module_ir = try analyzeToIr(allocator, wgsl);
    defer module_ir.deinit();

    return emit_dxil.emitWithToolchainConfig(&module_ir, out, config) catch |err| {
        const detail = emit_dxil.lastErrorMessage();
        const kind = switch (err) {
            error.OutputTooLarge => TranslateError.OutputTooLarge,
            error.UnsupportedConstruct => TranslateError.UnsupportedConstruct,
            error.InvalidIr => TranslateError.InvalidIr,
            error.OutOfMemory => TranslateError.OutOfMemory,
            error.ShaderToolchainUnavailable => TranslateError.ShaderToolchainUnavailable,
        };
        if (detail.len != 0)
            setLastErrorDetail(.dxil_emit, kind, detail)
        else
            setLastError(.dxil_emit, kind, null, null);
        return kind;
    };
}

fn mapSemanticError(err: anyerror) TranslateError {
    return switch (err) {
        error.OutOfMemory => TranslateError.OutOfMemory,
        error.UnsupportedConstruct => TranslateError.UnsupportedConstruct,
        error.UnsupportedBuiltin => TranslateError.UnsupportedBuiltin,
        error.DuplicateSymbol => TranslateError.DuplicateSymbol,
        error.InvalidAttribute => TranslateError.InvalidAttribute,
        error.InvalidType => TranslateError.InvalidType,
        error.TypeMismatch => TranslateError.TypeMismatch,
        error.UnknownIdentifier => TranslateError.UnknownIdentifier,
        error.UnknownType => TranslateError.UnknownType,
        error.InvalidWgsl => TranslateError.InvalidWgsl,
        else => TranslateError.InvalidWgsl,
    };
}

fn mapIrBuildError(err: anyerror) TranslateError {
    return switch (err) {
        error.OutOfMemory => TranslateError.OutOfMemory,
        error.UnsupportedConstruct => TranslateError.UnsupportedConstruct,
        error.InvalidWgsl => TranslateError.InvalidWgsl,
        error.InvalidIr => TranslateError.InvalidIr,
        else => TranslateError.InvalidIr,
    };
}

test {
    _ = token;
    _ = lexer;
    _ = ast;
    _ = parser;
    _ = sema;
    _ = ir;
    _ = ir_builder;
    _ = ir_validate;
    _ = emit_msl;
    _ = emit_hlsl;
    _ = emit_spirv;
    _ = emit_spirv_fn;
    _ = emit_spirv_stages;
    _ = emit_dxil;
    _ = @import("mod_test.zig");
}
