const vulkan_surface_create = @import("../../src/backend/vulkan/surface/surface_create.zig");
const vulkan_surface_configure = @import("../../src/backend/vulkan/surface/surface_configure.zig");
const vulkan_surface_present = @import("../../src/backend/vulkan/surface/present.zig");

test "vulkan surface lifecycle ops succeed" {
    try vulkan_surface_create.create_surface();
    try vulkan_surface_configure.get_surface_capabilities();
    try vulkan_surface_configure.configure_surface();
    try vulkan_surface_configure.unconfigure_surface();
    try vulkan_surface_present.acquire_surface();
    try vulkan_surface_present.present_surface();
    try vulkan_surface_present.release_surface();
}
