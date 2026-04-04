const builtin = @import("builtin");
const surface_ops = @import("../../backend/dropin_surface_ops.zig");
const metal_bridge_configure_surface_host = surface_ops.metal_bridge_configure_surface_host;
const metal_bridge_create_surface_host = surface_ops.metal_bridge_create_surface_host;
const metal_bridge_release = surface_ops.metal_bridge_release;

pub const ManagedPlatformSurface = struct {
    retained_host: ?*anyopaque,
    layer: ?*anyopaque,
};

pub fn createPlatformSurface() !?ManagedPlatformSurface {
    if (builtin.os.tag != .macos) return null;
    var layer: ?*anyopaque = null;
    const retained_host = metal_bridge_create_surface_host(&layer) orelse return error.SurfaceCreationFailed;
    return .{
        .retained_host = retained_host,
        .layer = layer,
    };
}

pub fn configureSurfaceLayer(retained_host: ?*anyopaque, width: u32, height: u32) void {
    if (builtin.os.tag != .macos) return;
    if (retained_host == null) return;
    metal_bridge_configure_surface_host(retained_host, width, height);
}

pub fn releasePlatformSurface(platform_surface: ?ManagedPlatformSurface) void {
    if (builtin.os.tag != .macos) return;
    if (platform_surface) |surface| {
        metal_bridge_release(surface.retained_host);
    }
}
