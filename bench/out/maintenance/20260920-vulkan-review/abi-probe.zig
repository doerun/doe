const std = @import("std");
const cap = @import("src/backend/vulkan/vk_capability_structs.zig");
const native = @cImport({ @cInclude("vulkan/vulkan_core.h"); });
test "Vulkan capability ABI matches installed Khronos headers" {
    @setEvalBranchQuota(100000);
    inline for (@typeInfo(cap).@"struct".decls) |decl| {
        if (comptime std.mem.startsWith(u8, decl.name, "Vk")) {
            const owned = @field(cap, decl.name);
            const reference = @field(native, decl.name);
            try std.testing.expectEqual(@sizeOf(reference), @sizeOf(owned));
            try std.testing.expectEqual(@alignOf(reference), @alignOf(owned));
            inline for (@typeInfo(owned).@"struct".fields) |field| {
                try std.testing.expectEqual(@offsetOf(reference, field.name), @offsetOf(owned, field.name));
                try std.testing.expectEqual(@sizeOf(@FieldType(reference, field.name)), @sizeOf(field.type));
            }
        }
    }
}
test "Vulkan constants and format codes match installed Khronos headers" {
    @setEvalBranchQuota(100000);
    inline for (.{ @import("src/backend/vulkan/vk_constants.zig"), @import("src/backend/vulkan/vk_formats.zig") }) |module| {
        inline for (@typeInfo(module).@"struct".decls) |decl| {
            if (comptime std.mem.startsWith(u8, decl.name, "VK_") and @hasDecl(native, decl.name)) {
                const value = @field(module, decl.name);
                switch (@typeInfo(@TypeOf(value))) {
                    .int, .comptime_int => try std.testing.expectEqual(@as(i128, @field(native, decl.name)), @as(i128, value)),
                    else => {},
                }
            }
        }
    }
}
