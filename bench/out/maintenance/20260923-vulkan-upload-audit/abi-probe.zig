const std = @import("std");
const native = @cImport({ @cInclude("vulkan/vulkan_core.h"); });
test "Vulkan structures and handles match the installed Khronos header ABI" {
    @setEvalBranchQuota(100000);
    inline for (.{ @import("src/backend/vulkan/vk_structs.zig"), @import("src/backend/vulkan/vulkan_types.zig") }) |module| {
        inline for (@typeInfo(module).@"struct".decls) |decl| {
            if (comptime std.mem.startsWith(u8, decl.name, "Vk") and !std.mem.eql(u8, decl.name, "VkAllocationCallbacks")) {
                const owned = @field(module, decl.name);
                const reference = @field(native, decl.name);
                try std.testing.expectEqual(@sizeOf(reference), @sizeOf(owned));
                try std.testing.expectEqual(@alignOf(reference), @alignOf(owned));
                switch (@typeInfo(owned)) {
                    .@"struct" => |info| inline for (info.fields) |field| {
                        try std.testing.expectEqual(@offsetOf(reference, field.name), @offsetOf(owned, field.name));
                        try std.testing.expectEqual(@sizeOf(@FieldType(reference, field.name)), @sizeOf(field.type));
                    },
                    .@"union" => |info| inline for (info.fields) |field| {
                        try std.testing.expectEqual(@sizeOf(@FieldType(reference, field.name)), @sizeOf(field.type));
                    },
                    else => {},
                }
            }
        }
    }
}
