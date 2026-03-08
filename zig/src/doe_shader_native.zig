// doe_shader_native.zig — Shader module and compute pipeline creation for Doe native Metal backend.
// Sharded from doe_wgpu_native.zig: WGSL→MSL translation, MTLLibrary/MTLComputePipelineState creation.

const std = @import("std");
const types = @import("wgpu_types.zig");
const wgsl_compiler = @import("doe_wgsl/mod.zig");
const native = @import("doe_wgpu_native.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const ERR_CAP = native.ERR_CAP;

const DoeDevice = native.DoeDevice;
const DoeShaderModule = native.DoeShaderModule;
const DoeComputePipeline = native.DoeComputePipeline;

extern fn metal_bridge_device_new_library_msl(device: ?*anyopaque, src: [*]const u8, src_len: usize, err: ?[*]u8, err_cap: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_library_new_function(library: ?*anyopaque, name: [*:0]const u8) callconv(.c) ?*anyopaque;
extern fn metal_bridge_device_new_compute_pipeline(device: ?*anyopaque, function: ?*anyopaque, err: ?[*]u8, err_cap: usize) callconv(.c) ?*anyopaque;
extern fn metal_bridge_release(obj: ?*anyopaque) callconv(.c) void;

// ============================================================
// Shader Module (WGSL → MSL → MTLLibrary)
// ============================================================

pub export fn doeNativeDeviceCreateShaderModule(dev_raw: ?*anyopaque, desc: ?*const types.WGPUShaderModuleDescriptor) callconv(.c) ?*anyopaque {
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
        std.log.err("doe: createShaderModule failed: WGSL→MSL translation error ({s})", .{@errorName(err)});
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
        if (err_msg.len > 0) {
            std.log.err("doe: createShaderModule failed: MSL compilation error: {s}", .{err_msg});
        } else {
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
    var bind_meta: [native.MAX_SHADER_BINDINGS]wgsl_compiler.BindingMeta = undefined;
    const bind_count = wgsl_compiler.extractBindings(alloc, wgsl, &bind_meta) catch 0;
    for (0..bind_count) |i| {
        sm.bindings[i] = .{ .group = bind_meta[i].group, .binding = bind_meta[i].binding };
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
    const dev = cast(DoeDevice, dev_raw) orelse return null;
    const d = desc orelse return null;
    const sm = cast(DoeShaderModule, d.compute.module) orelse {
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
        std.log.err("doe: createComputePipeline failed: entry point '{s}' not found in shader module", .{std.mem.span(entry)});
        return null;
    };
    defer metal_bridge_release(func);

    var err_buf: [ERR_CAP]u8 = undefined;
    const pso = metal_bridge_device_new_compute_pipeline(dev.mtl_device, func, &err_buf, ERR_CAP) orelse {
        const err_msg = std.mem.sliceTo(&err_buf, 0);
        if (err_msg.len > 0) {
            std.log.err("doe: createComputePipeline failed: {s}", .{err_msg});
        } else {
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
