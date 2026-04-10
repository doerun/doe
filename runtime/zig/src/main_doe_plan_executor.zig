const doe_plan_executor = @import("doe_plan_executor.zig");
const doe_plan_executor_cli = @import("cli/doe_plan_executor_cli.zig");

pub fn main() !void {
    try doe_plan_executor_cli.runCli(doe_plan_executor.runPlan);
}
