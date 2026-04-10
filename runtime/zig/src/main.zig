const runtime_cli = @import("cli/runtime_cli.zig");

pub fn main() !void {
    try runtime_cli.runCli();
}
