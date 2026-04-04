const builtin = @import("builtin");
const metal_bridge_mod = @import("metal/metal_bridge_decls.zig");
const vk_surface_mod = if (builtin.os.tag == .linux) @import("vulkan/vulkan_surface.zig") else struct {};

pub const metal_bridge_create_surface_host = metal_bridge_mod.metal_bridge_create_surface_host;
pub const metal_bridge_configure_surface_host = metal_bridge_mod.metal_bridge_configure_surface_host;
pub const metal_bridge_release = metal_bridge_mod.metal_bridge_release;
pub const create_wayland_surface = if (builtin.os.tag == .linux) vk_surface_mod.create_wayland_surface else {};
pub const create_xcb_surface = if (builtin.os.tag == .linux) vk_surface_mod.create_xcb_surface else {};
