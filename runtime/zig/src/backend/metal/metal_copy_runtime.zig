const std = @import("std");
const model = @import("../../contracts/model/model_resource_types.zig");
const values = @import("../../contracts/model/model_texture_value_types.zig");
const contract = @import("../../contracts/texture_copy.zig");
const webgpu = @import("../../contracts/runtime_types.zig");
const common_timing = @import("../common/timing.zig");
const resources = @import("metal_runtime_resources.zig");
const textures = @import("metal_texture_resources.zig");
const bridge = @import("metal_bridge_decls.zig");

pub const CopyMetrics = struct {
    setup_ns: u64,
    encode_ns: u64,
    submit_wait_ns: u64,
    gpu_elapsed_ns: u64 = 0,
    gpu_timestamps_attempted: bool = false,
    gpu_timestamps_valid: bool = false,
};

const Plan = struct {
    source: ?textures.Descriptor = null,
    destination: ?textures.Descriptor = null,
    source_buffer_size: ?u64 = null,
    destination_buffer_size: ?u64 = null,
    copy: ?contract.Copy = null,
    layout: ?contract.Region = null,
    staging_size: u64 = 0,

    fn init(map: *const textures.Map, cmd: model.CopyCommand) !Plan {
        var plan = Plan{};
        const source_is_buffer = cmd.direction == .buffer_to_buffer or cmd.direction == .buffer_to_texture;
        const destination_is_buffer = cmd.direction == .buffer_to_buffer or cmd.direction == .texture_to_buffer;
        if (cmd.src.kind != (if (source_is_buffer) model.CopyResourceKind.buffer else .texture) or cmd.dst.kind != (if (destination_is_buffer) model.CopyResourceKind.buffer else .texture)) return error.InvalidArgument;
        if (source_is_buffer) plan.source_buffer_size = try requiredBufferSize(cmd.bytes, cmd.src.offset) else plan.source = try textures.admit(map, cmd.src, values.WGPUTextureUsage_CopySrc);
        if (destination_is_buffer) plan.destination_buffer_size = try requiredBufferSize(cmd.bytes, cmd.dst.offset) else plan.destination = try textures.admit(map, cmd.dst, values.WGPUTextureUsage_CopyDst);
        switch (cmd.direction) {
            .buffer_to_buffer => {
                if (cmd.src.handle == cmd.dst.handle) return error.InvalidArgument;
                if (cmd.uses_temporary_buffer) return error.UnsupportedFeature;
            },
            .buffer_to_texture, .texture_to_buffer => {
                if (cmd.uses_temporary_buffer) return error.UnsupportedFeature;
                const upload = cmd.direction == .buffer_to_texture;
                const texture = if (upload) plan.destination.? else plan.source.?;
                const buffer = if (upload) cmd.src else cmd.dst;
                var region = texture.region(if (upload) cmd.dst else cmd.src);
                region.offset = buffer.offset;
                region.bytes_per_row = buffer.bytes_per_row;
                region.rows_per_image = buffer.rows_per_image;
                plan.layout = try contract.validate(if (upload) plan.source_buffer_size.? else plan.destination_buffer_size.?, texture.texture, region, if (upload) .buffer_to_texture else .texture_to_buffer, .native);
                plan.copy = region;
            },
            .texture_to_texture => {
                if (cmd.src.handle == cmd.dst.handle and cmd.src.mip_level == cmd.dst.mip_level) return error.InvalidArgument;
                if (plan.source.?.texture.format != plan.destination.?.texture.format) return error.InvalidArgument;
                var source = plan.source.?.region(cmd.src);
                var destination = plan.destination.?.region(cmd.dst);
                if (source.width != destination.width or source.height != destination.height or source.depth_or_layers != destination.depth_or_layers) return error.TextureCopyRange;
                try contract.validateTextureToTexture(plan.source.?.texture, source, plan.destination.?.texture, destination);
                source.offset = 0;
                destination.offset = 0;
                plan.copy = source;
                if (cmd.uses_temporary_buffer) {
                    plan.layout = try contract.validate(std.math.maxInt(u64), plan.source.?.texture, source, .texture_to_buffer, .native);
                    destination.bytes_per_row = plan.layout.?.pitch;
                    destination.rows_per_image = plan.layout.?.image_rows;
                    _ = try contract.validate(std.math.maxInt(u64), plan.destination.?.texture, destination, .buffer_to_texture, .native);
                    const required = @max(plan.layout.?.required_bytes, cmd.bytes);
                    const alignment: u64 = @max(cmd.temporary_buffer_alignment, 1);
                    const padded = std.math.add(u64, required, alignment - 1) catch return error.TextureCopyRange;
                    plan.staging_size = padded / alignment * alignment;
                }
            },
        }
        return plan;
    }
};

pub fn execute_copy(self: anytype, cmd: model.CopyCommand, queue_sync_mode: webgpu.QueueSyncMode) !CopyMetrics {
    const setup_start = common_timing.now_ns();
    const plan = try Plan.init(&self.textures, cmd);
    // Check both existing buffers before allocation or any encoder transition.
    if (plan.source_buffer_size) |size| try validateExistingBuffer(self, cmd.src.handle, size);
    if (plan.destination_buffer_size) |size| try validateExistingBuffer(self, cmd.dst.handle, size);
    const source_buffer = if (plan.source_buffer_size) |size| try resources.ensure_compute_buffer(self, cmd.src.handle, size, false) else null;
    const destination_buffer = if (plan.destination_buffer_size) |size| try resources.ensure_compute_buffer(self, cmd.dst.handle, size, false) else null;
    const source_texture = if (plan.source) |descriptor| try textures.ensure(&self.textures, self.allocator, self.device, cmd.src.handle, descriptor) else null;
    const destination_texture = if (plan.destination) |descriptor| try textures.ensure(&self.textures, self.allocator, self.device, cmd.dst.handle, descriptor) else null;
    var staging_buffer: ?*anyopaque = null;
    if (plan.staging_size != 0) {
        try self.deferred_releases.ensureUnusedCapacity(self.allocator, 1);
        staging_buffer = bridge.metal_bridge_device_new_buffer_shared(self.device, plan.staging_size) orelse return error.InvalidState;
    }
    errdefer if (staging_buffer) |buffer| bridge.metal_bridge_release(buffer);
    try ensure_blit_encoder(self);
    // Once encoding starts, retirement owns all temporary references.
    if (staging_buffer) |buffer| self.deferred_releases.appendAssumeCapacity(buffer);
    const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);
    const encode_start = common_timing.now_ns();
    switch (cmd.direction) {
        .buffer_to_buffer => bridge.metal_bridge_blit_encoder_copy_region(self.streaming_blit_encoder, source_buffer, cmd.src.offset, destination_buffer, cmd.dst.offset, cmd.bytes),
        .buffer_to_texture => {
            const copy = plan.copy.?;
            const layout = plan.layout.?;
            bridge.metal_bridge_blit_encoder_copy_buffer_to_texture(self.streaming_blit_encoder, source_buffer, copy.offset, layout.pitch, layout.image_rows, destination_texture, copy.mip, copy.width, copy.height, copy.depth_or_layers, 0, 0, 0, copy.aspect);
        },
        .texture_to_buffer => {
            const copy = plan.copy.?;
            const layout = plan.layout.?;
            bridge.metal_bridge_blit_encoder_copy_texture_to_buffer(self.streaming_blit_encoder, source_texture, copy.mip, destination_buffer, copy.offset, layout.pitch, layout.image_rows, copy.width, copy.height, copy.depth_or_layers, 0, 0, 0, copy.aspect);
        },
        .texture_to_texture => {
            const copy = plan.copy.?;
            if (staging_buffer) |buffer| {
                const layout = plan.layout.?;
                bridge.metal_bridge_blit_encoder_copy_texture_to_buffer(self.streaming_blit_encoder, source_texture, cmd.src.mip_level, buffer, 0, layout.pitch, layout.image_rows, copy.width, copy.height, copy.depth_or_layers, 0, 0, 0, cmd.src.aspect);
                bridge.metal_bridge_blit_encoder_copy_buffer_to_texture(self.streaming_blit_encoder, buffer, 0, layout.pitch, layout.image_rows, destination_texture, cmd.dst.mip_level, copy.width, copy.height, copy.depth_or_layers, 0, 0, 0, cmd.dst.aspect);
            } else {
                bridge.metal_bridge_blit_encoder_copy_texture_to_texture(self.streaming_blit_encoder, source_texture, cmd.src.mip_level, destination_texture, cmd.dst.mip_level, copy.width, copy.height, copy.depth_or_layers);
            }
        },
    }
    // Ownership has transferred even if the subsequent flush reports a failure.
    staging_buffer = null;
    const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);
    self.has_deferred_submissions = true;
    self.streaming_has_copy = true;
    if (queue_sync_mode == .deferred) return .{ .setup_ns = setup_ns, .encode_ns = encode_ns, .submit_wait_ns = 0 };
    const flush = try self.flush_queue_timed();
    return .{ .setup_ns = setup_ns, .encode_ns = encode_ns, .submit_wait_ns = flush.submit_wait_ns, .gpu_elapsed_ns = flush.gpu_elapsed_ns, .gpu_timestamps_attempted = flush.gpu_timestamps_attempted, .gpu_timestamps_valid = flush.gpu_timestamps_valid };
}

fn validateExistingBuffer(self: anytype, handle: u64, size: u64) !void {
    if (self.compute_buffers.get(handle)) |buffer| {
        if (bridge.metal_bridge_buffer_length(buffer) < size) return error.InvalidArgument;
    }
}

fn requiredBufferSize(bytes: usize, offset: u64) !u64 {
    return std.math.add(u64, offset, bytes) catch error.InvalidArgument;
}

fn ensure_blit_encoder(self: anytype) !void {
    if (self.streaming_compute_encoder) |enc| {
        bridge.metal_bridge_end_compute_encoding(enc);
        self.streaming_compute_encoder = null;
    }
    if (self.streaming_render_encoder) |enc| {
        bridge.metal_bridge_render_encoder_end(enc);
        bridge.metal_bridge_release(enc);
        self.streaming_render_encoder = null;
    }
    if (self.streaming_blit_encoder != null) return;
    if (self.streaming_cmd_buf == null) {
        self.streaming_cmd_buf = bridge.metal_bridge_create_command_buffer(self.queue) orelse return error.InvalidState;
    }
    self.streaming_blit_encoder = bridge.metal_bridge_cmd_buf_blit_encoder(self.streaming_cmd_buf) orelse return error.InvalidState;
}

test "Metal copy plans use format blocks and the last accessed byte before native work" {
    const map: textures.Map = .{};
    var cmd = model.CopyCommand{ .direction = .texture_to_buffer, .src = .{ .handle = 1, .kind = .texture, .width = 3, .height = 2, .depth_or_array_layers = 2, .format = values.WGPUTextureFormat_R8Unorm }, .dst = .{ .handle = 2, .bytes_per_row = 8, .rows_per_image = 3, .offset = 4 }, .bytes = 35 };
    const plan = try Plan.init(&map, cmd);
    try std.testing.expectEqual(@as(u64, 35), plan.layout.?.required_bytes);
    cmd.bytes -= 1;
    try std.testing.expectError(error.TextureCopyRange, Plan.init(&map, cmd));
    cmd.src.width = 8;
    cmd.src.height = 8;
    cmd.src.format = values.WGPUTextureFormat_BC1RGBAUnorm;
    cmd.dst.bytes_per_row = 32;
    cmd.dst.rows_per_image = 3;
    cmd.dst.offset = 8;
    cmd.bytes = 144;
    const compressed = try Plan.init(&map, cmd);
    try std.testing.expectEqual(@as(u64, 144), compressed.layout.?.required_bytes);
    cmd.src.mip_level = 32;
    try std.testing.expectError(error.InvalidArgument, Plan.init(&map, cmd));
}

test "Metal temporary texture copies allocate padded volume rather than nominal bytes" {
    const map: textures.Map = .{};
    const source = model.CopyTextureResource{ .handle = 1, .kind = .texture, .width = 8, .height = 8, .depth_or_array_layers = 2, .mip_level = 1, .format = values.WGPUTextureFormat_RGBA8Unorm, .bytes_per_row = 256, .rows_per_image = 6 };
    var destination = source;
    destination.handle = 2;
    var cmd = model.CopyCommand{ .direction = .texture_to_texture, .src = source, .dst = destination, .bytes = 128, .uses_temporary_buffer = true, .temporary_buffer_alignment = 256 };
    const plan = try Plan.init(&map, cmd);
    try std.testing.expectEqual(@as(u32, 4), plan.copy.?.width);
    try std.testing.expectEqual(@as(u64, 2320), plan.layout.?.required_bytes);
    try std.testing.expectEqual(@as(u64, 2560), plan.staging_size);
    cmd.dst.format = values.WGPUTextureFormat_R32Float;
    try std.testing.expectError(error.InvalidArgument, Plan.init(&map, cmd));
    cmd.dst = destination;
    cmd.dst.mip_level = 0;
    try std.testing.expectError(error.TextureCopyRange, Plan.init(&map, cmd));
    try std.testing.expectError(error.InvalidArgument, requiredBufferSize(1, std.math.maxInt(u64)));
}
