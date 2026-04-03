const m0 = @import("doe_native_object_helpers.zig");
const m1 = @import("doe_native_runtime_helpers.zig");

pub const alloc = m0.alloc;
pub const label_store = m0.label_store;
pub const make = m0.make;
pub const cast = m0.cast;
pub const object_add_ref = m0.object_add_ref;
pub const object_should_destroy = m0.object_should_destroy;
pub const toOpaque = m0.toOpaque;
pub const device_vk_runtime = m1.device_vk_runtime;
pub const device_d3d12_runtime = m1.device_d3d12_runtime;
