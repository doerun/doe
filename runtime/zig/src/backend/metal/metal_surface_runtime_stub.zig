const model = @import("../../model.zig");

pub const SurfaceState = struct {
    texture: ?*anyopaque = null,
    width: u32 = 0,
    height: u32 = 0,
    format: u32 = 0,
    configured: bool = false,
    acquired: bool = false,
};

pub fn create_surface(self: anytype, cmd: model.SurfaceCreateCommand) !void {
    _ = self;
    _ = cmd;
    return error.UnsupportedFeature;
}

pub fn surface_capabilities(self: anytype, cmd: model.SurfaceCapabilitiesCommand) !void {
    _ = self;
    _ = cmd;
    return error.UnsupportedFeature;
}

pub fn configure_surface(self: anytype, cmd: model.SurfaceConfigureCommand) !void {
    _ = self;
    _ = cmd;
    return error.UnsupportedFeature;
}

pub fn acquire_surface(self: anytype, cmd: model.SurfaceAcquireCommand) !void {
    _ = self;
    _ = cmd;
    return error.UnsupportedFeature;
}

pub fn present_surface(self: anytype, cmd: model.SurfacePresentCommand) !u64 {
    _ = self;
    _ = cmd;
    return error.UnsupportedFeature;
}

pub fn unconfigure_surface(self: anytype, cmd: model.SurfaceUnconfigureCommand) !void {
    _ = self;
    _ = cmd;
    return error.UnsupportedFeature;
}

pub fn release_surface(self: anytype, cmd: model.SurfaceReleaseCommand) !void {
    _ = self;
    _ = cmd;
    return error.UnsupportedFeature;
}
