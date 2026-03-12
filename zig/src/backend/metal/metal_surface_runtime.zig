const std = @import("std");
const common_timing = @import("../common/timing.zig");
const model = @import("../../model.zig");
const bridge = @import("metal_bridge_decls.zig");
const metal_bridge_command_buffer_commit = bridge.metal_bridge_command_buffer_commit;
const metal_bridge_command_buffer_wait_completed = bridge.metal_bridge_command_buffer_wait_completed;
const metal_bridge_create_command_buffer = bridge.metal_bridge_create_command_buffer;
const metal_bridge_device_new_render_target = bridge.metal_bridge_device_new_render_target;
const metal_bridge_release = bridge.metal_bridge_release;

pub const SurfaceState = struct {
    texture: ?*anyopaque = null,
    width: u32 = 0,
    height: u32 = 0,
    format: u32 = 0,
    configured: bool = false,
    acquired: bool = false,
};

pub fn create_surface(self: anytype, cmd: model.SurfaceCreateCommand) !void {
    _ = try surface_entry(self, cmd.handle);
}

pub fn surface_capabilities(self: anytype, cmd: model.SurfaceCapabilitiesCommand) !void {
    _ = try surface_entry(self, cmd.handle);
}

pub fn configure_surface(self: anytype, cmd: model.SurfaceConfigureCommand) !void {
    var entry = try surface_entry(self, cmd.handle);
    if (entry.texture != null and entry.width == cmd.width and entry.height == cmd.height and entry.format == cmd.format) {
        entry.configured = true;
        entry.acquired = false;
        return;
    }
    if (entry.texture) |texture| {
        try defer_or_release(self, texture);
        entry.texture = null;
    }
    entry.texture = metal_bridge_device_new_render_target(self.device, cmd.width, cmd.height, cmd.format) orelse return error.InvalidState;
    entry.width = cmd.width;
    entry.height = cmd.height;
    entry.format = cmd.format;
    entry.configured = true;
    entry.acquired = false;
}

pub fn acquire_surface(self: anytype, cmd: model.SurfaceAcquireCommand) !void {
    var entry = try surface_entry(self, cmd.handle);
    if (!entry.configured or entry.texture == null) return error.SurfaceUnavailable;
    entry.acquired = true;
}

pub fn present_surface(self: anytype, cmd: model.SurfacePresentCommand) !u64 {
    var entry = try surface_entry(self, cmd.handle);
    if (!entry.configured or !entry.acquired or entry.texture == null) return error.SurfaceUnavailable;
    const start_ns = common_timing.now_ns();
    const cmd_buf = metal_bridge_create_command_buffer(self.queue) orelse return error.InvalidState;
    metal_bridge_command_buffer_commit(cmd_buf);
    metal_bridge_command_buffer_wait_completed(cmd_buf);
    metal_bridge_release(cmd_buf);
    entry.acquired = false;
    return common_timing.ns_delta(common_timing.now_ns(), start_ns);
}

pub fn unconfigure_surface(self: anytype, cmd: model.SurfaceUnconfigureCommand) !void {
    var entry = try surface_entry(self, cmd.handle);
    if (entry.texture) |texture| {
        try defer_or_release(self, texture);
        entry.texture = null;
    }
    entry.configured = false;
    entry.acquired = false;
    entry.width = 0;
    entry.height = 0;
    entry.format = 0;
}

pub fn release_surface(self: anytype, cmd: model.SurfaceReleaseCommand) !void {
    if (self.surfaces.fetchRemove(cmd.handle)) |removed| {
        if (removed.value.texture) |texture| {
            try defer_or_release(self, texture);
        }
    }
}

fn surface_entry(self: anytype, handle: u64) !*SurfaceState {
    const gop = try self.surfaces.getOrPut(self.allocator, handle);
    if (!gop.found_existing) {
        gop.value_ptr.* = .{};
    }
    return gop.value_ptr;
}

fn defer_or_release(self: anytype, obj: ?*anyopaque) !void {
    if (self.streaming_cmd_buf != null or self.outstanding_cmd_buf != null) {
        try self.deferred_releases.append(self.allocator, obj);
        return;
    }
    metal_bridge_release(obj);
}
