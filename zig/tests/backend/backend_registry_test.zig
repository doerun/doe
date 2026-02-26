const std = @import("std");
const backend_ids = @import("../../src/backend/backend_ids.zig");

test "backend id names are stable" {
    try std.testing.expectEqualStrings("dawn_oracle", backend_ids.backend_id_name(.dawn_oracle));
    try std.testing.expectEqualStrings("zig_metal", backend_ids.backend_id_name(.zig_metal));
    try std.testing.expectEqualStrings("zig_vulkan", backend_ids.backend_id_name(.zig_vulkan));
}
