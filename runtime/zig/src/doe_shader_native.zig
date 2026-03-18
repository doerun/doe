// doe_shader_native.zig — Shader module and compute pipeline creation for Doe native Metal backend.
// Sharded from doe_wgpu_native.zig: WGSL→MSL translation, MTLLibrary/MTLComputePipelineState creation.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const wgsl_compiler = @import("doe_wgsl/mod.zig");
const wgsl_ir = @import("doe_wgsl/ir.zig");
const native = @import("doe_wgpu_native.zig");
const bridge = @import("backend/metal/metal_bridge_decls.zig");
const metal_bridge_device_new_compute_pipeline = bridge.metal_bridge_device_new_compute_pipeline;
const metal_bridge_device_new_library_msl = bridge.metal_bridge_device_new_library_msl;
const metal_bridge_library_new_function = bridge.metal_bridge_library_new_function;
const metal_bridge_release = bridge.metal_bridge_release;

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const ERR_CAP = native.ERR_CAP;
const label_store = native.label_store;

const DoeDevice = native.DoeDevice;
const DoeShaderModule = native.DoeShaderModule;
const DoeComputePipeline = native.DoeComputePipeline;
const DoePipelineLayout = native.DoePipelineLayout;
const CompilationMessageKind = native.CompilationMessageKind;
const LAST_ERROR_CAP: usize = 512;
const LAST_ERROR_META_CAP: usize = 64;
const DIAGNOSTIC_DIRECTIVE_INFO: []const u8 =
    "WGSL diagnostic directives are parsed on this path and currently reported as advisory compilation info only.";
var last_error_buf: [LAST_ERROR_CAP]u8 = undefined;
var last_error_len: usize = 0;
var last_error_stage_buf: [LAST_ERROR_META_CAP]u8 = undefined;
var last_error_stage_len: usize = 0;
var last_error_kind_buf: [LAST_ERROR_META_CAP]u8 = undefined;
var last_error_kind_len: usize = 0;
var last_error_line: u32 = 0;
var last_error_col: u32 = 0;

fn clear_last_error() void {
    last_error_len = 0;
    last_error_stage_len = 0;
    last_error_kind_len = 0;
    last_error_line = 0;
    last_error_col = 0;
}

fn set_last_error(message: []const u8) void {
    const len = @min(message.len, last_error_buf.len - 1);
    @memcpy(last_error_buf[0..len], message[0..len]);
    last_error_buf[len] = 0;
    last_error_len = len;
}

fn set_last_error_fmt(comptime fmt: []const u8, args: anytype) void {
    const text = std.fmt.bufPrint(&last_error_buf, fmt, args) catch {
        last_error_len = 0;
        return;
    };
    last_error_len = text.len;
}

fn set_last_error_meta(buf: []u8, len_out: *usize, text: []const u8) void {
    const len = @min(text.len, buf.len - 1);
    @memcpy(buf[0..len], text[0..len]);
    buf[len] = 0;
    len_out.* = len;
}

fn set_last_error_stage_name(stage: []const u8) void {
    set_last_error_meta(&last_error_stage_buf, &last_error_stage_len, stage);
}

fn set_last_error_stage(stage: wgsl_compiler.CompilationStage) void {
    if (stage == .none) {
        last_error_stage_len = 0;
        return;
    }
    set_last_error_stage_name(@tagName(stage));
}

fn set_last_error_kind(kind: []const u8) void {
    set_last_error_meta(&last_error_kind_buf, &last_error_kind_len, kind);
}

fn capture_wgsl_error_location() void {
    last_error_line = wgsl_compiler.lastErrorLine();
    last_error_col = wgsl_compiler.lastErrorColumn();
}

pub export fn doeNativeCopyLastErrorMessage(out_ptr: ?[*]u8, out_len: usize) callconv(.c) usize {
    if (out_ptr == null or out_len == 0 or last_error_len == 0) return last_error_len;
    const dst = out_ptr.?[0..out_len];
    const copy_len = @min(last_error_len, out_len - 1);
    @memcpy(dst[0..copy_len], last_error_buf[0..copy_len]);
    dst[copy_len] = 0;
    return last_error_len;
}

pub export fn doeNativeCopyLastErrorStage(out_ptr: ?[*]u8, out_len: usize) callconv(.c) usize {
    if (out_ptr == null or out_len == 0 or last_error_stage_len == 0) return last_error_stage_len;
    const dst = out_ptr.?[0..out_len];
    const copy_len = @min(last_error_stage_len, out_len - 1);
    @memcpy(dst[0..copy_len], last_error_stage_buf[0..copy_len]);
    dst[copy_len] = 0;
    return last_error_stage_len;
}

pub export fn doeNativeCopyLastErrorKind(out_ptr: ?[*]u8, out_len: usize) callconv(.c) usize {
    if (out_ptr == null or out_len == 0 or last_error_kind_len == 0) return last_error_kind_len;
    const dst = out_ptr.?[0..out_len];
    const copy_len = @min(last_error_kind_len, out_len - 1);
    @memcpy(dst[0..copy_len], last_error_kind_buf[0..copy_len]);
    dst[copy_len] = 0;
    return last_error_kind_len;
}

pub export fn doeNativeGetLastErrorLine() callconv(.c) u32 {
    return last_error_line;
}

pub export fn doeNativeGetLastErrorColumn() callconv(.c) u32 {
    return last_error_col;
}

pub export fn doeNativeCheckShaderSource(code_ptr: ?[*]const u8, code_len: usize) callconv(.c) u32 {
    clear_last_error();
    const ptr = code_ptr orelse {
        set_last_error_stage_name("native_check");
        set_last_error_kind("InvalidInput");
        set_last_error("shader check failed: WGSL source pointer is null");
        return 0;
    };
    const wgsl = ptr[0..code_len];
    var msl_buf: [wgsl_compiler.MAX_OUTPUT]u8 = undefined;
    _ = wgsl_compiler.translateToMsl(alloc, wgsl, &msl_buf) catch |err| {
        set_last_error_stage(wgsl_compiler.lastErrorStage());
        set_last_error_kind(@errorName(err));
        capture_wgsl_error_location();
        const detail = wgsl_compiler.lastErrorMessage();
        if (detail.len > 0) {
            set_last_error(detail);
        } else {
            set_last_error_fmt("{s}: {s}", .{ @tagName(wgsl_compiler.lastErrorStage()), @errorName(err) });
        }
        return 0;
    };
    return 1;
}

pub export fn doeNativeShaderModuleGetBindings(raw: ?*anyopaque, out_ptr: ?[*]native.BindingInfo, out_len: usize) callconv(.c) usize {
    const sm = cast(DoeShaderModule, raw) orelse return 0;
    const count: usize = sm.binding_count;
    if (out_ptr) |out| {
        const copy_len = @min(count, out_len);
        @memcpy(out[0..copy_len], sm.bindings[0..copy_len]);
    }
    return count;
}

// ============================================================
// Shader Module — sType dispatch
// ============================================================

/// Resolve a WGPUStringView to a byte slice, handling WGPU_STRLEN sentinel.
fn resolveStringView(sv: types.WGPUStringView) ?[]const u8 {
    const data = sv.data orelse return null;
    const len = if (sv.length == types.WGPU_STRLEN)
        std.mem.len(@as([*:0]const u8, @ptrCast(data)))
    else
        sv.length;
    return data[0..len];
}

/// Normalize workgroup size from descriptor: 0 → 1 (unknown defaults to 1).
fn normalizeWorkgroupDim(v: u32) u32 {
    return if (v > 0) v else 1;
}

fn offset_to_line_column(src: []const u8, offset: usize) struct { line: u32, column: u32 } {
    var line: u32 = 1;
    var column: u32 = 1;
    var i: usize = 0;
    const clamped_offset = @min(offset, src.len);
    while (i < clamped_offset) : (i += 1) {
        if (src[i] == '\n') {
            line += 1;
            column = 1;
        } else {
            column += 1;
        }
    }
    return .{ .line = line, .column = column };
}

fn set_module_compilation_message(
    sm: *DoeShaderModule,
    kind: CompilationMessageKind,
    message: []const u8,
    line: u32,
    column: u32,
) void {
    if (sm.compilation_message) |existing| {
        alloc.free(existing);
        sm.compilation_message = null;
    }
    sm.compilation_message = alloc.dupe(u8, message) catch null;
    sm.compilation_message_kind = kind;
    sm.compilation_message_line = line;
    sm.compilation_message_column = column;
}

fn set_module_info_from_diagnostic_directive(sm: *DoeShaderModule, wgsl: []const u8) void {
    const offset = std.mem.indexOf(u8, wgsl, "diagnostic") orelse return;
    const loc = offset_to_line_column(wgsl, offset);
    set_module_compilation_message(sm, .info, DIAGNOSTIC_DIRECTIVE_INFO, loc.line, loc.column);
}

fn set_module_warning_from_compiler_state(
    sm: *DoeShaderModule,
    fallback_message: []const u8,
) void {
    const detail = wgsl_compiler.lastErrorMessage();
    const line = wgsl_compiler.lastErrorLine();
    const column = wgsl_compiler.lastErrorColumn();
    const message = if (detail.len > 0) detail else fallback_message;
    set_module_compilation_message(sm, .warning, message, line, column);
}

pub export fn doeNativeDeviceCreateShaderModule(dev_raw: ?*anyopaque, desc: ?*const types.WGPUShaderModuleDescriptor) callconv(.c) ?*anyopaque {
    clear_last_error();
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;
    const chain = d.nextInChain orelse return null;

    const result = switch (chain.sType) {
        types.WGPUSType_ShaderSourceWGSL => createFromWGSL(dev, chain),
        types.WGPUSType_ShaderSourceMSL => createFromMSL(dev, chain),
        types.WGPUSType_ShaderSourceSPIRV => createFromSPIRV(chain),
        types.WGPUSType_ShaderSourceHLSL => createFromHLSL(chain),
        else => {
            set_last_error_stage_name("native_shader_create");
            set_last_error_kind("UnsupportedShaderFormat");
            set_last_error_fmt("unsupported shader source sType: 0x{x:0>8}", .{chain.sType});
            std.log.err("doe: createShaderModule failed: unsupported sType 0x{x:0>8}", .{chain.sType});
            return null;
        },
    };
    if (result != null) label_store.set(result, d.label.data, d.label.length);
    return result;
}

// ============================================================
// WGSL path (existing behavior, refactored into helper)
// ============================================================

fn createFromWGSL(dev: *DoeDevice, chain: *const types.WGPUChainedStruct) ?*anyopaque {
    const wgsl_chain: *const types.WGPUShaderSourceWGSL = @ptrCast(@alignCast(chain));
    const wgsl = resolveStringView(wgsl_chain.code) orelse return null;

    if (dev.backend == .vulkan) return createFromWGSLVulkan(dev, wgsl);

    // Translate WGSL → MSL.
    var msl_buf: [wgsl_compiler.MAX_OUTPUT]u8 = undefined;
    const msl_len = wgsl_compiler.translateToMsl(alloc, wgsl, &msl_buf) catch |err| {
        set_last_error_stage(wgsl_compiler.lastErrorStage());
        set_last_error_kind(@errorName(err));
        capture_wgsl_error_location();
        const detail = wgsl_compiler.lastErrorMessage();
        if (detail.len > 0) {
            set_last_error_fmt("WGSL→MSL translation failed: {s}", .{detail});
        } else {
            set_last_error_fmt("WGSL→MSL translation failed: {s}", .{@errorName(err)});
        }
        std.log.err("doe: createShaderModule failed: {s}", .{last_error_buf[0..last_error_len]});
        return null;
    };

    // Compile MSL → MTLLibrary.
    var err_buf: [ERR_CAP]u8 = undefined;
    const lib = compileMslToLibrary(dev, &msl_buf, msl_len, &err_buf) orelse return null;

    const sm = make(DoeShaderModule) orelse {
        metal_bridge_release(lib);
        return null;
    };
    sm.* = .{ .mtl_library = lib };
    set_module_info_from_diagnostic_directive(sm, wgsl);
    sm.needs_sizes_buf = std.mem.indexOf(u8, wgsl, "arrayLength") != null;
    const wg = native.extractWorkgroupSize(wgsl);
    sm.wg_x = wg.x;
    sm.wg_y = wg.y;
    sm.wg_z = wg.z;
    // Retain WGSL source for re-translation with pipeline override constants.
    sm.wgsl_source = alloc.dupe(u8, wgsl) catch null;
    // Extract binding metadata (non-fatal on failure).
    var bind_meta: [native.MAX_SHADER_BINDINGS]wgsl_compiler.BindingMeta = undefined;
    const bind_count = wgsl_compiler.extractBindings(alloc, wgsl, &bind_meta) catch |bind_err| blk: {
        set_last_error_stage(wgsl_compiler.lastErrorStage());
        set_last_error_kind(@errorName(bind_err));
        capture_wgsl_error_location();
        const detail = wgsl_compiler.lastErrorMessage();
        if (detail.len > 0) {
            set_last_error_fmt("binding extraction failed (shader compiled): {s}", .{detail});
        } else {
            set_last_error_fmt("binding extraction failed (shader compiled): {s}", .{@errorName(bind_err)});
        }
        std.log.warn("doe: createShaderModule: binding extraction failed ({s}); proceeding with 0 bindings", .{@errorName(bind_err)});
        set_module_warning_from_compiler_state(sm, "binding extraction failed after successful shader compilation");
        break :blk 0;
    };
    for (0..bind_count) |i| {
        sm.bindings[i] = .{
            .group = bind_meta[i].group,
            .binding = bind_meta[i].binding,
            .kind = @intFromEnum(bind_meta[i].kind),
            .addr_space = @intFromEnum(bind_meta[i].addr_space),
            .access = @intFromEnum(bind_meta[i].access),
        };
    }
    sm.binding_count = @intCast(bind_count);
    return toOpaque(sm);
}

// ============================================================
// Vulkan WGSL path — WGSL → SPIR-V, no Metal library
// ============================================================

fn createFromWGSLVulkan(dev: *DoeDevice, wgsl: []const u8) ?*anyopaque {
    _ = dev;
    const sm = make(DoeShaderModule) orelse return null;
    sm.* = .{};
    set_module_info_from_diagnostic_directive(sm, wgsl);
    sm.needs_sizes_buf = std.mem.indexOf(u8, wgsl, "arrayLength") != null;
    const wg = native.extractWorkgroupSize(wgsl);
    sm.wg_x = wg.x;
    sm.wg_y = wg.y;
    sm.wg_z = wg.z;
    sm.binding_count = 0;

    const vk_compute = @import("doe_vulkan_compute_native.zig");
    vk_compute.vulkan_create_shader_module(sm, wgsl) catch |err| {
        set_last_error_stage_name("native_shader_create");
        set_last_error_kind(@errorName(err));
        set_last_error_fmt("Vulkan WGSL→SPIR-V compilation failed: {s}", .{@errorName(err)});
        std.log.err("doe: createShaderModule (Vulkan) failed: {s}", .{@errorName(err)});
        alloc.destroy(sm);
        return null;
    };
    sm.wgsl_source = alloc.dupe(u8, wgsl) catch null;

    // Extract binding metadata for getBindGroupLayout (non-fatal on failure).
    var bind_meta: [native.MAX_SHADER_BINDINGS]wgsl_compiler.BindingMeta = undefined;
    const bind_count = wgsl_compiler.extractBindings(alloc, wgsl, &bind_meta) catch |bind_err| blk: {
        set_module_warning_from_compiler_state(sm, "binding extraction failed after successful Vulkan shader compilation");
        std.log.warn("doe: createShaderModule (Vulkan): binding extraction failed ({s}); proceeding with 0 bindings", .{@errorName(bind_err)});
        break :blk 0;
    };
    for (0..bind_count) |i| {
        sm.bindings[i] = .{
            .group = bind_meta[i].group,
            .binding = bind_meta[i].binding,
            .kind = @intFromEnum(bind_meta[i].kind),
            .addr_space = @intFromEnum(bind_meta[i].addr_space),
            .access = @intFromEnum(bind_meta[i].access),
        };
    }
    sm.binding_count = @intCast(bind_count);
    return toOpaque(sm);
}

// ============================================================
// MSL path — pre-translated Metal Shading Language source
// ============================================================

fn createFromMSL(dev: *DoeDevice, chain: *const types.WGPUChainedStruct) ?*anyopaque {
    const msl_chain: *const types.WGPUShaderSourceMSL = @ptrCast(@alignCast(chain));
    const msl_src = resolveStringView(msl_chain.code) orelse {
        set_last_error_stage_name("native_shader_create");
        set_last_error_kind("InvalidInput");
        set_last_error("pre-translated MSL source pointer is null");
        return null;
    };

    // Compile MSL → MTLLibrary directly (skip WGSL translation).
    var err_buf: [ERR_CAP]u8 = undefined;
    const lib = metal_bridge_device_new_library_msl(
        dev.mtl_device,
        msl_src.ptr,
        msl_src.len,
        &err_buf,
        ERR_CAP,
    ) orelse {
        const err_msg = std.mem.sliceTo(&err_buf, 0);
        set_last_error_stage_name("native_compile");
        set_last_error_kind("MSLCompilationFailed");
        if (err_msg.len > 0) {
            set_last_error_fmt("pre-translated MSL compilation failed: {s}", .{err_msg});
            std.log.err("doe: createShaderModule (MSL) failed: {s}", .{err_msg});
        } else {
            set_last_error("pre-translated MSL compilation failed: MTLLibrary creation returned null");
            std.log.err("doe: createShaderModule (MSL) failed: MTLLibrary returned null", .{});
        }
        return null;
    };

    const sm = make(DoeShaderModule) orelse {
        metal_bridge_release(lib);
        return null;
    };
    sm.* = .{ .mtl_library = lib };
    // Binding metadata is unavailable from pre-translated MSL (degraded mode).
    sm.binding_count = 0;
    sm.needs_sizes_buf = false;
    sm.wg_x = normalizeWorkgroupDim(msl_chain.workgroup_size_x);
    sm.wg_y = normalizeWorkgroupDim(msl_chain.workgroup_size_y);
    sm.wg_z = normalizeWorkgroupDim(msl_chain.workgroup_size_z);
    return toOpaque(sm);
}

// ============================================================
// SPIR-V path — store binary for Vulkan pipeline creation
// ============================================================

fn createFromSPIRV(chain: *const types.WGPUChainedStruct) ?*anyopaque {
    const spirv_chain: *const types.WGPUShaderSourceSPIRV = @ptrCast(@alignCast(chain));

    if (spirv_chain.code_size == 0 or spirv_chain.code_size % 4 != 0) {
        set_last_error_stage_name("native_shader_create");
        set_last_error_kind("InvalidSPIRV");
        set_last_error("SPIR-V code_size must be a positive multiple of 4");
        return null;
    }

    const word_count = spirv_chain.code_size / 4;
    const spirv_copy = alloc.alloc(u32, word_count) catch {
        set_last_error_stage_name("native_shader_create");
        set_last_error_kind("OutOfMemory");
        set_last_error("failed to allocate SPIR-V storage");
        return null;
    };
    @memcpy(spirv_copy, spirv_chain.code[0..word_count]);

    const sm = make(DoeShaderModule) orelse {
        alloc.free(spirv_copy);
        return null;
    };
    sm.* = .{};
    sm.spirv_data = spirv_copy;
    sm.binding_count = 0;
    sm.needs_sizes_buf = false;
    sm.wg_x = normalizeWorkgroupDim(spirv_chain.workgroup_size_x);
    sm.wg_y = normalizeWorkgroupDim(spirv_chain.workgroup_size_y);
    sm.wg_z = normalizeWorkgroupDim(spirv_chain.workgroup_size_z);
    return toOpaque(sm);
}

// ============================================================
// HLSL path — store source for D3D12 DXC compilation
// ============================================================

fn createFromHLSL(chain: *const types.WGPUChainedStruct) ?*anyopaque {
    const hlsl_chain: *const types.WGPUShaderSourceHLSL = @ptrCast(@alignCast(chain));
    const hlsl_src = resolveStringView(hlsl_chain.code) orelse {
        set_last_error_stage_name("native_shader_create");
        set_last_error_kind("InvalidInput");
        set_last_error("HLSL source pointer is null");
        return null;
    };

    const hlsl_copy = alloc.alloc(u8, hlsl_src.len) catch {
        set_last_error_stage_name("native_shader_create");
        set_last_error_kind("OutOfMemory");
        set_last_error("failed to allocate HLSL storage");
        return null;
    };
    @memcpy(hlsl_copy, hlsl_src);

    const sm = make(DoeShaderModule) orelse {
        alloc.free(hlsl_copy);
        return null;
    };
    sm.* = .{};
    sm.hlsl_source = hlsl_copy;
    sm.binding_count = 0;
    sm.needs_sizes_buf = false;
    sm.wg_x = normalizeWorkgroupDim(hlsl_chain.workgroup_size_x);
    sm.wg_y = normalizeWorkgroupDim(hlsl_chain.workgroup_size_y);
    sm.wg_z = normalizeWorkgroupDim(hlsl_chain.workgroup_size_z);
    return toOpaque(sm);
}

// ============================================================
// Shared MSL compilation helper
// ============================================================

fn compileMslToLibrary(dev: *DoeDevice, msl_buf: [*]const u8, msl_len: usize, err_buf: *[ERR_CAP]u8) ?*anyopaque {
    return metal_bridge_device_new_library_msl(
        dev.mtl_device,
        msl_buf,
        msl_len,
        err_buf,
        ERR_CAP,
    ) orelse {
        const err_msg = std.mem.sliceTo(err_buf, 0);
        set_last_error_stage_name("native_compile");
        set_last_error_kind("MSLCompilationFailed");
        if (err_msg.len > 0) {
            set_last_error_fmt("MSL compilation failed: {s}", .{err_msg});
            std.log.err("doe: createShaderModule failed: MSL compilation error: {s}", .{err_msg});
        } else {
            set_last_error("MSL compilation failed: MTLLibrary creation returned null");
            std.log.err("doe: createShaderModule failed: MTLLibrary creation returned null", .{});
        }
        return null;
    };
}

pub export fn doeNativeShaderModuleRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeShaderModule, raw)) |sm| {
        label_store.remove(raw);
        if (sm.mtl_library) |l| metal_bridge_release(l);
        if (sm.spirv_data) |s| alloc.free(s);
        if (sm.hlsl_source) |h| alloc.free(h);
        if (sm.wgsl_source) |w| alloc.free(w);
        if (sm.compilation_message) |message| alloc.free(message);
        alloc.destroy(sm);
    }
}

// ============================================================
// Compute Pipeline
// ============================================================

fn createComputePipelineVulkan(sm: *DoeShaderModule, layout: ?*DoePipelineLayout) ?*anyopaque {
    const cp = make(DoeComputePipeline) orelse return null;
    cp.* = .{};
    cp.layout = layout;
    cp.wg_x = sm.wg_x;
    cp.wg_y = sm.wg_y;
    cp.wg_z = sm.wg_z;
    cp.needs_sizes_buf = sm.needs_sizes_buf;
    cp.binding_count = sm.binding_count;
    for (0..sm.binding_count) |i| cp.bindings[i] = sm.bindings[i];

    const vk_compute = @import("doe_vulkan_compute_native.zig");
    vk_compute.vulkan_copy_pipeline_spirv(cp, sm) catch {
        set_last_error_stage_name("native_compile");
        set_last_error_kind("OutOfMemory");
        set_last_error("Vulkan compute pipeline creation failed: OOM duplicating SPIR-V");
        std.log.err("doe: createComputePipeline (Vulkan) failed: OOM duplicating SPIR-V", .{});
        alloc.destroy(cp);
        return null;
    };
    return toOpaque(cp);
}

// ============================================================
// Override constants — re-translate WGSL with overrides applied
// ============================================================

const MAX_OVERRIDE_ENTRIES: usize = 64;

/// Convert WGPUConstantEntry C ABI array to wgsl_ir.OverrideEntry slice for the compiler.
/// Returns null if any key pointer is invalid.
fn buildOverrideEntries(
    constants: [*]const types.WGPUConstantEntry,
    count: usize,
    out: *[MAX_OVERRIDE_ENTRIES]wgsl_ir.OverrideEntry,
) ?[]const wgsl_ir.OverrideEntry {
    if (count > MAX_OVERRIDE_ENTRIES) return null;
    for (0..count) |i| {
        const c = constants[i];
        const key_data = c.key.data orelse return null;
        const key_len = if (c.key.length == types.WGPU_STRLEN)
            std.mem.len(@as([*:0]const u8, @ptrCast(key_data)))
        else
            c.key.length;
        out[i] = .{
            .key = key_data[0..key_len],
            .value = c.value,
        };
    }
    return out[0..count];
}

/// Re-translate WGSL source with override constants applied, compile to MTLLibrary.
/// Returns a new MTLLibrary handle (caller must release), or null on failure.
fn recompileWithOverrides(
    dev: *DoeDevice,
    sm: *DoeShaderModule,
    constants: [*]const types.WGPUConstantEntry,
    count: usize,
) ?*anyopaque {
    const wgsl = sm.wgsl_source orelse {
        set_last_error_stage_name("native_compile");
        set_last_error_kind("OverrideConstantsUnavailable");
        set_last_error("pipeline override constants require WGSL source (not pre-translated MSL/SPIR-V)");
        return null;
    };

    var entries: [MAX_OVERRIDE_ENTRIES]wgsl_ir.OverrideEntry = undefined;
    const override_slice = buildOverrideEntries(constants, count, &entries) orelse {
        set_last_error_stage_name("native_compile");
        set_last_error_kind("InvalidOverrideConstants");
        set_last_error("pipeline override constants: invalid key pointer or too many entries");
        return null;
    };

    var msl_buf: [wgsl_compiler.MAX_OUTPUT]u8 = undefined;
    const msl_len = wgsl_compiler.translateToMslWithOverrides(
        alloc,
        wgsl,
        &msl_buf,
        override_slice.ptr,
        override_slice.len,
    ) catch |err| {
        set_last_error_stage(wgsl_compiler.lastErrorStage());
        set_last_error_kind(@errorName(err));
        capture_wgsl_error_location();
        const detail = wgsl_compiler.lastErrorMessage();
        if (detail.len > 0) {
            set_last_error_fmt("WGSL→MSL re-translation with overrides failed: {s}", .{detail});
        } else {
            set_last_error_fmt("WGSL→MSL re-translation with overrides failed: {s}", .{@errorName(err)});
        }
        return null;
    };

    var err_buf: [ERR_CAP]u8 = undefined;
    return compileMslToLibrary(dev, &msl_buf, msl_len, &err_buf);
}

pub export fn doeNativeDeviceCreateComputePipeline(dev_raw: ?*anyopaque, desc: ?*const types.WGPUComputePipelineDescriptor) callconv(.c) ?*anyopaque {
    clear_last_error();
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;
    const sm = cast(DoeShaderModule, d.compute.module) orelse {
        set_last_error_stage_name("native_compile");
        set_last_error_kind("InvalidShaderModule");
        set_last_error("compute pipeline creation failed: shader module is null or invalid");
        std.log.err("doe: createComputePipeline failed: shader module is null or invalid. " ++
            "Ensure createShaderModule succeeded (check stderr for WGSL translation errors).", .{});
        return null;
    };

    if (dev.backend == .vulkan) {
        const result = createComputePipelineVulkan(sm, cast(DoePipelineLayout, d.layout));
        if (result != null) label_store.set(result, d.label.data, d.label.length);
        return result;
    }

    // If override constants are provided, re-translate the WGSL with overrides applied.
    const has_overrides = d.compute.constantCount > 0 and d.compute.constants != null;
    var override_lib: ?*anyopaque = null;
    if (has_overrides) {
        override_lib = recompileWithOverrides(dev, sm, d.compute.constants.?, d.compute.constantCount);
        if (override_lib == null) return null;
    }
    const active_lib = override_lib orelse sm.mtl_library;

    // Map entry point name: WGSL "main" → MSL "main_kernel" (Metal forbids "main").
    const entry: [*:0]const u8 = blk: {
        if (d.compute.entryPoint.data) |ep_data| {
            const ep_slice: [*:0]const u8 = @ptrCast(ep_data);
            if (std.mem.eql(u8, std.mem.span(ep_slice), "main")) break :blk "main_kernel";
            break :blk ep_slice;
        }
        break :blk "main_kernel";
    };

    const func = metal_bridge_library_new_function(active_lib, entry) orelse {
        if (override_lib) |ol| metal_bridge_release(ol);
        set_last_error_stage_name("native_compile");
        set_last_error_kind("EntryPointNotFound");
        set_last_error_fmt("compute pipeline creation failed: entry point '{s}' not found", .{std.mem.span(entry)});
        std.log.err("doe: createComputePipeline failed: entry point '{s}' not found in shader module", .{std.mem.span(entry)});
        return null;
    };
    defer metal_bridge_release(func);

    var err_buf: [ERR_CAP]u8 = undefined;
    const pso = metal_bridge_device_new_compute_pipeline(dev.mtl_device, func, &err_buf, ERR_CAP) orelse {
        if (override_lib) |ol| metal_bridge_release(ol);
        const err_msg = std.mem.sliceTo(&err_buf, 0);
        set_last_error_stage_name("native_compile");
        set_last_error_kind("ComputePipelineCreationFailed");
        if (err_msg.len > 0) {
            set_last_error_fmt("compute pipeline creation failed: {s}", .{err_msg});
            std.log.err("doe: createComputePipeline failed: {s}", .{err_msg});
        } else {
            set_last_error("compute pipeline creation failed: MTLComputePipelineState creation returned null");
            std.log.err("doe: createComputePipeline failed: MTLComputePipelineState creation returned null", .{});
        }
        return null;
    };

    // Override library is no longer needed after PSO creation — release it.
    if (override_lib) |ol| metal_bridge_release(ol);

    const cp = make(DoeComputePipeline) orelse {
        metal_bridge_release(pso);
        return null;
    };
    cp.* = .{ .mtl_pso = pso, .layout = cast(DoePipelineLayout, d.layout) };
    // Transfer workgroup size from shader module for correct Metal dispatch.
    cp.wg_x = sm.wg_x;
    cp.wg_y = sm.wg_y;
    cp.wg_z = sm.wg_z;
    cp.needs_sizes_buf = sm.needs_sizes_buf;
    // Transfer binding metadata from shader module for getBindGroupLayout.
    cp.binding_count = sm.binding_count;
    for (0..sm.binding_count) |i| cp.bindings[i] = sm.bindings[i];
    const result = toOpaque(cp);
    label_store.set(result, d.label.data, d.label.length);
    return result;
}

pub export fn doeNativeComputePipelineRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeComputePipeline, raw)) |p| {
        label_store.remove(raw);
        if (p.mtl_pso) |pso| metal_bridge_release(pso);
        // Free Vulkan SPIR-V words if present (Vulkan path only; no-op on Metal).
        const vk_compute = @import("doe_vulkan_compute_native.zig");
        vk_compute.vulkan_release_compute_pipeline(p);
        alloc.destroy(p);
    }
}
