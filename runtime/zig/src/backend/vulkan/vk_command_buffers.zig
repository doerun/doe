const std = @import("std");

const c = @import("vk_constants.zig");
const vk_pipeline = @import("vk_pipeline.zig");
const vk_resources = @import("vk_resources.zig");

const DISPATCH_INDIRECT_ARGS_BYTES = @sizeOf([3]u32);

pub fn ensure_dispatch_indirect_args_buffer(self: anytype) !vk_resources.ComputeBuffer {
    if (self.dispatch_indirect_args_buffer == null) {
        self.dispatch_indirect_args_buffer = try vk_resources.create_host_visible_buffer(
            self,
            DISPATCH_INDIRECT_ARGS_BYTES,
            c.VK_BUFFER_USAGE_INDIRECT_BUFFER_BIT,
        );
    }
    return self.dispatch_indirect_args_buffer.?;
}

pub fn write_dispatch_indirect_args(buffer: vk_resources.ComputeBuffer, x: u32, y: u32, z: u32) !void {
    if (buffer.size < DISPATCH_INDIRECT_ARGS_BYTES) return error.InvalidArgument;
    const mapped = buffer.mapped orelse return error.InvalidState;
    const dispatch_args = [3]u32{ x, y, z };
    const dispatch_arg_bytes = std.mem.asBytes(&dispatch_args);
    @memcpy(@as([*]u8, @ptrCast(mapped))[0..dispatch_arg_bytes.len], dispatch_arg_bytes);
}

pub fn begin_recorded_submit_replay(self: anytype) !c.VkCommandBuffer {
    if (self.replay_recording_active) return self.replay_command_buffer;
    const command_buffer = try acquire_deferred_command_buffer(self);
    var begin_info = c.VkCommandBufferBeginInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .pNext = null,
        .flags = c.VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
        .pInheritanceInfo = null,
    };
    try c.check_vk(c.vkBeginCommandBuffer(command_buffer, &begin_info));
    vk_pipeline.reset_bound_compute_state(self);
    self.replay_command_buffer = command_buffer;
    self.replay_recording_active = true;
    self.has_deferred_submissions = true;
    return command_buffer;
}

pub fn acquire_deferred_command_buffer(self: anytype) !c.VkCommandBuffer {
    if (self.deferred_command_buffer_index < self.deferred_command_buffers.items.len) {
        const command_buffer = self.deferred_command_buffers.items[self.deferred_command_buffer_index];
        self.deferred_command_buffer_index += 1;
        return command_buffer;
    }

    try self.deferred_command_buffers.ensureUnusedCapacity(self.allocator, 1);
    var command_buffer: c.VkCommandBuffer = null;
    var alloc_info = c.VkCommandBufferAllocateInfo{
        .sType = c.VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .pNext = null,
        .commandPool = self.command_pool,
        .level = c.VK_COMMAND_BUFFER_LEVEL_PRIMARY,
        .commandBufferCount = 1,
    };
    try c.check_vk(c.vkAllocateCommandBuffers(self.device, &alloc_info, @ptrCast(&command_buffer)));
    self.deferred_command_buffers.appendAssumeCapacity(command_buffer);
    self.deferred_command_buffer_index += 1;
    return command_buffer;
}

test "Vulkan indirect arguments reject short capacity without changing bytes" {
    var bytes: [16]u8 = @splat(0xcc);
    var buffer = vk_resources.ComputeBuffer{ .buffer = 0, .memory = 0, .mapped = &bytes, .size = 11, .memory_kind = .host_visible };
    try std.testing.expectError(error.InvalidArgument, write_dispatch_indirect_args(buffer, 1, 2, 3));
    try std.testing.expectEqualSlices(u8, &(@as([16]u8, @splat(0xcc))), &bytes);
    buffer.size = 12;
    try write_dispatch_indirect_args(buffer, 1, 2, 3);
    const expected = [_]u32{ 1, 2, 3 };
    try std.testing.expectEqualSlices(u8, std.mem.sliceAsBytes(&expected), bytes[0..12]);
    try std.testing.expectEqualSlices(u8, &.{ 0xcc, 0xcc, 0xcc, 0xcc }, bytes[12..]);
}

test "Vulkan command buffer owner reserves before native allocation" {
    var failing = std.testing.FailingAllocator.init(std.testing.allocator, .{ .fail_index = 0 });
    var owner = struct {
        allocator: std.mem.Allocator,
        device: c.VkDevice = null,
        command_pool: c.VkCommandPool = 0,
        deferred_command_buffers: std.ArrayListUnmanaged(c.VkCommandBuffer) = .{},
        deferred_command_buffer_index: usize = 0,
    }{ .allocator = failing.allocator() };
    defer owner.deferred_command_buffers.deinit(owner.allocator);
    // A native allocation with these null handles would be invalid. Host OOM
    // must return before acquiring an untrackable command buffer.
    try std.testing.expectError(error.OutOfMemory, acquire_deferred_command_buffer(&owner));
    try std.testing.expectEqual(@as(usize, 0), owner.deferred_command_buffers.items.len);
    try std.testing.expectEqual(@as(usize, 0), owner.deferred_command_buffer_index);
}
