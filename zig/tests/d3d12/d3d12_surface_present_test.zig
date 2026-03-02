const d3d12_surface_create = @import("../../src/backend/d3d12/surface/surface_create.zig");
const d3d12_surface_configure = @import("../../src/backend/d3d12/surface/surface_configure.zig");
const d3d12_surface_present = @import("../../src/backend/d3d12/surface/present.zig");

test "d3d12 surface lifecycle ops succeed" {
    try d3d12_surface_create.create_surface();
    try d3d12_surface_configure.get_surface_capabilities();
    try d3d12_surface_configure.configure_surface();
    try d3d12_surface_configure.unconfigure_surface();
    try d3d12_surface_present.acquire_surface();
    try d3d12_surface_present.present_surface();
    try d3d12_surface_present.release_surface();
}
