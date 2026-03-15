// doe_compute_ext_native.zig — Compute pass and pipeline extensions for Doe native Metal backend.
// Sharded from doe_wgpu_native.zig: compute pass operations, getBindGroupLayout, dispatchIndirect.

const std = @import("std");
const native = @import("doe_wgpu_native.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const MAX_BIND = native.MAX_BIND;

const DoeComputePipeline = native.DoeComputePipeline;
const DoeComputePass = native.DoeComputePass;
const DoeBuffer = native.DoeBuffer;
const DoeBindGroup = native.DoeBindGroup;
const DoeBindGroupLayout = native.DoeBindGroupLayout;
const RecordedCmd = native.RecordedCmd;
const MAX_COMPUTE_BIND_GROUPS = native.MAX_COMPUTE_BIND_GROUPS;
const MAX_FLAT_BIND = native.MAX_FLAT_BIND;

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
    const pip = pass.pipeline orelse return;
    var cmd = RecordedCmd{ .dispatch = .{ .pso = pip.mtl_pso, .bufs = [_]?*anyopaque{null} ** MAX_FLAT_BIND, .buf_count = 0, .x = x, .y = y, .z = z, .wg_x = pip.wg_x, .wg_y = pip.wg_y, .wg_z = pip.wg_z } };
    var total: u32 = 0;
    for (pass.bind_groups, 0..) |maybe_bg, group_index| {
        const bg = maybe_bg orelse continue;
        for (0..bg.count) |i| {
            const slot = group_index * MAX_BIND + i;
            if (slot < MAX_FLAT_BIND) {
                cmd.dispatch.bufs[slot] = bg.buffers[i];
                if (slot + 1 > total) total = @intCast(slot + 1);
            }
        }
    }
    cmd.dispatch.buf_count = total;
    pass.enc.cmds.append(alloc, cmd) catch
        std.debug.panic("doe_compute_ext_native: OOM recording dispatch command", .{});
}

pub export fn doeNativeComputePassEnd(raw: ?*anyopaque) callconv(.c) void {
    _ = raw;
}

pub export fn doeNativeComputePassRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeComputePass, raw)) |p| alloc.destroy(p);
}

// ============================================================
// getBindGroupLayout — returns layout derived from WGSL source metadata.
// ============================================================

pub export fn doeNativeComputePipelineGetBindGroupLayout(pip_raw: ?*anyopaque, group_index: u32) callconv(.c) ?*anyopaque {
    const pip = cast(DoeComputePipeline, pip_raw) orelse return null;
    var entry_count: u32 = 0;
    for (pip.bindings[0..pip.binding_count]) |b| {
        if (b.group == group_index) entry_count += 1;
    }
    const bgl = make(DoeBindGroupLayout) orelse return null;
    bgl.* = .{ .entry_count = entry_count };
    return toOpaque(bgl);
}

// ============================================================
// dispatchWorkgroupsIndirect — indirect dispatch from GPU buffer.
// ============================================================

pub export fn doeNativeComputePassDispatchIndirect(pass_raw: ?*anyopaque, buf_raw: ?*anyopaque, offset: u64) callconv(.c) void {
    const pass = cast(DoeComputePass, pass_raw) orelse return;
    const pip = pass.pipeline orelse return;
    const indirect_buf = cast(DoeBuffer, buf_raw) orelse return;
    var cmd = RecordedCmd{ .dispatch_indirect = .{
        .pso = pip.mtl_pso,
        .bufs = [_]?*anyopaque{null} ** MAX_FLAT_BIND,
        .buf_count = 0,
        .indirect_buf = toOpaque(indirect_buf),
        .offset = offset,
        .wg_x = pip.wg_x,
        .wg_y = pip.wg_y,
        .wg_z = pip.wg_z,
    } };
    var total: u32 = 0;
    for (pass.bind_groups, 0..) |maybe_bg, group_index| {
        const bg = maybe_bg orelse continue;
        for (0..bg.count) |i| {
            const slot = group_index * MAX_BIND + i;
            if (slot < MAX_FLAT_BIND) {
                cmd.dispatch_indirect.bufs[slot] = bg.buffers[i];
                if (slot + 1 > total) total = @intCast(slot + 1);
            }
        }
    }
    cmd.dispatch_indirect.buf_count = total;
    pass.enc.cmds.append(alloc, cmd) catch
        std.debug.panic("doe_compute_ext_native: OOM recording indirect dispatch command", .{});
}
