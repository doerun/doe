const d3d12_queue = @import("../../src/backend/d3d12/d3d12_queue.zig");
const d3d12_sync = @import("../../src/backend/d3d12/d3d12_sync.zig");

test "d3d12 sync operations succeed" {
    try d3d12_queue.submit();
    try d3d12_sync.wait_for_completion();
}
