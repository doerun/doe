// doe_shader_native.zig — Shader module and compute pipeline creation for Doe native Metal backend.
// Sharded from doe_wgpu_native.zig: WGSL→MSL translation, MTLLibrary/MTLComputePipelineState creation.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const wgsl_compiler = @import("doe_wgsl/mod.zig");
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

const DoeDevice = native.DoeDevice;
const DoeShaderModule = native.DoeShaderModule;
const DoeComputePipeline = native.DoeComputePipeline;
const LAST_ERROR_CAP: usize = 512;
const LAST_ERROR_META_CAP: usize = 64;
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
// Shader Module (WGSL → MSL → MTLLibrary)
// ============================================================

pub export fn doeNativeDeviceCreateShaderModule(dev_raw: ?*anyopaque, desc: ?*const types.WGPUShaderModuleDescriptor) callconv(.c) ?*anyopaque {
    clear_last_error();
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;

    // The WGSL source is in the chained struct (WGPUShaderSourceWGSL).
    const chain = d.nextInChain orelse return null;
    const wgsl_chain: *const types.WGPUShaderSourceWGSL = @ptrCast(@alignCast(chain));
    const wgsl_data = wgsl_chain.code.data orelse return null;
    const wgsl_len = if (wgsl_chain.code.length == types.WGPU_STRLEN)
        std.mem.len(@as([*:0]const u8, @ptrCast(wgsl_data)))
    else
        wgsl_chain.code.length;
    const wgsl = wgsl_data[0..wgsl_len];

    // Translate WGSL → MSL for Metal shader module creation.
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
    const lib = metal_bridge_device_new_library_msl(
        dev.mtl_device,
        &msl_buf,
        msl_len,
        &err_buf,
        ERR_CAP,
    ) orelse {
        const err_msg = std.mem.sliceTo(&err_buf, 0);
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

    const sm = make(DoeShaderModule) orelse {
        metal_bridge_release(lib);
        return null;
    };
    sm.* = .{ .mtl_library = lib };
    // Extract workgroup size from WGSL for correct Metal threadgroup dispatch.
    const wg = native.extractWorkgroupSize(wgsl);
    sm.wg_x = wg.x;
    sm.wg_y = wg.y;
    sm.wg_z = wg.z;
    // Extract binding metadata from WGSL for getBindGroupLayout support.
    // Failure here is non-fatal: the shader compiled successfully, so we proceed with
    // zero bindings as degraded behavior and record the error for caller inspection.
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

pub export fn doeNativeShaderModuleRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeShaderModule, raw)) |sm| {
        if (sm.mtl_library) |l| metal_bridge_release(l);
        alloc.destroy(sm);
    }
}

// ============================================================
// Compute Pipeline
// ============================================================

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

    // Map entry point name: WGSL "main" → MSL "main_kernel" (Metal forbids "main").
    const entry: [*:0]const u8 = blk: {
        if (d.compute.entryPoint.data) |ep_data| {
            const ep_slice: [*:0]const u8 = @ptrCast(ep_data);
            if (std.mem.eql(u8, std.mem.span(ep_slice), "main")) break :blk "main_kernel";
            break :blk ep_slice;
        }
        break :blk "main_kernel";
    };

    const func = metal_bridge_library_new_function(sm.mtl_library, entry) orelse {
        set_last_error_stage_name("native_compile");
        set_last_error_kind("EntryPointNotFound");
        set_last_error_fmt("compute pipeline creation failed: entry point '{s}' not found", .{std.mem.span(entry)});
        std.log.err("doe: createComputePipeline failed: entry point '{s}' not found in shader module", .{std.mem.span(entry)});
        return null;
    };
    defer metal_bridge_release(func);

    var err_buf: [ERR_CAP]u8 = undefined;
    const pso = metal_bridge_device_new_compute_pipeline(dev.mtl_device, func, &err_buf, ERR_CAP) orelse {
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

    const cp = make(DoeComputePipeline) orelse {
        metal_bridge_release(pso);
        return null;
    };
    cp.* = .{ .mtl_pso = pso };
    // Transfer workgroup size from shader module for correct Metal dispatch.
    cp.wg_x = sm.wg_x;
    cp.wg_y = sm.wg_y;
    cp.wg_z = sm.wg_z;
    // Transfer binding metadata from shader module for getBindGroupLayout.
    cp.binding_count = sm.binding_count;
    for (0..sm.binding_count) |i| cp.bindings[i] = sm.bindings[i];
    return toOpaque(cp);
}

pub export fn doeNativeComputePipelineRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeComputePipeline, raw)) |p| {
        if (p.mtl_pso) |pso| metal_bridge_release(pso);
        alloc.destroy(p);
    }
}
