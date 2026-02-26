const std = @import("std");
const metal_instance = @import("../../src/backend/metal/metal_instance.zig");
const metal_adapter = @import("../../src/backend/metal/metal_adapter.zig");
const metal_device = @import("../../src/backend/metal/metal_device.zig");
const compute_encode = @import("../../src/backend/metal/commands/compute_encode.zig");
const timing = @import("../../src/backend/metal/metal_timing.zig");
const metal_runtime_state = @import("../../src/backend/metal/metal_runtime_state.zig");

test "metal timing returns immediate timing sample" {
    metal_runtime_state.reset_state();
    try metal_instance.create_instance();
    try metal_adapter.select_adapter();
    try metal_device.create_device();
    try compute_encode.encode_compute();
    const ns = try timing.operation_timing_ns();
    try std.testing.expectEqual(@as(u64, 7_500), ns);
}
