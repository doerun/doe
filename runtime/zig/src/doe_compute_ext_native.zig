// doe_compute_ext_native.zig — Compute pass and pipeline extensions for Doe native Metal backend.
// Sharded from doe_wgpu_native.zig: compute pass operations, getBindGroupLayout, dispatchIndirect.

const std = @import("std");
const native = @import("doe_wgpu_native.zig");
const compute_bind_groups = @import("doe_compute_bind_groups.zig");
const compute_preconditions = @import("doe_compute_preconditions_native.zig");
const wgsl_compiler = @import("doe_wgsl/mod.zig");
const bridge = @import("backend/metal/metal_bridge_decls.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const metal_bridge_buffer_contents = bridge.metal_bridge_buffer_contents;

const DoeComputePipeline = native.DoeComputePipeline;
const DoeComputePass = native.DoeComputePass;
const DoeBuffer = native.DoeBuffer;
const DoeBindGroup = native.DoeBindGroup;
const DoeBindGroupLayout = native.DoeBindGroupLayout;
const DoeBindGroupLayoutEntry = native.DoeBindGroupLayoutEntry;
const RecordedCmd = native.RecordedCmd;
const MAX_COMPUTE_BIND_GROUPS = compute_bind_groups.MAX_COMPUTE_BIND_GROUPS;
const MAX_FLAT_BIND = compute_bind_groups.MAX_FLAT_BIND;
const MAX_SHADER_BINDINGS = native.MAX_SHADER_BINDINGS;

const RESOURCE_KIND_NONE: u32 = 0;
const RESOURCE_KIND_BUFFER: u32 = 1;
const RESOURCE_KIND_SAMPLER: u32 = 2;
const RESOURCE_KIND_TEXTURE: u32 = 3;
const RESOURCE_KIND_STORAGE_TEXTURE: u32 = 4;

fn validate_dispatch_preconditions(pass: *const DoeComputePass, pip: *const DoeComputePipeline, dispatch: [3]u32) bool {
    compute_preconditions.validate_bind_groups(
        pip.dispatch_preconditions,
        pip.texture_dispatch_preconditions,
        pass.bind_groups[0..],
        dispatch,
        .{ pip.wg_x, pip.wg_y, pip.wg_z },
    ) catch {
        std.log.err("doe_compute_ext_native: dispatch precondition failed for proof-elided shader", .{});
        return false;
    };
    return true;
}

fn read_indirect_dispatch_counts(buffer: *const DoeBuffer, offset: u64) ?[3]u32 {
    const byte_offset: usize = @intCast(offset);
    const counts_bytes = 3 * @sizeOf(u32);
    if (byte_offset + counts_bytes > buffer.size) return null;
    const contents = metal_bridge_buffer_contents(buffer.mtl) orelse return null;
    const base = contents + byte_offset;
    const ints: *align(1) const [3]u32 = @ptrCast(base);
    return ints.*;
}

fn clamped_binding_count(pip: *const DoeComputePipeline) usize {
    const count: usize = @intCast(pip.binding_count);
    if (count <= MAX_SHADER_BINDINGS) return count;
    std.log.err(
        "doe_compute_ext_native: invalid compute pipeline binding_count={} max={} - clamping",
        .{ pip.binding_count, MAX_SHADER_BINDINGS },
    );
    return MAX_SHADER_BINDINGS;
}

fn synthesize_layout_entry(binding: native.BindingInfo) DoeBindGroupLayoutEntry {
    var entry = DoeBindGroupLayoutEntry{
        .binding = binding.binding,
        .resource_kind = RESOURCE_KIND_NONE,
    };
    switch (binding.kind) {
        @intFromEnum(wgsl_compiler.BindingKind.buffer) => {
            entry.resource_kind = RESOURCE_KIND_BUFFER;
        },
        @intFromEnum(wgsl_compiler.BindingKind.sampler) => {
            entry.resource_kind = RESOURCE_KIND_SAMPLER;
        },
        @intFromEnum(wgsl_compiler.BindingKind.texture) => {
            entry.resource_kind = RESOURCE_KIND_TEXTURE;
        },
        @intFromEnum(wgsl_compiler.BindingKind.storage_texture) => {
            entry.resource_kind = RESOURCE_KIND_STORAGE_TEXTURE;
            entry.texture_sample_type = binding.access;
        },
        else => {
            std.log.err(
                "doe_compute_ext_native: invalid binding kind={} for binding={} - leaving layout entry empty",
                .{ binding.kind, binding.binding },
            );
        },
    }
    return entry;
}

fn populateRecordedDispatchBindings(
    bind_groups: []const ?*DoeBindGroup,
    bufs: *[MAX_FLAT_BIND]?*anyopaque,
    buf_sizes: *[MAX_FLAT_BIND]u64,
) u32 {
    return compute_bind_groups.populateFlatBindings(bind_groups, bufs, buf_sizes);
}

// ============================================================
// Compute Pass operations
// ============================================================

pub export fn doeNativeComputePassSetPipeline(pass_raw: ?*anyopaque, pip_raw: ?*anyopaque) callconv(.c) void {
    const pass = cast(DoeComputePass, pass_raw) orelse return;
    pass.pipeline = cast(DoeComputePipeline, pip_raw);
}

pub export fn doeNativeComputePassSetBindGroup(pass_raw: ?*anyopaque, index: u32, bg_raw: ?*anyopaque, dyn_count: usize, dyn_offsets: ?[*]const u32) callconv(.c) void {
    _ = dyn_count;
    _ = dyn_offsets;
    const pass = cast(DoeComputePass, pass_raw) orelse return;
    if (index < MAX_COMPUTE_BIND_GROUPS) pass.bind_groups[index] = cast(DoeBindGroup, bg_raw);
}

pub export fn doeNativeComputePassDispatch(pass_raw: ?*anyopaque, x: u32, y: u32, z: u32) callconv(.c) void {
    const pass = cast(DoeComputePass, pass_raw) orelse return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_compute = @import("doe_vulkan_compute_native.zig");
        vk_compute.vulkan_compute_pass_dispatch(pass, x, y, z);
        return;
    }
    const pip = pass.pipeline orelse return;
    if (!validate_dispatch_preconditions(pass, pip, .{ x, y, z })) return;
    var cmd = RecordedCmd{ .dispatch = .{
        .pso = pip.mtl_pso,
        .needs_sizes_buf = pip.needs_sizes_buf,
        .bufs = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
        .buf_sizes = [_]u64{0} ** MAX_FLAT_BIND,
        .buf_count = 0,
        .x = x,
        .y = y,
        .z = z,
        .wg_x = pip.wg_x,
        .wg_y = pip.wg_y,
        .wg_z = pip.wg_z,
    } };
    cmd.dispatch.buf_count = populateRecordedDispatchBindings(
        pass.bind_groups[0..],
        &cmd.dispatch.bufs,
        &cmd.dispatch.buf_sizes,
    );
    pass.enc.cmds.append(alloc, cmd) catch
        std.debug.panic("doe_compute_ext_native: OOM recording dispatch command", .{});
}

pub export fn doeNativeComputePassEnd(raw: ?*anyopaque) callconv(.c) void {
    _ = raw;
}

// ============================================================
// Debug markers — no-ops in headless runtime; symbols required for API surface completeness.
// ============================================================

pub export fn doeNativeComputePassInsertDebugMarker(
    _: ?*anyopaque,
    _: ?[*]const u8,
    _: usize,
) callconv(.c) void {}

pub export fn doeNativeComputePassPushDebugGroup(
    _: ?*anyopaque,
    _: ?[*]const u8,
    _: usize,
) callconv(.c) void {}

pub export fn doeNativeComputePassPopDebugGroup(
    _: ?*anyopaque,
) callconv(.c) void {}

pub export fn doeNativeComputePassRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeComputePass, raw)) |p| {
        if (!native.object_should_destroy(p)) return;
        native.label_store.remove(raw);
        alloc.destroy(p);
    }
}

// ============================================================
// getBindGroupLayout — returns layout derived from WGSL source metadata.
// ============================================================

pub export fn doeNativeComputePipelineGetBindGroupLayout(pip_raw: ?*anyopaque, group_index: u32) callconv(.c) ?*anyopaque {
    const pip = cast(DoeComputePipeline, pip_raw) orelse return null;
    const binding_count = clamped_binding_count(pip);
    var entry_count: usize = 0;
    for (pip.bindings[0..binding_count]) |b| {
        if (b.group == group_index) entry_count += 1;
    }
    const bgl = make(DoeBindGroupLayout) orelse return null;
    var entries: ?[]DoeBindGroupLayoutEntry = null;
    if (entry_count > 0) {
        entries = alloc.alloc(DoeBindGroupLayoutEntry, entry_count) catch {
            alloc.destroy(bgl);
            return null;
        };
        var write_index: usize = 0;
        for (pip.bindings[0..binding_count]) |binding| {
            if (binding.group != group_index) continue;
            entries.?[write_index] = synthesize_layout_entry(binding);
            write_index += 1;
        }
    }
    bgl.* = .{
        .entry_count = @intCast(entry_count),
        .entries = entries,
    };
    return toOpaque(bgl);
}

// ============================================================
// dispatchWorkgroupsIndirect — indirect dispatch from GPU buffer.
// ============================================================

pub export fn doeNativeComputePassDispatchIndirect(pass_raw: ?*anyopaque, buf_raw: ?*anyopaque, offset: u64) callconv(.c) void {
    const pass = cast(DoeComputePass, pass_raw) orelse return;
    if (pass.enc.dev.backend == .vulkan) {
        const vk_compute = @import("doe_vulkan_compute_native.zig");
        vk_compute.vulkan_compute_pass_dispatch_indirect(pass, buf_raw, offset);
        return;
    }
    const pip = pass.pipeline orelse return;
    const indirect_buf = cast(DoeBuffer, buf_raw) orelse return;
    if (pip.dispatch_preconditions.len > 0) {
        const counts = read_indirect_dispatch_counts(indirect_buf, offset) orelse {
            std.log.err("doe_compute_ext_native: indirect dispatch preconditions require readable counts", .{});
            return;
        };
        if (!validate_dispatch_preconditions(pass, pip, counts)) return;
    }
    var cmd = RecordedCmd{ .dispatch_indirect = .{
        .pso = pip.mtl_pso,
        .needs_sizes_buf = pip.needs_sizes_buf,
        .bufs = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
        .buf_sizes = [_]u64{0} ** MAX_FLAT_BIND,
        .buf_count = 0,
        .indirect_buf = toOpaque(indirect_buf),
        .offset = offset,
        .wg_x = pip.wg_x,
        .wg_y = pip.wg_y,
        .wg_z = pip.wg_z,
    } };
    cmd.dispatch_indirect.buf_count = populateRecordedDispatchBindings(
        pass.bind_groups[0..],
        &cmd.dispatch_indirect.bufs,
        &cmd.dispatch_indirect.buf_sizes,
    );
    pass.enc.cmds.append(alloc, cmd) catch
        std.debug.panic("doe_compute_ext_native: OOM recording indirect dispatch command", .{});
}
