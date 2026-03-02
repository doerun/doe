const d3d12_adapter = @import("../../src/backend/d3d12/d3d12_adapter.zig");
const d3d12_device = @import("../../src/backend/d3d12/d3d12_device.zig");
const d3d12_instance = @import("../../src/backend/d3d12/d3d12_instance.zig");

test "d3d12 instance bootstrap succeeds" {
    try d3d12_instance.create_instance();
    try d3d12_adapter.select_adapter();
    try d3d12_device.create_device();
}
