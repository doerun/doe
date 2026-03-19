const std = @import("std");
const model = @import("src/model.zig");
const vulkan = @import("src/backend/vulkan/native_runtime.zig");

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    var rt = try vulkan.NativeVulkanRuntime.init(allocator, "../../bench/kernels");
    defer rt.deinit();

    const words = try rt.load_kernel_spirv(allocator, "workgroup_atomic.wgsl");
    defer allocator.free(words);

    const bindings = [_]model.KernelBinding{.{
        .binding = 0,
        .group = 0,
        .resource_kind = .buffer,
        .resource_handle = 5001,
        .buffer_size = 1048576,
        .buffer_type = model.WGPUBufferBindingType_Storage,
    }};

    rt.set_compute_shader_spirv(words, null, &bindings, true) catch |err| {
        std.debug.print("set_compute_shader_spirv={s}\n", .{@errorName(err)});
        return;
    };
    std.debug.print("set_compute_shader_spirv=ok\n", .{});

    const metrics = rt.run_dispatch(1024, 1, 1, .per_command, .process_events, .off) catch |err| {
        std.debug.print("run_dispatch={s}\n", .{@errorName(err)});
        return;
    };
    std.debug.print("run_dispatch=ok encode={d} submit={d}\n", .{ metrics.encode_ns, metrics.submit_wait_ns });
}
