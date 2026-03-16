const std = @import("std");
const metal_instance = @import("../../src/backend/metal/metal_instance.zig");
const metal_adapter = @import("../../src/backend/metal/metal_adapter.zig");
const metal_device = @import("../../src/backend/metal/metal_device.zig");
const surface_create = @import("../../src/backend/metal/surface/surface_create.zig");
const surface_configure = @import("../../src/backend/metal/surface/surface_configure.zig");
const present = @import("../../src/backend/metal/surface/present.zig");
const metal_runtime_state = @import("../../src/backend/metal/metal_runtime_state.zig");

test "metal present succeeds" {
    metal_runtime_state.reset_state();
    try metal_instance.create_instance();
    try metal_adapter.select_adapter();
    try metal_device.create_device();
    try surface_create.create_surface();
    try surface_configure.configure_surface();
    try present.present_surface();
}
