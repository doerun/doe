const module_runner_cli = @import("cli/module_runner_cli.zig");

pub const RunnerError = module_runner_cli.RunnerError;

pub fn main() !void {
    try module_runner_cli.runCli();
}
