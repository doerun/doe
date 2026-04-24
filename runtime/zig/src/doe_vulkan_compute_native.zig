// doe_vulkan_compute_native.zig — Vulkan-specific compute operations for the Doe native C ABI.
// Routes shader module creation through NativeVulkanRuntime when the device backend is
// .vulkan. Queue submit replays recorded compute dispatches with Vulkan-native deferred
// submission semantics.

const builtin = @import("builtin");
const has_vulkan = (builtin.os.tag == .linux);
const std = @import("std");
const doe_wgsl = @import("doe_wgsl/mod.zig");
const runtime_compile = @import("doe_wgsl/runtime_compile.zig");
const shader_translation_cache = @import("doe_shader_translation_cache.zig");
const native_types = @import("doe_native_object_types.zig");
const native_shared = @import("doe_native_shared_types.zig");
const native_helpers = @import("doe_native_object_helpers.zig");
const model_compute_types = @import("model_compute_types.zig");
const model_binding_types = @import("model_binding_value_types.zig");
const shader_native = @import("doe_shader_native.zig");
const webgpu = @import("backend/runtime_types.zig");

const alloc = native_helpers.alloc;
const cast = native_helpers.cast;
const MAX_COMPUTE_BIND_GROUPS = native_shared.MAX_COMPUTE_BIND_GROUPS;
const MAX_BIND = native_shared.MAX_BIND;

const NativeVulkanRuntime = native_shared.NativeVulkanRuntime;
const DoeShaderModule = native_types.DoeShaderModule;
const DoeComputePipeline = native_types.DoeComputePipeline;
const DoeBuffer = native_types.DoeBuffer;
// Maximum KernelBinding slots: groups × bindings per group.
const MAX_KERNEL_BINDINGS: usize = MAX_COMPUTE_BIND_GROUPS * MAX_BIND;

const BINDING_KIND_BUFFER: u32 = @intFromEnum(doe_wgsl.BindingKind.buffer);
const ADDRESS_SPACE_STORAGE: u32 = @intFromEnum(doe_wgsl.ir.AddressSpace.storage);
const ADDRESS_SPACE_UNIFORM: u32 = @intFromEnum(doe_wgsl.ir.AddressSpace.uniform);
const ACCESS_READ: u32 = @intFromEnum(doe_wgsl.ir.AccessMode.read);
const ACCESS_READ_WRITE: u32 = @intFromEnum(doe_wgsl.ir.AccessMode.read_write);

fn shader_buffer_binding_type(
    shader_module: ?*DoeShaderModule,
    group: u32,
    binding: u32,
) u32 {
    const sm = shader_module orelse return model_binding_types.WGPUBufferBindingType_Storage;
    shader_native.ensureShaderBindings(sm);
    const binding_count: usize = @min(
        @as(usize, @intCast(sm.binding_count)),
        native_shared.MAX_SHADER_BINDINGS,
    );
    for (sm.bindings[0..binding_count]) |meta| {
        if (meta.group != group or meta.binding != binding) continue;
        if (meta.kind != BINDING_KIND_BUFFER) break;
        if (meta.addr_space == ADDRESS_SPACE_UNIFORM) return model_binding_types.WGPUBufferBindingType_Uniform;
        if (meta.addr_space == ADDRESS_SPACE_STORAGE and
            meta.access == ACCESS_READ) return model_binding_types.WGPUBufferBindingType_ReadOnlyStorage;
        if (meta.addr_space == ADDRESS_SPACE_STORAGE and
            meta.access == ACCESS_READ_WRITE) return model_binding_types.WGPUBufferBindingType_Storage;
        return model_binding_types.WGPUBufferBindingType_Storage;
    }
    return model_binding_types.WGPUBufferBindingType_Storage;
}

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
    var cached_translation = shader_translation_cache.lookupComputeSpirvTranslation(alloc, wgsl);
    defer if (cached_translation) |*cached| cached.deinit(alloc);

    if (cached_translation) |*cached| {
        moveTranslationInfoToShader(shader, &cached.info);
        try assignSpirvWords(shader, cached.spirv);
        return;
    }

    var spirv_buf = alloc.alloc(u8, doe_wgsl.MAX_SPIRV_OUTPUT) catch return error.OutOfMemory;
    defer alloc.free(spirv_buf);

    var translation = runtime_compile.translateToSpirvForComputeRuntime(alloc, wgsl, spirv_buf) catch {
        const head_len: usize = @min(wgsl.len, 120);
        std.log.err(
            "doe_vulkan_compute: WGSL→SPIR-V translation failed: {s} | wgsl[0..{d}]: {s}",
            .{ doe_wgsl.lastErrorMessage(), head_len, wgsl[0..head_len] },
        );
        return error.ShaderCompileFailed;
    };
    errdefer translation.info.deinit(alloc);

    if (translation.len == 0 or (translation.len % 4) != 0) {
        std.log.err("doe_vulkan_compute: SPIR-V output length invalid: {}", .{translation.len});
        return error.ShaderCompileFailed;
    }

    shader_translation_cache.storeComputeSpirvTranslation(
        alloc,
        wgsl,
        spirv_buf[0..translation.len],
        &translation.info,
    );
    moveTranslationInfoToShader(shader, &translation.info);
    try assignSpirvWords(shader, spirv_buf[0..translation.len]);
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
// Compute dispatch — queue submit replay through NativeVulkanRuntime
// ============================================================

/// Build a KernelBinding slice from recorded flat buffer bindings for the given pipeline.
/// Returns the number of bindings populated in out_bindings.
fn collect_recorded_bindings(
    pip: *const DoeComputePipeline,
    bufs: []const ?*anyopaque,
    buf_sizes: []const u64,
    out_bindings: []model_compute_types.KernelBinding,
) usize {
    var count: usize = 0;
    const shader_module = pip.shader_module;
    for (bufs, 0..) |maybe_raw, slot| {
        const raw_ptr = maybe_raw orelse continue;
        const buf = cast(DoeBuffer, raw_ptr) orelse continue;
        if (buf.vk_id == 0) continue;
        if (count >= out_bindings.len) break;
        const group_u32: u32 = @intCast(slot / MAX_BIND);
        const binding_u32: u32 = @intCast(slot % MAX_BIND);
        out_bindings[count] = .{
            .group = group_u32,
            .binding = binding_u32,
            .resource_kind = .buffer,
            .resource_handle = buf.vk_id,
            .buffer_offset = 0,
            .buffer_size = buf_sizes[slot],
            .buffer_type = shader_buffer_binding_type(shader_module, group_u32, binding_u32),
        };
        count += 1;
    }
    return count;
}

/// Replay a recorded compute dispatch through NativeVulkanRuntime at queue-submit time.
pub fn vulkan_prepare_recorded_dispatch(rt: *NativeVulkanRuntime, dispatch: anytype) bool {
    if (comptime !has_vulkan) return false;
    const pip = cast(DoeComputePipeline, dispatch.compute_pipeline) orelse {
        std.log.err("doe_vulkan_compute: recorded dispatch missing compute pipeline", .{});
        return false;
    };
    const spirv = pip.spirv_data orelse {
        std.log.err("doe_vulkan_compute: recorded dispatch missing SPIR-V data", .{});
        return false;
    };

    var binding_storage: [MAX_KERNEL_BINDINGS]model_compute_types.KernelBinding = undefined;
    const binding_count = collect_recorded_bindings(
        pip,
        dispatch.bufs[0..dispatch.buf_count],
        dispatch.buf_sizes[0..dispatch.buf_count],
        &binding_storage,
    );
    const bindings: ?[]const model_compute_types.KernelBinding = if (binding_count > 0)
        binding_storage[0..binding_count]
    else
        null;

    rt.set_compute_shader_spirv(spirv, null, bindings, false) catch |err| {
        std.log.err("doe_vulkan_compute: set_compute_shader_spirv failed: {s}", .{@errorName(err)});
        return false;
    };
    return true;
}

pub fn vulkan_run_prepared_dispatch(rt: *NativeVulkanRuntime, dispatch: anytype) void {
    if (comptime !has_vulkan) return;
    _ = rt.run_dispatch(
        dispatch.x,
        dispatch.y,
        dispatch.z,
        webgpu.QueueSyncMode.deferred,
        webgpu.QueueWaitMode.process_events,
        webgpu.GpuTimestampMode.off,
    ) catch |err| {
        std.log.err("doe_vulkan_compute: recorded run_dispatch({},{},{}) failed: {s}", .{
            dispatch.x,
            dispatch.y,
            dispatch.z,
            @errorName(err),
        });
        return;
    };
}

pub fn vulkan_submit_recorded_dispatch(rt: *NativeVulkanRuntime, dispatch: anytype) void {
    if (!vulkan_prepare_recorded_dispatch(rt, dispatch)) return;
    vulkan_run_prepared_dispatch(rt, dispatch);
}

/// Replay a recorded indirect compute dispatch through NativeVulkanRuntime at queue-submit time.
pub fn vulkan_run_prepared_dispatch_indirect(rt: *NativeVulkanRuntime, dispatch: anytype) void {
    if (comptime !has_vulkan) return;
    const indirect_dims = resolve_indirect_dims(rt, dispatch.indirect_buf, dispatch.offset);
    const x = indirect_dims[0];
    const y = indirect_dims[1];
    const z = indirect_dims[2];
    const dispatch_x: u32 = if (x > 0) x else 1;
    const dispatch_y: u32 = if (y > 0) y else 1;
    const dispatch_z: u32 = if (z > 0) z else 1;
    _ = rt.run_dispatch_indirect(
        dispatch_x,
        dispatch_y,
        dispatch_z,
        webgpu.QueueSyncMode.deferred,
        webgpu.QueueWaitMode.process_events,
    ) catch |err| {
        std.log.err("doe_vulkan_compute: recorded dispatch_indirect failed: {s}", .{@errorName(err)});
    };
}

pub fn vulkan_submit_recorded_dispatch_indirect(rt: *NativeVulkanRuntime, dispatch: anytype) void {
    if (!vulkan_prepare_recorded_dispatch(rt, dispatch)) return;
    vulkan_run_prepared_dispatch_indirect(rt, dispatch);
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

fn moveTranslationInfoToShader(
    shader: *DoeShaderModule,
    info: *runtime_compile.TranslationInfo,
) void {
    shader.needs_sizes_buf = info.needs_sizes_buf;
    shader.dispatch_preconditions = info.dispatch_preconditions;
    shader.texture_dispatch_preconditions = info.texture_dispatch_preconditions;
    shader.wg_x = info.workgroup_size[0];
    shader.wg_y = info.workgroup_size[1];
    shader.wg_z = info.workgroup_size[2];
    info.dispatch_preconditions = &.{};
    info.texture_dispatch_preconditions = &.{};
}

fn assignSpirvWords(
    shader: *DoeShaderModule,
    spirv_bytes: []const u8,
) error{ OutOfMemory, ShaderCompileFailed }!void {
    if (spirv_bytes.len == 0 or (spirv_bytes.len % 4) != 0) {
        return error.ShaderCompileFailed;
    }
    const word_count = spirv_bytes.len / 4;
    const words = alloc.alloc(u32, word_count) catch return error.OutOfMemory;
    errdefer alloc.free(words);
    for (words, 0..) |*word, index| {
        const offset = index * 4;
        const chunk: *const [4]u8 = @ptrCast(spirv_bytes[offset .. offset + 4].ptr);
        word.* = std.mem.readInt(u32, chunk, .little);
    }
    shader.spirv_data = words;
}
