const std = @import("std");
const metal_instance = @import("../../src/backend/metal/metal_instance.zig");
const metal_adapter = @import("../../src/backend/metal/metal_adapter.zig");
const metal_device = @import("../../src/backend/metal/metal_device.zig");
const pipeline_cache = @import("../../src/backend/metal/pipeline/pipeline_cache.zig");
const metal_runtime_state = @import("../../src/backend/metal/metal_runtime_state.zig");

test "metal pipeline cache lookup succeeds" {
    metal_runtime_state.reset_state();
    try metal_instance.create_instance();
    try metal_adapter.select_adapter();
    try metal_device.create_device();
    try pipeline_cache.pipeline_cache_lookup();
}
