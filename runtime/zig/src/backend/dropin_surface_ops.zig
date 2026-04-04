const builtin = @import("builtin");
const vk_surface_mod = if (builtin.os.tag == .linux) @import("vulkan/vulkan_surface.zig") else struct {};

pub const create_wayland_surface = if (builtin.os.tag == .linux) vk_surface_mod.create_wayland_surface else {};
pub const create_xcb_surface = if (builtin.os.tag == .linux) vk_surface_mod.create_xcb_surface else {};
