const std = @import("std");
const runtime = @import("src/backend/vulkan/native_runtime.zig");
const upload = @import("src/backend/vulkan/vk_upload.zig");
const c = @import("src/backend/vulkan/vk_constants.zig");
extern fn audit_begin() void;
extern fn audit_fail(c_int) void;
extern fn audit_buffers() i64;
extern fn audit_memories() i64;
extern fn audit_mappings() i64;
extern fn audit_end() void;
const BYTES = 4096;

test "upload fault sweep releases fresh and pooled native acquisitions" {
    for ([_]bool{ false, true }) |pooled| {
        const steps: usize = if (pooled) 3 else 7;
        for (1..steps + 1) |step| {
            var rt = try runtime.NativeVulkanRuntime.init(std.testing.allocator, null);
            audit_begin();
            if (pooled) {
                try upload.prewarm_staged_upload_pool(&rt, BYTES, c.VK_BUFFER_USAGE_TRANSFER_DST_BIT);
                upload.release_pool_entry(rt.device, rt.hot_dst_pool_entry);
                rt.hot_dst_pool_entry = null;
                rt.hot_dst_pool_size = 0;
            }
            audit_fail(@intCast(step));
            const result = upload.prewarm_staged_upload_pool(&rt, BYTES, c.VK_BUFFER_USAGE_TRANSFER_DST_BIT);
            audit_fail(0);
            rt.deinit();
            const live_buffers = audit_buffers();
            const live_memories = audit_memories();
            const live_mappings = audit_mappings();
            audit_end();
            std.debug.print("pooled={} step={} buffers={} memories={} mappings={}\n", .{ pooled, step, live_buffers, live_memories, live_mappings });
            try std.testing.expectError(error.InvalidState, result);
            try std.testing.expectEqual(@as(i64, 0), live_buffers);
            try std.testing.expectEqual(@as(i64, 0), live_memories);
            try std.testing.expectEqual(@as(i64, 0), live_mappings);
        }
    }
}

test "upload fault during fast-buffer replacement preserves the working buffer" {
    for (1..5) |step| {
        var rt = try runtime.NativeVulkanRuntime.init(std.testing.allocator, null);
        audit_begin();
        try upload.ensure_fast_upload_buffer(&rt, BYTES);
        const old_buffer = rt.fast_upload_buffer;
        const old_memory = rt.fast_upload_memory;
        const old_mapping = rt.fast_upload_mapped;
        audit_fail(@intCast(step));
        const result = upload.ensure_fast_upload_buffer(&rt, BYTES * 2);
        audit_fail(0);
        const preserved = old_buffer == rt.fast_upload_buffer and old_memory == rt.fast_upload_memory and old_mapping == rt.fast_upload_mapped and rt.fast_upload_capacity == BYTES;
        try upload.ensure_fast_upload_buffer(&rt, BYTES * 2);
        rt.deinit();
        const live_buffers = audit_buffers();
        const live_memories = audit_memories();
        const live_mappings = audit_mappings();
        audit_end();
        std.debug.print("fast step={} preserved={} buffers={} memories={} mappings={}\n", .{ step, preserved, live_buffers, live_memories, live_mappings });
        try std.testing.expectError(error.InvalidState, result);
        try std.testing.expect(preserved);
        try std.testing.expectEqual(@as(i64, 0), live_buffers);
        try std.testing.expectEqual(@as(i64, 0), live_memories);
        try std.testing.expectEqual(@as(i64, 0), live_mappings);
    }
}
