const webgpu_plan_executor = @import("webgpu_plan_executor.zig");

pub fn main() !void {
    try webgpu_plan_executor.main();
}
