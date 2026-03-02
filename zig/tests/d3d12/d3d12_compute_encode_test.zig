const d3d12_compute_encode = @import("../../src/backend/d3d12/commands/compute_encode.zig");

test "d3d12 compute encode succeeds" {
    try d3d12_compute_encode.encode_compute();
}
