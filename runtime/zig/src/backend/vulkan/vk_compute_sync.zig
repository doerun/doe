const c = @import("vk_constants.zig");
const model_binding_types = @import("../../model_binding_value_types.zig");
const model_compute_types = @import("../../model_compute_types.zig");

pub const MAX_TRACKED_COMPUTE_BINDINGS: usize = c.MAX_DESCRIPTOR_SETS * 16;

pub const ComputeBindingAccess = struct {
    resource_handle: u64 = 0,
    reads: bool = false,
    writes: bool = false,
};

pub fn make_prior_transfer_writes_visible(self: anytype, command_buffer: c.VkCommandBuffer) void {
    if (!self.has_pending_transfer_writes) return;
    const barrier = c.VkMemoryBarrier{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = c.VK_ACCESS_TRANSFER_WRITE_BIT,
        .dstAccessMask = c.VK_ACCESS_SHADER_READ_BIT | c.VK_ACCESS_SHADER_WRITE_BIT,
    };
    c.vkCmdPipelineBarrier(
        command_buffer,
        c.VK_PIPELINE_STAGE_TRANSFER_BIT,
        c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
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

pub fn make_prior_transfer_writes_visible_for_transfer_read(self: anytype, command_buffer: c.VkCommandBuffer) void {
    if (!self.has_pending_transfer_writes) return;
    const barrier = c.VkMemoryBarrier{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = c.VK_ACCESS_TRANSFER_WRITE_BIT,
        .dstAccessMask = c.VK_ACCESS_TRANSFER_READ_BIT,
    };
    c.vkCmdPipelineBarrier(
        command_buffer,
        c.VK_PIPELINE_STAGE_TRANSFER_BIT,
        c.VK_PIPELINE_STAGE_TRANSFER_BIT,
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

pub fn make_prior_compute_writes_visible_for_transfer_read(self: anytype, command_buffer: c.VkCommandBuffer) void {
    const barrier = c.VkMemoryBarrier{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = c.VK_ACCESS_SHADER_WRITE_BIT,
        .dstAccessMask = c.VK_ACCESS_TRANSFER_READ_BIT,
    };
    c.vkCmdPipelineBarrier(
        command_buffer,
        c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        c.VK_PIPELINE_STAGE_TRANSFER_BIT,
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

pub fn make_prior_compute_writes_visible_for_current_bindings(
    self: anytype,
    command_buffer: c.VkCommandBuffer,
) void {
    if (!self.has_pending_compute_writes) return;
    if (!self.current_compute_binding_tracking_complete or self.pending_compute_write_buffers.count() == 0) {
        emit_compute_write_visibility_barrier(self, command_buffer);
        return;
    }

    for (current_compute_bindings(self)) |binding| {
        if (!binding.reads and !binding.writes) continue;
        if (self.pending_compute_write_buffers.contains(binding.resource_handle)) {
            emit_compute_write_visibility_barrier(self, command_buffer);
            return;
        }
    }
}

pub fn remember_current_compute_writes(self: anytype) void {
    if (!self.current_compute_binding_tracking_complete) {
        self.pending_compute_write_buffers.clearRetainingCapacity();
        self.has_pending_compute_writes = true;
        return;
    }

    var recorded_write = false;
    for (current_compute_bindings(self)) |binding| {
        if (!binding.writes) continue;
        recorded_write = true;
        self.pending_compute_write_buffers.put(self.allocator, binding.resource_handle, {}) catch {
            self.pending_compute_write_buffers.clearRetainingCapacity();
            self.has_pending_compute_writes = true;
            return;
        };
    }
    if (recorded_write) self.has_pending_compute_writes = true;
}

pub fn clear_pending_compute_writes(self: anytype) void {
    self.has_pending_compute_writes = false;
    self.pending_compute_write_buffers.clearRetainingCapacity();
}

fn emit_compute_write_visibility_barrier(self: anytype, command_buffer: c.VkCommandBuffer) void {
    const barrier = c.VkMemoryBarrier{
        .sType = c.VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .pNext = null,
        .srcAccessMask = c.VK_ACCESS_SHADER_WRITE_BIT,
        .dstAccessMask = c.VK_ACCESS_SHADER_READ_BIT | c.VK_ACCESS_SHADER_WRITE_BIT,
    };
    c.vkCmdPipelineBarrier(
        command_buffer,
        c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        c.VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
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

fn access_for_buffer_binding(binding: model_compute_types.KernelBinding) ComputeBindingAccess {
    return switch (binding.buffer_type) {
        model_binding_types.WGPUBufferBindingType_Uniform,
        model_binding_types.WGPUBufferBindingType_ReadOnlyStorage,
        => .{ .reads = true },
        model_binding_types.WGPUBufferBindingType_Storage => .{ .reads = true, .writes = true },
        else => .{ .reads = true, .writes = true },
    };
}

fn current_compute_bindings(self: anytype) []const ComputeBindingAccess {
    const count: usize = @intCast(self.current_compute_binding_count);
    return self.current_compute_bindings[0..count];
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
