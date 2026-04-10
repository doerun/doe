const webgpu_plan_executor = @import("webgpu_plan_executor.zig");
const webgpu_plan_executor_cli = @import("plan/webgpu_plan_executor_cli.zig");

pub fn main() !void {
    try webgpu_plan_executor_cli.runCli(webgpu_plan_executor.runPlan);
}
