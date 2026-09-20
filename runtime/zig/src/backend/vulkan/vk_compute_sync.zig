const std = @import("std");
const c = @import("vk_constants.zig");
const model_binding_types = @import("../../contracts/model/model_binding_value_types.zig");
const model_compute_types = @import("../../contracts/model/model_compute_types.zig");

pub const MAX_TRACKED_COMPUTE_BINDINGS: usize = c.MAX_DESCRIPTOR_SETS * 16;

pub const ComputeBindingAccess = struct {
    resource_handle: u64 = 0,
    reads: bool = false,
    writes: bool = false,
};

pub fn make_prior_transfer_writes_visible(self: anytype, command_buffer: c.VkCommandBuffer) void {
    make_prior_transfer_writes_visible_for_indirect_dispatch(self, command_buffer);
}

pub fn make_prior_transfer_writes_visible_for_indirect_dispatch(self: anytype, command_buffer: c.VkCommandBuffer) void {
    if (!self.has_pending_transfer_writes) return;
    const barrier = c.VkMemoryBarrier{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = c.VK_ACCESS_TRANSFER_WRITE_BIT,
        .dstAccessMask = c.VK_ACCESS_INDIRECT_COMMAND_READ_BIT |
            c.VK_ACCESS_SHADER_READ_BIT |
            c.VK_ACCESS_SHADER_WRITE_BIT,
    };
    c.vkCmdPipelineBarrier(
        command_buffer,
        c.VK_PIPELINE_STAGE_TRANSFER_BIT,
        c.VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT | c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        0,
        1,
        @ptrCast(&barrier),
        0,
        null,
        0,
        null,
    );
    self.has_pending_transfer_writes = false;
}

pub fn make_prior_compute_writes_visible(self: anytype, command_buffer: c.VkCommandBuffer) void {
    if (!self.has_pending_compute_writes) return;
    emit_compute_write_visibility_barrier(self, command_buffer);
}

pub fn make_prior_compute_writes_visible_for_indirect_read(
    self: anytype,
    command_buffer: c.VkCommandBuffer,
    resource_handle: u64,
    buffer: c.VkBuffer,
) void {
    make_indirect_writes_visible(self, command_buffer, resource_handle, buffer, c);
}

fn make_indirect_writes_visible(self: anytype, command_buffer: c.VkCommandBuffer, resource_handle: u64, buffer: c.VkBuffer, comptime native: type) void {
    if (!self.has_pending_compute_writes) return;
    if (!self.pending_compute_write_tracking_complete or self.pending_compute_write_buffer_count == 0) {
        const barrier = c.VkMemoryBarrier{
            .sType = c.VK_STRUCTURE_TYPE_MEMORY_BARRIER,
            .pNext = null,
            .srcAccessMask = c.VK_ACCESS_SHADER_WRITE_BIT,
            .dstAccessMask = c.VK_ACCESS_INDIRECT_COMMAND_READ_BIT,
        };
        native.vkCmdPipelineBarrier(
            command_buffer,
            c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
            c.VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT,
            0,
            1,
            @ptrCast(&barrier),
            0,
            null,
            0,
            null,
        );
        // Indirect visibility does not discharge later shader reads or writes.
        return;
    }
    if (!pending_compute_write_buffer_contains(self, resource_handle)) return;
    var barrier = buffer_memory_barrier(buffer, c.VK_ACCESS_INDIRECT_COMMAND_READ_BIT);
    native.vkCmdPipelineBarrier(
        command_buffer,
        c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        c.VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT,
        0,
        0,
        null,
        1,
        @ptrCast(&barrier),
        0,
        null,
    );
    // Preserve the shader hazard until a barrier covers compute accesses too.
}

pub fn make_transfer_writes_visible_for_host_read(command_buffer: c.VkCommandBuffer) void {
    const barrier = c.VkMemoryBarrier{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = c.VK_ACCESS_TRANSFER_WRITE_BIT,
        .dstAccessMask = c.VK_ACCESS_HOST_READ_BIT,
    };
    c.vkCmdPipelineBarrier(
        command_buffer,
        c.VK_PIPELINE_STAGE_TRANSFER_BIT,
        c.VK_PIPELINE_STAGE_HOST_BIT,
        0,
        1,
        @ptrCast(&barrier),
        0,
        null,
        0,
        null,
    );
}

pub fn capture_current_compute_bindings(
    self: anytype,
    bindings: ?[]const model_compute_types.KernelBinding,
) void {
    self.current_compute_binding_count = 0;
    self.current_compute_binding_tracking_complete = true;
    const bs = bindings orelse return;

    for (bs) |binding| {
        if (binding.resource_kind == .storage_texture) {
            if (storage_texture_binding_writes(binding)) {
                // Buffer handles can be tracked precisely across dispatches.
                // Storage images need an image-aware tracker; until that exists,
                // force the next dependent dispatch through the global compute
                // visibility barrier rather than silently dropping the hazard.
                self.current_compute_binding_tracking_complete = false;
            }
            continue;
        }
        if (binding.resource_kind != .buffer or binding.resource_handle == 0) continue;
        const access = access_for_buffer_binding(binding);
        if (!access.reads and !access.writes) continue;
        if (merge_current_binding_access(self, binding.resource_handle, access)) continue;

        const index: usize = @intCast(self.current_compute_binding_count);
        if (index >= MAX_TRACKED_COMPUTE_BINDINGS) {
            self.current_compute_binding_tracking_complete = false;
            return;
        }
        self.current_compute_bindings[index] = .{
            .resource_handle = binding.resource_handle,
            .reads = access.reads,
            .writes = access.writes,
        };
        self.current_compute_binding_count += 1;
    }
}

pub fn make_prior_compute_writes_visible_for_current_bindings(self: anytype, command_buffer: c.VkCommandBuffer) void {
    if (current_bindings_need_visibility(self)) emit_compute_write_visibility_barrier(self, command_buffer);
}

fn current_bindings_need_visibility(self: anytype) bool {
    if (!self.has_pending_compute_writes) return false;
    if (!self.current_compute_binding_tracking_complete or !self.pending_compute_write_tracking_complete or self.pending_compute_write_buffer_count == 0) return true;
    for (current_compute_bindings(self)) |binding| {
        if ((binding.reads or binding.writes) and pending_compute_write_buffer_contains(self, binding.resource_handle)) return true;
    }
    return false;
}

pub fn make_replay_compute_writes_visible(self: anytype, command_buffer: c.VkCommandBuffer) void {
    // Replay submissions can outlive the WebGPU resources tracked above. A later
    // resource may reuse the same Vulkan allocation under a different handle, so
    // handle-intersection alone cannot prove that the memory is independent.
    emit_compute_write_visibility_barrier(self, command_buffer);
}

pub fn remember_current_compute_writes(self: anytype) void {
    if (!self.current_compute_binding_tracking_complete) {
        clear_pending_compute_write_buffers(self);
        self.pending_compute_write_tracking_complete = false;
        self.has_pending_compute_writes = true;
        return;
    }

    var recorded_write = false;
    for (current_compute_bindings(self)) |binding| {
        if (!binding.writes) continue;
        recorded_write = true;
        add_pending_compute_write_buffer(self, binding.resource_handle) catch {
            clear_pending_compute_write_buffers(self);
            self.pending_compute_write_tracking_complete = false;
            self.has_pending_compute_writes = true;
            return;
        };
    }
    if (recorded_write) self.has_pending_compute_writes = true;
}

pub fn clear_pending_compute_writes(self: anytype) void {
    self.has_pending_compute_writes = false;
    self.pending_compute_write_tracking_complete = true;
    clear_pending_compute_write_buffers(self);
}

fn emit_compute_write_visibility_barrier(self: anytype, command_buffer: c.VkCommandBuffer) void {
    const barrier = c.VkMemoryBarrier{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = c.VK_ACCESS_SHADER_WRITE_BIT,
        .dstAccessMask = c.VK_ACCESS_SHADER_READ_BIT | c.VK_ACCESS_SHADER_WRITE_BIT | c.VK_ACCESS_INDIRECT_COMMAND_READ_BIT,
    };
    c.vkCmdPipelineBarrier(
        command_buffer,
        c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT | c.VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT,
        0,
        1,
        @ptrCast(&barrier),
        0,
        null,
        0,
        null,
    );
    clear_pending_compute_writes(self);
}

fn buffer_memory_barrier(buffer: c.VkBuffer, dst_access_mask: u32) c.VkBufferMemoryBarrier {
    return .{
        .sType = c.VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = c.VK_ACCESS_SHADER_WRITE_BIT,
        .dstAccessMask = dst_access_mask,
        .srcQueueFamilyIndex = c.VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = c.VK_QUEUE_FAMILY_IGNORED,
        .buffer = buffer,
        .offset = 0,
        .size = c.VK_WHOLE_SIZE,
    };
}

fn access_for_buffer_binding(binding: model_compute_types.KernelBinding) ComputeBindingAccess {
    return switch (binding.buffer_type) {
        model_binding_types.WGPUBufferBindingType_Uniform,
        model_binding_types.WGPUBufferBindingType_ReadOnlyStorage,
        => .{ .reads = true },
        model_binding_types.WGPUBufferBindingType_Storage => .{ .reads = true, .writes = true },
        else => .{ .reads = true, .writes = true },
    };
}

fn storage_texture_binding_writes(binding: model_compute_types.KernelBinding) bool {
    return switch (binding.storage_texture_access) {
        model_binding_types.WGPUStorageTextureAccess_ReadOnly => false,
        model_binding_types.WGPUStorageTextureAccess_Undefined,
        model_binding_types.WGPUStorageTextureAccess_WriteOnly,
        model_binding_types.WGPUStorageTextureAccess_ReadWrite,
        => true,
        else => true,
    };
}

fn current_compute_bindings(self: anytype) []const ComputeBindingAccess {
    const count: usize = @intCast(self.current_compute_binding_count);
    return self.current_compute_bindings[0..count];
}

pub fn pending_compute_write_buffer_contains(self: anytype, resource_handle: u64) bool {
    if (resource_handle == 0) return false;
    if (!self.pending_compute_write_tracking_complete) return true;
    for (self.pending_compute_write_buffer_handles[0..@intCast(self.pending_compute_write_buffer_count)]) |handle| {
        if (handle == resource_handle) return true;
    }
    return false;
}

fn add_pending_compute_write_buffer(self: anytype, resource_handle: u64) !void {
    if (resource_handle == 0 or pending_compute_write_buffer_contains(self, resource_handle)) return;
    const index: usize = @intCast(self.pending_compute_write_buffer_count);
    if (index >= MAX_TRACKED_COMPUTE_BINDINGS) return error.Overflow;
    self.pending_compute_write_buffer_handles[index] = resource_handle;
    self.pending_compute_write_buffer_count += 1;
}

fn clear_pending_compute_write_buffers(self: anytype) void {
    const count: usize = @intCast(self.pending_compute_write_buffer_count);
    @memset(self.pending_compute_write_buffer_handles[0..count], 0);
    self.pending_compute_write_buffer_count = 0;
}

fn merge_current_binding_access(self: anytype, resource_handle: u64, access: ComputeBindingAccess) bool {
    for (self.current_compute_bindings[0..@intCast(self.current_compute_binding_count)]) |*binding| {
        if (binding.resource_handle != resource_handle) continue;
        binding.reads = binding.reads or access.reads;
        binding.writes = binding.writes or access.writes;
        return true;
    }
    return false;
}

test "storage texture write access requires conservative compute synchronization" {
    const base = model_compute_types.KernelBinding{
        .binding = 0,
        .resource_kind = .storage_texture,
        .resource_handle = 7,
    };
    var read_only = base;
    read_only.storage_texture_access = model_binding_types.WGPUStorageTextureAccess_ReadOnly;
    var write_only = base;
    write_only.storage_texture_access = model_binding_types.WGPUStorageTextureAccess_WriteOnly;
    var read_write = base;
    read_write.storage_texture_access = model_binding_types.WGPUStorageTextureAccess_ReadWrite;

    try std.testing.expect(!storage_texture_binding_writes(read_only));
    try std.testing.expect(storage_texture_binding_writes(write_only));
    try std.testing.expect(storage_texture_binding_writes(read_write));
    try std.testing.expect(storage_texture_binding_writes(base));
}

const VisibilityProbe = struct {
    var barriers: usize = 0;
    fn vkCmdPipelineBarrier(_: c.VkCommandBuffer, _: u32, destination: u32, _: u32, memory_count: u32, memory: ?*const anyopaque, buffer_count: u32, buffers: ?*const anyopaque, _: u32, _: ?[*]const c.VkImageMemoryBarrier) void {
        std.testing.expectEqual(c.VK_PIPELINE_STAGE_DRAW_INDIRECT_BIT, destination) catch @panic("wrong indirect stage");
        const access = if (memory_count != 0)
            @as(*const c.VkMemoryBarrier, @ptrCast(@alignCast(memory.?))).dstAccessMask
        else access: {
            std.testing.expectEqual(@as(u32, 1), buffer_count) catch @panic("missing buffer barrier");
            break :access @as(*const c.VkBufferMemoryBarrier, @ptrCast(@alignCast(buffers.?))).dstAccessMask;
        };
        std.testing.expectEqual(c.VK_ACCESS_INDIRECT_COMMAND_READ_BIT, access) catch @panic("wrong indirect access");
        barriers += 1;
    }
};

test "Vulkan indirect visibility retains hazards for later shader consumers" {
    const Tracker = struct {
        has_pending_compute_writes: bool = true,
        pending_compute_write_tracking_complete: bool = true,
        pending_compute_write_buffer_count: u32 = 1,
        pending_compute_write_buffer_handles: [MAX_TRACKED_COMPUTE_BINDINGS]u64 = @splat(0),
        current_compute_binding_tracking_complete: bool = true,
        current_compute_binding_count: u32 = 1,
        current_compute_bindings: [MAX_TRACKED_COMPUTE_BINDINGS]ComputeBindingAccess = @splat(.{}),
    };
    VisibilityProbe.barriers = 0;
    for ([_]bool{ true, false }) |complete| {
        var tracker = Tracker{ .pending_compute_write_tracking_complete = complete };
        tracker.pending_compute_write_buffer_handles[0] = 7;
        tracker.current_compute_bindings[0] = .{ .resource_handle = 7, .reads = true };
        make_indirect_writes_visible(&tracker, null, 7, 9, VisibilityProbe);
        try std.testing.expect(tracker.has_pending_compute_writes);
        try std.testing.expectEqual(@as(u32, 1), tracker.pending_compute_write_buffer_count);
        try std.testing.expect(current_bindings_need_visibility(&tracker));
    }
    try std.testing.expectEqual(@as(usize, 2), VisibilityProbe.barriers);
    var tracker = Tracker{};
    tracker.pending_compute_write_buffer_handles[0] = 7;
    tracker.current_compute_bindings[0] = .{ .resource_handle = 8, .reads = true };
    try std.testing.expect(!current_bindings_need_visibility(&tracker));
    tracker.current_compute_binding_tracking_complete = false;
    try std.testing.expect(current_bindings_need_visibility(&tracker));
}
