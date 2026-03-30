// doe_vulkan_compute_native.zig — Vulkan-specific compute operations for the Doe native C ABI.
// Routes shader module creation and compute dispatch through NativeVulkanRuntime when the
// device backend is .vulkan. Commands execute immediately (no deferred batching).

const builtin = @import("builtin");
const has_vulkan = (builtin.os.tag == .linux);
const std = @import("std");
const doe_wgsl = @import("doe_wgsl/mod.zig");
const runtime_compile = @import("doe_wgsl/runtime_compile.zig");
const compute_preconditions = @import("doe_compute_preconditions_native.zig");
const native = @import("doe_wgpu_native.zig");
const model = @import("model.zig");

const alloc = native.alloc;
const cast = native.cast;
const device_vk_runtime = native.device_vk_runtime;
const MAX_COMPUTE_BIND_GROUPS = native.MAX_COMPUTE_BIND_GROUPS;
const MAX_BIND = native.MAX_BIND;

const NativeVulkanRuntime = native.NativeVulkanRuntime;
const DoeShaderModule = native.DoeShaderModule;
const DoeComputePipeline = native.DoeComputePipeline;
const DoeComputePass = native.DoeComputePass;
const DoeBuffer = native.DoeBuffer;

// Maximum KernelBinding slots: groups × bindings per group.
const MAX_KERNEL_BINDINGS: usize = MAX_COMPUTE_BIND_GROUPS * MAX_BIND;

// ============================================================
// Shader module — WGSL → SPIR-V
// ============================================================

/// Translate WGSL source to SPIR-V words and store them in shader.spirv_data.
/// Called from doe_shader_native.zig when dev.backend == .vulkan.
/// Returns error on OOM or compilation failure.
pub fn vulkan_create_shader_module(
    shader: *DoeShaderModule,
    wgsl: []const u8,
) error{ OutOfMemory, ShaderCompileFailed }!void {
    var spirv_buf = alloc.alloc(u8, doe_wgsl.MAX_SPIRV_OUTPUT) catch return error.OutOfMemory;
    defer alloc.free(spirv_buf);

    var translation = runtime_compile.translateToSpirvForComputeRuntime(alloc, wgsl, spirv_buf) catch {
        std.log.err("doe_vulkan_compute: WGSL→SPIR-V translation failed: {s}", .{doe_wgsl.lastErrorMessage()});
        return error.ShaderCompileFailed;
    };
    errdefer translation.info.deinit(alloc);
    shader.needs_sizes_buf = translation.info.needs_sizes_buf;
    shader.dispatch_preconditions = translation.info.dispatch_preconditions;
    shader.texture_dispatch_preconditions = translation.info.texture_dispatch_preconditions;
    translation.info.dispatch_preconditions = &.{};
    translation.info.texture_dispatch_preconditions = &.{};
    shader.wg_x = translation.info.workgroup_size[0];
    shader.wg_y = translation.info.workgroup_size[1];
    shader.wg_z = translation.info.workgroup_size[2];

    if (translation.len == 0 or (translation.len % 4) != 0) {
        std.log.err("doe_vulkan_compute: SPIR-V output length invalid: {}", .{translation.len});
        return error.ShaderCompileFailed;
    }

    const word_count = translation.len / 4;
    const words = alloc.alloc(u32, word_count) catch return error.OutOfMemory;
    errdefer alloc.free(words);

    // Reinterpret byte buffer as u32 words (SPIR-V is little-endian u32 stream).
    for (words, 0..) |*w, i| {
        const offset = i * 4;
        const chunk: *const [4]u8 = @ptrCast(spirv_buf[offset .. offset + 4].ptr);
        w.* = std.mem.readInt(u32, chunk, .little);
    }

    shader.spirv_data = words;
}

// ============================================================
// Compute pipeline — copy SPIR-V from shader to pipeline
// ============================================================

/// Duplicate SPIR-V words from shader into pip.spirv_data.
/// Called from doe_shader_native.zig for the Vulkan compute pipeline creation path.
/// Returns error on OOM.
pub fn vulkan_copy_pipeline_spirv(
    pip: *DoeComputePipeline,
    shader: *const DoeShaderModule,
) error{OutOfMemory}!void {
    const src = shader.spirv_data orelse return;
    pip.spirv_data = alloc.dupe(u32, src) catch return error.OutOfMemory;
}

/// Free pip.spirv_data if heap-allocated. The runtime manages VkPipeline lifecycle.
pub fn vulkan_release_compute_pipeline(pip: *DoeComputePipeline) void {
    if (pip.spirv_data) |s| {
        alloc.free(s);
        pip.spirv_data = null;
    }
}

// ============================================================
// Compute dispatch — immediate execution through NativeVulkanRuntime
// ============================================================

/// Build a KernelBinding slice from the pass bind groups for the given pipeline.
/// Returns the number of bindings populated in out_bindings.
fn collect_bindings(
    pass: *const DoeComputePass,
    out_bindings: []model.KernelBinding,
) usize {
    var count: usize = 0;
    for (pass.bind_groups, 0..) |maybe_bg, group_i| {
        const bg = maybe_bg orelse continue;
        for (0..bg.count) |slot_i| {
            const raw_ptr = bg.buffers[slot_i] orelse continue;
            const buf = cast(DoeBuffer, raw_ptr) orelse continue;
            if (buf.vk_id == 0) continue; // not a Vulkan buffer
            if (count >= out_bindings.len) break;
            out_bindings[count] = .{
                .group = @intCast(group_i),
                .binding = @intCast(slot_i),
                .resource_kind = .buffer,
                .resource_handle = buf.vk_id,
                .buffer_offset = 0,
                .buffer_size = model.WGPUWholeSize,
                .buffer_type = model.WGPUBufferBindingType_Storage,
            };
            count += 1;
        }
    }
    return count;
}

/// Immediate Vulkan compute dispatch via NativeVulkanRuntime.
/// Called from doe_compute_ext_native.zig when pass.enc.dev.backend == .vulkan.
pub fn vulkan_compute_pass_dispatch(pass: *DoeComputePass, x: u32, y: u32, z: u32) void {
    if (comptime !has_vulkan) return;
    if (x == 0 or y == 0 or z == 0) {
        std.log.err("doe_vulkan_compute: dispatch called with zero dimension ({},{},{})", .{ x, y, z });
        return;
    }
    const rt = device_vk_runtime(pass.enc.dev) orelse {
        std.log.err("doe_vulkan_compute: dispatch failed: no VulkanRuntime on device", .{});
        return;
    };
    const pip = pass.pipeline orelse {
        std.log.err("doe_vulkan_compute: dispatch failed: no pipeline set on compute pass", .{});
        return;
    };
    const spirv = pip.spirv_data orelse {
        std.log.err("doe_vulkan_compute: dispatch failed: pipeline has no SPIR-V data", .{});
        return;
    };
    compute_preconditions.validate_bind_groups(
        pip.dispatch_preconditions,
        pip.texture_dispatch_preconditions,
        pass.bind_groups[0..],
        .{ x, y, z },
        .{ pip.wg_x, pip.wg_y, pip.wg_z },
    ) catch {
        std.log.err("doe_vulkan_compute: dispatch precondition failed for proof-elided shader", .{});
        return;
    };

    var binding_storage: [MAX_KERNEL_BINDINGS]model.KernelBinding = undefined;
    const binding_count = collect_bindings(pass, &binding_storage);
    const bindings: ?[]const model.KernelBinding = if (binding_count > 0)
        binding_storage[0..binding_count]
    else
        null;

    rt.set_compute_shader_spirv(spirv, null, bindings, false) catch |err| {
        std.log.err("doe_vulkan_compute: set_compute_shader_spirv failed: {s}", .{@errorName(err)});
        return;
    };

    const webgpu = @import("webgpu_ffi.zig");
    _ = rt.run_dispatch(
        x,
        y,
        z,
        webgpu.QueueSyncMode.per_command,
        webgpu.QueueWaitMode.process_events,
        webgpu.GpuTimestampMode.off,
    ) catch |err| {
        std.log.err("doe_vulkan_compute: run_dispatch({},{},{}) failed: {s}", .{ x, y, z, @errorName(err) });
        return;
    };
}

/// Immediate Vulkan indirect compute dispatch.
/// Falls back to a direct dispatch (1,1,1) when indirect VkBuffer lookup fails.
/// Called from doe_compute_ext_native.zig when pass.enc.dev.backend == .vulkan.
pub fn vulkan_compute_pass_dispatch_indirect(
    pass: *DoeComputePass,
    buf_raw: ?*anyopaque,
    offset: u64,
) void {
    if (comptime !has_vulkan) return;
    const rt = device_vk_runtime(pass.enc.dev) orelse {
        std.log.err("doe_vulkan_compute: dispatch_indirect failed: no VulkanRuntime on device", .{});
        return;
    };
    const pip = pass.pipeline orelse {
        std.log.err("doe_vulkan_compute: dispatch_indirect failed: no pipeline set", .{});
        return;
    };
    const spirv = pip.spirv_data orelse {
        std.log.err("doe_vulkan_compute: dispatch_indirect failed: pipeline has no SPIR-V data", .{});
        return;
    };

    var binding_storage: [MAX_KERNEL_BINDINGS]model.KernelBinding = undefined;
    const binding_count = collect_bindings(pass, &binding_storage);
    const bindings: ?[]const model.KernelBinding = if (binding_count > 0)
        binding_storage[0..binding_count]
    else
        null;

    rt.set_compute_shader_spirv(spirv, null, bindings, false) catch |err| {
        std.log.err("doe_vulkan_compute: dispatch_indirect set_compute_shader_spirv failed: {s}", .{@errorName(err)});
        return;
    };

    // Attempt true indirect dispatch when the indirect buffer is resolvable.
    const indirect_dims = resolve_indirect_dims(rt, buf_raw, offset);
    const x = indirect_dims[0];
    const y = indirect_dims[1];
    const z = indirect_dims[2];
    const dispatch_x: u32 = if (x > 0) x else 1;
    const dispatch_y: u32 = if (y > 0) y else 1;
    const dispatch_z: u32 = if (z > 0) z else 1;
    compute_preconditions.validate_bind_groups(
        pip.dispatch_preconditions,
        pip.texture_dispatch_preconditions,
        pass.bind_groups[0..],
        .{ dispatch_x, dispatch_y, dispatch_z },
        .{ pip.wg_x, pip.wg_y, pip.wg_z },
    ) catch {
        std.log.err("doe_vulkan_compute: indirect dispatch precondition failed for proof-elided shader", .{});
        return;
    };

    const webgpu = @import("webgpu_ffi.zig");
    _ = rt.run_dispatch(
        dispatch_x,
        dispatch_y,
        dispatch_z,
        webgpu.QueueSyncMode.per_command,
        webgpu.QueueWaitMode.process_events,
        webgpu.GpuTimestampMode.off,
    ) catch |err| {
        std.log.err("doe_vulkan_compute: dispatch_indirect run_dispatch failed: {s}", .{@errorName(err)});
    };
}

// ============================================================
// Indirect buffer helpers
// ============================================================

/// Read dispatch dimensions from the mapped Vulkan indirect buffer.
/// Returns [x, y, z] = {0, 0, 0} on any error (callers substitute safe defaults).
fn resolve_indirect_dims(
    rt: *NativeVulkanRuntime,
    buf_raw: ?*anyopaque,
    offset: u64,
) [3]u32 {
    if (comptime !has_vulkan) return .{ 0, 0, 0 };
    const NULL_DIMS = [3]u32{ 0, 0, 0 };
    const buf = cast(DoeBuffer, buf_raw) orelse return NULL_DIMS;
    if (buf.vk_id == 0) return NULL_DIMS;
    const cb = rt.compute_buffers.get(buf.vk_id) orelse return NULL_DIMS;
    const base: [*]const u8 = @ptrCast(cb.mapped orelse return NULL_DIMS);
    // Indirect dispatch buffer layout: uint32 x, uint32 y, uint32 z at `offset`.
    const DISPATCH_STRUCT_SIZE: u64 = 12;
    if (offset + DISPATCH_STRUCT_SIZE > cb.size) return NULL_DIMS;
    const dims_ptr: *const [3]u32 = @ptrCast(@alignCast(base + offset));
    return dims_ptr.*;
}
